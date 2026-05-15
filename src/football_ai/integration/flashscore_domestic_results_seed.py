"""Flashscore.pl ``/wyniki/`` URLs for domestic leagues — HTML embeds ``~AA÷`` rows for meta augmentation."""
from __future__ import annotations

from football_ai.integration.flashscore_uefa_results_seed import (
    FLASHSCORE_PL_BASE,
    season_folder4_to_url_segment,
)

# Keys align with ``scripts/data_integrity_flashscore.league_manifest`` domestic tuples.
_FS_SLUG: dict[str, str] = {
    "ekstraklasa": "ekstraklasa",
    "chance_liga": "chance-liga",
    "liga_portugal": "liga-portugal",
    "laliga": "laliga",
    "serie_a": "serie-a",
    "premier_league": "premier-league",
    "bundesliga": "bundesliga",
    "ligue_1": "ligue-1",
    "eredivisie": "eredivisie",
    "jupiler_league": "jupiler-league",
    "super_league": "super-league",
    "super_lig": "super-lig",
}

# league_key -> country path segment on flashscore.pl
_COUNTRY: dict[str, str] = {
    "ekstraklasa": "polska",
    "chance_liga": "czechy",
    "liga_portugal": "portugalia",
    "laliga": "hiszpania",
    "serie_a": "wlochy",
    "premier_league": "anglia",
    "bundesliga": "niemcy",
    "ligue_1": "francja",
    "eredivisie": "holandia",
    "jupiler_league": "belgia",
    "super_league": "grecja",
    "super_lig": "turcja",
}

TIER1_KEYS = frozenset(_COUNTRY.keys())


def pol_wyniki_results_url(league_key: str, season4: str) -> str:
    """Full ``…/wyniki/`` URL for a domestic league season on Flashscore Poland."""
    slug = _FS_SLUG.get(league_key)
    country = _COUNTRY.get(league_key)
    if slug is None or country is None:
        raise KeyError(league_key)
    seg = season_folder4_to_url_segment(season4)
    return f"{FLASHSCORE_PL_BASE}/pilka-nozna/{country}/{slug}-{seg}/wyniki/"
