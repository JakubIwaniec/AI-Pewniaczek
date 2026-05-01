from __future__ import annotations

"""
Flashscore module (RAW downloader).

This file intentionally starts as a thin scaffold:
- Flashscore pages and selectors change.
- Some pages are JS-rendered / protected.

We treat Flashscore as a *raw acquisition* source:
store HTML (or extracted JSON fragments if available) + metadata, and parse later.
"""

from dataclasses import dataclass

from football_ai.http import HttpClient
from football_ai.storage import Storage


@dataclass(frozen=True)
class FlashscoreConfig:
    base_url: str = "https://www.flashscore.pl"
    min_delay_s: float = 2.0
    # Flashscore uses a project-specific ninja host; for flashscore.pl we observed:
    #   https://3.flashscore.ninja/3/x/feed/<feed>
    ninja_base: str = "https://3.flashscore.ninja/3"
    x_fsign: str = "SW9D1eZo"


def download_url_raw(
    *,
    storage: Storage,
    http: HttpClient,
    url: str,
    subdir: str,
    filename: str,
    force: bool = False,
) -> None:
    if (not force) and storage.has_url("flashscore", url):
        return

    status, content, final_url = http.get(url)
    storage.save_bytes(
        source="flashscore",
        kind="html",
        url=final_url,
        status_code=status,
        content=content,
        filename=filename,
        subdir=subdir,
    )


def download_feed_raw(
    *,
    storage: Storage,
    http: HttpClient,
    feed: str,
    subdir: str,
    filename: str | None = None,
    force: bool = False,
    config: FlashscoreConfig | None = None,
) -> None:
    """
    Download Flashscore x/feed raw payload.
    This is usually the most stable way to acquire match lists / details.
    """
    cfg = config or FlashscoreConfig()
    url = f"{cfg.ninja_base}/x/feed/{feed}"
    if (not force) and storage.has_url("flashscore", url):
        return

    status, content, final_url = http.get(url, headers={"x-fsign": cfg.x_fsign})
    fname = filename or (feed.replace("/", "_") + ".txt")
    storage.save_bytes(
        source="flashscore",
        kind="text",
        url=final_url,
        status_code=status,
        content=content,
        filename=fname,
        subdir=subdir,
    )

