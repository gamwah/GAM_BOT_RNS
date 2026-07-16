"""Classifies results/trading announcements against expectations via Claude.

Uses Claude's structured-outputs feature (output_config.format) rather than
free-text JSON + fence-stripping: it guarantees a schema-valid response,
which removes the parse-failure/retry path a plain-text-JSON prompt needs.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import anthropic
from dotenv import load_dotenv

from .fetcher import Announcement, fetch_article_text

load_dotenv()

MODEL_DAILY = "claude-haiku-4-5"
MODEL_BACKFILL_CHECK = "claude-sonnet-4-6"
MAX_WORDS = 800
MAX_PARALLEL = 8

SYSTEM_PROMPT = """You are an analyst screening UK RNS announcements. Classify the company's stated
performance versus expectations.

Classifications:
- "STRONGLY_AHEAD": materially/significantly/substantially/comfortably ahead of
  expectations; guidance upgraded; record results explicitly beating forecasts.
- "AHEAD": ahead of / above / better than / exceeding market, board, or analyst
  expectations; "slightly ahead"; "at the upper end of the range".
- "IN_LINE": in line with expectations; "consistent with"; "on track".
- "MIXED": one metric ahead, another in line or below (e.g. revenue ahead,
  profit in line). Specify which in the summary.
- "BELOW": below / behind / short of expectations; guidance lowered; profit warning;
  "no longer expects to meet".
- "NO_GUIDANCE": results reported with no comparison to expectations.

Catch ALL phrasings that mean better than expected, including but not limited to:
"ahead of expectations", "ahead of market expectations", "ahead of board
expectations", "materially ahead", "significantly ahead", "comfortably ahead",
"well ahead", "substantially ahead", "exceeds expectations", "above expectations",
"better than expected", "outperforming", "upgraded guidance", "raises guidance",
"raises full-year outlook", "upper end of expectations", "beats forecasts",
"record results" (only when tied to beating expectations). Judge meaning, not
just keywords - a phrase you have not seen before that clearly means results
beat expectations should still be classified AHEAD or STRONGLY_AHEAD.

Beware negation and hedging: "no longer ahead", "was ahead but now expects",
"ahead of prior year" (that is year-on-year growth, NOT ahead of expectations
unless expectations are also referenced)."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "company": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": ["STRONGLY_AHEAD", "AHEAD", "IN_LINE", "MIXED", "BELOW", "NO_GUIDANCE"],
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "key_quote": {"type": "string"},
        "summary": {"type": "string"},
        "metrics_ahead": {"type": "array", "items": {"type": "string"}},
        "guidance_change": {
            "type": "string",
            "enum": ["upgraded", "maintained", "lowered", "none_stated"],
        },
    },
    "required": [
        "ticker",
        "company",
        "classification",
        "confidence",
        "key_quote",
        "summary",
        "metrics_ahead",
        "guidance_change",
    ],
    "additionalProperties": False,
}

_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment


@dataclass
class Classification:
    announcement: Announcement
    ticker: str
    company: str
    classification: str
    confidence: str
    key_quote: str
    summary: str
    metrics_ahead: list[str]
    guidance_change: str


def _truncate_words(text: str, max_words: int) -> str:
    return " ".join(text.split()[:max_words])


def classify_announcement(announcement: Announcement, model: str = MODEL_DAILY) -> Classification:
    full_text = fetch_article_text(announcement)
    excerpt = _truncate_words(full_text, MAX_WORDS)

    user_content = (
        f"Company: {announcement.company}\n"
        f"Ticker: {announcement.ticker}\n"
        f"Headline: {announcement.headline}\n\n"
        f"{excerpt}"
    )

    response = _client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
        messages=[{"role": "user", "content": user_content}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    return Classification(announcement=announcement, **data)


def classify_many(announcements: list[Announcement], model: str = MODEL_DAILY) -> list[Classification]:
    """Classify announcements concurrently (spec calls for 5-10 parallel requests)."""
    results: list[Classification] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {pool.submit(classify_announcement, ann, model): ann for ann in announcements}
        for future in as_completed(futures):
            ann = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                print(f"Classification failed for {ann.company} ({ann.ticker}): {exc}")
    return results
