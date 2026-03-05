from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from gb_monitor.models import MetricDatum


@dataclass(slots=True)
class Collector:
    task_name: str
    platform: str
    category: str
    source_file: Path

    def collect(self, now: datetime) -> list[MetricDatum]:
        if not self.source_file.exists():
            return []

        data = json.loads(self.source_file.read_text(encoding="utf-8"))
        captured_at = _parse_captured_at(data.get("captured_at"), now)

        records: list[MetricDatum] = []
        for store in data.get("stores", []):
            store_id = str(store.get("store_id", ""))
            store_name = str(store.get("store_name", ""))
            metrics: dict[str, Any] = store.get("metrics", {})
            for metric_key, metric_value in metrics.items():
                num, text = _split_metric_value(metric_value)
                records.append(
                    MetricDatum(
                        task_name=self.task_name,
                        platform=self.platform,
                        category=self.category,
                        store_id=store_id,
                        store_name=store_name,
                        metric_key=str(metric_key),
                        metric_value_num=num,
                        metric_value_text=text,
                        captured_at=captured_at,
                        raw_payload={"store": store, "source_file": str(self.source_file)},
                    )
                )
        return records


def _parse_captured_at(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return fallback
    return fallback


def _split_metric_value(value: Any) -> tuple[float | None, str | None]:
    if isinstance(value, bool):
        return (1.0 if value else 0.0), str(value)
    if isinstance(value, int | float):
        return float(value), str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None, None
        try:
            return float(cleaned), cleaned
        except ValueError:
            return None, cleaned
    return None, str(value)
