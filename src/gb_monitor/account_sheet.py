from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


@dataclass(slots=True)
class PlatformAccountRecord:
    platform_label: str
    platform_key: str
    store_name: str
    city: str
    store_link: str
    account: str
    password: str
    login_method: str
    second_factor: str


def import_account_sheet(xlsx_path: Path, profile_dir: Path) -> dict[str, Path]:
    records = load_account_sheet(xlsx_path)
    if not records:
        raise ValueError("account sheet is empty")

    primary = records[0]
    store_id = build_store_id(primary.city, primary.store_name)
    store_payload = build_store_registry_payload(store_id, records)
    login_payload = build_login_inventory_payload(store_id, records)
    checklist_text = build_login_checklist(records)
    signal_rules_payload = build_signal_rules_payload(store_id, primary)
    signal_input_payloads = build_signal_input_payloads()
    signal_input_readme = build_signal_input_readme(primary.store_name, primary.city)
    verification_plan_payload = build_verification_plan_payload(records)
    execution_board_text = build_execution_board(records, verification_plan_payload)
    snapshot_payloads = build_snapshot_payloads(store_id, primary.store_name)

    profile_dir.mkdir(parents=True, exist_ok=True)
    registry_path = profile_dir / "stores_registry.json"
    login_path = profile_dir / "login_inventory.local.json"
    checklist_path = profile_dir / "login_checklist.md"
    rules_path = profile_dir / "store_signal_rules.json"
    verification_plan_path = profile_dir / "verification_plan.json"
    execution_board_path = profile_dir / "execution_board.md"
    snapshots_dir = profile_dir / "snapshots"
    signal_inputs_dir = profile_dir / "signal_inputs"
    signal_input_readme_path = signal_inputs_dir / "README.md"

    registry_path.write_text(
        json.dumps(store_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    login_path.write_text(
        json.dumps(login_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    checklist_path.write_text(checklist_text, encoding="utf-8")
    rules_path.write_text(
        json.dumps(signal_rules_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    verification_plan_path.write_text(
        json.dumps(verification_plan_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    execution_board_path.write_text(execution_board_text, encoding="utf-8")
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in snapshot_payloads.items():
        (snapshots_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    signal_inputs_dir.mkdir(parents=True, exist_ok=True)
    signal_input_readme_path.write_text(signal_input_readme, encoding="utf-8")
    for filename, payload in signal_input_payloads.items():
        (signal_inputs_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "stores_registry": registry_path,
        "login_inventory": login_path,
        "login_checklist": checklist_path,
        "signal_rules": rules_path,
        "signal_inputs_dir": signal_inputs_dir,
        "signal_input_readme": signal_input_readme_path,
        "verification_plan": verification_plan_path,
        "execution_board": execution_board_path,
        "snapshots_dir": snapshots_dir,
    }


def load_account_sheet(xlsx_path: Path) -> list[PlatformAccountRecord]:
    rows = _read_first_sheet_rows(xlsx_path)
    if len(rows) < 2:
        return []

    header = [str(cell).strip() for cell in rows[0]]
    records: list[PlatformAccountRecord] = []
    for raw in rows[1:]:
        mapped = _row_to_dict(header, raw)
        platform_label = str(mapped.get("平台", "")).strip()
        if not platform_label:
            continue
        records.append(
            PlatformAccountRecord(
                platform_label=platform_label,
                platform_key=normalize_platform(platform_label),
                store_name=str(mapped.get("门店名称", "")).strip(),
                city=str(mapped.get("城市", "")).strip(),
                store_link=str(mapped.get("店铺链接", "")).strip(),
                account=str(mapped.get("账号", "")).strip(),
                password=str(mapped.get("密码", "")).strip(),
                login_method=str(mapped.get("登录方式", "")).strip(),
                second_factor=str(mapped.get("二次验证", "")).strip(),
            )
        )
    return records


def build_store_registry_payload(
    store_id: str,
    records: list[PlatformAccountRecord],
) -> dict[str, object]:
    primary = records[0]
    platforms: dict[str, dict[str, object]] = {}
    for item in records:
        platforms[item.platform_key] = {
            "auth_mode": infer_auth_mode(item.login_method),
            "account_alias": build_account_alias(item),
            "login_owner": "客户-门店账号",
            "enabled": True,
        }

    return {
        "stores": [
            {
                "store_id": store_id,
                "store_name": primary.store_name,
                "city": primary.city,
                "platforms": platforms,
            }
        ]
    }


def build_login_inventory_payload(
    store_id: str,
    records: list[PlatformAccountRecord],
) -> dict[str, object]:
    primary = records[0]
    platforms: dict[str, dict[str, str | bool]] = {}
    for item in records:
        platforms[item.platform_key] = {
            "platform_label": item.platform_label,
            "account": item.account,
            "password": item.password,
            "store_link": item.store_link,
            "login_method": item.login_method,
            "second_factor": item.second_factor,
            "verification_required": needs_verification(item),
        }

    return {
        "store_id": store_id,
        "store_name": primary.store_name,
        "city": primary.city,
        "platforms": platforms,
    }


def build_login_checklist(records: list[PlatformAccountRecord]) -> str:
    primary = records[0]
    lines = [
        f"# {primary.store_name} 首登配合清单",
        "",
        f"- 城市：{primary.city}",
        "- 当前账号表已导入本地运行档。",
        "- 不把真实账号密码写进仓库或 PR。",
        "",
        "## 平台登录情况",
    ]

    for item in records:
        verification = "需要用户配合" if needs_verification(item) else "可先按现有资料推进"
        lines.append(
            f"- {item.platform_label}（{item.platform_key}）：{item.login_method or '登录方式待确认'}；{verification}"
        )
        if item.second_factor:
            lines.append(f"  二验：{item.second_factor}")
        if item.store_link:
            lines.append(f"  链接：{item.store_link}")

    return "\n".join(lines) + "\n"


def build_signal_rules_payload(store_id: str, primary: PlatformAccountRecord) -> dict[str, object]:
    base_keywords = extract_store_keywords(primary.store_name)
    exact_keywords = build_exact_store_keywords(primary.store_name)
    context_keywords = build_public_signal_context_keywords(primary.store_name, primary.city)
    location_keywords = build_store_location_keywords(primary.store_name, primary.city)
    common_excludes = build_public_signal_noise_keywords(primary.store_name)

    return {
        "stores": [
            {
                "store_id": store_id,
                "store_name": primary.store_name,
                "platform": "douyin",
                "include_keywords": base_keywords,
                "exact_include_keywords": exact_keywords,
                "required_all_keywords": [],
                "required_context_keywords": context_keywords,
                "required_location_keywords": location_keywords,
                "exclude_keywords": common_excludes,
                "author_include_keywords": [],
                "author_exclude_keywords": [],
                "required_any_fields": ["title", "content", "poi_name"],
                "min_score": 8,
            },
            {
                "store_id": store_id,
                "store_name": primary.store_name,
                "platform": "xiaohongshu",
                "include_keywords": base_keywords,
                "exact_include_keywords": exact_keywords,
                "required_all_keywords": [],
                "required_context_keywords": context_keywords,
                "required_location_keywords": location_keywords,
                "exclude_keywords": common_excludes,
                "author_include_keywords": [],
                "author_exclude_keywords": [],
                "required_any_fields": ["title", "content", "poi_name"],
                "min_score": 8,
            },
            {
                "store_id": store_id,
                "store_name": primary.store_name,
                "platform": "shipinhao",
                "include_keywords": base_keywords,
                "exact_include_keywords": exact_keywords,
                "required_all_keywords": [],
                "required_context_keywords": context_keywords,
                "required_location_keywords": location_keywords,
                "exclude_keywords": common_excludes,
                "author_include_keywords": [],
                "author_exclude_keywords": [],
                "required_any_fields": ["title", "content", "poi_name"],
                "min_score": 8,
            },
        ]
    }


def build_verification_plan_payload(records: list[PlatformAccountRecord]) -> dict[str, object]:
    priority = {
        "douyin": 1,
        "dianping": 2,
        "meituan": 3,
        "eleme": 4,
        "jdwm": 5,
        "amap": 6,
    }

    items: list[dict[str, object]] = []
    for item in records:
        items.append(
            {
                "platform_key": item.platform_key,
                "platform_label": item.platform_label,
                "priority": priority.get(item.platform_key, 99),
                "status": "pending" if needs_verification(item) else "not_required",
                "verification_required": needs_verification(item),
                "login_method": item.login_method,
                "second_factor": item.second_factor,
                "store_link": item.store_link,
            }
        )

    items.sort(key=lambda row: (row["priority"], row["platform_key"]))
    return {
        "steps": items,
    }


def build_execution_board(
    records: list[PlatformAccountRecord],
    verification_plan_payload: dict[str, object],
) -> str:
    primary = records[0]
    steps_raw = verification_plan_payload.get("steps", [])
    steps = steps_raw if isinstance(steps_raw, list) else []
    step_by_platform = {
        str(step.get("platform_key")): step
        for step in steps
        if isinstance(step, dict)
    }

    lines = [
        f"# {primary.store_name} 单店执行面板",
        "",
        f"- 城市：{primary.city}",
        f"- 后台平台数：{len(records)}",
        "- 当前目标：先把单店链路跑通，再逐个平台进入真实登录与采集。",
        "",
        "## 平台执行状态",
        "",
        "| 平台 | 账号 | 登录方式 | 当前状态 | 卡点 |",
        "| --- | --- | --- | --- | --- |",
    ]

    for item in records:
        step = step_by_platform.get(item.platform_key, {})
        status = summarize_platform_status(item, step)
        blocker = summarize_platform_blocker(item, step)
        lines.append(
            "| "
            f"{item.platform_label} | "
            f"{mask_account(item.account)} | "
            f"{item.login_method or '待确认'} | "
            f"{status} | "
            f"{blocker} |"
        )

    lines.extend(
        [
            "",
            "## 公开舆情范围",
            "",
            "- 抖音：已按门店关键词生成首版精筛规则。",
            "- 小红书：已建标准输入文件和规则位，真实内容源可直接按统一结构接入。",
            "- 视频号：已建标准输入文件和规则位，真实内容源可直接按统一结构接入。",
            "",
            "## 当前先做什么",
            "",
            "1. 先推进不依赖验证码的本地链路与规则校准。",
            "2. 真到登录窗口时，再找客户拿当前平台验证码。",
            "3. 大众点评和美团若触发首次异地二验，再做一次性配合。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def build_snapshot_payloads(store_id: str, store_name: str) -> dict[str, dict[str, object]]:
    files = {
        "review_dianping.json": "review",
        "review_douyin.json": "review",
        "review_amap.json": "review",
        "delivery_meituan.json": "delivery",
        "delivery_eleme.json": "delivery",
        "delivery_jdwm.json": "delivery",
    }
    payloads: dict[str, dict[str, object]] = {}
    for filename in files:
        payloads[filename] = {
            "captured_at": "",
            "stores": [
                {
                    "store_id": store_id,
                    "store_name": store_name,
                    "metrics": {},
                }
            ],
        }
    return payloads


def build_signal_input_payloads() -> dict[str, dict[str, object]]:
    return {
        "public_xiaohongshu.json": {"platform": "xiaohongshu", "items": []},
        "public_douyin.json": {"platform": "douyin", "items": []},
        "public_shipinhao.json": {"platform": "shipinhao", "items": []},
    }


def build_signal_input_readme(store_name: str, city: str) -> str:
    lines = [
        "# 实时舆情输入规范",
        "",
        f"- 门店：{store_name}",
        f"- 城市：{city}",
        "- 调度频率：每天 10:00-21:00 每小时一次",
        "- 目标：把小红书 / 抖音 / 视频号的门店相关内容转成统一结构，再做门店级命中、噪音过滤、去重和飞书分发。",
        "",
        "## 这套系统如何解决“舆情监测太模糊”的问题",
        "",
        "1. 不是模糊的“OpenClaw+skills”，而是明确的输入文件、规则文件、调度规则和分发输出。",
        "2. 每个平台都有固定字段，不满足字段的内容不会进入正式命中结果。",
        "3. 门店命中不是关键词乱撞，而是门店名、POI、城市、上下文、排除词一起判断。",
        "4. 每次命中都会落出作者、地域、链接、发布时间、互动量、POI 和命中原因，方便客户复核。",
        "5. 派送有去重账本，同一内容不会在短时间内反复推送。",
        "",
        "## 文件",
        "",
        "- `public_xiaohongshu.json`: 小红书候选内容",
        "- `public_douyin.json`: 抖音候选内容",
        "- `public_shipinhao.json`: 视频号候选内容",
        "- `store_signal_rules.json`: 门店匹配规则",
        "",
        "## 统一字段要求",
        "",
        "- 必填：`content_id`, `platform`, `title`, `content`, `author_name`, `url`",
        "- 推荐：`poi_name`, `published_at`, `like_count`, `comment_count`, `share_count`",
        "- 扩展：`author_level`, `ip_location`, `topic_tags`, `favorite_count`",
        "",
        "## 平台字段重点",
        "",
        "### 小红书",
        "- 需要重点提供：作者、IP 地域、笔记链接、标题、正文、话题标签、发布时间、点赞、收藏。",
        "",
        "### 抖音",
        "- 需要重点提供：发布者级别、标题、视频文案、点赞、评论、转发、POI 门店地址。",
        "",
        "### 视频号",
        "- 需要重点提供：标题、视频文案、点赞、转发、POI 门店地址。",
        "",
        "## 最小 JSON 示例",
        "",
        "```json",
        "{",
        "  \"platform\": \"xiaohongshu\",",
        "  \"items\": [",
        "    {",
        "      \"content_id\": \"xhs-001\",",
        "      \"title\": \"食宝街这家米粉到底值不值\",",
        "      \"content\": \"凤状元这家店我今天去吃了\",",
        "      \"author_name\": \"北京探店阿宁\",",
        "      \"author_level\": \"Lv.5\",",
        "      \"ip_location\": \"北京\",",
        "      \"topic_tags\": [\"食宝街\", \"江西小炒\"],",
        "      \"poi_name\": \"凤状元·江西小炒·非遗米粉(食宝街店)\",",
        "      \"url\": \"https://example.com/xhs/001\",",
        "      \"published_at\": \"2026-03-07T18:00:00+08:00\",",
        "      \"like_count\": 128,",
        "      \"favorite_count\": 45,",
        "      \"comment_count\": 12,",
        "      \"share_count\": 6",
        "    }",
        "  ]",
        "}",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def next_verification_target(profile_dir: Path) -> dict[str, object] | None:
    path = profile_dir / "verification_plan.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        return None
    for step in steps:
        if (
            isinstance(step, dict)
            and step.get("verification_required")
            and step.get("status", "pending") == "pending"
        ):
            return step
    return None


def update_verification_status(profile_dir: Path, platform_key: str, status: str) -> Path:
    if status not in {"pending", "ready", "completed", "skipped", "failed", "not_required"}:
        raise ValueError("unsupported status")

    path = profile_dir / "verification_plan.json"
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("invalid verification plan")

    updated = False
    for step in steps:
        if isinstance(step, dict) and step.get("platform_key") == platform_key:
            step["status"] = status
            updated = True
            break
    if not updated:
        raise ValueError(f"platform not found: {platform_key}")

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    execution_board_path = profile_dir / "execution_board.md"
    inventory_path = profile_dir / "login_inventory.local.json"
    if inventory_path.exists():
        execution_board_path.write_text(
            build_profile_execution_board(profile_dir),
            encoding="utf-8",
        )
    return path


def build_client_verification_message(profile_dir: Path) -> str:
    inventory_path = profile_dir / "login_inventory.local.json"
    if not inventory_path.exists():
        raise FileNotFoundError(inventory_path)
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    step = next_verification_target(profile_dir)
    if not step:
        return "当前没有待处理的验证码平台。"

    store_name = str(payload.get("store_name", "")).strip()
    platform_key = str(step["platform_key"])
    platforms = payload.get("platforms", {})
    platform_conf = platforms.get(platform_key, {}) if isinstance(platforms, dict) else {}
    platform_label = str(step["platform_label"]).strip()
    account = str(platform_conf.get("account", "")).strip()

    parts = [
        f"老板，现在要配合一下 {platform_label} 这边的登录。",
        f"门店是：{store_name}。",
    ]
    if account:
        parts.append(f"账号是：{account}。")
    parts.append("这次只需要您这边看到验证码时转我一下，或者帮忙点一次验证。")
    second_factor = str(step.get("second_factor", "")).strip()
    if second_factor and second_factor not in {"无", ""}:
        parts.append(f"这边还要注意：{second_factor}。")
    parts.append("我这边拿到后会马上处理，尽量一次把会话留住，不反复打扰您。")
    return "".join(parts)


def build_profile_status(profile_dir: Path) -> str:
    inventory_path = profile_dir / "login_inventory.local.json"
    verification_path = profile_dir / "verification_plan.json"
    if not inventory_path.exists():
        raise FileNotFoundError(inventory_path)
    if not verification_path.exists():
        raise FileNotFoundError(verification_path)

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))

    store_name = str(inventory.get("store_name", "")).strip()
    platforms = inventory.get("platforms", {})
    steps = verification.get("steps", [])
    if not isinstance(platforms, dict) or not isinstance(steps, list):
        raise ValueError("invalid profile files")

    lines = [f"门店: {store_name}"]
    lines.append(f"平台总数: {len(platforms)}")

    pending_steps = [step for step in steps if isinstance(step, dict) and step.get("status") == "pending"]
    completed_steps = [step for step in steps if isinstance(step, dict) and step.get("status") == "completed"]
    direct_steps = [
        step for step in steps if isinstance(step, dict) and step.get("status") == "not_required"
    ]
    lines.append(f"待验证码: {len(pending_steps)}")
    lines.append(f"已完成验证: {len(completed_steps)}")
    lines.append(f"可直接推进: {len(direct_steps)}")

    next_step = next_verification_target(profile_dir)
    if next_step:
        lines.append(
            "当前优先级: "
            f"{next_step['platform_label']}({next_step['platform_key']}) / {next_step['login_method'] or '登录方式待确认'}"
        )
    else:
        lines.append("当前优先级: 无")

    if pending_steps:
        lines.append("待验证码平台:")
        for step in pending_steps:
            lines.append(
                f"- {step['platform_label']}({step['platform_key']}) / {step['login_method'] or '登录方式待确认'}"
            )

    if direct_steps:
        lines.append("无需验证码平台:")
        for step in direct_steps:
            lines.append(
                f"- {step['platform_label']}({step['platform_key']})"
            )

    unresolved: list[str] = []
    for platform_key, conf in platforms.items():
        if not isinstance(conf, dict):
            continue
        if not str(conf.get("login_method", "")).strip():
            unresolved.append(f"{conf.get('platform_label', platform_key)} 登录方式待确认")
        if str(conf.get("store_link", "")).strip() in {"", "无"}:
            unresolved.append(f"{conf.get('platform_label', platform_key)} 店铺链接待确认")
    if unresolved:
        lines.append("待确认信息:")
        for item in unresolved:
            lines.append(f"- {item}")

    return "\n".join(lines)


def build_profile_execution_board(profile_dir: Path) -> str:
    inventory_path = profile_dir / "login_inventory.local.json"
    verification_path = profile_dir / "verification_plan.json"
    if not inventory_path.exists():
        raise FileNotFoundError(inventory_path)
    if not verification_path.exists():
        raise FileNotFoundError(verification_path)

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    store_name = str(inventory.get("store_name", "")).strip()
    city = str(inventory.get("city", "")).strip()
    platforms_raw = inventory.get("platforms", {})
    if not isinstance(platforms_raw, dict):
        raise ValueError("invalid login inventory")

    records: list[PlatformAccountRecord] = []
    for platform_key, conf in platforms_raw.items():
        if not isinstance(conf, dict):
            continue
        records.append(
            PlatformAccountRecord(
                platform_label=str(conf.get("platform_label", platform_key)).strip(),
                platform_key=str(platform_key).strip(),
                store_name=store_name,
                city=city,
                store_link=str(conf.get("store_link", "")).strip(),
                account=str(conf.get("account", "")).strip(),
                password="",
                login_method=str(conf.get("login_method", "")).strip(),
                second_factor=str(conf.get("second_factor", "")).strip(),
            )
        )
    records.sort(key=lambda item: item.platform_key)
    if not records:
        raise ValueError("no platform records found in login inventory")
    return build_execution_board(records, verification)


def build_profile_deliverable(profile_dir: Path) -> str:
    inventory_path = profile_dir / "login_inventory.local.json"
    verification_path = profile_dir / "verification_plan.json"
    snapshots_dir = profile_dir / "snapshots"
    if not inventory_path.exists():
        raise FileNotFoundError(inventory_path)
    if not verification_path.exists():
        raise FileNotFoundError(verification_path)
    if not snapshots_dir.exists():
        raise FileNotFoundError(snapshots_dir)

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    store_name = str(inventory.get("store_name", "")).strip()
    city = str(inventory.get("city", "")).strip()
    platforms = inventory.get("platforms", {})
    steps_raw = verification.get("steps", [])
    if not isinstance(platforms, dict) or not isinstance(steps_raw, list):
        raise ValueError("invalid profile files")

    step_by_platform = {
        str(step.get("platform_key")): step
        for step in steps_raw
        if isinstance(step, dict)
    }

    lines = [
        f"# {store_name} 单店交付页",
        "",
        f"- 城市：{city}",
        "- 交付层级：单店首版（已能统一落库、查数、出执行状态与舆情看板）",
        "- 当前结论：不需要所有平台都先有完整经营指标，系统也可以先交付；当前已经具备首版可交付条件。",
        "- 舆情补充：可单独输出《实时舆情交付页》，把输入、规则、调度、去重和派发方式讲清楚。",
        "",
        "## 现在已经完成了什么",
        "",
        "1. 单店账号映射已经建好，6 个平台都接进了同一套 profile。",
        "2. 已登录平台的数据快照可以统一灌进 SQLite，并用同一套命令查看。",
        "3. 门店级实时舆情精筛已经可以运行，能过滤掉和门店无关的噪音内容。",
        "4. 验证码链路、执行面板、状态推进都已经接通，不再靠手工记忆。",
        "",
        "## 平台打通状态",
        "",
        "| 平台 | 当前状态 | 已有结果 | 说明 |",
        "| --- | --- | --- | --- |",
    ]

    for platform_key in ["douyin", "dianping", "eleme", "jdwm", "meituan", "amap"]:
        platform_conf = platforms.get(platform_key, {})
        if not isinstance(platform_conf, dict):
            continue
        step = step_by_platform.get(platform_key, {})
        snapshot_path = snapshots_dir / snapshot_filename_for_platform(platform_key)
        snapshot = load_snapshot_payload(snapshot_path) if snapshot_path.exists() else {}
        status, result_summary, note = summarize_deliverable_platform(
            platform_key=platform_key,
            platform_conf=platform_conf,
            step=step,
            snapshot=snapshot,
        )
        lines.append(
            f"| {platform_conf.get('platform_label', platform_key)} | {status} | {result_summary} | {note} |"
        )

    lines.extend(
        [
            "",
            "## 当前这套系统已经能做什么",
            "",
            "- 输出单店执行面板，知道每个平台是“已打通”“待补指标”还是“待补登录方式”。",
            "- 查询最新入库指标，不需要重新进后台翻页面。",
            "- 运行门店级实时舆情精筛，把探店/打卡/门店内容和无关噪音分开。",
            "- 单独输出舆情交付说明页，向客户讲清楚这套系统不是模糊的“OpenClaw+skills”。",
            "- 继续往后补平台时，不用推倒重来，只补缺的平台快照就行。",
            "",
            "## 还差什么才算更完整",
            "",
            "1. 高德当前只拿到了门店主数据，没有经营指标页，这不阻塞首版交付，但会限制平台层分析深度。",
            "2. 小红书 / 视频号 当前已经有标准输入位和规则位，后续只要补真实内容源即可，不需要重写系统。",
            "3. 若客户后面要自动通知，再决定接飞书或别的分发方式；这不影响先交付首版系统。",
            "",
            "## 交付判断",
            "",
            "- 现在已经不是“只登录后台”。",
            "- 现在是“单店首版已能交付，后续继续补平台深度”。",
            "- 如果今天就要交，建议口径是：先交单店首版，已覆盖抖音 / 大众点评 / 美团外卖 / 淘宝闪购 / 京东外卖的数据链路，高德保留为主数据补强位。",
            "- 舆情部分建议同时附上 `signal_delivery_explainer.md`，把客户最关心的“怎么监测、怎么过滤、怎么派发”一次说透。",
            "- 使用层建议同时附上 `client_usage_guide.md`，把客户怎么查看、怎么继续沿用 OpenClaw 讲清楚。",
            "",
        ]
    )
    return "\n".join(lines)


def build_profile_signal_deliverable(profile_dir: Path) -> str:
    inventory_path = profile_dir / "login_inventory.local.json"
    rules_path = profile_dir / "store_signal_rules.json"
    if not inventory_path.exists():
        raise FileNotFoundError(inventory_path)
    if not rules_path.exists():
        raise FileNotFoundError(rules_path)

    from gb_monitor.signal_pipeline import resolve_profile_signal_input_paths
    from gb_monitor.signal_rules import load_signal_candidates, load_signal_rules

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    store_name = str(inventory.get("store_name", "")).strip()
    city = str(inventory.get("city", "")).strip()
    rules = load_signal_rules(rules_path)
    input_paths = resolve_profile_signal_input_paths(profile_dir)

    rule_counts: dict[str, int] = {}
    for rule in rules:
        rule_counts[rule.platform] = rule_counts.get(rule.platform, 0) + 1

    signal_inputs_dir = profile_dir / "signal_inputs"
    standardized_inputs = {
        "xiaohongshu": signal_inputs_dir / "public_xiaohongshu.json",
        "douyin": signal_inputs_dir / "public_douyin.json",
        "shipinhao": signal_inputs_dir / "public_shipinhao.json",
    }
    candidate_counts: dict[str, int] = {"xiaohongshu": 0, "douyin": 0, "shipinhao": 0}
    for path in input_paths:
        for candidate in load_signal_candidates(path):
            candidate_counts[candidate.platform] = candidate_counts.get(candidate.platform, 0) + 1

    total_candidates = sum(candidate_counts.values())
    loaded_files = [path.name for path in input_paths]
    lines = [
        f"# {store_name} 实时舆情交付页",
        "",
        f"- 城市：{city}",
        "- 监测时段：每天 10:00-21:00 每小时一次",
        "- 当前目标：把小红书 / 抖音 / 视频号的公开内容统一进入门店级判断和飞书派发链路。",
        f"- 当前规则数：{len(rules)}",
        f"- 当前候选内容数：{total_candidates}",
        f"- 当前已识别输入文件：{', '.join(loaded_files) if loaded_files else '无'}",
        "",
        "## 这套系统如何真正解决实时舆情问题",
        "",
        "1. 不是模糊的“OpenClaw+skills”，而是固定输入文件 + 门店规则 + 调度窗口 + 去重账本 + 派发输出。",
        "2. 输入层先把各平台内容转成统一 JSON，确保作者、链接、时间、互动量、POI 等字段能被稳定读取。",
        "3. 规则层按门店名、商圈、城市、POI、上下文和排除词同时判断，不靠单个关键词碰运气。",
        "4. 判断层会输出命中词、命中字段、作者/IP、互动量和原因，客户能看到为什么推送、为什么过滤。",
        "5. 去重层会记录已发内容，同一条内容不会在短时间内反复轰炸飞书。",
        "6. 派发层可直接生成 `signal_report.txt` 和 `signal_watchboard.md`，也可以接飞书 webhook。",
        "",
        "## 与需求文档的对应关系",
        "",
        "| 平台 | 客户要的重点字段 | 我们的标准输入文件 |",
        "| --- | --- | --- |",
        "| 小红书 | 作者、IP 地域、链接、标题、正文、话题标签、发布时间、点赞、收藏 | `signal_inputs/public_xiaohongshu.json` |",
        "| 抖音 | 发布者级别、标题、视频文案、点赞、评论、转发、POI 门店 | `signal_inputs/public_douyin.json` |",
        "| 视频号 | 标题、视频文案、点赞、转发、POI 门店 | `signal_inputs/public_shipinhao.json` |",
        "",
        "## 当前门店输入状态",
        "",
        "| 平台 | 状态 | 候选内容数 | 规则数 | 输入文件 |",
        "| --- | --- | ---: | ---: | --- |",
    ]

    for platform in ["xiaohongshu", "douyin", "shipinhao"]:
        path = standardized_inputs[platform]
        exists = path.exists()
        count = candidate_counts.get(platform, 0)
        status = "已标准化接入" if exists and count > 0 else "已建输入位待补真实源" if exists else "待创建输入文件"
        path_label = str(path.relative_to(profile_dir)) if exists else path.name
        lines.append(
            f"| {_signal_platform_label(platform)} | {status} | {count} | {rule_counts.get(platform, 0)} | `{path_label}` |"
        )

    lines.extend(
        [
            "",
            "## 当前规则覆盖方式",
            "",
            "- 每个平台都有独立门店规则，最低命中分默认不低于 8 分。",
            "- 规则同时包含门店名、别名、城市、位置上下文、餐饮上下文和排除词。",
            "- 对凤状元这类容易撞到戏曲/民俗内容的词，已经单独加了噪音排除规则。",
            "",
            "## 本次交付会一起给客户什么",
            "",
            "- `signal_inputs/README.md`：说明输入格式、字段要求和最小示例。",
            "- `signal_watchboard.md`：面向运营或老板的舆情看板。",
            "- `signal_report.txt`：适合飞书直接发送的文本版命中结果。",
            "- `signal_delivery_explainer.md`：说明这套系统怎么解决“实时舆情太模糊”的问题。",
            "- `client_usage_guide.md`：告诉客户日常怎么用，以及如果继续用 OpenClaw 应该怎么接。",
            "",
            "## 对客户的说明口径",
            "",
            "这套实时舆情不是一句“会用 OpenClaw+skills 做监测”的抽象表述，而是已经明确到输入、规则、时间窗、过滤逻辑和派发结果的系统。OpenClaw 如果继续用，也只承担采集和执行层，不直接作为客户看到的交付结果。后面即使再补小红书或视频号的真实来源，也只是往标准输入文件里加数据，不需要推倒重来。",
            "",
        ]
    )
    return "\n".join(lines)


def build_profile_usage_guide(profile_dir: Path) -> str:
    inventory_path = profile_dir / "login_inventory.local.json"
    if not inventory_path.exists():
        raise FileNotFoundError(inventory_path)

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    store_name = str(inventory.get("store_name", "")).strip()
    city = str(inventory.get("city", "")).strip()
    profile_path = profile_dir.as_posix()
    lines = [
        f"# {store_name} 系统使用说明",
        "",
        f"- 城市：{city}",
        "- 适用对象：门店老板 / 运营 / 代运营 / 内部执行同学",
        "- 核心原则：客户看到的是稳定的门店监测系统，不是直接操作底层采集脚本。",
        "",
        "## 客户怎么理解这套系统",
        "",
        "1. OpenClaw 可以继续保留，但它的角色是采集和执行引擎，不是最终交付本身。",
        "2. 客户真正使用的是标准化后的结果层：门店指标快照、执行面板、舆情看板、舆情报告。",
        "3. 这样做的好处是：以后即使换采集方式，客户使用方式也不用改。",
        "",
        "## 客户日常使用顺序",
        "",
        "1. 先看 `single_store_deliverable.md`，确认门店当前整体交付状态。",
        "2. 再看 `execution_board.md`，确认哪个平台已打通、哪个平台还在补。",
        "3. 看 `signal_watchboard.md` 和 `signal_report.txt`，确认实时舆情命中内容。",
        "4. 需要查经营指标时，直接看最新导出的交付页或查询最新指标结果。",
        "",
        "## 如果客户还是希望继续用 OpenClaw",
        "",
        "可以，但要把职责说清楚：",
        "- OpenClaw：负责登录、抓取、调度、把原始内容写进标准输入文件。",
        "- 本系统：负责统一字段、门店规则判断、噪音过滤、去重、落库、出看板、出飞书文本。",
        "- 客户最终看的是本系统产出的交付文件，而不是原始抓取结果。",
        "",
        "## 执行同学怎么跑",
        "",
        f"1. 跑整店链路：`./scripts/run_profile.sh {profile_path}`",
        f"2. 只跑实时舆情：`PYTHONPATH=src python3 -m gb_monitor.cli profile-signals --profile-dir '{profile_path}' --mode all --board-output '{profile_path}/signal_watchboard.md' --report-output '{profile_path}/signal_report.txt'`",
        f"3. 生成舆情说明页：`PYTHONPATH=src python3 -m gb_monitor.cli profile-signal-deliverable --profile-dir '{profile_path}' --output '{profile_path}/signal_delivery_explainer.md'`",
        f"4. 生成客户使用说明：`PYTHONPATH=src python3 -m gb_monitor.cli profile-usage-guide --profile-dir '{profile_path}' --output '{profile_path}/client_usage_guide.md'`",
        "",
        "## 需要客户补什么",
        "",
        "- 登录验证码或二次验证时，按执行面板顺序一次性配合。",
        "- 如果要接更多舆情来源，只需要继续补标准输入文件，不需要改客户使用方式。",
        "- 如果要自动飞书推送，只需要补 webhook，不需要重做规则。",
        "",
    ]
    return "\n".join(lines)


def summarize_platform_status(
    record: PlatformAccountRecord,
    step: dict[str, object] | None,
) -> str:
    if step and step.get("status") == "completed":
        return "已完成验证"
    if needs_verification(record):
        return "待验证码"
    if not str(record.login_method).strip():
        return "登录方式待确认"
    return "可先推进"


def summarize_platform_blocker(
    record: PlatformAccountRecord,
    step: dict[str, object] | None,
) -> str:
    blockers: list[str] = []
    if not str(record.store_link).strip() or str(record.store_link).strip() == "无":
        blockers.append("店铺链接待补")
    if not str(record.login_method).strip():
        blockers.append("登录方式待确认")
    second_factor = str(record.second_factor).strip()
    if second_factor and second_factor not in {"无", ""}:
        blockers.append(second_factor)
    if step and step.get("status") == "failed":
        blockers.append("上次验证失败")
    if not blockers:
        return "无"
    return "；".join(blockers)


def _signal_platform_label(platform: str) -> str:
    mapping = {
        "xiaohongshu": "小红书",
        "douyin": "抖音",
        "shipinhao": "视频号",
    }
    return mapping.get(platform, platform)


def mask_account(account: str) -> str:
    text = str(account).strip()
    if not text:
        return "-"
    if len(text) <= 4:
        return text
    if text.isdigit() and len(text) >= 7:
        return f"{text[:3]}****{text[-4:]}"
    if len(text) <= 8:
        return text[:2] + "***"
    return text[:2] + "***" + text[-2:]


def normalize_platform(label: str) -> str:
    text = "".join(str(label).strip().lower().split())
    mapping = {
        "抖音": "douyin",
        "大众点评": "dianping",
        "高德": "amap",
        "美团外卖": "meituan",
        "淘宝闪购": "eleme",
        "饿了么": "eleme",
        "京东外卖": "jdwm",
        "京东到家": "jdwm",
    }
    if text in mapping:
        return mapping[text]
    raise ValueError(f"unsupported platform label: {label}")


def infer_auth_mode(login_method: str) -> str:
    text = str(login_method).strip()
    if not text:
        return "manual"
    if "验证" in text or "扫码" in text or "短信" in text:
        return "manual"
    return "manual"


def build_store_id(city: str, store_name: str) -> str:
    city_token = slugify(city) or "store"
    store_token = slugify(store_name) or "shop"
    return f"{city_token}-{store_token}"


def build_account_alias(record: PlatformAccountRecord) -> str:
    suffix = record.account or record.platform_label
    return f"{record.platform_key}_{slugify(suffix) or 'account'}"


def needs_verification(record: PlatformAccountRecord) -> bool:
    combined = f"{record.login_method} {record.second_factor}".strip()
    return any(token in combined for token in ("验证", "验证码", "二次", "外地登录", "扫码"))


def extract_store_keywords(store_name: str) -> list[str]:
    cleaned = str(store_name).strip()
    if not cleaned:
        return []
    parts = re.split(r"[·+\-]", cleaned)
    keywords: list[str] = [cleaned]
    for part in parts:
        part = part.strip()
        if len(part) >= 2 and part not in keywords:
            keywords.append(part)

    bracket_values = re.findall(r"\(([^)]+)\)", cleaned)
    for item in bracket_values:
        item = item.strip()
        if item and item not in keywords:
            keywords.append(item)

    return keywords


def build_exact_store_keywords(store_name: str) -> list[str]:
    keywords = [store_name]
    normalized = store_name.replace("·", "").replace(" ", "")
    if normalized and normalized not in keywords:
        keywords.append(normalized)

    main_name = re.sub(r"\(.*?\)", "", store_name).strip("· ").strip()
    if main_name and main_name not in keywords:
        keywords.append(main_name)
    return keywords


def build_public_signal_context_keywords(store_name: str, city: str) -> list[str]:
    keywords = [
        "探店",
        "打卡",
        "到店",
        "门店",
        "店里",
        "餐厅",
        "饭店",
        "美食",
        "吃饭",
        "团购",
        "套餐",
        "测评",
        "推荐",
        city,
    ]
    for token in extract_store_keywords(store_name):
        if any(marker in token for marker in ("小炒", "米粉", "食宝街", "店")):
            keywords.append(token.replace("(", "").replace(")", ""))
    return _dedupe_keywords(keywords)


def build_store_location_keywords(store_name: str, city: str) -> list[str]:
    keywords = [city]
    for token in extract_store_keywords(store_name):
        if "店" in token or "街" in token:
            keywords.append(token.replace("(", "").replace(")", ""))
    return _dedupe_keywords(keywords)


def build_public_signal_noise_keywords(store_name: str) -> list[str]:
    keywords = [
        "加盟",
        "招商",
        "培训",
        "招聘",
        "代运营",
        "无关品牌",
        "戏曲",
        "京剧",
        "琼剧",
        "状元媒",
        "状元探花郎",
        "青年戏",
        "戏院",
        "剧团",
        "录制",
        "民俗",
        "妈祖",
        "营老爷",
        "大年初五",
    ]
    if "凤状元" in store_name:
        keywords.extend(["状元媒", "凤状元最新内容", "谁说戏曲不抖音"])
    return _dedupe_keywords(keywords)


def _dedupe_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in keywords:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def slugify(text: str) -> str:
    lowered = str(text).strip().lower()
    if not lowered:
        return ""
    lowered = lowered.replace("·", "-")
    lowered = lowered.replace("+", "-")
    lowered = lowered.replace("（", "(").replace("）", ")")
    lowered = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff()\-]+", "-", lowered)
    lowered = lowered.strip("-")
    return lowered


def snapshot_filename_for_platform(platform_key: str) -> str:
    mapping = {
        "dianping": "review_dianping.json",
        "douyin": "review_douyin.json",
        "amap": "review_amap.json",
        "meituan": "delivery_meituan.json",
        "eleme": "delivery_eleme.json",
        "jdwm": "delivery_jdwm.json",
    }
    return mapping[platform_key]


def load_snapshot_payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def summarize_deliverable_platform(
    platform_key: str,
    platform_conf: dict[str, object],
    step: dict[str, object],
    snapshot: dict[str, object],
) -> tuple[str, str, str]:
    captured_at = str(snapshot.get("captured_at", "")).strip()
    stores = snapshot.get("stores", [])
    metrics: dict[str, object] = {}
    if isinstance(stores, list) and stores and isinstance(stores[0], dict):
        maybe_metrics = stores[0].get("metrics", {})
        if isinstance(maybe_metrics, dict):
            metrics = maybe_metrics

    if platform_key == "meituan":
        if step.get("status") == "completed" and not metrics:
            return ("登录已通", "暂无经营快照", "验证码链路已过，后续补一次后台指标页即可")
    if platform_key == "amap":
        if metrics:
            return ("主数据已通", render_metric_brief(platform_key, metrics), "当前平台侧拿到的是门店主数据，不是经营看板")
        return ("已登录", "门店详情页可达", "高德当前只作为门店主数据补充，不阻塞首版交付")
    if metrics:
        return (
            "数据已落",
            render_metric_brief(platform_key, metrics),
            f"最新快照：{captured_at or '未写时间'}",
        )
    if step.get("status") == "completed":
        return ("登录已通", "暂无经营快照", "会话已打通，待补平台指标")
    return ("待补", "暂无结果", "当前还不能稳定产出平台数据")


def render_metric_brief(platform_key: str, metrics: dict[str, object]) -> str:
    if platform_key == "douyin":
        return (
            f"实时成交 {metrics.get('realtime_transaction_amount', '-')}"
            f" / 核销 {metrics.get('realtime_writeoff_amount', '-')}"
            f" / 曝光 {metrics.get('traffic_impressions', '-')}"
        )
    if platform_key == "dianping":
        return (
            f"成交额 {metrics.get('transaction_amount_discounted', '-')}"
            f" / 消费额 {metrics.get('consumption_amount', '-')}"
            f" / ROS {metrics.get('ros_score_avg', '-')}"
        )
    if platform_key == "eleme":
        return (
            f"预计收入 {metrics.get('estimated_income_today', '-')}"
            f" / 营业额 {metrics.get('transaction_amount_today', '-')}"
            f" / 有效订单 {metrics.get('valid_orders', '-')}"
        )
    if platform_key == "jdwm":
        return (
            f"预计收入 {metrics.get('estimated_income_today', '-')}"
            f" / 有效订单 {metrics.get('valid_orders', '-')}"
            f" / 曝光 {metrics.get('exposure_count_yesterday', '-')}"
        )
    if platform_key == "meituan":
        return (
            f"预计收入 {metrics.get('estimated_income_today', '-')}"
            f" / 有效订单 {metrics.get('valid_orders', '-')}"
            f" / 店铺分 {metrics.get('store_score_today', '-')}"
        )
    if platform_key == "amap":
        return (
            f"门店 {metrics.get('dashboard_store_name_text', '-')}"
            f" / 状态 {metrics.get('status_text', '-')}"
            f" / 认领 {metrics.get('claim_status_text', '-')}"
        )
    return "已接入"


def _row_to_dict(header: list[str], row: list[str]) -> dict[str, str]:
    return {
        header[idx]: str(row[idx]).strip() if idx < len(row) else ""
        for idx in range(len(header))
    }


def _read_first_sheet_rows(xlsx_path: Path) -> list[list[str]]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_ns = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    rows: list[list[str]] = []

    with ZipFile(xlsx_path) as archive:
        shared_strings = _read_shared_strings(archive, ns)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        first_sheet = workbook.find("a:sheets/a:sheet", ns)
        if first_sheet is None:
            return rows

        rel_id = first_sheet.attrib[f"{{{rel_ns['r']}}}id"]
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = ""
        for rel in rels:
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib.get("Target", "")
                break
        if not target:
            return rows

        sheet = ET.fromstring(archive.read(f"xl/{target}"))
        for row in sheet.findall(".//a:sheetData/a:row", ns):
            values: list[str] = []
            for cell in row.findall("a:c", ns):
                cell_type = cell.attrib.get("t")
                value = cell.find("a:v", ns)
                if value is None:
                    values.append("")
                    continue
                raw = value.text or ""
                if cell_type == "s":
                    values.append(shared_strings[int(raw)])
                else:
                    values.append(raw)
            rows.append(values)

    return rows


def _read_shared_strings(archive: ZipFile, ns: dict[str, str]) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(path))
    values: list[str] = []
    for item in root.findall("a:si", ns):
        fragments = [node.text or "" for node in item.findall(".//a:t", ns)]
        values.append("".join(fragments))
    return values
