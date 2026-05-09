"""Download UEFA plaintext datasets from openfootball/champions-league (+ merge → supplement.sqlite).

Free static hosting on GitHub raw; no API key.

Usage:
  python scripts/download_openfootball_allowlist.py
  python scripts/download_openfootball_allowlist.py --delay 1.25
  python scripts/download_openfootball_allowlist.py --openfoot-miss-report data/integrated/openfootball_miss_latest.json

Also writes ``data/integrated/openfootball_source_status.json`` after each run and reads optional
``data/integrated/openfootball_url_fallbacks.json`` for extra raw URLs when the champions-league tree 404s.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FALLBACKS_JSON = ROOT / "data" / "integrated" / "openfootball_url_fallbacks.json"


def load_openfootball_url_fallbacks(path: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """Parse optional JSON: ``{ \"2025-26\": { \"el\": [ \"https://...\" ] } }``."""
    p = path or FALLBACKS_JSON
    if not p.exists() or p.stat().st_size == 0:
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for season_key, block in raw.items():
        if not isinstance(season_key, str) or not isinstance(block, dict):
            continue
        inner: dict[str, list[str]] = {}
        for kind_key, urls_val in block.items():
            if not isinstance(kind_key, str):
                continue
            seq: list[str] = []
            if isinstance(urls_val, str) and urls_val.strip():
                seq = [urls_val.strip()]
            elif isinstance(urls_val, list):
                seq = [u.strip() for u in urls_val if isinstance(u, str) and u.strip()]
            if seq:
                inner[kind_key.strip()] = seq
        if inner:
            out[season_key.strip()] = inner
    return out


sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import data_integrity_flashscore as di  # noqa: E402

from football_ai.integration.join_openfootball import (
    diagnose_openfoot_miss,
    index_openfoot_matches,
    lookup_openfoot,
)  # noqa: E402
from football_ai.integration.openfootball_parse import iter_openfootball_matches  # noqa: E402
from football_ai.integration.flashscore_integration_feeds import (
    ordered_feed_txt_paths,
    seed_augment_html_paths,
)
from football_ai.integration.match_identity import compute_fixture_uid, compute_match_uid
from football_ai.integration.supplement_store import upsert_supplement_row
from football_ai.sources.flashscore_feed_match_meta import (  # noqa: E402
    FlashscoreMatchMeta,
    augment_meta_index_from_seed_html,
    build_event_meta_union,
)

BASE_RAW = "https://raw.githubusercontent.com/openfootball/champions-league/master"

UE_LABEL_TO_KIND = {
    "liga_mistrzow": "cl",
    "liga_europy": "el",
    "liga_konferencji": "conf",
}


def openfoot_rel_folder(season_folder4: str) -> str:
    y1, y2 = int(season_folder4[:2]), int(season_folder4[2:])
    return f"{2000 + y1}-{str(2000 + y2)[2:]}"


def ds_split(ds: str) -> tuple[str, str]:
    i = ds.rfind("-")
    return ds[:i], ds[i + 1 :]


def fetch_text(url: str, delay_s: float) -> str | None:
    time.sleep(delay_s)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 football-ai-integration"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        return data.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {url}", flush=True)
        return None
    except OSError as e:
        print(f"fetch failed {url} ({e})", flush=True)
        return None


def load_uefa_plaintext_chain(
    loc: Path,
    urls_to_try: list[str],
    delay_s: float,
) -> tuple[str | None, bool, list[str], str | None]:
    """Load local cache or try ``urls_to_try`` in order. Returns text, fetched_remote_new (wrote disk), urls_tried, url_resolved (None when local-only)."""
    urls_tried: list[str] = []
    if loc.exists() and loc.stat().st_size > 0:
        return loc.read_text(encoding="utf-8", errors="replace"), False, urls_tried, None
    for url in urls_to_try:
        if not url.strip():
            continue
        urls_tried.append(url.strip())
        blob = fetch_text(url.strip(), delay_s)
        if blob is None:
            continue
        loc.parent.mkdir(parents=True, exist_ok=True)
        loc.write_text(blob, encoding="utf-8", errors="replace")
        return blob, True, urls_tried, url.strip()
    return None, False, urls_tried, None


def _upstream_status_append(
    reports: list[dict],
    *,
    loc: Path,
    kind: str,
    rel_folder: str,
    text: str | None,
    urls_tried: list[str],
    url_resolved: str | None,
    primary_url: str,
) -> None:
    """Append one telemetry record (local ok, remote ok, or unavailable)."""
    row: dict = {
        "season_folder_github": rel_folder,
        "kind": kind,
        "local_relative_path": str(loc.relative_to(ROOT)),
        "urls_tried": list(urls_tried),
        "url_primary_template": primary_url,
    }
    if text is None:
        row.update(
            {
                "url_attempted": primary_url,
                "url_resolved": None,
                "status": "unavailable",
                "byte_length": 0,
                "parsed_match_row_count": 0,
                "note": (
                    "Place plaintext at local_relative_path or add entries to "
                    "data/integrated/openfootball_url_fallbacks.json "
                    "(see keys by season_folder_github), or wait for upstream publish."
                ),
            }
        )
        reports.append(row)
        return
    parsed_rows = list(iter_openfootball_matches(text))
    parsed_n = len(parsed_rows)
    from_cache_local = url_resolved is None
    row.update(
        {
            "url_attempted": primary_url,
            "url_resolved": url_resolved if not from_cache_local else None,
            "status": "ok",
            "source_channel": "local_cache" if from_cache_local else "fetched_remote",
            "byte_length": len(text.encode("utf-8", errors="replace")),
            "parsed_match_row_count": parsed_n,
        }
    )
    reports.append(row)


