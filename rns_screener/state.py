"""Tracks per-day processed announcement IDs and pending skipped X posts.

Persisted to small JSON files that get committed back to the repo (see
the GitHub Actions workflow's "Record state" step). This is what lets a
midday run know what an earlier run today already covered, and retry
any X posts that got rejected earlier - without needing to know or
care what time it's being called.
"""
from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_IDS_FILE = _REPO_ROOT / "processed_ids.json"
SKIPPED_POSTS_FILE = _REPO_ROOT / "skipped_x_posts.json"


def load_processed_ids(date_str: str) -> set[str]:
    if not PROCESSED_IDS_FILE.exists():
        return set()
    data = json.loads(PROCESSED_IDS_FILE.read_text(encoding="utf-8"))
    return set(data.get(date_str, []))


def save_processed_ids(date_str: str, ids: set[str]) -> None:
    # Only today's entry is kept - no need to accumulate history indefinitely.
    PROCESSED_IDS_FILE.write_text(
        json.dumps({date_str: sorted(ids)}, indent=2), encoding="utf-8"
    )


def load_skipped_posts() -> list[str]:
    if not SKIPPED_POSTS_FILE.exists():
        return []
    return json.loads(SKIPPED_POSTS_FILE.read_text(encoding="utf-8"))


def save_skipped_posts(posts: list[str]) -> None:
    SKIPPED_POSTS_FILE.write_text(json.dumps(posts, indent=2), encoding="utf-8")
