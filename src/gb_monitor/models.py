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


@dataclass(slots=True)
class SignalRule:
    store_id: str
    store_name: str
    platform: str
    include_keywords: list[str]
    exact_include_keywords: list[str]
    exclude_keywords: list[str]
    required_all_keywords: list[str]
    required_context_keywords: list[str]
    required_location_keywords: list[str]
    required_any_fields: list[str]
    author_include_keywords: list[str]
    author_exclude_keywords: list[str]
    min_score: int = 5


@dataclass(slots=True)
class SignalCandidate:
    content_id: str
    platform: str
    title: str
    content: str
    poi_name: str
    author_name: str
    url: str
    published_at: str | None
    like_count: int
    comment_count: int
    share_count: int
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class SignalMatch:
    store_id: str
    store_name: str
    platform: str
    content_id: str
    url: str
    title: str
    author_name: str
    published_at: str | None
    like_count: int
    comment_count: int
    share_count: int
    score: int
    confidence: str
    matched_terms: list[str]
    matched_fields: list[str]
    reason: str
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class SignalRejection:
    store_id: str
    store_name: str
    platform: str
    content_id: str
    url: str
    title: str
    author_name: str
    published_at: str | None
    like_count: int
    comment_count: int
    share_count: int
    reason: str
    raw_payload: dict[str, Any]
