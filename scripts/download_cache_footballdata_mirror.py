"""
Download selective CSV mirrors from github.com/footballcsv/cache.footballdata
into ``data/raw/footballcsv/cache-footballdata/{{YYYY-YY}}/``.

These files use English ``Date`` + ``Team 1`` / ``Team 2`` (not Buchdahl HomeTeam/AwayTeam).
Used when ``scripts/build_integration_supplement.py --footballcsv-cache-fallback`` lacks MMZ files.

Chance Liga (football-data C1) has no analogue in cache.footballdata — skipped.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_ai.cli import FOOTBALL_DATA_LEAGUES
from football_ai.http import HttpClient
from football_ai.integration.join_football_data import (
    MMZ_DIVISION_CODE_TO_CACHE_MIRROR_STEM,
    cache_footballdata_repo_root,
    load_manifest_mmz_overlay,
    season_four_to_cache_footballdata_slug,
)
from football_ai.paths import get_paths

_RAW_GH = (
    "https://raw.githubusercontent.com/footballcsv/cache.footballdata/master/"
)

_SEASONS = ("2223", "2324", "2425", "2526")


def _stems_from_mmz_codes(codes: set[str]) -> set[str]:
    out: set[str] = set()
    for code in codes:
        stem = MMZ_DIVISION_CODE_TO_CACHE_MIRROR_STEM.get(code.strip())
        if stem:
            out.add(stem)
    return out


def main() -> int:
    os.chdir(ROOT)
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Re-download existing files")
    ap.add_argument(
        "--min-delay",
        type=float,
        default=1.25,
        help="Seconds between HTTP GETs",
    )
    args = ap.parse_args()

    paths = get_paths()
    overlay = load_manifest_mmz_overlay(paths.root)
    mmz_codes = {FOOTBALL_DATA_LEAGUES[k].code for k in FOOTBALL_DATA_LEAGUES}

    overlay_codes_norm = {
        str(c).strip() for c in overlay.values() if isinstance(c, str) and str(c).strip()
    }

    stems = sorted(_stems_from_mmz_codes(mmz_codes | overlay_codes_norm))

    if not stems:
        print("No mirror stems resolved (nothing to download).", flush=True)
        return 0

    http = HttpClient()
    http.min_delay_s = max(http.min_delay_s, args.min_delay)
    repo_root_on_disk = cache_footballdata_repo_root(paths.raw_dir)
    errs: list[str] = []

    for season4 in _SEASONS:
        slug = season_four_to_cache_footballdata_slug(season4)
        out_dir = repo_root_on_disk / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        for stem in stems:
            name = f"{stem}.csv"
            dest = out_dir / name
            if dest.exists() and not args.force and dest.stat().st_size > 0:
                continue
            url = f"{_RAW_GH}{slug}/{name}"
            try:
                code, blob, url_final = http.get(url)
                if code != 200:
                    errs.append(f"{slug}/{name}: HTTP {code}")
                    continue
                dest.write_bytes(blob)
                print(f"OK {dest.relative_to(paths.root)} ({len(blob)} B) <- {url_final}", flush=True)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{slug}/{name}: {e}")

    if errs:
        print("\nFailures:", flush=True)
        for ln in errs:
            print(f" - {ln}", flush=True)
        return 2
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
