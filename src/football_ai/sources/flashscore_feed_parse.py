from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class FlashscoreEventRef:
    event_id: str
    tournament_path: str


def extract_event_ids_by_tournament_path(feed_text: str, tournament_path: str) -> List[str]:
    """
    Extract event IDs (~AA÷<id>) from a Flashscore x/feed payload, filtering
    by tournament path (the ZL path usually contains it).

    tournament_path example:
      '/pilka-nozna/polska/pko-bp-ekstraklasa/'
    """
    if not tournament_path.startswith("/"):
        tournament_path = "/" + tournament_path

    # Tournament blocks are separated by '~ZA÷<tournament name>' markers.
    blocks = feed_text.split("~ZA÷")
    ids: list[str] = []
    pat = re.compile(r"~AA÷([A-Za-z0-9]{8})")
    for b in blocks:
        if tournament_path not in b:
            continue
        ids.extend(pat.findall(b))

    # stable unique order
    seen = set()
    out: list[str] = []
    for x in ids:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def chunked(seq: Iterable[str], n: int) -> Iterable[list[str]]:
    buf: list[str] = []
    for x in seq:
        buf.append(x)
        if len(buf) >= n:
            yield buf
            buf = []
    if buf:
        yield buf

