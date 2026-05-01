from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RawArtifact:
    source: str
    kind: str  # e.g. "csv", "html", "json"
    url: str
    fetched_at: str
    status_code: int
    content_sha256: str
    rel_path: str  # path relative to data/raw


class Storage:
    def __init__(self, db_path: Path, raw_dir: Path) -> None:
        self.db_path = db_path
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    url TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    UNIQUE(source, url, content_sha256)
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_artifacts_source_url ON raw_artifacts(source, url);"
            )

    def has_url(self, source: str, url: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM raw_artifacts WHERE source = ? AND url = ? LIMIT 1;",
                (source, url),
            )
            return cur.fetchone() is not None

    def save_bytes(
        self,
        *,
        source: str,
        kind: str,
        url: str,
        status_code: int,
        content: bytes,
        filename: str,
        subdir: str,
        fetched_at: Optional[str] = None,
    ) -> RawArtifact:
        fetched_at = fetched_at or _utc_now_iso()
        digest = sha256_bytes(content)

        safe_source = source.replace("..", "").replace("\\", "_").replace("/", "_")
        safe_subdir = subdir.replace("..", "").replace("\\", "/").strip("/")
        out_dir = self.raw_dir / safe_source / safe_subdir
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / filename
        out_path.write_bytes(content)

        rel_path = str(out_path.relative_to(self.raw_dir)).replace("\\", "/")
        artifact = RawArtifact(
            source=source,
            kind=kind,
            url=url,
            fetched_at=fetched_at,
            status_code=status_code,
            content_sha256=digest,
            rel_path=rel_path,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO raw_artifacts
                    (source, kind, url, fetched_at, status_code, content_sha256, rel_path)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    artifact.source,
                    artifact.kind,
                    artifact.url,
                    artifact.fetched_at,
                    artifact.status_code,
                    artifact.content_sha256,
                    artifact.rel_path,
                ),
            )

        return artifact

