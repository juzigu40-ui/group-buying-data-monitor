from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gb_monitor.collectors import Collector


class CollectorTests(unittest.TestCase):
    def test_collector_parses_example_file(self) -> None:
        source = Path("examples/review_dianping.json")
        collector = Collector(
            task_name="review_dianping",
            platform="dianping",
            category="review",
            source_file=source,
        )
        now = datetime(2026, 3, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        metrics = collector.collect(now)
        self.assertTrue(metrics)
        self.assertTrue(all(m.task_name == "review_dianping" for m in metrics))
        keys = {m.metric_key for m in metrics}
        self.assertIn("new_reviews", keys)
        self.assertIn("taste_score", keys)


if __name__ == "__main__":
    unittest.main()
