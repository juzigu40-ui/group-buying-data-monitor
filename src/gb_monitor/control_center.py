from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover - depends on local Python build
    tk = None
    messagebox = None
    ttk = None


@dataclass(slots=True)
class StoreTargetConfig:
    store_id: str
    store_name: str
    daily_target_count: int
    require_source_store: bool


@dataclass(slots=True)
class PlatformBindingConfig:
    store_id: str
    store_name: str
    platform: str
    auth_mode: str
    account_alias: str
    login_owner: str
    enabled: bool


ENV_FIELD_ORDER = [
    "GBM_FEISHU_WEBHOOK",
    "GBM_FEISHU_AT_MOBILES",
    "GBM_SIGNAL_WINDOW_START",
    "GBM_SIGNAL_WINDOW_END",
    "GBM_SIGNAL_INTERVAL_MINUTES",
    "GBM_REVIEW_WINDOW_START",
    "GBM_REVIEW_WINDOW_END",
    "GBM_REVIEW_INTERVAL_MINUTES",
    "GBM_DELIVERY_LUNCH_START",
    "GBM_DELIVERY_LUNCH_END",
    "GBM_DELIVERY_DINNER_START",
    "GBM_DELIVERY_DINNER_END",
    "GBM_DELIVERY_INTERVAL_MINUTES",
]

TIME_FIELDS = {
    "GBM_SIGNAL_WINDOW_START",
    "GBM_SIGNAL_WINDOW_END",
    "GBM_REVIEW_WINDOW_START",
    "GBM_REVIEW_WINDOW_END",
    "GBM_DELIVERY_LUNCH_START",
    "GBM_DELIVERY_LUNCH_END",
    "GBM_DELIVERY_DINNER_START",
    "GBM_DELIVERY_DINNER_END",
}

INTERVAL_FIELDS = {
    "GBM_SIGNAL_INTERVAL_MINUTES",
    "GBM_REVIEW_INTERVAL_MINUTES",
    "GBM_DELIVERY_INTERVAL_MINUTES",
}


def load_env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def save_env_values(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(updates)
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in pending:
            new_lines.append(f"{key}={pending.pop(key)}")
        else:
            new_lines.append(line)
    if pending:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        for key in ENV_FIELD_ORDER:
            if key in pending:
                new_lines.append(f"{key}={pending.pop(key)}")
        for key, value in pending.items():
            new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def load_store_targets(path: Path) -> list[StoreTargetConfig]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, StoreTargetConfig] = {}
    for item in payload.get("stores", []):
        store_id = str(item.get("store_id", "")).strip()
        if not store_id:
            continue
        existing = grouped.get(store_id)
        target = int(item.get("daily_target_count", 0) or 0)
        require_source = bool(item.get("require_source_store", False))
        if existing is None:
            grouped[store_id] = StoreTargetConfig(
                store_id=store_id,
                store_name=str(item.get("store_name", "")).strip() or store_id,
                daily_target_count=max(target, 0),
                require_source_store=require_source,
            )
            continue
        existing.daily_target_count = max(existing.daily_target_count, target)
        existing.require_source_store = existing.require_source_store or require_source
    return sorted(grouped.values(), key=lambda item: (item.store_name, item.store_id))


