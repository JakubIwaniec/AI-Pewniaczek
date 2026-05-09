"""Tests for OpenFootball join helpers (unordered pair + day, UEFA aliases, clock tie-break)."""
from __future__ import annotations

import datetime as dt
from datetime import date

from football_ai.integration.join_openfootball import (
    diagnose_openfoot_miss,
    index_openfoot_matches,
    lookup_openfoot,
)
from football_ai.integration.openfootball_parse import OpenFootballParsedMatch


def test_lookup_unordered_pair_matches_of_home_away_order() -> None:
    """OF row Athletic (home) v Arsenal — FS meta may list teams in either order."""
    m = OpenFootballParsedMatch(
        d=date(2025, 9, 17),
        kick_clock="18.45",
        home_short="Athletic Club",
        away_short="Arsenal FC",
        score_ft="0-2",
        score_ht="0-0",
    )
    ix = index_openfoot_matches([m])
    u = int(dt.datetime(2025, 9, 17, 12, 0, tzinfo=dt.timezone.utc).timestamp())
    hit = lookup_openfoot(ix=ix, unix_ts=u, nh="Arsenal FC", na="Athletic Club")
    assert hit is not None
    assert hit.home_short == "Athletic Club"


def test_unicode_bayern_monachium_alias_matches_munchen() -> None:
    m = OpenFootballParsedMatch(
        d=date(2025, 9, 17),
        kick_clock="21.00",
        home_short="FC Bayern München",
        away_short="Chelsea FC",
        score_ft="3-1",
        score_ht="2-1",
    )
    ix = index_openfoot_matches([m])
    u = int(dt.datetime(2025, 9, 17, 20, 0, tzinfo=dt.timezone.utc).timestamp())
    hit = lookup_openfoot(ix=ix, unix_ts=u, nh="Bayern Monachium", na="Chelsea")
    assert hit is not None


def test_clock_disambiguation_when_two_same_day_buckets() -> None:
    """Rare duplicate keys; clock hint picks exactly one row."""
    d = date(2025, 9, 30)
    a = OpenFootballParsedMatch(
        d=d, kick_clock="18.45", home_short="FC A", away_short="FC B", score_ft="1-0", score_ht=None
    )
    b = OpenFootballParsedMatch(
        d=d, kick_clock="21.00", home_short="FC A", away_short="FC B", score_ft="2-2", score_ht=None
    )
    ix = index_openfoot_matches([a, b])
    u = int(dt.datetime(2025, 9, 30, 18, 0, tzinfo=dt.timezone.utc).timestamp())
    hit = lookup_openfoot(
        ix=ix,
        unix_ts=u,
        nh="FC A",
        na="FC B",
        kick_clock_hint="18.45",
    )
    assert hit == a


def test_identical_normalized_teams_yield_no_lookup() -> None:
    ix = index_openfoot_matches([])
    u = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    assert lookup_openfoot(ix=ix, unix_ts=u, nh="Foo", na="Foo") is None


def test_diagnose_miss_missing() -> None:
    ix = index_openfoot_matches([])
    u = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    cat = diagnose_openfoot_miss(ix=ix, unix_ts=u, nh="X", na="Y")
    assert cat == "missing_openfoot_match"
