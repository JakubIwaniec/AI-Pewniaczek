"""Tests for scripts/integration_gap_review.py."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCR = ROOT / "scripts"

sys.path.insert(0, str(_SCR))

import integration_gap_review as igr  # noqa: E402


class TestIntegrationGapReview(unittest.TestCase):
    def test_tier1_candidates_order_and_threshold(self):
        skipped = {
            "a-big": {"missing_meta": 10, "in_join_scope_events": 100, "share": 1.0},
            "c-small-scope": {"missing_meta": 5, "in_join_scope_events": 40, "share": 0.5},  # N<50 out
            "b-bigger": {"missing_meta": 20, "in_join_scope_events": 100, "share": 1.0},
            "low-share": {"missing_meta": 999, "in_join_scope_events": 1000, "share": 0.05},  # share out
        }
        tier = igr.tier1_candidates(skipped, min_n=50, min_share=0.2, top_k=10)
        self.assertEqual([t[0] for t in tier], ["b-bigger", "a-big"])

    def test_summarize_minimal_blob(self):
        blob = {
            "schema_version": "4",
            "generated_at": "2026-01-01T00:00:00Z",
            "git_rev_short": "abcd",
            "options": {
                "footballcsv_cache_fallback": False,
                "lookup_miss_classify_full_population": True,
                "skip_lookup_miss_sample": True,
            },
            "ids_total_manifest_events": 1000,
            "ids_in_join_scope": 800,
            "ids_never_attempted_join": 200,
            "supplement_counters": {
                "skipped_no_meta": 100,
                "skipped_no_row": 10,
                "join_would_succeed_count": 5,
                "breakdown_in_scope": {
                    "meta_no_valid_unix_attempted_lookup": 0,
                    "lookup_miss_given_valid_unix": 10,
                },
            },
            "skipped_no_meta_by_dataset": {
                "laliga-2526": {"missing_meta": 50, "in_join_scope_events": 50, "share": 1.0},
            },
            "lookup_miss_category_histogram_by_dataset": {
                "fa_cup-2526": {"csv_index_empty": 3},
            },
            "league_join_scope_table": [
                {"dataset_label": "x-y", "join_scope": "unsupported_league_key", "join_detail": "foo", "ids_event_count": 50, "ids_file": "present"},
            ],
            "baseline_bottleneck_hint": "test hint line",
        }
        txt = igr.summarize_blob(blob, tier1_top=12, tier1_min_n=50, tier1_min_share=0.2)
        self.assertIn("laliga-2526", txt)
        self.assertIn("fa_cup-2526", txt)
        self.assertIn("test hint line", txt)
        self.assertIn("skipped_no_meta=100", txt)


class TestTier1AgainstLatestJson(unittest.TestCase):
    def test_optional_latest_json_parse(self):
        p = ROOT / "data" / "integrated" / "integration_diag_latest.json"
        if not p.is_file():
            self.skipTest("no integration_diag_latest.json in checkout")
        blob = json.loads(p.read_text(encoding="utf-8-sig"))
        self.assertEqual(blob.get("schema_version"), "4")
        tier = igr.tier1_candidates(blob["skipped_no_meta_by_dataset"], min_n=50, min_share=0.2, top_k=12)
        self.assertGreaterEqual(len(tier), 1)


if __name__ == "__main__":
    unittest.main()
