from __future__ import annotations

import unittest
from pathlib import Path

from gb_monitor.store_registry import (
    enabled_platform_binding_counts,
    load_registry,
    summarize_registry,
)


class StoreRegistryTests(unittest.TestCase):
    def test_load_registry_and_summary(self) -> None:
        entries = load_registry(Path("examples/stores_registry.json"))
        self.assertEqual(len(entries), 2)

        summary = summarize_registry(entries)
        self.assertEqual(summary["store_count"], 2)
        self.assertEqual(summary["platform_bindings"], 6)
        self.assertEqual(summary["cookie_bindings"], 3)
        self.assertEqual(summary["manual_bindings"], 3)

        platform_counts = enabled_platform_binding_counts(entries)
        self.assertEqual(platform_counts["dianping"], 2)
        self.assertEqual(platform_counts["douyin"], 1)
        self.assertEqual(platform_counts["meituan"], 1)


if __name__ == "__main__":
    unittest.main()
