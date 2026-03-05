from __future__ import annotations

import argparse
from datetime import datetime

from gb_monitor.config import Settings
from gb_monitor.feishu import FeishuNotifier, build_manual_report
from gb_monitor.logging import configure_logging
from gb_monitor.service import MonitorService, build_default_collectors
from gb_monitor.storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gbm", description="Group buying monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Initialize sqlite schema")

    run = sub.add_parser("run", help="Run data collection")
    run.add_argument("--mode", choices=["scheduled", "all"], default="scheduled")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--no-notify", action="store_true")

    report = sub.add_parser("report", help="Show recent metric count report")
    report.add_argument("--hours", type=int, default=24)

    return parser


def _print_summary(summary) -> None:  # noqa: ANN001
    print(f"run_id={summary.run_id}")
    print(f"mode={summary.mode}")
    print(f"metrics={summary.total_metrics}")
    print(f"stores={summary.total_stores}")
    if summary.collector_results:
        for item in summary.collector_results:
            print(
                f"collector={item.task_name} platform={item.platform} metrics={item.metric_count} stores={item.store_count}"
            )
    if summary.skipped_tasks:
        print("skipped=" + ",".join(summary.skipped_tasks))
    if summary.failed_tasks:
        print("failed=" + ",".join(summary.failed_tasks))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings.from_env()
    configure_logging(settings.log_level)
    storage = Storage(settings.db_path)

    if args.command == "init-db":
        storage.init_schema()
        print(f"initialized db: {settings.db_path}")
        return 0

    if args.command == "run":
        service = MonitorService(
            settings=settings,
            storage=storage,
            collectors=build_default_collectors(settings),
            notifier=FeishuNotifier(
                webhook=settings.feishu_webhook,
                at_mobiles=settings.feishu_at_mobiles,
            ),
        )
        summary = service.run(
            mode=args.mode,
            dry_run=args.dry_run,
            notify=not args.no_notify,
        )
        _print_summary(summary)
        return 0

    if args.command == "report":
        rows = storage.summarize_recent(hours=args.hours)
        print(build_manual_report(datetime.now(settings.timezone), rows))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
