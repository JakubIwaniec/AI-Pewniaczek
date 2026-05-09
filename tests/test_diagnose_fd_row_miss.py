"""Unit tests for diagnose_fd_row_miss (lookup miss taxonomy)."""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from football_ai.integration.join_football_data import CsvRowIndex, diagnose_fd_row_miss, lookup_fd_row
from football_ai.integration.normalize import norm_club


def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, 12, 0, tzinfo=UTC).timestamp())


class TestDiagnoseFdRowMiss(unittest.TestCase):
    def test_swap_category(self) -> None:
        base = datetime(2024, 6, 1, 14, tzinfo=UTC).date()
        nh_n = norm_club("Home A")
        na_n = norm_club("Away B")
        key_swapped = (base.year, base.month, base.day, na_n, nh_n)
        ix = CsvRowIndex(
            key_to_rows={
                key_swapped: [
                    {"Date": "2024-06-01", "home": "Away B", "visitor": "Home A"}
                ]
            }
        )
        ts = _ts(2024, 6, 1)
        self.assertIsNone(lookup_fd_row(ix, unix_ts=ts, nh="Home A", na="Away B"))
        cat, _ = diagnose_fd_row_miss(ix, unix_ts=ts, nh="Home A", na="Away B")
        self.assertEqual(cat, "would_match_team_order_swap")

    def test_ambiguous_or_dense_pm1(self) -> None:
        nh2, na2 = norm_club("X FC"), norm_club("Y FC")
        d = datetime(2024, 6, 2, 12, tzinfo=UTC).date()
        key = (d.year, d.month, d.day, nh2, na2)
        ix = CsvRowIndex(
            key_to_rows={
                key: [
                    {"Date": "2024-06-02", "home": "X FC", "visitor": "Y FC"},
                    {"Date": "2024-06-02", "home": "X FC", "visitor": "Y FC"},
                ],
            }
        )
        ts = _ts(2024, 6, 2)
        cat, _ = diagnose_fd_row_miss(ix, unix_ts=ts, nh="X FC", na="Y FC")
        self.assertEqual(cat, "ambiguous_or_dense_pm1")

    def test_single_hit_wide_outside_pm1(self) -> None:
        ts = _ts(2024, 6, 10)
        utc_d = datetime.fromtimestamp(ts, tz=UTC).date()
        nh2, na2 = norm_club("A"), norm_club("B")
        wd = utc_d + timedelta(days=2)
        key_hit = (wd.year, wd.month, wd.day, nh2, na2)
        ix = CsvRowIndex(
            key_to_rows={
                key_hit: [
                    {"Date": f"{wd.year}-{wd.month:02d}-{wd.day:02d}", "HomeTeam": "A", "AwayTeam": "B"}
                ]
            }
        )
        cat, ex = diagnose_fd_row_miss(
            ix, unix_ts=ts, nh="A", na="B", diagnostic_radius_days=7
        )
        self.assertEqual(cat, "single_hit_wide_pmR_only")
        self.assertEqual(ex.get("diagnostic_wide_radius_days"), 7)

    def test_wide_skipped_when_radius_lt2(self) -> None:
        ts = _ts(2024, 8, 1)
        utc_d = datetime.fromtimestamp(ts, tz=UTC).date()
        nh2, na2 = norm_club("P"), norm_club("Q")
        wd = utc_d + timedelta(days=2)
        key_hit = (wd.year, wd.month, wd.day, nh2, na2)
        ix = CsvRowIndex(key_to_rows={key_hit: [{"Date": str(wd), "HomeTeam": "P", "AwayTeam": "Q"}]})
        cat, ex = diagnose_fd_row_miss(
            ix, unix_ts=ts, nh="P", na="Q", diagnostic_radius_days=1
        )
        self.assertEqual(cat, "no_row_pm1")
        self.assertTrue(ex.get("diagnostic_wide_skipped"))

    def test_prod_finds_hit_when_other_day_ambiguous_then_single(self) -> None:
        nh2, na2 = norm_club("G"), norm_club("H")
        utc_d = datetime(2024, 7, 1, 18, tzinfo=UTC).date()
        dm1 = utc_d + timedelta(days=-1)
        k_amb = (utc_d.year, utc_d.month, utc_d.day, nh2, na2)
        k_ok = (dm1.year, dm1.month, dm1.day, nh2, na2)
        row_ok = {"Date": "2024-06-30", "home": "G", "visitor": "H"}
        ix = CsvRowIndex(
            key_to_rows={
                k_amb: [row_ok, row_ok],
                k_ok: [row_ok],
            }
        )
        ts = _ts(2024, 7, 1)
        self.assertIsNotNone(lookup_fd_row(ix, unix_ts=ts, nh="G", na="H"))


if __name__ == "__main__":
    unittest.main()
