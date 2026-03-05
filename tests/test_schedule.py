from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from gb_monitor.schedule import due_for_delivery, due_for_review


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


if __name__ == "__main__":
    unittest.main()
