"""Phase 2: download prices into the data archive (data/), fetching only what's new.

    python collect.py                  # update everything
    python collect.py --only stocks    # just one group: stocks, crypto, forex, macro
    python collect.py --force          # ignore the "updated recently" skip for forex/macro

First run downloads history (daily bars since 2021, 15-minute bars for the last 60 days),
which takes a minute or two. Later runs only fetch bars since the newest one already saved.
Read-only: nothing here can place an order.
"""
import argparse
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from sd import config, env, store
from sd.net import FetchError
from sd.sources import alpaca, binance, fred, twelvedata

env.load()

DAILY_START = "2021-01-01T00:00:00Z"   # 5+ years of daily history for backtesting
INTRADAY_DAYS = 60                     # 15-minute history kept for intraday momentum
TWELVE_PAUSE = 8.0                     # seconds between Twelve Data calls (free plan: 8 per minute)
MACRO_REFRESH_HOURS = 6                # FRED data changes at most daily


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def default_start(timeframe):
    return DAILY_START if timeframe == "1Day" else iso(now() - timedelta(days=INTRADAY_DAYS))


def start_for(group, symbols, timeframe):
    """Fetch from the OLDEST "newest saved bar" among the symbols (re-fetching that bar on
    purpose, so a still-forming candle gets corrected). A symbol with no file yet starts at
    the full-history default."""
    starts = [store.last_time(store.path_for(group, s, timeframe)) or default_start(timeframe)
              for s in symbols]
    return min(starts)


def minutes_since_update(path):
    if not path.is_file():
        return None
    return store.minutes_since_fetch(path)


def save_all(group, timeframe, bars_by_symbol, symbols, report):
    for s in symbols:
        rows = bars_by_symbol.get(s, [])
        p = store.path_for(group, s, timeframe)
        added, total = store.upsert(p, rows)
        report.append((group, s, timeframe, added, total, store.last_time(p) or "-"))


def collect_stocks(cfg, report, _force):
    syms = cfg["stocks"]
    for tf in ("1Day", "15Min"):
        bars = alpaca.stock_bars(syms, tf, start_for("stocks", syms, tf))
        save_all("stocks", tf, bars, syms, report)


def collect_crypto(cfg, report, _force):
    syms = cfg["crypto"]
    for tf in ("1Day", "15Min"):
        try:
            bars = alpaca.crypto_bars(syms, tf, start_for("crypto", syms, tf))
            save_all("crypto", tf, bars, syms, report)
        except FetchError as e:
            # Backup: Binance, saved separately so the two sources never mix.
            print(f"  Alpaca crypto {tf} failed ({e}); using Binance backup")
            for s in syms:
                p = store.path_for("crypto_binance", s, tf)
                rows = binance.bars(s, tf, store.last_time(p) or default_start(tf))
                added, total = store.upsert(p, rows)
                report.append(("crypto_binance", s, tf, added, total, store.last_time(p) or "-"))


def collect_crypto_volume(cfg, report, _force):
    syms = cfg["crypto"]
    # Binance daily candles, used as the market-wide VOLUME reference: Alpaca's own crypto venue
    # is small (about 1.6 BTC a day), so one big order there can fake a "13x volume" reading.
    for s in syms:
        p = store.path_for("crypto_binance", s, "1Day")
        try:
            rows = binance.bars(s, "1Day", store.last_time(p) or DAILY_START)
        except FetchError as e:
            report.append(("crypto_binance", s, "1Day", 0, len(store.read(p)), f"ERROR: {e}"))
            continue
        added, total = store.upsert(p, rows)
        report.append(("crypto_binance", s, "1Day", added, total, store.last_time(p) or "-"))


def forex_symbols(cfg):
    """[(symbol, [timeframes])]: tradeable pairs get daily + hourly candles, context-only pairs daily."""
    fx = cfg["forex"]
    return [(p["symbol"], ["1Day", "1h"]) for p in fx["pairs"]] + [(s, ["1Day"]) for s in fx["context_only"]]


FOREX_INTERVAL = {"1Day": "1day", "1h": "1h"}
FOREX_HISTORY = {"1Day": None, "1h": 30}     # days of history on the first download (None = since 2021)


