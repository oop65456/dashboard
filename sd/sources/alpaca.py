"""Alpaca market data: US stocks/ETFs (IEX feed, free) and crypto. Read-only."""
from .. import env, net

BASE = "https://data.alpaca.markets"


def _headers():
    return {"APCA-API-KEY-ID": env.get("APCA_API_KEY_ID") or "",
            "APCA-API-SECRET-KEY": env.get("APCA_API_SECRET_KEY") or ""}


def _bar(b):
    """Alpaca's short names (t, o, h, l, c, v) -> the archive's column names."""
    return {"time": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
            "close": b["c"], "volume": b.get("v", "")}


def _paged(url, params):
    """Alpaca returns at most `limit` bars per reply plus a next_page_token; keep asking until done."""
    out = {}
    params = {**params, "limit": 10000}
    while True:
        d = net.get_json(url, params=params, headers=_headers())
        for sym, bars in (d.get("bars") or {}).items():
            out.setdefault(sym, []).extend(_bar(b) for b in bars)
        token = d.get("next_page_token")
        if not token:
            return out
        params["page_token"] = token


def stock_bars(symbols, timeframe, start):
    """Bars for many stocks in one go. timeframe: "1Day", "15Min", ...  start: ISO time."""
    return _paged(f"{BASE}/v2/stocks/bars",
                  {"symbols": ",".join(symbols), "timeframe": timeframe, "start": start,
                   "feed": "iex",            # the free real-time feed, same as your agent uses
                   "adjustment": "split"})   # past prices adjusted for stock splits


def crypto_bars(symbols, timeframe, start):
    """Bars for crypto pairs like "BTC/USD", "PAXG/USD"."""
    return _paged(f"{BASE}/v1beta3/crypto/us/bars",
                  {"symbols": ",".join(symbols), "timeframe": timeframe, "start": start})
