#!/usr/bin/env python3
"""Filtruj wpisy ``lookup_miss_diagnosis_sample`` z RCA diag (np. ekstraklasa-2526).

Przykład::

  python scripts/rca_lookup_miss_filter.py \\
    --json data/integrated/integration_diag_rca_lookup_miss.json \\
    --dataset-prefix ekstraklasa"""
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
        default=ROOT / "data/integrated/integration_diag_rca_lookup_miss.json",
        help="Plik RCA (diag bez skip próbki).",
    )
    ap.add_argument(
        "--dataset-prefix",
        default="ekstraklasa",
        help="Substring ``dataset_label`` (np. ekstraklasa-2526).",
    )
    args = ap.parse_args()
    p = Path(args.json)
    if not p.is_file():
        sys.stderr.write(f"Brak pliku: {p}\n")
        return 2
    blob = json.loads(p.read_text(encoding="utf-8"))
    sample = blob.get("lookup_miss_diagnosis_sample") or []
    if not isinstance(sample, list):
        sys.stderr.write("Brak listy lookup_miss_diagnosis_sample.\n")
        return 3
    pref = args.dataset_prefix
    hits = [
        row
        for row in sample
        if isinstance(row, dict)
        and pref in str(row.get("dataset_label", ""))
    ]
    for row in hits:
        print(json.dumps(row, ensure_ascii=False))
    if not hits:
        sys.stderr.write(f"Brak wierszy dla dataset zawierającego '{pref}'.\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
