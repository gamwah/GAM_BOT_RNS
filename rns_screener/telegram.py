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


def send_telegram_message(
    text: str, chat_id: str, bot_token: str | None = None, parse_mode: str | None = "HTML"
) -> None:
    """parse_mode="HTML" expects text with pre-escaped &/</> outside of intentional
    <b>/<i> tags (see rns_screener.digest.esc). Pass parse_mode=None for plain-text
    alerts that interpolate raw AI-generated content and have no formatting to
    preserve - simpler and safer than escaping content nobody needs escaped.
    """
    token = bot_token or os.environ["TELEGRAM_BOT_TOKEN"]
    for chunk in _chunk(text, MAX_CHUNK_CHARS):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram send failed: {data}")


def channel_id() -> str | None:
    """Optional second destination for the digest (a private channel others can
    subscribe to). Unset/blank means private-chat-only, exactly as before."""
    return (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip() or None


def describe_error(exc: Exception) -> str:
    """Short, token-free description of a send failure. str(exc) for an
    HTTPError includes the full request URL, which contains the bot token."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            detail = resp.json().get("description", "")
        except Exception:
            detail = ""
        return f"HTTP {resp.status_code}: {detail or resp.reason}"
    return type(exc).__name__


def send_telegram_broadcast(
    text: str,
    chat_ids: list[str],
    bot_token: str | None = None,
    parse_mode: str | None = "HTML",
) -> list[tuple[str, str]]:
    """Sends the same message to every chat_id, independently - one failing
    doesn't stop the others. Returns [(chat_id, error description)] for the
    ones that failed. Raises only if *every* destination failed, so a total
    delivery failure still aborts the run (and the announcements stay
    unprocessed) the way a single failed send always did.
    """
    failed: list[tuple[str, str]] = []
    last_exc: Exception | None = None
    for cid in chat_ids:
        try:
            send_telegram_message(text, chat_id=cid, bot_token=bot_token, parse_mode=parse_mode)
        except Exception as exc:
            last_exc = exc
            failed.append((cid, describe_error(exc)))
            print(f"Telegram send to {cid} failed: {describe_error(exc)}")
    if len(failed) == len(chat_ids) and last_exc is not None:
        raise last_exc
    return failed
