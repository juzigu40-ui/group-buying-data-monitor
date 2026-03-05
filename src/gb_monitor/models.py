from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class MetricDatum:
    task_name: str
    platform: str
    category: str
    store_id: str
    store_name: str
    metric_key: str
    metric_value_num: float | None
    metric_value_text: str | None
    captured_at: datetime
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class CollectorResult:
    task_name: str
    platform: str
    category: str
    metric_count: int
    store_count: int


@dataclass(slots=True)
class RunSummary:
    run_id: str
    started_at: datetime
    finished_at: datetime
    mode: str
    total_metrics: int
    total_stores: int
    collector_results: list[CollectorResult]
    skipped_tasks: list[str]
    failed_tasks: list[str]
