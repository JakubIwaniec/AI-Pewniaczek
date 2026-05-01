from __future__ import annotations

import re

from playwright.sync_api import sync_playwright


def main() -> None:
    url = "https://www.flashscore.pl/pilka-nozna/polska/pko-bp-ekstraklasa-2025-2026/wyniki/"
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        c = b.new_context(locale="pl-PL")
        page = c.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        # Inspect live DOM links
        hrefs = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.getAttribute('href')).slice(0, 50)",
        )
        print("sample hrefs:", hrefs[:20])
        html = page.content()
        b.close()

    print("len", len(html))
    for name, pat in [
        ("mecz", r"/mecz/([A-Za-z0-9]{8})/"),
        ("match", r"/match/([A-Za-z0-9]{8})/"),
        ("wcl-loadMore", r"wcl-loadMore"),
        ("eventId", r"eventId\\\":\\\"([A-Za-z0-9]{8})\\\""),
    ]:
        m = re.findall(pat, html)
        print(name, len(m), m[:5])


if __name__ == "__main__":
    main()

