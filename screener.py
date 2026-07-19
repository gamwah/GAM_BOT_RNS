"""RNS "Ahead of Expectations" Screener - main entry point.

Usage:
  python screener.py                    # run for today (UK date)
  python screener.py --date YYYY-MM-DD  # run for a specific date
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from rns_screener.classify import classify_many
from rns_screener.config import load_config
from rns_screener.digest import build_digest
from rns_screener.director_dealings import extract_many
from rns_screener.fetcher import fetch_day_announcements
from rns_screener.filters import prefilter
from rns_screener.telegram import send_telegram_message


def run(date_str: str) -> None:
    config = load_config()
    watchlist = {t.upper() for t in config.get("watchlist", [])}
    min_director_buy_value = config.get("min_director_buy_value", 0)
    chat_id = config["telegram_chat_id"]

    print(f"Fetching announcements for {date_str} ...")
    announcements = fetch_day_announcements(date_str)
    print(f"  {len(announcements)} total announcements")

    if not announcements:
        is_weekend = datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5
        if not is_weekend:
            send_telegram_message(
                "⚠️ RNS screener: fetch returned zero announcements today. "
                "The source layout may have changed.",
                chat_id=chat_id,
            )
        else:
            print("Zero announcements, but it's a weekend - no alert sent (expected).")
        return

    buckets = prefilter(announcements)
    print(
        f"  {len(buckets['results_candidate'])} results candidates, "
        f"{len(buckets['director_dealing'])} director dealings"
    )

    classifications = classify_many(buckets["results_candidate"]) if buckets["results_candidate"] else []
    director_dealings = extract_many(buckets["director_dealing"]) if buckets["director_dealing"] else []

    digest = build_digest(classifications, director_dealings, watchlist, min_director_buy_value)
    print("\n--- Digest ---\n")
    print(digest)

    send_telegram_message(digest, chat_id=chat_id)
    print("\nSent to Telegram.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    run(args.date)
