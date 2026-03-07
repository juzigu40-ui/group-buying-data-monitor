from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from gb_monitor.schedule import due_for_delivery, due_for_review, due_for_signal


TZ = ZoneInfo("Asia/Shanghai")


class ScheduleTests(unittest.TestCase):
    def test_due_for_review_in_window_when_no_history(self) -> None:
        now = datetime(2026, 3, 5, 10, 0, tzinfo=TZ)
        self.assertTrue(due_for_review(now, None))

    def test_due_for_review_outside_window(self) -> None:
        now = datetime(2026, 3, 5, 21, 0, tzinfo=TZ)
        self.assertFalse(due_for_review(now, None))

    def test_due_for_delivery_interval(self) -> None:
        now = datetime(2026, 3, 5, 11, 0, tzinfo=TZ)
        self.assertTrue(due_for_delivery(now, now - timedelta(minutes=31)))
        self.assertFalse(due_for_delivery(now, now - timedelta(minutes=15)))

    def test_due_for_signal_in_window(self) -> None:
        now = datetime(2026, 3, 5, 10, 0, tzinfo=TZ)
        self.assertTrue(due_for_signal(now, None))

    def test_due_for_signal_interval_and_outside_window(self) -> None:
        now = datetime(2026, 3, 5, 13, 0, tzinfo=TZ)
        self.assertTrue(due_for_signal(now, now - timedelta(hours=1, minutes=1)))
        self.assertFalse(due_for_signal(now, now - timedelta(minutes=20)))
        late = datetime(2026, 3, 5, 21, 30, tzinfo=TZ)
        self.assertFalse(due_for_signal(late, None))


if __name__ == "__main__":
    unittest.main()
