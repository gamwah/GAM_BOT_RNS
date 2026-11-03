"""One-off catch-up: send a past day's digest to Telegram only (private chat + channel).

Usage: python catchup_send.py YYYY-MM-DD

Classifies everything for that day from scratch and sends the digest titled as
a catch-up. Does not post to X and does not touch processed_ids.json.
"""
from __future__ import annotations

import sys
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from rns_screener.classify import classify_many
from rns_screener.config import load_config
from rns_screener.digest import build_digest
from rns_screener.director_dealings import extract_many
from rns_screener.fetcher import fetch_day_announcements
from rns_screener.filters import prefilter
from rns_screener.telegram import channel_id, send_telegram_broadcast


def main(date_str: str) -> None:
    config = load_config()
    watchlist = {t.upper() for t in config.get("watchlist", [])}
    chat_id = config["telegram_chat_id"]

    buckets = prefilter(fetch_day_announcements(date_str))
    failures: list[tuple] = []
    classifications = classify_many(buckets["results_candidate"], failures=failures)
    dealings = extract_many(buckets["director_dealing"], failures=failures)
    if failures:
        sys.exit(f"{len(failures)} announcement(s) failed to analyse ({failures[0][1][:200]}); nothing sent.")

    label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %d %b")
    digest = build_digest(
        classifications, dealings, watchlist, config.get("min_director_buy_value", 0),
        title=f"RNS Screen - catch-up for {label}",
    )
    print(digest)
    destinations = [chat_id] + ([channel_id()] if channel_id() else [])
    failed = send_telegram_broadcast(digest, destinations)
    print("Sent to Telegram." if not failed else f"Sent with failures: {failed}")


if __name__ == "__main__":
    main(sys.argv[1])
