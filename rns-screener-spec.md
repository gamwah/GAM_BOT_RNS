# RNS "Ahead of Expectations" Screener — Build Spec

## Goal
A daily agent that reviews UK RNS announcements each morning, classifies results/trading
statements by whether performance is ahead of / in line with / below expectations, and
delivers a digest. Also supports a historical backfill mode for backtesting.

## Architecture Overview
1. **Fetch** — pull the morning's RNS announcements (or a historical date range).
2. **Pre-filter** — keep only relevant announcement categories.
3. **Classify** — send each announcement's headline + opening text to the Claude API.
4. **Deliver** — Telegram message (or email) digest by ~8:00am UK time.
5. **Store** — append every classification to a local SQLite DB / CSV for backtesting.

Run via GitHub Actions scheduled workflow (cron: `30 6 * * 1-5` UTC ≈ 7:30am UK,
adjust for BST) so no server is needed. Store API keys as GitHub Secrets.

## 1. Data Source
- Primary: **Investegate** (investegate.co.uk) — free, publishes RNS announcements.
  - RSS feeds filterable by category, plus a date-browseable archive for backfill.
  - Scrape politely: identify User-Agent, rate-limit requests, cache pages.
- Fallback: London Stock Exchange news explorer.
- Most RNSs drop at 07:00 UK time; a 07:30 run catches nearly all.

## 2. Pre-filter (cheap, no LLM)
Keep announcements in these categories:
- Final Results / Annual Results
- Interim / Half-year Results
- Trading Statement / Trading Update
- Quarterly Results
- Profit guidance / outlook statements (sometimes filed under "Miscellaneous" —
  also keyword-match headlines for: "trading", "results", "update", "guidance",
  "upgrade", "ahead")

Separately, ALSO capture (do not classify, just list in digest):
- **Director/PDMR Dealings** ("Director/PDMR Shareholding") — flag BUYS only,
  with director name, role, number of shares, price, and total value.
  Highlight clusters (2+ directors buying the same stock within 5 trading days —
  "pack trades").

Optional filter: restrict to AIM + FTSE Small Cap / Fledgling, or a watchlist of
tickers supplied in a config file.

## 3. Claude API Classification

Model: `claude-haiku-4-5` for daily runs (cheap); `claude-sonnet-4-6` for backfill
accuracy checks if desired.

Send: company name, ticker, headline, and the first ~800 words of the announcement
(the expectations language is nearly always in the headline or opening paragraphs).

### System prompt (use verbatim or refine)

```
You are an analyst screening UK RNS announcements. Classify the company's stated
performance versus expectations. Respond ONLY with valid JSON, no markdown fences.

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
just keywords — a phrase you have not seen before that clearly means results
beat expectations should still be classified AHEAD or STRONGLY_AHEAD.

Beware negation and hedging: "no longer ahead", "was ahead but now expects",
"ahead of prior year" (that is year-on-year growth, NOT ahead of expectations
unless expectations are also referenced).

JSON schema:
{
  "ticker": string,
  "company": string,
  "classification": "STRONGLY_AHEAD" | "AHEAD" | "IN_LINE" | "MIXED" | "BELOW" | "NO_GUIDANCE",
  "confidence": "high" | "medium" | "low",
  "key_quote": string,        // the exact sentence driving the classification, max 30 words
  "summary": string,          // one line, plain English
  "metrics_ahead": [string],  // e.g. ["revenue", "EBITDA"]
  "guidance_change": "upgraded" | "maintained" | "lowered" | "none_stated"
}
```

### API call notes
- Parse response with fence-stripping + try/except; on parse failure, retry once
  with "Respond ONLY with JSON" appended.
- Batch: classify announcements concurrently (5–10 parallel) to keep the run fast.

## 4. Digest & Delivery
Telegram bot message (or email), ordered:
1. 🚀 STRONGLY_AHEAD (with key quote)
2. ✅ AHEAD
3. ⚖️ MIXED
4. 🔻 BELOW (useful for holdings — early profit-warning alert)
5. 👔 Director buys (name, size, value, ⭐ for pack trades)
Skip IN_LINE and NO_GUIDANCE unless the ticker is on the watchlist (config file:
always report watchlist tickers regardless of classification).

## 5. Historical Backfill Mode
`python screener.py --backfill 2023-01-01 2026-07-01`
- Iterate Investegate's date archive, apply the same filter + classification.
- Rate-limit scraping (1–2 req/sec) and cache raw pages locally so re-runs are free.
- Store all results in SQLite: date, ticker, classification, quote, category.

### Backtest extension
- Pull historical daily prices via `yfinance` (append ".L" to LSE tickers).
- For each STRONGLY_AHEAD / AHEAD announcement, compute forward returns at
  +1d, +5d, +1m, +3m, +6m vs FTSE All-Share benchmark.
- Output a summary table: does "materially ahead" outperform "slightly ahead"?
  Do AIM names react differently to main-market names? Does the drift persist
  past day one (post-earnings-announcement drift)?

## 6. Config file (config.yaml)
```yaml
watchlist: [CTO, RFX, GTLY, IPF, MTRO, HOC]   # always report these
markets: [AIM, FTSE_SMALL_CAP]                 # or "all"
min_director_buy_value: 20000                  # GBP, ignore token buys
telegram_chat_id: "..."
run_time_uk: "07:30"
```

## 7. Costs & housekeeping
- Haiku classification of ~30 announcements/day: pennies per month.
- Backfill of 3 years ≈ 15–20k classifications: roughly a few pounds with Haiku.
- Log every run; alert via Telegram if the fetch returns zero announcements
  (source layout may have changed).
- Respect Investegate robots.txt / ToS; keep request rates low.

## Build order for Claude Code
1. Fetcher + pre-filter for today's announcements (test on a live morning).
2. Claude classification with the prompt above + JSON parsing.
3. Telegram delivery + config file.
4. GitHub Actions workflow with secrets.
5. Backfill mode + SQLite storage.
6. Backtest module with yfinance.
