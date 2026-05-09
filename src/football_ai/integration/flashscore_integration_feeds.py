"""Resolve ordered Flashscore list-feed RAW .txt files for AA meta indexing."""
from __future__ import annotations

import json
from pathlib import Path


MANIFEST_NAME = "flashscore_list_feed_manifest.json"


def default_manifest_path(repo_root: Path) -> Path:
    return repo_root / "data" / "integrated" / MANIFEST_NAME


def feed_output_path(feeds_dir: Path, feed_key: str, filename: str | None) -> Path:
    fname = filename or (feed_key.replace("/", "_") + ".txt")
    return feeds_dir / fname


def _safe_glob_txt(feeds_dir: Path, sub_glob: str) -> list[Path]:
    if not feeds_dir.is_dir():
        return []
    if sub_glob == "**/*.txt":
        return sorted(feeds_dir.rglob("*.txt"))
    return sorted(feeds_dir.glob(sub_glob))


def load_manifest(repo_root: Path) -> dict | None:
    mp = default_manifest_path(repo_root)
    if not mp.exists():
        return None
    try:
        return json.loads(mp.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON manifest {mp}: {e}") from e


def ordered_feed_txt_paths(
    *,
    repo_root: Path,
    raw_flashscore_dir: Path,
    only_tags: frozenset[str] | None = None,
) -> tuple[list[Path], str]:
    """Ascending (priority, path): last file wins duplicate event_id in build_event_meta_index."""
    feeds_dir = raw_flashscore_dir / "feeds"
    manifest = load_manifest(repo_root)
    if manifest is None:
        files = _safe_glob_txt(feeds_dir, "**/*.txt")
        return files, "no_manifest_all_feeds_rglob"

    wild = int(manifest.get("wildcard_priority") or 50)
    priority_by_resolved: dict[Path, int] = {}

    for ent in manifest.get("download") or []:
        fk = str(ent.get("feed_key") or "").strip()
        if not fk:
            continue
        tags = {str(t) for t in (ent.get("tags") or [])}
        if only_tags is not None and tags and not (tags & only_tags):
            continue
        fn_opt = ent.get("filename")
        filename = None if fn_opt in (None, "") else str(fn_opt)
        outp = feed_output_path(feeds_dir, fk, filename)
        pr = int(ent.get("priority") if ent.get("priority") is not None else wild)
        priority_by_resolved[outp] = max(priority_by_resolved.get(outp, pr), pr)

    for sub in manifest.get("include_feed_subdir_globs") or ["**/*.txt"]:
        for p in _safe_glob_txt(feeds_dir, str(sub)):
            if p.is_file() and p.suffix.lower() == ".txt":
                priority_by_resolved.setdefault(p, wild)

    scored = [(p, prio) for p, prio in priority_by_resolved.items()]
    scored.sort(key=lambda t: (t[1], str(t[0]).lower()))
    ordered = [p for t in scored for p in [t[0]] if p.exists()]
    note = f"manifest_wild={wild}_count={len(ordered)}"
    return ordered, note


def seed_augment_html_paths(raw_flashscore_dir: Path) -> list[Path]:
    """Cached HTML usable with ``iter_match_meta_from_feed`` (~AA÷ in page or embedded data)."""
    if not raw_flashscore_dir.is_dir():
        return []
    seeds = sorted(raw_flashscore_dir.glob("**/seed/*.html"))
    sr = raw_flashscore_dir / "seed_results"
    extra = sorted(sr.glob("*.html")) if sr.is_dir() else []
    return seeds + extra
