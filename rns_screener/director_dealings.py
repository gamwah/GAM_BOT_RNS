"""Extracts director/PDMR dealing details (direction, size, value) via Claude.

The pre-filter only flags headlines as "director_dealing" — it doesn't know
whether it was a buy or sell, or how large. That structured extraction
happens here, on the (much smaller) director-dealing subset.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import anthropic
from dotenv import load_dotenv

from .fetcher import Announcement, fetch_article_text

load_dotenv()

MODEL = "claude-haiku-4-5"
MAX_WORDS = 600
MAX_PARALLEL = 8

SYSTEM_PROMPT = """Extract director/PDMR dealing details from this UK RNS announcement.
Report the primary transaction described; if several are listed, summarize the largest one.
"direction" is "buy" for open-market purchases/acquisitions of shares, "sell" for disposals,
or "other" for anything without a simple cash buy/sell (option exercises with no purchase,
gifts, scheme awards vesting, etc). If a field isn't stated, use null."""

SCHEMA = {
    "type": "object",
    "properties": {
        "director_name": {"type": "string"},
        "role": {"type": "string"},
        "direction": {"type": "string", "enum": ["buy", "sell", "other"]},
        "shares": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "price_per_share_gbp": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "total_value_gbp": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    "required": [
        "director_name",
        "role",
        "direction",
        "shares",
        "price_per_share_gbp",
        "total_value_gbp",
    ],
    "additionalProperties": False,
}

_client = anthropic.Anthropic()


@dataclass
class DirectorDealing:
    announcement: Announcement
    director_name: str
    role: str
    direction: str
    shares: int | None
    price_per_share_gbp: float | None
    total_value_gbp: float | None


def extract_director_dealing(announcement: Announcement) -> DirectorDealing:
    text = fetch_article_text(announcement)
    excerpt = " ".join(text.split()[:MAX_WORDS])

    response = _client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": f"Company: {announcement.company}\nTicker: {announcement.ticker}\n\n{excerpt}",
            }
        ],
    )

    body = next(b.text for b in response.content if b.type == "text")
    data = json.loads(body)
    return DirectorDealing(announcement=announcement, **data)


def extract_many(announcements: list[Announcement]) -> list[DirectorDealing]:
    results: list[DirectorDealing] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {pool.submit(extract_director_dealing, a): a for a in announcements}
        for future in as_completed(futures):
            ann = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                print(f"Director dealing extraction failed for {ann.company}: {exc}")
    return results
