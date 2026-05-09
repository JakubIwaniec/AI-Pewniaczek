from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS supplement (
    dataset TEXT NOT NULL,
    event_id TEXT NOT NULL,
    source TEXT NOT NULL,
    unix_kickoff INTEGER,
    home_name TEXT NOT NULL,
    away_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    match_uid TEXT,
    fixture_uid TEXT,
    PRIMARY KEY (dataset, event_id, source)
);

CREATE INDEX IF NOT EXISTS idx_supplement_source ON supplement(source);
"""


def _migrate(con: sqlite3.Connection) -> None:
    cols = {row[1] for row in con.execute("PRAGMA table_info(supplement);")}
    if "match_uid" not in cols:
        con.execute("ALTER TABLE supplement ADD COLUMN match_uid TEXT;")
    if "fixture_uid" not in cols:
        con.execute("ALTER TABLE supplement ADD COLUMN fixture_uid TEXT;")
    con.execute("CREATE INDEX IF NOT EXISTS idx_supplement_match_uid ON supplement(match_uid);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_supplement_fixture_uid ON supplement(fixture_uid);")


def ensure_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.executescript(SCHEMA_SQL)
        _migrate(con)
        con.commit()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def upsert_supplement_row(
    db_path: Path,
    *,
    dataset: str,
    event_id: str,
    source: str,
    unix_kickoff: int | None,
    home_name: str,
    away_name: str,
    payload: dict,
    match_uid: str | None = None,
    fixture_uid: str | None = None,
) -> None:
    ensure_db(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            INSERT INTO supplement(dataset,event_id,source,unix_kickoff,home_name,away_name,payload_json,created_at,match_uid,fixture_uid)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(dataset,event_id,source) DO UPDATE SET
              unix_kickoff=excluded.unix_kickoff,
              home_name=excluded.home_name,
              away_name=excluded.away_name,
              payload_json=excluded.payload_json,
              created_at=excluded.created_at,
              match_uid=COALESCE(excluded.match_uid, supplement.match_uid),
              fixture_uid=COALESCE(excluded.fixture_uid, supplement.fixture_uid);
            """,
            (
                dataset,
                event_id,
                source,
                unix_kickoff,
                home_name,
                away_name,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                utc_now_iso(),
                match_uid,
                fixture_uid,
            ),
        )
        con.commit()


def has_supplement_for(db_path: Path, dataset: str, event_id: str, source_prefix: str) -> bool:
    if not db_path.exists():
        return False
    like = source_prefix + "%"
    with sqlite3.connect(db_path) as con:
        row = con.execute(
            "SELECT 1 FROM supplement WHERE dataset=? AND event_id=? AND source LIKE ? LIMIT 1;",
            (dataset, event_id, like),
        ).fetchone()
        return row is not None



def backfill_fixture_uids(db_path: Path) -> int:
    """Set ``fixture_uid`` on rows where kickoff/club names permit recompute."""
    from football_ai.integration.match_identity import compute_fixture_uid

    if not db_path.exists():
        return 0
    ensure_db(db_path)
    updated = 0
    with sqlite3.connect(db_path) as con:
        rows = con.execute(
            "SELECT rowid, unix_kickoff, home_name, away_name, fixture_uid "
            "FROM supplement WHERE fixture_uid IS NULL OR trim(fixture_uid) = '';"
        ).fetchall()
        for rowid, ts, hm, aw, _ in rows:
            f = compute_fixture_uid(unix_kickoff=ts, home_name=hm, away_name=aw)
            if f:
                con.execute("UPDATE supplement SET fixture_uid=? WHERE rowid=?;", (f, rowid))
                updated += 1
        con.commit()
    return updated


