"""Sends the digest to Telegram via the Bot API."""
from __future__ import annotations

import os

import truststore

truststore.inject_into_ssl()

import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_CHUNK_CHARS = 3800  # Telegram's limit is 4096; leave headroom


def _chunk(text: str, size: int) -> list[str]:
    lines = text.split("\n")
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > size and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_telegram_message(text: str, chat_id: str, bot_token: str | None = None) -> None:
    token = bot_token or os.environ["TELEGRAM_BOT_TOKEN"]
    for chunk in _chunk(text, MAX_CHUNK_CHARS):
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram send failed: {data}")
