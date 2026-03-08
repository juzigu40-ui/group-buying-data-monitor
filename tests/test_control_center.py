from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from gb_monitor.control_center import (
    PlatformBindingConfig,
    StoreTargetConfig,
    load_env_values,
    load_registry_bindings,
    load_store_targets,
    save_registry_bindings,
    save_env_values,
    save_store_targets,
)


class ControlCenterTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
