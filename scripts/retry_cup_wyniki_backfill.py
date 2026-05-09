"""Retry Playwright snapshot of Flashscore /wyniki/ pages for domestic cups (AA meta seed HTML).

Does not re-download per-match df_* feeds. Exits with code 1 if any target remains missing
or invalid after all attempts.

Examples:
  python scripts/retry_cup_wyniki_backfill.py --only-missing --cup fa_cup --cup carabao_cup
  python scripts/retry_cup_wyniki_backfill.py --dry-run --only-missing
"""
from __future__ import annotations

import argparse
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from football_ai.integration.domestic_cup_flashscore import (  # noqa: E402
    CUPS,
    FLASHSCORE_CUP_SEASON_FOLDERS,
    results_page_url,
)
from football_ai.sources.flashscore_feed_match_meta import iter_match_meta_from_feed  # noqa: E402


def _parse_cup_args(values: list[str] | None) -> list[str]:
    if not values or (len(values) == 1 and values[0].lower() == "all"):
        return list(CUPS.keys())
    bad = [v for v in values if v not in CUPS]
    if bad:
        raise SystemExit(f"Unknown --cup key(s): {bad}. Known: {sorted(CUPS)}")
    return values


def _parse_season_args(values: list[str] | None) -> list[str]:
    if not values:
        return list(FLASHSCORE_CUP_SEASON_FOLDERS)
    allowed = set(FLASHSCORE_CUP_SEASON_FOLDERS)
    bad = [v for v in values if v not in allowed]
    if bad:
        raise SystemExit(f"Unknown --season: {bad}. Allowed: {sorted(allowed)}")
    return values


def _seed_acceptable(path: Path, *, min_bytes: int, require_rich_meta: bool) -> bool:
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    txt = path.read_text(encoding="utf-8", errors="ignore")
    if "~AA÷" not in txt:
        return False
    if not require_rich_meta:
        return True
    return any(iter_match_meta_from_feed(txt))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--cup",
        action="append",
        metavar="KEY",
        help="Repeatable. Cup key from domestic_cup_flashscore.CUPS, or omit with --cup all (default).",
    )
    p.add_argument(
        "--season",
        action="append",
        metavar="2223",
        help="Repeatable season folder token. Default: all four.",
    )
    p.add_argument("--attempts", type=int, default=2, help="Playwright attempts per job (default 2)")
    p.add_argument("--pause-seconds", type=float, default=8.0, help="Pause after each success (default 8)")
    p.add_argument(
        "--jitter-seconds",
        type=float,
        default=0.0,
        help="Extra random Uniform(0,N) pause before each attempt (default 0)",
    )
    p.add_argument(
        "--only-missing",
        action="store_true",
        help="Skip jobs whose seed HTML already passes validation",
    )
    p.add_argument(
        "--no-validate-rich-meta",
        action="store_true",
        help="Only require min-bytes and ~AA÷ substring (skip iter_match_meta_from_feed check)",
    )
    p.add_argument("--min-bytes", type=int, default=4096)
    p.add_argument("--headed", action="store_true", help="Forward --headed to collect-flashscore-match-ids")
    p.add_argument("--max-clicks", type=int, default=500)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    cups = _parse_cup_args(args.cup)
    seasons = _parse_season_args(args.season)
    seed_results_dir = ROOT / "data/raw/flashscore/seed_results"
    seed_results_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    skipped_ok = 0

    require_rich_meta = not args.no_validate_rich_meta

    def run_collect(url: str, out: Path) -> int:
        cmd = [
            sys.executable,
            "-m",
            "football_ai",
            "collect-flashscore-match-ids",
            "--url",
            url,
            "--wyniki-html-out",
            str(out),
            "--max-clicks",
            str(args.max_clicks),
            "--storage-state",
            str(ROOT / "data/flashscore_storage_state.json"),
            "--profile-dir",
            str(ROOT / "data/flashscore_profile"),
        ]
        if args.headed:
            cmd.append("--headed")
        print(f"   subprocess: football_ai collect-flashscore-match-ids ... → {out.name}", flush=True)
        return subprocess.run(cmd, cwd=str(ROOT)).returncode

    for cup_key in cups:
        info = CUPS[cup_key]
        slug = info["slug"]
        for season_short in seasons:
            label = f"{cup_key}_{season_short}"
            wyniki_path = seed_results_dir / f"{label}_wyniki.html"

            need = True
            if args.only_missing and _seed_acceptable(
                wyniki_path, min_bytes=args.min_bytes, require_rich_meta=require_rich_meta
            ):
                need = False

            url = results_page_url(slug=slug, season_folder4=season_short)
            if not need:
                print(f"SKIP OK: {label}", flush=True)
                skipped_ok += 1
                continue

            if args.dry_run:
                print(f"DRY-RUN would fetch: {label}\n  {url}\n  -> {wyniki_path.relative_to(ROOT)}", flush=True)
                continue

            rc = 1
            for attempt in range(1, args.attempts + 1):
                if args.jitter_seconds > 0:
                    time.sleep(random.uniform(0, args.jitter_seconds))
                print(f"\n=== {label} attempt {attempt}/{args.attempts} ===\n{url}", flush=True)
                rc = run_collect(url, wyniki_path)
                if rc == 0 and _seed_acceptable(
                    wyniki_path, min_bytes=args.min_bytes, require_rich_meta=require_rich_meta
                ):
                    print(f"  OK {label}", flush=True)
                    break
                print(f"  attempt failed (exit={rc}) or invalid HTML; retrying…", flush=True)
                if attempt < args.attempts:
                    time.sleep(max(4.0, args.pause_seconds))

            if rc != 0 or not _seed_acceptable(
                wyniki_path, min_bytes=args.min_bytes, require_rich_meta=require_rich_meta
            ):
                failures.append(label)
                print(f"  FAIL {label}", flush=True)
            else:
                time.sleep(args.pause_seconds)

    print(f"\nSkipped (already OK): {skipped_ok}", flush=True)
    if args.dry_run:
        print("Dry run — no subprocesses.", flush=True)
        return 0
    if failures:
        print(f"FAILURES ({len(failures)}): {', '.join(failures)}", flush=True)
        return 1
    print("All requested cup wyniki seeds OK.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
