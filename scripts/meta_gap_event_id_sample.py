#!/usr/bin/env python3
"""Wypisz próbkę ``event_id`` z braku meta (Tier-1 RAW gate).

Źródło: pola ``skipped_no_meta_event_id_sample_by_dataset`` w wygenerowanym
``integration_diag_latest.json``. Uruchom wcześniej::

  python scripts/integration_diag.py -F --skip-lookup-miss-sample --footballcsv-cache-fallback

Następnie sprawdź w ``data/raw/flashscore/feeds/*.txt``, czy dany ``event_id``
w ogóle występuje w pobranych mega-listach/slice."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--json",
        type=Path,
        default=ROOT / "data" / "integrated" / "integration_diag_latest.json",
        help="Ścieżka do artefaktu integration_diag.",
    )
    ap.add_argument(
        "--dataset",
        metavar="LBL",
        help="Filtr substringów ``dataset_label`` (np. laliga-2526); domyślnie wszystkie ze próbki.",
    )
    args = ap.parse_args()
    path = Path(args.json)
    if not path.is_file():
        sys.stderr.write(f"Brak pliku: {path}\n")
        return 2
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"Nie da się odczytać JSON: {exc}\n")
        return 2
    raw = blob.get("skipped_no_meta_event_id_sample_by_dataset")
    if raw is None:
        sys.stderr.write(
            "Pole skipped_no_meta_event_id_sample_by_dataset nie istnieje — "
            "odśwież integration_diag scripts/integration_diag.py (nowszy output).\n"
        )
        return 3
    if not isinstance(raw, dict):
        sys.stderr.write("Niepoprawny typ skipped_no_meta_event_id_sample_by_dataset.\n")
        return 3
    filt = args.dataset.strip() if isinstance(args.dataset, str) and args.dataset.strip() else None
    total = 0
    any_out = False
    for dsl in sorted(raw.keys()):
        if filt is not None and filt not in dsl:
            continue
        lst = raw.get(dsl)
        if not isinstance(lst, list) or not lst:
            continue
        print(f"# {dsl} ({len(lst)} próbek)")
        for eid in lst:
            if isinstance(eid, str) and eid.strip():
                print(eid.strip())
                total += 1
                any_out = True
            else:
                print("(invalid sample entry)")
    if filt and not any_out:
        sys.stderr.write(f"Brak dopasowań dla filtra dataset zawierającego '{filt}'.\n")
        return 1
    if not any_out:
        skipped = int(blob.get("supplement_counters", {}).get("skipped_no_meta") or 0)  # type: ignore[union-attr]
        if skipped == 0:
            print("# skipped_no_meta=0 — brak próbek do sprawdzenia w RAW.")
        else:
            sys.stderr.write(
                "skipped_no_meta>0 ale brak pola próbek — uruchom ponownie integration_diag.py.\n"
            )
            return 3
        return 0
    sys.stderr.write(f"# Łącznie {total} ID (sprawdź literalnie w plikach feeds pod data/raw/).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
