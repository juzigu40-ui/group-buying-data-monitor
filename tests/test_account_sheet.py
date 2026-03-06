from __future__ import annotations

import unittest

from gb_monitor.account_sheet import (
    PlatformAccountRecord,
    build_account_alias,
    build_login_checklist,
    build_store_id,
    build_store_registry_payload,
    infer_auth_mode,
    needs_verification,
    normalize_platform,
)


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


if __name__ == "__main__":
    unittest.main()
