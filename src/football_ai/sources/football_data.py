from __future__ import annotations

from dataclasses import dataclass

from football_ai.http import HttpClient
from football_ai.storage import Storage


@dataclass(frozen=True)
class FootballDataLeague:
    # football-data.co.uk division codes (common ones)
    code: str  # e.g. "E0" for Premier League
    name: str


FOOTBALL_DATA_BASE = "https://www.football-data.co.uk/mmz4281"

# Consolidated Poland Ekstraklasa (many seasons); not under mmz4281/{season}/.
POLAND_HISTORICAL_CSV_URL = "https://www.football-data.co.uk/new/POL.csv"


def _season_path(season: str) -> str:
    """
    football-data.co.uk uses folder like '2425' for 2024/25 season.
    We accept:
      - '2024/2025' -> '2425'
      - '2024-2025' -> '2425'
      - '2425' -> '2425'
    """
    s = season.strip()
    if len(s) == 4 and s.isdigit():
        return s
    if "/" in s:
        a, b = s.split("/", 1)
        return a[-2:] + b[-2:]
    if "-" in s:
        a, b = s.split("-", 1)
        return a[-2:] + b[-2:]
    raise ValueError(f"Unrecognized season format: {season!r}")


def build_results_url(season: str, division_code: str) -> str:
    return f"{FOOTBALL_DATA_BASE}/{_season_path(season)}/{division_code}.csv"


def download_results_csv(
    *,
    storage: Storage,
    http: HttpClient,
    season: str,
    league: FootballDataLeague,
    force: bool = False,
) -> None:
    url = build_results_url(season, league.code)
    if (not force) and storage.has_url("football-data.co.uk", url):
        return

    status, content, final_url = http.get(url)
    filename = f"{league.code}.csv"
    subdir = _season_path(season)
    storage.save_bytes(
        source="football-data.co.uk",
        kind="csv",
        url=final_url,
        status_code=status,
        content=content,
        filename=filename,
        subdir=subdir,
    )


def download_poland_consolidated_csv(
    *,
    storage: Storage,
    http: HttpClient,
    force: bool = False,
) -> None:
    """All-season Ekstraklasa + odds CSV from football-data `new/` tree."""
    url = POLAND_HISTORICAL_CSV_URL
    if (not force) and storage.has_url("football-data.co.uk", url):
        return
    status, content, final_url = http.get(url)
    storage.save_bytes(
        source="football-data.co.uk",
        kind="csv",
        url=final_url,
        status_code=status,
        content=content,
        filename="POL.csv",
        subdir="new",
    )

