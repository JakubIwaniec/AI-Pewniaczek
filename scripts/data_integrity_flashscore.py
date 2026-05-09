"""Merge misplaced RAW paths, audit df_sui/df_st/df_li coverage, optionally re-fetch gaps."""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
from pathlib import Path

# Project root = parent of scripts/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_ai.http import HttpClient
from football_ai.integration.flashscore_repair_feeds import (
    REPAIR_FEED_KINDS,
    parse_repair_feed_kinds,
)
from football_ai.integration.domestic_cup_flashscore import domestic_cup_flashscore_manifest_rows
from football_ai.paths import get_paths
from football_ai.sources.flashscore import download_feed_raw
from football_ai.storage import Storage

FLASH = ROOT / "data" / "raw" / "flashscore"
IDS = ROOT / "data" / "event_ids"
REPAIR_LOCK = ROOT / "data" / ".flashscore_repair.lock"


def _pid_is_running(pid: int) -> bool:
    """Best-effort: avoid running two concurrent repair loops."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _repair_lock_acquire() -> None:
    REPAIR_LOCK.parent.mkdir(parents=True, exist_ok=True)
    if REPAIR_LOCK.exists():
        parts = REPAIR_LOCK.read_text(encoding="utf-8", errors="ignore").strip().split()
        try:
            old = int(parts[0])
        except (ValueError, IndexError):
            old = 0
        if _pid_is_running(old):
            raise SystemExit(
                f"Repair już dziala (PID {old}). Zamknij ten proces lub, jesli wisial, "
                f"usun plik blokady recznie: {REPAIR_LOCK}"
            )
        REPAIR_LOCK.unlink(missing_ok=True)
    REPAIR_LOCK.write_text(f"{os.getpid()}\n", encoding="ascii")


def _repair_lock_release() -> None:
    REPAIR_LOCK.unlink(missing_ok=True)


def league_manifest() -> list[tuple[str, str, Path]]:
    m: list[tuple[str, str, Path]] = []
    leagues = [
        ("ekstraklasa", "polska/ekstraklasa"),
        ("chance_liga", "czechy/chance-liga"),
        ("liga_portugal", "portugalia/liga-portugal"),
        ("laliga", "hiszpania/laliga"),
        ("serie_a", "wlochy/serie-a"),
        ("premier_league", "anglia/premier-league"),
        ("bundesliga", "niemcy/bundesliga"),
        ("ligue_1", "francja/ligue-1"),
        ("eredivisie", "holandia/eredivisie"),
        ("jupiler_league", "belgia/jupiler-league"),
        ("super_league", "grecja/super-league"),
        ("super_lig", "turcja/super-lig"),
    ]
    for key, rel in leagues:
        for sea in ["2223", "2324", "2425", "2526"]:
            m.append((f"{key}-{sea}", f"{key}_{sea}", FLASH / rel / sea / "matches"))
    uefa = [
        ("liga_mistrzow", "europa/liga-mistrzow"),
        ("liga_europy", "europa/liga-europejska"),
        ("liga_konferencji", "europa/liga-konferencji"),
    ]
    for key, rel in uefa:
        for sea in ["2223", "2324", "2425", "2526"]:
            m.append((f"{key}-{sea}", f"{key}_{sea}", FLASH / rel / sea / "matches"))
    m.extend(domestic_cup_flashscore_manifest_rows(raw_flashscore_root=FLASH))
    return m


def feed_ok(match_dir: Path, eid: str, suffix: str) -> bool:
    f = match_dir / eid / f"{suffix}_{eid}.txt"
    return f.exists() and f.stat().st_size > 0


def merge_orphan_poland_ekstraklasa() -> int:
    """Move misplaced `flashscore/ekstraklasa/...` into `flashscore/polska/ekstraklasa/...`."""
    src = FLASH / "ekstraklasa"
    dst = FLASH / "polska" / "ekstraklasa"
    if not src.exists():
        return 0
    moved = 0
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > 0:
            p.unlink(missing_ok=True)
        elif target.exists():
            target.unlink(missing_ok=True)
            shutil.move(str(p), str(target))
            moved += 1
        else:
            shutil.move(str(p), str(target))
            moved += 1
    shutil.rmtree(src, ignore_errors=True)
    return moved


def audit() -> tuple[int, int, int, list[tuple[str, str, list[str]]]]:
    incomplete_events = 0
    total_events = 0
    ok_events = 0
    datasets_bad: list[tuple[str, str, list[str]]] = []

    for dlabel, ids_name, base in league_manifest():
        path = IDS / f"{ids_name}.txt"
        if not path.exists():
            datasets_bad.append((dlabel, "missing_event_ids_file", []))
            continue
        eids = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not eids:
            datasets_bad.append((dlabel, "empty_event_ids", []))
            continue
        bad_sample: list[str] = []
        bad_n = 0
        for eid in eids:
            total_events += 1
            needs = []
            if not feed_ok(base, eid, "df_sui_1"):
                needs.append("sui")
            if not feed_ok(base, eid, "df_st_1"):
                needs.append("st")
            if not feed_ok(base, eid, "df_li_1"):
                needs.append("li")
            if needs:
                incomplete_events += 1
                bad_n += 1
                if len(bad_sample) < 8:
                    bad_sample.append(f"{eid}:{','.join(needs)}")
            else:
                ok_events += 1
        if bad_n:
            datasets_bad.append((dlabel, f"incomplete {bad_n}/{len(eids)}", bad_sample))

    return ok_events, total_events, incomplete_events, datasets_bad


def gap_stats() -> tuple[int, int, int, int, dict[str, tuple[int, int, int]], int]:
    """
    Count missing non-empty RAW feeds (same rules as audit).
    Returns:
      missing_sui, missing_st, missing_li, incomplete_events,
      per_dataset_need (dlabel -> (n_sui, n_st, n_li)),
      total_events.
    """
    missing_sui = missing_st = missing_li = 0
    incomplete_events = 0
    per_ds: dict[str, tuple[int, int, int]] = {}
    total_events = 0

    def add_ds(label: str) -> tuple[int, int, int]:
        if label not in per_ds:
            per_ds[label] = (0, 0, 0)
        return per_ds[label]

    for dlabel, ids_name, base in league_manifest():
        path = IDS / f"{ids_name}.txt"
        if not path.exists():
            continue
        eids = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for eid in eids:
            total_events += 1
            ds = list(add_ds(dlabel))
            lacks = []
            if not feed_ok(base, eid, "df_sui_1"):
                missing_sui += 1
                ds[0] += 1
                lacks.append("sui")
            if not feed_ok(base, eid, "df_st_1"):
                missing_st += 1
                ds[1] += 1
                lacks.append("st")
            if not feed_ok(base, eid, "df_li_1"):
                missing_li += 1
                ds[2] += 1
                lacks.append("li")
            per_ds[dlabel] = tuple(ds)
            if lacks:
                incomplete_events += 1
    return missing_sui, missing_st, missing_li, incomplete_events, per_ds, total_events


def gap_download_pairs(*, feeds: frozenset[str] | None = None) -> list[tuple[str, str]]:
    """Unique (feed_key, storage_subdir) under source *flashscore* (no flashscore prefix).

    If ``feeds`` is omitted, includes sui, st, li. Otherwise only suffix kinds in the set:
    ``sui`` -> df_sui_1, ``st`` -> df_st_1, ``li`` -> df_li_1.
    """
    kinds = feeds if feeds is not None else REPAIR_FEED_KINDS
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for _dlabel, ids_name, base in league_manifest():
        path = IDS / f"{ids_name}.txt"
        if not path.exists():
            continue
        eids = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rel_base = base.relative_to(FLASH).as_posix()
        for eid in eids:
            sd = f"{rel_base}/{eid}"
            if "sui" in kinds and not feed_ok(base, eid, "df_sui_1"):
                t = (f"df_sui_1_{eid}", sd)
                if t not in seen:
                    seen.add(t)
                    out.append(t)
            if "st" in kinds and not feed_ok(base, eid, "df_st_1"):
                t = (f"df_st_1_{eid}", sd)
                if t not in seen:
                    seen.add(t)
                    out.append(t)
            if "li" in kinds and not feed_ok(base, eid, "df_li_1"):
                t = (f"df_li_1_{eid}", sd)
                if t not in seen:
                    seen.add(t)
                    out.append(t)
    return out


def download_gaps(feeds: frozenset[str] | None = None) -> None:
    paths = get_paths()
    storage = Storage(db_path=paths.db_path, raw_dir=paths.raw_dir)
    http = HttpClient()
    http.min_delay_s = max(http.min_delay_s, 2.0)
    pairs = sorted(gap_download_pairs(feeds=feeds), key=lambda x: (x[1], x[0]))
    n = len(pairs)
    for i, (feed, sd) in enumerate(pairs, 1):
        if i % 50 == 0 or i == 1:
            print(f"Fetching {i}/{n} feed={feed} subdir={sd}", flush=True)
        download_feed_raw(
            storage=storage,
            http=http,
            feed=feed,
            subdir=sd,
            force=True,
        )


def main() -> None:
    import argparse
    import os

    os.chdir(ROOT)

    ap = argparse.ArgumentParser()
    ap.add_argument("--merge-orphan-poland", action="store_true", help="Merge flashscore/ekstraklasa into polska/ekstraklasa")
    ap.add_argument("--audit-only", action="store_true")
    ap.add_argument("--gap-stats", action="store_true", help="Count missing df_sui/df_st/df_li without full audit lines")
    ap.add_argument("--repair", action="store_true", help="Re-fetch missing/empty feeds (force)")
    ap.add_argument(
        "--repair-feeds",
        default="all",
        help="Comma list with --repair only: li,st,sui or all (default all). Limits which df_* feeds to fetch.",
    )
    args = ap.parse_args()

    if args.merge_orphan_poland:
        n = merge_orphan_poland_ekstraklasa()
        print(f"Merged orphan poland ekstraklasa files touched: {n}", flush=True)

    if args.gap_stats:
        ms, mt, ml, incomplete, per_ds, tot = gap_stats()
        print(
            "GAP_STATS events_total=%d incomplete_events=%d missing_feeds "
            "(df_sui=%d df_st=%d df_li=%d)"
            % (tot, incomplete, ms, mt, ml),
            flush=True,
        )
        top_ds = sorted(
            ((label, triple) for label, triple in per_ds.items() if sum(triple)),
            key=lambda row: -(sum(row[1])),
        )[:30]
        for label, (a, b, c) in top_ds:
            if a + b + c:
                print(
                    " ",
                    (
                        label,
                        f"gaps total={a + b + c}",
                        {"sui": a, "st": b, "li": c},
                    ),
                    flush=True,
                )
        if len(per_ds) > 30:
            print(f"  ... ({len(per_ds)} datasets; showing top by gap count)", flush=True)
    elif args.audit_only:
        ok, tot, bad, dbg = audit()
        print(f"AUDIT OK={ok}/{tot} incomplete_events={bad}", flush=True)
        problematic = [(d, err, samp) for d, err, samp in dbg if err in ("missing_event_ids_file", "empty_event_ids") or samp]
        for row in problematic[:80]:
            print(" ", row, flush=True)
        if len(problematic) > 80:
            print(f" ... and {len(problematic)-80} more dataset warnings", flush=True)
    elif args.repair:
        try:
            feed_set = parse_repair_feed_kinds(args.repair_feeds)
        except ValueError as e:
            raise SystemExit(str(e)) from e
        kinds_s = ",".join(sorted(feed_set))
        before = len(gap_download_pairs(feeds=feed_set))
        print(
            f"Repair (feeds={kinds_s}): fetching up to {before} missing/empty feeds (force)...",
            flush=True,
        )
        _repair_lock_acquire()
        try:
            download_gaps(feeds=feed_set)
        finally:
            _repair_lock_release()
        after = len(gap_download_pairs(feeds=feed_set))
        ok, tot, bad, _ = audit()
        print(f"Repair done. Remaining raw gap downloads: {after}", flush=True)
        print(f"Post-repair AUDIT OK={ok}/{tot} incomplete_events={bad}", flush=True)
    else:
        ok, tot, bad, _ = audit()
        print(f"AUDIT OK={ok}/{tot} incomplete_events={bad}", flush=True)


if __name__ == "__main__":
    main()
