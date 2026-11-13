"""Binance public market data: backup source for crypto, no key needed.

Saved to separate files (data/crypto_binance/) so they never mix with Alpaca's candles,
because the two exchanges' prices and candle times differ slightly.
"""
from datetime import datetime, timezone

from .. import net
from ..net import FetchError

# api.binance.com refuses US-based servers (GitHub Actions runs in the US);
# data-api.binance.vision is Binance's public market-data host and answers from anywhere.
URLS = ["https://api.binance.com/api/v3/klines", "https://data-api.binance.vision/api/v3/klines"]
INTERVALS = {"1Day": "1d", "15Min": "15m", "1Hour": "1h", "5Min": "5m"}


def pair(symbol):
    """"BTC/USD" -> "BTCUSDT" (Binance trades against the USDT stablecoin, which tracks USD)."""
    base, quote = symbol.split("/")
    return base + ("USDT" if quote == "USD" else quote)


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bars(symbol, timeframe, start):
    """All candles from `start` (ISO time) until now, 1000 per request."""
    start_ms = int(datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp() * 1000)
    out = []
    while True:
        rows = _get({"symbol": pair(symbol), "interval": INTERVALS[timeframe], "startTime": start_ms, "limit": 1000})
        # Each row: [open time ms, open, high, low, close, volume, close time ms, ...]
        out += [{"time": _iso(r[0]), "open": r[1], "high": r[2], "low": r[3],
                 "close": r[4], "volume": r[5]} for r in rows]
        if len(rows) < 1000:
            return out
        start_ms = rows[-1][0] + 1


def _get(params):
    err = None
    for url in URLS:
        try:
            return net.get_json(url, params=params, retries=1)
        except FetchError as e:
            err = e
    raise err
