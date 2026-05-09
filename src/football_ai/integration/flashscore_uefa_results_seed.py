"""Flashscore UEFA ``/wyniki/`` page URLs — HTML embeds mega-list rows (`~AA÷`) usable as AA-meta."""
from __future__ import annotations

FLASHSCORE_PL_BASE = "https://www.flashscore.pl"

# Keys align with ``scripts/data_integrity_flashscore.league_manifest`` UEFA tuples.
_FS_SLUG: dict[str, str] = {
    "liga_mistrzow": "liga-mistrzow",
    "liga_europy": "liga-europejska",
    # Flashscore.pl uses this spelling in URLs (historical typo in site paths).
    "liga_konferencji": "liga-konfetrencji",
}


def season_folder4_to_url_segment(season4: str) -> str:
    """``2526`` → ``2025-2026`` (Flashscore UEFA seasonal URL segment)."""
    if len(season4) != 4 or not season4.isdigit():
        raise ValueError(f"expected 4-digit season folder, got {season4!r}")
    y1 = 2000 + int(season4[:2])
    y2_full = 2000 + int(season4[2:])
    return f"{y1}-{y2_full}"


def pol_wyniki_results_url(league_key: str, season4: str) -> str:
    """Full ``…/wyniki/`` URL for a UEFA competition season on Flashscore Poland."""
    slug = _FS_SLUG.get(league_key)
    if slug is None:
        raise KeyError(league_key)
    seg = season_folder4_to_url_segment(season4)
    return f"{FLASHSCORE_PL_BASE}/pilka-nozna/europa/{slug}-{seg}/wyniki/"
