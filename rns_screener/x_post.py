"""Posts a thread to X summarizing the day's classifications.

Uses OAuth 1.0a user-context auth (posting from your own account) - the
simplest path for a single-account bot, since it just needs the app's
own keys plus your own access token, no 3-legged OAuth flow.
"""
from __future__ import annotations

import os
import time

import truststore

truststore.inject_into_ssl()

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1

from .classify import Classification
from .director_dealings import DirectorDealing

load_dotenv()

X_API_URL = "https://api.x.com/2/tweets"
MAX_POST_CHARS = 280
POST_DELAY_SECONDS = 1.5  # be polite between posts in a thread

_EMOJI = {
    "STRONGLY_AHEAD": "\U0001F680",
    "AHEAD": "✅",
    "MIXED": "⚖️",
    "BELOW": "\U0001F53B",
}
_SECTION_ORDER = ["STRONGLY_AHEAD", "AHEAD", "MIXED", "BELOW"]


def _auth() -> OAuth1:
    return OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_KEY_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def _post(text: str, auth: OAuth1, in_reply_to: str | None = None) -> str:
    payload: dict = {"text": text}
    if in_reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": in_reply_to}

    resp = requests.post(X_API_URL, auth=auth, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _build_posts(
    classifications: list[Classification],
    director_dealings: list[DirectorDealing],
    watchlist: set[str],
    min_director_buy_value: float,
    date_str: str,
) -> list[str]:
    posts: list[str] = []

    counts = {
        label: sum(1 for c in classifications if c.classification == label)
        for label in _SECTION_ORDER
    }
    summary_bits = [f"{_EMOJI[label]}{count}" for label, count in counts.items() if count]
    intro = (
        f"RNS morning screen {date_str}: " + " ".join(summary_bits)
        if summary_bits
        else f"RNS morning screen {date_str}: nothing notable today."
    )
    posts.append(_truncate(intro, MAX_POST_CHARS))

    for label in _SECTION_ORDER:
        for c in classifications:
            if c.classification != label:
                continue
            body = f"{_EMOJI[label]} {c.company} ({c.ticker}): {c.summary}"
            posts.append(_truncate(body, MAX_POST_CHARS))

    watchlist_extra = [
        c
        for c in classifications
        if c.classification in ("IN_LINE", "NO_GUIDANCE") and c.ticker.upper() in watchlist
    ]
    for c in watchlist_extra:
        body = f"⭐ {c.company} ({c.ticker}) - {c.classification}: {c.summary}"
        posts.append(_truncate(body, MAX_POST_CHARS))

    buys = [
        d
        for d in director_dealings
        if d.direction == "buy" and (d.total_value_gbp or 0) >= min_director_buy_value
    ]
    for d in buys:
        value_str = f"£{d.total_value_gbp:,.0f}" if d.total_value_gbp else "value n/a"
        body = (
            f"\U0001F454 {d.announcement.company} ({d.announcement.ticker}): "
            f"{d.director_name} ({d.role}) bought {value_str}"
        )
        posts.append(_truncate(body, MAX_POST_CHARS))

    return posts


def post_thread(
    classifications: list[Classification],
    director_dealings: list[DirectorDealing],
    watchlist: set[str],
    min_director_buy_value: float,
    date_str: str,
) -> None:
    posts = _build_posts(classifications, director_dealings, watchlist, min_director_buy_value, date_str)
    if not posts:
        return

    auth = _auth()
    previous_id: str | None = None
    for text in posts:
        previous_id = _post(text, auth, in_reply_to=previous_id)
        time.sleep(POST_DELAY_SECONDS)
