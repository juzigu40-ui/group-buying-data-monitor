from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from gb_monitor.signal_rules import (
    build_signal_report,
    load_signal_candidates,
    load_signal_rules,
    match_candidates,
)


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


if __name__ == "__main__":
    unittest.main()
