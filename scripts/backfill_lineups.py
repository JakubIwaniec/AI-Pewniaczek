"""Backfill df_li (lineup) feeds for all leagues and seasons."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LEAGUES = {
    "ekstraklasa": "polska/ekstraklasa",
    "chance_liga": "czechy/chance-liga",
    "liga_portugal": "portugalia/liga-portugal",
    "laliga": "hiszpania/laliga",
    "serie_a": "wlochy/serie-a",
    "premier_league": "anglia/premier-league",
    "bundesliga": "niemcy/bundesliga",
    "ligue_1": "francja/ligue-1",
    "eredivisie": "holandia/eredivisie",
    "jupiler_league": "belgia/jupiler-league",
    "super_league": "grecja/super-league",
    "super_lig": "turcja/super-lig",
}

SEASONS = ["2223", "2324", "2425", "2526"]


def main() -> None:
    event_ids_dir = Path("data/event_ids")
    total = 0
    for league_key, subdir_base in LEAGUES.items():
        for season in SEASONS:
            ids_file = event_ids_dir / f"{league_key}_{season}.txt"
            if not ids_file.exists():
                print(f"SKIP (no file): {ids_file}")
                continue
            out_subdir = f"{subdir_base}/{season}/matches"
            n = sum(1 for line in ids_file.read_text(encoding="utf-8").splitlines() if line.strip())
            total += n
            print(f"\n{'='*60}")
            print(f"{league_key} {season}: {n} events -> {out_subdir}")
            print(f"{'='*60}")
            subprocess.run(
                [
                    sys.executable, "-m", "football_ai",
                    "backfill-flashscore-lineups",
                    "--event-ids-file", str(ids_file),
                    "--out-subdir", out_subdir,
                ],
                check=True,
            )
    print(f"\nAll done. Total events processed: {total}")


if __name__ == "__main__":
    main()
