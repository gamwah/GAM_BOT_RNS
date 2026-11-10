# RNS Screener web app

A phone-installable web app (PWA) in `docs/`, served by GitHub Pages. Three tabs:

- **Results**: each day's classifications and director dealings, filterable and searchable.
- **Watchlist**: edit the watchlist, the headline pick-up keywords and the director-buy threshold,
  with a "test a headline" box that shows whether a headline would be caught.
- **Performance**: how "ahead" calls did against the FTSE All-Share after 1 day, 5 days, 1 month, 3 months.

## How the data gets there

| File (in `docs/data/`) | Written by |
|---|---|
| `results/YYYY-MM-DD.json`, `index.json` | `screener.py` on every run (`rns_screener/store.py`) |
| `backtest.json` | `backtest.py`, daily via `.github/workflows/backtest.yml` |
| `settings.json` | the app (via the GitHub API) or by hand; read by `screener.py` and overrides `config.yaml` for `watchlist`, `keywords`, `min_director_buy_value` |

## One-time setup

1. **Enable Pages:** repo Settings > Pages > Source: *Deploy from a branch* > `master` / `/docs`.
   The app is then at `https://gamwah.github.io/GAM_BOT_RNS/`.
2. **Install on your phone:** open that URL, then *Add to Home Screen* (iPhone: Share menu; Android: browser menu).
3. **Saving settings from the app:** create a
   [fine-grained token](https://github.com/settings/personal-access-tokens/new) restricted to this repo with
   *Contents: Read and write*, and paste it into the Watchlist tab once. It is stored only in that browser.
   Without it the app is read-only.

## Filling in history (optional)

Results only exist from the first run after this was added. To backfill past days (costs a few pence of
Anthropic credit per day) and measure them:

```
python backfill.py 2026-08-26 2026-11-06      # add --dealings for director buys too
pip install -r requirements-backtest.txt
python backtest.py
```

Then commit `docs/data/`. If yfinance fails with a certificate error on a PC with HTTPS-scanning antivirus,
point `CURL_CA_BUNDLE` at a PEM export of the Windows certificate store.
