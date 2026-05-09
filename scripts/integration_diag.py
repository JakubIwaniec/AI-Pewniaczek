"""Phase-1 integration diagnostics: meta kickoff gaps, supplement join scope, RAW forensics.

Writes ``data/integrated/integration_diag_latest.json``. JSON uses ``schema_version`` ``"4"`` and:

- ``skipped_no_meta_by_dataset``: per ``dataset_label`` with join-scope CSV —
  ``missing_meta`` (aligned with aggregate ``supplement_counters.skipped_no_meta``),
  ``in_join_scope_events``, and ``share`` (ratio, or JSON ``null`` if denominator zero).

When Football-Data lookups miss despite a valid unix on an in-scope IDS event, annotates extras:

- ``lookup_miss_sample_meta`` — sampling metadata (population cap, seed, wide radius ``R``, flags).
- ``lookup_miss_diagnosis_sample`` — per-row ``diagnose_fd_row_miss`` for a stratified sample.
- ``lookup_miss_category_histogram_sample`` — counts from that sample.

With ``--lookup-miss-classify-full-population`` (``-F``), also writes
``lookup_miss_category_histogram_population`` and ``lookup_miss_category_histogram_by_dataset``
after classifying every pooled miss.

``diagnose_fd_row_miss`` uses production ±1-day logic first; the wide scan only considers offsets
``k \\in [-R, R] \\ {-1, 0, 1}``. If ``R < 2``, wide scan is skipped (see diagnostics on each row).

Usage (repo root):
  python scripts/integration_diag.py
  python scripts/integration_diag.py --footballcsv-cache-fallback

Lookup-miss probes (defaults: sample cap 200, seed 42, wide radius ``R``=7):

  python scripts/integration_diag.py -n 500 --lookup-miss-sample-seed 0
  python scripts/integration_diag.py --skip-lookup-miss-sample       # telemetry only / no sampling
  python scripts/integration_diag.py -F                               # classify full population
  python scripts/integration_diag.py --lm-wide-days 14                # synonym: ``-R 14``

Flags (aliases):

- ``--lookup-miss-sample-size`` | ``--lm-sample`` | ``-n`` — stratified sample size cap (default cap
  inside ``run_diag`` if omitted).
- ``--lookup-miss-sample-seed`` | ``--lm-seed`` — RNG seed for stratified shuffle.
- ``--skip-lookup-miss-sample`` | ``--no-lm-sample`` — omit sample rows and sample histogram (``-F``
  still emits population histogram when pool non-empty).
- ``-F`` | ``--lookup-miss-classify-full-population`` | ``--lm-classify-all`` — full taxonomy over
  the lookup_miss pool.
- ``--lookup-miss-diagnostic-radius-days`` | ``--lm-wide-days`` | ``-R`` — wide-window radius ``R``.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import data_integrity_flashscore as di  # noqa: E402

from football_ai.cli import FOOTBALL_DATA_LEAGUES  # noqa: E402
from football_ai.integration.flashscore_event_meta import (  # noqa: E402
    load_flashscore_event_meta_bundle,
)
from football_ai.integration.join_football_data import (  # noqa: E402
    LEAG_KEY_TO_CLI,
    cache_footballdata_mirror_csv_path,
    cli_key_to_mmz_csv,
    diagnose_fd_row_miss,
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
from football_ai.paths import get_paths  # noqa: E402

OUTPUT_DEFAULT = ROOT / "data" / "integrated" / "integration_diag_latest.json"
DEFAULT_LM_SAMPLE_SIZE = 200
DEFAULT_LM_SEED = 42
_KICKOFF_OK_THRESHOLD = 1_000_000_000
_FORENSICS_MAX_BYTES = 65_536
_FORENSICS_TARGET_SAMPLES = 8


def split_dataset(ds: str) -> tuple[str, str]:
    i = ds.rfind("-")
    return ds[:i], ds[i + 1 :]


def _kickoff_ok(u: int | None) -> bool:
    return u is not None and u > _KICKOFF_OK_THRESHOLD


def _git_rev_short() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def _sniff_raw_bytes(blob: bytes) -> dict[str, object]:
    latin_px = ("\xac" + "PX" + "\xf7").encode("latin-1")
    utf8_px = ("¬" + "PX" + "÷").encode("utf-8")
    return {
        "byte_len_scanned": len(blob),
        "has_tilde_aa": b"~AA" in blob,
        "has_marker_px_latin1": latin_px in blob,
        "has_marker_px_utf8": utf8_px in blob,
    }


def _baseline_bottleneck_hint(blob: dict[str, object]) -> str:
    tot = int(blob.get("ids_total_manifest_events") or 0)
    never = int(blob.get("ids_never_attempted_join") or 0)
    sc_raw = blob.get("supplement_counters")
    snm = 0
    snr = 0
    if isinstance(sc_raw, dict):
        snm = int(sc_raw.get("skipped_no_meta") or 0)
        snr = int(sc_raw.get("skipped_no_row_build_semantics") or 0)
    if tot <= 0:
        return "Brak wydarzeń w plikach IDS z manifestu — sprawdź data/event_ids."
    parts = []
    if never > 0:
        pct = 100.0 * never / tot
        parts.append(f"nigdy próby join: {never}/{tot} ({pct:.1f}%) — zakres CSV/unsupported")
    if snm > 0:
        parts.append(f"w scope join brak wpisu meta_ix: skipped_no_meta={snm}")
    if snr > 0:
        parts.append(f"meta jest, brak dopasowania CSV: skipped_no_row~={snr}")
    return "; ".join(parts) if parts else "Baseline OK pod kątem głównych liczników — uzupełnij X/Y w TARGET_SPEC."


def stratified_sample_lookup_miss_pool(pool: list[dict], cap: int, rng: random.Random) -> list[dict]:
    """Proportional quotas + largest remainder; zero-count labels omitted."""
    if not pool or cap <= 0:
        return []
    cap = min(cap, len(pool))
    by_lab: defaultdict[str, list[dict]] = defaultdict(list)
    for rec in pool:
        by_lab[rec["dataset_label"]].append(rec)
    laps = sorted(lab for lab, rows in by_lab.items() if rows)
    if not laps:
        return []
    counts = {lab: len(by_lab[lab]) for lab in laps}
    total_mass = sum(counts.values())
    ideals = {lab: counts[lab] / total_mass * cap for lab in laps}
    quotas = {lab: int(math.floor(ideals[lab])) for lab in laps}
    leftover = cap - sum(quotas.values())
    for lab in sorted(laps, key=lambda lb: ideals[lb] - quotas[lb], reverse=True):
        if leftover <= 0:
            break
        quotas[lab] += 1
        leftover -= 1
    out: list[dict] = []
    for lab in laps:
        rows = list(by_lab[lab])
        rng.shuffle(rows)
        nt = min(quotas.get(lab, 0), len(rows))
        out.extend(rows[:nt])
    rng.shuffle(out)
    return out


def run_diag(
    *,
    fb_cache_mirror: bool,
    lookup_miss_sample_size: int | None = None,
    lookup_miss_seed: int | None = None,
    skip_lookup_miss_sample: bool = False,
    lookup_miss_classify_full_population: bool = False,
    lookup_miss_diagnostic_radius_days: int = 7,
) -> dict[str, object]:
    lm_cap = DEFAULT_LM_SAMPLE_SIZE if lookup_miss_sample_size is None else lookup_miss_sample_size
    lm_rng_seed = DEFAULT_LM_SEED if lookup_miss_seed is None else lookup_miss_seed
    lookup_miss_pool: list[dict[str, Any]] = []

    paths = get_paths()
    bundle = load_flashscore_event_meta_bundle(
        repo_root=ROOT,
        raw_flashscore_dir=paths.raw_dir / "flashscore",
    )
    meta_ix = bundle.index

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
            csv_cache[ck] = None
            return None
        try:
            sy = season_four_to_engsoccer_start_year(season4)
        except ValueError:
            csv_cache[ck] = None
            return None
        ix = engsoccerdata_cup_index(p, season_start_year=sy, cup=cup_kind)
        if not ix.key_to_rows and ck not in esd_empty_warned:
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

    kickoff_by_dataset: dict[str, dict[str, int]] = defaultdict(
        lambda: {"absent_key": 0, "present_no_valid_unix": 0, "present_unix_ok": 0}
    )

    skipped_no_meta = 0
    in_join_scope_events_by_ds: defaultdict[str, int] = defaultdict(int)
    missing_meta_by_ds: defaultdict[str, int] = defaultdict(int)
    meta_no_valid_unix_in_scope = 0
    lookup_miss_with_valid_unix = 0
    join_would_succeed = 0
    ids_never_attempted_join = 0
    ids_total_manifest_events = 0
    ids_in_join_scope = 0
    never_attempted_dataset_labels: set[str] = set()

    league_rows: list[dict[str, object]] = []
    forensics_samples: list[dict[str, object]] = []

    def try_forensics(rel_path: str, blob: bytes) -> None:
        if len(forensics_samples) >= _FORENSICS_TARGET_SAMPLES:
            return
        forensics_samples.append(
            {
                "sample_path_relative": rel_path.replace("\\", "/"),
                "first_bytes_hex": blob[:24].hex() if blob else "",
                **_sniff_raw_bytes(blob),
            }
        )

    for dlabel, ids_name, base in di.league_manifest():
        ids_path = di.IDS / f"{ids_name}.txt"
        if not ids_path.is_file():
            league_rows.append(
                {
                    "dataset_label": dlabel,
                    "ids_name": ids_name,
                    "ids_file": "missing",
                    "ids_event_count": 0,
                    "join_scope": "no_ids_file",
                    "join_detail": None,
                }
            )
            continue

        eids = [ln.strip() for ln in ids_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        n_e = len(eids)
        ids_total_manifest_events += n_e

        leigh_key, season4 = split_dataset(dlabel)
        idx_obj: object | None
        cli = ""
        div_code = ""
        join_scope = ""
        join_detail: str | None = None

        if leigh_key == "ekstraklasa":
            idx_obj = pol_idx(season4)
            cli = "POL_AGG"
            join_scope = "ekstraklasa_pol_agg"
            if not pol_path.exists():
                join_detail = "pol_csv_missing"
        elif leigh_key in LEAG_KEY_TO_CLI:
            idx_obj = csv_idx(LEAG_KEY_TO_CLI[leigh_key], season4)
            lk = LEAG_KEY_TO_CLI[leigh_key]
            cli = lk
            div_code = FOOTBALL_DATA_LEAGUES[lk].code
            join_scope = "leag_key_to_cli"
            ck_b = f"{lk}:{season4}"
            join_detail = csv_bridge_origin.get(ck_b)
        elif leigh_key in mmz_overlay:
            ocode = mmz_overlay[leigh_key]
            idx_obj = csv_idx_overlay(ocode, season4)
            cli = "MMZ_OVERLAY"
            div_code = ocode
            join_scope = "mmz_overlay"
            ck_b = f"ov:{ocode}:{season4}"
            join_detail = csv_bridge_origin.get(ck_b)
        elif leigh_key == "fa_cup":
            idx_obj = esd_cup_idx("fa_cup", season4, "facup")
            cli = "ENGSD"
            div_code = "FACUP"
            join_scope = "engsoccerdata_facup"
        elif leigh_key == "carabao_cup":
            idx_obj = esd_cup_idx("carabao_cup", season4, "leaguecup")
            cli = "ENGSD"
            div_code = "CARABAO"
            join_scope = "engsoccerdata_leaguecup"
        else:
            ids_never_attempted_join += n_e
            never_attempted_dataset_labels.add(dlabel)
            league_rows.append(
                {
                    "dataset_label": dlabel,
                    "ids_name": ids_name,
                    "ids_file": "present",
                    "ids_event_count": n_e,
                    "join_scope": "unsupported_league_key",
                    "join_detail": leigh_key,
                }
            )
            for eid in eids:
                if eid not in meta_ix:
                    kickoff_by_dataset[dlabel]["absent_key"] += 1
                elif not _kickoff_ok(meta_ix[eid].unix_kickoff):
                    kickoff_by_dataset[dlabel]["present_no_valid_unix"] += 1
                else:
                    kickoff_by_dataset[dlabel]["present_unix_ok"] += 1
            continue

        if idx_obj is None:
            ids_never_attempted_join += n_e
            never_attempted_dataset_labels.add(dlabel)
            league_rows.append(
                {
                    "dataset_label": dlabel,
                    "ids_name": ids_name,
                    "ids_file": "present",
                    "ids_event_count": n_e,
                    "join_scope": join_scope,
                    "join_detail": join_detail or "csv_index_unavailable",
                    "cli": cli or None,
                }
            )
            for eid in eids:
                if eid not in meta_ix:
                    kickoff_by_dataset[dlabel]["absent_key"] += 1
                elif not _kickoff_ok(meta_ix[eid].unix_kickoff):
                    kickoff_by_dataset[dlabel]["present_no_valid_unix"] += 1
                else:
                    kickoff_by_dataset[dlabel]["present_unix_ok"] += 1
            continue

        ids_in_join_scope += n_e
        in_join_scope_events_by_ds[dlabel] += n_e
        league_rows.append(
            {
                "dataset_label": dlabel,
                "ids_name": ids_name,
                "ids_file": "present",
                "ids_event_count": n_e,
                "join_scope": join_scope,
                "join_detail": join_detail,
                "cli": cli or None,
                "division": div_code or None,
            }
        )

        for eid in eids:
            meta = meta_ix.get(eid)
            if meta is None:
                skipped_no_meta += 1
                missing_meta_by_ds[dlabel] += 1
                kickoff_by_dataset[dlabel]["absent_key"] += 1
                continue
            if not _kickoff_ok(meta.unix_kickoff):
                meta_no_valid_unix_in_scope += 1
                kickoff_by_dataset[dlabel]["present_no_valid_unix"] += 1
            else:
                kickoff_by_dataset[dlabel]["present_unix_ok"] += 1

            row = lookup_fd_row(
                idx_obj,
                unix_ts=meta.unix_kickoff,
                nh=meta.home_team,
                na=meta.away_team,
            )
            if row is None:
                if _kickoff_ok(meta.unix_kickoff):
                    lookup_miss_with_valid_unix += 1
                    lookup_miss_pool.append(
                        {
                            "dataset_label": dlabel,
                            "event_id": eid,
                            "unix_kickoff": meta.unix_kickoff,
                            "home_team": meta.home_team,
                            "away_team": meta.away_team,
                            "_idx": idx_obj,
                        }
                    )
            else:
                join_would_succeed += 1

            # Forensics: first available df_st / df_li under base
            if len(forensics_samples) < _FORENSICS_TARGET_SAMPLES:
                for suf in ("df_st_1", "df_li_1"):
                    rel = base / eid / f"{suf}_{eid}.txt"
                    if rel.is_file() and rel.stat().st_size > 0:
                        try:
                            blob = rel.read_bytes()[:_FORENSICS_MAX_BYTES]
                        except OSError:
                            break
                        try:
                            rel_to_root = str(rel.resolve().relative_to(ROOT.resolve()))
                        except ValueError:
                            rel_to_root = str(rel)
                        try_forensics(rel_to_root, blob)
                        break

    global_kick = {"absent_key": 0, "present_no_valid_unix": 0, "present_unix_ok": 0}
    for bucket in kickoff_by_dataset.values():
        for k, v in bucket.items():
            global_kick[k] += v

    skipped_no_row_build_semantics = meta_no_valid_unix_in_scope + lookup_miss_with_valid_unix

    skipped_no_meta_by_ds_out: dict[str, dict[str, float | int | None]] = {}
    for dsl in sorted(in_join_scope_events_by_ds.keys()):
        denom = int(in_join_scope_events_by_ds[dsl])
        miss_ds = int(missing_meta_by_ds.get(dsl, 0))
        skipped_no_meta_by_ds_out[dsl] = {
            "missing_meta": miss_ds,
            "in_join_scope_events": denom,
            "share": (miss_ds / denom) if denom > 0 else None,
        }

    population_lookup_miss = len(lookup_miss_pool)
    rng_lm = random.Random(lm_rng_seed)
    classify_cache: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}

    def _classify_lm(rec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        key_t = rec["dataset_label"], rec["event_id"]
        if key_t not in classify_cache:
            ix = rec["_idx"]
            cat_lm, diag_ex_lm = diagnose_fd_row_miss(
                ix,
                unix_ts=rec["unix_kickoff"],
                nh=rec["home_team"],
                na=rec["away_team"],
                diagnostic_radius_days=lookup_miss_diagnostic_radius_days,
            )
            classify_cache[key_t] = (cat_lm, diag_ex_lm)
        return classify_cache[key_t]

    hist_pop: Counter[str] = Counter()
    hist_pop_by_ds: defaultdict[str, Counter[str]] = defaultdict(Counter)
    hist_sample_ct: Counter[str] = Counter()
    lm_diag_sample: list[dict[str, Any]] = []

    if lookup_miss_classify_full_population and lookup_miss_pool:
        for rec_lm in lookup_miss_pool:
            c_lm, _ = _classify_lm(rec_lm)
            hist_pop[c_lm] += 1
            hist_pop_by_ds[rec_lm["dataset_label"]][c_lm] += 1

    sampled_lm: list[dict[str, Any]] = []
    if lookup_miss_pool and not skip_lookup_miss_sample:
        sampled_lm = stratified_sample_lookup_miss_pool(lookup_miss_pool, lm_cap, rng_lm)
        for rec_lm in sampled_lm:
            c_lm, dex_lm = _classify_lm(rec_lm)
            hist_sample_ct[c_lm] += 1
            pub = {
                "event_id": rec_lm["event_id"],
                "dataset_label": rec_lm["dataset_label"],
                "unix_kickoff": rec_lm["unix_kickoff"],
                "category": c_lm,
            }
            pub.update(dex_lm)
            lm_diag_sample.append(pub)

    lm_extra: dict[str, object] = {}
    if population_lookup_miss > 0:
        lm_extra["lookup_miss_sample_meta"] = {
            "preset": "lookup_miss_valid_unix",
            "population": population_lookup_miss,
            "sample_size": len(sampled_lm),
            "seed": lm_rng_seed,
            "stratification": "proportional_largest_remainder",
            "diagnostic_wide_radius_days": lookup_miss_diagnostic_radius_days,
            "sampling_skipped": skip_lookup_miss_sample,
            "classified_full_population": lookup_miss_classify_full_population,
            "taxonomy_reference": (
                "diagnose_fd_row_miss in football_ai.integration.join_football_data "
                "(wide uses k∈[-R,R] excluding {-1,0,1})"
            ),
        }
        lm_extra["lookup_miss_diagnosis_sample"] = lm_diag_sample
        lm_extra["lookup_miss_category_histogram_sample"] = dict(sorted(hist_sample_ct.items()))
        if lookup_miss_classify_full_population and hist_pop:
            lm_extra["lookup_miss_category_histogram_population"] = dict(sorted(hist_pop.items()))
            lm_extra["lookup_miss_category_histogram_by_dataset"] = {
                ds_lab: dict(sorted(ct.items())) for ds_lab, ct in sorted(hist_pop_by_ds.items())
            }

    out = {
        "schema_version": "4",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_rev_short": _git_rev_short(),
        "options": {
            "footballcsv_cache_fallback": fb_cache_mirror,
            "lookup_miss_sample_size": lm_cap,
            "lookup_miss_seed": lm_rng_seed,
            "skip_lookup_miss_sample": skip_lookup_miss_sample,
            "lookup_miss_classify_full_population": lookup_miss_classify_full_population,
            "lookup_miss_diagnostic_radius_days": lookup_miss_diagnostic_radius_days,
        },
        "meta_fingerprint_summary": {
            "feed_note": bundle.feed_note,
            "augment_seed_count": bundle.augment_seed_count,
            "feeds_used_count": len(bundle.feeds_used_paths),
            "meta_index_size": len(meta_ix),
        },
        "ids_total_manifest_events": ids_total_manifest_events,
        "ids_in_join_scope": ids_in_join_scope,
        "ids_never_attempted_join": ids_never_attempted_join,
        "supplement_counters": {
            "skipped_no_meta": skipped_no_meta,
            "skipped_no_row": skipped_no_row_build_semantics,
            "skipped_no_row_build_semantics": skipped_no_row_build_semantics,
            "breakdown_in_scope": {
                "meta_no_valid_unix_attempted_lookup": meta_no_valid_unix_in_scope,
                "lookup_miss_given_valid_unix": lookup_miss_with_valid_unix,
            },
            "join_would_succeed_count": join_would_succeed,
        },
        "meta_state_per_event_aggregate": dict(global_kick),
        "kickoff_aggregate_global": global_kick,
        "skipped_no_meta_by_dataset": skipped_no_meta_by_ds_out,
        "kickoff_histogram_by_dataset": {k: dict(v) for k, v in sorted(kickoff_by_dataset.items())},
        "league_join_scope_table": league_rows,
        "ids_never_attempted_dataset_labels": sorted(never_attempted_dataset_labels),
        "forensics_df_st_li": forensics_samples,
        "notes": (
            "skipped_no_row_build_semantics matches build_integration_supplement counter "
            "(meta present but lookup_fd_row returned None, including unix_ts is None)."
        ),
    }
    out.update(lm_extra)
    out["baseline_bottleneck_hint"] = _baseline_bottleneck_hint(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--footballcsv-cache-fallback",
        action="store_true",
        help="Same as supplement build: use footballcsv mirror when MMZ CSV missing.",
    )
    ap.add_argument(
        "--lookup-miss-sample-size",
        "--lm-sample",
        "-n",
        type=int,
        default=None,
        help=f"Caps lookup_miss stratified sample (default {DEFAULT_LM_SAMPLE_SIZE} if omitted).",
    )
    ap.add_argument(
        "--lookup-miss-sample-seed",
        "--lm-seed",
        type=int,
        default=None,
        help=f"RNG seed for sampling (default {DEFAULT_LM_SEED} if omitted).",
    )
    ap.add_argument(
        "--skip-lookup-miss-sample",
        "--no-lm-sample",
        action="store_true",
        help="Skip sample + sample histogram (-F still builds population histogram).",
    )
    ap.add_argument(
        "-F",
        "--lookup-miss-classify-full-population",
        "--lm-classify-all",
        action="store_true",
        dest="lookup_miss_classify_full_population",
        help="Full lookup_miss taxonomy counts (writes lookup_miss_category_histogram_population).",
    )
    ap.add_argument(
        "--lookup-miss-diagnostic-radius-days",
        "--lm-wide-days",
        "-R",
        type=int,
        default=7,
        metavar="R",
        help="Wide-window radius R (diagnose_fd_row_miss); excludes ±1 prod days.",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DEFAULT,
        help="Write JSON diagnostics here",
    )
    args = ap.parse_args()

    blob = run_diag(
        fb_cache_mirror=args.footballcsv_cache_fallback,
        lookup_miss_sample_size=args.lookup_miss_sample_size,
        lookup_miss_seed=args.lookup_miss_sample_seed,
        skip_lookup_miss_sample=args.skip_lookup_miss_sample,
        lookup_miss_classify_full_population=args.lookup_miss_classify_full_population,
        lookup_miss_diagnostic_radius_days=args.lookup_miss_diagnostic_radius_days,
    )
    out_path = args.output.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}", flush=True)
    sc = blob["supplement_counters"]
    print(
        f"ids_total={blob['ids_total_manifest_events']} never_attempt_join={blob['ids_never_attempted_join']} "
        f"in_scope={blob['ids_in_join_scope']} skipped_no_meta={sc['skipped_no_meta']} "
        f"skipped_no_row={sc['skipped_no_row']} would_join={sc['join_would_succeed_count']}",
        flush=True,
    )
    gk = blob["kickoff_aggregate_global"]
    print(
        f"meta_kick kickoff_aggregate: absent_key={gk['absent_key']} "
        f"no_valid_unix={gk['present_no_valid_unix']} unix_ok={gk['present_unix_ok']}",
        flush=True,
    )
    lmm = blob.get("lookup_miss_sample_meta")
    if isinstance(lmm, dict):
        h = blob.get("lookup_miss_category_histogram_sample")
        hp = blob.get("lookup_miss_category_histogram_population")
        hbd = blob.get("lookup_miss_category_histogram_by_dataset")
        hbd_note = ""
        if isinstance(hbd, dict):
            hbd_note = f" datasets={len(hbd)}"
        print(
            "lookup_miss: "
            f"population={lmm.get('population')} sample_size={lmm.get('sample_size')} "
            f"hist_sample={h or {}} hist_pop={hp}{hbd_note}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
