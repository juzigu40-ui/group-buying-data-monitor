from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class TaskSchedule:
    name: str
    kind: str


def _parse_hhmm(value: str | None, default: tuple[int, int]) -> tuple[int, int]:
    text = (value or "").strip()
    if not text:
        return default
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (TypeError, ValueError):
        return default
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return default
    return hour, minute


def _parse_positive_int(value: str | None, default: int) -> int:
    text = (value or "").strip()
    if not text:
        return default
    try:
        parsed = int(text)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return parsed


def _in_time_window(now: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    current = now.hour * 60 + now.minute
    start_min = start[0] * 60 + start[1]
    end_min = end[0] * 60 + end[1]
    return start_min <= current <= end_min


def due_for_review(now: datetime, last_success: datetime | None) -> bool:
    start = _parse_hhmm(os.getenv("GBM_REVIEW_WINDOW_START"), (10, 0))
    end = _parse_hhmm(os.getenv("GBM_REVIEW_WINDOW_END"), (20, 0))
    interval_minutes = _parse_positive_int(os.getenv("GBM_REVIEW_INTERVAL_MINUTES"), 120)
    if not _in_time_window(now, start, end):
        return False
    if last_success is None:
        return True
    return now - last_success >= timedelta(minutes=interval_minutes)


def due_for_delivery(now: datetime, last_success: datetime | None) -> bool:
    lunch_start = _parse_hhmm(os.getenv("GBM_DELIVERY_LUNCH_START"), (10, 30))
    lunch_end = _parse_hhmm(os.getenv("GBM_DELIVERY_LUNCH_END"), (12, 30))
    dinner_start = _parse_hhmm(os.getenv("GBM_DELIVERY_DINNER_START"), (17, 0))
    dinner_end = _parse_hhmm(os.getenv("GBM_DELIVERY_DINNER_END"), (19, 0))
    interval_minutes = _parse_positive_int(os.getenv("GBM_DELIVERY_INTERVAL_MINUTES"), 30)
    in_lunch = _in_time_window(now, lunch_start, lunch_end)
    in_dinner = _in_time_window(now, dinner_start, dinner_end)
    if not (in_lunch or in_dinner):
        return False
    if last_success is None:
        return True
    return now - last_success >= timedelta(minutes=interval_minutes)


def due_for_signal(now: datetime, last_success: datetime | None) -> bool:
    start = _parse_hhmm(os.getenv("GBM_SIGNAL_WINDOW_START"), (10, 0))
    end = _parse_hhmm(os.getenv("GBM_SIGNAL_WINDOW_END"), (21, 0))
    interval_minutes = _parse_positive_int(os.getenv("GBM_SIGNAL_INTERVAL_MINUTES"), 60)
    if not _in_time_window(now, start, end):
        return False
    if last_success is None:
        return True
    return now - last_success >= timedelta(minutes=interval_minutes)


def should_run(now: datetime, schedule_kind: str, last_success: datetime | None) -> bool:
    if schedule_kind == "review":
        return due_for_review(now, last_success)
    if schedule_kind == "delivery":
        return due_for_delivery(now, last_success)
    if schedule_kind == "signal":
        return due_for_signal(now, last_success)
    raise ValueError(f"Unknown schedule kind: {schedule_kind}")
