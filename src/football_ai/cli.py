from __future__ import annotations

import argparse
from pathlib import Path

from football_ai.http import HttpClient
from football_ai.paths import get_paths
from football_ai.sources.football_data import (
    FootballDataLeague,
    download_results_csv,
)
from football_ai.sources.flashscore import download_feed_raw, download_url_raw
from football_ai.sources.flashscore_feed_parse import extract_event_ids_by_tournament_path
from football_ai.sources.flashscore_playwright import (
    CollectConfig,
    collect_match_ids_from_results_page,
    init_storage_state,
)
from football_ai.storage import Storage


FOOTBALL_DATA_LEAGUES = {
    # Basic mapping (we will extend as needed)
    "ENG1": FootballDataLeague(code="E0", name="Premier League"),
    "ENG2": FootballDataLeague(code="E1", name="Championship"),
    "ESP1": FootballDataLeague(code="SP1", name="La Liga"),
    "ITA1": FootballDataLeague(code="I1", name="Serie A"),
    "GER1": FootballDataLeague(code="D1", name="Bundesliga"),
    "FRA1": FootballDataLeague(code="F1", name="Ligue 1"),
    "NED1": FootballDataLeague(code="N1", name="Eredivisie"),
    "POR1": FootballDataLeague(code="P1", name="Primeira Liga"),
    "BEL1": FootballDataLeague(code="B1", name="Belgian Pro League"),
    "TUR1": FootballDataLeague(code="T1", name="Süper Lig"),
    "GRE1": FootballDataLeague(code="G1", name="Super League Greece"),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="football_ai")
    sub = p.add_subparsers(dest="cmd", required=True)

    dl_fd = sub.add_parser("download-football-data", help="Download football-data.co.uk CSVs")
    dl_fd.add_argument(
        "--season",
        action="append",
        required=True,
        help="Repeatable. Example: --season 2223 --season 2324 --season 2425 --season 2526",
    )
    dl_fd.add_argument(
        "--league",
        action="append",
        required=True,
        help="League key, repeatable. Example: --league ENG1 --league ESP1",
    )
    dl_fd.add_argument("--force", action="store_true", help="Ignore cache and re-download")

    dl_urls = sub.add_parser(
        "download-urls",
        help="Download RAW URLs to data/raw (useful for Flashscore)",
    )
    dl_urls.add_argument("--source", required=True, help="Source name label, e.g. flashscore")
    dl_urls.add_argument("--urls-file", required=True, help="Text file with one URL per line")
    dl_urls.add_argument("--subdir", required=True, help="Subdirectory under data/raw/<source>/")
    dl_urls.add_argument("--force", action="store_true", help="Ignore cache and re-download")

    dl_feed = sub.add_parser(
        "download-flashscore-feed",
        help="Download Flashscore x/feed payload (RAW)",
    )
    dl_feed.add_argument("--feed", required=True, help="Feed key, e.g. f_1_-1_3_pl_1")
    dl_feed.add_argument("--subdir", required=True, help="Subdirectory under data/raw/flashscore/")
    dl_feed.add_argument("--force", action="store_true", help="Ignore cache and re-download")

    dl_from_feed = sub.add_parser(
        "download-flashscore-from-feed",
        help="From a list feed, download match detail/stat feeds for one tournament",
    )
    dl_from_feed.add_argument("--feed", required=True, help="List feed key, e.g. f_1_-1_3_pl_1")
    dl_from_feed.add_argument(
        "--tournament-path",
        required=True,
        help="Tournament path substring, e.g. /pilka-nozna/polska/pko-bp-ekstraklasa/",
    )
    dl_from_feed.add_argument(
        "--out-subdir",
        required=True,
        help="Where to store match feeds under data/raw/flashscore/",
    )
    dl_from_feed.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit of matches to download (0 = no limit).",
    )
    dl_from_feed.add_argument("--force", action="store_true", help="Ignore cache and re-download")

    collect_ids = sub.add_parser(
        "collect-flashscore-match-ids",
        help="Use headless browser to collect match IDs from a results page",
    )
    collect_ids.add_argument("--url", required=True, help="Tournament results URL")
    collect_ids.add_argument("--out", required=True, help="Output .txt file path")
    collect_ids.add_argument("--max-clicks", type=int, default=500, help="Max 'show more' clicks")
    collect_ids.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    collect_ids.add_argument(
        "--storage-state",
        default="data/flashscore_storage_state.json",
        help="Path to Playwright storage_state.json",
    )
    collect_ids.add_argument(
        "--debug-dir",
        default="data/flashscore_debug",
        help="Write debug artifacts (png/html/response urls) here",
    )

    init_session = sub.add_parser(
        "init-flashscore-session",
        help="Open browser to accept consent and save storage state",
    )
    init_session.add_argument(
        "--url",
        default="https://www.flashscore.pl/",
        help="URL to open in browser for session init",
    )
    init_session.add_argument(
        "--out",
        default="data/flashscore_storage_state.json",
        help="Where to save storage_state.json",
    )
    init_session.add_argument(
        "--profile-dir",
        default="data/flashscore_profile",
        help="Persistent browser profile directory",
    )

    harvest = sub.add_parser(
        "harvest-flashscore-season",
        help="Collect eventIds from a results page and download df_sui+df_st for all matches",
    )
    harvest.add_argument("--results-url", required=True, help="Season results URL (Flashscore.pl)")
    harvest.add_argument(
        "--out-subdir",
        required=True,
        help="Where to store match feeds under data/raw/flashscore/",
    )
    harvest.add_argument(
        "--event-ids-out",
        default="event_ids.txt",
        help="Write collected eventIds to this file path",
    )
    harvest.add_argument("--max-clicks", type=int, default=500, help="Max 'show more' clicks")
    harvest.add_argument("--limit", type=int, default=0, help="Optional limit (0 = no limit)")
    harvest.add_argument(
        "--storage-state",
        default="data/flashscore_storage_state.json",
        help="Path to Playwright storage_state.json",
    )
    harvest.add_argument(
        "--profile-dir",
        default="data/flashscore_profile",
        help="Persistent browser profile directory",
    )
    harvest.add_argument(
        "--debug-dir",
        default="data/flashscore_debug",
        help="Write debug artifacts here",
    )
    harvest.add_argument("--force", action="store_true", help="Ignore cache and re-download")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = get_paths()
    storage = Storage(db_path=paths.db_path, raw_dir=paths.raw_dir)
    http = HttpClient()

    if args.cmd == "download-football-data":
        for season in args.season:
            for key in args.league:
                if key not in FOOTBALL_DATA_LEAGUES:
                    raise SystemExit(
                        f"Unknown league key: {key}. Known: {sorted(FOOTBALL_DATA_LEAGUES)}"
                    )
                download_results_csv(
                    storage=storage,
                    http=http,
                    season=season,
                    league=FOOTBALL_DATA_LEAGUES[key],
                    force=args.force,
                )
        return 0

    if args.cmd == "download-urls":
        urls_path = Path(args.urls_file)
        if not urls_path.exists():
            raise SystemExit(f"urls-file not found: {urls_path}")
        urls: list[str] = []
        for line in urls_path.read_text(encoding="utf-8").splitlines():
            u = line.strip()
            if not u or u.startswith("#"):
                continue
            urls.append(u)
        if not urls:
            return 0

        if args.source.lower() != "flashscore":
            raise SystemExit("Only --source flashscore is supported in MVP.")

        # Be polite to public websites.
        http.min_delay_s = max(http.min_delay_s, 2.0)

        for i, url in enumerate(urls, start=1):
            filename = f"{i:06d}.html"
            download_url_raw(
                storage=storage,
                http=http,
                url=url,
                subdir=args.subdir,
                filename=filename,
                force=args.force,
            )
        return 0

    if args.cmd == "download-flashscore-feed":
        http.min_delay_s = max(http.min_delay_s, 2.0)
        download_feed_raw(
            storage=storage,
            http=http,
            feed=args.feed,
            subdir=args.subdir,
            force=args.force,
        )
        return 0

    if args.cmd == "download-flashscore-from-feed":
        # 1) ensure list feed is present as RAW
        http.min_delay_s = max(http.min_delay_s, 2.0)
        download_feed_raw(
            storage=storage,
            http=http,
            feed=args.feed,
            subdir="feeds",
            force=args.force,
        )
        # 2) read the feed we just stored (most recent version in our RAW folder is fine)
        # We know our downloader stores as <feed>.txt.
        feed_path = paths.raw_dir / "flashscore" / "feeds" / f"{args.feed}.txt"
        if not feed_path.exists():
            raise SystemExit(f"Feed file not found after download: {feed_path}")

        feed_text = feed_path.read_text(encoding="utf-8", errors="ignore")
        event_ids = extract_event_ids_by_tournament_path(feed_text, args.tournament_path)
        if args.limit and args.limit > 0:
            event_ids = event_ids[: args.limit]

        for eid in event_ids:
            # Match info/events + match stats
            for match_feed in (f"df_sui_1_{eid}", f"df_st_1_{eid}"):
                download_feed_raw(
                    storage=storage,
                    http=http,
                    feed=match_feed,
                    subdir=f"{args.out_subdir}/{eid}",
                    force=args.force,
                )
        return 0

    if args.cmd == "collect-flashscore-match-ids":
        cfg = CollectConfig(
            headless=not args.headed,
            timeout_ms=120_000,
            storage_state_path=Path(args.storage_state),
            user_data_dir=Path("data/flashscore_profile"),
            debug_dir=Path(args.debug_dir),
        )
        ids = collect_match_ids_from_results_page(
            url=args.url,
            max_clicks=args.max_clicks,
            config=cfg,
        )
        out_path = Path(args.out)
        out_path.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
        return 0

    if args.cmd == "init-flashscore-session":
        init_storage_state(
            url=args.url,
            out_path=Path(args.out),
            user_data_dir=Path(args.profile_dir),
        )
        return 0

    if args.cmd == "harvest-flashscore-season":
        cfg = CollectConfig(
            headless=True,
            # Some Flashscore seasons occasionally load slower / hit anti-bot delays.
            # We keep this higher for reliability; it only affects Playwright navigation/actions.
            timeout_ms=240_000,
            storage_state_path=Path(args.storage_state),
            user_data_dir=Path(args.profile_dir),
            debug_dir=Path(args.debug_dir),
        )
        event_ids = collect_match_ids_from_results_page(
            url=args.results_url,
            max_clicks=args.max_clicks,
            config=cfg,
        )
        if args.limit and args.limit > 0:
            event_ids = event_ids[: args.limit]

        out_ids_path = Path(args.event_ids_out)
        out_ids_path.parent.mkdir(parents=True, exist_ok=True)
        out_ids_path.write_text(
            "\n".join(event_ids) + ("\n" if event_ids else ""), encoding="utf-8"
        )

        # Be polite to public websites.
        http.min_delay_s = max(http.min_delay_s, 2.0)

        for eid in event_ids:
            for match_feed in (f"df_sui_1_{eid}", f"df_st_1_{eid}"):
                download_feed_raw(
                    storage=storage,
                    http=http,
                    feed=match_feed,
                    subdir=f"{args.out_subdir}/{eid}",
                    force=args.force,
                )
        return 0

    raise SystemExit(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())

