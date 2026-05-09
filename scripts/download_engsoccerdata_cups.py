"""
Download England cup CSVs from the ``jalapic/engsoccerdata`` GitHub repo (James Curley).

Upstream: https://github.com/jalapic/engsoccerdata — data in ``data-raw/``. License is
CC BY 4.0 per that repository (attribute when publishing derivatives).

Fetched files land under ``data/raw/engsoccerdata/cups/`` and are registered in the
SQLite raw cache (same mechanics as Buchdahl / OpenFootball downloads). These CSVs use
their own column layout; they do not plug into MMZ overlay without an adapter.

**Refreshing from the same Git ref:** if the SQLite cache already recorded this URL
(default ``ref=master``), a run without ``--force`` skips HTTP entirely. The content
behind ``master`` on GitHub may change anyway; pass ``--force`` to re-download and
overwrite files on disk. The project README («FA Cup i EFL Cup») describes a lightweight
CSV sanity check and optional downstream scripts.

Typical refresh from repo root: ``python scripts/download_engsoccerdata_cups.py --force``.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_ai.http import HttpClient  # noqa: E402
from football_ai.paths import get_paths  # noqa: E402
from football_ai.storage import Storage  # noqa: E402

RAW_BASE = "https://raw.githubusercontent.com/jalapic/engsoccerdata"
SOURCE_KEY = "engsoccerdata"
_SUBDIR = "cups"


@dataclass(frozen=True)
class _ArtifactSpec:
    filename: str
    required_header_tokens: tuple[str, ...] = ("Date", "Season")


_ARTIFACTS: tuple[_ArtifactSpec, ...] = (
    _ArtifactSpec("facup.csv"),
    _ArtifactSpec("leaguecup.csv"),
)


def _canonical_url(ref: str, filename: str) -> str:
    ref = ref.strip().strip("/")
    if not ref:
        raise ValueError("ref must be non-empty")
    return f"{RAW_BASE}/{ref}/data-raw/{filename}"


def _body_sanity_checks(content: bytes, spec: _ArtifactSpec) -> None:
    sniff = content[:768].lower()
    if b"<!doctype html" in sniff or b"<html" in sniff:
        raise ValueError("response looks like HTML, not CSV")
    text = content.decode("utf-8-sig", errors="strict")
    first = text.splitlines()[0] if text else ""
    for tok in spec.required_header_tokens:
        if tok not in first:
            raise ValueError(f"missing header token {tok!r} in first line: {first[:120]!r}")


def _fetch_one(
    *,
    storage: Storage,
    http: HttpClient,
    spec: _ArtifactSpec,
    ref: str,
    force: bool,
    errs: list[str],
) -> None:
    url = _canonical_url(ref, spec.filename)
    if (not force) and storage.has_url(SOURCE_KEY, url):
        print(f"skip (cached URL): {spec.filename}", flush=True)
        return
    status, content, _final_url = http.get(url)
    if status != 200:
        errs.append(f"{spec.filename}: HTTP {status} for {url}")
        return
    try:
        _body_sanity_checks(content, spec)
    except ValueError as e:
        errs.append(f"{spec.filename}: {e}")
        return
    storage.save_bytes(
        source=SOURCE_KEY,
        kind="csv",
        url=url,
        status_code=status,
        content=content,
        filename=spec.filename,
        subdir=_SUBDIR,
    )
    print(f"wrote {spec.filename}", flush=True)


def main() -> int:
    os.chdir(ROOT)
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Re-download even if URL already in raw DB")
    ap.add_argument(
        "--ref",
        default="master",
        help="Git branch, tag, or commit SHA under jalapic/engsoccerdata (default: master)",
    )
    ap.add_argument(
        "--min-delay",
        type=float,
        default=1.25,
        help="Minimum seconds between HTTP requests",
    )
    ap.add_argument(
        "--include-test",
        action="store_true",
        help="Also download leagucuptest.csv (auxiliary dataset in upstream data-raw/)",
    )
    args = ap.parse_args()

    paths = get_paths()
    storage = Storage(db_path=paths.db_path, raw_dir=paths.raw_dir)
    http = HttpClient()
    http.min_delay_s = max(http.min_delay_s, args.min_delay)

    specs: tuple[_ArtifactSpec, ...] = (
        *_ARTIFACTS,
        *((_ArtifactSpec("leagucuptest.csv"),) if args.include_test else ()),
    )

    errs: list[str] = []
    ref = (args.ref or "").strip() or "master"

    for spec in specs:
        try:
            _fetch_one(
                storage=storage,
                http=http,
                spec=spec,
                ref=ref,
                force=args.force,
                errs=errs,
            )
        except Exception as e:  # noqa: BLE001
            errs.append(f"{spec.filename}: {e}")

    if errs:
        print("\nFailures:", flush=True)
        for ln in errs:
            print(f" - {ln}", flush=True)
        return 2

    raw_out = paths.raw_dir / SOURCE_KEY / _SUBDIR
    print(f"Done. Files under {raw_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
