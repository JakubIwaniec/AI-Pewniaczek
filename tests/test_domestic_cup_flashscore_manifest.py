"""domestic_cup_flashscore cup rows align with data_integrity_flashscore.league_manifest."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "data" / "raw" / "flashscore"
_SCR = ROOT / "scripts"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(_SCR))

import data_integrity_flashscore as di  # noqa: E402

from football_ai.integration.domestic_cup_flashscore import (  # noqa: E402
    CUPS,
    FLASHSCORE_CUP_SEASON_FOLDERS,
    domestic_cup_flashscore_manifest_rows,
)


def _split_dataset(ds: str) -> tuple[str, str]:
    i = ds.rfind("-")
    return ds[:i], ds[i + 1 :]


class TestDomesticCupManifest(unittest.TestCase):
    def test_generator_matches_league_manifest_cup_slice(self):
        gen = {
            (a, b, c.resolve())
            for a, b, c in domestic_cup_flashscore_manifest_rows(raw_flashscore_root=FLASH)
        }
        ml_cups = {
            (a, b, c.resolve())
            for a, b, c in di.league_manifest()
            if _split_dataset(a)[0] in CUPS
        }
        self.assertEqual(gen, ml_cups)

    def test_season_tokens(self):
        for dlabel, _ids, _base in domestic_cup_flashscore_manifest_rows(raw_flashscore_root=FLASH):
            _lk, seas = _split_dataset(dlabel)
            self.assertIn(seas, FLASHSCORE_CUP_SEASON_FOLDERS)


if __name__ == "__main__":
    unittest.main()
