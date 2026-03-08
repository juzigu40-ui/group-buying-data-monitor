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

    def test_profile_readiness_reports_missing_items(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            profile_dir = Path(tmpdir) / "profile"
            profile_dir.mkdir()
            with patch.dict(
                os.environ,
                {"GBM_DB_PATH": str(db_path)},
                clear=True,
            ):
                with patch(
                    "sys.argv",
                    ["gbm", "profile-readiness", "--profile-dir", str(profile_dir), "--require-feishu"],
                ):
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        rc = main()
        self.assertEqual(rc, 1)
        self.assertIn("profile_ready=False", stdout.getvalue())
        self.assertIn("GBM_FEISHU_WEBHOOK", stdout.getvalue())

    def test_profile_readiness_reports_ready(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            profile_dir = Path(tmpdir) / "profile"
            signal_inputs = profile_dir / "signal_inputs"
            signal_inputs.mkdir(parents=True)
            (profile_dir / "login_inventory.local.json").write_text("{}", encoding="utf-8")
            (profile_dir / "stores_registry.json").write_text("[]", encoding="utf-8")
            (profile_dir / "store_signal_rules.json").write_text('{"stores":[]}', encoding="utf-8")
            (signal_inputs / "public_douyin.json").write_text('{"platform":"douyin","items":[]}', encoding="utf-8")
            env = {
                "GBM_DB_PATH": str(db_path),
                "GBM_FEISHU_WEBHOOK": "https://example.com/webhook",
            }
            with patch.dict(os.environ, env, clear=True):
                with patch(
                    "sys.argv",
                    ["gbm", "profile-readiness", "--profile-dir", str(profile_dir), "--require-feishu"],
                ):
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        rc = main()
        self.assertEqual(rc, 0)
        self.assertIn("profile_ready=True", stdout.getvalue())
        self.assertIn("next_step=run_profile", stdout.getvalue())

    def test_profile_readiness_requires_source_binding_for_kpi_mode(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            profile_dir = Path(tmpdir) / "profile"
            signal_inputs = profile_dir / "signal_inputs"
            signal_inputs.mkdir(parents=True)
            (profile_dir / "login_inventory.local.json").write_text("{}", encoding="utf-8")
            (profile_dir / "stores_registry.json").write_text("[]", encoding="utf-8")
            (profile_dir / "store_signal_rules.json").write_text(
                '{"stores":[{"store_id":"s1","store_name":"测试门店","platform":"douyin","include_keywords":["测试"],"exact_include_keywords":[],"required_all_keywords":[],"required_context_keywords":[],"required_location_keywords":[],"exclude_keywords":[],"author_include_keywords":[],"author_exclude_keywords":[],"author_level_include_keywords":[],"required_any_fields":["title","content"],"min_score":1,"daily_target_count":3,"require_source_store":true}]}',
                encoding="utf-8",
            )
            (signal_inputs / "public_douyin.json").write_text(
                '{"platform":"douyin","items":[{"content_id":"1","title":"测试","content":"测试","author_name":"用户","url":"https://example.com/1"}]}',
                encoding="utf-8",
            )
            env = {
                "GBM_DB_PATH": str(db_path),
                "GBM_FEISHU_WEBHOOK": "https://example.com/webhook",
            }
            with patch.dict(os.environ, env, clear=True):
                with patch(
                    "sys.argv",
                    ["gbm", "profile-readiness", "--profile-dir", str(profile_dir), "--require-feishu"],
                ):
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        rc = main()
        self.assertEqual(rc, 1)
        self.assertIn("store_kpi_mode=enabled", stdout.getvalue())
        self.assertIn("source_store_binding=missing", stdout.getvalue())
        self.assertIn("missing=source_store_binding", stdout.getvalue())

    def test_profile_readiness_accepts_source_binding_for_kpi_mode(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            profile_dir = Path(tmpdir) / "profile"
            signal_inputs = profile_dir / "signal_inputs"
            signal_inputs.mkdir(parents=True)
            (profile_dir / "login_inventory.local.json").write_text("{}", encoding="utf-8")
            (profile_dir / "stores_registry.json").write_text("[]", encoding="utf-8")
            (profile_dir / "store_signal_rules.json").write_text(
                '{"stores":[{"store_id":"s1","store_name":"测试门店","platform":"douyin","include_keywords":["测试"],"exact_include_keywords":[],"required_all_keywords":[],"required_context_keywords":[],"required_location_keywords":[],"exclude_keywords":[],"author_include_keywords":[],"author_exclude_keywords":[],"author_level_include_keywords":[],"required_any_fields":["title","content"],"min_score":1,"daily_target_count":3,"require_source_store":true}]}',
                encoding="utf-8",
            )
            (signal_inputs / "public_douyin.json").write_text(
                '{"platform":"douyin","items":[{"content_id":"1","title":"测试","content":"测试","author_name":"用户","url":"https://example.com/1","source_store_id":"s1","source_store_name":"测试门店"}]}',
                encoding="utf-8",
            )
            env = {
                "GBM_DB_PATH": str(db_path),
                "GBM_FEISHU_WEBHOOK": "https://example.com/webhook",
            }
            with patch.dict(os.environ, env, clear=True):
                with patch(
                    "sys.argv",
                    ["gbm", "profile-readiness", "--profile-dir", str(profile_dir), "--require-feishu"],
                ):
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        rc = main()
        self.assertEqual(rc, 0)
        self.assertIn("store_kpi_mode=enabled", stdout.getvalue())
        self.assertIn("source_store_binding=ok", stdout.getvalue())
        self.assertIn("profile_ready=True", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
