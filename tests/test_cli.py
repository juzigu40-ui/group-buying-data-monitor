from __future__ import annotations

import io
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gb_monitor.cli import main


class CliTests(unittest.TestCase):
    def test_feishu_ping_requires_webhook(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            with patch.dict(
                os.environ,
                {"GBM_DB_PATH": str(db_path)},
                clear=True,
            ):
                with patch("sys.argv", ["gbm", "feishu-ping"]):
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        rc = main()
        self.assertEqual(rc, 1)
        self.assertIn("delivered=False", stdout.getvalue())
        self.assertIn("error=missing_feishu_webhook", stdout.getvalue())

    def test_feishu_ping_sends_default_message(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            env = {
                "GBM_DB_PATH": str(db_path),
                "GBM_FEISHU_WEBHOOK": "https://example.com/webhook",
            }
            with patch.dict(os.environ, env, clear=True):
                with patch("sys.argv", ["gbm", "feishu-ping"]):
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        with patch(
                            "gb_monitor.cli.FeishuNotifier.send_text",
                            return_value=True,
                        ) as send_text:
                            rc = main()
        self.assertEqual(rc, 0)
        self.assertIn("delivered=True", stdout.getvalue())
        send_text.assert_called_once()
        self.assertIn("飞书 webhook 连通性测试", send_text.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
