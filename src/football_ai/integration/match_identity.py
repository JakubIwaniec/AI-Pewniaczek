"""Stable cross-source match identity (date + home/away + competition bucket)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from football_ai.integration.normalize import norm_club


def utc_date_iso_from_unix(ts: int | None) -> str | None:
    if ts is None or ts < 1_000_000_000:
        return None
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return dt.date().isoformat()


def canonical_match_uid(
    *,
    competition_bucket: str,
    utc_date: str,
    home_norm: str,
    away_norm: str,
) -> str:
    rec = "|".join((competition_bucket, utc_date, home_norm, away_norm))
    return hashlib.sha256(rec.encode("utf-8")).hexdigest()


def compute_fixture_uid(
    *,
    unix_kickoff: int | None,
    home_name: str,
    away_name: str,
) -> str | None:
    """Cross-source id: UTC calendar date + normalized home/away (no dataset bucket). Same match across supplement sources."""
    d = utc_date_iso_from_unix(unix_kickoff)
    if not d:
        return None
    hn = norm_club(home_name)
    an = norm_club(away_name)
    if not hn or not an:
        return None
    rec = "|".join((d, hn, an))
    return hashlib.sha256(rec.encode("utf-8")).hexdigest()


def compute_match_uid(
    *,
    dataset_label: str,
    unix_kickoff: int | None,
    home_name: str,
    away_name: str,
) -> str | None:
    """Stable id for linking supplement rows across sources (`dataset`=league_manifest label)."""
    d = utc_date_iso_from_unix(unix_kickoff)
    if not d:
        return None
    hn = norm_club(home_name)
    an = norm_club(away_name)
    if not hn or not an:
        return None
    return canonical_match_uid(competition_bucket=dataset_label, utc_date=d, home_norm=hn, away_norm=an)
