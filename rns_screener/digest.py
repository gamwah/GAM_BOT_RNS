"""Builds the Telegram digest text, ordered per the spec:

1. STRONGLY_AHEAD, 2. AHEAD, 3. MIXED, 4. BELOW, 5. director buys.
IN_LINE / NO_GUIDANCE are skipped unless the ticker is on the watchlist.
"""
from __future__ import annotations

import html
from collections import defaultdict

from .classify import Classification
from .director_dealings import DirectorDealing


def esc(text: str) -> str:
    """Escapes &, <, > for Telegram's HTML parse mode.

    Telegram's HTML parser chokes on any literal &, <, or > in the
    message text (outside our own <b>/<i> tags) - a clinical trial
    summary containing "p<0.0001" broke a real digest send this way.
    Quotes are deliberately left alone (quote=False): they're not part
    of tag syntax here, and Telegram doesn't decode &quot; back to ".
    """
    return html.escape(str(text), quote=False)


_SECTION_ORDER = [
    ("STRONGLY_AHEAD", "🚀", "Strongly Ahead"),
    ("AHEAD", "✅", "Ahead"),
    ("MIXED", "⚖️", "Mixed"),
    ("BELOW", "🔻", "Below (profit-warning alert)"),
]


def build_digest(
    classifications: list[Classification],
    director_dealings: list[DirectorDealing],
    watchlist: set[str],
    min_director_buy_value: float,
    title: str = "RNS Screen",
) -> str:
    lines: list[str] = [f"<b>{title}</b>", ""]
    has_content = False

    by_class: dict[str, list[Classification]] = defaultdict(list)
    for c in classifications:
        by_class[c.classification].append(c)

    for label, emoji, title in _SECTION_ORDER:
        items = by_class.get(label, [])
        if not items:
            continue
        has_content = True
        lines.append(f"{emoji} <b>{title}</b>")
        for c in items:
            lines.append(f"• <b>{esc(c.company)}</b> ({esc(c.ticker)}): {esc(c.summary)}")
            lines.append(f'  <i>"{esc(c.key_quote)}"</i>')
        lines.append("")

    watchlist_extra = [
        c
        for c in classifications
        if c.classification in ("IN_LINE", "NO_GUIDANCE") and c.ticker.upper() in watchlist
    ]
    if watchlist_extra:
        has_content = True
        lines.append("⭐ <b>Watchlist (always reported)</b>")
        for c in watchlist_extra:
            lines.append(
                f"• <b>{esc(c.company)}</b> ({esc(c.ticker)}) — {esc(c.classification)}: {esc(c.summary)}"
            )
        lines.append("")

    buys = [
        d
        for d in director_dealings
        if d.direction == "buy" and (d.total_value_gbp or 0) >= min_director_buy_value
    ]
    if buys:
        has_content = True
        buy_counts: dict[str, int] = defaultdict(int)
        for d in buys:
            buy_counts[d.announcement.ticker] += 1

        lines.append("👔 <b>Director Buys</b>")
        for d in buys:
            pack_star = " ⭐" if buy_counts[d.announcement.ticker] >= 2 else ""
            value_str = f"£{d.total_value_gbp:,.0f}" if d.total_value_gbp else "value n/a"
            shares_str = f"{d.shares:,}" if d.shares else "? "
            lines.append(
                f"• <b>{esc(d.announcement.company)}</b> ({esc(d.announcement.ticker)}){pack_star}: "
                f"{esc(d.director_name)} ({esc(d.role)}) bought {shares_str} shares, {value_str}"
            )
        lines.append("")

    if not has_content:
        lines.append("No notable announcements today.")

    return "\n".join(lines).strip()
