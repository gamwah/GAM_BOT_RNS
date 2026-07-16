"""Manual test for Step 1: fetch + pre-filter today's announcements.

Run with: python test_fetch.py [YYYY-MM-DD]
Defaults to today (UK date).
"""
import sys
from datetime import date

from rns_screener.fetcher import fetch_day_announcements, fetch_article_text
from rns_screener.filters import prefilter


def main() -> None:
    date_str = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    print(f"Fetching announcements for {date_str} ...")
    announcements = fetch_day_announcements(date_str)
    print(f"Total announcements found: {len(announcements)}\n")

    buckets = prefilter(announcements)

    print(f"=== Results candidates ({len(buckets['results_candidate'])}) ===")
    for ann in buckets["results_candidate"]:
        print(f"  {ann.time} | {ann.company} ({ann.ticker}) | {ann.headline}")
        print(f"    {ann.url}")

    print(f"\n=== Director/PDMR dealings ({len(buckets['director_dealing'])}) ===")
    for ann in buckets["director_dealing"]:
        print(f"  {ann.time} | {ann.company} ({ann.ticker}) | {ann.headline}")

    if buckets["results_candidate"]:
        first = buckets["results_candidate"][0]
        print(f"\n=== Sample full article text for: {first.company} - {first.headline} ===")
        text = fetch_article_text(first)
        print(text[:1000])
        print(f"... [{len(text)} chars total]")


if __name__ == "__main__":
    main()
