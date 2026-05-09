import unittest

from football_ai.integration.flashscore_repair_feeds import (
    REPAIR_FEED_KINDS,
    parse_repair_feed_kinds,
)


class TestRepairFeedParsing(unittest.TestCase):
    def test_all_default(self):
        self.assertEqual(parse_repair_feed_kinds("all"), REPAIR_FEED_KINDS)

    def test_subset(self):
        self.assertEqual(parse_repair_feed_kinds("li"), frozenset({"li"}))
        self.assertEqual(parse_repair_feed_kinds("li,st"), frozenset({"li", "st"}))

    def test_unknown(self):
        with self.assertRaises(ValueError):
            parse_repair_feed_kinds("foo")


if __name__ == "__main__":
    unittest.main()
