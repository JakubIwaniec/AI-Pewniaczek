"""Index openfootball plaintext matches by calendar date + norm club names."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from football_ai.integration.normalize import norm_club
from football_ai.integration.openfootball_parse import OpenFootballParsedMatch
from football_ai.integration.uefa_openfoot_aliases import norm_club_uefa_flashscore_vs_openfoot

OpenfootMissCategory = str

_ORDERED_KEY = tuple[int, int, int, str, str]
_PAIR_KEY = tuple[int, int, int, frozenset[str]]

_CLOCK_PAIR = re.compile(r"\b(\d{1,2})[.:](\d{2})\b")


@dataclass(frozen=True)
class OpenfootLookupIndex:
    """OpenFootball rows keyed by ordered home/away norms and by unordered pair (same day)."""

    by_ordered: dict[_ORDERED_KEY, list[OpenFootballParsedMatch]]
    by_pair: dict[_PAIR_KEY, list[OpenFootballParsedMatch]]


def index_openfoot_matches(
    records: list[OpenFootballParsedMatch],
) -> OpenfootLookupIndex:
    """Build ordered and pair-of-teams indexes for the same calendar day (OF local date)."""
    by_o: dict[_ORDERED_KEY, list[OpenFootballParsedMatch]] = defaultdict(list)
    by_p: dict[_PAIR_KEY, list[OpenFootballParsedMatch]] = defaultdict(list)
    for r in records:
        h, a = norm_club(r.home_short), norm_club(r.away_short)
        y, m, d = r.d.year, r.d.month, r.d.day
        by_o[(y, m, d, h, a)].append(r)
        by_p[(y, m, d, frozenset((h, a)))].append(r)
    return OpenfootLookupIndex(by_ordered=dict(by_o), by_pair=dict(by_p))


def _norm_clock(s: str | None) -> str:
    if not s:
        return ""
    m = _CLOCK_PAIR.search(s.strip())
    if not m:
        return ""
    return f"{int(m.group(1)):02d}.{m.group(2)}"


def _disambiguate_by_clock(
    hits: list[OpenFootballParsedMatch],
    kick_clock_hint: str | None,
) -> OpenFootballParsedMatch | None:
    if len(hits) <= 1 or not kick_clock_hint:
        return None
    want = _norm_clock(kick_clock_hint)
    if len(want) < 4:
        return None
    filt = [h for h in hits if _norm_clock(h.kick_clock) == want]
    if len(filt) == 1:
        return filt[0]
    return None


def _resolve_bucket(
    hits: list[OpenFootballParsedMatch] | None,
    *,
    kick_clock_hint: str | None,
) -> OpenFootballParsedMatch | None:
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    return _disambiguate_by_clock(hits, kick_clock_hint)


def lookup_openfoot(
    *,
    ix: OpenfootLookupIndex,
    unix_ts: int | None,
    nh: str,
    na: str,
    kick_clock_hint: str | None = None,
) -> OpenFootballParsedMatch | None:
    """Match AA-meta to plaintext: ±1 UTC calendar day + unordered team pair (+ optional kick clock)."""
    if unix_ts is None:
        return None
    nh2, na2 = norm_club_uefa_flashscore_vs_openfoot(nh), norm_club_uefa_flashscore_vs_openfoot(na)
    pair_k = frozenset((nh2, na2))
    if len(pair_k) != 2:
        return None
    utc_d = datetime.fromtimestamp(unix_ts, tz=UTC).date()
    for delta in (0, -1, 1):
        cal = utc_d + timedelta(days=delta)
        y, mn, dd = cal.year, cal.month, cal.day
        bucket = ix.by_pair.get((y, mn, dd, pair_k))
        hit = _resolve_bucket(bucket, kick_clock_hint=kick_clock_hint)
        if hit is not None:
            return hit
    return None


def diagnose_openfoot_miss(
    *,
    ix: OpenfootLookupIndex,
    unix_ts: int | None,
    nh: str,
    na: str,
    kick_clock_hint: str | None = None,
) -> OpenfootMissCategory:
    """Rough bucket after :func:`lookup_openfoot` returned ``None`` (telemetry / reports)."""
    if unix_ts is None:
        return "no_unix_kickoff"

    if (
        lookup_openfoot(
            ix=ix,
            unix_ts=unix_ts,
            nh=nh,
            na=na,
            kick_clock_hint=kick_clock_hint,
        )
        is not None
    ):
        return "would_match_diag_bug"

    nh2, na2 = norm_club_uefa_flashscore_vs_openfoot(nh), norm_club_uefa_flashscore_vs_openfoot(na)
    pair_k = frozenset((nh2, na2))
    if len(pair_k) != 2:
        return "missing_openfoot_match"

    utc_d = datetime.fromtimestamp(unix_ts, tz=UTC).date()
    ambiguous = False
    any_hit = False
    for delta in (0, -1, 1):
        cal = utc_d + timedelta(days=delta)
        y, mn, dd = cal.year, cal.month, cal.day
        hits = ix.by_pair.get((y, mn, dd, pair_k))
        if not hits:
            continue
        any_hit = True
        if len(hits) > 1:
            ambiguous = True
    if not any_hit:
        return "missing_openfoot_match"
    if ambiguous:
        return "ambiguous_openfoot_rows"
    return "lookup_inconsistency"
