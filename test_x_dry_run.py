"""Dry run for the X posting feature: builds the thread text but never
calls the X API, so you can review it before spending any real credits.

Run with: python test_x_dry_run.py [YYYY-MM-DD]
"""
import sys
from datetime import date

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from rns_screener.classify import classify_many
from rns_screener.config import load_config
from rns_screener.director_dealings import extract_many
from rns_screener.fetcher import fetch_day_announcements
from rns_screener.filters import prefilter
from rns_screener.x_post import _build_posts, MAX_POST_CHARS


def main() -> None:
    date_str = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    config = load_config()
    watchlist = {t.upper() for t in config.get("watchlist", [])}
    min_director_buy_value = config.get("min_director_buy_value", 0)

    print(f"Fetching + classifying announcements for {date_str} ...")
    announcements = fetch_day_announcements(date_str)
    buckets = prefilter(announcements)

    classifications = classify_many(buckets["results_candidate"]) if buckets["results_candidate"] else []
    director_dealings = extract_many(buckets["director_dealing"]) if buckets["director_dealing"] else []

    posts = _build_posts(classifications, director_dealings, watchlist, min_director_buy_value, date_str)

    print(f"\n=== Would post {len(posts)} tweets (thread), est. cost ${len(posts) * 0.015:.3f} ===\n")
    for i, text in enumerate(posts, 1):
        over = " [OVER LIMIT!]" if len(text) > MAX_POST_CHARS else ""
        print(f"--- Post {i}/{len(posts)} ({len(text)} chars){over} ---")
        print(text)
        print()


if __name__ == "__main__":
    main()
