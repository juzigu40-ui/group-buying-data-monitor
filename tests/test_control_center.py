from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from gb_monitor.control_center import (
    PlatformBindingConfig,
    SessionBindingConfig,
    StoreTargetConfig,
    compute_connection_snapshot,
    default_session_file,
    load_env_values,
    load_registry_bindings,
    load_session_bindings,
    load_store_targets,
    platform_display_name,
    save_registry_bindings,
    save_env_values,
    save_session_bindings,
    save_store_targets,
)


class ControlCenterTests(unittest.TestCase):
    def test_platform_display_name_uses_chinese_labels(self) -> None:
        self.assertEqual(platform_display_name("meituan"), "美团外卖")
        self.assertEqual(platform_display_name("dianping"), "大众点评")
        self.assertEqual(platform_display_name("douyin"), "抖音")
        self.assertEqual(platform_display_name("unknown"), "unknown")

    def test_env_round_trip_preserves_existing_lines(self) -> None:
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "# comment\nGBM_FEISHU_WEBHOOK=\nGBM_SIGNAL_INTERVAL_MINUTES=60\nOTHER=keep\n",
                encoding="utf-8",
            )
            save_env_values(
                env_path,
                {
                    "GBM_FEISHU_WEBHOOK": "https://example.com/hook",
                    "GBM_SIGNAL_INTERVAL_MINUTES": "30",
                    "GBM_SIGNAL_WINDOW_START": "09:00",
                },
            )
            self.assertEqual(
                load_env_values(env_path),
                {
                    "GBM_FEISHU_WEBHOOK": "https://example.com/hook",
                    "GBM_SIGNAL_INTERVAL_MINUTES": "30",
                    "OTHER": "keep",
                    "GBM_SIGNAL_WINDOW_START": "09:00",
                },
            )
            text = env_path.read_text(encoding="utf-8")
            self.assertIn("# comment", text)
            self.assertIn("OTHER=keep", text)

    def test_store_targets_group_and_save_back(self) -> None:
        with TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "store_signal_rules.json"
            payload = {
                "stores": [
                    {
                        "store_id": "s1",
                        "store_name": "门店一",
                        "platform": "douyin",
                        "daily_target_count": 1,
                        "require_source_store": False,
                    },
                    {
                        "store_id": "s1",
                        "store_name": "门店一",
                        "platform": "xiaohongshu",
                        "daily_target_count": 3,
                        "require_source_store": False,
                    },
                    {
                        "store_id": "s2",
                        "store_name": "门店二",
                        "platform": "douyin",
                        "daily_target_count": 2,
                        "require_source_store": True,
                    },
                ]
            }
            rules_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            grouped = load_store_targets(rules_path)
            self.assertEqual(
                [(item.store_id, item.daily_target_count, item.require_source_store) for item in grouped],
                [("s1", 3, False), ("s2", 2, True)],
            )

            save_store_targets(
                rules_path,
                [
                    StoreTargetConfig("s1", "门店一", 5, True),
                    StoreTargetConfig("s2", "门店二", 8, False),
                ],
            )
            updated = json.loads(rules_path.read_text(encoding="utf-8"))
            s1_rows = [item for item in updated["stores"] if item["store_id"] == "s1"]
            s2_rows = [item for item in updated["stores"] if item["store_id"] == "s2"]
            self.assertTrue(all(item["daily_target_count"] == 5 for item in s1_rows))
            self.assertTrue(all(item["require_source_store"] is True for item in s1_rows))
            self.assertTrue(all(item["daily_target_count"] == 8 for item in s2_rows))
            self.assertTrue(all(item["require_source_store"] is False for item in s2_rows))

    def test_registry_bindings_load_and_save_back(self) -> None:
        with TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "stores_registry.json"
            payload = {
                "stores": [
                    {
                        "store_id": "s1",
                        "store_name": "门店一",
                        "city": "北京",
                        "platforms": {
                            "douyin": {
                                "auth_mode": "manual",
                                "account_alias": "dy_1",
                                "login_owner": "A",
                                "enabled": True,
                            },
                            "meituan": {
                                "auth_mode": "cookie",
                                "account_alias": "mt_1",
                                "login_owner": "B",
                                "enabled": False,
                            },
                        },
                    }
                ]
            }
            registry_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            bindings = load_registry_bindings(registry_path)
            self.assertEqual(
                [(item.platform, item.auth_mode, item.account_alias, item.login_owner, item.enabled) for item in bindings],
                [
                    ("douyin", "manual", "dy_1", "A", True),
                    ("meituan", "cookie", "mt_1", "B", False),
                ],
            )

            save_registry_bindings(
                registry_path,
                [
                    PlatformBindingConfig("s1", "门店一", "douyin", "api", "dy_new", "C", False),
                    PlatformBindingConfig("s1", "门店一", "meituan", "manual", "mt_new", "D", True),
                ],
            )
            updated = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["stores"][0]["platforms"]["douyin"]["auth_mode"], "api")
            self.assertEqual(updated["stores"][0]["platforms"]["douyin"]["account_alias"], "dy_new")
            self.assertEqual(updated["stores"][0]["platforms"]["douyin"]["login_owner"], "C")
            self.assertFalse(updated["stores"][0]["platforms"]["douyin"]["enabled"])
            self.assertEqual(updated["stores"][0]["platforms"]["meituan"]["account_alias"], "mt_new")
            self.assertTrue(updated["stores"][0]["platforms"]["meituan"]["enabled"])

    def test_session_bindings_default_and_save_round_trip(self) -> None:
        with TemporaryDirectory() as tmpdir:
            session_path = Path(tmpdir) / "auth" / "session_registry.json"
            bindings = [
                PlatformBindingConfig("s1", "门店一", "meituan", "manual", "mt_1", "A", True),
                PlatformBindingConfig("s1", "门店一", "dianping", "manual", "dp_1", "A", False),
            ]

            loaded = load_session_bindings(session_path, bindings, "DESKTOP-001")
            self.assertEqual(loaded[0].machine_alias, "DESKTOP-001")
            self.assertEqual(loaded[0].session_file, default_session_file("meituan", "mt_1"))
            self.assertEqual(loaded[0].status, "未初始化")
            self.assertEqual(loaded[1].status, "已停用")

            save_session_bindings(
                session_path,
                [
                    SessionBindingConfig(
                        store_id="s1",
                        store_name="门店一",
                        platform="meituan",
                        machine_alias="DESKTOP-002",
                        session_file="auth/meituan__mt_1.state.json",
                        status="可复用",
                        last_login_at="2026-03-08 20:00",
                        note="首登完成",
                    )
                ],
            )
            reloaded = load_session_bindings(session_path, [bindings[0]], "DESKTOP-001")
            self.assertEqual(reloaded[0].machine_alias, "DESKTOP-002")
            self.assertEqual(reloaded[0].status, "可复用")
            self.assertEqual(reloaded[0].last_login_at, "2026-03-08 20:00")
            self.assertEqual(reloaded[0].note, "首登完成")

    def test_connection_snapshot_reports_normal_when_recent_metrics_exist(self) -> None:
        snapshot = compute_connection_snapshot(
            binding=SessionBindingConfig(
                store_id="s1",
                store_name="门店一",
                platform="meituan",
                machine_alias="DESKTOP-001",
                session_file="auth/meituan.state.json",
                status="可复用",
                last_login_at="",
                note="",
            ),
            env_values={"GBM_DELIVERY_INTERVAL_MINUTES": "30", "GBM_REVIEW_INTERVAL_MINUTES": "60"},
            task_success_map={"delivery_meituan": datetime(2026, 3, 9, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))},
            latest_metric_map={("s1", "meituan"): datetime(2026, 3, 9, 8, 55, tzinfo=ZoneInfo("Asia/Shanghai"))},
            now=datetime(2026, 3, 9, 9, 20, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        self.assertEqual(snapshot.connection_status, "正常")
        self.assertIn("最近这家门店已经成功出数", snapshot.connection_hint)

    def test_connection_snapshot_reports_relogin_when_marked_and_stale(self) -> None:
        snapshot = compute_connection_snapshot(
            binding=SessionBindingConfig(
                store_id="s1",
                store_name="门店一",
                platform="dianping",
                machine_alias="DESKTOP-001",
                session_file="auth/dianping.state.json",
                status="需补登录",
                last_login_at="",
                note="",
            ),
            env_values={"GBM_DELIVERY_INTERVAL_MINUTES": "30", "GBM_REVIEW_INTERVAL_MINUTES": "60"},
            task_success_map={},
            latest_metric_map={},
            now=datetime(2026, 3, 9, 9, 20, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        self.assertEqual(snapshot.connection_status, "需要补登")
        self.assertIn("需要补登", snapshot.connection_hint)


if __name__ == "__main__":
    unittest.main()
