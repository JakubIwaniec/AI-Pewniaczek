"""
Tier-B coverage: RAW Flashscore completeness vs supplementary SQLite overlays.

Produces data/integrated/coverage_latest.json
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import DefaultDict

ROOT = Path(__file__).resolve().parents[1]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(ROOT / "scripts"))

import data_integrity_flashscore as di  # noqa: E402

from football_ai.integration.join_football_data import (  # noqa: E402
    LEAG_KEY_TO_CLI,
    cli_key_to_mmz_csv,
    engsoccerdata_cup_csv_path,
    engsoccerdata_cup_index,
    load_manifest_mmz_overlay,
    overlay_mmz_csv_path,
    pol_csv_path,
    season_four_to_engsoccer_start_year,
)
from football_ai.integration.domestic_cup_flashscore import is_domestic_cup_league_key  # noqa: E402
from football_ai.integration.match_identity import utc_date_iso_from_unix  # noqa: E402
from football_ai.integration.normalize import norm_club  # noqa: E402
from football_ai.paths import get_paths  # noqa: E402
from football_ai.sources.flashscore_feed_match_meta import iter_match_meta_from_feed  # noqa: E402


def _load_sources_by_event(db_path: Path) -> DefaultDict[tuple[str, str], list[str]]:
    from collections import defaultdict

    buckets: DefaultDict[tuple[str, str], list[str]] = defaultdict(list)
    if not db_path.exists():
        return buckets
    with sqlite3.connect(db_path) as con:
        for row in con.execute("SELECT dataset,event_id,source FROM supplement;"):
            buckets[(row[0], row[1])].append(row[2])
    return buckets


def _ds_label_split(ds: str) -> tuple[str, str]:
    idx = ds.rfind("-")
    return ds[:idx], ds[idx + 1 :]


def _openfootball_uefa_overlay(db_path: Path) -> dict:
    """IDS event counts vs supplemental OpenFootball rows for UEFA datasets."""
    ue = frozenset({"liga_mistrzow", "liga_europy", "liga_konferencji"})
    if not db_path.exists():
        return {"supplement_missing": True, "by_dataset_label": {}, "overall": {}}
    rows: dict[str, dict] = {}
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        for dlabel, ids_name, _base in di.league_manifest():
            leigh_key, season4 = _ds_label_split(dlabel)
            if leigh_key not in ue:
                continue
            id_p = di.IDS / f"{ids_name}.txt"
            if not id_p.exists():
                continue
            n_ids = sum(1 for ln in id_p.read_text(encoding="utf-8").splitlines() if ln.strip())
            n_of = int(
                cur.execute(
                    "SELECT COUNT(DISTINCT event_id) FROM supplement "
                    "WHERE dataset = ? AND source LIKE 'openfootball:%';",
                    (dlabel,),
                ).fetchone()[0]
                or 0
            )
            rows[dlabel] = {
                "ids_event_count": n_ids,
                "openfootball_distinct_event_ids": n_of,
                "openfootball_coverage_vs_ids_fraction": round(n_of / n_ids, 4) if n_ids else None,
                "season_folder4": season4,
            }
    tot_ids = sum(r["ids_event_count"] for r in rows.values())
    tot_of = sum(r["openfootball_distinct_event_ids"] for r in rows.values())
    return {
        "by_dataset_label": rows,
        "overall": {
            "uefa_sum_ids_events": tot_ids,
            "uefa_sum_openfootball_distinct_events": tot_of,
            "openfootball_coverage_vs_ids_fraction": round(tot_of / tot_ids, 4) if tot_ids else None,
        },
    }


def _experimental_cross_source_by_date_pair(db_path: Path) -> dict:
    """D2: same UTC date + sorted norm pair with both FD and OF rows (high false-positive risk)."""
    if not db_path.exists():
        return {
            "distinct_date_pair_keys_with_both_fd_and_openfootball": 0,
            "disclaimer": "Experimental: may count unrelated league+cup same-day homonyms.",
        }
    buckets: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    with sqlite3.connect(db_path) as con:
        for unix_k, home, away, source in con.execute(
            "SELECT unix_kickoff, home_name, away_name, source FROM supplement;"
        ):
            d_iso = utc_date_iso_from_unix(unix_k)
            if not d_iso:
                continue
            h, a = norm_club(str(home)), norm_club(str(away))
            if not h or not a:
                continue
            p0, p1 = (h, a) if h <= a else (a, h)
            key = (d_iso, p0, p1)
            if str(source).startswith("football-data.co.uk"):
                buckets[key].add("fd")
            elif str(source).startswith("openfootball:"):
                buckets[key].add("of")
    n_both = sum(1 for tags in buckets.values() if "fd" in tags and "of" in tags)
    return {
        "distinct_date_pair_keys_with_both_fd_and_openfootball": n_both,
        "disclaimer": (
            "Experimental cross-competition proxy: same UTC calendar date and same sorted norm_club pair "
            "with at least one football-data row and one openfootball row. "
            "Can double-count or mis-link (e.g. domestic vs European fixture same names)."
        ),
    }


def _football_data_manifest_bridge_stats() -> dict:
    """B1/B2: manifest datasets vs CSV on disk (standard MMZ, POL, optional overlay map)."""
    raw_dir = get_paths().raw_dir
    root = get_paths().root
    overlay = load_manifest_mmz_overlay(root)

    no_bridge: list[dict] = []
    csv_missing: list[dict] = []
    csv_present = 0
    for dlabel, _ids_name, _base in di.league_manifest():
        lk, seas4 = _ds_label_split(dlabel)
        if lk == "ekstraklasa":
            p = pol_csv_path(raw_dir)
            if p.exists() and p.stat().st_size > 0:
                csv_present += 1
            else:
                csv_missing.append({"dataset_label": dlabel, "expected_csv": str(p)})
        elif lk in LEAG_KEY_TO_CLI:
            p = cli_key_to_mmz_csv(raw_dir, seas4, LEAG_KEY_TO_CLI[lk])
            if p.exists() and p.stat().st_size > 0:
                csv_present += 1
            else:
                csv_missing.append(
                    {
                        "dataset_label": dlabel,
                        "cli_key": LEAG_KEY_TO_CLI[lk],
                        "expected_csv": str(p),
                    }
                )
        elif lk in overlay:
            p = overlay_mmz_csv_path(raw_dir, seas4, overlay[lk])
            if p.exists() and p.stat().st_size > 0:
                csv_present += 1
            else:
                csv_missing.append(
                    {
                        "dataset_label": dlabel,
                        "manifest_mmz_overlay_key": lk,
                        "division_code": overlay[lk],
                        "expected_csv": str(p),
                    }
                )
        else:
            no_bridge.append(
                {
                    "dataset_label": dlabel,
                    "league_key": lk,
                    "reason": (
                        "not in LEAG_KEY_TO_CLI / ekstraklasa / "
                        "data/integrated/football_data_manifest_mmz_overlay.json"
                    ),
                }
            )
    return {
        "manifest_rows_total": len(di.league_manifest()),
        "datasets_with_football_data_bridge_and_nonempty_csv": csv_present,
        "datasets_excluded_from_football_data_join": len(no_bridge),
        "datasets_bridged_but_csv_missing_or_empty": len(csv_missing),
        "mmz_overlay_league_keys_configured": sorted(overlay),
        "excluded_detail_sample": no_bridge[:25],
        "csv_missing_detail_sample": csv_missing[:25],
    }


def _load_openfootball_upstream_status() -> list | dict:
    p = ROOT / "data" / "integrated" / "openfootball_source_status.json"
    if not p.exists():
        return {"note": "Run scripts/download_openfootball_allowlist.py to generate openfootball_source_status.json"}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {"error": "invalid_json", "path": str(p)}


def _supplement_identity_stats(db_path: Path) -> dict:
    base_note = (
        "match_uid includes dataset_label in the hash (see match_identity.compute_match_uid). "
        "UEFA supplement rows use liga_mistrzow-* etc.; football-data rows use premier_league-* etc. "
        "The pipeline never writes both sources for the same dataset_label, so "
        "match_uids_with_both_fd_and_openfootball is expected to be 0; it is not a global integration KPI."
    )
    fid_note = (
        "fixture_uid is UTC calendar date plus norm_club home/away (see compute_fixture_uid). "
        "It may collide across unrelated same-day fixtures—fixture_uid KPIs exclude UEFA dataset GLOB liga_* "
        "when reporting domestic FD+OF co-occurrence."
    )
    collision_sql = """
        SELECT COUNT(*) FROM (
          SELECT fixture_uid FROM supplement
          WHERE fixture_uid IS NOT NULL AND trim(fixture_uid) <> ''
          GROUP BY fixture_uid HAVING COUNT(DISTINCT dataset) > 1
        ) q;
        """
    domestic_fixture_multi_sql = """
        SELECT COUNT(*) FROM (
          SELECT fixture_uid FROM supplement
          WHERE fixture_uid IS NOT NULL AND trim(fixture_uid) <> ''
            AND dataset NOT GLOB 'liga_mistrzow-*'
            AND dataset NOT GLOB 'liga_europy-*'
            AND dataset NOT GLOB 'liga_konferencji-*'
          GROUP BY fixture_uid
          HAVING SUM(CASE WHEN source LIKE 'football-data.co.uk%' THEN 1 ELSE 0 END) > 0
             AND SUM(CASE WHEN source LIKE 'openfootball:%' THEN 1 ELSE 0 END) > 0
        ) x;
        """
    empty = {
        "rows_with_nonempty_match_uid": 0,
        "distinct_match_uid": 0,
        "match_uids_with_both_fd_and_openfootball": 0,
        "rows_with_nonempty_fixture_uid": 0,
        "distinct_fixture_uid": 0,
        "fixture_uids_collision_distinct_dataset_count_gt1": 0,
        "fixture_uids_domestic_non_uefa_dataset_with_fd_and_openfootball": 0,
        "match_uid_dual_metric_note": base_note,
        "fixture_uid_cross_source_note": fid_note,
        "experimental_cross_source_date_norm_pair": _experimental_cross_source_by_date_pair(db_path),
    }
    if not db_path.exists():
        return empty

    with sqlite3.connect(db_path) as con:
        def _scalar(q: str) -> int:
            return int(con.execute(q).fetchone()[0] or 0)

        cols = {row[1] for row in con.execute("PRAGMA table_info(supplement);")}
        has_fixture = "fixture_uid" in cols

        rows_uid = _scalar(
            "SELECT COUNT(*) FROM supplement WHERE match_uid IS NOT NULL AND trim(match_uid) <> '';"
        )
        distinct = _scalar(
            "SELECT COUNT(DISTINCT match_uid) FROM supplement "
            "WHERE match_uid IS NOT NULL AND trim(match_uid) <> '';"
        )
        multi = _scalar(
            """
            SELECT COUNT(*) FROM (
              SELECT match_uid FROM supplement
              WHERE match_uid IS NOT NULL AND trim(match_uid) <> ''
              GROUP BY match_uid
              HAVING SUM(CASE WHEN source LIKE 'football-data.co.uk%' THEN 1 ELSE 0 END) > 0
                 AND SUM(CASE WHEN source LIKE 'openfootball:%' THEN 1 ELSE 0 END) > 0
            ) x;
            """
        )
        rows_fid = distinct_fid = coll = dom_multi = 0
        if has_fixture:
            rows_fid = _scalar(
                "SELECT COUNT(*) FROM supplement WHERE fixture_uid IS NOT NULL AND trim(fixture_uid) <> '';"
            )
            distinct_fid = _scalar(
                "SELECT COUNT(DISTINCT fixture_uid) FROM supplement "
                "WHERE fixture_uid IS NOT NULL AND trim(fixture_uid) <> '';"
            )
            coll = _scalar(collision_sql)
            dom_multi = _scalar(domestic_fixture_multi_sql)

    return {
        "rows_with_nonempty_match_uid": rows_uid,
        "distinct_match_uid": distinct,
        "match_uids_with_both_fd_and_openfootball": multi,
        "rows_with_nonempty_fixture_uid": rows_fid,
        "distinct_fixture_uid": distinct_fid,
        "fixture_uids_collision_distinct_dataset_count_gt1": coll,
        "fixture_uids_domestic_non_uefa_dataset_with_fd_and_openfootball": dom_multi,
        "match_uid_dual_metric_note": base_note,
        "fixture_uid_cross_source_note": fid_note,
        "experimental_cross_source_date_norm_pair": _experimental_cross_source_by_date_pair(db_path),
    }


def _jalapic_fa_carabao_bridge_by_dataset() -> dict:
    """Same season-year rule as build_integration_supplement + engsoccerdata_cup_index."""
    from football_ai.integration.domestic_cup_flashscore import FLASHSCORE_CUP_SEASON_FOLDERS

    raw_dir = get_paths().raw_dir
    by: dict[str, dict] = {}
    for lk, ck in (("fa_cup", "facup"), ("carabao_cup", "leaguecup")):
        p = engsoccerdata_cup_csv_path(raw_dir, ck)
        csv_ok = p.exists() and p.stat().st_size > 0
        for seas in FLASHSCORE_CUP_SEASON_FOLDERS:
            dlabel = f"{lk}-{seas}"
            sy = season_four_to_engsoccer_start_year(seas)
            n_bk = 0
            nonzero = False
            if csv_ok:
                ix = engsoccerdata_cup_index(p, season_start_year=sy, cup=ck)
                n_bk = len(ix.key_to_rows)
                nonzero = n_bk > 0
            by[dlabel] = {
                "cup_kind_jalapic": ck,
                "jalapic_csv_path": str(p),
                "jalapic_csv_nonempty_on_disk": csv_ok,
                "season_start_year": sy,
                "indexed_key_bucket_count": n_bk,
                "indexed_non_empty_for_season": nonzero,
            }
    return {"by_dataset_label": by, "note": "Empty buckets for sy>=2022 with current jalapic CSVs is expected."}


def _domestic_cups_augment_metrics() -> dict:
    IDS = di.IDS
    seed_root = ROOT / "data/raw/flashscore/seed_results"
    cup_cap_missing = 15
    metric_note = (
        "aa_meta_rich_coverage_fraction_seed_html_only intersects IDS with iter_match_meta_from_feed(parsed seed); "
        "build_integration_supplement loads mega-feeds before augment_meta_index_from_seed_html — final meta_ix differs."
    )
    by_dl: dict[str, dict[str, object]] = {}
    for dlabel, ids_name, base in di.league_manifest():
        lk, seas4 = _ds_label_split(dlabel)
        if not is_domestic_cup_league_key(lk):
            continue
        id_path = IDS / f"{ids_name}.txt"
        ids_list: list[str] = []
        if id_path.exists():
            ids_list = [ln.strip() for ln in id_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        ids_set = set(ids_list)
        seed_p = seed_root / f"{ids_name}_wyniki.html"
        seed_exists = seed_p.exists() and seed_p.stat().st_size > 0
        rich_hit: set[str] = set()
        if ids_set and seed_exists:
            txt = seed_p.read_text(encoding="utf-8", errors="ignore")
            for m in iter_match_meta_from_feed(txt):
                if m.event_id in ids_set:
                    rich_hit.add(m.event_id)

        denom = len(ids_list)
        n_sui_st = sum(
            1
            for eid in ids_list
            if di.feed_ok(base, eid, "df_sui_1") and di.feed_ok(base, eid, "df_st_1")
        )
        n_li = sum(1 for eid in ids_list if di.feed_ok(base, eid, "df_li_1"))

        missing = sorted(ids_set - rich_hit)[:cup_cap_missing]
        by_dl[dlabel] = {
            "league_key": lk,
            "season_folder4": seas4,
            "ids_txt_stem": ids_name,
            "ids_event_count": denom,
            "seed_wyniki_html_path_expected": str(seed_p.relative_to(ROOT)),
            "seed_wyniki_html_exists_nonempty": seed_exists,
            "aa_meta_rich_coverage_fraction_seed_html_only": (round(len(rich_hit) / denom, 4) if denom else None),
            "ids_without_rich_meta_in_seed_sample": missing if missing else None,
            "raw_fraction_with_nonempty_df_sui_and_df_st": (round(n_sui_st / denom, 4) if denom else None),
            "raw_fraction_with_nonempty_df_li": (round(n_li / denom, 4) if denom else None),
        }

    sql_hints = (
        "-- supplement.sqlite: domestic cups by dataset prefix\n"
        "SELECT substr(dataset, 1, 30) ds, COUNT(*), COUNT(DISTINCT event_id)\n"
        "FROM supplement\n"
        "WHERE dataset LIKE 'fa_cup-%'\n"
        "   OR dataset LIKE 'carabao_cup-%'\n"
        "GROUP BY 1 ORDER BY 2 DESC;\n"
        "SELECT DISTINCT source FROM supplement WHERE dataset LIKE 'fa_cup-%' OR dataset LIKE 'carabao_cup-%' LIMIT 20;"
    )
    return {"by_dataset_label": by_dl, "metric_note": metric_note, "sqlite_hints": sql_hints}


def main() -> int:
    gap = di.gap_stats()
    ms, mt, ml, incomplete, _, tot = gap

    db_path = ROOT / "data" / "integrated" / "supplement.sqlite"
    buckets = _load_sources_by_event(db_path)

    still_st_no_fallback = raw_li_gap = fallback_fd = fallback_of = tier_b_dual = 0
    li_gap_has_st = li_gap_no_st = 0
    tier_b_dual_detail: list[tuple[str, str]] = []

    for dlabel, ids_name, base in di.league_manifest():
        path = di.IDS / f"{ids_name}.txt"
        if not path.exists():
            continue
        eids = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for eid in eids:
            ok_st = di.feed_ok(base, eid, "df_st_1")
            ok_li = di.feed_ok(base, eid, "df_li_1")
            srcs = buckets.get((dlabel, eid), [])
            fd_hit = any(s.startswith("football-data.co.uk") for s in srcs)
            of_hit = any(s.startswith("openfootball:") for s in srcs)
            if fd_hit:
                fallback_fd += 1
            if of_hit:
                fallback_of += 1
            if fd_hit and of_hit:
                tier_b_dual += 1
                if len(tier_b_dual_detail) < 120:
                    tier_b_dual_detail.append((dlabel, eid))

            if (not ok_st) and not fd_hit and not of_hit:
                still_st_no_fallback += 1
            if not ok_li:
                raw_li_gap += 1
                if ok_st:
                    li_gap_has_st += 1
                else:
                    li_gap_no_st += 1

    out = ROOT / "data" / "integrated" / "coverage_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "2",
        "raw_gap_stats": {
            "events_total": tot,
            "incomplete_events_flashscore_audit": incomplete,
            "missing_df_sui": ms,
            "missing_df_st": mt,
            "missing_df_li": ml,
            "notes": (
                "df_sui_missing counts events where RAW sui absent; "
                "supplement.sqlite does NOT change these checks."
            ),
        },
        "supplement_totals_seen_on_any_event_iteration": {
            "events_touching_fallback_fd_counts_loops_events": fallback_fd,
            "events_touching_fallback_of_counts_loops_events": fallback_of,
            "events_dual_fallback_fd_and_of": tier_b_dual,
            "dual_sample_pairs_dataset_eid": tier_b_dual_detail[:40],
            "events_dual_note": (
                "Per manifest (dataset_label, event_id): event has at least one football-data row and one "
                "openfootball row in supplement. Usually 0 because UEFA datasets only receive OpenFootball merges "
                "and domestic leagues only football-data in the default pipeline."
            ),
        },
        "tier_b_model_hints": {
            "still_without_raw_df_st_and_without_any_supplement": still_st_no_fallback,
            "raw_lineup_gap_count_events_missing_nonempty_df_li": raw_li_gap,
            "footnote": (
                "football-data + openfootball supply results/some aggregates; neither replaces df_li XI."
            ),
        },
        "lineup_gap_breakdown": {
            "missing_df_li_and_raw_df_st_present": li_gap_has_st,
            "missing_df_li_and_missing_raw_df_st": li_gap_no_st,
            "sums_to_raw_gap_missing_df_li": raw_li_gap == li_gap_has_st + li_gap_no_st,
            "cli_for_lineups": (
                "python scripts/data_integrity_flashscore.py --repair --repair-feeds li "
                "(or scripts/backfill_lineups.py)."
            ),
        },
        "raw_backfill_and_repair_hints": {
            "full_manifest_flashscore_raw_repair": (
                "python scripts/data_integrity_flashscore.py --repair          # df_sui + df_st + df_li gaps"
            ),
            "subset_lineups_only": (
                "python scripts/data_integrity_flashscore.py --repair --repair-feeds li "
                "# lineup gaps only"
            ),
            "subset_stats_only": (
                "python scripts/data_integrity_flashscore.py --repair --repair-feeds st"
            ),
            "subset_sui_only": (
                "python scripts/data_integrity_flashscore.py --repair --repair-feeds sui"
            ),
            "script_backfill_li_convenience": "python scripts/backfill_lineups.py  # delegates to filtered repair(li)",
            "df_li_legacy_cli": (
                "python -m football_ai backfill-flashscore-lineups (single IDS file + out-subdir)."
            ),
            "df_st": (
                "Use full --repair or --repair-feeds st; Flashscore supplement never replaces df_st."
            ),
            "fixture_uid_migration_note": (
                "After pulling new writers, python scripts/migrate_supplement_fixture_uid.py "
                "(creates dated .bak + fills fixture_uid on legacy rows)."
            ),
            "note": "Repair does not guarantee non-empty upstream responses — compare gap-stats before vs after.",
        },
        "three_source_coverage_note": (
            "Flashscore RAW + football-data supplement + OpenFootball UEFA text cover different fields; "
            "full stat/XI parity requires complete df_* RAW plus successful joins (see metrics above)."
        ),
        "integration_pipeline_hint": (
            "UEFA/OpenFootball merge needs AA÷ meta for each IDS event_id; global mega f_1_-1_* often omits UEFA CL/EL. "
            "Run scripts/download_flashscore_uefa_results_seeds.py → data/raw/flashscore/seed_results/*_wyniki.html "
            "(embedded AA rows from /wyniki/ pages), plus optional manifest feed keys, slice_flashscore_list_feed.py, "
            "or capture list-feed via football_ai download-flashscore-from-feed into feeds/. "
            "OpenFootball plaintext may list fewer fixtures than IDS; see openfootball_uefa_overlay ratios. "
            "Each download_openfootball allowlist run writes data/integrated/openfootball_source_status.json "
            "(urls_tried, url_resolved optional, unavailable vs ok). Fallback URLs: "
            "data/integrated/openfootball_url_fallbacks.json (by github season_folder and kind)."
            "After merge, classify remaining gaps with scripts/download_openfootball_allowlist.py "
            "--openfoot-miss-report data/integrated/openfootball_miss_latest.json "
            "(prints openfoot_no_hit_breakdown). "
            "Scripts: download_flashscore_integration_feeds.py, build_integration_supplement.py, "
            "download_openfootball_allowlist.py."
        ),
        "openfootball_plaintext_upstream": _load_openfootball_upstream_status(),
        "openfootball_uefa_overlay": _openfootball_uefa_overlay(db_path),
        "football_data_manifest_bridge": _football_data_manifest_bridge_stats(),
        "football_data_integration_scope": {
            "included_in_build_integration_supplement": (
                "domestic leagues mapped in join_football_data.LEAG_KEY_TO_CLI plus "
                "Poland Ekstraklasa POL aggregation plus optional leagues in "
                "data/integrated/football_data_manifest_mmz_overlay.json (MMZ filename stem)"
            ),
            "excluded": (
                "UEFA (liga_* manifest keys): no bundled football-data MMZ analogue; overlays may still target cups "
                "via the JSON map after manual URL validation."
            ),
        },
        "supplement_match_identity": _supplement_identity_stats(db_path),
        "domestic_cups_seed_html_and_raw_fractions": _domestic_cups_augment_metrics(),
        "fa_cup_carabao_jalapic_index_snapshot": _jalapic_fa_carabao_bridge_by_dataset(),
    }
    out.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
