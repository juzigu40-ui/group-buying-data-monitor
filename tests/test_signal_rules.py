from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from gb_monitor.models import SignalCandidate, SignalRule
from gb_monitor.signal_rules import (
    build_signal_dashboard,
    build_signal_report,
    load_signal_candidates,
    load_signal_rules,
    match_candidates,
    review_candidates,
)
from gb_monitor.storage import Storage


class SignalRuleTests(unittest.TestCase):
    def test_match_candidates_filters_noise_and_keeps_high_confidence_hits(self) -> None:
        rules = load_signal_rules(Path("examples/store_signal_rules.template.json"))
        candidates = load_signal_candidates(Path("examples/douyin_signal_candidates.json"))

        matches = match_candidates(rules, candidates)
        self.assertEqual(len(matches), 2)

        urls = {item.url for item in matches}
        self.assertIn("https://example.com/douyin/dy-001", urls)
        self.assertIn("https://example.com/douyin/dy-003", urls)
        self.assertNotIn("https://example.com/douyin/dy-002", urls)
        self.assertNotIn("https://example.com/douyin/dy-004", urls)

        first = matches[0]
        self.assertGreaterEqual(first.score, 5)
        self.assertTrue(first.matched_terms)
        self.assertTrue(first.matched_fields)

    def test_build_signal_report_prints_summary(self) -> None:
        rules = load_signal_rules(Path("examples/store_signal_rules.template.json"))
        candidates = load_signal_candidates(Path("examples/douyin_signal_candidates.json"))
        matches = match_candidates(rules, candidates)

        report = build_signal_report(datetime.now(), matches)
        self.assertIn("门店实时舆情精筛结果", report)
        self.assertIn("命中条数", report)
        self.assertIn("高置信", report)
        self.assertIn("热度", report)

    def test_build_signal_dashboard_prints_table(self) -> None:
        rules = load_signal_rules(Path("examples/store_signal_rules.template.json"))
        candidates = load_signal_candidates(Path("examples/douyin_signal_candidates.json"))
        matches, rejections = review_candidates(rules, candidates)

        board = build_signal_dashboard(datetime.now(), matches, rejections)
        self.assertIn("# 门店实时舆情看板", board)
        self.assertIn("## 平台分布", board)
        self.assertIn("| 平台 | 置信 | 分数 |", board)
        self.assertIn("## 已过滤噪音样例", board)

    def test_match_candidates_suppresses_ambiguous_store_hits(self) -> None:
        rules = [
            SignalRule(
                store_id="s1",
                store_name="杨记烤鱼(静安店)",
                platform="douyin",
                include_keywords=["杨记烤鱼", "静安"],
                exact_include_keywords=["杨记烤鱼(静安店)"],
                exclude_keywords=[],
                required_all_keywords=[],
                required_context_keywords=[],
                required_location_keywords=[],
                required_any_fields=["title", "content"],
                author_include_keywords=[],
                author_exclude_keywords=[],
                min_score=4,
            ),
            SignalRule(
                store_id="s2",
                store_name="杨记烤鱼(徐汇店)",
                platform="douyin",
                include_keywords=["杨记烤鱼", "静安"],
                exact_include_keywords=["杨记烤鱼(徐汇店)"],
                exclude_keywords=[],
                required_all_keywords=[],
                required_context_keywords=[],
                required_location_keywords=[],
                required_any_fields=["title", "content"],
                author_include_keywords=[],
                author_exclude_keywords=[],
                min_score=4,
            ),
        ]
        candidates = [
            SignalCandidate(
                content_id="dy-ambiguous",
                platform="douyin",
                title="杨记烤鱼最近很火",
                content="静安商圈这家店人很多，但没写具体门店。",
                poi_name="",
                author_name="探店路人",
                author_level="",
                ip_location="",
                topic_tags=[],
                url="https://example.com/ambiguous",
                published_at=None,
                like_count=0,
                favorite_count=0,
                comment_count=0,
                share_count=0,
                raw_payload={},
            )
        ]

        matches = match_candidates(rules, candidates)
        self.assertEqual(matches, [])

    def test_match_candidates_supports_required_all_and_author_filter(self) -> None:
        rules = [
            SignalRule(
                store_id="s1",
                store_name="杨记烤鱼(静安店)",
                platform="douyin",
                include_keywords=["双人烤鱼套餐"],
                exact_include_keywords=["杨记烤鱼(静安店)"],
                exclude_keywords=[],
                required_all_keywords=["静安", "烤鱼"],
                required_context_keywords=[],
                required_location_keywords=[],
                required_any_fields=["title", "content", "poi_name"],
                author_include_keywords=["探店"],
                author_exclude_keywords=["招商"],
                min_score=6,
            )
        ]
        candidates = [
            SignalCandidate(
                content_id="dy-author-ok",
                platform="douyin",
                title="静安这家烤鱼套餐怎么点",
                content="双人烤鱼套餐适合第一次来的人。",
                poi_name="杨记烤鱼(静安店)",
                author_name="探店阿青",
                author_level="",
                ip_location="",
                topic_tags=[],
                url="https://example.com/ok",
                published_at=None,
                like_count=0,
                favorite_count=0,
                comment_count=0,
                share_count=0,
                raw_payload={},
            ),
            SignalCandidate(
                content_id="dy-author-drop",
                platform="douyin",
                title="静安这家烤鱼套餐怎么点",
                content="双人烤鱼套餐适合第一次来的人。",
                poi_name="杨记烤鱼(静安店)",
                author_name="普通用户",
                author_level="",
                ip_location="",
                topic_tags=[],
                url="https://example.com/drop",
                published_at=None,
                like_count=0,
                favorite_count=0,
                comment_count=0,
                share_count=0,
                raw_payload={},
            ),
        ]

        matches = match_candidates(rules, candidates)
        self.assertEqual([item.content_id for item in matches], ["dy-author-ok"])

    def test_match_candidates_requires_context_for_ambiguous_brand_terms(self) -> None:
        rules = [
            SignalRule(
                store_id="s1",
                store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
                platform="douyin",
                include_keywords=["凤状元", "江西小炒", "食宝街店"],
                exact_include_keywords=["凤状元·江西小炒·非遗米粉(食宝街店)"],
                exclude_keywords=["戏曲", "状元媒"],
                required_all_keywords=[],
                required_context_keywords=["探店", "米粉", "小炒", "门店"],
                required_location_keywords=["北京", "食宝街店"],
                required_any_fields=["title", "content", "poi_name"],
                author_include_keywords=[],
                author_exclude_keywords=[],
                min_score=8,
            )
        ]
        candidates = [
            SignalCandidate(
                content_id="noise-1",
                platform="douyin",
                title="凤状元最新内容",
                content="山东省京剧院《状元媒》现场录制",
                poi_name="",
                author_name="戏曲账号",
                author_level="",
                ip_location="",
                topic_tags=[],
                url="https://example.com/noise-1",
                published_at=None,
                like_count=30,
                favorite_count=0,
                comment_count=1,
                share_count=0,
                raw_payload={},
            ),
            SignalCandidate(
                content_id="keep-1",
                platform="douyin",
                title="食宝街这家江西小炒可以冲",
                content="凤状元这家米粉和小炒都不错，算是北京探店里比较稳的。",
                poi_name="凤状元·江西小炒·非遗米粉(食宝街店)",
                author_name="北京探店小李",
                author_level="",
                ip_location="北京",
                topic_tags=["食宝街", "江西小炒"],
                url="https://example.com/keep-1",
                published_at=None,
                like_count=30,
                favorite_count=8,
                comment_count=1,
                share_count=0,
                raw_payload={},
            ),
        ]

        matches = match_candidates(rules, candidates)
        self.assertEqual([item.content_id for item in matches], ["keep-1"])

    def test_review_candidates_returns_rejection_reason_for_noise(self) -> None:
        rules = [
            SignalRule(
                store_id="s1",
                store_name="凤状元·江西小炒·非遗米粉(食宝街店)",
                platform="douyin",
                include_keywords=["凤状元", "江西小炒", "食宝街店"],
                exact_include_keywords=["凤状元·江西小炒·非遗米粉(食宝街店)"],
                exclude_keywords=["戏曲", "状元媒"],
                required_all_keywords=[],
                required_context_keywords=["探店", "米粉", "小炒", "门店"],
                required_location_keywords=["北京", "食宝街店"],
                required_any_fields=["title", "content", "poi_name"],
                author_include_keywords=[],
                author_exclude_keywords=[],
                min_score=8,
            )
        ]
        candidates = [
            SignalCandidate(
                content_id="noise-1",
                platform="douyin",
                title="凤状元最新内容",
                content="山东省京剧院《状元媒》现场录制",
                poi_name="",
                author_name="戏曲账号",
                author_level="",
                ip_location="",
                topic_tags=[],
                url="https://example.com/noise-1",
                published_at=None,
                like_count=30,
                favorite_count=0,
                comment_count=1,
                share_count=0,
                raw_payload={},
            ),
        ]

        matches, rejections = review_candidates(rules, candidates)
        self.assertEqual(matches, [])
        self.assertEqual(len(rejections), 1)
        self.assertIn("命中排除词", rejections[0].reason)

    def test_storage_filters_repeated_dispatches(self) -> None:
        rules = load_signal_rules(Path("examples/store_signal_rules.template.json"))
        candidates = load_signal_candidates(Path("examples/douyin_signal_candidates.json"))
        matches = match_candidates(rules, candidates)

        with TemporaryDirectory() as tmpdir:
            storage = Storage(Path(tmpdir) / "monitor.db")
            storage.init_schema()
            now = datetime.now()
            fresh = storage.filter_new_signal_matches(matches, now=now, dedupe_hours=24)
            self.assertEqual(len(fresh), len(matches))

            storage.record_signal_dispatches(dispatched_at=now, matches=fresh)
            repeated = storage.filter_new_signal_matches(matches, now=now, dedupe_hours=24)
            self.assertEqual(repeated, [])

    def test_load_signal_candidates_supports_xiaohongshu_extension_fields(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "public_xiaohongshu.json"
            path.write_text(
                """
{
  "platform": "xiaohongshu",
  "items": [
    {
      "content_id": "xhs-001",
      "title": "食宝街江西小炒笔记",
      "content": "凤状元这家门店值得试试",
      "author_name": "北京探店阿宁",
      "author_level": "Lv.5",
      "ip_location": "北京",
      "topic_tags": ["食宝街", "江西小炒"],
      "url": "https://example.com/xhs/001",
      "favorite_count": 22,
      "comment_count": 3,
      "share_count": 1
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )
            candidates = load_signal_candidates(path)
            self.assertEqual(candidates[0].author_level, "Lv.5")
            self.assertEqual(candidates[0].ip_location, "北京")
            self.assertEqual(candidates[0].topic_tags, ["食宝街", "江西小炒"])
            self.assertEqual(candidates[0].favorite_count, 22)


if __name__ == "__main__":
    unittest.main()
