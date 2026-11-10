"""Cheap, no-LLM pre-filter over a day's announcement headlines.

Splits announcements into two buckets worth caring about:
- "results_candidate": headlines that might contain an
  ahead-of/in-line-with/below-expectations statement, to send to Claude.
- "director_dealing": PDMR dealing notices, handled separately (buy/sell
  direction and values get parsed from the full text later, not classified).
Everything else is dropped before it ever reaches the Claude API.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .fetcher import Announcement

RESULTS_KEYWORDS = ["trading", "results", "update", "guidance", "upgrade", "ahead", "statement", "profit", "outlook"]


@lru_cache(maxsize=8)
def _results_pattern(keywords: tuple[str, ...]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b", re.IGNORECASE)


def _pattern_for(keywords: list[str] | None) -> re.Pattern:
    """Pattern for the given keywords (blank entries ignored). Falls back to the
    built-in list if none are supplied, so a wiped list can't silently turn the
    screener off."""
    cleaned = tuple(k.strip() for k in (keywords or []) if k and k.strip())
    return _results_pattern(cleaned or tuple(RESULTS_KEYWORDS))


_DIRECTOR_DEALING_PATTERN = re.compile(
    r"director[/\s]*pdmr\s+(shareholding|dealing)", re.IGNORECASE
)


def classify_headline(headline: str, keywords: list[str] | None = None) -> str | None:
    """Return 'director_dealing', 'results_candidate', or None (drop).

    `keywords` overrides the built-in list (the web app edits it via settings.json).
    """
    if _DIRECTOR_DEALING_PATTERN.search(headline):
        return "director_dealing"
    if _pattern_for(keywords).search(headline):
        return "results_candidate"
    return None


def prefilter(
    announcements: list[Announcement], keywords: list[str] | None = None
) -> dict[str, list[Announcement]]:
    buckets: dict[str, list[Announcement]] = {"results_candidate": [], "director_dealing": []}
    for ann in announcements:
        category = classify_headline(ann.headline, keywords)
        if category:
            buckets[category].append(ann)
    return buckets
