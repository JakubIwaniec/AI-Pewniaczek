import unittest

from football_ai.integration.match_identity import (
    compute_fixture_uid,
    compute_match_uid,
    utc_date_iso_from_unix,
)


class TestMatchIdentity(unittest.TestCase):
    def test_utc_day(self):
        self.assertEqual(utc_date_iso_from_unix(1704067200), "2024-01-01")

    def test_match_uid_stable(self):
        u = compute_match_uid(
            dataset_label="premier_league-2526",
            unix_kickoff=1704067200,
            home_name="Arsenal FC",
            away_name="chelsea ",
        )
        v = compute_match_uid(
            dataset_label="premier_league-2526",
            unix_kickoff=1704067200,
            home_name="arsenal fc",
            away_name="Chelsea",
        )
        self.assertEqual(u, v)
        self.assertEqual(len(u or ""), 64)

    def test_different_buckets(self):
        a = compute_match_uid(
            dataset_label="premier_league-2526",
            unix_kickoff=1704067200,
            home_name="A",
            away_name="B",
        )
        b = compute_match_uid(
            dataset_label="laliga-2526",
            unix_kickoff=1704067200,
            home_name="A",
            away_name="B",
        )
        self.assertNotEqual(a, b)

    def test_fixture_uid_same_without_dataset_bucket(self):
        a = compute_fixture_uid(
            unix_kickoff=1704067200,
            home_name="A FC",
            away_name="B ",
        )
        b = compute_fixture_uid(
            unix_kickoff=1704067200,
            home_name="  a fc ",
            away_name="b",
        )
        self.assertEqual(a, b)

    def test_fixture_uid_differs_from_match_uid_with_dataset(self):
        f = compute_fixture_uid(
            unix_kickoff=1704067200,
            home_name="A",
            away_name="B",
        )
        m1 = compute_match_uid(
            dataset_label="premier_league-2526",
            unix_kickoff=1704067200,
            home_name="A",
            away_name="B",
        )
        m2 = compute_match_uid(
            dataset_label="bundesliga-2526",
            unix_kickoff=1704067200,
            home_name="A",
            away_name="B",
        )
        self.assertEqual(f, compute_fixture_uid(unix_kickoff=1704067200, home_name="A", away_name="B"))
        self.assertNotEqual(m1, m2)
        self.assertNotEqual(f, m1)
        self.assertNotEqual(f, m2)
if __name__ == "__main__":
    unittest.main()
