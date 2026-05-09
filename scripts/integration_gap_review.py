"""Operational summary from integration_diag_latest.json (data gap protocol).

Aligns with docs/DATA_GAP_PROTOCOL.md Etap 1–2: replay snapshot, join-scope exclusions,
Tier-1 style meta-gap ranking, lookup_miss totals per dataset.

Usage (repo root):
  python scripts/integration_gap_review.py
  python scripts/integration_gap_review.py --diag-json path/to/integration_diag_latest.json

Does not regenerate the JSON — run scripts/integration_diag.py first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAG = ROOT / "data" / "integrated" / "integration_diag_latest.json"

_TIER1_MIN_N_DEFAULT = 50
_TIER1_MIN_SHARE_DEFAULT = 0.2
_TIER1_TOP_DEFAULT = 12

_PROBLEM_SCOPES = frozenset(
    {
        "no_ids_file",
        "unsupported_league_key",
    }
)


def _intish(x: Any) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def _floatish_share(rec: dict[str, Any]) -> float:
    s = rec.get("share")
    if s is None:
        return 0.0
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _lookup_miss_totals(blob: dict[str, Any]) -> dict[str, int]:
    hbd = blob.get("lookup_miss_category_histogram_by_dataset")
    if not isinstance(hbd, dict):
        return {}
    out: dict[str, int] = {}
    for lab, buckets in hbd.items():
        if not isinstance(lab, str) or not isinstance(buckets, dict):
            continue
        out[lab] = sum(int(v) for v in buckets.values() if isinstance(v, (int, float)))
    return out


def _problem_join_rows(table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in table:
        scope = row.get("join_scope")
        jd = row.get("join_detail")
        if isinstance(scope, str) and scope in _PROBLEM_SCOPES:
            out.append(row)
            continue
        if row.get("ids_file") == "missing":
            out.append(row)
            continue
        if jd in ("csv_index_unavailable", "missing", "pol_csv_missing"):
            out.append(row)
    return sorted(out, key=lambda r: -_intish(r.get("ids_event_count")))


def tier1_candidates(
    skipped_by_ds: dict[str, Any],
    *,
    min_n: int,
    min_share: float,
    top_k: int,
) -> list[tuple[str, int, int, float]]:
    """Return (dataset_label, missing_meta, in_join_scope_events, share)."""
    pool: list[tuple[int, str, int, float]] = []
    for lab, raw in skipped_by_ds.items():
        if not isinstance(lab, str) or not isinstance(raw, dict):
            continue
        ins = _intish(raw.get("in_join_scope_events"))
        miss = _intish(raw.get("missing_meta"))
        shr = _floatish_share(raw)
        if ins < min_n or shr + 1e-12 < min_share:
            continue
        pool.append((miss, lab, ins, shr))
    pool.sort(key=lambda x: (-x[0], x[1]))
    return [(lab, miss, ins, shr) for miss, lab, ins, shr in pool[:top_k]]


def summarize_blob(blob: dict[str, Any], *, tier1_top: int, tier1_min_n: int, tier1_min_share: float) -> str:
    lines: list[str] = []
    lines.append("=== integration_gap_review (diag JSON snapshot) ===\n")

    replay = [
        f"generated_at={blob.get('generated_at')!r}",
        f"git_rev_short={blob.get('git_rev_short')!r}",
        f"schema_version={blob.get('schema_version')!r}",
    ]
    opts = blob.get("options")
    if isinstance(opts, dict):
        replay.append(
            "options: "
            f"footballcsv_cache_fallback={opts.get('footballcsv_cache_fallback')!r} "
            f"lookup_miss_classify_full_population={opts.get('lookup_miss_classify_full_population')!r} "
            f"skip_lookup_miss_sample={opts.get('skip_lookup_miss_sample')!r}"
        )
        if opts.get("skip_lookup_miss_sample"):
            lines.append("[note] regressja: lookup_miss_diagnosis_sample expected empty/skipped semantics")
        elif opts.get("lookup_miss_classify_full_population"):
            lines.append("[note] RCA-friendly: sprawdź lookup_miss_diagnosis_sample przy pool > 0")
    lines.extend(replay)

    totals = (
        f"ids_total_manifest_events={blob.get('ids_total_manifest_events')} "
        f"ids_in_join_scope={blob.get('ids_in_join_scope')} "
        f"ids_never_attempted_join={blob.get('ids_never_attempted_join')}"
    )
    lines.append("\n--- counts ---")
    lines.append(totals)
    sc = blob.get("supplement_counters")
    if isinstance(sc, dict):
        lines.append(
            f"skipped_no_meta={sc.get('skipped_no_meta')} "
            f"skipped_no_row={sc.get('skipped_no_row')} "
            f"join_would_succeed={sc.get('join_would_succeed_count')}"
        )
        bk = sc.get("breakdown_in_scope")
        if isinstance(bk, dict):
            lines.append(
                "breakdown_in_scope: "
                f"meta_no_valid_unix={bk.get('meta_no_valid_unix_attempted_lookup')} "
                f"lookup_miss_valid_unix={bk.get('lookup_miss_given_valid_unix')}"
            )

    lm_tot = _lookup_miss_totals(blob)
    lm_nonempty = [(lab, n) for lab, n in sorted(lm_tot.items(), key=lambda x: -x[1]) if n > 0]

    skipped_by_ds = blob.get("skipped_no_meta_by_dataset")
    lines.append("\n--- never_attempt_join spotlight (manifest rows) ---")
    table_raw = blob.get("league_join_scope_table")
    if isinstance(table_raw, list):
        problems = _problem_join_rows([r for r in table_raw if isinstance(r, dict)])
        if blob.get("ids_never_attempted_join", 0) and problems:
            lines.append(f"problematic league_join_scope rows (show up to {min(18, len(problems))}):")
            for row in problems[:18]:
                lines.append(
                    f"  {row.get('dataset_label')}: join_scope={row.get('join_scope')!r} "
                    f"detail={row.get('join_detail')!r} n_events={row.get('ids_event_count')} "
                    f"ids_file={row.get('ids_file')!r}"
                )
        elif not blob.get("ids_never_attempted_join"):
            lines.append("ids_never_attempted_join=0 - akcent na scope z join lub meta.")
        else:
            lines.append("(no parsed problem rows — inspect league_join_scope_table manually)")
    else:
        lines.append("(missing league_join_scope_table)")

    lines.append("\n--- Tier-1 style meta-gap (skipped_no_meta_by_dataset) ---")
    if isinstance(skipped_by_ds, dict) and skipped_by_ds:
        tier_rows = tier1_candidates(
            skipped_by_ds,
            min_n=tier1_min_n,
            min_share=tier1_min_share,
            top_k=tier1_top,
        )
        lines.append(
            f"criteria: in_join_scope_events>={tier1_min_n}, share>={tier1_min_share:.0%}, top {tier1_top} by missing_meta"
        )
        for lab, miss, ins, shr in tier_rows:
            lines.append(
                f"  {lab}: missing_meta={miss} share={shr:.4f} in_scope={ins} lookup_miss_N={lm_tot.get(lab, 0)}"
            )
        if not tier_rows:
            lines.append("(no datasets match thresholds — widen --tier1-* or rerun diag)")
    else:
        lines.append("(skipped_no_meta_by_dataset missing — rerun integration_diag schema 4+)")

    lines.append("\n--- CSV / lookup_miss signal per dataset (nonzero population) ---")
    if lm_nonempty:
        lines.append("(sum of lookup_miss histogram buckets)")
        for lab, n in lm_nonempty[:22]:
            hbd = blob.get("lookup_miss_category_histogram_by_dataset")
            detail = ""
            if isinstance(hbd, dict) and isinstance(hbd.get(lab), dict):
                detail = dict(sorted((hbd[lab]).items()))
            lines.append(f"  {lab}: total={n} hist={detail}")
        if len(lm_nonempty) > 22:
            lines.append(f"  ... {len(lm_nonempty) - 22} more")
    else:
        lines.append("(no histogram — run: python scripts/integration_diag.py -F [--skip|no-skip lookup sample])")

    hint = blob.get("baseline_bottleneck_hint")
    if isinstance(hint, str) and hint.strip():
        lines.append("\n--- baseline_bottleneck_hint ---")
        lines.append(hint.strip())

    lines.append("\n--- suggested next heuristic ---")
    n_never = _intish(blob.get("ids_never_attempted_join"))
    snm = _intish((blob.get("supplement_counters") or {}).get("skipped_no_meta"))
    tot = max(_intish(blob.get("ids_total_manifest_events")), 1)
    if n_never > tot // 10:
        lines.append("- Duży ids_never_attempted_join -> najpierw league_join_scope_table / ścieżki CSV lub unsupported keys.")
    if snm > 0:
        lines.append("- skipped_no_meta>0 -> pobieranie/slice/feeds lub augmentacja HTML (patrz DATA_GAP_PROTOCOL Etap A).")
    if lm_nonempty and all(x[0].startswith(("fa_cup", "carabao_cup")) or "cup" in x[0] for x in lm_nonempty[:5]):
        lines.append("- Dominują puchary w lookup_miss -> jalapic/MMZ/epik poza pobieraniem tego samego facup/leaguecup.")
    elif lm_nonempty:
        lines.append("- lookup_miss przy meta -> RCA diag bez skip próbki albo ścieżka mirror/MMZ/normalizacja nazw.")

    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--diag-json",
        type=Path,
        default=DEFAULT_DIAG,
        help="Path to integration_diag_latest.json",
    )
    p.add_argument("--tier1-top", type=int, default=_TIER1_TOP_DEFAULT)
    p.add_argument("--tier1-min-n", type=int, default=_TIER1_MIN_N_DEFAULT)
    p.add_argument("--tier1-min-share", type=float, default=_TIER1_MIN_SHARE_DEFAULT)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    path = args.diag_json if args.diag_json.is_absolute() else (ROOT / args.diag_json)
    path = path.resolve()
    if not path.is_file():
        print(f"No file: {path}", file=sys.stderr, flush=True)
        return 2
    try:
        blob = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        print(f"Invalid JSON {path}: {e}", file=sys.stderr, flush=True)
        return 2
    if not isinstance(blob, dict):
        print("diag JSON root must be an object", file=sys.stderr, flush=True)
        return 2

    txt = summarize_blob(
        blob,
        tier1_top=args.tier1_top,
        tier1_min_n=args.tier1_min_n,
        tier1_min_share=args.tier1_min_share,
    )
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    _ascii_arrows_dashes = str.maketrans(
        {
            "\u2192": "->",
            "\u2190": "<-",
            "\u2026": "...",
            "\u2014": "-",
            "\u2013": "-",
        }
    )
    print(txt.translate(_ascii_arrows_dashes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
