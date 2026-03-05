from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


@dataclass(slots=True)
class Settings:
    timezone: ZoneInfo
    db_path: Path
    log_level: str
    feishu_webhook: str | None
    feishu_at_mobiles: list[str]
    data_files: dict[str, Path]

    @classmethod
    def from_env(cls) -> "Settings":
        tz_name = _get_env("GBM_TIMEZONE", "Asia/Shanghai")
        assert tz_name is not None
        timezone = ZoneInfo(tz_name)

        db_path = Path(_get_env("GBM_DB_PATH", "data/monitor.db") or "data/monitor.db")
        log_level = (_get_env("GBM_LOG_LEVEL", "INFO") or "INFO").upper()
        webhook = _get_env("GBM_FEISHU_WEBHOOK")

        mobiles_raw = _get_env("GBM_FEISHU_AT_MOBILES", "") or ""
        feishu_at_mobiles = [m.strip() for m in mobiles_raw.split(",") if m.strip()]

        file_env = {
            "review_dianping": _get_env("GBM_DIANGPING_FILE", "examples/review_dianping.json"),
            "review_douyin": _get_env("GBM_DOUYIN_FILE", "examples/review_douyin.json"),
            "review_amap": _get_env("GBM_AMAP_FILE", "examples/review_amap.json"),
            "delivery_meituan": _get_env("GBM_MEITUAN_FILE", "examples/delivery_meituan.json"),
            "delivery_eleme": _get_env("GBM_ELEME_FILE", "examples/delivery_eleme.json"),
            "delivery_jdwm": _get_env("GBM_JDWM_FILE", "examples/delivery_jdwm.json"),
        }
        data_files = {k: Path(v) for k, v in file_env.items() if v}

        return cls(
            timezone=timezone,
            db_path=db_path,
            log_level=log_level,
            feishu_webhook=webhook,
            feishu_at_mobiles=feishu_at_mobiles,
            data_files=data_files,
        )
