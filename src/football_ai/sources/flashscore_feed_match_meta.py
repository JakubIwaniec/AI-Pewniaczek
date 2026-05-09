"""Extract structured match identifiers from Flashscore mega-list x/feed text."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class FlashscoreMatchMeta:
    """One ~AA÷ event row."""

    event_id: str
    unix_kickoff: int | None
    home_team: str
    away_team: str


_EID_TAIL = re.compile(r"^[A-Za-z0-9]{8}")


def _parse_fields(chunk_after_eid_div: str) -> dict[str, str]:
    out: dict[str, str] = {}
    # chunks end with '~' separators; omit empty trailing from split('¬').
    for piece in chunk_after_eid_div.split("¬"):
        if not piece or "÷" not in piece:
            continue
        k, _, v = piece.partition("÷")
        out[k] = v
    return out


def iter_match_meta_from_feed(feed_text: str) -> Iterator[FlashscoreMatchMeta]:
    """Yield FlashscoreMatchMeta for every '~AA÷' block."""
    parts = feed_text.split("~AA÷")
    for raw in parts[1:]:
        if not raw:
            continue
        head_sep = raw.find("¬")
        if head_sep == -1:
            eid_candidate = raw[:8]
            rest = raw[8:]
        else:
            eid_candidate = raw[:head_sep]
            rest = raw[head_sep + 1 :]
        if not _EID_TAIL.match(eid_candidate):
            continue
        fld = _parse_fields(rest)
        ae = fld.get("AE") or fld.get("CX")
        af = fld.get("AF")
        unix: int | None = None
        for key in ("AD", "ADE", "AO"):
            raw_u = fld.get(key)
            if not raw_u:
                continue
            digit = "".join(ch for ch in raw_u if ch.isdigit())
            try:
                u = int(digit)
                if u > 1_000_000_000:
                    unix = u
                    break
            except ValueError:
                continue
        if not ae or not af:
            continue
        yield FlashscoreMatchMeta(
            event_id=eid_candidate,
            unix_kickoff=unix,
            home_team=ae.strip(),
            away_team=af.strip(),
        )


def _richer_meta(a: FlashscoreMatchMeta, b: FlashscoreMatchMeta) -> FlashscoreMatchMeta:
    """Prefer non-null unix; on tie keep *a* (stable). Avoid preferring longest names (breaks CSV match)."""

    def has_u(u: int | None) -> bool:
        return u is not None and u > 0

    au, bu = a.unix_kickoff, b.unix_kickoff
    if has_u(au) and not has_u(bu):
        return a
    if has_u(bu) and not has_u(au):
        return b
    if has_u(au) and has_u(bu) and au != bu:
        return a if au >= bu else b
    return a


def build_event_meta_index(feed_paths: list[Path]) -> dict[str, FlashscoreMatchMeta]:
    """Later paths override duplicates."""
    ix: dict[str, FlashscoreMatchMeta] = {}
    for fp in feed_paths:
        txt = fp.read_text(encoding="utf-8", errors="ignore")
        for m in iter_match_meta_from_feed(txt):
            ix[m.event_id] = m
    return ix


def build_event_meta_union(feed_paths: list[Path]) -> dict[str, FlashscoreMatchMeta]:
    """Union ``~AA÷`` rows from many feeds; on collision keep the richer row (unix kickoff > name length)."""
    ix: dict[str, FlashscoreMatchMeta] = {}
    for fp in feed_paths:
        txt = fp.read_text(encoding="utf-8", errors="ignore")
        for m in iter_match_meta_from_feed(txt):
            if m.event_id not in ix:
                ix[m.event_id] = m
            else:
                ix[m.event_id] = _richer_meta(ix[m.event_id], m)
    return ix


def augment_meta_index_from_seed_html(
    ix: dict[str, FlashscoreMatchMeta],
    seed_html_paths: list[Path],
) -> int:
    """Fill missing Flashscore event ids using cached league HTML (embedded ``~AA÷`` blocks).

    Typical locations: ``data/raw/flashscore/**/seed/*.html`` and
    ``data/raw/flashscore/seed_results/*_wyniki.html`` (UEFA /wyniki/ saves).
    Prefer mega-feed entries when present; this only supplies gaps."""
    added = 0
    for hp in seed_html_paths:
        try:
            txt = hp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in iter_match_meta_from_feed(txt):
            if m.event_id not in ix:
                ix[m.event_id] = m
                added += 1
    return added
