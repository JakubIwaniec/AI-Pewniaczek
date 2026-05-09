"""Text normalization used for deterministic joins (avoid fuzzy matchers)."""
from __future__ import annotations

import re
import unicodedata


_WS = re.compile(r"\s+", re.UNICODE)


def norm_club(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").strip()
    s = s.lower()
    s = _WS.sub(" ", s)
    return s


def strip_openfoot_country_suffix(text: str) -> str:
    """Remove trailing '(ENG)' etc. produced in openfootball datasets."""
    s = unicodedata.normalize("NFKC", text or "").strip()
    return re.sub(r"\s*\([A-Z]{2,3}(?:/[A-Za-z.]*)?\)\s*$", "", s).strip()
