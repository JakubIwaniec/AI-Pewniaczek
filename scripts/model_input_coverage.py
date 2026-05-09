"""Weighted availability KPI for upstream model inputs (RAW Flashscore + meta + enrichment join).

Does not evaluate derived features (form, Elo, etc.). See ``metric_interpretation`` in JSON output."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import data_integrity_flashscore as di  # noqa: E402

from football_ai.integration.flashscore_event_meta import (  # noqa: E402
    load_flashscore_event_meta_bundle,
    meta_source_fingerprint,
)
from football_ai.paths import get_paths  # noqa: E402

DEFAULT_MANIFEST = ROOT / "data" / "integrated" / "model_input_coverage_manifest.json"
OUTPUT_DEFAULT = ROOT / "data" / "integrated" / "model_input_coverage_latest.json"

ALLOWED_PROBES = frozenset(
    {
        "flash_nonempty",
        "flash_contains_any",
        "flash_aa_field_key_any",
        "meta_has_kickoff",
        "supplement_any_fd_like_row",
        "supplement_bucket_hit",
        "always_true_in_manifest_iteration",
    }
)

SUPPLEMENT_BUCKET_NAMES = frozenset({"football_data_co_uk", "mirror", "engsoccerdata"})
MANIFEST_SOURCE_ORDER = ("football_data_co_uk", "mirror", "engsoccerdata")

FEED_SHORT_TO_SUFFIX = {"df_st": "df_st_1", "df_li": "df_li_1", "df_sui": "df_sui_1"}
_MIN_STRICT_BYTES = 512
_DEFAULT_PREFETCH_SCAN_CAP = 786_432

_AA_FIELD_KEY_RE = re.compile(r"^[A-Za-z0-9]{2,12}$")


@dataclass(frozen=True)
class SupplementBuckets:
    """Distinct (dataset_label, event_id) keys per supplement origin (see upsert_supplement_row source_tag)."""

    fd_plus_mirror_union: frozenset[tuple[str, str]]
    football_data_co_uk: frozenset[tuple[str, str]]
    mirror: frozenset[tuple[str, str]]
    esd: frozenset[tuple[str, str]]


EMPTY_SUP_BUCKETS = SupplementBuckets(frozenset(), frozenset(), frozenset(), frozenset())


def validate_manifest(blob: dict) -> list[dict]:
    if not isinstance(blob, dict):
        raise SystemExit("manifest root must be a JSON object")
    sv = str(blob.get("schema_version", "")).strip()
    if sv != "1":
        raise SystemExit(f"unsupported schema_version: {sv!r} (need '1')")
    slots_obj = blob.get("slots")
    if not isinstance(slots_obj, list) or not slots_obj:
        raise SystemExit("manifest.slots must be a non-empty array")
    for raw in slots_obj:
        if not isinstance(raw, dict):
            raise SystemExit("each slot must be object")
        sid = str(raw.get("id") or "").strip()
        if not sid:
            raise SystemExit("slot missing id")
        probe = str(raw.get("probe") or "").strip()
        if probe not in ALLOWED_PROBES:
            raise SystemExit(f"{sid}: unknown probe {probe!r}")
        w = float(raw.get("weight", 0))
        if w < 0:
            raise SystemExit(f"{sid}: negative weight")
        ctc = str(raw.get("counts_toward_coverage") or "").strip()
        if ctc == "informational" and w != 0.0:
            raise SystemExit(f"{sid}: informational slot must use weight 0")
        probe_args = raw.get("probe_args")
        if probe_args is not None and not isinstance(probe_args, dict):
            raise SystemExit(f"{sid}: probe_args must be object or absent")
        if probe == "flash_nonempty":
            key = str((probe_args or {}).get("feed_suffix") or "").strip()
            if key not in FEED_SHORT_TO_SUFFIX:
                raise SystemExit(
                    f"{sid}: flash_nonempty needs probe_args.feed_suffix in {sorted(FEED_SHORT_TO_SUFFIX)}"
                )
        if probe == "flash_contains_any":
            key = str((probe_args or {}).get("feed_suffix") or "").strip()
            if key not in FEED_SHORT_TO_SUFFIX:
                raise SystemExit(
                    f"{sid}: flash_contains_any feed_suffix must be one of {sorted(FEED_SHORT_TO_SUFFIX)}"
                )
            raw_subs = (probe_args or {}).get("substrings")
            if not isinstance(raw_subs, list) or not raw_subs:
                raise SystemExit(f"{sid}: flash_contains_any needs non-empty probe_args.substrings array")
            if len(raw_subs) > 48:
                raise SystemExit(f"{sid}: flash_contains_any substrings overflow (max 48)")
            for i, raw in enumerate(raw_subs):
                s = str(raw).strip()
                if len(s) < 2 or len(s) > 200:
                    raise SystemExit(f"{sid}: substrings[{i}] length must be between 2 and 200 chars")
            pargs_norm = probe_args or {}
            mxb = pargs_norm.get("max_scan_bytes")
            if mxb is not None:
                try:
                    mxi = int(mxb)
                except (TypeError, ValueError):
                    raise SystemExit(f"{sid}: max_scan_bytes must be integer")
                if not (4096 <= mxi <= 8_388_608):
                    raise SystemExit(f"{sid}: max_scan_bytes must be within [4096, 8388608]")
        if probe == "flash_aa_field_key_any":
            key = str((probe_args or {}).get("feed_suffix") or "").strip()
            if key not in FEED_SHORT_TO_SUFFIX:
                raise SystemExit(
                    f"{sid}: flash_aa_field_key_any feed_suffix must be one of {sorted(FEED_SHORT_TO_SUFFIX)}"
                )
            raw_keys = (probe_args or {}).get("field_keys")
            if not isinstance(raw_keys, list) or not raw_keys:
                raise SystemExit(f"{sid}: flash_aa_field_key_any needs non-empty probe_args.field_keys array")
            if len(raw_keys) > 32:
                raise SystemExit(f"{sid}: flash_aa_field_key_any field_keys overflow (max 32)")
            for i, rk in enumerate(raw_keys):
                s = str(rk).strip()
                if not _AA_FIELD_KEY_RE.match(s):
                    raise SystemExit(
                        f"{sid}: field_keys[{i}] must be ASCII alnum, length between 2 and 12 chars"
                    )
            mp = str((probe_args or {}).get("match_policy", "any")).strip().lower()
            if mp not in {"any", "all"}:
                raise SystemExit(f'{sid}: match_policy must be "any" or "all"')
            pargs_aa = probe_args or {}
            mxb = pargs_aa.get("max_scan_bytes")
            if mxb is not None:
                try:
                    mxi = int(mxb)
                except (TypeError, ValueError):
                    raise SystemExit(f"{sid}: max_scan_bytes must be integer")
                if not (4096 <= mxi <= 8_388_608):
                    raise SystemExit(f"{sid}: max_scan_bytes must be within [4096, 8388608]")
        if probe == "supplement_bucket_hit":
            bk = str((probe_args or {}).get("bucket") or "").strip()
            if bk not in SUPPLEMENT_BUCKET_NAMES:
                raise SystemExit(
                    f"{sid}: supplement_bucket_hit bucket must be one of {sorted(SUPPLEMENT_BUCKET_NAMES)}"
                )
    return slots_obj


def flash_feed_path(match_dir: Path, eid: str, short: str) -> Path:
    suf = FEED_SHORT_TO_SUFFIX[short]
    return match_dir / eid / f"{suf}_{eid}.txt"


def clamp_scan_cap(mxb_raw: object | None) -> int:
    cap = _DEFAULT_PREFETCH_SCAN_CAP if mxb_raw is None else int(mxb_raw)
    return max(4096, min(cap, 8_388_608))


def max_scan_caps_by_suffix(slots: list[dict]) -> dict[str, int]:
    caps: dict[str, int] = {}
    probes_scan = frozenset({"flash_contains_any", "flash_aa_field_key_any"})
    for s in slots:
        probe = str(s.get("probe") or "")
        if probe not in probes_scan:
            continue
        args = s.get("probe_args") if isinstance(s.get("probe_args"), dict) else {}
        short = str(args.get("feed_suffix") or "").strip()
        if short not in FEED_SHORT_TO_SUFFIX:
            continue
        cap = clamp_scan_cap(args.get("max_scan_bytes"))
        caps[short] = max(caps.get(short, 0), cap)
    return caps


def read_feed_prefixed_bytes(match_dir: Path, eid: str, feed_short: str, cap: int) -> bytes:
    p = flash_feed_path(match_dir, eid, feed_short)
    if not p.is_file():
        return b""
    try:
        sz = int(p.stat().st_size)
    except OSError:
        return b""
    if sz <= 0:
        return b""
    rd = max(4096, min(cap, 8_388_608))
    try:
        with p.open("rb") as fh:
            return fh.read(min(rd, sz))
    except OSError:
        return b""


def aa_field_needle_pair(key_ascii_upper: str) -> tuple[bytes, bytes]:
    latin = ("\xac" + key_ascii_upper + "\xf7").encode("latin-1")
    utf = ("¬" + key_ascii_upper + "÷").encode("utf-8")
    return latin, utf


def flash_contains_chunk_matches(chunk: bytes, args: dict) -> bool:
    subs = [str(x).strip() for x in (args.get("substrings") or []) if str(x).strip()]
    if not subs:
        return False
    ci = args.get("case_insensitive", True)
    if ci:
        hay = chunk.decode("latin-1", errors="replace").casefold()
        return any(ss.casefold() in hay for ss in subs)
    hay_ascii = chunk.decode("latin-1", errors="replace")
    return any(ss in hay_ascii for ss in subs)


def flash_aa_field_key_chunk_matches(chunk: bytes, args: dict) -> bool:
    keys = []
    raw_keys = args.get("field_keys") if isinstance(args, dict) else None
    if not isinstance(raw_keys, list):
        return False
    for rk in raw_keys:
        s = str(rk).strip()
        if not _AA_FIELD_KEY_RE.match(s):
            return False
        keys.append(s.upper())
    mp = str(args.get("match_policy", "any")).strip().lower()
    hits: list[bool] = []
    for ku in keys:
        lat_u8 = aa_field_needle_pair(ku)
        ok = lat_u8[0] in chunk or lat_u8[1] in chunk
        hits.append(ok)
    if mp == "all":
        return all(hits) if hits else False
    return any(hits)


def probe_flash_nonempty(match_dir: Path, eid: str, short: str, *, strict: bool) -> bool:
    p = flash_feed_path(match_dir, eid, short)
    if not p.is_file():
        return False
    try:
        sz = p.stat().st_size
    except OSError:
        return False
    if sz <= 0:
        return False
    if not strict:
        return True
    if sz < _MIN_STRICT_BYTES:
        return False
    try:
        head = p.read_bytes()[:16384]
    except OSError:
        return False
    return b"~AA" in head


def probe_flash_contains_any(
    match_dir: Path,
    eid: str,
    short: str,
    args: dict,
    *,
    prefetched: bytes | None = None,
) -> bool:
    cap = clamp_scan_cap(args.get("max_scan_bytes"))
    if prefetched is not None:
        if not prefetched:
            return False
        chunk = prefetched[:cap]
        return flash_contains_chunk_matches(chunk, args)

    p = flash_feed_path(match_dir, eid, short)
    if not p.is_file():
        return False
    try:
        sz = p.stat().st_size
    except OSError:
        return False
    if sz <= 0:
        return False
    blob = read_feed_prefixed_bytes(match_dir, eid, short, cap)
    return flash_contains_chunk_matches(blob, args)


def probe_flash_aa_field_key_any(
    match_dir: Path,
    eid: str,
    short: str,
    args: dict,
    *,
    prefetched: bytes | None = None,
) -> bool:
    cap = clamp_scan_cap(args.get("max_scan_bytes"))
    if prefetched is not None:
        if not prefetched:
            return False
        chunk = prefetched[:cap]
        return flash_aa_field_key_chunk_matches(chunk, args if isinstance(args, dict) else {})
    blob = read_feed_prefixed_bytes(match_dir, eid, short, cap)
    return flash_aa_field_key_chunk_matches(blob, args if isinstance(args, dict) else {})


def load_supplement_buckets(db_path: Path) -> SupplementBuckets:
    if not db_path.is_file():
        return EMPTY_SUP_BUCKETS
    fd: set[tuple[str, str]] = set()
    mir: set[tuple[str, str]] = set()
    esd: set[tuple[str, str]] = set()
    with sqlite3.connect(db_path) as con:
        cur = con.execute("SELECT DISTINCT dataset, event_id, source FROM supplement")
        for row in cur.fetchall():
            d, ev, src = str(row[0]), str(row[1]), str(row[2])
            pair = (d, ev)
            if src.startswith("football-data.co.uk"):
                fd.add(pair)
            elif src.startswith("footballcsv-cache-footballdata"):
                mir.add(pair)
            elif src.startswith("engsoccerdata:"):
                esd.add(pair)
    uni = fd | mir
    return SupplementBuckets(
        fd_plus_mirror_union=frozenset(uni),
        football_data_co_uk=frozenset(fd),
        mirror=frozenset(mir),
        esd=frozenset(esd),
    )


def eval_slot(
    slot: dict,
    *,
    dataset_label: str,
    base: Path,
    eid: str,
    meta_ix: dict,
    sup_buckets: SupplementBuckets | None,
    strict: bool,
    prefetched_feeds: dict[str, bytes] | None = None,
) -> bool:
    probe = str(slot.get("probe") or "")
    args = slot.get("probe_args") or {}
    if probe == "flash_nonempty":
        short = str(args.get("feed_suffix"))
        return probe_flash_nonempty(base, eid, short, strict=strict)
    if probe == "flash_contains_any":
        short = str(args.get("feed_suffix"))
        pre = prefetched_feeds.get(short) if prefetched_feeds is not None else None
        return probe_flash_contains_any(
            base, eid, short, args if isinstance(args, dict) else {}, prefetched=pre
        )
    if probe == "flash_aa_field_key_any":
        short = str(args.get("feed_suffix"))
        pre_aa = prefetched_feeds.get(short) if prefetched_feeds is not None else None
        return probe_flash_aa_field_key_any(
            base, eid, short, args if isinstance(args, dict) else {}, prefetched=pre_aa
        )
    if probe == "meta_has_kickoff":
        m = meta_ix.get(eid)
        if m is None:
            return False
        u = m.unix_kickoff
        return u is not None and u > 1_000_000_000
    if probe == "supplement_any_fd_like_row":
        if sup_buckets is None:
            return False
        return (dataset_label, eid) in sup_buckets.fd_plus_mirror_union
    if probe == "supplement_bucket_hit":
        bk = str((args or {}).get("bucket") or "").strip()
        if sup_buckets is None:
            return False
        bset = {
            "football_data_co_uk": sup_buckets.football_data_co_uk,
            "mirror": sup_buckets.mirror,
            "engsoccerdata": sup_buckets.esd,
        }.get(bk)
        if bset is None:
            return False
        return (dataset_label, eid) in bset
    if probe == "always_true_in_manifest_iteration":
        return True
    return False


def run_coverage(
    *,
    manifest_path: Path,
    out_path: Path,
    strict_feed_sanity: bool,
    no_supplement_query: bool,
    by_dataset: bool,
    db_path: Path,
) -> dict:
    blob = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    slots = validate_manifest(blob)

    paths = get_paths()
    bundle = load_flashscore_event_meta_bundle(
        repo_root=paths.root,
        raw_flashscore_dir=paths.raw_dir / "flashscore",
    )
    meta_ix = bundle.index
    fp = meta_source_fingerprint(bundle, repo_root=paths.root)

    sup_buckets: SupplementBuckets | None = None if no_supplement_query else load_supplement_buckets(db_path)

    enrichment_source_hits_manifest: dict[str, int] | None = (
        dict.fromkeys(MANIFEST_SOURCE_ORDER, 0) if sup_buckets is not None else None
    )

    global_slots = [
        s
        for s in slots
        if s.get("counts_toward_coverage") == "primitive"
        and bool(s.get("included_in_global", False))
        and float(s.get("weight", 0)) > 0
    ]
    sum_w_global = sum(float(s.get("weight", 0)) for s in global_slots)
    if sum_w_global <= 0:
        raise SystemExit("no primitive slots with weight>0 and included_in_global")

    caps_suffix = max_scan_caps_by_suffix(slots)

    per_slot_hits: dict[str, int] = {str(s["id"]): 0 for s in slots}
    per_slot_totals: dict[str, int] = {str(s["id"]): 0 for s in slots}
    by_ds_weighted_num: dict[str, float] = {}
    by_ds_weighted_den: dict[str, float] = {}
    by_ds_events: dict[str, int] = {}

    total_events = 0
    global_weighted_hits = 0.0

    for dlabel, _ids_name, base in di.league_manifest():
        ids_path = di.IDS / f"{_ids_name}.txt"
        if not ids_path.is_file():
            continue
        eids = [ln.strip() for ln in ids_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for eid in eids:
            total_events += 1
            if by_dataset:
                by_ds_events[dlabel] = by_ds_events.get(dlabel, 0) + 1

            if enrichment_source_hits_manifest is not None and sup_buckets is not None:
                tup = (dlabel, eid)
                if tup in sup_buckets.football_data_co_uk:
                    enrichment_source_hits_manifest["football_data_co_uk"] += 1
                if tup in sup_buckets.mirror:
                    enrichment_source_hits_manifest["mirror"] += 1
                if tup in sup_buckets.esd:
                    enrichment_source_hits_manifest["engsoccerdata"] += 1

            prefetched_feeds: dict[str, bytes] | None = (
                {
                    suf: read_feed_prefixed_bytes(base, eid, suf, caps_suffix[suf])
                    for suf in caps_suffix
                }
                if caps_suffix
                else None
            )

            event_num = 0.0
            for s in global_slots:
                sw = float(s.get("weight", 0))
                hit = eval_slot(
                    s,
                    dataset_label=dlabel,
                    base=base,
                    eid=eid,
                    meta_ix=meta_ix,
                    sup_buckets=sup_buckets,
                    strict=strict_feed_sanity,
                    prefetched_feeds=prefetched_feeds,
                )
                if hit:
                    event_num += sw
                    global_weighted_hits += sw

            for s in slots:
                sid = str(s["id"])
                per_slot_totals[sid] = per_slot_totals.get(sid, 0) + 1
                if eval_slot(
                    s,
                    dataset_label=dlabel,
                    base=base,
                    eid=eid,
                    meta_ix=meta_ix,
                    sup_buckets=sup_buckets,
                    strict=strict_feed_sanity,
                    prefetched_feeds=prefetched_feeds,
                ):
                    per_slot_hits[sid] = per_slot_hits.get(sid, 0) + 1

            if by_dataset:
                by_ds_weighted_num[dlabel] = by_ds_weighted_num.get(dlabel, 0.0) + event_num
                by_ds_weighted_den[dlabel] = by_ds_weighted_den.get(dlabel, 0.0) + sum_w_global

    global_primitive_coverage = (
        (global_weighted_hits / (total_events * sum_w_global)) if total_events else 0.0
    )

    per_bucket: dict[str, object] = {}
    for s in slots:
        sid = str(s["id"])
        tot = per_slot_totals[sid]
        hit = per_slot_hits[sid]
        per_bucket[sid] = {
            "label_pl": s.get("label_pl"),
            "category": s.get("category"),
            "counts_toward_coverage": s.get("counts_toward_coverage"),
            "weight": float(s.get("weight", 0)),
            "included_in_global": bool(s.get("included_in_global", False)),
            "hit_count": hit,
            "event_total": tot,
            "fraction": (hit / tot) if tot else 0.0,
        }

    enrichment_hits = per_slot_hits.get("supplement_any_fd_like_row", 0)
    enrichment_frac = (enrichment_hits / total_events) if total_events else 0.0

    out: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifest_path": str(manifest_path),
        "manifest_schema_version": str(blob.get("schema_version")),
        "manifest_revision": str(blob.get("manifest_revision") or ""),
        "metric_interpretation": (
            "This KPI measures presence of upstream artifacts (non-empty RAW files, meta keys, optional "
            "SQLite join rows). It does not guarantee parseable semantics inside df_st/df_li (use parsers / "
            "golden checks separately). Probe flash_contains_any is a lexical scan (latin1, optional "
            "case-fold)—exploratory, language-dependent; prefer flash_aa_field_key_any for delimiter-style "
            "AA markers (¬KEY÷), validated only against latin-1 vs UTF-8 bytes (possible FN with other encodings)."
        ),
        "coverage_scope_notice": [
            "flash_feed_probes_enabled",
            "flash_aa_marker_scan_latin1_and_utf8_only",
            "meta_seed_augmentation_enabled",
            "openfootball_plaintext_probes_disabled_v1",
            "flash_aa_manifest_field_keys_derived_from_repo_list_feed_proxy_not_guaranteed_for_match_level_dfs",
        ],
        "strict_feed_sanity": strict_feed_sanity,
        "supplement_query_skipped": no_supplement_query,
        "meta_fingerprint": fp,
        "total_manifest_events_scanned": total_events,
        "global_primitive_slots_weight_sum": sum_w_global,
        "global_primitive_coverage": round(global_primitive_coverage, 6),
        "per_bucket": per_bucket,
        "enrichment_join_coverage_fraction": round(enrichment_frac, 6),
        "enrichment_join_hit_count": enrichment_hits,
    }

    if enrichment_source_hits_manifest is not None and total_events:
        out["enrichment_join_by_manifest_source"] = {
            k: {
                "manifest_event_hit_count": enrichment_source_hits_manifest[k],
                "fraction_of_manifest_events": round(
                    enrichment_source_hits_manifest[k] / total_events, 6
                ),
            }
            for k in MANIFEST_SOURCE_ORDER
        }

    if by_dataset and total_events:
        out["by_dataset_label"] = {
            ds: {
                "events": by_ds_events.get(ds, 0),
                "global_primitive_coverage": round(
                    (by_ds_weighted_num.get(ds, 0.0) / by_ds_weighted_den.get(ds, 1.0)), 6
                )
                if by_ds_weighted_den.get(ds, 0) > 0
                else 0.0,
            }
            for ds in sorted(by_ds_events.keys())
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--manifest-path",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Coverage manifest JSON (default: data/integrated/model_input_coverage_manifest.json)",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DEFAULT,
        help="Write JSON report here",
    )
    ap.add_argument(
        "--strict-feed-sanity",
        action="store_true",
        help="Besides non-empty RAW file: min size + ~AA magic in first 16KiB",
    )
    ap.add_argument(
        "--no-supplement-query",
        action="store_true",
        help="Skip SQLite supplement scan (enrichment KPI will be unset/forced empty)",
    )
    ap.add_argument(
        "--by-dataset",
        action="store_true",
        help="Add global_primitive_coverage breakdown per dataset_label",
    )
    ap.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "data" / "integrated" / "supplement.sqlite",
        help="supplement.sqlite path",
    )
    args = ap.parse_args()

    if not args.manifest_path.is_file():
        print(f"Manifest not found: {args.manifest_path}", flush=True)
        return 2

    out = run_coverage(
        manifest_path=args.manifest_path.resolve(),
        out_path=args.output.resolve(),
        strict_feed_sanity=args.strict_feed_sanity,
        no_supplement_query=args.no_supplement_query,
        by_dataset=args.by_dataset,
        db_path=args.db_path.resolve(),
    )
    print(
        f"global_primitive_coverage={out['global_primitive_coverage']} "
        f"events={out['total_manifest_events_scanned']} -> {args.output}",
        flush=True,
    )
    print(
        f"enrichment_join_coverage_fraction={out['enrichment_join_coverage_fraction']} "
        f"(hits={out['enrichment_join_hit_count']})",
        flush=True,
    )
    bk = out.get("enrichment_join_by_manifest_source")
    if bk:
        parts = []
        for k in MANIFEST_SOURCE_ORDER:
            frac = bk[k]["fraction_of_manifest_events"]
            n = bk[k]["manifest_event_hit_count"]
            parts.append(f"{k}:{frac}#{n}")
        print("enrichment_manifest_source " + "; ".join(parts), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