def collect_forex(cfg, report, force):
    every = cfg["forex"]["refresh_minutes"]
    first = True
    for s, tfs in forex_symbols(cfg):
        for tf in tfs:
            p = store.path_for("forex", s, tf)
            age = minutes_since_update(p)
            limit = every["1day" if tf == "1Day" else "1h"]
            if not force and age is not None and age < limit:
                report.append(("forex", s, tf, 0, len(store.read(p)), f"skipped: updated {age:.0f} min ago"))
                continue
            if not first:
                time.sleep(TWELVE_PAUSE)   # stay under 8 requests per minute
            first = False
            last = store.last_time(p)
            if last:
                # From a little before the newest saved candle: the overlap is harmless (rows are
                # de-duplicated) and avoids asking for a range with no finished candles yet.
                since = datetime.fromisoformat(last.replace("Z", "+00:00")) - timedelta(days=5 if tf == "1Day" else 1)
            elif FOREX_HISTORY[tf]:
                since = now() - timedelta(days=FOREX_HISTORY[tf])
            else:
                since = datetime.fromisoformat(DAILY_START.replace("Z", "+00:00"))
            try:
                rows = twelvedata.bars(s, since.strftime("%Y-%m-%d"), interval=FOREX_INTERVAL[tf])
            except FetchError as e:
                report.append(("forex", s, tf, 0, len(store.read(p)), f"ERROR: {e}"))
                continue
            added, total = store.upsert(p, rows)
            store.mark_fetched(p)
            report.append(("forex", s, tf, added, total, store.last_time(p) or "-"))


def collect_macro(cfg, report, force):
    for sid in cfg["macro_fred"]:
        p = store.DATA / "macro" / f"{sid}.csv"
        age = minutes_since_update(p)
        if not force and age is not None and age < MACRO_REFRESH_HOURS * 60:
            report.append(("macro", sid, "daily", 0, len(store.read(p)), f"skipped: updated {age / 60:.1f} h ago"))
            continue
        last = store.last_time(p)
        rows = fred.series(sid, (last or DAILY_START)[:10])
        added, total = store.upsert(p, rows, columns=fred.COLUMNS)
        store.mark_fetched(p)
        report.append(("macro", sid, "daily", added, total, store.last_time(p) or "-"))


GROUPS = {"stocks": collect_stocks, "crypto": collect_crypto, "crypto_volume": collect_crypto_volume,
          "forex": collect_forex, "macro": collect_macro}


def run(names, force=False, quiet=True):
    """Update these groups. Returns (report rows, {group: ok/error}). Used by run_scanner.py too."""
    cfg = config.load()
    report, result = [], {}
    for name in names:
        t0 = time.time()
        if not quiet:
            print(f"Updating {name} ...")
        try:
            GROUPS[name](cfg, report, force)
            result[name] = {"ok": True, "seconds": round(time.time() - t0, 1)}
        except Exception as e:                          # one failing source must not stop the others
            result[name] = {"ok": False, "error": env.scrub(e)[:300]}
            if not quiet:
                print(f"  {name} FAILED: {result[name]['error']}")
    with _status_lock:
        _write_status(result)
    return report, result


_status_lock = threading.Lock()


def _write_status(result):
    status_file = store.DATA / "status.json"
    try:
        status = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = {"groups": {}}
    status.setdefault("groups", {})
    for name, r in result.items():
        status["groups"][name] = {**r, "at": iso(now())}
    status["updated_at"] = iso(now())
    store.write_text(status_file, json.dumps(status, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Update the price archive in data/.")
    ap.add_argument("--only", choices=sorted(GROUPS), action="append", help="update just this group (repeatable)")
    ap.add_argument("--force", action="store_true", help="don't skip forex/macro that were updated recently")
    args = ap.parse_args()
    report, result = run(args.only or list(GROUPS), args.force, quiet=False)
    print(f"\n{'group':<15}{'symbol':<11}{'tf':<7}{'new':>6}{'total':>7}  newest bar")
    for g, s, tf, added, total, last in report:
        print(f"{g:<15}{s:<11}{tf:<7}{added:>6}{total:>7}  {last}")
    failed = [g for g, v in result.items() if not v["ok"]]
    print("\nDone." if not failed else f"\nDone, but these groups failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