def save_store_targets(path: Path, targets: list[StoreTargetConfig]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    target_map = {item.store_id: item for item in targets}
    for item in payload.get("stores", []):
        store_id = str(item.get("store_id", "")).strip()
        target = target_map.get(store_id)
        if target is None:
            continue
        item["daily_target_count"] = max(target.daily_target_count, 0)
        item["require_source_store"] = bool(target.require_source_store)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_registry_bindings(path: Path) -> list[PlatformBindingConfig]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[PlatformBindingConfig] = []
    for store in payload.get("stores", []):
        store_id = str(store.get("store_id", "")).strip()
        store_name = str(store.get("store_name", "")).strip() or store_id
        platforms = store.get("platforms", {})
        if not isinstance(platforms, dict):
            continue
        for platform, conf in sorted(platforms.items()):
            if not isinstance(conf, dict):
                continue
            rows.append(
                PlatformBindingConfig(
                    store_id=store_id,
                    store_name=store_name,
                    platform=str(platform).strip(),
                    auth_mode=str(conf.get("auth_mode", "manual")).strip() or "manual",
                    account_alias=str(conf.get("account_alias", "")).strip(),
                    login_owner=str(conf.get("login_owner", "")).strip(),
                    enabled=bool(conf.get("enabled", True)),
                )
            )
    return rows


def save_registry_bindings(path: Path, bindings: list[PlatformBindingConfig]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    binding_map = {(item.store_id, item.platform): item for item in bindings}
    for store in payload.get("stores", []):
        store_id = str(store.get("store_id", "")).strip()
        platforms = store.get("platforms", {})
        if not isinstance(platforms, dict):
            continue
        for platform, conf in platforms.items():
            binding = binding_map.get((store_id, str(platform).strip()))
            if binding is None or not isinstance(conf, dict):
                continue
            conf["auth_mode"] = binding.auth_mode
            conf["account_alias"] = binding.account_alias
            conf["login_owner"] = binding.login_owner
            conf["enabled"] = bool(binding.enabled)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_env_file(env_path: Path, example_path: Path) -> None:
    if env_path.exists():
        return
    if example_path.exists():
        env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        return
    env_path.write_text("", encoding="utf-8")


def resolve_python(root_dir: Path) -> Path:
    if os.name == "nt":
        candidate = root_dir / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = root_dir / ".venv" / "bin" / "python"
    if candidate.exists():
        return candidate
    return Path(sys.executable)


def build_runtime_env(root_dir: Path, profile_dir: Path, env_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root_dir / "src")
    env.update(load_env_values(env_path))
    env["GBM_STORE_REGISTRY"] = str(profile_dir / "stores_registry.json")
    signal_rules = profile_dir / "store_signal_rules.json"
    if signal_rules.exists():
        env["GBM_SIGNAL_RULES"] = str(signal_rules)
    snapshot_dir = profile_dir / "snapshots"
    snapshot_map = {
        "GBM_DIANGPING_FILE": snapshot_dir / "review_dianping.json",
        "GBM_DOUYIN_FILE": snapshot_dir / "review_douyin.json",
        "GBM_AMAP_FILE": snapshot_dir / "review_amap.json",
        "GBM_MEITUAN_FILE": snapshot_dir / "delivery_meituan.json",
        "GBM_ELEME_FILE": snapshot_dir / "delivery_eleme.json",
        "GBM_JDWM_FILE": snapshot_dir / "delivery_jdwm.json",
    }
    for key, path in snapshot_map.items():
        if path.exists():
            env[key] = str(path)
    return env


def open_path(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(path)])


def _is_valid_hhmm(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return False
    hour, minute = int(parts[0]), int(parts[1])
    return 0 <= hour <= 23 and 0 <= minute <= 59


class ControlCenterApp:
    def __init__(self, root_dir: Path, profile_dir: Path, env_path: Path, rules_path: Path, registry_path: Path) -> None:
        if tk is None or messagebox is None or ttk is None:
            raise RuntimeError(
                "当前 Python 环境缺少 tkinter，无法启动可视化控制台。请安装带 Tk 的 Python，或先用命令行脚本运行。"
            )
        self.root_dir = root_dir
        self.profile_dir = profile_dir
        self.env_path = env_path
        self.rules_path = rules_path
        self.registry_path = registry_path
        self.output_queue: Queue[str] = Queue()
        self.running = False

        ensure_env_file(self.env_path, self.root_dir / ".env.example")
        self.env_values = load_env_values(self.env_path)
        self.store_targets = load_store_targets(self.rules_path)
        self.registry_bindings = load_registry_bindings(self.registry_path)

        self.root = tk.Tk()
        self.root.title("门店监控控制台")
        self.root.geometry("1020x780")

        self.entries: dict[str, tk.Entry] = {}
        self.target_entries: dict[str, tk.Entry] = {}
        self.target_source_flags: dict[str, tk.BooleanVar] = {}
        self.binding_auth_modes: dict[tuple[str, str], tk.StringVar] = {}
        self.binding_account_entries: dict[tuple[str, str], tk.Entry] = {}
        self.binding_owner_entries: dict[tuple[str, str], tk.Entry] = {}
        self.binding_enabled_flags: dict[tuple[str, str], tk.BooleanVar] = {}

        self._build_ui()
        self.root.after(120, self._flush_output)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        intro = (
            "先保存配置，再点按钮运行。验证码仍在平台登录页里输入；"
            "这个控制台负责飞书、时间段、频率、门店平台绑定、门店目标和一键安装/验收。"
        )
        ttk.Label(container, text=intro, wraplength=940, justify="left").pack(anchor="w", pady=(0, 10))

        top = ttk.Frame(container)
        top.pack(fill="x", pady=(0, 12))
        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(top)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))

        self._build_basic_settings(left)
        self._build_schedule_settings(right)
        self._build_registry_bindings(container)
        self._build_store_targets(container)
        self._build_actions(container)
        self._build_output(container)

    def _build_basic_settings(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="基础配置", padding=10)
        frame.pack(fill="both", expand=True)
        fields = [
            ("GBM_FEISHU_WEBHOOK", "飞书 Webhook"),
            ("GBM_FEISHU_AT_MOBILES", "飞书 @ 手机号（逗号分隔）"),
        ]
        for idx, (key, label) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", pady=6)
            entry = ttk.Entry(frame, width=52)
            entry.insert(0, self.env_values.get(key, ""))
            entry.grid(row=idx, column=1, sticky="ew", pady=6, padx=(8, 0))
            self.entries[key] = entry
        frame.columnconfigure(1, weight=1)

    def _build_schedule_settings(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="时间段和频率", padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="频率直接填分钟：30=每30分钟，60=每1小时，120=每2小时。",
            wraplength=380,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        fields = [
            ("GBM_SIGNAL_WINDOW_START", "内容开始时间"),
            ("GBM_SIGNAL_WINDOW_END", "内容结束时间"),
            ("GBM_SIGNAL_INTERVAL_MINUTES", "内容频率（分钟）"),
            ("GBM_REVIEW_WINDOW_START", "评价开始时间"),
            ("GBM_REVIEW_WINDOW_END", "评价结束时间"),
            ("GBM_REVIEW_INTERVAL_MINUTES", "评价频率（分钟）"),
            ("GBM_DELIVERY_LUNCH_START", "外卖午市开始"),
            ("GBM_DELIVERY_LUNCH_END", "外卖午市结束"),
            ("GBM_DELIVERY_DINNER_START", "外卖晚市开始"),
            ("GBM_DELIVERY_DINNER_END", "外卖晚市结束"),
            ("GBM_DELIVERY_INTERVAL_MINUTES", "外卖频率（分钟）"),
        ]
        for idx, (key, label) in enumerate(fields, start=1):
            ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            entry = ttk.Entry(frame, width=24)
            entry.insert(0, self.env_values.get(key, ""))
            entry.grid(row=idx, column=1, sticky="ew", pady=4, padx=(8, 0))
            self.entries[key] = entry
        frame.columnconfigure(1, weight=1)

    def _build_store_targets(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="门店 KPI", padding=10)
        frame.pack(fill="x", pady=(0, 12))
        ttk.Label(frame, text="门店").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="每日目标条数").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(frame, text="仅统计门店来源").grid(row=0, column=2, sticky="w", padx=(12, 0))
        for idx, target in enumerate(self.store_targets, start=1):
            ttk.Label(frame, text=target.store_name).grid(row=idx, column=0, sticky="w", pady=4)
            entry = ttk.Entry(frame, width=12)
            entry.insert(0, str(target.daily_target_count))
            entry.grid(row=idx, column=1, sticky="w", padx=(12, 0), pady=4)
            flag = tk.BooleanVar(value=target.require_source_store)
            ttk.Checkbutton(frame, variable=flag).grid(row=idx, column=2, sticky="w", padx=(20, 0), pady=4)
            self.target_entries[target.store_id] = entry
            self.target_source_flags[target.store_id] = flag

    def _build_registry_bindings(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="门店平台绑定", padding=10)
        frame.pack(fill="x", pady=(0, 12))
        headings = ["门店", "平台", "接入方式", "账号标识", "负责人", "启用"]
        for col, title in enumerate(headings):
            ttk.Label(frame, text=title).grid(row=0, column=col, sticky="w", padx=(0, 8))

        auth_options = ("api", "cookie", "manual")
        for idx, binding in enumerate(self.registry_bindings, start=1):
            key = (binding.store_id, binding.platform)
            ttk.Label(frame, text=binding.store_name).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Label(frame, text=binding.platform).grid(row=idx, column=1, sticky="w", pady=4, padx=(8, 0))

            auth_var = tk.StringVar(value=binding.auth_mode)
            auth_box = ttk.Combobox(frame, textvariable=auth_var, values=auth_options, width=10, state="readonly")
            auth_box.grid(row=idx, column=2, sticky="w", padx=(8, 0), pady=4)
            self.binding_auth_modes[key] = auth_var

            account_entry = ttk.Entry(frame, width=22)
            account_entry.insert(0, binding.account_alias)
            account_entry.grid(row=idx, column=3, sticky="ew", padx=(8, 0), pady=4)
            self.binding_account_entries[key] = account_entry

            owner_entry = ttk.Entry(frame, width=18)
            owner_entry.insert(0, binding.login_owner)
            owner_entry.grid(row=idx, column=4, sticky="ew", padx=(8, 0), pady=4)
            self.binding_owner_entries[key] = owner_entry

            enabled_var = tk.BooleanVar(value=binding.enabled)
            ttk.Checkbutton(frame, variable=enabled_var).grid(row=idx, column=5, sticky="w", padx=(18, 0), pady=4)
            self.binding_enabled_flags[key] = enabled_var

        frame.columnconfigure(3, weight=1)
        frame.columnconfigure(4, weight=1)

    def _build_actions(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="操作", padding=10)
        frame.pack(fill="x", pady=(0, 12))
        buttons: list[tuple[str, Callable[[], None]]] = [
            ("保存配置", self.save_settings),
            ("一键安装", lambda: self.run_task("安装环境", self.install_environment)),
            ("测试飞书", lambda: self.run_task("测试飞书", self.test_feishu)),
            ("运行验收", lambda: self.run_task("运行验收", self.run_acceptance)),
            ("打开结果目录", self.open_results),
            ("打开登录清单", self.open_login_checklist),
        ]
        for idx, (label, action) in enumerate(buttons):
            ttk.Button(frame, text=label, command=action).grid(row=0, column=idx, padx=(0, 8), pady=4)

    def _build_output(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="运行输出", padding=10)
        frame.pack(fill="both", expand=True)
        self.output = tk.Text(frame, height=20, wrap="word")
        self.output.pack(fill="both", expand=True)
        self.output.insert("end", "控制台已启动。建议先点“保存配置”，再点“一键安装”。\n")
        self.output.configure(state="disabled")

    def _append_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _flush_output(self) -> None:
        while True:
            try:
                line = self.output_queue.get_nowait()
            except Empty:
                break
            self._append_output(line)
        self.root.after(120, self._flush_output)

    def _log(self, text: str) -> None:
        self.output_queue.put(text.rstrip() + "\n")

    def save_settings(self, notify: bool = True) -> bool:
        updates = {key: entry.get().strip() for key, entry in self.entries.items()}
        for key in TIME_FIELDS:
            value = updates.get(key, "")
            if value and not _is_valid_hhmm(value):
                messagebox.showerror("保存失败", f"{key} 必须是 HH:MM 格式，例如 10:30")
                return False
        for key in INTERVAL_FIELDS:
            value = updates.get(key, "")
            if not value:
                continue
            try:
                minutes = int(value)
            except ValueError:
                messagebox.showerror("保存失败", f"{key} 必须是整数分钟，例如 30 或 60")
                return False
            if minutes <= 0:
                messagebox.showerror("保存失败", f"{key} 必须大于 0")
                return False
        save_env_values(self.env_path, updates)

        bindings: list[PlatformBindingConfig] = []
        for item in self.registry_bindings:
            key = (item.store_id, item.platform)
            account_alias = self.binding_account_entries[key].get().strip()
            login_owner = self.binding_owner_entries[key].get().strip()
            if not account_alias:
                messagebox.showerror("保存失败", f"{item.store_name}-{item.platform} 的账号标识不能为空")
                return False
            if not login_owner:
                messagebox.showerror("保存失败", f"{item.store_name}-{item.platform} 的负责人不能为空")
                return False
            bindings.append(
                PlatformBindingConfig(
                    store_id=item.store_id,
                    store_name=item.store_name,
                    platform=item.platform,
                    auth_mode=self.binding_auth_modes[key].get().strip() or "manual",
                    account_alias=account_alias,
                    login_owner=login_owner,
                    enabled=self.binding_enabled_flags[key].get(),
                )
            )
        save_registry_bindings(self.registry_path, bindings)

        targets: list[StoreTargetConfig] = []
        for item in self.store_targets:
            raw_target = self.target_entries[item.store_id].get().strip() or "0"
            try:
                target_value = max(int(raw_target), 0)
            except ValueError:
                messagebox.showerror("保存失败", f"{item.store_name} 的每日目标条数必须是整数")
                return False
            targets.append(
                StoreTargetConfig(
                    store_id=item.store_id,
                    store_name=item.store_name,
                    daily_target_count=target_value,
                    require_source_store=self.target_source_flags[item.store_id].get(),
                )
            )
        save_store_targets(self.rules_path, targets)
        self.env_values = load_env_values(self.env_path)
        self.store_targets = load_store_targets(self.rules_path)
        self.registry_bindings = load_registry_bindings(self.registry_path)
        self._append_output("配置已保存。\n")
        if notify:
            messagebox.showinfo("保存成功", "飞书、时间段、门店平台绑定和 KPI 配置已保存。")
        return True

    def run_task(self, name: str, task: Callable[[], None]) -> None:
        if self.running:
            messagebox.showwarning("请稍候", "当前已有任务在运行，请先等它完成。")
            return
        if not self.save_settings(notify=False):
            return
        self.running = True
        self._append_output(f"开始执行：{name}\n")

        def runner() -> None:
            try:
                task()
                self._log(f"{name}完成。")
            except subprocess.CalledProcessError as exc:
                self._log(f"{name}失败，退出码={exc.returncode}")
                self.root.after(0, lambda: messagebox.showerror("执行失败", f"{name}失败，请看输出日志。"))
            except Exception as exc:  # noqa: BLE001
                self._log(f"{name}失败：{exc}")
                self.root.after(0, lambda: messagebox.showerror("执行失败", str(exc)))
            finally:
                self.running = False

        threading.Thread(target=runner, daemon=True).start()

    def install_environment(self) -> None:
        system_python = Path(sys.executable)
        venv_dir = self.root_dir / ".venv"
        if not venv_dir.exists():
            self._run_command([str(system_python), "-m", "venv", ".venv"], env=os.environ.copy())
        python_path = resolve_python(self.root_dir)
        self._run_command([str(python_path), "-m", "pip", "install", "-U", "pip"], env=os.environ.copy())
        self._run_command([str(python_path), "-m", "pip", "install", "-e", "."], env=os.environ.copy())
        ensure_env_file(self.env_path, self.root_dir / ".env.example")

    def test_feishu(self) -> None:
        env = build_runtime_env(self.root_dir, self.profile_dir, self.env_path)
        python_path = resolve_python(self.root_dir)
        self._run_command([str(python_path), "-m", "gb_monitor.cli", "feishu-ping"], env=env)

    def run_acceptance(self) -> None:
        env = build_runtime_env(self.root_dir, self.profile_dir, self.env_path)
        python_path = resolve_python(self.root_dir)
        commands = [
            [str(python_path), "-m", "gb_monitor.cli", "init-db"],
            [
                str(python_path),
                "-m",
                "gb_monitor.cli",
                "profile-readiness",
                "--profile-dir",
                str(self.profile_dir),
                "--require-feishu",
            ],
            [
                str(python_path),
                "-m",
                "gb_monitor.cli",
                "validate-registry",
                "--registry",
                str(self.profile_dir / "stores_registry.json"),
            ],
            [str(python_path), "-m", "gb_monitor.cli", "feishu-ping"],
            [str(python_path), "-m", "gb_monitor.cli", "run", "--mode", "all"],
            [str(python_path), "-m", "gb_monitor.cli", "report", "--hours", "24"],
            [
                str(python_path),
                "-m",
                "gb_monitor.cli",
                "profile-deliverable",
                "--profile-dir",
                str(self.profile_dir),
                "--output",
                str(self.profile_dir / "single_store_deliverable.md"),
            ],
            [
                str(python_path),
                "-m",
                "gb_monitor.cli",
                "profile-signals",
                "--profile-dir",
                str(self.profile_dir),
                "--mode",
                "all",
                "--notify",
                "--mark-dispatched",
                "--board-output",
                str(self.profile_dir / "signal_watchboard.md"),
                "--report-output",
                str(self.profile_dir / "signal_report.txt"),
            ],
            [
                str(python_path),
                "-m",
                "gb_monitor.cli",
                "profile-signal-deliverable",
                "--profile-dir",
                str(self.profile_dir),
                "--output",
                str(self.profile_dir / "signal_delivery_explainer.md"),
            ],
            [
                str(python_path),
                "-m",
                "gb_monitor.cli",
                "profile-usage-guide",
                "--profile-dir",
                str(self.profile_dir),
                "--output",
                str(self.profile_dir / "client_usage_guide.md"),
            ],
        ]
        for cmd in commands:
            self._run_command(cmd, env=env)

    def _run_command(self, cmd: list[str], env: dict[str, str]) -> None:
        self._log("$ " + " ".join(cmd))
        process = subprocess.Popen(
            cmd,
            cwd=self.root_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            self._log(line.rstrip())
        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, cmd)

    def open_results(self) -> None:
        open_path(self.profile_dir)

    def open_login_checklist(self) -> None:
        checklist = self.profile_dir / "login_checklist.md"
        open_path(checklist if checklist.exists() else self.profile_dir)

    def run(self) -> None:
        self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the customer control center")
    parser.add_argument("--root-dir", default=".", help="Repository root")
    parser.add_argument(
        "--profile-dir",
        default="data/client_profiles/shibaojie",
        help="Profile directory",
    )
    parser.add_argument("--env-file", default=".env", help="Environment file path")
    parser.add_argument(
        "--rules-file",
        default="data/client_profiles/shibaojie/store_signal_rules.json",
        help="Signal rules path",
    )
    parser.add_argument(
        "--registry-file",
        default="data/client_profiles/shibaojie/stores_registry.json",
        help="Store registry path",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root_dir = Path(args.root_dir).resolve()
    app = ControlCenterApp(
        root_dir=root_dir,
        profile_dir=(root_dir / args.profile_dir).resolve(),
        env_path=(root_dir / args.env_file).resolve(),
        rules_path=(root_dir / args.rules_file).resolve(),
        registry_path=(root_dir / args.registry_file).resolve(),
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
