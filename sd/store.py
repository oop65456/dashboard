"""The data archive: one CSV file per symbol and timeframe, e.g. data/stocks/AAPL_1Day.csv

Every file has the same columns:  time,open,high,low,close,volume
  - time is UTC in ISO format ("2026-11-12T05:00:00Z"), so files sort correctly as text.
  - Rows are unique by time. Writing a bar that already exists REPLACES it; that's how a
    still-forming bar (today's candle) gets corrected on the next run.

Plain CSV on purpose: you can open any file in Excel, and it works with any Python version.
"""
import csv
import json
import os
import threading
import time

from .env import ROOT

DATA = ROOT / "data"
COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def path_for(group, symbol, timeframe):
    """data/<group>/<SYMBOL>_<timeframe>.csv, with "/" in symbols like BTC/USD turned into "-"."""
    safe = symbol.replace("/", "-")
    return DATA / group / f"{safe}_{timeframe}.csv"


def read(path):
    """All rows of a file as a list of dicts (empty list if the file doesn't exist yet)."""
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def last_time(path):
    """Time of the newest bar in the file, or None for a new file."""
    rows = read(path)
    return rows[-1]["time"] if rows else None


def upsert(path, new_rows, columns=COLUMNS):
    """Merge new bars into the file. Returns (bars that are new, total bars now).

    Writes to a temporary file first and then swaps it in, so a crash or a closed
    window can never leave a half-written archive behind.
    """
    by_time = {r["time"]: r for r in read(path)}
    before = set(by_time)
    for r in new_rows:
        by_time[r["time"]] = {c: r.get(c, "") for c in columns}
    rows = [by_time[t] for t in sorted(by_time)]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)
    replace(tmp, path)
    return len(set(by_time) - before), len(rows)


def replace(tmp, path, tries=10):
    """os.replace with retries: on Windows it fails while another program (the dashboard, Excel)
    has the file open for a moment, so wait briefly and try again."""
    for i in range(tries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.2)


def write_text(path, text):
    """Write a whole text file safely: readers never see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    replace(tmp, path)


# When was each file last downloaded? Kept in data/fetch_times.json rather than read from file
# times, because GitHub Actions restores the archive from its cache with new file times.
FETCH_TIMES = DATA / "fetch_times.json"
_fetch_lock = threading.Lock()


def _key(path):
    return path.relative_to(DATA).as_posix()


def mark_fetched(path):
    with _fetch_lock:
        try:
            times = json.loads(FETCH_TIMES.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            times = {}
        times[_key(path)] = time.time()
        write_text(FETCH_TIMES, json.dumps(times, indent=1, sort_keys=True))


def minutes_since_fetch(path):
    """Minutes since this file was last downloaded, or None if never (or no record)."""
    try:
        times = json.loads(FETCH_TIMES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    t = times.get(_key(path))
    return None if t is None else (time.time() - t) / 60
