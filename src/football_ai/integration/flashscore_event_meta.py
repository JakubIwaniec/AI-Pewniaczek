"""Unified Flashscore event meta (mega-feed union + HTML seed augmentation)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from football_ai.integration.flashscore_integration_feeds import (
    ordered_feed_txt_paths,
    seed_augment_html_paths,
)
from football_ai.sources.flashscore_feed_match_meta import (
    FlashscoreMatchMeta,
    augment_meta_index_from_seed_html,
    build_event_meta_union,
)


@dataclass(frozen=True)
class FlashscoreEventMetaBundle:
    index: dict[str, FlashscoreMatchMeta]
    feed_note: str
    augment_seed_count: int
    feeds_used_paths: tuple[Path, ...]
    seed_paths_used: tuple[Path, ...]


def load_flashscore_event_meta_bundle(
    *,
    repo_root: Path,
    raw_flashscore_dir: Path,
) -> FlashscoreEventMetaBundle:
    feeds, feed_note = ordered_feed_txt_paths(
        repo_root=repo_root,
        raw_flashscore_dir=raw_flashscore_dir,
    )
    ix: dict[str, FlashscoreMatchMeta] = {}
    if feeds:
        ix = build_event_meta_union(feeds)
    seeds = seed_augment_html_paths(raw_flashscore_dir)
    augment_seed_count = augment_meta_index_from_seed_html(ix, seeds)
    return FlashscoreEventMetaBundle(
        index=ix,
        feed_note=feed_note,
        augment_seed_count=augment_seed_count,
        feeds_used_paths=tuple(feeds),
        seed_paths_used=tuple(seeds),
    )


def meta_source_fingerprint(
    bundle: FlashscoreEventMetaBundle,
    *,
    repo_root: Path,
) -> dict:
    repo_res = repo_root.resolve()

    def stat_entry(path: Path) -> dict[str, object]:
        try:
            st = path.stat()
            rel = ""
            try:
                rel = str(path.resolve().relative_to(repo_res))
            except ValueError:
                rel = str(path.resolve())
            return {"path": rel, "size": st.st_size, "mtime_ns": st.st_mtime_ns}
        except OSError:
            return {"path": str(path), "size": None, "mtime_ns": None}

    return {
        "feed_note": bundle.feed_note,
        "augment_seed_count": bundle.augment_seed_count,
        "feed_files": [stat_entry(p) for p in bundle.feeds_used_paths],
        "seed_html_files": [stat_entry(p) for p in bundle.seed_paths_used],
    }
