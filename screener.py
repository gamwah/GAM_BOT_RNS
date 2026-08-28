"""RNS "Ahead of Expectations" Screener - main entry point.

Usage:
  python screener.py                    # run for today (UK date)
  python screener.py --date YYYY-MM-DD  # run for a specific date

Safe to call more than once on the same day (e.g. a 7:15am run and a
12:15pm follow-up): each run only processes announcements it hasn't
seen yet today, and also retries any X posts that got skipped earlier
in the day - see rns_screener/state.py.
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
from rns_screener.state import load_processed_ids, load_skipped_posts, save_processed_ids, save_skipped_posts
from rns_screener.telegram import send_telegram_message
from rns_screener.x_post import post_standalone, post_thread


def run(date_str: str) -> None:
    config = load_config()
    watchlist = {t.upper() for t in config.get("watchlist", [])}
    min_director_buy_value = config.get("min_director_buy_value", 0)
    chat_id = config["telegram_chat_id"]

    processed_ids = load_processed_ids(date_str)
    is_first_run_today = not processed_ids
    pending_x_posts = load_skipped_posts()

    print(f"Fetching announcements for {date_str} ...")
    announcements = fetch_day_announcements(date_str)
    print(f"  {len(announcements)} total announcements")

    if not announcements:
        if is_first_run_today:
            is_weekend = datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5
            if not is_weekend:
                send_telegram_message(
                    "⚠️ RNS screener: fetch returned zero announcements today. "
                    "The source layout may have changed.",
                    chat_id=chat_id,
                    parse_mode=None,
                )
            else:
                print("Zero announcements, but it's a weekend - no alert sent (expected).")
        else:
            print("No announcements found on a later pass - nothing to do.")
        return

    buckets = prefilter(announcements)
    new_results = [a for a in buckets["results_candidate"] if a.id not in processed_ids]
    new_dealings = [a for a in buckets["director_dealing"] if a.id not in processed_ids]
    print(
        f"  {len(new_results)} new results candidates, {len(new_dealings)} new director dealings "
        f"({len(buckets['results_candidate'])}/{len(buckets['director_dealing'])} total today, "
        f"rest already processed earlier today)"
    )

    if not new_results and not new_dealings and not pending_x_posts:
        print("Nothing new since the last run today, and no pending X retries - nothing to do.")
        return

    classifications = classify_many(new_results) if new_results else []
    director_dealings = extract_many(new_dealings) if new_dealings else []

    if classifications or director_dealings:
        title = "RNS Morning Digest" if is_first_run_today else "RNS Update (new since last run today)"
        digest = build_digest(classifications, director_dealings, watchlist, min_director_buy_value, title=title)
        print(f"\n--- {title} ---\n")
        print(digest)
        send_telegram_message(digest, chat_id=chat_id)
        print("\nSent to Telegram.")
    else:
        print("Nothing new to report this pass (only pending X retries below).")

    newly_skipped: list[str] = []
    try:
        if classifications or director_dealings:
            newly_skipped = post_thread(
                classifications, director_dealings, watchlist, min_director_buy_value, date_str
            )
        if pending_x_posts:
            print(f"Retrying {len(pending_x_posts)} previously skipped X post(s)...")
            still_skipped = post_standalone(pending_x_posts)
            recovered = len(pending_x_posts) - len(still_skipped)
            if recovered:
                print(f"  {recovered} of them posted successfully this time.")
            pending_x_posts = still_skipped
        print("Posted to X.")
    except Exception as exc:
        print(f"X posting failed (Telegram digest already sent OK): {exc}")

    if newly_skipped:
        skipped_list = "\n".join(f"- {text}" for text in newly_skipped)
        send_telegram_message(
            f"⚠️ {len(newly_skipped)} post(s) didn't make it to X (X rejected them after retries - "
            f"likely its bot/spam filter, not a code issue). Will retry automatically on the next "
            f"run today. Full content below in case you want to post it manually in the meantime:"
            f"\n\n{skipped_list}",
            chat_id=chat_id,
            parse_mode=None,
        )

    processed_ids |= {a.id for a in new_results} | {a.id for a in new_dealings}
    save_processed_ids(date_str, processed_ids)
    save_skipped_posts(pending_x_posts + newly_skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    run(args.date)
