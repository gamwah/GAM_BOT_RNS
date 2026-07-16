"""Manual test for Step 2: Claude classification.

Run with: python test_classify.py [YYYY-MM-DD]
Only classifies the first 3 results-candidates found, to keep the test cheap.
"""
import sys
from datetime import date

from rns_screener.classify import classify_many
from rns_screener.fetcher import fetch_day_announcements
from rns_screener.filters import prefilter


def main() -> None:
    date_str = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    print(f"Fetching + pre-filtering announcements for {date_str} ...")
    announcements = fetch_day_announcements(date_str)
    buckets = prefilter(announcements)
    candidates = buckets["results_candidate"][:3]

    if not candidates:
        print("No results candidates found for this date.")
        return

    print(f"Classifying {len(candidates)} announcements with Claude...\n")
    results = classify_many(candidates)

    for r in results:
        print(f"=== {r.company} ({r.ticker}) ===")
        print(f"  Headline: {r.announcement.headline}")
        print(f"  Classification: {r.classification} (confidence: {r.confidence})")
        print(f"  Guidance change: {r.guidance_change}")
        print(f"  Metrics ahead: {r.metrics_ahead}")
        print(f"  Key quote: {r.key_quote}")
        print(f"  Summary: {r.summary}")
        print()


if __name__ == "__main__":
    main()
