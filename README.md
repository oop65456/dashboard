# signal-dashboard

A free, read-only dashboard of buy / sell / hold signals for stocks, GLD, crypto and PAXG,
with forex and macro data as context. **It never places orders**; you trade yourself in the Alpaca app.
Plan: "Signal Dashboard - Final Plan" doc.

This project is fully self-contained: it never reads or changes anything outside this folder,
and it is the only thing that goes to GitHub. Your agent and its old `Dashboard` stay local.

## Setup (Phase 1)

1. Double-click **`setup.bat`**. It creates a private Python environment (`.venv`), installs
   `requests` and `pandas`, and runs the connection check.
2. Double-click **`edit_keys.bat`**. Notepad opens your `.env` file. Paste each free key right after
   its `=` (no spaces, no quotes), then save with Ctrl+S:
   `TWELVEDATA_API_KEY`, `COINGECKO_API_KEY`, `FRED_API_KEY`, `FINNHUB_API_KEY`.
   Also paste your Alpaca paper keys into `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`.
3. Double-click **`check_setup.bat`** to test again. Every row should say `OK`.

## Price archive (Phase 2)

Double-click **`collect.bat`** to update `data\`. The first run downloads history (daily candles
since 2021, 15-minute candles for the last 60 days, about 2 minutes); later runs fetch only new
candles (a few seconds). Forex is skipped if updated in the last 10 minutes and macro data if
updated in the last 6 hours, to stay inside the free limits. Use `collect.bat --force` to override.

| Folder | Contents | Source |
| --- | --- | --- |
| `data\stocks\` | 16 stocks + GLD, `_1Day` and `_15Min` | Alpaca (IEX feed, split-adjusted) |
| `data\crypto\` | BTC, ETH, SOL, PAXG, `_1Day` and `_15Min` | Alpaca |
| `data\crypto_binance\` | Only created if Alpaca crypto fails | Binance (backup) |
| `data\forex\` | EUR/USD, USD/JPY, GBP/USD, USD/THB, XAU/USD daily | Twelve Data |
| `data\macro\` | Dollar index, 10-year yield, 10-year real yield | FRED |
| `data\status.json` | When the archive was last updated, and whether each group worked | |

Every CSV opens in Excel. Columns: `time` (UTC), `open`, `high`, `low`, `close`, `volume`.

## Signals (Phase 3)

Double-click **`signals.bat`**: it updates prices and news, then writes `public\signals.json` and prints a summary.

- **Daily rules** are the same as your agent's `Tools\Signals.py` (v6): trend, momentum, dip, plus the
  trend-exit rule. Checked on 2026-11-13: SMA5/20/50 and 20-day highs match the agent's journal to the cent.
- **Intraday momentum** (15-minute bars) is experimental and always low confidence until the backtest.
- **Signal**: `buy` if any style fires, `sell` if the trend is broken (for anyone holding it), else `hold`.
- **Confidence**: low by default; medium only when the market backdrop agrees (SPY above its 50-day
  average for stocks, BTC for crypto, gold's own trend for GLD/PAXG) plus a style-specific check.
  High is never given until a style passes the backtest.
- Every buy lists the main risk, what would prove it wrong, and a stop price from the style's trailing stop.

## News (Phase 4)

`news.py` (run by `signals.bat`) saves `data\news.json`; `signals.py` adds it to each asset.

- **Headlines per symbol**: Alpaca/Benzinga, last 3 days. Round-ups tagging more than 3 tickers are left out.
  Gold (GLD, PAXG) gets any headline with the whole word "gold" or "bullion" (Alpaca + Finnhub).
- **Sentiment**: VADER plus a finance word list (`sd\sentiment.py`), scored on your PC. Rough: a warning
  light, never a reason to buy.
- **Negative-news warning** (same 24h window as your agent's rule): a headline from the last 24 hours that
  scores -0.5 or lower AND names the company (`names` in `config.json`) AND isn't the company acting as an
  analyst ("JPMorgan Downgrades X"). It flags the asset and lowers medium confidence to low.
- **Market headlines**: Finnhub general news.
- **Events (next 30 days)**: CPI, jobs, GDP, PCE, PPI, retail sales (dates from FRED; usual 08:30 New York
  time) and Fed decisions (14:00 New York, from `fomc_decision_days` in `config.json`: update it each year
  from federalreserve.gov).

## Dashboard (Phase 5)

Double-click **`dashboard.bat`**: it updates prices, news and signals once, then opens
**http://127.0.0.1:8000** in your browser. Close the black window to stop it.
Only this PC can see it (the phone version comes with GitHub Pages in Phase 7).

- Top: when it was updated (red banner if the data is over 30 minutes old), US session, market
  risk-on/off, max position size, crypto backdrop, then the upcoming events.
- Cards: one per asset, buys first. Tap a card for its chart (daily with SMA20/50, or 15 min), the full
  reason / main risk / wrong-if / stop price, the indicators, and its headlines.
- Bottom: forex, gold and US macro context (view only), market headlines.
- The page re-reads `signals.json` every 30 seconds; the scanner (below) keeps it fresh.

## Forex & gold for XM

Section "Forex & gold · trade yourself on XM" on the dashboard. Pairs and XM symbol names are in
`config.json` under `forex` (EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF, USD/CAD, NZD/USD, XAU/USD = GOLD;
USD/THB as context only). Data: Twelve Data, daily candles every 2 hours and hourly candles every 30
minutes (about 500 of the 800 free requests a day).

- **Setups** (`sd/forex.py`): your three styles adapted to forex, LONG and SHORT, with thresholds in
  ATR (the pair's average daily range). Always low confidence until the backtest (Phase 8).
- **Fixed stop-loss** 1.5 x ATR and **take-profit** 2x that distance: enter both as SL/TP in XM
  (MetaTrader trailing stops only work while your terminal is running).
- **Lot-size calculator**: enter your XM balance (USD), risk per trade, account type and leverage.
  Kept only in your browser. Lots are rounded DOWN so hitting the stop loses about your chosen risk;
  if even 0.01 lot is too big it says so. Contract sizes: XM Micro 1,000 / Standard 100,000 units per
  forex lot (XM help centre); gold assumed 1 oz Micro / 100 oz Standard: check GOLD's "Specification"
  in the XM app and edit `contract` in `config.json` if different.
- **Headlines**: per pair by currency and central-bank words, plus a "Dollar & Fed" list.
- XM is a leveraged CFD broker: most retail CFD accounts lose money. Practise on the XM demo first.

## Automatic scanner (Phase 6)

`run_scanner.py` keeps everything up to date while your PC is on, and serves the dashboard.

| Data | How often |
| --- | --- |
| US stocks + GLD | every minute during pre-market, regular and after-hours; every 15 min otherwise |
| Crypto + PAXG, then signals and charts | every minute |
| Binance crypto volume | every 5 minutes |
| News and upcoming events | every 15 minutes |
| Forex hourly / daily candles | every 30 minutes / every 2 hours |
| US macro (FRED) | every 6 hours |

| File | Use it to |
| --- | --- |
| `dashboard.bat` | open the dashboard; starts the scanner in a window if it isn't running |
| `scanner.bat` | run the scanner in a window so you can watch every update |
| `start_scanner_hidden.bat` | run it in the background with no window |
| `stop_scanner.bat` | stop it (it finishes the current step, usually within seconds) |
| `install_autostart.bat` | start it hidden every time you log in (adds one file to your Startup folder) |
| `remove_autostart.bat` | undo that |

- Only one scanner runs at a time; starting another just opens the dashboard.
- Everything it does is logged to `data\scanner.log` (kept under 2 MB). Keys never appear in it.
- If one source fails, the others keep going and the error is logged.
- When the PC sleeps, updates pause; the page shows a red banner once data is over 30 minutes old.

## GitHub and your phone (Phase 7)

- **Code** goes to the `main` branch (`upload_code.bat`): never `.env`, never `data\`.
- **Website** goes to the `gh-pages` branch, replaced each time so it never piles up history:
  the page plus your data **encrypted** with `DASHBOARD_PASSPHRASE` (AES-256-GCM). The repo must be
  public for free Pages and Actions, so the data is encrypted: the free data plans are for personal use only.
- **While your PC is on**, the scanner publishes every 15 minutes.
- **When your PC is off**, GitHub Actions (`.github/workflows/scan.yml`) runs every 15 minutes, skips
  itself if the PC published in the last 20 minutes, and otherwise updates and publishes from the cloud.

### One-time setup
1. On github.com, create a **public**, **empty** repository called `signal-dashboard` (no README).
2. Create a token: GitHub Settings > Developer settings > Personal access tokens > **Fine-grained tokens**
   > Generate new token. Repository access: **Only select repositories** > `signal-dashboard`.
   Permissions > Repository permissions > **Contents: Read and write**. Copy the token.
3. `edit_keys.bat`: fill in `GITHUB_TOKEN`, `GITHUB_REPO` (yourname/signal-dashboard) and
   `DASHBOARD_PASSPHRASE` (4+ random words, not your GitHub password). Save.
4. `setup.bat` (installs the encryption package), then `upload_code.bat` (check the list, type y).
5. In the repo: Settings > Secrets and variables > Actions > **New repository secret**, once for each:
   `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `TWELVEDATA_API_KEY`, `FRED_API_KEY`, `FINNHUB_API_KEY`,
   `COINGECKO_API_KEY`, `DASHBOARD_PASSPHRASE` (same values as in `.env`).
