from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from gb_monitor.feishu import FeishuNotifier
from gb_monitor.signal_pipeline import (
    resolve_profile_signal_input_paths,
    run_profile_signal_pipeline,
)
from gb_monitor.storage import Storage


TZ = ZoneInfo("Asia/Shanghai")


class SignalPipelineTests(unittest.TestCase):
    def test_resolve_profile_signal_input_paths_prefers_standard_inputs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir)
            signal_inputs = profile_dir / "signal_inputs"
            signal_inputs.mkdir()
            (signal_inputs / "public_douyin.json").write_text(
                json.dumps({"platform": "douyin", "items": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (profile_dir / "douyin_signal_candidates.json").write_text(
                json.dumps(
                    {"platform": "douyin", "items": [{"content_id": "legacy-1", "title": "", "content": "", "author_name": "", "url": ""}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            paths = resolve_profile_signal_input_paths(profile_dir)
            self.assertEqual(paths, [signal_inputs / "public_douyin.json"])

    def test_run_profile_signal_pipeline_builds_report_and_board(self) -> None:
        with TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir)
            signal_inputs = profile_dir / "signal_inputs"
            signal_inputs.mkdir()
            (profile_dir / "store_signal_rules.json").write_text(
                json.dumps(
                    {
                        "stores": [
                            {
                                "store_id": "bj-fzy",
                                "store_name": "凤状元·江西小炒·非遗米粉(食宝街店)",
                                "platform": "douyin",
                                "include_keywords": ["凤状元", "江西小炒", "食宝街店"],
                                "exact_include_keywords": ["凤状元·江西小炒·非遗米粉(食宝街店)"],
                                "exclude_keywords": ["加盟", "招商"],
                                "required_all_keywords": [],
                                "required_context_keywords": ["探店", "米粉", "小炒"],
                                "required_location_keywords": ["北京", "食宝街店"],
                                "required_any_fields": ["title", "content", "poi_name"],
                                "author_include_keywords": [],
                                "author_exclude_keywords": [],
                                "focus_author_names": ["北京探店小林"],
                                "focus_author_tags": ["北京探店"],
                                "focus_verified_labels": ["探店达人"],
                                "min_follower_count": 10000,
                                "require_poi": True,
                                "min_score": 8,
                            },
                            {
                                "store_id": "bj-fzy",
                                "store_name": "凤状元·江西小炒·非遗米粉(食宝街店)",
                                "platform": "xiaohongshu",
                                "include_keywords": ["凤状元", "江西小炒", "食宝街店"],
                                "exact_include_keywords": ["凤状元·江西小炒·非遗米粉(食宝街店)"],
                                "exclude_keywords": ["加盟", "招商"],
                                "required_all_keywords": [],
                                "required_context_keywords": ["探店", "米粉", "小炒"],
                                "required_location_keywords": ["北京", "食宝街店"],
                                "required_any_fields": ["title", "content", "poi_name"],
                                "author_include_keywords": [],
                                "author_exclude_keywords": [],
                                "min_score": 8,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (signal_inputs / "public_douyin.json").write_text(
                json.dumps(
                    {
                        "platform": "douyin",
                        "items": [
                            {
                                "content_id": "dy-001",
                                "title": "食宝街这家凤状元可以冲",
                                "content": "北京探店，凤状元这家米粉和江西小炒都很稳。",
                                "poi_name": "凤状元·江西小炒·非遗米粉(食宝街店)",
                                "author_name": "北京探店小林",
                                "author_level": "Lv.4",
                                "verified_label": "探店达人",
                                "follower_count": 56000,
                                "author_tags": ["北京探店", "美食博主"],
                                "ip_location": "北京",
                                "topic_tags": ["食宝街", "江西小炒"],
                                "url": "https://example.com/dy/001",
                                "published_at": "2026-03-07T12:00:00+08:00",
                                "like_count": 120,
                                "comment_count": 10,
                                "share_count": 4,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (signal_inputs / "public_xiaohongshu.json").write_text(
                json.dumps(
                    {
                        "platform": "xiaohongshu",
                        "items": [
                            {
                                "content_id": "xhs-001",
                                "title": "食宝街江西小炒笔记",
                                "content": "北京探店，凤状元这家门店可以试试。",
                                "poi_name": "凤状元·江西小炒·非遗米粉(食宝街店)",
                                "author_name": "北京探店阿宁",
                                "author_level": "Lv.5",
                                "ip_location": "北京",
                                "topic_tags": ["食宝街", "江西小炒"],
                                "url": "https://example.com/xhs/001",
                                "published_at": "2026-03-07T13:00:00+08:00",
                                "like_count": 80,
                                "favorite_count": 18,
                                "comment_count": 5,
                                "share_count": 2,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (signal_inputs / "public_shipinhao.json").write_text(
                json.dumps({"platform": "shipinhao", "items": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            storage = Storage(profile_dir / "monitor.db")
            storage.init_schema()
            result = run_profile_signal_pipeline(
                profile_dir=profile_dir,
                storage=storage,
                notifier=FeishuNotifier(webhook=None, at_mobiles=[]),
                timezone=TZ,
                mode="all",
                notify=False,
                mark_dispatched=False,
                dedupe_hours=24,
                min_score_override=None,
            )
            self.assertTrue(result.executed)
            self.assertEqual(result.candidate_count, 2)
            self.assertEqual(result.match_count, 2)
            self.assertEqual(result.deduped_match_count, 2)
            self.assertIn("门店实时舆情精筛结果", result.report_text)
            self.assertIn("凤状元·江西小炒·非遗米粉(食宝街店)", result.report_text)
            self.assertIn("认证信息: 探店达人", result.report_text)
            self.assertIn("粉丝量: 56000", result.report_text)
            self.assertIn("重点达人命中:", result.report_text)
            self.assertIn("北京探店小林", result.report_text)
            self.assertIn("北京探店", result.report_text)
            self.assertIn("探店达人", result.report_text)
            self.assertIn("# 门店实时舆情看板", result.board_text)
            self.assertIn("粉丝56000", result.board_text)
            self.assertIn("重点名单", result.board_text)
            self.assertIn("当前窗口数据不足", result.board_text)
            self.assertIsNotNone(storage.get_last_success("signal_watchboard"))


if __name__ == "__main__":
    unittest.main()
