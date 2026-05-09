import unittest
from pathlib import Path

from football_ai.sources.flashscore_feed_match_meta import iter_match_meta_from_feed


SAMPLE_ONE = "~ZZ÷pre¬~AA÷AbCdEf12¬AD÷1704067200¬AE÷Arsenal¬AF÷Chelsea¬AX÷1¬~ZA÷NEXT"


class TestFlashscoreFeedMatchMeta(unittest.TestCase):
    def test_extract_one_block(self):
        xs = list(iter_match_meta_from_feed(SAMPLE_ONE))
        self.assertEqual(len(xs), 1)
        m = xs[0]
        self.assertEqual(m.event_id, "AbCdEf12")
        self.assertEqual(m.unix_kickoff, 1704067200)
        self.assertEqual(m.home_team, "Arsenal")
        self.assertEqual(m.away_team, "Chelsea")

    def test_cx_fallback_for_home_when_ae_missing(self):
        txt = "~AA÷XyZwVuTs¬CX÷Hosts FC¬AF÷Guests FC¬AD÷1735689600¬"
        m = next(iter_match_meta_from_feed(txt))
        self.assertEqual(m.home_team, "Hosts FC")

    def test_seed_results_html_has_rich_aa_blocks(self):
        root = Path(__file__).resolve().parents[1]
        hp = root / "data/raw/flashscore/seed_results/liga_europy_2425_wyniki.html"
        if not hp.is_file():
            self.skipTest("seed HTML not present in workspace")
        txt = hp.read_text(encoding="utf-8", errors="ignore")
        xs = list(iter_match_meta_from_feed(txt))
        self.assertGreater(len(xs), 20)
        by_id = {m.event_id: m for m in xs}
        self.assertIn("CQQaJNbm", by_id)
        m = by_id["CQQaJNbm"]
        self.assertEqual(m.home_team, "Tottenham")
        self.assertEqual(m.away_team, "Manchester Utd")
        self.assertEqual(m.unix_kickoff, 1747854000)


if __name__ == "__main__":
    unittest.main()
