import json
import shutil
import tempfile
import unittest
from pathlib import Path

from football_ai.integration.flashscore_integration_feeds import ordered_feed_txt_paths
from football_ai.sources.flashscore_feed_match_meta import FlashscoreMatchMeta, build_event_meta_union


class TestFlashscoreIntegrationFeeds(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="fstest_"))

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_richer_meta_union_for_same_event(self) -> None:
        feeds = self._tmp / "data" / "raw" / "flashscore" / "feeds"
        inte = self._tmp / "data" / "integrated"
        feeds.mkdir(parents=True)
        inte.mkdir(parents=True)
        (feeds / "lowprio.txt").write_text(
            "~AA÷ColIdxxx¬AD÷1700000100¬AE÷First¬AF÷Guest1¬AX÷1¬~",
            encoding="utf-8",
        )
        (feeds / "highprio.txt").write_text(
            "~AA÷ColIdxxx¬AD÷1700000200¬AE÷Second¬AF÷Guest2¬AX÷1¬~",
            encoding="utf-8",
        )
        inte.joinpath("flashscore_list_feed_manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "wildcard_priority": 50,
                    "download": [
                        {
                            "feed_key": "__low__",
                            "filename": "lowprio.txt",
                            "priority": 10,
                            "tags": ["t"],
                        },
                        {
                            "feed_key": "__high__",
                            "filename": "highprio.txt",
                            "priority": 90,
                            "tags": ["t"],
                        },
                    ],
                    "include_feed_subdir_globs": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        paths, note = ordered_feed_txt_paths(
            repo_root=self._tmp,
            raw_flashscore_dir=self._tmp / "data" / "raw" / "flashscore",
        )
        self.assertEqual(len(paths), 2)
        ix = build_event_meta_union(paths)
        m = ix.get("ColIdxxx")
        self.assertIsInstance(m, FlashscoreMatchMeta)
        self.assertEqual(m.home_team, "Second")
        self.assertIn("manifest", note)


if __name__ == "__main__":
    unittest.main()
