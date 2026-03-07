from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class TaskSchedule:
    name: str
    kind: str


def _in_time_window(now: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    current = now.hour * 60 + now.minute
    start_min = start[0] * 60 + start[1]
    end_min = end[0] * 60 + end[1]
    return start_min <= current <= end_min


def due_for_review(now: datetime, last_success: datetime | None) -> bool:
    if not _in_time_window(now, (10, 0), (20, 0)):
        return False
    if last_success is None:
        return True
    return now - last_success >= timedelta(hours=2)


def due_for_delivery(now: datetime, last_success: datetime | None) -> bool:
    in_lunch = _in_time_window(now, (10, 30), (12, 30))
    in_dinner = _in_time_window(now, (17, 0), (19, 0))
    if not (in_lunch or in_dinner):
        return False
    if last_success is None:
        return True
    return now - last_success >= timedelta(minutes=30)


def due_for_signal(now: datetime, last_success: datetime | None) -> bool:
    if not _in_time_window(now, (10, 0), (21, 0)):
        return False
    if last_success is None:
        return True
    return now - last_success >= timedelta(hours=1)


def should_run(now: datetime, schedule_kind: str, last_success: datetime | None) -> bool:
    if schedule_kind == "review":
        return due_for_review(now, last_success)
    if schedule_kind == "delivery":
        return due_for_delivery(now, last_success)
    if schedule_kind == "signal":
        return due_for_signal(now, last_success)
    raise ValueError(f"Unknown schedule kind: {schedule_kind}")