def main(argv: list[str]) -> int:
    delay_s = 0.75
    if "--delay" in argv:
        i = argv.index("--delay")
        delay_s = float(argv[i + 1])

    miss_report: Path | None = None
    if "--openfoot-miss-report" in argv:
        i = argv.index("--openfoot-miss-report")
        miss_report = Path(argv[i + 1])

    feeds, _fn = ordered_feed_txt_paths(
        repo_root=ROOT,
        raw_flashscore_dir=ROOT / "data" / "raw" / "flashscore",
    )
    meta_ix: dict[str, FlashscoreMatchMeta] = build_event_meta_union(feeds) if feeds else {}
    augment_meta_index_from_seed_html(
        meta_ix,
        seed_augment_html_paths(ROOT / "data" / "raw" / "flashscore"),
    )

    raw_out = ROOT / "data" / "raw" / "openfootball" / "champions-league"
    raw_out.mkdir(parents=True, exist_ok=True)
    db_path = ROOT / "data" / "integrated" / "supplement.sqlite"

    fetched_files = merged = skipped_meta = no_hit = 0
    miss_reasons: Counter[str] = Counter()

    text_cache: dict[Path, str] = {}

    ue_rows: list[tuple[str, str, Path, str, str]] = []
    for dlabel, ids_name, _base in di.league_manifest():
        leigh, seas4 = ds_split(dlabel)
        if leigh not in UE_LABEL_TO_KIND:
            continue
        kind = UE_LABEL_TO_KIND[leigh]
        rel = openfoot_rel_folder(seas4)
        loc = raw_out / rel / f"{kind}.txt"
        primary_url = f"{BASE_RAW}/{rel}/{kind}.txt"
        ue_rows.append((dlabel, ids_name, loc, primary_url, kind))

    fb_map = load_openfootball_url_fallbacks()

    upstream_reports: list[dict] = []
    seen_loc: set[Path] = set()
    for _, _, loc, primary_url, kind in ue_rows:
        if loc in seen_loc:
            continue
        seen_loc.add(loc)
        rel_folder = loc.parent.name
        extra = fb_map.get(rel_folder, {}).get(kind, [])
        urls_to_try = [primary_url]
        for u in extra:
            u = u.strip()
            if u and u not in urls_to_try:
                urls_to_try.append(u)
        text, nw, urls_tried, url_resolved = load_uefa_plaintext_chain(loc, urls_to_try, delay_s)
        _upstream_status_append(
            upstream_reports,
            loc=loc,
            kind=kind,
            rel_folder=rel_folder,
            text=text,
            urls_tried=urls_tried,
            url_resolved=url_resolved,
            primary_url=primary_url,
        )
        if text is None:
            continue
        text_cache[loc] = text
        if nw:
            fetched_files += 1

    of_index_cache: dict[Path, object] = {}
    for dlabel, ids_name, loc, _primary_url, kind in ue_rows:
        text = text_cache.get(loc)
        if text is None:
            continue
        if loc not in of_index_cache:
            recs = list(iter_openfootball_matches(text))
            of_index_cache[loc] = index_openfoot_matches(recs)
        of_ix = of_index_cache[loc]

        ids_path = di.IDS / f"{ids_name}.txt"
        if not ids_path.exists():
            continue
        source_tag = f"openfootball:champions-league:{loc.parent.name}:{kind}"
        eids = [ln.strip() for ln in ids_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for eid in eids:
            meta = meta_ix.get(eid)
            if meta is None:
                skipped_meta += 1
                continue
            hit = lookup_openfoot(
                ix=of_ix,
                unix_ts=meta.unix_kickoff,
                nh=meta.home_team,
                na=meta.away_team,
            )
            if hit is None:
                no_hit += 1
                miss_reasons[
                    diagnose_openfoot_miss(
                        ix=of_ix,
                        unix_ts=meta.unix_kickoff,
                        nh=meta.home_team,
                        na=meta.away_team,
                    )
                ] += 1
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
                db_path,
                dataset=dlabel,
                event_id=eid,
                source=source_tag,
                unix_kickoff=meta.unix_kickoff,
                home_name=meta.home_team,
                away_name=meta.away_team,
                match_uid=m_uid,
                fixture_uid=f_uid,
                payload={
                    "repo": "openfootball/champions-league",
                    "match_uid": m_uid,
                    "fixture_uid": f_uid,
                    "folder": loc.parent.name,
                    "kind": kind,
                    "kick_clock": hit.kick_clock,
                    "score_ft": hit.score_ft,
                    "score_ht": hit.score_ht,
                    "parsed_home": hit.home_short,
                    "parsed_away": hit.away_short,
                },
            )
            merged += 1

    print(
        f"Openfootball: fetched {fetched_files} remote files anew;",
        merged,
        "rows merged;",
        skipped_meta,
        "missing_aa_meta;",
        no_hit,
        "no_matching_line;",
        flush=True,
    )
    if miss_reasons:
        print(
            "openfoot_no_hit_breakdown",
            dict(miss_reasons),
            flush=True,
        )
    if miss_report is not None:
        miss_report.parent.mkdir(parents=True, exist_ok=True)
        miss_report.write_text(
            json.dumps(dict(sorted(miss_reasons.items())), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote OpenFootball miss breakdown {miss_report}", flush=True)

    status_path = ROOT / "data" / "integrated" / "openfootball_source_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(upstream_reports, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote OpenFootball upstream telemetry {status_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
