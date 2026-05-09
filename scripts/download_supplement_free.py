"""
Download complementary FREE league CSVs from football-data.co.uk (Joseph Buchdahl datasets).

Coverage pulls domestic leagues in ``LEAG_KEY_TO_CLI`` plus optional MMZ overlays from
``data/integrated/football_data_manifest_mmz_overlay.json`` (map ``manifest league_key``
→ CSV stem under ``football-data.co.uk/mmz4281/{{season}}/``). Validate overlays before trusting joins.

Uses existing Storage/http politesse (reuse cache unless --force).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_ai.cli import FOOTBALL_DATA_LEAGUES
from football_ai.http import HttpClient
from football_ai.integration.join_football_data import load_manifest_mmz_overlay
from football_ai.paths import get_paths
from football_ai.sources.football_data import (
    FootballDataLeague,
    download_poland_consolidated_csv,
    download_results_csv,
)
from football_ai.storage import Storage

_SEASON_FOLDERS = ("2223", "2324", "2425", "2526")

# Keys into FOOTBALL_DATA_LEAGUES (premier league -> ENG1 …). Czech + Poland handled separately.
_LEAGUES_MMZ4281_KEYS = (
    "ENG1",
    "ESP1",
    "ITA1",
    "GER1",
    "FRA1",
    "NED1",
    "POR1",
    "BEL1",
    "TUR1",
    "GRE1",
    "CZE1",
)


def main() -> int:
    os.chdir(ROOT)
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Re-download even if URL already in raw DB")
    ap.add_argument(
        "--min-delay",
        type=float,
        default=1.25,
        help="Seconds between HTTP requests (politeness)",
    )
    args = ap.parse_args()

    paths = get_paths()
    overlay = load_manifest_mmz_overlay(paths.root)
    storage = Storage(db_path=paths.db_path, raw_dir=paths.raw_dir)
    http = HttpClient()
    http.min_delay_s = max(http.min_delay_s, args.min_delay)

    errs: list[str] = []

    print("Fetching Poland consolidated Ekstraklasa POL.csv...", flush=True)
    try:
        download_poland_consolidated_csv(storage=storage, http=http, force=args.force)
    except Exception as e:  # noqa: BLE001
        errs.append(f"POL.csv: {e}")

    league: FootballDataLeague
    for key in _LEAGUES_MMZ4281_KEYS:
        league = FOOTBALL_DATA_LEAGUES[key]
        for season in _SEASON_FOLDERS:
            try:
                print(f"Fetching {season} / {key} ({league.code})", flush=True)
                download_results_csv(
                    storage=storage,
                    http=http,
                    season=season,
                    league=league,
                    force=args.force,
                )
            except Exception as e:  # noqa: BLE001
                errs.append(f"{season}/{league.code}: {e}")

    seen_overlay_codes: set[str] = set()
    for mk, division_code in sorted(overlay.items()):
        if division_code in seen_overlay_codes:
            continue
        seen_overlay_codes.add(division_code)
        league_ov = FootballDataLeague(code=division_code, name=f"manifest_overlay:{division_code}")
        for season in _SEASON_FOLDERS:
            try:
                print(f"Fetching overlay {mk} → {season} / {division_code}", flush=True)
                download_results_csv(
                    storage=storage,
                    http=http,
                    season=season,
                    league=league_ov,
                    force=args.force,
                )
            except Exception as e:  # noqa: BLE001
                errs.append(f"overlay-{mk}/{season}/{division_code}: {e}")

    if errs:
        print("\nFailures (some seasons may legitimately not be published yet):", flush=True)
        for ln in errs:
            print(f" - {ln}", flush=True)
        return 2
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
