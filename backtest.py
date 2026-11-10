"""Does an "ahead of expectations" call actually lead to outperformance?

Reads every classification saved in docs/data/results/, pulls daily prices from
Yahoo Finance (LSE tickers get ".L" appended), and writes docs/data/backtest.json
for the web app's Performance tab.

How returns are measured (daily closes only, so this is a rough guide):
  * base  = close of the trading day BEFORE the announcement date. RNS lands
            at 7am, so this is roughly what you'd pay buying at the open.
  * +1d   = announcement-day close (the day-one reaction)
  * +5d / +1m / +3m = close 5 / 21 / 63 trading days in (counting the
            announcement day as day 1)
  * excess = stock return minus the FTSE All-Share over the same window
A horizon that hasn't elapsed yet is left blank and ignored in the averages.

Usage:  python backtest.py
Needs:  pip install -r requirements-backtest.txt
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "docs" / "data"
RESULTS_DIR = DATA_DIR / "results"
OUT_FILE = DATA_DIR / "backtest.json"

BENCHMARKS = ["^FTAS", "^FTSE"]  # first one that returns data is used
CLASSES = ["STRONGLY_AHEAD", "AHEAD", "MIXED", "BELOW"]
HORIZONS = {"1d": 1, "5d": 5, "1m": 21, "3m": 63}
MAX_GAP_DAYS = 5  # ignore if the first price is this long after the announcement (suspended?)


def yahoo_symbol(ticker: str) -> str:
    """Investegate tickers map to Yahoo as TICKER.L; a few LSE tickers end in a
    period ("BA.") to disambiguate, which Yahoo doesn't want doubled up."""
    return ticker.strip().rstrip(".").upper() + ".L"


def load_events(results_dir: Path = RESULTS_DIR) -> list[dict]:
    seen: dict[str, dict] = {}
    for path in sorted(results_dir.glob("*.json")):
        day = json.loads(path.read_text(encoding="utf-8"))
        for row in day.get("results", []):
            if row.get("classification") in CLASSES and row.get("ticker"):
                seen[row["id"]] = {
                    "id": row["id"],
                    "date": day["date"],
                    "ticker": row["ticker"],
                    "company": row["company"],
                    "classification": row["classification"],
                    "key_quote": row.get("key_quote", ""),
                    "url": row.get("url", ""),
                }
    return sorted(seen.values(), key=lambda e: (e["date"], e["id"]), reverse=True)


def forward_returns(stock: pd.Series, bench: pd.Series, ann_date: date) -> dict | None:
    """Returns {"returns": {...}, "excess": {...}} (None where a horizon hasn't
    elapsed), or None if there's no usable price history around the date."""
    idx = stock.index
    t = idx.searchsorted(pd.Timestamp(ann_date))  # first trading day on/after the announcement
    if t < 1 or t >= len(idx):
        return None
    if (idx[t] - pd.Timestamp(ann_date)).days > MAX_GAP_DAYS:
        return None

    base = float(stock.iloc[t - 1])
    bench_base = bench.asof(idx[t - 1])
    if base <= 0 or pd.isna(bench_base):
        return None

    returns: dict[str, float | None] = {}
    excess: dict[str, float | None] = {}
    for label, k in HORIZONS.items():
        pos = t + k - 1
        if pos >= len(idx):
            returns[label] = excess[label] = None
            continue
        stock_ret = float(stock.iloc[pos]) / base - 1
        bench_end = bench.asof(idx[pos])
        returns[label] = round(stock_ret, 4)
        excess[label] = None if pd.isna(bench_end) else round(stock_ret - (float(bench_end) / float(bench_base) - 1), 4)
    return {"returns": returns, "excess": excess}


def summarise(events: list[dict]) -> dict:
    summary: dict[str, dict] = {}
    for cls in CLASSES:
        rows = [e for e in events if e["classification"] == cls and e.get("returns")]
        per_horizon = {}
        for label in HORIZONS:
            rets = [e["returns"][label] for e in rows if e["returns"][label] is not None]
            exs = [e["excess"][label] for e in rows if e["excess"][label] is not None]
            per_horizon[label] = (
                {
                    "n": len(exs),
                    "avg_return": round(mean(rets), 4),
                    "avg_excess": round(mean(exs), 4),
                    "median_excess": round(median(exs), 4),
                    "hit_rate": round(sum(1 for x in exs if x > 0) / len(exs), 3),
                }
                if exs
                else {"n": 0}
            )
        summary[cls] = per_horizon
    return summary


def _fetch_closes(symbol: str, start: date, end: date) -> pd.Series | None:
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
    except Exception as exc:
        print(f"  {symbol}: fetch failed ({str(exc)[:80]})")
        return None
    if hist is None or hist.empty:
        return None
    closes = hist["Close"].dropna()
    closes.index = closes.index.tz_localize(None).normalize()
    return closes[~closes.index.duplicated(keep="last")]


def run(results_dir: Path = RESULTS_DIR, out_file: Path = OUT_FILE) -> dict:
    events = load_events(results_dir)
    print(f"{len(events)} classified events to measure")
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not events:
        out = {"generated": generated, "benchmark": None, "horizons": list(HORIZONS), "events": [],
               "summary": summarise([]), "missing": []}
        out_file.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
        return out

    start = date.fromisoformat(min(e["date"] for e in events)) - timedelta(days=10)
    end = date.today() + timedelta(days=1)

    bench = bench_name = None
    for name in BENCHMARKS:
        bench = _fetch_closes(name, start, end)
        if bench is not None:
            bench_name = name
            break
    if bench is None:
        raise SystemExit("Could not fetch a benchmark index from Yahoo Finance - leaving backtest.json unchanged.")

    prices: dict[str, pd.Series | None] = {}
    missing: set[str] = set()
    for ev in events:
        symbol = yahoo_symbol(ev["ticker"])
        if symbol not in prices:
            prices[symbol] = _fetch_closes(symbol, start, end)
            time.sleep(0.2)
        closes = prices[symbol]
        result = forward_returns(closes, bench, date.fromisoformat(ev["date"])) if closes is not None else None
        if result is None:
            missing.add(ev["ticker"])
            ev["returns"] = ev["excess"] = None
        else:
            ev.update(result)

    out = {
        "generated": generated,
        "benchmark": bench_name,
        "horizons": list(HORIZONS),
        "events": events,
        "summary": summarise(events),
        "missing": sorted(missing),
    }
    out_file.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    measured = sum(1 for e in events if e.get("returns"))
    print(f"Measured {measured}/{len(events)} events vs {bench_name}; no price data for: {sorted(missing) or 'none'}")
    return out


if __name__ == "__main__":
    run()
