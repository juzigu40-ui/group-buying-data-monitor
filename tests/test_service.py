from __future__ import annotations

import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from gb_monitor.config import Settings
from gb_monitor.feishu import FeishuNotifier
from gb_monitor.service import MonitorService, build_default_collectors
from gb_monitor.storage import Storage


class ServiceTests(unittest.TestCase):
    def test_service_run_all_mode(self) -> None:
        db_path = Path("data/test-monitor.db")
        if db_path.exists():
            db_path.unlink()

        settings = Settings(
            timezone=ZoneInfo("Asia/Shanghai"),
            db_path=db_path,
            log_level="INFO",
            feishu_webhook=None,
            feishu_at_mobiles=[],
            data_files={
                "review_dianping": Path("examples/review_dianping.json"),
                "review_douyin": Path("examples/review_douyin.json"),
                "review_amap": Path("examples/review_amap.json"),
                "delivery_meituan": Path("examples/delivery_meituan.json"),
                "delivery_eleme": Path("examples/delivery_eleme.json"),
                "delivery_jdwm": Path("examples/delivery_jdwm.json"),
            },
            store_registry_path=Path("examples/stores_registry.json"),
            signal_rules_path=Path("examples/store_signal_rules.template.json"),
        )

        storage = Storage(db_path)
        service = MonitorService(
            settings=settings,
            storage=storage,
            collectors=build_default_collectors(settings),
            notifier=FeishuNotifier(None, []),
        )

        summary = service.run(mode="all", dry_run=False, notify=False)
        self.assertGreater(summary.total_metrics, 0)
        self.assertEqual(len(summary.collector_results), 6)

        rows = storage.summarize_recent(hours=72)
        self.assertTrue(rows)

        if db_path.exists():
            db_path.unlink()

    def test_service_skips_tasks_without_platform_binding(self) -> None:
        db_path = Path("data/test-monitor-skip.db")
        if db_path.exists():
            db_path.unlink()

        settings = Settings(
            timezone=ZoneInfo("Asia/Shanghai"),
            db_path=db_path,
            log_level="INFO",
            feishu_webhook=None,
            feishu_at_mobiles=[],
            data_files={
                "review_dianping": Path("examples/review_dianping.json"),
                "review_douyin": Path("examples/review_douyin.json"),
                "review_amap": Path("examples/review_amap.json"),
                "delivery_meituan": Path("examples/delivery_meituan.json"),
                "delivery_eleme": Path("examples/delivery_eleme.json"),
                "delivery_jdwm": Path("examples/delivery_jdwm.json"),
            },
            store_registry_path=Path("examples/stores_registry.json"),
            signal_rules_path=Path("examples/store_signal_rules.template.json"),
        )

        storage = Storage(db_path)
        service = MonitorService(
            settings=settings,
            storage=storage,
            collectors=build_default_collectors(settings),
            notifier=FeishuNotifier(None, []),
            active_platforms={"dianping"},
            allowed_store_ids_by_platform={"dianping": {"non-existent-store-id"}},
        )
        summary = service.run(mode="all", dry_run=False, notify=False)
        self.assertEqual(len(summary.collector_results), 1)
        self.assertEqual(summary.total_metrics, 0)
        self.assertIn("review_douyin(no_account_binding)", summary.skipped_tasks)
        self.assertIn("review_amap(no_account_binding)", summary.skipped_tasks)

        if db_path.exists():
            db_path.unlink()


if __name__ == "__main__":
    unittest.main()
