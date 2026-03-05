from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PlatformAuth:
    auth_mode: str
    account_alias: str
    login_owner: str
    enabled: bool


@dataclass(slots=True)
class StoreEntry:
    store_id: str
    store_name: str
    city: str
    platforms: dict[str, PlatformAuth]


ALLOWED_AUTH_MODES = {"api", "cookie", "manual"}


def load_registry(path: Path) -> list[StoreEntry]:
    if not path.exists():
        raise FileNotFoundError(f"registry file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("registry root must be object")

    stores = payload.get("stores")
    if not isinstance(stores, list):
        raise ValueError("registry.stores must be list")

    entries: list[StoreEntry] = []
    for idx, item in enumerate(stores):
        if not isinstance(item, dict):
            raise ValueError(f"stores[{idx}] must be object")

        store_id = str(item.get("store_id", "")).strip()
        store_name = str(item.get("store_name", "")).strip()
        city = str(item.get("city", "")).strip()
        platform_map = item.get("platforms", {})

        if not store_id or not store_name:
            raise ValueError(f"stores[{idx}] missing store_id/store_name")
        if not isinstance(platform_map, dict):
            raise ValueError(f"stores[{idx}].platforms must be object")

        parsed: dict[str, PlatformAuth] = {}
        for platform, conf in platform_map.items():
            if not isinstance(conf, dict):
                raise ValueError(f"stores[{idx}].platforms.{platform} must be object")
            auth_mode = str(conf.get("auth_mode", "")).strip().lower()
            account_alias = str(conf.get("account_alias", "")).strip()
            login_owner = str(conf.get("login_owner", "")).strip()
            enabled = bool(conf.get("enabled", True))

            if auth_mode not in ALLOWED_AUTH_MODES:
                raise ValueError(
                    f"stores[{idx}].platforms.{platform}.auth_mode must be one of {sorted(ALLOWED_AUTH_MODES)}"
                )
            if not account_alias:
                raise ValueError(f"stores[{idx}].platforms.{platform}.account_alias is required")
            if not login_owner:
                raise ValueError(f"stores[{idx}].platforms.{platform}.login_owner is required")

            parsed[str(platform)] = PlatformAuth(
                auth_mode=auth_mode,
                account_alias=account_alias,
                login_owner=login_owner,
                enabled=enabled,
            )

        entries.append(
            StoreEntry(
                store_id=store_id,
                store_name=store_name,
                city=city,
                platforms=parsed,
            )
        )

    return entries


def summarize_registry(entries: list[StoreEntry]) -> dict[str, int]:
    summary: dict[str, int] = {
        "store_count": len(entries),
        "platform_bindings": 0,
        "api_bindings": 0,
        "cookie_bindings": 0,
        "manual_bindings": 0,
    }

    for store in entries:
        for auth in store.platforms.values():
            summary["platform_bindings"] += 1
            key = f"{auth.auth_mode}_bindings"
            summary[key] = summary.get(key, 0) + 1

    return summary


def enabled_platform_binding_counts(entries: list[StoreEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for store in entries:
        for platform, auth in store.platforms.items():
            if not auth.enabled:
                continue
            counts[platform] = counts.get(platform, 0) + 1
    return counts
