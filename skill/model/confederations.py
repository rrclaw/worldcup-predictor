"""Country → FIFA confederation lookup.

Loaded once at import time from `data/confederations.json` (see that file's
_meta block for source and naming convention). Unknown countries return None;
callers must treat None as "skip this match" rather than guessing.
"""
from __future__ import annotations

import json

from ..helpers import paths

_CONFED_FILE = paths.DATA / "confederations.json"
_CACHE: dict[str, str] | None = None


def _load() -> dict[str, str]:
    """Build a flat country -> confederation map. Cached after first call."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    raw = json.loads(_CONFED_FILE.read_text())
    flat: dict[str, str] = {}
    for confed, countries in raw.items():
        if confed.startswith("_"):
            continue
        for c in countries:
            flat[c] = confed
    _CACHE = flat
    return flat


def confederation(country: str) -> str | None:
    """Return the FIFA confederation code (UEFA/CONMEBOL/...) or None."""
    return _load().get(country)


def is_cross_confederation(home: str, away: str) -> bool:
    """True iff both teams are mapped AND belong to different confederations."""
    h, a = confederation(home), confederation(away)
    return h is not None and a is not None and h != a


def confed_pair(home: str, away: str) -> tuple[str | None, str | None]:
    """(home_confed, away_confed) — returns (None, None) if either side is unmapped."""
    return confederation(home), confederation(away)
