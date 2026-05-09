"""Parse champions-league/openfootball style plain-text match lists."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_MONTH = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

FULL_DATE_LINE = re.compile(r"^\s+[A-Za-z]{2,3}\s+([A-Za-z]{3})/(\d{1,2})\s+(\d{4})\s*$")

SHORT_DATE_LINE = re.compile(r"^\s+[A-Za-z]{2,3}\s+([A-Za-z]{3})/(\d{1,2})\s*$")

MATCH_LINE = re.compile(
    r"^\s*(\d{2}\.\d{2})\s+(.+)\s+v\s+(.+?)\s+(\d+-\d+)\s*(?:\((\d+-\d+)\))?\s*$"
)


@dataclass(frozen=True)
class OpenFootballParsedMatch:
    d: date
    kick_clock: str
    home_short: str
    away_short: str
    score_ft: str
    score_ht: str | None


def _stripped_country(name: str) -> str:
    from football_ai.integration.normalize import strip_openfoot_country_suffix

    return strip_openfoot_country_suffix(name.strip())


def iter_openfootball_matches(text: str):
    lines = text.splitlines()
    last_year: int | None = None
    last_dom: tuple[int, int, int] | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m_full = FULL_DATE_LINE.match(line)
        if m_full:
            mon_s, dd, yyyy = m_full.group(1), int(m_full.group(2)), int(m_full.group(3))
            last_year = yyyy
            mon = _MONTH[mon_s]
            last_dom = (yyyy, mon, dd)
            i += 1
            continue
        m_short = SHORT_DATE_LINE.match(line)
        if m_short and last_year is not None:
            mon_s, dd = m_short.group(1), int(m_short.group(2))
            mon = _MONTH[mon_s]
            last_dom = (last_year, mon, dd)
            i += 1
            continue
        mo = MATCH_LINE.match(line.strip())
        if mo and last_dom is not None:
            clock, ht, away, fts, ht_score = mo.group(1), mo.group(2), mo.group(3), mo.group(4), mo.group(5)
            d = date(*last_dom)
            yield OpenFootballParsedMatch(
                d=d,
                kick_clock=clock,
                home_short=_stripped_country(ht),
                away_short=_stripped_country(away),
                score_ft=fts,
                score_ht=ht_score,
            )
            i += 1
            continue
        mo_hash = line.strip().startswith("# Date ")
        if mo_hash:
            rx = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", line)
            if rx:
                y, mn, dd = map(int, rx.groups())
                last_dom = (y, mn, dd)
                last_year = y
        i += 1
