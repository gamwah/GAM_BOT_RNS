"""Persists every classification to JSON so the web app (docs/) can show history.

Layout, all under docs/data/ (served as-is by GitHub Pages):
  results/YYYY-MM-DD.json   that day's classifications and director dealings
  index.json                list of dates that have results, newest first

A day can be written several times (morning + midday runs); entries are keyed
by announcement id, so re-saving never duplicates and later runs just add.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .classify import Classification
from .director_dealings import DirectorDealing

DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"
RESULTS_DIR = DATA_DIR / "results"
INDEX_FILE = DATA_DIR / "index.json"

_COUNTED = ("STRONGLY_AHEAD", "AHEAD", "MIXED", "BELOW")


def results_path(date_str: str, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"{date_str}.json"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _base(ann) -> dict:
    return {
        "id": ann.id,
        "time": ann.time,
        "company": ann.company,
        "ticker": ann.ticker,
        "headline": ann.headline,
        "url": ann.url,
    }


def _result_row(c: Classification, watchlist: set[str]) -> dict:
    return {
        **_base(c.announcement),
        "classification": c.classification,
        "confidence": c.confidence,
        "key_quote": c.key_quote,
        "summary": c.summary,
        "metrics_ahead": c.metrics_ahead,
        "guidance_change": c.guidance_change,
        "watchlist": c.announcement.ticker.upper() in watchlist,
    }


def _dealing_row(d: DirectorDealing) -> dict:
    return {
        **_base(d.announcement),
        "director_name": d.director_name,
        "role": d.role,
        "direction": d.direction,
        "shares": d.shares,
        "price_per_share_gbp": d.price_per_share_gbp,
        "total_value_gbp": d.total_value_gbp,
    }


def _merge(existing: list[dict], new: list[dict]) -> list[dict]:
    by_id = {row["id"]: row for row in existing}
    by_id.update({row["id"]: row for row in new})
    return sorted(by_id.values(), key=lambda r: r["id"])


def _day_counts(day: dict) -> dict:
    counts = {label: 0 for label in _COUNTED}
    for row in day.get("results", []):
        if row["classification"] in counts:
            counts[row["classification"]] += 1
    counts["buys"] = sum(1 for d in day.get("dealings", []) if d.get("direction") == "buy")
    return counts


def _update_index(date_str: str, day: dict, index_file: Path) -> None:
    try:
        index = json.loads(index_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {}
    days = {entry["date"]: entry for entry in index.get("dates", [])}
    days[date_str] = {"date": date_str, "counts": _day_counts(day)}
    _write_json(
        index_file,
        {
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dates": sorted(days.values(), key=lambda e: e["date"], reverse=True),
        },
    )


def save_results(
    date_str: str,
    classifications: list[Classification],
    director_dealings: list[DirectorDealing],
    watchlist: set[str],
    results_dir: Path = RESULTS_DIR,
    index_file: Path = INDEX_FILE,
) -> None:
    path = results_path(date_str, results_dir)
    try:
        day = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        day = {}

    day["date"] = date_str
    day["results"] = _merge(day.get("results", []), [_result_row(c, watchlist) for c in classifications])
    day["dealings"] = _merge(day.get("dealings", []), [_dealing_row(d) for d in director_dealings])

    _write_json(path, day)
    _update_index(date_str, day, index_file)
