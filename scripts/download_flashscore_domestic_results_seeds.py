"""Download domestic league ``/wyniki/`` HTML into ``seed_results`` (embedded ``~AA÷`` for meta gaps).

Tier-1 pilot: mega-list ``f_1_-1_*`` often omits most IDS rows for a season; results pages
carry far more ``~AA÷`` blocks (see preflight overlap with ``data/event_ids/*.txt``).

Usage (repo root):
  python scripts/download_flashscore_domestic_results_seeds.py --league laliga --season 2526
  python scripts/download_flashscore_domestic_results_seeds.py --force
  python scripts/download_flashscore_domestic_results_seeds.py --all-tier1 --season 2526
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_ai.http import HttpClient  # noqa: E402
from football_ai.integration.flashscore_domestic_results_seed import (  # noqa: E402
    TIER1_KEYS,
    pol_wyniki_results_url,
)

OUT_DIR = ROOT / "data" / "raw" / "flashscore" / "seed_results"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download Flashscore.pl domestic /wyniki/ HTML seeds")
    p.add_argument("--force", action="store_true", help="Re-download even if file exists")
    p.add_argument("--season", default="2526", help="4-digit season folder, e.g. 2526")
    p.add_argument(
        "--league",
        action="append",
        default=[],
        help="Internal league key (repeatable), e.g. laliga, premier_league",
    )
    p.add_argument(
        "--all-tier1",
        action="store_true",
        help="All domestic Tier-1 keys in flashscore_domestic_results_seed",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.all_tier1:
        keys = sorted(TIER1_KEYS)
    elif args.league:
        keys = []
        for k in args.league:
            if k not in TIER1_KEYS:
                raise SystemExit(f"unknown league key {k!r}; known: {sorted(TIER1_KEYS)}")
            keys.append(k)
    else:
        raise SystemExit("pass --league KEY and/or --all-tier1")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = HttpClient(min_delay_s=1.25)
    fetched = reused = errors = 0
    for leigh in keys:
        url = pol_wyniki_results_url(leigh, args.season)
        outp = OUT_DIR / f"{leigh}_{args.season}_wyniki.html"
        if outp.exists() and outp.stat().st_size > 0 and not args.force:
            reused += 1
            print(f"[reuse] {outp.name}", flush=True)
            continue
        status, blob, final_url = client.get(url)
        txt = blob.decode("utf-8", errors="replace")
        if status != 200 or "~AA÷" not in txt:
            print(f"[skip] HTTP {status} or no AA: {final_url}", flush=True)
            errors += 1
            continue
        outp.write_text(txt, encoding="utf-8")
        fetched += 1
        print(f"saved {outp.name} ({len(txt)} chars)", flush=True)
    print(f"Done: fetched={fetched} reused={reused} errors={errors}", flush=True)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
