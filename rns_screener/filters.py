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

from .fetcher import Announcement

RESULTS_KEYWORDS = ["trading", "results", "update", "guidance", "upgrade", "ahead"]
_RESULTS_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in RESULTS_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

_DIRECTOR_DEALING_PATTERN = re.compile(
    r"director[/\s]*pdmr\s+(shareholding|dealing)", re.IGNORECASE
)


def classify_headline(headline: str) -> str | None:
    """Return 'director_dealing', 'results_candidate', or None (drop)."""
    if _DIRECTOR_DEALING_PATTERN.search(headline):
        return "director_dealing"
    if _RESULTS_PATTERN.search(headline):
        return "results_candidate"
    return None


def prefilter(announcements: list[Announcement]) -> dict[str, list[Announcement]]:
    buckets: dict[str, list[Announcement]] = {"results_candidate": [], "director_dealing": []}
    for ann in announcements:
        category = classify_headline(ann.headline)
        if category:
            buckets[category].append(ann)
    return buckets
