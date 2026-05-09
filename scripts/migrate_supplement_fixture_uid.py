"""Back-fill ``fixture_uid`` on supplement.sqlite (additive column + row updates).

Usage (from repo root):
  python scripts/migrate_supplement_fixture_uid.py
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_ai.integration.supplement_store import (  # noqa: E402
    backfill_fixture_uids,
    ensure_db,
)

DB_DEFAULT = ROOT / "data" / "integrated" / "supplement.sqlite"


def main() -> int:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_DEFAULT
    ensure_db(db)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = db.with_suffix(f".sqlite.bak-{stamp}")
    shutil.copy2(db, bak)
    print(f"Backup: {bak}", flush=True)
    n = backfill_fixture_uids(db)
    print(f"Updated fixture_uid on {n} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
