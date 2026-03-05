from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from gb_monitor.models import MetricDatum


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    category TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    store_name TEXT NOT NULL,
                    metric_key TEXT NOT NULL,
                    metric_value_num REAL,
                    metric_value_text TEXT,
                    captured_at TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_metrics_platform_time
                    ON metrics(platform, captured_at);
                CREATE INDEX IF NOT EXISTS idx_metrics_store_time
                    ON metrics(store_id, captured_at);

                CREATE TABLE IF NOT EXISTS task_state (
                    task_name TEXT PRIMARY KEY,
                    last_success_at TEXT
                );
                """
            )

    def start_run(self, run_id: str, started_at: datetime, mode: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runs(run_id, started_at, mode, status) VALUES(?,?,?,?)",
                (run_id, started_at.isoformat(), mode, "running"),
            )

    def finish_run(self, run_id: str, finished_at: datetime, status: str, note: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET finished_at = ?, status = ?, note = ? WHERE run_id = ?",
                (finished_at.isoformat(), status, note, run_id),
            )

    def write_metrics(self, run_id: str, metrics: list[MetricDatum]) -> None:
        rows = [
            (
                run_id,
                m.task_name,
                m.platform,
                m.category,
                m.store_id,
                m.store_name,
                m.metric_key,
                m.metric_value_num,
                m.metric_value_text,
                m.captured_at.isoformat(),
                json.dumps(m.raw_payload, ensure_ascii=False),
            )
            for m in metrics
        ]
        if not rows:
            return
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO metrics(
                    run_id, task_name, platform, category, store_id, store_name,
                    metric_key, metric_value_num, metric_value_text, captured_at, raw_payload
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )

    def get_last_success(self, task_name: str) -> datetime | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT last_success_at FROM task_state WHERE task_name = ?",
                (task_name,),
            ).fetchone()
        if not row or not row[0]:
            return None
        return datetime.fromisoformat(row[0])

    def set_last_success(self, task_name: str, dt: datetime) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO task_state(task_name, last_success_at)
                VALUES(?,?)
                ON CONFLICT(task_name) DO UPDATE SET last_success_at = excluded.last_success_at
                """,
                (task_name, dt.isoformat()),
            )

    def summarize_recent(self, hours: int) -> list[tuple[str, str, int]]:
        threshold_ts = datetime.now(UTC).timestamp() - int(hours) * 3600
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT platform, metric_key, captured_at
                FROM metrics
                ORDER BY platform
                """
            ).fetchall()

        counter: dict[tuple[str, str], int] = {}
        for platform, metric_key, captured_at in rows:
            try:
                ts = datetime.fromisoformat(captured_at).timestamp()
            except ValueError:
                continue
            if ts < threshold_ts:
                continue
            key = (platform, metric_key)
            counter[key] = counter.get(key, 0) + 1

        merged = [(platform, metric_key, count) for (platform, metric_key), count in counter.items()]
        merged.sort(key=lambda x: (x[0], -x[2], x[1]))
        return merged
