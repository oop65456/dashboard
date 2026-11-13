"""Phase 6: keep everything up to date automatically while this PC is on, and serve the dashboard.

    python run_scanner.py             # run (also serves http://127.0.0.1:8000 and opens it)
    python run_scanner.py --no-open   # run without opening the browser (used at login)

Two loops run side by side, so a slow source never holds up a fast one:
  PUBLISH (every 15 min): encrypted copy to GitHub Pages, if GITHUB_TOKEN etc. are in .env.
  FAST (every minute):  US stocks (only while the US market has a session; every 15 min otherwise),
                        crypto, then signals.json + charts.
  SLOW (own timers):    Binance crypto volume every 5 min, news + events every 15 min,
                        forex (hourly candles every 30 min, daily every 2 h: inside Twelve Data's
                        free 800 requests/day), macro every 6 h.
Stop it: run stop_scanner.bat (it rewrites data/STOP; the scanner notices within a few seconds).
Only one scanner can run at a time (the second one just opens the dashboard and exits).
Read-only: nothing here can place an order.
"""
import functools
import http.server
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timedelta, timezone

import collect
import news
import publish
import signals
from sd import env, market, store
from serve import HOST, PORT, Handler, PUBLIC

env.load()

STOP_FILE = store.DATA / "STOP"
LOG_FILE = store.DATA / "scanner.log"
LOG_MAX_BYTES = 2_000_000

FAST_EVERY = 60                      # seconds between fast cycles
STOCKS_IDLE_EVERY = 15 * 60          # stocks when there is no US session (weekend, holiday)
SLOW_JOBS = [                        # (name, seconds between runs)
    ("crypto_volume", 5 * 60),
    ("news", 15 * 60),
    ("forex", 5 * 60),               # forex checks often but only downloads what is due (30 min / 2 h)
    ("macro", 60 * 60),              # macro checks hourly but only downloads every 6 h
    ("publish", 15 * 60),            # encrypted copy to GitHub Pages for your phone (if set up)
]
STOCK_SESSIONS = {"pre-market", "regular", "after-hours"}   # when the free IEX feed has new bars

stop = threading.Event()
STARTED = time.time()


def stop_requested():
    """stop_scanner.bat (re)writes data/STOP. Only a request made AFTER this scanner started counts,
    so an old STOP file never needs deleting."""
    try:
        return STOP_FILE.stat().st_mtime > STARTED
    except OSError:
        return False
log_lock = threading.Lock()


