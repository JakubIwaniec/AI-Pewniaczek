from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import Page, Response, sync_playwright


@dataclass(frozen=True)
class CollectConfig:
    headless: bool = True
    timeout_ms: int = 60_000
    storage_state_path: Optional[Path] = None
    user_data_dir: Optional[Path] = None
    debug_dir: Optional[Path] = None
    # After scrolling/load-more we can persist page HTML for AA blocks (supplement seed).
    wyniki_html_out: Optional[Path] = None


EVENT_ID_RE = re.compile(r"~AA÷([A-Za-z0-9]{8})")


def init_storage_state(*, url: str, out_path: Path, user_data_dir: Optional[Path] = None) -> None:
    """
    Open a headed browser so the user can accept cookie consent / pass any checks.
    Saves Playwright storage state (cookies + localStorage) to out_path.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        if user_data_dir:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=False,
                locale="pl-PL",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
        else:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                locale="pl-PL",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
        context.add_init_script(
            """
            // Basic stealth patches (best-effort).
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['pl-PL','pl','en-US','en']});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            """
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        # Give time to interact manually (cookie banner / consent / anti-bot).
        # While waiting, try to detect that match list is actually visible.
        for _ in range(240):  # ~8 minutes
            page.wait_for_timeout(2000)
            # If we can already see match links, we can finish early.
            try:
                if page.locator('a[href*="/mecz/"]').count() > 0:
                    break
            except Exception:
                pass
        context.storage_state(path=str(out_path))
        context.close()


def _click_show_more(page: Page) -> bool:
    """
    Try to click 'Show more matches' button on tournament results page.
    Returns True if clicked, False if button not found/clickable.
    """
    # On many Flashscore tournament pages, the button has data-testid="wcl-loadMore"
    loc = page.locator('[data-testid="wcl-loadMore"]')
    if loc.count() == 0:
        return False
    try:
        loc.first.click(timeout=2_000)
        return True
    except Exception:
        return False


def collect_match_ids_from_results_page(
    *,
    url: str,
    max_clicks: int = 500,
    config: Optional[CollectConfig] = None,
) -> List[str]:
    cfg = config or CollectConfig()
    with sync_playwright() as p:
        if cfg.user_data_dir:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(cfg.user_data_dir),
                headless=cfg.headless,
                locale="pl-PL",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
        else:
            browser = p.chromium.launch(headless=cfg.headless)
            context = browser.new_context(
                locale="pl-PL",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                storage_state=str(cfg.storage_state_path) if cfg.storage_state_path else None,
            )
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['pl-PL','pl','en-US','en']});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            """
        )
        page = context.new_page()
        page.set_default_timeout(cfg.timeout_ms)

        captured_event_ids: list[str] = []
        debug_urls: list[str] = []
        debug_hits: list[str] = []

        def on_response(resp: Response) -> None:
            try:
                url = resp.url
                if "pq_graphql" not in url and "/x/feed/" not in url:
                    return
                debug_urls.append(url)
                # Only small text payloads are interesting here.
                ct = resp.headers.get("content-type", "")
                if "text" not in ct and "json" not in ct and "javascript" not in ct:
                    return
                body = resp.text()
                aa = EVENT_ID_RE.findall(body)
                if aa:
                    debug_hits.append(url)
                captured_event_ids.extend(aa)
            except Exception:
                # best-effort capture
                return

        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded")

        # Try to force-load more content: scroll + "show more" clicks.
        page.wait_for_timeout(5000)
        for _ in range(30):
            try:
                page.mouse.wheel(0, 4000)
            except Exception:
                pass
            page.wait_for_timeout(600)

        clicks = 0
        while clicks < max_clicks:
            clicked = _click_show_more(page)
            if not clicked:
                break
            clicks += 1
            page.wait_for_timeout(800)

        # Primary: eventIds are embedded in scripts as '~AA÷<eventId>'
        html = page.content()
        ids: list[str] = EVENT_ID_RE.findall(html)
        # Fallback: captured from network responses
        if not ids and captured_event_ids:
            ids = captured_event_ids

        if cfg.debug_dir:
            cfg.debug_dir.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(cfg.debug_dir / "page.png"), full_page=True)
            except Exception:
                pass
            try:
                (cfg.debug_dir / "page.html").write_text(page.content(), encoding="utf-8", errors="ignore")
            except Exception:
                pass
            (cfg.debug_dir / "responses.txt").write_text("\n".join(debug_urls) + "\n", encoding="utf-8")
            (cfg.debug_dir / "hit_responses.txt").write_text("\n".join(debug_hits) + "\n", encoding="utf-8")
            (cfg.debug_dir / "captured_ids.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")

        if cfg.wyniki_html_out is not None:
            cfg.wyniki_html_out.parent.mkdir(parents=True, exist_ok=True)
            cfg.wyniki_html_out.write_text(page.content(), encoding="utf-8", errors="ignore")

        context.close()

    # stable unique order
    seen = set()
    out: list[str] = []
    for x in ids:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

