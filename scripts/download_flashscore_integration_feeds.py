"""Pobieranie list-feedow Flashscore wg manifestu (data/integrated/flashscore_list_feed_manifest.json).

  python scripts/download_flashscore_integration_feeds.py
  python scripts/download_flashscore_integration_feeds.py --force --delay 2.0
  python scripts/download_flashscore_integration_feeds.py --only mega

Nastepnie: build_integration_supplement, download_openfootball_allowlist, integration_coverage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_ai.http import HttpClient
from football_ai.integration.flashscore_integration_feeds import feed_output_path
from football_ai.paths import get_paths
from football_ai.sources.flashscore import download_feed_raw
from football_ai.storage import Storage


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download Flashscore x/feed list files for integration meta")
    p.add_argument("--delay", type=float, default=2.0, help="Seconds between HTTP downloads")
    p.add_argument("--force", action="store_true", help="Re-download even if cached in storage")
    p.add_argument("--only", action="append", default=[], help="Tag filter (repeatable); entry must share a tag")
    p.add_argument("--manifest", type=Path, default=None, help="Override manifest path")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo = Path.cwd()
    paths = get_paths()
    mf = args.manifest if args.manifest is not None else (repo / "data" / "integrated" / "flashscore_list_feed_manifest.json")
    if not mf.exists():
        print(f"No manifest at {mf} — skip downloads.", flush=True)
        return 0
    manifest = json.loads(mf.read_text(encoding="utf-8-sig"))
    tags_filter = frozenset(args.only) if args.only else None
    http = HttpClient(min_delay_s=max(args.delay, 1.25))
    storage = Storage(db_path=paths.db_path, raw_dir=paths.raw_dir)
    feeds_dir = paths.raw_dir / "flashscore" / "feeds"
    feeds_dir.mkdir(parents=True, exist_ok=True)

    entries = manifest.get("download") or []
    downloaded = skipped = 0
    for ent in entries:
        fk = str(ent.get("feed_key") or "").strip()
        if not fk:
            continue
        tset = {str(x) for x in (ent.get("tags") or [])}
        if tags_filter is not None and tset and not (tset & tags_filter):
            skipped += 1
            continue
        fn_opt = ent.get("filename")
        filename_arg = None if fn_opt in (None, "") else str(fn_opt)
        target = feed_output_path(feeds_dir, fk, filename_arg).name
        download_feed_raw(
            storage=storage,
            http=http,
            feed=fk,
            subdir="feeds",
            filename=target,
            force=args.force,
        )
        downloaded += 1
        print(f"OK {fk} -> flashscore/feeds/{target}", flush=True)
    print(f"Done: downloaded={downloaded} skipped_by_tag={skipped}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
