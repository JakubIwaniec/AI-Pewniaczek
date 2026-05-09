"""Harvest all domestic cups from Flashscore for 4 seasons.

Flashscore slugs vary by country — config lives in football_ai.integration.domestic_cup_flashscore.
Run with stdio line-buffered, e.g.:
  python -u scripts/harvest_cups.py

Also writes AA seed HTML to data/raw/flashscore/seed_results/{cup}_{season}_wyniki.html
for build_integration_supplement. When event IDs already exist (SKIP full harvest),
missing *_wyniki.html is backfilled via collect-flashscore-match-ids only.

Exit code 1 if any cup-season failed after all attempts.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_ai.integration.domestic_cup_flashscore import (  # noqa: E402
    CUPS,
    FLASHSCORE_CUP_SEASON_TO_LONG_LABEL,
    results_page_url,
)

# Backward-compatible alias for scripts / muscle memory
SEASON_MAP = FLASHSCORE_CUP_SEASON_TO_LONG_LABEL


def _count_nonempty_ids(ids_file: Path) -> int:
    if not ids_file.exists():
        return 0
    return sum(
        1 for line in ids_file.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def main() -> int:
    event_ids_dir = ROOT / "data/event_ids"
    event_ids_dir.mkdir(parents=True, exist_ok=True)
    seed_results_dir = ROOT / "data/raw/flashscore/seed_results"
    seed_results_dir.mkdir(parents=True, exist_ok=True)

    done = 0
    failed: list[str] = []

    for cup_key, cup_info in CUPS.items():
        for season_short, _long in SEASON_MAP.items():
            ids_file = event_ids_dir / f"{cup_key}_{season_short}.txt"
            slug = cup_info["slug"]
            url = results_page_url(slug=slug, season_folder4=season_short)
            out_subdir = f"{cup_info['out_base']}/{season_short}/matches"
            wyniki_path = seed_results_dir / f"{cup_key}_{season_short}_wyniki.html"
            n_ids = _count_nonempty_ids(ids_file)

            if n_ids > 0 and not wyniki_path.exists():
                print(f"\n{'='*60}")
                print(f"BACKFILL wyniki HTML (have {n_ids} IDs): {cup_key} {season_short}")
                print(f"URL: {url}")
                print(f"Out: {wyniki_path.relative_to(ROOT)}")
                print(f"{'='*60}")
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "football_ai",
                        "collect-flashscore-match-ids",
                        "--url",
                        url,
                        "--wyniki-html-out",
                        str(wyniki_path),
                        "--storage-state",
                        str(ROOT / "data/flashscore_storage_state.json"),
                        "--profile-dir",
                        str(ROOT / "data/flashscore_profile"),
                    ],
                    cwd=str(ROOT),
                    capture_output=False,
                )
                if result.returncode != 0:
                    print(f"  FAILED (exit={result.returncode}): {cup_key} {season_short} wyniki HTML")
                    failed.append(f"{cup_key}_{season_short}_wyniki")
                else:
                    print(f"  OK: wrote {wyniki_path.relative_to(ROOT)}")
                    done += 1
                continue

            if n_ids > 0:
                print(f"SKIP (already have {n_ids} IDs + wyniki HTML): {cup_key} {season_short}")
                done += 1
                continue

            print(f"\n{'='*60}")
            print(f"Harvesting: {cup_key} {season_short}")
            print(f"URL: {url}")
            print(f"Out: {out_subdir}")
            print(f"{'='*60}")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "football_ai",
                    "harvest-flashscore-season",
                    "--results-url",
                    url,
                    "--out-subdir",
                    out_subdir,
                    "--event-ids-out",
                    str(ids_file),
                    "--wyniki-html-out",
                    str(wyniki_path),
                    "--storage-state",
                    str(ROOT / "data/flashscore_storage_state.json"),
                    "--profile-dir",
                    str(ROOT / "data/flashscore_profile"),
                ],
                cwd=str(ROOT),
                capture_output=False,
            )

            if result.returncode != 0:
                print(f"  FAILED (exit={result.returncode}): {cup_key} {season_short}")
                failed.append(f"{cup_key}_{season_short}")
            else:
                n = _count_nonempty_ids(ids_file)
                print(f"  OK: {n} events for {cup_key} {season_short}")
                done += 1

    print(f"\n{'='*60}")
    print(f"DONE: {done} cup-seasons completed")
    if failed:
        print(f"FAILED ({len(failed)}): {', '.join(failed)}")
        return 1
    print("No failures!")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
