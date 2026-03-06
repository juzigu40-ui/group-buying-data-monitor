from __future__ import annotations

import json
import logging
from datetime import datetime
from urllib import request

from gb_monitor.models import RunSummary

logger = logging.getLogger(__name__)


class FeishuNotifier:
    def __init__(self, webhook: str | None, at_mobiles: list[str]) -> None:
        self.webhook = webhook
        self.at_mobiles = at_mobiles

    def build_text(self, summary: RunSummary) -> str:
        lines = [
            "【团购/外卖监测任务运行结果】",
            f"运行ID: {summary.run_id}",
            f"模式: {summary.mode}",
            f"开始: {summary.started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"结束: {summary.finished_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"指标条数: {summary.total_metrics}",
            f"门店数: {summary.total_stores}",
        ]

        if summary.collector_results:
            lines.append("采集明细:")
            for item in summary.collector_results:
                lines.append(
                    f"- {item.task_name}: 指标{item.metric_count}条 / 门店{item.store_count}家"
                )

        if summary.skipped_tasks:
            lines.append("跳过任务: " + ", ".join(summary.skipped_tasks))
        if summary.failed_tasks:
            lines.append("失败任务: " + ", ".join(summary.failed_tasks))

        for mobile in self.at_mobiles:
            lines.append(f"<at user_id=\"{mobile}\"></at>")

        return "\n".join(lines)

    def send(self, summary: RunSummary) -> bool:
        text = self.build_text(summary)
        return self.send_text(text)

    def send_text(self, text: str) -> bool:
        if not self.webhook:
            logger.info("Feishu webhook not configured. Message:\n%s", text)
            return False

        body = {
            "msg_type": "text",
            "content": {"text": text},
        }
        payload = json.dumps(body).encode("utf-8")

        req = request.Request(
            self.webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as resp:
                _ = resp.read().decode("utf-8", errors="ignore")
                logger.info("Feishu notification sent, status=%s", resp.status)
                return 200 <= resp.status < 300
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send Feishu notification: %s", exc)
            return False


def build_manual_report(now: datetime, rows: list[tuple[str, str, int]]) -> str:
    if not rows:
        return f"[{now:%Y-%m-%d %H:%M:%S}] 近窗口内暂无数据"
    lines = [f"[{now:%Y-%m-%d %H:%M:%S}] 近窗口数据统计"]
    for platform, metric, count in rows:
        lines.append(f"- {platform} / {metric}: {count}")
    return "\n".join(lines)
