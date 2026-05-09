"""
Build supplemental SQLite bridging Flashscore AA-meta with football-data CSV rows.

Usage (from repo root):
  python scripts/build_integration_supplement.py
  python scripts/build_integration_supplement.py --footballcsv-cache-fallback
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import data_integrity_flashscore as di  # noqa: E402

from football_ai.cli import FOOTBALL_DATA_LEAGUES  # noqa: E402
from football_ai.integration.join_football_data import (
    LEAG_KEY_TO_CLI,
    cache_footballdata_mirror_csv_path,
    cli_key_to_mmz_csv,
    engsoccerdata_cup_csv_path,
    engsoccerdata_cup_index,
    football_data_standard_index,
    footballcsv_cache_footballdata_index,
    load_manifest_mmz_overlay,
    lookup_fd_row,
    overlay_mmz_csv_path,
    pol_csv_path,
    poland_filtered_index,
    season_folder_pol_slash,
    season_four_to_engsoccer_start_year,
)
from football_ai.integration.flashscore_event_meta import load_flashscore_event_meta_bundle
from football_ai.integration.match_identity import compute_fixture_uid, compute_match_uid
from football_ai.integration.supplement_store import upsert_supplement_row
from football_ai.paths import get_paths
from football_ai.sources.flashscore_feed_match_meta import FlashscoreMatchMeta


def split_dataset(ds: str) -> tuple[str, str]:
    i = ds.rfind("-")
    return ds[:i], ds[i + 1 :]


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--footballcsv-cache-fallback",
        action="store_true",
        help=(
            "If Buchdahl MMZ CSV under football-data.co.uk/{season}/{code}.csv is missing, "
            "use mirror CSV from data/raw/footballcsv/cache-footballdata/{YYYY-YY}/ (github.com/footballcsv/cache.footballdata). "
            "Rows use english Date + Team 1/2; joins use distinct source tags."
        ),
    )
    args = ap.parse_args()
    fb_cache_mirror = args.footballcsv_cache_fallback

    paths = get_paths()
    bundle = load_flashscore_event_meta_bundle(
        repo_root=ROOT,
        raw_flashscore_dir=paths.raw_dir / "flashscore",
    )
    meta_ix: dict[str, FlashscoreMatchMeta] = bundle.index
    feeds = bundle.feeds_used_paths
    feed_note = bundle.feed_note
    if not feeds:
        print(
            "No feed .txt files for AA meta (see data/integrated/flashscore_list_feed_manifest.json).",
            feed_note,
            flush=True,
        )
    else:
        print(f"AA meta from {len(feeds)} feed file(s) ({feed_note})", flush=True)
    if bundle.augment_seed_count:
        print(
            "AA meta augmented from seed HTML:",
            bundle.augment_seed_count,
            "new event ids",
            flush=True,
        )

    db = ROOT / "data" / "integrated" / "supplement.sqlite"
    joined_fd = skipped_no_meta = skipped_no_row = 0

    csv_cache: dict[str, object | None] = {}
    csv_bridge_origin: dict[str, str] = {}
    esd_empty_warned: set[str] = set()
    pol_path = pol_csv_path(paths.raw_dir)
    pol_season_indexes: dict[str, object] = {}
    mmz_overlay = load_manifest_mmz_overlay(paths.root)

    def esd_cup_idx(league_key: str, season4: str, cup: str) -> object | None:
        ck = f"esd:{cup}:{season4}"
        if ck in csv_cache:
            return csv_cache[ck]
        cup_kind = "facup" if cup == "facup" else "leaguecup"
        p = engsoccerdata_cup_csv_path(paths.raw_dir, cup_kind)
        if not p.exists():
            print(f"Note: jalapic cup CSV missing ({league_key}): {p}", flush=True)
            csv_cache[ck] = None
            return None
        try:
            sy = season_four_to_engsoccer_start_year(season4)
        except ValueError as e:
            print(f"Note: bad season token for jalapic ({league_key}-{season4}): {e}", flush=True)
            csv_cache[ck] = None
            return None
        ix = engsoccerdata_cup_index(p, season_start_year=sy, cup=cup_kind)
        if not ix.key_to_rows and ck not in esd_empty_warned:
            print(
                f"Note: jalapic cup index empty for {cup_kind} year={sy} ({league_key}-{season4}): {p}",
                flush=True,
            )
            esd_empty_warned.add(ck)
        csv_cache[ck] = ix
        return ix

    def pol_idx(season4: str):
        if not pol_path.exists():
            return None
        slug = season_folder_pol_slash(season4)
        if slug not in pol_season_indexes:
            pol_season_indexes[slug] = poland_filtered_index(pol_path, slug)
        return pol_season_indexes[slug]

    def csv_idx(league_cli: str, season4: str):
        ck = f"{league_cli}:{season4}"
        if ck not in csv_cache:
            div_code = FOOTBALL_DATA_LEAGUES[league_cli].code
            mmz_p = cli_key_to_mmz_csv(paths.raw_dir, season4, league_cli)
            if mmz_p.exists():
                csv_cache[ck] = football_data_standard_index(mmz_p)
                csv_bridge_origin[ck] = "mmz"
            elif fb_cache_mirror:
                mirror_p = cache_footballdata_mirror_csv_path(paths.raw_dir, season4, div_code)
                if mirror_p and mirror_p.exists():
                    csv_cache[ck] = footballcsv_cache_footballdata_index(mirror_p)
                    csv_bridge_origin[ck] = "cache"
                else:
                    csv_cache[ck] = None
                    csv_bridge_origin[ck] = "missing"
            else:
                csv_cache[ck] = None
                csv_bridge_origin[ck] = "missing"
        return csv_cache[ck]

    def csv_idx_overlay(division_code: str, season4: str):
        ck = f"ov:{division_code}:{season4}"
        if ck not in csv_cache:
            mmz_p = overlay_mmz_csv_path(paths.raw_dir, season4, division_code)
            if mmz_p.exists():
                csv_cache[ck] = football_data_standard_index(mmz_p)
                csv_bridge_origin[ck] = "mmz"
            elif fb_cache_mirror:
                mirror_p = cache_footballdata_mirror_csv_path(paths.raw_dir, season4, division_code)
                if mirror_p and mirror_p.exists():
                    csv_cache[ck] = footballcsv_cache_footballdata_index(mirror_p)
                    csv_bridge_origin[ck] = "cache"
                else:
                    csv_cache[ck] = None
                    csv_bridge_origin[ck] = "missing"
            else:
                csv_cache[ck] = None
                csv_bridge_origin[ck] = "missing"
        return csv_cache[ck]

    if not pol_path.exists():
        print(f"Note: aggregated POL Ekstraklasa CSV missing: {pol_path}", flush=True)

    for dlabel, ids_name, base in di.league_manifest():
        leigh_key, season4 = split_dataset(dlabel)
        ids_path = di.IDS / f"{ids_name}.txt"
        if not ids_path.exists():
            continue

        idx_obj: object | None
        cli: str = ""
        div_code = ""

        if leigh_key == "ekstraklasa":
            idx_obj = pol_idx(season4)
            cli = "POL_AGG"
        elif leigh_key in LEAG_KEY_TO_CLI:
            idx_obj = csv_idx(LEAG_KEY_TO_CLI[leigh_key], season4)
            lk = LEAG_KEY_TO_CLI[leigh_key]
            cli = lk
            div_code = FOOTBALL_DATA_LEAGUES[lk].code
        elif leigh_key in mmz_overlay:
            ocode = mmz_overlay[leigh_key]
            idx_obj = csv_idx_overlay(ocode, season4)
            cli = "MMZ_OVERLAY"
            div_code = ocode
        elif leigh_key == "fa_cup":
            idx_obj = esd_cup_idx("fa_cup", season4, "facup")
            cli = "ENGSD"
            div_code = "FACUP"
        elif leigh_key == "carabao_cup":
            idx_obj = esd_cup_idx("carabao_cup", season4, "leaguecup")
            cli = "ENGSD"
            div_code = "CARABAO"
        else:
            continue

        if idx_obj is None:
            continue

        event_ids = [ln.strip() for ln in ids_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

        ck_bridge = ""
        if leigh_key in LEAG_KEY_TO_CLI:
            ck_bridge = f"{LEAG_KEY_TO_CLI[leigh_key]}:{season4}"
        elif leigh_key in mmz_overlay:
            ck_bridge = f"ov:{mmz_overlay[leigh_key]}:{season4}"

        if leigh_key == "fa_cup":
            source_tag = f"engsoccerdata:facup:{season4}"
        elif leigh_key == "carabao_cup":
            source_tag = f"engsoccerdata:carabao:{season4}"
        elif ck_bridge and csv_bridge_origin.get(ck_bridge) == "cache":
            source_tag = f"footballcsv-cache-footballdata:{season4}:{leigh_key}:{div_code or 'POL'}"
        else:
            source_tag = f"football-data.co.uk:{season4}:{leigh_key}:{div_code or 'POL'}"

        for eid in event_ids:
            meta = meta_ix.get(eid)
            if meta is None:
                skipped_no_meta += 1
                continue
            row = lookup_fd_row(
                idx_obj,
                unix_ts=meta.unix_kickoff,
                nh=meta.home_team,
                na=meta.away_team,
            )
            if row is None:
                skipped_no_row += 1
                continue
            m_uid = compute_match_uid(
                dataset_label=dlabel,
                unix_kickoff=meta.unix_kickoff,
                home_name=meta.home_team,
                away_name=meta.away_team,
            )
            f_uid = compute_fixture_uid(
                unix_kickoff=meta.unix_kickoff,
                home_name=meta.home_team,
                away_name=meta.away_team,
            )
            upsert_supplement_row(
                db,
                dataset=dlabel,
                event_id=eid,
                source=source_tag,
                unix_kickoff=meta.unix_kickoff,
                home_name=meta.home_team,
                away_name=meta.away_team,
                match_uid=m_uid,
                fixture_uid=f_uid,
                payload={
                    "source": source_tag,
                    "match_uid": m_uid,
                    "fixture_uid": f_uid,
                    "cli_key": cli,
                    "division": div_code or "POL",
                    "csv_row": row,
                },
            )
            joined_fd += 1

    print(
        "football-data join: ",
        joined_fd,
        "rows written; skipped_no_meta AA=",
        skipped_no_meta,
        "skipped_no_row=",
        skipped_no_row,
        flush=True,
    )
    print(f"SQLite at {db}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
