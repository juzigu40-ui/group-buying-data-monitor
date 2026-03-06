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

    profile_dir.mkdir(parents=True, exist_ok=True)
    registry_path = profile_dir / "stores_registry.json"
    login_path = profile_dir / "login_inventory.local.json"
    checklist_path = profile_dir / "login_checklist.md"

    registry_path.write_text(
        json.dumps(store_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    login_path.write_text(
        json.dumps(login_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    checklist_path.write_text(checklist_text, encoding="utf-8")

    return {
        "stores_registry": registry_path,
        "login_inventory": login_path,
        "login_checklist": checklist_path,
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
