from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    data_dir: Path
    raw_dir: Path
    db_path: Path


def get_paths() -> ProjectPaths:
    # Works both when run from repo root and when installed as a package.
    # We resolve relative to current working directory because this is a hobby
    # project and we want data to land in the workspace folder.
    root = Path.cwd()
    data_dir = root / "data"
    raw_dir = data_dir / "raw"
    db_path = data_dir / "football_ai.sqlite"
    return ProjectPaths(root=root, data_dir=data_dir, raw_dir=raw_dir, db_path=db_path)

