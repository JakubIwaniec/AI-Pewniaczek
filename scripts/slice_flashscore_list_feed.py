"""Wycinanie z mega-listy x/feed bloków tur ZA zawierających substring (np. ścieżka ZL).

Usage (repo root):
  python scripts/slice_flashscore_list_feed.py \\
    --in data/raw/flashscore/feeds/f_1_-1_3_pl_1.txt \\
    --contains /pilka-nozna/europa/liga-mistrzow/ \\
    --out data/raw/flashscore/feeds/slices/liga_mistrzow_pl3.txt

Katalog feeds/slices/ jest objęty przez glob **/*.txt w manifeście integracji.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def slice_za_blocks(text: str, needle: str) -> str:
    if needle not in text:
        return ""
    chunks: list[str] = []
    pos = 0
    while True:
        idx = text.find("~ZA÷", pos)
        if idx == -1:
            break
        nxt = text.find("~ZA÷", idx + 3)
        block = text[idx:nxt] if nxt != -1 else text[idx:]
        if needle in block:
            chunks.append(block)
        pos = idx + 3
    return "".join(chunks).strip()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--contains", required=True)
    ap.add_argument("--out", required=True)
    ns = ap.parse_args(argv)
    src = Path(ns.inp)
    if not src.is_file():
        raise SystemExit(f"missing input {src}")
    blob = slice_za_blocks(src.read_text(encoding="utf-8", errors="replace"), ns.contains)
    dst = Path(ns.out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not blob:
        print("No matching ZA-blocks; skipping write.", flush=True)
        return 0
    dst.write_text(blob + "\n", encoding="utf-8")
    print(f"wrote {len(blob)} chars -> {dst}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
