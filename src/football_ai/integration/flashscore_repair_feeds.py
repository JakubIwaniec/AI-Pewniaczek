"""Shared parsing for selective Flashscore RAW repair (dataset-agnostic constants)."""

REPAIR_FEED_KINDS = frozenset({"li", "st", "sui"})


def parse_repair_feed_kinds(csv: str) -> frozenset[str]:
    parts = tuple(p.strip().lower() for p in csv.replace(" ", "").split(",") if p.strip())
    if not parts or parts == ("all",):
        return REPAIR_FEED_KINDS
    unk = [p for p in parts if p not in REPAIR_FEED_KINDS]
    if unk:
        raise ValueError(f"Unknown repair-feeds token(s): {unk}; use sui, st, li, or all")
    return frozenset(parts)
