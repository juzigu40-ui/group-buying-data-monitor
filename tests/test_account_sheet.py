from __future__ import annotations

import unittest

from gb_monitor.account_sheet import (
    PlatformAccountRecord,
    build_client_verification_message,
    build_execution_board,
    build_snapshot_payloads,
    build_profile_execution_board,
    build_profile_status,
    build_account_alias,
    build_login_checklist,
    build_signal_rules_payload,
    build_store_id,
    build_store_registry_payload,
    build_verification_plan_payload,
    infer_auth_mode,
    extract_store_keywords,
    needs_verification,
    next_verification_target,
    normalize_platform,
    update_verification_status,
)
from pathlib import Path
from tempfile import TemporaryDirectory
import json


class AccountSheetTests(unittest.TestCase):
    def test_normalize_platform_maps_taobao_flash_sale_to_eleme(self) -> None:
        self.assertEqual(normalize_platform("淘宝闪购"), "eleme")
        self.assertEqual(normalize_platform("饿了么"), "eleme")

    def test_build_store_registry_payload_marks_manual_auth(self) -> None:
        records = [
            PlatformAccountRecord(
                platform_label="大众点评",
                platform_key="dianping",
                store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
                city="北京",
                store_link="https://example.com/dianping",
                account="anrangongzuoshi",
                password="secret",
                login_method="验证码登录",
                second_factor="首次外地登录需要二次验证",
            ),
            PlatformAccountRecord(
                platform_label="淘宝闪购",
                platform_key="eleme",
                store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
                city="北京",
                store_link="",
                account="15311099858",
                password="",
                login_method="验证码登录",
                second_factor="无",
            ),
        ]

        payload = build_store_registry_payload(
            store_id=build_store_id("北京", records[0].store_name),
            records=records,
        )
        store = payload["stores"][0]
        self.assertEqual(store["platforms"]["dianping"]["auth_mode"], "manual")
        self.assertEqual(store["platforms"]["eleme"]["account_alias"], "eleme_15311099858")

    def test_checklist_calls_out_verification(self) -> None:
        record = PlatformAccountRecord(
            platform_label="美团外卖",
            platform_key="meituan",
            store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
            city="北京",
            store_link="http://dpurl.cn/demo",
            account="mt099858wr",
            password="secret",
            login_method="验证码登录",
            second_factor="首次外地登录需要二次验证",
        )
        self.assertTrue(needs_verification(record))
        text = build_login_checklist([record])
        self.assertIn("需要用户配合", text)
        self.assertIn("首次外地登录需要二次验证", text)

    def test_alias_and_auth_helpers(self) -> None:
        record = PlatformAccountRecord(
            platform_label="抖音",
            platform_key="douyin",
            store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
            city="北京",
            store_link="",
            account="13311549056",
            password="secret",
            login_method="验证码登录",
            second_factor="无",
        )
        self.assertEqual(build_account_alias(record), "douyin_13311549056")
        self.assertEqual(infer_auth_mode("验证码登录"), "manual")

    def test_extract_store_keywords_keeps_store_and_subparts(self) -> None:
        keywords = extract_store_keywords("凤状元·江西小炒·非遗米粉(食宝街店)")
        self.assertIn("凤状元·江西小炒·非遗米粉(食宝街店)", keywords)
        self.assertIn("凤状元", keywords)
        self.assertIn("江西小炒", keywords)
        self.assertIn("非遗米粉(食宝街店)", keywords)
        self.assertIn("食宝街店", keywords)

    def test_build_signal_rules_payload_covers_public_platforms(self) -> None:
        primary = PlatformAccountRecord(
            platform_label="抖音",
            platform_key="douyin",
            store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
            city="北京",
            store_link="",
            account="13311549056",
            password="secret",
            login_method="验证码登录",
            second_factor="无",
        )
        payload = build_signal_rules_payload("bj-store-001", primary)
        platforms = [item["platform"] for item in payload["stores"]]
        self.assertEqual(platforms, ["douyin", "xiaohongshu", "shipinhao"])

    def test_next_verification_target_returns_highest_priority_step(self) -> None:
        records = [
            PlatformAccountRecord(
                platform_label="美团外卖",
                platform_key="meituan",
                store_name="店",
                city="北京",
                store_link="",
                account="mt",
                password="secret",
                login_method="验证码登录",
                second_factor="首次外地登录需要二次验证",
            ),
            PlatformAccountRecord(
                platform_label="抖音",
                platform_key="douyin",
                store_name="店",
                city="北京",
                store_link="",
                account="dy",
                password="secret",
                login_method="验证码登录",
                second_factor="无",
            ),
        ]
        plan = build_verification_plan_payload(records)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "verification_plan.json"
            path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            step = next_verification_target(Path(tmpdir))
            self.assertIsNotNone(step)
            assert step is not None
            self.assertEqual(step["platform_key"], "douyin")

    def test_update_verification_status_advances_queue(self) -> None:
        records = [
            PlatformAccountRecord(
                platform_label="抖音",
                platform_key="douyin",
                store_name="店",
                city="北京",
                store_link="",
                account="dy",
                password="secret",
                login_method="验证码登录",
                second_factor="无",
            ),
            PlatformAccountRecord(
                platform_label="大众点评",
                platform_key="dianping",
                store_name="店",
                city="北京",
                store_link="",
                account="dp",
                password="secret",
                login_method="验证码登录",
                second_factor="首次外地登录需要二次验证",
            ),
        ]
        plan = build_verification_plan_payload(records)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "verification_plan.json"
            path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            (Path(tmpdir) / "login_inventory.local.json").write_text(
                json.dumps(
                    {
                        "store_name": "店",
                        "city": "北京",
                        "platforms": {
                            "douyin": {
                                "platform_label": "抖音",
                                "account": "dy",
                                "login_method": "验证码登录",
                                "second_factor": "无",
                                "store_link": "",
                            },
                            "dianping": {
                                "platform_label": "大众点评",
                                "account": "dp",
                                "login_method": "验证码登录",
                                "second_factor": "首次外地登录需要二次验证",
                                "store_link": "",
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            update_verification_status(Path(tmpdir), "douyin", "completed")
            step = next_verification_target(Path(tmpdir))
            self.assertIsNotNone(step)
            assert step is not None
            self.assertEqual(step["platform_key"], "dianping")
            board = (Path(tmpdir) / "execution_board.md").read_text(encoding="utf-8")
            self.assertIn("| 抖音 |", board)
            self.assertIn("已完成验证", board)

    def test_build_client_verification_message_uses_current_step(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "login_inventory.local.json").write_text(
                json.dumps(
                    {
                        "store_name": "凤状元·江西小炒·非遗米粉(食宝街店)",
                        "platforms": {
                            "douyin": {
                                "account": "13311549056",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (tmp / "verification_plan.json").write_text(
                json.dumps(
                    {
                        "steps": [
                            {
                                "platform_key": "douyin",
                                "platform_label": "抖音",
                                "priority": 1,
                                "status": "pending",
                                "verification_required": True,
                                "login_method": "验证码登录",
                                "second_factor": "无",
                                "store_link": "",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            message = build_client_verification_message(tmp)
            self.assertIn("抖音", message)
            self.assertIn("13311549056", message)
            self.assertIn("验证码", message)

    def test_build_profile_status_summarizes_queue_and_gaps(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "login_inventory.local.json").write_text(
                json.dumps(
                    {
                        "store_name": "凤状元·江西小炒·非遗米粉(食宝街店)",
                        "platforms": {
                            "douyin": {
                                "platform_label": "抖音",
                                "login_method": "验证码登录",
                                "store_link": "https://example.com/dy",
                            },
                            "amap": {
                                "platform_label": "高德",
                                "login_method": "",
                                "store_link": "",
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (tmp / "verification_plan.json").write_text(
                json.dumps(
                    {
                        "steps": [
                            {
                                "platform_key": "douyin",
                                "platform_label": "抖音",
                                "priority": 1,
                                "status": "pending",
                                "verification_required": True,
                                "login_method": "验证码登录",
                                "second_factor": "无",
                                "store_link": "https://example.com/dy",
                            },
                            {
                                "platform_key": "amap",
                                "platform_label": "高德",
                                "priority": 6,
                                "status": "not_required",
                                "verification_required": False,
                                "login_method": "",
                                "second_factor": "",
                                "store_link": "",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            text = build_profile_status(tmp)
            self.assertIn("待验证码: 1", text)
            self.assertIn("可直接推进: 1", text)
            self.assertIn("当前优先级: 抖音(douyin)", text)
            self.assertIn("高德 登录方式待确认", text)

    def test_build_execution_board_masks_account_and_lists_blockers(self) -> None:
        records = [
            PlatformAccountRecord(
                platform_label="抖音",
                platform_key="douyin",
                store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
                city="北京",
                store_link="https://example.com/dy",
                account="13311549056",
                password="secret",
                login_method="验证码登录",
                second_factor="无",
            ),
            PlatformAccountRecord(
                platform_label="高德",
                platform_key="amap",
                store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
                city="北京",
                store_link="",
                account="13311549056",
                password="",
                login_method="",
                second_factor="",
            ),
        ]
        board = build_execution_board(
            records,
            {
                "steps": [
                    {
                        "platform_key": "douyin",
                        "platform_label": "抖音",
                        "status": "pending",
                    },
                    {
                        "platform_key": "amap",
                        "platform_label": "高德",
                        "status": "not_required",
                    },
                ]
            },
        )
        self.assertIn("133****9056", board)
        self.assertIn("待验证码", board)
        self.assertIn("登录方式待确认", board)
        self.assertIn("店铺链接待补", board)

    def test_build_profile_execution_board_reads_local_profile(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "login_inventory.local.json").write_text(
                json.dumps(
                    {
                        "store_name": "凤状元·江西小炒·非遗米粉(食宝街店)",
                        "city": "北京",
                        "platforms": {
                            "douyin": {
                                "platform_label": "抖音",
                                "account": "13311549056",
                                "login_method": "验证码登录",
                                "second_factor": "无",
                                "store_link": "https://example.com/dy",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (tmp / "verification_plan.json").write_text(
                json.dumps(
                    {
                        "steps": [
                            {
                                "platform_key": "douyin",
                                "platform_label": "抖音",
                                "priority": 1,
                                "status": "pending",
                                "verification_required": True,
                                "login_method": "验证码登录",
                                "second_factor": "无",
                                "store_link": "https://example.com/dy",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            text = build_profile_execution_board(tmp)
            self.assertIn("单店执行面板", text)
            self.assertIn("抖音", text)
            self.assertIn("133****9056", text)

    def test_build_snapshot_payloads_creates_all_single_store_files(self) -> None:
        payloads = build_snapshot_payloads(
            "北京-凤状元-江西小炒-非遗米粉(食宝街店)",
            "凤状元·江西小炒·非遗米粉(食宝街店)",
        )
        self.assertEqual(
            sorted(payloads.keys()),
            [
                "delivery_eleme.json",
                "delivery_jdwm.json",
                "delivery_meituan.json",
                "review_amap.json",
                "review_dianping.json",
                "review_douyin.json",
            ],
        )
        self.assertEqual(
            payloads["review_douyin.json"]["stores"][0]["store_id"],
            "北京-凤状元-江西小炒-非遗米粉(食宝街店)",
        )
        self.assertEqual(
            payloads["delivery_meituan.json"]["stores"][0]["store_name"],
            "凤状元·江西小炒·非遗米粉(食宝街店)",
        )
        self.assertEqual(
            payloads["review_dianping.json"]["stores"][0]["metrics"],
            {},
        )


if __name__ == "__main__":
    unittest.main()
