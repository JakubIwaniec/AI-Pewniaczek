"""Schema smoke for scripts/integration_diag.py output."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCR = ROOT / "scripts"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(_SCR))

import integration_diag as idiag  # noqa: E402


class TestIntegrationDiag(unittest.TestCase):
    def test_run_diag_has_plan_fields(self):
        d = idiag.run_diag(fb_cache_mirror=False)
        self.assertEqual(d.get("schema_version"), "4")
        for key in (
            "generated_at",
            "ids_total_manifest_events",
            "ids_in_join_scope",
            "ids_never_attempted_join",
            "skipped_no_meta_by_dataset",
            "supplement_counters",
            "meta_state_per_event_aggregate",
            "kickoff_aggregate_global",
            "kickoff_histogram_by_dataset",
            "league_join_scope_table",
            "forensics_df_st_li",
            "baseline_bottleneck_hint",
            "ids_never_attempted_dataset_labels",
            "options",
        ):
            self.assertIn(key, d)
        sc = d["supplement_counters"]
        self.assertIsInstance(sc, dict)
        self.assertIn("skipped_no_meta", sc)
        self.assertIn("skipped_no_row", sc)
        self.assertEqual(sc["skipped_no_row"], sc["skipped_no_row_build_semantics"])
        self.assertIsInstance(d["baseline_bottleneck_hint"], str)
        self.assertGreater(len(d["baseline_bottleneck_hint"]), 0)
        opts = d["options"]
        self.assertIn("lookup_miss_diagnostic_radius_days", opts)
        skipped_ds = d["skipped_no_meta_by_dataset"]
        self.assertIsInstance(skipped_ds, dict)
        sum_miss = sum(int(rec["missing_meta"]) for rec in skipped_ds.values())  # type: ignore[arg-type]
        sum_scope = sum(int(rec["in_join_scope_events"]) for rec in skipped_ds.values())  # type: ignore[arg-type]
        self.assertEqual(sum_miss, sc["skipped_no_meta"])
        self.assertEqual(sum_scope, d["ids_in_join_scope"])
        for rec in skipped_ds.values():
            self.assertIn("missing_meta", rec)
            self.assertIn("in_join_scope_events", rec)
            self.assertIn("share", rec)
            self.assertGreaterEqual(rec["missing_meta"], 0)  # type: ignore[arg-type]
            den = rec["in_join_scope_events"]
            mo = rec["missing_meta"]
            shr = rec["share"]
            if den == 0:  # type: ignore[comparison-overlap]
                self.assertIsNone(shr)
            else:
                self.assertTrue(isinstance(shr, float) or isinstance(shr, int))
                self.assertAlmostEqual(float(shr), float(mo) / float(den), places=10)  # type: ignore[arg-type]
        lm_m = sc.get("breakdown_in_scope", {}).get("lookup_miss_given_valid_unix", 0)
        if isinstance(lm_m, int) and lm_m > 0:
            self.assertIn("lookup_miss_sample_meta", d)
            self.assertIn("lookup_miss_diagnosis_sample", d)
            self.assertIn("lookup_miss_category_histogram_sample", d)

        d_full = idiag.run_diag(
            fb_cache_mirror=False,
            lookup_miss_classify_full_population=True,
            skip_lookup_miss_sample=True,
        )
        self.assertEqual(d_full.get("schema_version"), "4")
        lm_full = d_full["supplement_counters"].get("breakdown_in_scope", {}).get(
            "lookup_miss_given_valid_unix", 0
        )
        if isinstance(lm_full, int) and lm_full > 0:
            self.assertIn("lookup_miss_category_histogram_population", d_full)
            self.assertIn("lookup_miss_category_histogram_by_dataset", d_full)
            by_ds = d_full["lookup_miss_category_histogram_by_dataset"]
            self.assertIsInstance(by_ds, dict)
            self.assertGreater(len(by_ds), 0)

    def test_stratified_sample_quotas(self) -> None:
        import random
        from collections import defaultdict

        pool = [{"dataset_label": "a"}] * 60 + [{"dataset_label": "b"}] * 30 + [{"dataset_label": "c"}] * 10
        sampled = idiag.stratified_sample_lookup_miss_pool(pool, 10, random.Random(0))
        cnt: defaultdict[str, int] = defaultdict(int)
        for r in sampled:
            cnt[r["dataset_label"]] += 1
        self.assertEqual(cnt["a"], 6)
        self.assertEqual(cnt["b"], 3)
        self.assertEqual(cnt["c"], 1)

    def test_sniff_bytes(self) -> None:
        blob = b"prefix~AAsuffix"
        s = idiag._sniff_raw_bytes(blob)
        self.assertTrue(s["has_tilde_aa"])


if __name__ == "__main__":
    unittest.main()
