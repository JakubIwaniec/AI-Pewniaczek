"""Join Flashscore AA-meta rows to football-data.co.uk CSV rows."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from football_ai.cli import FOOTBALL_DATA_LEAGUES
from football_ai.integration.normalize import norm_club


def season_folder_pol_slash(s4: str) -> str:
    i, j = int(s4[:2]), int(s4[2:])
    return f"{2000 + i}/{2000 + j}"


def csv_path_mmz(raw_dir: Path, season_folder: str, division_code: str) -> Path:
    return raw_dir / "football-data.co.uk" / season_folder / f"{division_code}.csv"


def cache_footballdata_repo_root(raw_dir: Path) -> Path:
    return raw_dir / "footballcsv" / "cache-footballdata"


def season_four_to_cache_footballdata_slug(season_four: str) -> str:
    """Map MMZ folder token ``2223`` → cache directory ``2022-23``."""
    s = season_four.strip()
    if len(s) != 4 or not s.isdigit():
        raise ValueError(f"season_four must be 4 digits, got {season_four!r}")
    yy = 2000 + int(s[:2])
    yy2 = yy + 1
    return f"{yy}-{str(yy2)[2:]}"


MMZ_DIVISION_CODE_TO_CACHE_MIRROR_STEM: dict[str, str] = {
    # Verified against footballcsv/cache.footballdata (e.g. 2022-23/*.csv).
    "E0": "eng.1",
    "SP1": "es.1",
    "I1": "it.1",
    "D1": "de.1",
    "F1": "fr.1",
    "N1": "nl.1",
    "P1": "pt.1",
    "B1": "be.1",
    "T1": "tr.1",
    "G1": "gr.1",
}


def cache_footballdata_mirror_csv_path(
    raw_dir: Path, season_four: str, mmz_division_code: str
) -> Path | None:
    stem = MMZ_DIVISION_CODE_TO_CACHE_MIRROR_STEM.get(mmz_division_code)
    if not stem:
        return None
    try:
        slug = season_four_to_cache_footballdata_slug(season_four)
    except ValueError:
        return None
    return cache_footballdata_repo_root(raw_dir) / slug / f"{stem}.csv"


def pol_csv_path(raw_dir: Path) -> Path:
    return raw_dir / "football-data.co.uk" / "new" / "POL.csv"


EngsoccerdataCupKind = Literal["facup", "leaguecup"]


def season_four_to_engsoccer_start_year(season4: str) -> int:
    """Map folder token (e.g. ``2324``) to jalapic ``Season`` starting year (2023).

    ``engsoccerdata_cup_index`` keeps rows whose ``Season`` matches this integer (plus slash/hyphen
    forms). If ``facup.csv`` / ``leaguecup.csv`` have no rows for modern seasons (truncated mirror),
    the index stays empty even when parsing succeeds.
    """
    s = season4.strip()
    if len(s) != 4 or not s.isdigit():
        raise ValueError(f"season4 must be 4 digits, got {season4!r}")
    return 2000 + int(s[:2])


def engsoccerdata_cup_csv_path(raw_dir: Path, cup: EngsoccerdataCupKind) -> Path:
    name = "facup.csv" if cup == "facup" else "leaguecup.csv"
    return raw_dir / "engsoccerdata" / "cups" / name


_ENGSD_SEASON_HYPHEN_4_2 = re.compile(
    r"^\s*((?:19|20)\d{2})\s*-\s*(?:\d{2}|\d{4})\s*$"
)
_ENGSD_SEASON_HYPHEN_2_2 = re.compile(r"^\s*(\d{2})\s*-\s*(\d{2})\s*$")


def _engsoccer_numeric_year_token(tok: str) -> int | None:
    t = tok.strip()
    if not t:
        return None
    if t.isdigit():
        n = len(t)
        if n == 4:
            y = int(t)
            return y if 1800 <= y <= 2100 else None
        if n <= 2:
            yy = int(t)
            y = 2000 + yy if yy < 70 else 1900 + yy
            return y if 1800 <= y <= 2100 else None
        return None
    try:
        y = int(float(t.replace(",", "")))
    except ValueError:
        return None
    return y if 1800 <= y <= 2100 else None


def _engsoccer_parse_season_year(val: Any) -> int | None:
    """Map jalapic ``Season`` cell to **starting** calendar year (aligns with ``season_four_to_engsoccer_start_year``)."""
    if val is None:
        return None
    raw = str(val).strip()
    if not raw or raw.upper() == "NA":
        return None
    s = raw.replace("\u2212", "-")

    m4 = _ENGSD_SEASON_HYPHEN_4_2.match(s)
    if m4:
        y = int(m4.group(1))
        if 1800 <= y <= 2100:
            return y

    m2 = _ENGSD_SEASON_HYPHEN_2_2.match(s)
    if m2:
        a = int(m2.group(1))
        y = 2000 + a if a < 70 else 1900 + a
        if 1800 <= y <= 2100:
            return y

    if "/" in s:
        left = s.split("/", 1)[0].strip()
        py = _engsoccer_numeric_year_token(left)
        if py is not None:
            return py

    try:
        return int(float(raw.replace(",", "")))
    except ValueError:
        return None


LEAG_KEY_TO_CLI = {
    "premier_league": "ENG1",
    "laliga": "ESP1",
    "serie_a": "ITA1",
    "bundesliga": "GER1",
    "ligue_1": "FRA1",
    "eredivisie": "NED1",
    "liga_portugal": "POR1",
    "jupiler_league": "BEL1",
    "super_league": "GRE1",
    "super_lig": "TUR1",
    "chance_liga": "CZE1",
}


def load_manifest_mmz_overlay(project_root: Path) -> dict[str, str]:
    """Optional B2 map: manifest league_key (e.g. fa_cup) -> mmz4281 division filename without .csv."""
    p = project_root / "data" / "integrated" / "football_data_manifest_mmz_overlay.json"
    if not p.exists() or p.stat().st_size == 0:
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            out[k.strip()] = v.strip().removesuffix(".csv")
    return out


def overlay_mmz_csv_path(raw_dir: Path, season_folder: str, division_code: str) -> Path:
    return csv_path_mmz(raw_dir, season_folder, division_code)


@dataclass
class CsvRowIndex:
    key_to_rows: dict[tuple[int, int, int, str, str], list[dict[str, Any]]]


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    text = ""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) < 2:
        return []
    return list(csv.DictReader(lines))


def _parse_ddmmyyyy(s: str) -> tuple[int, int, int] | None:
    s = s.strip()
    if "/" in s:
        parts = [p.strip() for p in s.split("/")]
        if len(parts) != 3:
            return None
        dd_s, mm_s, yyyy_s = parts
        return int(yyyy_s), int(mm_s), int(dd_s)
    return None


def _parse_yyyy_mm_dd(s: str) -> tuple[int, int, int] | None:
    if s.count("-") != 2:
        return None
    y, mn, dd = [p.strip() for p in s.split("-")]
    return int(y), int(mn), int(dd)


def flexible_match_date(cell: str) -> tuple[int, int, int] | None:
    cell = cell.strip()
    if not cell:
        return None
    if "-" in cell and len(cell) >= 10 and cell[4] == "-":
        return _parse_yyyy_mm_dd(cell)
    return _parse_ddmmyyyy(cell.replace(".", "/"))


def extract_row_date(row: dict[str, Any]) -> tuple[int, int, int] | None:
    for key in ("Date", "date", "GameDate"):
        if key in row and row[key]:
            r = flexible_match_date(str(row[key]))
            if r:
                return r
    return None


def engsoccerdata_cup_index(
    csv_path: Path, *, season_start_year: int, cup: EngsoccerdataCupKind
) -> CsvRowIndex:
    """Index jalapic ``facup.csv`` / ``leaguecup.csv`` rows by local date + normalized club names."""
    assert cup in ("facup", "leaguecup")
    rows = _read_csv_rows(csv_path)
    buckets: dict[tuple[int, int, int, str, str], list[dict[str, Any]]] = {}
    for r_raw in rows:
        r = {
            str(k).strip(): (str(v).strip() if isinstance(v, str) else v) for k, v in r_raw.items() if k
        }
        sy = _engsoccer_parse_season_year(r.get("Season"))
        if sy is None or sy != season_start_year:
            continue
        d = extract_row_date(r)
        if not d:
            continue
        hh = norm_club(str(r.get("home") or ""))
        aa = norm_club(str(r.get("visitor") or ""))
        if not hh or not aa:
            continue
        nm = str(r.get("nonmatch") or "").strip().upper()
        if nm and nm != "NA":
            continue
        y, mn, dd = d
        buckets.setdefault((y, mn, dd, hh, aa), []).append(r)
    return CsvRowIndex(key_to_rows=buckets)


_MONTH_ABBR_EN: dict[str, int] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_footballcsv_cache_eng_date(cell: str) -> tuple[int, int, int] | None:
    """Parse ``Fri Aug 5 2022`` from footballcsv/cache.footballdata (English month abbr).

    Uses fixed month map — no OS locale dependence.
    """
    parts = cell.strip().split()
    if len(parts) != 4:
        return None
    _wk, mon_s, dd_s, yyyy_s = parts
    mn = _MONTH_ABBR_EN.get(mon_s.strip().lower()[:3])
    if mn is None:
        return None
    try:
        dd = int(dd_s.strip())
        y = int(yyyy_s.strip())
    except ValueError:
        return None
    if not (1 <= dd <= 31 and y >= 1800):
        return None
    return (y, mn, dd)


def footballcsv_cache_footballdata_index(csv_path: Path) -> CsvRowIndex:
    """Index rows from github.com/footballcsv/cache.footballdata (Team 1 / Team 2, English dates)."""
    rows = _read_csv_rows(csv_path)
    buckets: dict[tuple[int, int, int, str, str], list[dict[str, Any]]] = {}
    for r_raw in rows:
        r = {}
        for k, v in r_raw.items():
            if not k:
                continue
            k2 = str(k).strip()
            r[k2] = (str(v).strip() if isinstance(v, str) else v)
        dcell = (
            str(r.get("Date") or r.get("date") or "").strip()
        )
        dd = parse_footballcsv_cache_eng_date(dcell) if dcell else None
        if not dd:
            continue
        t1 = str(r.get("Team 1") or r.get("Team1") or "").strip()
        t2 = str(r.get("Team 2") or r.get("Team2") or "").strip()
        hh = norm_club(t1)
        aa = norm_club(t2)
        if not hh or not aa:
            continue
        y, mn, day = dd
        buckets.setdefault((y, mn, day, hh, aa), []).append(r)
    return CsvRowIndex(key_to_rows=buckets)


def football_data_standard_index(csv_path: Path) -> CsvRowIndex:
    rows = _read_csv_rows(csv_path)
    buckets: dict[tuple[int, int, int, str, str], list[dict[str, Any]]] = {}
    for r_raw in rows:
        r = {str(k).strip(): (str(v).strip() if isinstance(v, str) else v) for k, v in r_raw.items() if k}
        d = extract_row_date(r)
        if not d:
            continue
        hh = norm_club(str(r.get("HomeTeam") or ""))
        aa = norm_club(str(r.get("AwayTeam") or ""))
        if not hh or not aa:
            continue
        y, mn, dd = d
        k = (y, mn, dd, hh, aa)
        buckets.setdefault(k, []).append(r)
    return CsvRowIndex(key_to_rows=buckets)


def poland_filtered_index(csv_path: Path, season_slash: str) -> CsvRowIndex:
    rows = _read_csv_rows(csv_path)
    buckets: dict[tuple[int, int, int, str, str], list[dict[str, Any]]] = {}
    for r_raw in rows:
        r = {str(k).strip(): (str(v).strip() if isinstance(v, str) else v) for k, v in r_raw.items() if k}
        if str(r.get("Season") or "").strip() != season_slash:
            continue
        d = flexible_match_date(str(r.get("Date") or ""))
        if not d:
            continue
        y, mn, dd = d
        hh = norm_club(str(r.get("Home") or ""))
        aa = norm_club(str(r.get("Away") or ""))
        if not hh or not aa:
            continue
        buckets.setdefault((y, mn, dd, hh, aa), []).append(r)
    return CsvRowIndex(key_to_rows=buckets)


def cli_key_to_mmz_csv(raw_dir: Path, season_folder: str, cli_key: str) -> Path:
    lg = FOOTBALL_DATA_LEAGUES[cli_key]
    return csv_path_mmz(raw_dir, season_folder, lg.code)


def lookup_fd_row(idx: CsvRowIndex, *, unix_ts: int | None, nh: str, na: str) -> dict[str, Any] | None:
    if unix_ts is None:
        return None
    utc_d = datetime.fromtimestamp(unix_ts, tz=UTC).date()
    nh2, na2 = norm_club(nh), norm_club(na)
    for delta in (0, -1, 1):
        d = utc_d + timedelta(days=delta)
        k = (d.year, d.month, d.day, nh2, na2)
        hits = idx.key_to_rows.get(k)
        if hits and len(hits) == 1:
            return hits[0]
    return None


def csv_row_imprint(row: dict[str, Any]) -> tuple[Any, ...]:
    """Deterministic imprint for diagnostics (prefer Date + home + away variants)."""

    def _strip(v: Any) -> str:
        return str(v).strip() if v is not None else ""

    for date_k, hk, ak in (
        ("Date", "HomeTeam", "AwayTeam"),
        ("date", "HomeTeam", "AwayTeam"),
        ("Date", "home", "visitor"),
        ("date", "home", "visitor"),
        ("Date", "Team 1", "Team 2"),
    ):
        if date_k not in row:
            continue
        dv = _strip(row.get(date_k))
        hv = _strip(row.get(hk))
        av = _strip(row.get(ak))
        if dv and hv and av:
            return ("std3", dv, hv, av)
    items = [(str(k), str(v).strip() if isinstance(v, str) else str(v)) for k, v in sorted(row.items())]
    return ("full_row", tuple(items))


def _hits_for_pair(idx: CsvRowIndex, utc_d: date, nh2: str, na2: str, delta_days: int) -> list[dict[str, Any]]:
    d = utc_d + timedelta(days=delta_days)
    k = (d.year, d.month, d.day, nh2, na2)
    return idx.key_to_rows.get(k) or []


def diagnose_fd_row_miss(
    idx: CsvRowIndex,
    *,
    unix_ts: int | None,
    nh: str,
    na: str,
    diagnostic_radius_days: int = 7,
) -> tuple[str, dict[str, Any]]:
    """Classify ``lookup_fd_row`` misses for tooling (exclusive categories).

    Caller should pass Flashscore nominal home ``nh``, away ``na`` identical to prod join.
    """

    extra: dict[str, Any] = {}
    if unix_ts is None:
        return "no_unix", extra
    nh2, na2 = norm_club(nh), norm_club(na)
    if not nh2 or not na2:
        return "norm_empty_side", extra
    if not idx.key_to_rows:
        return "csv_index_empty", extra

    if lookup_fd_row(idx, unix_ts=unix_ts, nh=nh, na=na) is not None:
        return "would_match_diag_bug", extra

    if lookup_fd_row(idx, unix_ts=unix_ts, nh=na, na=nh) is not None:
        return "would_match_team_order_swap", extra

    utc_d = datetime.fromtimestamp(unix_ts, tz=UTC).date()

    ms = {delta: len(_hits_for_pair(idx, utc_d, nh2, na2, delta)) for delta in (0, -1, 1)}

    if all(ms[d] == 0 for d in (0, -1, 1)):
        nom = "no_row_pm1"
    else:
        nom = "ambiguous_or_dense_pm1"

    if nom != "no_row_pm1":
        return nom, extra

    r = diagnostic_radius_days
    extra["diagnostic_wide_radius_days"] = r
    if r < 2:
        extra["diagnostic_wide_skipped"] = True
        extra["wide_skipped_reason"] = "radius_lt_2"
        return "no_row_pm1", extra

    ks: list[int] = []
    ks.extend(range(-2, -r - 1, -1))
    ks.extend(range(2, r + 1))

    imprints: set[tuple[Any, ...]] = set()
    any_multi_hit = False
    any_hit = False
    for k in ks:
        hits = _hits_for_pair(idx, utc_d, nh2, na2, k)
        if hits:
            any_hit = True
        if len(hits) > 1:
            any_multi_hit = True
        for row in hits:
            imprints.add(csv_row_imprint(row))

    if not any_hit:
        return "no_ordered_hit_after_pmR", extra
    if any_multi_hit or len(imprints) != 1:
        return "ambiguous_or_dense_wide", extra
    return "single_hit_wide_pmR_only", extra
