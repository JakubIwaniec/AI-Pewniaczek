"""Tests for jalapic engsoccerdata cup CSV indexing and Flashscore join lookup."""
from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from football_ai.integration.join_football_data import (
    engsoccerdata_cup_index,
    lookup_fd_row,
    season_four_to_engsoccer_start_year,
)


class TestEngsoccerdataJoin(unittest.TestCase):
    def test_season_four_to_engsoccer_start_year(self) -> None:
        self.assertEqual(season_four_to_engsoccer_start_year("2324"), 2023)
        self.assertEqual(season_four_to_engsoccer_start_year("2223"), 2022)
        with self.assertRaises(ValueError):
            season_four_to_engsoccer_start_year("232")
        with self.assertRaises(ValueError):
            season_four_to_engsoccer_start_year("abcd")

    def test_index_filters_na_season_and_lookup(self) -> None:
        body = (
            "Date,Season,home,visitor,nonmatch\n"
            '2024-06-01,2023,"Alpha United","Beta City",NA\n'
            '2024-06-01,NA,"Gamma Rovers","Delta Town",NA\n'
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            delete=False,
            encoding="utf-8",
            newline="",
        ) as f:
            f.write(body)
            path = Path(f.name)
        try:
            ix = engsoccerdata_cup_index(path, season_start_year=2023, cup="facup")
            ts = int(datetime(2024, 6, 1, 14, 0, tzinfo=UTC).timestamp())
            row = lookup_fd_row(ix, unix_ts=ts, nh="Alpha United", na="Beta City")
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row.get("home"), "Alpha United")
            self.assertEqual(row.get("visitor"), "Beta City")
            miss = lookup_fd_row(ix, unix_ts=ts, nh="Gamma Rovers", na="Delta Town")
            self.assertIsNone(miss)
        finally:
            path.unlink(missing_ok=True)

    def test_ambiguous_duplicate_key_returns_none(self) -> None:
        body = (
            "Date,Season,home,visitor\n"
            '2024-06-02,2023,"X FC","Y FC"\n'
            '2024-06-02,2023,"X FC","Y FC"\n'
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            delete=False,
            encoding="utf-8",
            newline="",
        ) as f:
            f.write(body)
            path = Path(f.name)
        try:
            ix = engsoccerdata_cup_index(path, season_start_year=2023, cup="facup")
            ts = int(datetime(2024, 6, 2, 12, 0, tzinfo=UTC).timestamp())
            self.assertIsNone(lookup_fd_row(ix, unix_ts=ts, nh="X FC", na="Y FC"))
        finally:
            path.unlink(missing_ok=True)

    def test_index_accepts_slash_and_hyphen_season_labels(self) -> None:
        body = (
            "Date,Season,home,visitor,nonmatch\n"
            '2024-06-10,2022/23,"Slash Home","Slash Away",NA\n'
            '2024-06-11,2023-24,"Hyphen Four","Hyphen Away",NA\n'
            '2024-06-12,23-24,"Yy Home","Yy Away",NA\n'
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            delete=False,
            encoding="utf-8",
            newline="",
        ) as f:
            f.write(body)
            path = Path(f.name)
        try:
            ix22 = engsoccerdata_cup_index(path, season_start_year=2022, cup="facup")
            ts10 = int(datetime(2024, 6, 10, 12, 0, tzinfo=UTC).timestamp())
            self.assertIsNotNone(lookup_fd_row(ix22, unix_ts=ts10, nh="Slash Home", na="Slash Away"))

            ix23 = engsoccerdata_cup_index(path, season_start_year=2023, cup="facup")
            ts11 = int(datetime(2024, 6, 11, 12, 0, tzinfo=UTC).timestamp())
            ts12 = int(datetime(2024, 6, 12, 12, 0, tzinfo=UTC).timestamp())
            self.assertIsNotNone(lookup_fd_row(ix23, unix_ts=ts11, nh="Hyphen Four", na="Hyphen Away"))
            self.assertIsNotNone(lookup_fd_row(ix23, unix_ts=ts12, nh="Yy Home", na="Yy Away"))
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
