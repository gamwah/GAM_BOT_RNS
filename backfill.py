"""Fills docs/data/results/ for past dates, so the app's history and the
backtest have something to work with. Sends nothing to Telegram or X and does
not touch processed_ids.json / skipped_x_posts.json.

Usage:
  python backfill.py 2026-08-26 2026-11-06            # weekdays in range, results only
  python backfill.py 2026-08-26 2026-11-06 --dealings # also extract director dealings
  python backfill.py 2026-11-03 2026-11-03 --force    # redo a date that already has results

Needs ANTHROPIC_API_KEY (reads .env). Costs real API credits: roughly a few
pence per day of announcements with Haiku. Dates that already have a results
file are skipped unless --force is given, so it is safe to re-run after an
interruption.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from rns_screener.classify import classify_many
from rns_screener.config import load_config
from rns_screener.director_dealings import extract_many
from rns_screener.fetcher import fetch_day_announcements
from rns_screener.filters import prefilter
from rns_screener.store import results_path, save_results


def weekdays(start: date, end: date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("start", type=date.fromisoformat)
    parser.add_argument("end", type=date.fromisoformat)
    parser.add_argument("--dealings", action="store_true", help="also extract director dealings")
    parser.add_argument("--force", action="store_true", help="redo dates that already have results")
    args = parser.parse_args()

    config = load_config()
    watchlist = {t.upper() for t in config.get("watchlist", [])}
    keywords = config.get("keywords")

    total_failures = 0
    for day in weekdays(args.start, args.end):
        date_str = day.isoformat()
        if results_path(date_str).exists() and not args.force:
            print(f"{date_str}: already has results, skipping")
            continue

        announcements = fetch_day_announcements(date_str)
        if not announcements:
            print(f"{date_str}: no announcements (holiday?)")
            continue

        buckets = prefilter(announcements, keywords)
        failures: list[tuple] = []
        classifications = classify_many(buckets["results_candidate"], failures=failures)
        dealings = extract_many(buckets["director_dealing"], failures=failures) if args.dealings else []
        total_failures += len(failures)

        save_results(date_str, classifications, dealings, watchlist)
        print(
            f"{date_str}: {len(announcements)} announcements -> {len(classifications)} classified"
            + (f", {len(dealings)} dealings" if args.dealings else "")
            + (f", {len(failures)} FAILED" if failures else ""),
            flush=True,
        )

    if total_failures:
        print(f"\n{total_failures} announcement(s) failed to classify; re-run with --force for the affected dates.")


if __name__ == "__main__":
    main()
