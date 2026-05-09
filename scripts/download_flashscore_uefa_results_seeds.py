"""Download UEFA ``/wyniki/`` HTML from Flashscore.pl into ``seed_results`` (embedded ``~AA÷`` AA-meta).

Uses the same HttpClient throttling as other fetchers. Run before
``build_integration_supplement.py`` / ``download_openfootball_allowlist.py`` when mega-list
feeds omit UEFA event rows.

Usage (from repo root):
  python scripts/download_flashscore_uefa_results_seeds.py
  python scripts/download_flashscore_uefa_results_seeds.py --force
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import data_integrity_flashscore as di  # noqa: E402

from football_ai.http import HttpClient  # noqa: E402
from football_ai.integration.flashscore_uefa_results_seed import pol_wyniki_results_url  # noqa: E402

UEFA_INTERNAL_KEYS = frozenset({"liga_mistrzow", "liga_europy", "liga_konferencji"})
OUT_DIR = ROOT / "data" / "raw" / "flashscore" / "seed_results"


def _ds_split(ds: str) -> tuple[str, str]:
    i = ds.rfind("-")
    return ds[:i], ds[i + 1 :]


def main(argv: list[str]) -> int:
    force = "--force" in argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = HttpClient(min_delay_s=1.0)
    fetched = reused = errors = 0
    tasks: dict[Path, str] = {}
    for dlabel, _ids_name, _base in di.league_manifest():
        leigh, seas4 = _ds_split(dlabel)
        if leigh not in UEFA_INTERNAL_KEYS:
            continue
        url = pol_wyniki_results_url(leigh, seas4)
        outp = OUT_DIR / f"{leigh}_{seas4}_wyniki.html"
        tasks[outp] = url

    for outp, url in sorted(tasks.items(), key=lambda t: str(t[0])):
        if outp.exists() and outp.stat().st_size > 0 and not force:
            reused += 1
            continue
        status, blob, final_url = client.get(url)
        txt = blob.decode("utf-8", errors="replace")
        if status != 200 or "~AA÷" not in txt:
            print(f"[skip] HTTP {status} or no AA segments: {final_url}", flush=True)
            errors += 1
            continue
        outp.write_text(txt, encoding="utf-8")
        fetched += 1
        print("saved", outp.name, flush=True)

    print(
        f"UEFA wyniki HTML: fetched={fetched} reused_existing={reused} problems={errors} dir={OUT_DIR}",
        flush=True,
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
