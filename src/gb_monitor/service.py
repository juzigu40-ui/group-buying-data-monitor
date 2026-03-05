from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from gb_monitor.collectors import Collector
from gb_monitor.config import Settings
from gb_monitor.feishu import FeishuNotifier
from gb_monitor.models import CollectorResult, RunSummary
from gb_monitor.schedule import should_run
from gb_monitor.storage import Storage

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MonitorService:
    settings: Settings
    storage: Storage
    collectors: list[Collector]
    notifier: FeishuNotifier

    def run(self, mode: str = "scheduled", dry_run: bool = False, notify: bool = True) -> RunSummary:
        if mode not in {"scheduled", "all"}:
            raise ValueError("mode must be 'scheduled' or 'all'")

        now = datetime.now(self.settings.timezone)
        started_at = now
        run_id = f"run-{started_at:%Y%m%d%H%M%S}-{uuid4().hex[:8]}"

        self.storage.init_schema()
        if not dry_run:
            self.storage.start_run(run_id=run_id, started_at=started_at, mode=mode)

        collector_results: list[CollectorResult] = []
        skipped_tasks: list[str] = []
        failed_tasks: list[str] = []
        total_metrics = 0
        total_stores = 0

        for collector in self.collectors:
            last_success = self.storage.get_last_success(collector.task_name)
            if mode == "scheduled" and not should_run(now, collector.category, last_success):
                skipped_tasks.append(collector.task_name)
                continue

            try:
                metrics = collector.collect(now)
                metric_count = len(metrics)
                store_count = len({(m.store_id, m.store_name) for m in metrics})

                if not dry_run and metric_count > 0:
                    self.storage.write_metrics(run_id=run_id, metrics=metrics)
                if not dry_run:
                    self.storage.set_last_success(collector.task_name, now)

                total_metrics += metric_count
                total_stores += store_count
                collector_results.append(
                    CollectorResult(
                        task_name=collector.task_name,
                        platform=collector.platform,
                        category=collector.category,
                        metric_count=metric_count,
                        store_count=store_count,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Collector failed: %s", collector.task_name)
                failed_tasks.append(f"{collector.task_name}({exc})")

        finished_at = datetime.now(self.settings.timezone)
        status = "success" if not failed_tasks else "partial_failed"

        summary = RunSummary(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            mode=mode,
            total_metrics=total_metrics,
            total_stores=total_stores,
            collector_results=collector_results,
            skipped_tasks=skipped_tasks,
            failed_tasks=failed_tasks,
        )

        if not dry_run:
            self.storage.finish_run(
                run_id=run_id,
                finished_at=finished_at,
                status=status,
                note=("" if status == "success" else "; ".join(failed_tasks)),
            )

        if notify:
            self.notifier.send(summary)

        return summary


def build_default_collectors(settings: Settings) -> list[Collector]:
    spec = [
        ("review_dianping", "dianping", "review"),
        ("review_douyin", "douyin", "review"),
        ("review_amap", "amap", "review"),
        ("delivery_meituan", "meituan", "delivery"),
        ("delivery_eleme", "eleme", "delivery"),
        ("delivery_jdwm", "jdwm", "delivery"),
    ]

    collectors: list[Collector] = []
    for task_name, platform, category in spec:
        source_file = settings.data_files[task_name]
        collectors.append(
            Collector(
                task_name=task_name,
                platform=platform,
                category=category,
                source_file=source_file,
            )
        )
    return collectors
