"""Tests for model_input_coverage script helpers (loaded via importlib)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from football_ai.sources.flashscore_feed_match_meta import FlashscoreMatchMeta  # noqa: E402


def _load_mic():
    path = ROOT / "scripts" / "model_input_coverage.py"
    spec = importlib.util.spec_from_file_location("_model_input_coverage_mic", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    prev = sys.path[:]
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = prev
    return mod


_mic = _load_mic()


class TestModelInputCoverage(unittest.TestCase):
    def test_informational_must_have_zero_weight(self) -> None:
        blob = {
            "schema_version": "1",
            "slots": [
                {
                    "id": "bad",
                    "counts_toward_coverage": "informational",
                    "weight": 1.0,
                    "probe": "always_true_in_manifest_iteration",
                    "probe_args": {},
                },
            ],
        }
        with self.assertRaises(SystemExit):
            _mic.validate_manifest(blob)

    def test_flash_nonempty_strict_requires_magic(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ab12cd34").mkdir(parents=True)
            p = root / "ab12cd34" / "df_st_1_ab12cd34.txt"
            p.write_bytes(b"x" * 10)
            self.assertTrue(_mic.probe_flash_nonempty(root, "ab12cd34", "df_st", strict=False))
            self.assertFalse(_mic.probe_flash_nonempty(root, "ab12cd34", "df_st", strict=True))
            p.write_bytes(b"z" * 600 + b"~AA\xde")
            self.assertTrue(_mic.probe_flash_nonempty(root, "ab12cd34", "df_st", strict=True))

    def test_meta_kickoff_probe(self) -> None:
        ix_ok = {
            "e1": FlashscoreMatchMeta(
                event_id="e1",
                unix_kickoff=1_700_000_000,
                home_team="A",
                away_team="B",
            )
        }
        slot = {"probe": "meta_has_kickoff", "probe_args": {}}
        self.assertTrue(
            _mic.eval_slot(
                slot,
                dataset_label="x-2223",
                base=Path(),
                eid="e1",
                meta_ix=ix_ok,
                sup_buckets=_mic.EMPTY_SUP_BUCKETS,
                strict=False,
            )
        )
        ix_bad = {
            "e2": FlashscoreMatchMeta(event_id="e2", unix_kickoff=None, home_team="A", away_team="B"),
        }
        self.assertFalse(
            _mic.eval_slot(
                slot,
                dataset_label="x",
                base=Path(),
                eid="e2",
                meta_ix=ix_bad,
                sup_buckets=_mic.EMPTY_SUP_BUCKETS,
                strict=False,
            )
        )

    def test_flash_contains_rejects_short_substring(self) -> None:
        blob = {
            "schema_version": "1",
            "slots": [
                {
                    "id": "bad",
                    "counts_toward_coverage": "informational",
                    "weight": 0,
                    "probe": "flash_contains_any",
                    "probe_args": {"feed_suffix": "df_st", "substrings": ["x"]},
                },
            ],
        }
        with self.assertRaises(SystemExit):
            _mic.validate_manifest(blob)

    def test_flash_contains_any_matches(self) -> None:
        import tempfile

        tmp = tempfile.TemporaryDirectory
        with tmp() as td:
            root = Path(td)
            (root / "e1deadbe").mkdir()
            path = root / "e1deadbe" / "df_st_1_e1deadbe.txt"
            path.write_bytes(b"some binary\x00 STATS corner data")
            slot = {
                "probe": "flash_contains_any",
                "probe_args": {
                    "feed_suffix": "df_st",
                    "substrings": ["Corner"],
                    "case_insensitive": True,
                    "max_scan_bytes": 10000,
                },
            }
            self.assertTrue(
                _mic.eval_slot(
                    slot,
                    dataset_label="x",
                    base=root,
                    eid="e1deadbe",
                    meta_ix={},
                    sup_buckets=None,
                    strict=False,
                )
            )

    def test_supplement_bucket_hit(self) -> None:
        buckets = _mic.SupplementBuckets(
            fd_plus_mirror_union=frozenset({("lig-2223", "e1"), ("lig-2223", "e2")}),
            football_data_co_uk=frozenset({("lig-2223", "e1")}),
            mirror=frozenset({("lig-2223", "e2")}),
            esd=frozenset(),
        )
        slot_fd = {"probe": "supplement_bucket_hit", "probe_args": {"bucket": "football_data_co_uk"}}
        self.assertTrue(
            _mic.eval_slot(slot_fd, dataset_label="lig-2223", base=Path(), eid="e1", meta_ix={}, sup_buckets=buckets, strict=False)
        )
        self.assertFalse(
            _mic.eval_slot(slot_fd, dataset_label="lig-2223", base=Path(), eid="e2", meta_ix={}, sup_buckets=buckets, strict=False)
        )

    def test_flash_aa_rejects_short_field_key(self) -> None:
        blob = {
            "schema_version": "1",
            "slots": [
                {
                    "id": "bad",
                    "counts_toward_coverage": "informational",
                    "weight": 0,
                    "probe": "flash_aa_field_key_any",
                    "probe_args": {
                        "feed_suffix": "df_st",
                        "field_keys": ["A"],
                        "match_policy": "any",
                    },
                },
            ],
        }
        with self.assertRaises(SystemExit):
            _mic.validate_manifest(blob)

    def test_flash_aa_rejects_bad_match_policy(self) -> None:
        blob = {
            "schema_version": "1",
            "slots": [
                {
                    "id": "bad",
                    "counts_toward_coverage": "informational",
                    "weight": 0,
                    "probe": "flash_aa_field_key_any",
                    "probe_args": {
                        "feed_suffix": "df_st",
                        "field_keys": ["AG", "AH"],
                        "match_policy": "bogus",
                    },
                },
            ],
        }
        with self.assertRaises(SystemExit):
            _mic.validate_manifest(blob)

    def test_flash_aa_field_key_any_chunk_latin1(self) -> None:
        needle = ("\xac" + "PX" + "\xf7").encode("latin-1")
        self.assertTrue(
            _mic.flash_aa_field_key_chunk_matches(
                b"noise" + needle + b"z",
                {"field_keys": ["PX"], "match_policy": "any"},
            )
        )

    def test_flash_aa_field_key_any_chunk_utf8(self) -> None:
        chunk = ("pre" + "¬" + "PX" + "÷" + "post").encode("utf-8")
        self.assertTrue(
            _mic.flash_aa_field_key_chunk_matches(chunk, {"field_keys": ["px"], "match_policy": "any"})
        )

    def test_flash_aa_match_policy_all(self) -> None:
        chunk = ("\xac" + "PX" + "\xf7").encode("latin-1")
        self.assertTrue(_mic.flash_aa_field_key_chunk_matches(chunk, {"field_keys": ["PX", "PY"], "match_policy": "any"}))
        self.assertFalse(
            _mic.flash_aa_field_key_chunk_matches(chunk, {"field_keys": ["PX", "PY"], "match_policy": "all"})
        )

    def test_prefetch_caps_unions_suffix_scan_depth(self) -> None:
        slots = [
            {
                "probe": "flash_contains_any",
                "probe_args": {"feed_suffix": "df_st", "substrings": ["x"], "max_scan_bytes": 4096},
            },
            {
                "probe": "flash_aa_field_key_any",
                "probe_args": {"feed_suffix": "df_st", "field_keys": ["AG"], "max_scan_bytes": 8192},
            },
        ]
        caps = _mic.max_scan_caps_by_suffix(slots)
        self.assertEqual(caps["df_st"], 8192)


if __name__ == "__main__":
    unittest.main()
