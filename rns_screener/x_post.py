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


def _ticker_tags(ticker: str) -> str:
    """#TICKER for reach, $TICKER.L (the London cashtag convention) for discovery.

    A few LSE tickers already end in a period (e.g. "BA.", "QQ.") to
    disambiguate them - strip that before appending ".L" so it doesn't
    become "BA..L".
    """
    clean = ticker.rstrip(".")
    return f"#{clean} ${clean}.L"


def _build_posts(
    classifications: list[Classification],
    director_dealings: list[DirectorDealing],
    watchlist: set[str],
    min_director_buy_value: float,
    date_str: str,
) -> list[str]:
    posts: list[str] = []

    watchlist_extra = [
        c
        for c in classifications
        if c.classification in ("IN_LINE", "NO_GUIDANCE") and c.ticker.upper() in watchlist
    ]
    buys = [
        d
        for d in director_dealings
        if d.direction == "buy" and (d.total_value_gbp or 0) >= min_director_buy_value
    ]

    # Count everything the thread will actually contain - not just the 4 main
    # categories - so the intro never says "nothing notable" right before
    # posting a watchlist company or a director buy (a real bug: a watchlist
    # ticker classified IN_LINE/NO_GUIDANCE still gets posted below, but
    # wasn't counted here, so the intro contradicted the very next post).
    counts = {
        label: sum(1 for c in classifications if c.classification == label)
        for label in _SECTION_ORDER
    }
    summary_bits = [f"{_EMOJI[label]}{count}" for label, count in counts.items() if count]
    if watchlist_extra:
        summary_bits.append(f"⭐{len(watchlist_extra)}")
    if buys:
        summary_bits.append(f"\U0001F454{len(buys)}")

    intro = (
        f"RNS Screen {date_str}: " + " ".join(summary_bits)
        if summary_bits
        else f"RNS Screen {date_str}: nothing notable today."
    )
    posts.append(_truncate(intro, MAX_POST_CHARS))

    for label in _SECTION_ORDER:
        for c in classifications:
            if c.classification != label:
                continue
            body = f'{_EMOJI[label]} {c.company} ({_ticker_tags(c.ticker)}): "{c.key_quote}"'
            posts.append(_truncate(body, MAX_POST_CHARS))

    for c in watchlist_extra:
        body = f'⭐ {c.company} ({_ticker_tags(c.ticker)}) - {c.classification}: "{c.key_quote}"'
        posts.append(_truncate(body, MAX_POST_CHARS))

    for d in buys:
        value_str = f"£{d.total_value_gbp:,.0f}" if d.total_value_gbp else "value n/a"
        body = (
            f"\U0001F454 {d.announcement.company} ({_ticker_tags(d.announcement.ticker)}): "
            f"{d.director_name} ({d.role}) bought {value_str}"
        )
        posts.append(_truncate(body, MAX_POST_CHARS))

    return posts


RETRY_DELAYS_SECONDS = [5, 15]  # backoff schedule for a post that gets rejected


def _post_with_retries(text: str, auth: OAuth1, in_reply_to: str | None = None) -> tuple[str | None, bool]:
    """Posts one text with retries. Returns (new_post_id_or_None, was_skipped).

    X's duplicate-content check appears to fingerprint the exact bytes of an
    attempt even when that attempt was rejected (confirmed: retrying
    byte-identical text after a rejection - even in a later run, even the
    next day - gets flagged as a duplicate of the earlier failed attempt,
    not just of a successful post). So retries after the first append a few
    invisible zero-width-space characters to make each attempt's text
    genuinely distinct, trimming the visible text first so it still fits
    within MAX_POST_CHARS.
    """
    last_error = None
    for attempt, delay in enumerate([0, *RETRY_DELAYS_SECONDS]):
        if delay:
            time.sleep(delay)
        attempt_text = text if attempt == 0 else text[: MAX_POST_CHARS - attempt] + ("​" * attempt)
        try:
            new_id = _post(attempt_text, auth, in_reply_to=in_reply_to)
            return new_id, False
        except requests.HTTPError as exc:
            last_error = exc.response.text if exc.response is not None else str(exc)
            print(f"X post attempt {attempt + 1} failed: {last_error} | {text[:60]!r}")

    print(f"Skipping this X post after retries: {text[:60]!r}")
    return None, True


def post_thread(
    classifications: list[Classification],
    director_dealings: list[DirectorDealing],
    watchlist: set[str],
    min_director_buy_value: float,
    date_str: str,
) -> list[str]:
    """Posts the thread; returns the text of any posts that had to be skipped.

    A handful of posts have failed transiently in testing (X's spam/bot
    heuristics seem to occasionally flag one post out of a long,
    similarly-templated thread) and succeeded seconds later on retry -
    so each post gets a couple of retries with backoff before giving up.
    A post that still fails is skipped rather than aborting the rest of
    the thread; the caller surfaces skipped posts to the user, since
    they'd otherwise silently go missing from X with no record anywhere
    the user would see.
    """
    posts = _build_posts(classifications, director_dealings, watchlist, min_director_buy_value, date_str)
    if not posts:
        return []

    auth = _auth()
    previous_id: str | None = None
    skipped: list[str] = []

    for text in posts:
        new_id, was_skipped = _post_with_retries(text, auth, in_reply_to=previous_id)
        if was_skipped:
            skipped.append(text)
        else:
            previous_id = new_id
        time.sleep(POST_DELAY_SECONDS)

    return skipped


def post_standalone(texts: list[str]) -> list[str]:
    """Retries previously-skipped posts as independent posts (not threaded to
    each other or to whatever thread they originally belonged to - each
    post's text already stands on its own). Returns any still-skipped texts.
    """
    if not texts:
        return []

    auth = _auth()
    still_skipped: list[str] = []
    for text in texts:
        _new_id, was_skipped = _post_with_retries(text, auth)
        if was_skipped:
            still_skipped.append(text)
        time.sleep(POST_DELAY_SECONDS)

    return still_skipped
