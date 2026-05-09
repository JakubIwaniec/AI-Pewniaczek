"""Single source for domestic cup URLs / RAW paths synced with Flashscore harvest.

Used by scripts/harvest_cups.py and data_integrity_flashscore.league_manifest cup rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

FLASHSCORE_CUP_SEASON_FOLDERS: Final[tuple[str, ...]] = ("2223", "2324", "2425", "2526")

FLASHSCORE_CUP_SEASON_TO_LONG_LABEL: Final[dict[str, str]] = {
    "2223": "2022-2023",
    "2324": "2023-2024",
    "2425": "2024-2025",
    "2526": "2025-2026",
}

CUPS: Final[dict[str, dict[str, str]]] = {
    "puchar_polski": {
        "slug": "polska/sts-puchar-polski",
        "out_base": "polska/puchar-polski",
    },
    "puchar_czech": {
        "slug": "czechy/mol-cup",
        "out_base": "czechy/mol-cup",
    },
    "taca_de_portugal": {
        "slug": "portugalia/taca-de-portugal",
        "out_base": "portugalia/taca-de-portugal",
    },
    "copa_del_rey": {
        "slug": "hiszpania/copa-del-rey",
        "out_base": "hiszpania/copa-del-rey",
    },
    "coppa_italia": {
        "slug": "wlochy/coppa-italia",
        "out_base": "wlochy/coppa-italia",
    },
    "fa_cup": {
        "slug": "anglia/fa-cup",
        "out_base": "anglia/fa-cup",
    },
    "carabao_cup": {
        "slug": "anglia/efl-cup",
        "out_base": "anglia/efl-cup",
    },
    "dfb_pokal": {
        "slug": "niemcy/dfb-pokal",
        "out_base": "niemcy/dfb-pokal",
    },
    "coupe_de_france": {
        "slug": "francja/coupe-de-france",
        "out_base": "francja/coupe-de-france",
    },
    "knvb_beker": {
        "slug": "holandia/knvb-beker",
        "out_base": "holandia/knvb-beker",
    },
    "puchar_belgii": {
        "slug": "belgia/puchar",
        "out_base": "belgia/puchar",
    },
    "puchar_grecji": {
        "slug": "grecja/puchar",
        "out_base": "grecja/puchar",
    },
    "puchar_turcji": {
        "slug": "turcja/puchar",
        "out_base": "turcja/puchar",
    },
}

_DOMESTIC_CUP_KEYS_FROZEN: Final[frozenset[str]] = frozenset(CUPS.keys())


def is_domestic_cup_league_key(league_key: str) -> bool:
    return league_key in _DOMESTIC_CUP_KEYS_FROZEN


def domestic_cup_flashscore_manifest_rows(
    *,
    raw_flashscore_root: Path,
) -> list[tuple[str, str, Path]]:
    """``(dataset_label, ids_name, matches_base_dir)`` for each domestic cup-season."""
    out: list[tuple[str, str, Path]] = []
    for cup_key, info in CUPS.items():
        rel = Path(info["out_base"])
        for sea in FLASHSCORE_CUP_SEASON_FOLDERS:
            matches = raw_flashscore_root / rel / sea / "matches"
            out.append((f"{cup_key}-{sea}", f"{cup_key}_{sea}", matches))
    return out


def results_page_url(*, slug: str, season_folder4: str) -> str:
    long_label = FLASHSCORE_CUP_SEASON_TO_LONG_LABEL[season_folder4]
    return f"https://www.flashscore.pl/pilka-nozna/{slug}-{long_label}/wyniki/"
