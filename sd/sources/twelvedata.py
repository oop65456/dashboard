"""Twelve Data: forex pairs and XAU/USD. Free plan = 8 requests/min and 800/day, so use sparingly."""
from .. import env, net
from ..net import FetchError

URL = "https://api.twelvedata.com/time_series"


def bars(symbol, start_date, interval="1day"):
    """Daily candles from start_date ("YYYY-MM-DD") to today. Forex has no volume, so it stays empty."""
    d = net.get_json(URL, params={"symbol": symbol, "interval": interval, "start_date": start_date,
                                  "outputsize": 5000, "timezone": "UTC",
                                  "apikey": env.get("TWELVEDATA_API_KEY")})
    if d.get("status") == "error":                 # errors arrive inside a normal reply
        if "No data is available" in d.get("message", ""):
            return []                              # nothing new since start_date: not a real error
        raise FetchError(env.scrub(d.get("message", "unknown error")))
    rows = []
    for v in d.get("values", []):
        t = v["datetime"]
        t = t + "T00:00:00Z" if len(t) == 10 else t.replace(" ", "T") + "Z"
        rows.append({"time": t, "open": v["open"], "high": v["high"], "low": v["low"],
                     "close": v["close"], "volume": ""})
    return rows
