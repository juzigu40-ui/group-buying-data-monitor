from __future__ import annotations

import argparse
import json
import os
import re
import socket
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
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
    city: str = ""


@dataclass(slots=True)
class SessionBindingConfig:
    store_id: str
    store_name: str
    platform: str
    machine_alias: str
    session_file: str
    status: str
    last_login_at: str
    note: str


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

PLATFORM_LABELS = {
    "amap": "高德地图",
    "dianping": "大众点评",
    "douyin": "抖音",
    "eleme": "饿了么",
    "jdwm": "京东外卖",
    "meituan": "美团外卖",
    "shipinhao": "视频号",
    "xiaohongshu": "小红书",
}

AUTH_MODE_LABELS = {
    "api": "接口接入",
    "cookie": "导入登录态",
    "manual": "页面登录",
}
AUTH_MODE_DISPLAY_TO_KEY = {label: key for key, label in AUTH_MODE_LABELS.items()}
AUTH_MODE_CHOICE_VALUES = tuple(AUTH_MODE_LABELS[key] for key in ("manual", "cookie", "api"))

SESSION_STATUS_LABELS = {
    "未初始化": "待登录",
    "可复用": "已可用",
    "需补登录": "需要重登",
    "已停用": "暂停使用",
}
SESSION_STATUS_DISPLAY_TO_KEY = {label: key for key, label in SESSION_STATUS_LABELS.items()}
SESSION_STATUS_VALUES = tuple(SESSION_STATUS_LABELS.keys())
SESSION_STATUS_CHOICE_VALUES = tuple(SESSION_STATUS_LABELS[key] for key in SESSION_STATUS_VALUES)
PLATFORM_OPTIONS = tuple(PLATFORM_LABELS.keys())
PLATFORM_DISPLAY_TO_KEY = {label: key for key, label in PLATFORM_LABELS.items()}
PLATFORM_CHOICE_VALUES = tuple(PLATFORM_LABELS[key] for key in PLATFORM_OPTIONS)
PLATFORM_PORTAL_URLS = {
    "amap": "https://yunying.gaode.com/",
    "dianping": "https://e.dianping.com/",
    "douyin": "https://fxg.jinritemai.com/",
    "eleme": "https://shop.ele.me/",
    "jdwm": "https://store.jddj.com/",
    "meituan": "https://e.waimai.meituan.com/",
    "shipinhao": "https://channels.weixin.qq.com/",
    "xiaohongshu": "https://creator.xiaohongshu.com/",
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


def merge_store_targets(
    targets: list[StoreTargetConfig],
    bindings: list[PlatformBindingConfig],
) -> list[StoreTargetConfig]:
    merged: dict[str, StoreTargetConfig] = {item.store_id: item for item in targets}
    for binding in bindings:
        existing = merged.get(binding.store_id)
        if existing is not None:
            existing.store_name = binding.store_name
            continue
        merged[binding.store_id] = StoreTargetConfig(
            store_id=binding.store_id,
            store_name=binding.store_name,
            daily_target_count=0,
            require_source_store=False,
        )
    return sorted(merged.values(), key=lambda item: (item.store_name, item.store_id))


def build_store_id(city: str, store_name: str) -> str:
    city_text = str(city).strip()
    name_text = re.sub(r"[·•/\\\s]+", "-", str(store_name).strip())
    name_text = re.sub(r"-+", "-", name_text).strip("-")
    if city_text and name_text:
        return f"{city_text}-{name_text}"
    return name_text or city_text or "未命名门店"


def build_default_rule_entry(store_id: str, store_name: str, platform: str) -> dict[str, object]:
    compact_name = store_name.replace("·", "").strip()
    alias = re.sub(r"[·•/\\\s]+", "", store_name).strip()
    keywords = [item for item in [store_name, compact_name, alias] if item]
    return {
        "store_id": store_id,
        "store_name": store_name,
        "platform": platform,
        "include_keywords": keywords,
        "exact_include_keywords": keywords[:2],
        "required_all_keywords": [],
        "required_context_keywords": keywords[:2],
        "required_location_keywords": [],
        "exclude_keywords": [],
        "author_include_keywords": [],
        "author_exclude_keywords": [],
        "author_level_include_keywords": [],
        "focus_author_names": [],
        "focus_author_tags": [],
        "focus_verified_labels": [],
        "store_aliases": [],
        "min_follower_count": 0,
        "daily_target_count": 0,
        "require_poi": False,
        "require_source_store": False,
        "required_any_fields": ["title", "content", "poi_name"],
        "min_score": 4,
    }


def save_store_targets(path: Path, targets: list[StoreTargetConfig]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stores = payload.setdefault("stores", [])
    target_map = {item.store_id: item for item in targets}
    existing_store_ids: set[str] = set()
    for item in stores:
        store_id = str(item.get("store_id", "")).strip()
        target = target_map.get(store_id)
        if target is None:
            continue
        existing_store_ids.add(store_id)
        item["store_name"] = target.store_name
        item["daily_target_count"] = max(target.daily_target_count, 0)
        item["require_source_store"] = bool(target.require_source_store)
    for target in targets:
        if target.store_id in existing_store_ids:
            continue
        for platform in ("douyin", "xiaohongshu", "shipinhao"):
            entry = build_default_rule_entry(target.store_id, target.store_name, platform)
            entry["daily_target_count"] = max(target.daily_target_count, 0)
            entry["require_source_store"] = bool(target.require_source_store)
            stores.append(entry)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_registry_bindings(path: Path) -> list[PlatformBindingConfig]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[PlatformBindingConfig] = []
    for store in payload.get("stores", []):
        store_id = str(store.get("store_id", "")).strip()
        city = str(store.get("city", "")).strip()
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
                    city=city,
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
    stores: list[dict[str, object]] = []
    store_map: dict[str, dict[str, object]] = {}
    for item in bindings:
        store_id = item.store_id.strip() or build_store_id(item.city, item.store_name)
        if not store_id:
            continue
        if store_id not in store_map:
            payload = {
                "store_id": store_id,
                "store_name": item.store_name.strip() or store_id,
                "city": item.city.strip(),
                "platforms": {},
            }
            stores.append(payload)
            store_map[store_id] = payload
        payload = store_map[store_id]
        payload["store_name"] = item.store_name.strip() or store_id
        payload["city"] = item.city.strip()
        platforms = payload["platforms"]
        assert isinstance(platforms, dict)
        platforms[item.platform] = {
            "auth_mode": item.auth_mode,
            "account_alias": item.account_alias,
            "login_owner": item.login_owner,
            "enabled": bool(item.enabled),
        }
    path.write_text(json.dumps({"stores": stores}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def open_url(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", url])
        return
    if os.name == "nt":
        os.startfile(url)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", url])


def _is_valid_hhmm(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return False
    hour, minute = int(parts[0]), int(parts[1])
    return 0 <= hour <= 23 and 0 <= minute <= 59


def platform_display_name(platform: str) -> str:
    key = platform.strip().lower()
    return PLATFORM_LABELS.get(key, platform.strip() or platform)


def platform_key_from_choice(value: str) -> str:
    label = str(value).strip()
    if label in PLATFORM_DISPLAY_TO_KEY:
        return PLATFORM_DISPLAY_TO_KEY[label]
    return label.lower()


def auth_mode_display_name(auth_mode: str) -> str:
    key = auth_mode.strip().lower()
    return AUTH_MODE_LABELS.get(key, auth_mode.strip() or auth_mode)


def auth_mode_key_from_choice(value: str) -> str:
    label = str(value).strip()
    if label in AUTH_MODE_DISPLAY_TO_KEY:
        return AUTH_MODE_DISPLAY_TO_KEY[label]
    return label.lower()


def session_status_display_name(status: str) -> str:
    key = str(status).strip()
    return SESSION_STATUS_LABELS.get(key, key or "待登录")


def session_status_key_from_choice(value: str) -> str:
    label = str(value).strip()
    if label in SESSION_STATUS_DISPLAY_TO_KEY:
        return SESSION_STATUS_DISPLAY_TO_KEY[label]
    return label


def current_machine_alias() -> str:
    return socket.gethostname().strip() or "本机"


def _slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    return text.strip("._-") or "default"


def default_session_file(platform: str, account_alias: str) -> str:
    return f"auth/{_slugify(platform)}__{_slugify(account_alias)}.state.json"


def load_session_bindings(path: Path, registry_bindings: list[PlatformBindingConfig], machine_alias: str) -> list[SessionBindingConfig]:
    existing_map: dict[tuple[str, str], dict[str, str]] = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("bindings", []):
            if not isinstance(item, dict):
                continue
            store_id = str(item.get("store_id", "")).strip()
            platform = str(item.get("platform", "")).strip()
            if store_id and platform:
                existing_map[(store_id, platform)] = {
                    "machine_alias": str(item.get("machine_alias", "")).strip(),
                    "session_file": str(item.get("session_file", "")).strip(),
                    "status": str(item.get("status", "")).strip(),
                    "last_login_at": str(item.get("last_login_at", "")).strip(),
                    "note": str(item.get("note", "")).strip(),
                }

    rows: list[SessionBindingConfig] = []
    for binding in registry_bindings:
        key = (binding.store_id, binding.platform)
        existing = existing_map.get(key, {})
        rows.append(
            SessionBindingConfig(
                store_id=binding.store_id,
                store_name=binding.store_name,
                platform=binding.platform,
                machine_alias=existing.get("machine_alias") or machine_alias,
                session_file=existing.get("session_file") or default_session_file(binding.platform, binding.account_alias),
                status=_normalize_session_status(
                    existing.get("status") or ("已停用" if not binding.enabled else "未初始化")
                ),
                last_login_at=existing.get("last_login_at", ""),
                note=existing.get("note", ""),
            )
        )
    return rows


def save_session_bindings(path: Path, bindings: list[SessionBindingConfig]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "bindings": [
            {
                "store_id": item.store_id,
                "store_name": item.store_name,
                "platform": item.platform,
                "machine_alias": item.machine_alias,
                "session_file": item.session_file,
                "status": item.status,
                "last_login_at": item.last_login_at,
                "note": item.note,
            }
            for item in bindings
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_session_status(value: str) -> str:
    mapping = {
        "待登录": "未初始化",
        "已可用": "可复用",
        "需要重登": "需补登录",
        "暂停使用": "已停用",
    }
    normalized = mapping.get(str(value).strip(), str(value).strip())
    if normalized in SESSION_STATUS_VALUES:
        return normalized
    return "未初始化"


class ControlCenterApp:
    def __init__(
        self,
        root_dir: Path,
        profile_dir: Path,
        env_path: Path,
        rules_path: Path,
        registry_path: Path,
        session_path: Path,
    ) -> None:
        if tk is None or messagebox is None or ttk is None:
            raise RuntimeError(
                "当前 Python 环境缺少 tkinter，无法启动可视化控制台。请安装带 Tk 的 Python，或先用命令行脚本运行。"
            )
        self.root_dir = root_dir
        self.profile_dir = profile_dir
        self.env_path = env_path
        self.rules_path = rules_path
        self.registry_path = registry_path
        self.session_path = session_path
        self.output_queue: Queue[str] = Queue()
        self.running = False
        self.font_family = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"
        self.theme: dict[str, str] = {}
        self._active_scroll_canvas: tk.Canvas | None = None

        ensure_env_file(self.env_path, self.root_dir / ".env.example")
        self.env_values = load_env_values(self.env_path)
        self.registry_bindings = load_registry_bindings(self.registry_path)
        self.store_targets = merge_store_targets(load_store_targets(self.rules_path), self.registry_bindings)
        self.machine_alias = current_machine_alias()
        self.session_bindings = load_session_bindings(self.session_path, self.registry_bindings, self.machine_alias)

        self.root = tk.Tk()
        self.root.title("橘子谷门店监控")
        self.root.geometry("1420x980")
        self.root.minsize(1280, 860)
        self._apply_theme()
        self.icon_image: tk.PhotoImage | None = None
        self._load_icon()

        self.entries: dict[str, tk.Entry] = {}
        self.target_entries: dict[str, tk.Entry] = {}
        self.target_source_flags: dict[str, tk.BooleanVar] = {}
        self.binding_rows: list[dict[str, object]] = []
        self.session_status_vars: dict[tuple[str, str], tk.StringVar] = {}
        self.session_last_login_vars: dict[tuple[str, str], tk.StringVar] = {}
        self.summary_vars: dict[str, tk.StringVar] = {}
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.page_shells: dict[str, ttk.Frame] = {}
        self.current_page_key = "start"

        self._build_ui()
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.root.after(120, self._flush_output)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=18, style="App.TFrame")
        container.pack(fill="both", expand=True)

        self._build_header(container)
        self._build_summary_banner(container)

        nav_bar = ttk.Frame(container, style="App.TFrame")
        nav_bar.pack(fill="x", pady=(0, 12))
        self._build_navigation(nav_bar)

        content_host = ttk.Frame(container, style="App.TFrame")
        content_host.pack(fill="both", expand=True)

        start_tab_shell = ttk.Frame(content_host, style="App.TFrame", padding=0)
        store_tab_shell = ttk.Frame(content_host, style="App.TFrame", padding=0)
        login_tab_shell = ttk.Frame(content_host, style="App.TFrame", padding=0)
        result_tab_shell = ttk.Frame(content_host, style="App.TFrame", padding=0)
        self.page_shells = {
            "start": start_tab_shell,
            "stores": store_tab_shell,
            "login": login_tab_shell,
            "results": result_tab_shell,
        }

        start_tab = self._make_scrolled_body(start_tab_shell)

        intro = "第一次使用时，只需要接好飞书、设好刷新时间、填好门店和平台关系。后面老板主要在飞书里看日报、预警和门店达标情况。"
        ttk.Label(start_tab, text=intro, wraplength=1240, justify="left", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))

        feishu_card = ttk.LabelFrame(start_tab, text="老板以后怎么用", padding=16, style="Card.TLabelframe")
        feishu_card.pack(fill="x", pady=(0, 12))
        ttk.Label(
            feishu_card,
            text="1. 打开程序，确认飞书和刷新时间没问题。\n2. 点“开始联通测试”或按计划运行。\n3. 老板主要在飞书里看：哪个门店达标、哪个门店掉队、今天和昨天有什么变化。",
            wraplength=1240,
            justify="left",
            style="Muted.TLabel",
        ).pack(anchor="w")

        top = ttk.Frame(start_tab, style="App.TFrame")
        top.pack(fill="x", pady=(0, 12))
        left = ttk.Frame(top, style="App.TFrame")
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(top, style="App.TFrame")
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))

        self._build_basic_settings(left)
        self._build_schedule_settings(right)
        self._build_actions(start_tab)

        store_body = self._make_scrolled_body(store_tab_shell)
        self.registry_host = ttk.Frame(store_body, style="App.TFrame")
        self.registry_host.pack(fill="x", pady=(0, 12))
        self.target_host = ttk.Frame(store_body, style="App.TFrame")
        self.target_host.pack(fill="x", pady=(0, 12))

        login_body = self._make_scrolled_body(login_tab_shell)
        self.session_host = ttk.Frame(login_body, style="App.TFrame")
        self.session_host.pack(fill="x", pady=(0, 12))
        self.openclaw_host = ttk.Frame(login_body, style="App.TFrame")
        self.openclaw_host.pack(fill="x", pady=(0, 12))

        result_tab = self._make_scrolled_body(result_tab_shell)
        self._build_result_tools(result_tab)
        self._build_output(result_tab)
        self._render_dynamic_sections()
        self._show_page("start")

    def _apply_theme(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        bg = "#f7f0e7"
        panel = "#fffdf9"
        accent = "#e46a11"
        accent_soft = "#fff0df"
        text = "#2b241e"
        muted = "#7d6a5b"
        entry_bg = "#fff6eb"
        border = "#e9dccb"
        card_shadow = "#f2e7db"

        self.theme = {
            "bg": bg,
            "panel": panel,
            "accent": accent,
            "accent_soft": accent_soft,
            "text": text,
            "muted": muted,
            "entry_bg": entry_bg,
            "border": border,
            "card_shadow": card_shadow,
        }

        self.root.configure(bg=bg)
        style.configure("App.TFrame", background=bg)
        style.configure("Card.TLabelframe", background=panel, foreground=text, borderwidth=1, relief="solid")
        style.configure(
            "Card.TLabelframe.Label",
            background=panel,
            foreground=text,
            font=(self.font_family, 15, "bold"),
        )
        style.configure("TLabel", background=panel, foreground=text, font=(self.font_family, 13))
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=(self.font_family, 13))
        style.configure("HeroTitle.TLabel", background=bg, foreground=text, font=(self.font_family, 26, "bold"))
        style.configure("HeroSub.TLabel", background=bg, foreground=muted, font=(self.font_family, 13))
        style.configure("SummaryValue.TLabel", background=panel, foreground=accent, font=(self.font_family, 18, "bold"))
        style.configure("Primary.TButton", font=(self.font_family, 13, "bold"), padding=(20, 12))
        style.map(
            "Primary.TButton",
            background=[("!disabled", accent), ("active", "#f08b39")],
            foreground=[("!disabled", "#ffffff")],
        )
        style.configure("Nav.TButton", font=(self.font_family, 13, "bold"), padding=(16, 14))
        style.map(
            "Nav.TButton",
            background=[("!disabled", panel), ("active", "#fff1e3")],
            foreground=[("!disabled", text)],
        )
        style.configure("NavActive.TButton", font=(self.font_family, 13, "bold"), padding=(16, 14))
        style.map(
            "NavActive.TButton",
            background=[("!disabled", accent), ("active", "#f08b39")],
            foreground=[("!disabled", "#ffffff")],
        )
        style.configure("Secondary.TButton", font=(self.font_family, 12), padding=(12, 8))
        style.configure("TButton", font=(self.font_family, 12), padding=(10, 8))
        style.configure("TCheckbutton", background=panel, foreground=text)
        style.configure(
            "TCombobox",
            fieldbackground=entry_bg,
            background=entry_bg,
            foreground=text,
            padding=4,
            bordercolor=border,
            lightcolor=entry_bg,
            darkcolor=entry_bg,
        )
        style.configure(
            "TEntry",
            fieldbackground=entry_bg,
            foreground=text,
            insertcolor=text,
            bordercolor=border,
            lightcolor=entry_bg,
            darkcolor=entry_bg,
        )
        style.map("TEntry", fieldbackground=[("readonly", entry_bg)])
        style.configure("Log.TFrame", background=panel)

    def _render_dynamic_sections(self) -> None:
        for host in (self.registry_host, self.session_host, self.target_host, self.openclaw_host):
            for child in host.winfo_children():
                child.destroy()
        self._build_registry_bindings(self.registry_host)
        self._build_store_targets(self.target_host)
        self._build_session_bindings(self.session_host)
        self._build_openclaw_bridge(self.openclaw_host)
        self._refresh_summary()

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self._active_scroll_canvas is None:
            return
        if sys.platform == "darwin":
            delta = int(-1 * event.delta)
        else:
            delta = int(-1 * (event.delta / 120))
        self._active_scroll_canvas.yview_scroll(delta, "units")

    def _make_scrolled_body(self, parent: ttk.Frame) -> ttk.Frame:
        shell = ttk.Frame(parent, style="App.TFrame")
        shell.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            shell,
            highlightthickness=0,
            borderwidth=0,
            background=self.theme["bg"],
        )
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas, padding=14, style="App.TFrame")
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        for widget in (canvas, body):
            widget.bind("<Enter>", lambda _event, current=canvas: self._set_active_canvas(current))
            widget.bind("<Leave>", lambda _event, current=canvas: self._clear_active_canvas(current))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return body

    def _set_active_canvas(self, canvas: tk.Canvas) -> None:
        self._active_scroll_canvas = canvas

    def _clear_active_canvas(self, canvas: tk.Canvas) -> None:
        if self._active_scroll_canvas is canvas:
            self._active_scroll_canvas = None

    def _build_header(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, style="App.TFrame")
        frame.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, text="橘子谷门店监控", style="HeroTitle.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="把门店内容监管、外卖经营数据和飞书预警收进一个真正能落地的门店控制台。老板平时主要在飞书里看日报、预警和门店达标状态。",
            style="HeroSub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

    def _build_navigation(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent, style="App.TFrame")
        left.pack(side="left", fill="x", expand=True)
        right = ttk.Frame(parent, style="App.TFrame")
        right.pack(side="right")
        items = [
            ("start", "开始使用"),
            ("stores", "门店配置"),
            ("login", "平台登录"),
            ("results", "飞书结果"),
        ]
        for key, title in items:
            button = ttk.Button(
                left,
                text=title,
                style="Nav.TButton",
                command=lambda current=key: self._show_page(current),
            )
            button.pack(side="left", padx=(0, 10))
            self.nav_buttons[key] = button
        ttk.Label(
            right,
            text="固定一台正式运行电脑，后面只需要打开程序、看飞书、看门店结果。",
            style="Muted.TLabel",
        ).pack(anchor="e", pady=(4, 0))

    def _show_page(self, key: str) -> None:
        self.current_page_key = key
        for page_key, shell in self.page_shells.items():
            if page_key == key:
                shell.pack(fill="both", expand=True)
            else:
                shell.pack_forget()
        for page_key, button in self.nav_buttons.items():
            button.configure(style="NavActive.TButton" if page_key == key else "Nav.TButton")

    def _load_icon(self) -> None:
        icon_path = self.root_dir / "assets" / "orange_monitor_icon.png"
        if not icon_path.exists():
            return
        try:
            self.icon_image = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self.icon_image)
        except tk.TclError:
            self.icon_image = None

    def _build_summary_banner(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="当前部署摘要", padding=14, style="Card.TLabelframe")
        frame.pack(fill="x", pady=(0, 10))
        items = [
            ("当前部署电脑", "machine_alias", self.machine_alias),
            ("已绑定平台数", "platform_count", str(len(self.registry_bindings))),
            ("外卖更新频率", "delivery_interval", f"{self.env_values.get('GBM_DELIVERY_INTERVAL_MINUTES', '30')} 分钟"),
            ("评价更新频率", "review_interval", f"{self.env_values.get('GBM_REVIEW_INTERVAL_MINUTES', '60')} 分钟"),
        ]
        self.summary_vars = {}
        for idx, (label, key, value) in enumerate(items):
            box = ttk.Frame(frame, padding=(0, 2))
            box.grid(row=0, column=idx, sticky="w", padx=(0, 18))
            ttk.Label(box, text=label).pack(anchor="w")
            var = tk.StringVar(value=value)
            self.summary_vars[key] = var
            ttk.Label(box, textvariable=var, style="SummaryValue.TLabel").pack(anchor="w")

    def _refresh_summary(self) -> None:
        if not self.summary_vars:
            return
        delivery_value = self.entries["GBM_DELIVERY_INTERVAL_MINUTES"].get().strip() or self.env_values.get(
            "GBM_DELIVERY_INTERVAL_MINUTES",
            "30",
        )
        review_value = self.entries["GBM_REVIEW_INTERVAL_MINUTES"].get().strip() or self.env_values.get(
            "GBM_REVIEW_INTERVAL_MINUTES",
            "60",
        )
        self.summary_vars["machine_alias"].set(self.machine_alias)
        self.summary_vars["platform_count"].set(str(len(self.registry_bindings)))
        self.summary_vars["delivery_interval"].set(f"{delivery_value} 分钟")
        self.summary_vars["review_interval"].set(f"{review_value} 分钟")

    def _build_basic_settings(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="第一步：接上飞书群", padding=16, style="Card.TLabelframe")
        frame.pack(fill="both", expand=True)
        fields = [
            ("GBM_FEISHU_WEBHOOK", "飞书收消息地址"),
            ("GBM_FEISHU_AT_MOBILES", "需要提醒的人（手机号，可空，多个用逗号隔开）"),
        ]
        for idx, (key, label) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", pady=6)
            entry = ttk.Entry(frame, width=52)
            entry.insert(0, self.env_values.get(key, ""))
            entry.grid(row=idx, column=1, sticky="ew", pady=6, padx=(8, 0))
            self.entries[key] = entry
        ttk.Label(
            frame,
            text="把老板平时要看的飞书群机器人地址贴到这里。以后门店日报、异常提醒、舆情汇总都从这个群发出去。",
            wraplength=760,
            justify="left",
            style="Muted.TLabel",
        ).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(10, 0))
        frame.columnconfigure(1, weight=1)

    def _build_schedule_settings(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="第二步：设定刷新时间", padding=16, style="Card.TLabelframe")
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="频率直接填分钟：30=每30分钟，60=每1小时，120=每2小时。高峰期想更密，就填 10 或 30。这里填的是自动刷新节奏，不是老板手动操作次数。",
            wraplength=380,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        core_fields = [
            ("GBM_SIGNAL_WINDOW_START", "内容监控开始时间"),
            ("GBM_SIGNAL_WINDOW_END", "内容监控结束时间"),
            ("GBM_SIGNAL_INTERVAL_MINUTES", "内容刷新频率（分钟）"),
            ("GBM_REVIEW_INTERVAL_MINUTES", "评价刷新频率（分钟）"),
            ("GBM_DELIVERY_INTERVAL_MINUTES", "外卖经营数据刷新频率（分钟）"),
        ]
        for idx, (key, label) in enumerate(core_fields, start=1):
            ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            entry = ttk.Entry(frame, width=24)
            entry.insert(0, self.env_values.get(key, ""))
            entry.grid(row=idx, column=1, sticky="ew", pady=4, padx=(8, 0))
            self.entries[key] = entry

        advanced_toggle = ttk.Button(frame, text="打开高级时间设置", style="Secondary.TButton")
        advanced_toggle.grid(row=len(core_fields) + 1, column=0, columnspan=2, sticky="w", pady=(10, 6))

        advanced_frame = ttk.Frame(frame, style="App.TFrame")
        advanced_frame.grid(row=len(core_fields) + 2, column=0, columnspan=2, sticky="ew")
        advanced_fields = [
            ("GBM_REVIEW_WINDOW_START", "评价监控开始时间"),
            ("GBM_REVIEW_WINDOW_END", "评价监控结束时间"),
            ("GBM_DELIVERY_LUNCH_START", "外卖午餐营业时段开始"),
            ("GBM_DELIVERY_LUNCH_END", "外卖午餐营业时段结束"),
            ("GBM_DELIVERY_DINNER_START", "外卖晚餐营业时段开始"),
            ("GBM_DELIVERY_DINNER_END", "外卖晚餐营业时段结束"),
        ]
        for idx, (key, label) in enumerate(advanced_fields):
            ttk.Label(advanced_frame, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            entry = ttk.Entry(advanced_frame, width=24)
            entry.insert(0, self.env_values.get(key, ""))
            entry.grid(row=idx, column=1, sticky="ew", pady=4, padx=(8, 0))
            self.entries[key] = entry
        advanced_frame.columnconfigure(1, weight=1)
        advanced_frame.grid_remove()

        def toggle_advanced() -> None:
            if advanced_frame.winfo_ismapped():
                advanced_frame.grid_remove()
                advanced_toggle.configure(text="打开高级时间设置")
            else:
                advanced_frame.grid()
                advanced_toggle.configure(text="收起高级时间设置")

        advanced_toggle.configure(command=toggle_advanced)
        frame.columnconfigure(1, weight=1)

    def _build_store_targets(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="门店目标", padding=14, style="Card.TLabelframe")
        frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            frame,
            text="新增门店后，这里会自动出现。老板只需要填每天希望每个门店完成多少条内容，后面飞书就能直接看达标没达标。",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="门店").grid(row=1, column=0, sticky="w")
        ttk.Label(frame, text="每日目标内容数").grid(row=1, column=1, sticky="w", padx=(12, 0))
        ttk.Label(frame, text="只统计门店来源内容").grid(row=1, column=2, sticky="w", padx=(12, 0))
        self.target_entries = {}
        self.target_source_flags = {}
        for idx, target in enumerate(self.store_targets, start=2):
            ttk.Label(frame, text=target.store_name).grid(row=idx, column=0, sticky="w", pady=4)
            entry = ttk.Entry(frame, width=12)
            entry.insert(0, str(target.daily_target_count))
            entry.grid(row=idx, column=1, sticky="w", padx=(12, 0), pady=4)
            flag = tk.BooleanVar(value=target.require_source_store)
            ttk.Checkbutton(frame, variable=flag).grid(row=idx, column=2, sticky="w", padx=(20, 0), pady=4)
            self.target_entries[target.store_id] = entry
            self.target_source_flags[target.store_id] = flag

    def _build_openclaw_bridge(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="采集执行助手（可选）", padding=14, style="Card.TLabelframe")
        frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            frame,
            text="如果你们后面还想保留 OpenClaw，最好的方式不是让它继续直接给老板推泛消息，而是让它退到后台去做登录、采集、补抓。真正负责按门店归因、去噪、算 KPI、对比今天和昨天，再统一往飞书汇报的，是橘子谷门店监控。",
            wraplength=1180,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        ttk.Button(frame, text="打开采集投递目录", style="Secondary.TButton", command=self.open_signal_input_dir).grid(
            row=1, column=0, padx=(0, 8), pady=4, sticky="w"
        )
        ttk.Button(frame, text="打开经营数据目录", style="Secondary.TButton", command=self.open_snapshot_dir).grid(
            row=1, column=1, padx=(0, 8), pady=4, sticky="w"
        )
        ttk.Label(
            frame,
            text="如果以后还要兼容 OpenClaw 或别的采集机器人，只要把采集结果投递进这两个目录，当前系统就会继续负责门店归因、监控时段、飞书推送和 KPI 达标状态。老板以后主要还是看我们的机器人，不需要同时盯两套结果。",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def _build_registry_bindings(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="门店与平台绑定", padding=14, style="Card.TLabelframe")
        frame.pack(fill="x", pady=(0, 12))
        toolbar = ttk.Frame(frame, style="App.TFrame")
        toolbar.grid(row=0, column=0, columnspan=9, sticky="ew", pady=(0, 10))
        ttk.Label(
            toolbar,
            text="后面如果新增门店、新开平台、改账号备注，直接在这里增删改就行，不需要再改代码。",
        ).pack(side="left")
        ttk.Button(toolbar, text="新增门店/平台", style="Secondary.TButton", command=self.add_binding_row).pack(
            side="right"
        )

        headings = ["城市/区域", "门店名称", "监控平台", "登录方式", "平台账号备注", "登录负责人", "启用", "打开后台", "删除"]
        for col, title in enumerate(headings):
            ttk.Label(frame, text=title).grid(row=1, column=col, sticky="w", padx=(0, 8))

        self.binding_rows = []
        auth_options = AUTH_MODE_CHOICE_VALUES
        bindings = self.registry_bindings or [
            PlatformBindingConfig(
                store_id="",
                city="",
                store_name="",
                platform="meituan",
                auth_mode="manual",
                account_alias="",
                login_owner="客户-门店账号",
                enabled=True,
            )
        ]
        for idx, binding in enumerate(bindings, start=2):
            city_entry = ttk.Entry(frame, width=12)
            city_entry.insert(0, binding.city)
            city_entry.grid(row=idx, column=0, sticky="ew", pady=4, padx=(0, 8))

            store_entry = ttk.Entry(frame, width=26)
            store_entry.insert(0, binding.store_name)
            store_entry.grid(row=idx, column=1, sticky="ew", pady=4, padx=(0, 8))

            platform_var = tk.StringVar(value=platform_display_name(binding.platform))
            platform_box = ttk.Combobox(
                frame,
                textvariable=platform_var,
                values=PLATFORM_CHOICE_VALUES,
                width=10,
                state="readonly",
            )
            platform_box.grid(row=idx, column=2, sticky="ew", pady=4, padx=(0, 8))

            auth_var = tk.StringVar(value=auth_mode_display_name(binding.auth_mode))
            auth_box = ttk.Combobox(frame, textvariable=auth_var, values=auth_options, width=10, state="readonly")
            auth_box.grid(row=idx, column=3, sticky="ew", pady=4, padx=(0, 8))

            account_entry = ttk.Entry(frame, width=22)
            account_entry.insert(0, binding.account_alias)
            account_entry.grid(row=idx, column=4, sticky="ew", pady=4, padx=(0, 8))

            owner_entry = ttk.Entry(frame, width=18)
            owner_entry.insert(0, binding.login_owner)
            owner_entry.grid(row=idx, column=5, sticky="ew", pady=4, padx=(0, 8))

            enabled_var = tk.BooleanVar(value=binding.enabled)
            ttk.Checkbutton(frame, variable=enabled_var).grid(row=idx, column=6, sticky="w", padx=(12, 0), pady=4)

            ttk.Button(
                frame,
                text="去登录",
                style="Secondary.TButton",
                command=lambda var=platform_var: self.open_platform_login(platform_key_from_choice(var.get())),
            ).grid(row=idx, column=7, sticky="w", pady=4, padx=(0, 8))

            row_state: dict[str, object] = {
                "store_id": binding.store_id,
                "city_entry": city_entry,
                "store_entry": store_entry,
                "platform_var": platform_var,
                "auth_var": auth_var,
                "account_entry": account_entry,
                "owner_entry": owner_entry,
                "enabled_var": enabled_var,
            }
            ttk.Button(
                frame,
                text="删除",
                style="Secondary.TButton",
                command=lambda current=row_state: self.remove_binding_row(current),
            ).grid(row=idx, column=8, sticky="w", pady=4)
            self.binding_rows.append(row_state)

        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(4, weight=1)
        frame.columnconfigure(5, weight=1)

    def _build_session_bindings(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="平台登录状态", padding=14, style="Card.TLabelframe")
        frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            frame,
            text="你不需要自己去找任何本地会话文件。首次在这台正式运行电脑上登录一次后，系统就默认把登录状态记在这台电脑上。只有平台失效时，再点“打开对应后台”补一次。",
            wraplength=1100,
            justify="left",
        ).grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 8))

        headings = ["门店", "平台", "当前状态", "最后登录时间", "打开对应后台", "我已登录", "需要重登"]
        for col, title in enumerate(headings):
            ttk.Label(frame, text=title).grid(row=1, column=col, sticky="w", padx=(0, 8))

        self.session_last_login_vars = {}
        for idx, item in enumerate(self.session_bindings, start=2):
            key = (item.store_id, item.platform)
            ttk.Label(frame, text=item.store_name).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Label(frame, text=platform_display_name(item.platform)).grid(row=idx, column=1, sticky="w", pady=4)

            status_var = tk.StringVar(value=session_status_display_name(item.status))
            status_box = ttk.Combobox(
                frame,
                textvariable=status_var,
                values=SESSION_STATUS_CHOICE_VALUES,
                width=10,
                state="readonly",
            )
            status_box.grid(row=idx, column=2, sticky="w", pady=4)
            self.session_status_vars[key] = status_var

            last_login_var = tk.StringVar(value=item.last_login_at or "还没有完成首次登录")
            ttk.Label(frame, textvariable=last_login_var).grid(row=idx, column=3, sticky="w", pady=4, padx=(8, 0))
            self.session_last_login_vars[key] = last_login_var

            ttk.Button(
                frame,
                text="打开对应后台",
                style="Secondary.TButton",
                command=lambda current=item.platform: self.open_platform_login(current),
            ).grid(row=idx, column=4, sticky="w", pady=4, padx=(8, 0))
            ttk.Button(
                frame,
                text="我已登录",
                style="Secondary.TButton",
                command=lambda item_key=key: self.mark_session_reusable(item_key),
            ).grid(row=idx, column=5, sticky="w", pady=4, padx=(8, 0))
            ttk.Button(
                frame,
                text="需要重登",
                style="Secondary.TButton",
                command=lambda item_key=key: self.mark_session_relogin(item_key),
            ).grid(row=idx, column=6, sticky="w", pady=4, padx=(8, 0))

        frame.columnconfigure(3, weight=1)

    def _build_actions(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="第三步：开始联通测试", padding=18, style="Card.TLabelframe")
        frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            frame,
            text="第一次只需要点下面三个主按钮：先保存设置，再发飞书测试，最后开始联通测试。联通测试跑通后，老板平时主要看飞书，不需要天天进来研究程序。",
            style="Muted.TLabel",
        ).grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 10)
        )
        primary_buttons: list[tuple[str, Callable[[], None]]] = [
            ("① 保存设置", lambda: self.run_task("保存设置", self.install_environment), "Primary.TButton"),
            ("② 发送飞书测试", lambda: self.run_task("发送飞书测试", self.test_feishu), "Primary.TButton"),
            ("③ 开始联通测试", lambda: self.run_task("开始联通测试", self.run_acceptance), "Primary.TButton"),
        ]
        for idx, (label, action, style_name) in enumerate(primary_buttons):
            ttk.Button(frame, text=label, style=style_name, command=action).grid(row=1, column=idx, padx=(0, 10), pady=4)

    def _build_result_tools(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="飞书结果与回看", padding=14, style="Card.TLabelframe")
        frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            frame,
            text="老板平时主要在飞书里看结果。这里主要用于回看本地结果、查看后台登录清单，以及在需要时打开采集投递目录。",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 10))
        buttons: list[tuple[str, Callable[[], None]]] = [
            ("查看结果", self.open_results),
            ("打开后台登录清单", self.open_login_checklist),
            ("打开采集投递目录", self.open_signal_input_dir),
            ("打开经营数据目录", self.open_snapshot_dir),
            ("打开认证目录", self.open_auth_dir),
        ]
        for idx, (label, action) in enumerate(buttons):
            ttk.Button(frame, text=label, style="Secondary.TButton", command=action).grid(
                row=1, column=idx, padx=(0, 8), pady=4, sticky="w"
            )

    def _build_output(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="运行日志", padding=14, style="Card.TLabelframe")
        frame.pack(fill="both", expand=True)
        self.output = tk.Text(
            frame,
            height=16,
            wrap="word",
            bg="#fffaf4",
            fg="#2b241e",
            insertbackground="#2b241e",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=(self.font_family, 12),
        )
        self.output.pack(fill="both", expand=True)
        self.output.insert("end", "橘子谷门店监控已启动。建议先点“① 保存设置”，再点“② 发送飞书测试”，最后点“③ 开始联通测试”。\n")
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

    def _collect_binding_rows(self, validate: bool) -> list[PlatformBindingConfig] | None:
        bindings: list[PlatformBindingConfig] = []
        seen_keys: set[tuple[str, str]] = set()
        for row in self.binding_rows:
            city = str(row["city_entry"].get()).strip()  # type: ignore[union-attr]
            store_name = str(row["store_entry"].get()).strip()  # type: ignore[union-attr]
            platform = platform_key_from_choice(str(row["platform_var"].get()).strip())  # type: ignore[union-attr]
            auth_mode = auth_mode_key_from_choice(str(row["auth_var"].get()).strip()) or "manual"  # type: ignore[union-attr]
            account_alias = str(row["account_entry"].get()).strip()  # type: ignore[union-attr]
            login_owner = str(row["owner_entry"].get()).strip()  # type: ignore[union-attr]
            enabled = bool(row["enabled_var"].get())  # type: ignore[union-attr]
            blank_row = not any([city, store_name, account_alias, login_owner])
            if blank_row:
                continue
            if validate and not store_name:
                messagebox.showerror("保存失败", "门店名称不能为空。")
                return None
            if validate and platform not in PLATFORM_OPTIONS:
                messagebox.showerror("保存失败", "请选择有效的平台。")
                return None
            if validate and not account_alias:
                messagebox.showerror("保存失败", f"{store_name or '未命名门店'} 的账号备注不能为空。")
                return None
            if validate and not login_owner:
                messagebox.showerror("保存失败", f"{store_name or '未命名门店'} 的负责人不能为空。")
                return None
            store_id = str(row.get("store_id") or "").strip() or build_store_id(city, store_name)
            key = (store_id, platform)
            if key in seen_keys:
                if validate:
                    messagebox.showerror("保存失败", f"{store_name} 的 {platform_display_name(platform)} 重复了。")
                    return None
                continue
            seen_keys.add(key)
            bindings.append(
                PlatformBindingConfig(
                    store_id=store_id,
                    city=city,
                    store_name=store_name or store_id,
                    platform=platform,
                    auth_mode=auth_mode,
                    account_alias=account_alias,
                    login_owner=login_owner or "客户-门店账号",
                    enabled=enabled,
                )
            )
        return bindings

    def add_binding_row(self) -> None:
        snapshot = self._collect_binding_rows(validate=False)
        if snapshot is not None:
            self.registry_bindings = snapshot
        self.registry_bindings.append(
            PlatformBindingConfig(
                store_id="",
                city="",
                store_name="",
                platform="meituan",
                auth_mode="manual",
                account_alias="",
                login_owner="客户-门店账号",
                enabled=True,
            )
        )
        self._render_dynamic_sections()

    def remove_binding_row(self, row_state: dict[str, object]) -> None:
        snapshot = self._collect_binding_rows(validate=False)
        if snapshot is None:
            return
        remove_store_id = str(row_state.get("store_id") or "").strip()
        remove_platform = platform_key_from_choice(str(row_state["platform_var"].get()).strip())  # type: ignore[union-attr]
        remove_name = str(row_state["store_entry"].get()).strip()  # type: ignore[union-attr]
        filtered: list[PlatformBindingConfig] = []
        removed = False
        for item in snapshot:
            if removed:
                filtered.append(item)
                continue
            same_row = item.platform == remove_platform and item.store_name == (remove_name or item.store_name)
            if remove_store_id:
                same_row = same_row and item.store_id == remove_store_id
            if same_row:
                removed = True
                continue
            filtered.append(item)
        self.registry_bindings = filtered
        self.store_targets = merge_store_targets(self.store_targets, self.registry_bindings)
        self._render_dynamic_sections()

    def open_platform_login(self, platform: str) -> None:
        url = PLATFORM_PORTAL_URLS.get(platform)
        if not url:
            messagebox.showwarning("暂不支持", f"{platform_display_name(platform)} 暂时还没有预设后台地址。")
            return
        open_url(url)

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

        bindings = self._collect_binding_rows(validate=True)
        if bindings is None:
            return False
        save_registry_bindings(self.registry_path, bindings)

        targets: list[StoreTargetConfig] = []
        merged_targets = merge_store_targets(self.store_targets, bindings)
        for item in merged_targets:
            target_entry = self.target_entries.get(item.store_id)
            raw_target = target_entry.get().strip() if target_entry is not None else "0"
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
                    require_source_store=self.target_source_flags.get(item.store_id).get()
                    if item.store_id in self.target_source_flags
                    else False,
                )
            )
        save_store_targets(self.rules_path, targets)

        session_rows: list[SessionBindingConfig] = []
        for item in self.session_bindings:
            key = (item.store_id, item.platform)
            status = session_status_key_from_choice(self.session_status_vars[key].get().strip()) or "未初始化"
            last_login_at = self.session_last_login_vars[key].get().strip() if key in self.session_last_login_vars else item.last_login_at
            session_rows.append(
                SessionBindingConfig(
                    store_id=item.store_id,
                    store_name=item.store_name,
                    platform=item.platform,
                    machine_alias=self.machine_alias,
                    session_file=item.session_file,
                    status=status,
                    last_login_at=last_login_at,
                    note=item.note,
                )
            )
        save_session_bindings(self.session_path, session_rows)

        self.env_values = load_env_values(self.env_path)
        self.store_targets = merge_store_targets(load_store_targets(self.rules_path), bindings)
        self.registry_bindings = load_registry_bindings(self.registry_path)
        self.session_bindings = load_session_bindings(self.session_path, self.registry_bindings, self.machine_alias)
        self._render_dynamic_sections()
        self._append_output("配置已保存。\n")
        if notify:
            messagebox.showinfo("保存成功", "飞书、时间段、平台绑定、登录状态和 KPI 配置已保存。")
        return True

    def mark_session_reusable(self, key: tuple[str, str]) -> None:
        self.session_status_vars[key].set("已可用")
        if key in self.session_last_login_vars:
            self.session_last_login_vars[key].set(datetime.now().strftime("%Y-%m-%d %H:%M"))

    def mark_session_relogin(self, key: tuple[str, str]) -> None:
        self.session_status_vars[key].set("需要重登")

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
        python_path = Path(sys.executable)
        self._run_command([str(python_path), "--version"], env=os.environ.copy())
        self._run_command([str(python_path), "-c", "import tkinter"], env=os.environ.copy())
        ensure_env_file(self.env_path, self.root_dir / ".env.example")
        (self.root_dir / "auth").mkdir(parents=True, exist_ok=True)

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

    def open_signal_input_dir(self) -> None:
        signal_dir = self.profile_dir / "signal_inputs"
        signal_dir.mkdir(parents=True, exist_ok=True)
        open_path(signal_dir)

    def open_snapshot_dir(self) -> None:
        snapshot_dir = self.profile_dir / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        open_path(snapshot_dir)

    def open_login_checklist(self) -> None:
        checklist = self.profile_dir / "login_checklist.md"
        open_path(checklist if checklist.exists() else self.profile_dir)

    def open_auth_dir(self) -> None:
        auth_dir = self.profile_dir / "auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        open_path(auth_dir)

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
    parser.add_argument(
        "--session-file",
        default="data/client_profiles/shibaojie/auth/session_registry.json",
        help="Session binding registry path",
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
        session_path=(root_dir / args.session_file).resolve(),
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