6. `publish.bat` (creates the `gh-pages` branch).
7. In the repo: Settings > Pages > Source **Deploy from a branch** > Branch **gh-pages**, folder **/ (root)** > Save.
   After 1-2 minutes the site is at `https://yourname.github.io/signal-dashboard/`.
8. On your iPhone: open that address in Safari, type the passphrase (tick "Remember"), then
   Share > **Add to Home Screen**.
9. Test the cloud scanner: repo > Actions > **scan** > Run workflow (tick "force"). The first run takes
   about 5 minutes because it downloads the price history; later runs take about 1-2 minutes.
10. Restart the scanner (`stop_scanner.bat`, then `dashboard.bat`) so it starts publishing.

Notes: the token expires (you choose when): make a new one and update `.env`. GitHub pauses scheduled
workflows in a repo with no activity for 60 days and emails you; re-enable it on the Actions tab.
To update from your phone at any time: Actions > scan > Run workflow.

## Files

| File | What it does |
| --- | --- |
| `config.json` | Which symbols to watch (this project's own list; edit it freely) |
| `.env` | Your keys. Private: never share it; `.gitignore` keeps it off GitHub |
| `edit_keys.bat` | Opens `.env` in Notepad |
| `check_setup.py` | One small read-only request per data source, prints OK / NO KEY / FAIL |
| `sd/env.py` | Loads keys and scrubs them out of any error message |
| `sd/net.py` | All web requests: timeout, polite retries on 429/5xx |
| `collect.py` / `collect.bat` | Updates the price archive |
| `signals.py` / `signals.bat` | Computes signals into `public/signals.json` |
| `news.py` | Collects headlines + upcoming events into `data/news.json` |
| `sd/sentiment.py` | Headline sentiment and the finance word list |
| `sd/styles.py` | The trading-style rules, confidence, risks |
| `sd/forex.py` | Forex/gold setups (long/short, ATR), market hours, lot-size math |
| `sd/market.py` | Open-now session (from Alpaca's calendar) and time zones |
| `serve.py` | Local web server for `public/` on port 8000 (also used by the scanner) |
| `run_scanner.py` | The automatic scanner (Phase 6); also publishes every 15 min |
| `publish.py` / `publish.bat` | Encrypt and publish the dashboard to GitHub Pages |
| `upload_code.py` / `upload_code.bat` | Upload the code (not keys or data) to GitHub |
| `.github/workflows/scan.yml` | The cloud scanner on GitHub Actions |
| `sd/crypto.py`, `sd/github.py` | Encryption, and the GitHub upload helper |
| `public/index.html` | The dashboard page |
| `public/charts/` | Chart data per asset, written by `signals.py` |
| `public/vendor/` | TradingView Lightweight Charts 4.1.3 (Apache 2.0) |
| `sd/store.py` | Reads and safely writes the archive's CSV files |
| `sd/sources/` | One file per data source: `alpaca`, `binance`, `twelvedata`, `fred` |
| `data/` | The price archive, kept on your PC only (never uploaded) |