def log(msg):
    """One line to the console (if there is one) and to data/scanner.log, which is kept under 2 MB."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    with log_lock:
        try:
            print(line, flush=True)
        except (OSError, ValueError, AttributeError):   # no console when started hidden
            pass
        try:
            store.DATA.mkdir(exist_ok=True)
            if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
                store.replace(LOG_FILE, LOG_FILE.with_suffix(".old.log"))
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(env.scrub(line) + "\n")
        except OSError:
            pass


def safely(name, fn):
    """Run one step; log any error (keys scrubbed) instead of crashing the scanner."""
    t0 = time.time()
    try:
        out = fn()
        return out, time.time() - t0
    except Exception as e:
        log(f"ERROR in {name}: {env.scrub(e)}")
        log(env.scrub("".join(traceback.format_exc().splitlines(keepends=True)[-3:])).strip())
        return None, time.time() - t0


def sleep(seconds):
    """Sleep, but wake up early if a stop was requested (checked every 2 seconds)."""
    end = time.time() + seconds
    while time.time() < end and not stop.is_set():
        if stop_requested():
            stop.set()
            break
        time.sleep(min(2, max(0, end - time.time())))


class Calendar:
    """US trading days from Alpaca, refreshed every 6 hours, to know when stocks have new bars."""
    def __init__(self):
        self.days, self.loaded = {}, 0

    def session(self):
        now = datetime.now(timezone.utc)
        if time.time() - self.loaded > 6 * 3600:
            try:
                self.days = market.trading_days(now.astimezone(market.NY).date() - timedelta(days=1))
                self.loaded = time.time()
            except Exception as e:
                log(f"calendar unavailable ({env.scrub(e)}); treating stocks as active")
                return "unknown"
        return market.stock_session(now, self.days)


def fast_loop():
    cal = Calendar()
    last_stocks = 0
    while not stop.is_set():
        t0 = time.time()
        session = cal.session()
        groups = ["crypto"]
        if session in STOCK_SESSIONS or session == "unknown" or time.time() - last_stocks >= STOCKS_IDLE_EVERY:
            groups.insert(0, "stocks")
            last_stocks = time.time()
        result, _ = safely("collect " + "+".join(groups), lambda: collect.run(groups)[1])
        d, secs = safely("signals", signals.update)
        if d:
            buys = [a["symbol"] for a in d["assets"] if a["signal"] == "buy"]
            fx = [f"{a['symbol']} {a['signal']}" for a in d["forex"]["assets"] if a["signal"] != "none"]
            bad = [g for g, r in (result or {}).items() if not r["ok"]]
            line = f"fast: {'+'.join(groups)} | US {session} | buy: {', '.join(buys) or '-'} | forex: {', '.join(fx) or '-'} ({secs:.1f}s)"
            if bad:
                line += f" | FAILED: {', '.join(bad)}"
            log(line)
        sleep(max(1, FAST_EVERY - (time.time() - t0)))


def slow_loop():
    last = {name: 0 for name, _ in SLOW_JOBS}
    while not stop.is_set():
        for name, every in SLOW_JOBS:
            if stop.is_set():
                break
            if time.time() - last[name] < every:
                continue
            last[name] = time.time()
            if name == "publish":
                msg, secs = safely("publish", lambda: publish.publish("pc"))
                if msg and not msg.startswith("not configured"):
                    log(f"slow: {msg} ({secs:.0f}s)")
                continue
            if name == "news":
                data, secs = safely("news", lambda: news.main(quiet=True))
                if data:
                    log(f"slow: news {sum(len(v) for v in data['by_symbol'].values())} symbol headlines, "
                        f"{len(data['events'])} events ({secs:.0f}s)")
            else:
                out, secs = safely(name, lambda: collect.run([name]))
                if out:
                    report, result = out
                    new = sum(r[3] for r in report)
                    errors = [f"{r[1]} {r[2]}" for r in report if str(r[5]).startswith("ERROR")]
                    if new or errors or not result[name]["ok"]:
                        log(f"slow: {name} +{new} bars ({secs:.0f}s)" + (f" | errors: {', '.join(errors)}" if errors else "")
                            + ("" if result[name]["ok"] else f" | FAILED: {result[name]['error']}"))
        sleep(10)


def main():
    # Single instance: the dashboard port doubles as the lock.
    handler = functools.partial(Handler, directory=str(PUBLIC))
    try:
        server = http.server.ThreadingHTTPServer((HOST, PORT), handler)
    except OSError:
        print(f"The scanner (or another dashboard) is already running on port {PORT}. Opening the dashboard.")
        if "--no-open" not in sys.argv:
            webbrowser.open(f"http://{HOST}:{PORT}/")
        return 0
    log(f"scanner started; dashboard at http://{HOST}:{PORT}/ (stop: stop_scanner.bat)")
    threading.Thread(target=server.serve_forever, daemon=True, name="web").start()
    workers = [threading.Thread(target=fast_loop, name="fast"), threading.Thread(target=slow_loop, name="slow")]
    for w in workers:
        w.start()
    if "--no-open" not in sys.argv:
        threading.Timer(3, lambda: webbrowser.open(f"http://{HOST}:{PORT}/")).start()
    try:
        while any(w.is_alive() for w in workers):
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
    for w in workers:
        w.join(timeout=200)
    server.shutdown()
    log("scanner stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
