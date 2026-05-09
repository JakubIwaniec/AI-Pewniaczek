from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from football_ai.integration.join_football_data import (
    MMZ_DIVISION_CODE_TO_CACHE_MIRROR_STEM,
    footballcsv_cache_footballdata_index,
    parse_footballcsv_cache_eng_date,
    season_four_to_cache_footballdata_slug,
)
from football_ai.integration.normalize import norm_club


class TestCacheFootballdataMirror(unittest.TestCase):
    def test_season_four_to_cache_slug(self) -> None:
        self.assertEqual(season_four_to_cache_footballdata_slug("2223"), "2022-23")
        self.assertEqual(season_four_to_cache_footballdata_slug("2526"), "2025-26")

    def test_parse_cache_eng_date(self) -> None:
        self.assertEqual(parse_footballcsv_cache_eng_date("Fri Aug 5 2022"), (2022, 8, 5))

    def test_footballcsv_cache_index_fixture(self) -> None:
        body = (
            "Date,Team 1,FT,HT,Team 2\n"
            "Fri Aug 5 2022,Crystal Palace,0-2,0-1,Arsenal\n"
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
            ix = footballcsv_cache_footballdata_index(path)
            h = norm_club("Crystal Palace")
            a = norm_club("Arsenal")
            key = (2022, 8, 5, h, a)
            self.assertIn(key, ix.key_to_rows)
            self.assertEqual(len(ix.key_to_rows[key]), 1)
        finally:
            path.unlink()

    def test_chance_liga_not_in_mirror_map(self) -> None:
        self.assertNotIn("C1", MMZ_DIVISION_CODE_TO_CACHE_MIRROR_STEM)


if __name__ == "__main__":
    unittest.main()
