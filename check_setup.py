"""Phase 1 check: can we reach every data source with the keys you have?

    python check_setup.py

Makes ONE small read-only request per source and prints a table. It never prints your keys.
Sources whose key you haven't added yet show "NO KEY": that's fine, add it to .env and run again.
"""
import sys

from sd import env, net
from sd.net import FetchError

env.load()

ALPACA_DATA = "https://data.alpaca.markets"


def alpaca_headers():
    return {"APCA-API-KEY-ID": env.get("APCA_API_KEY_ID") or "",
            "APCA-API-SECRET-KEY": env.get("APCA_API_SECRET_KEY") or ""}


# Each check returns a short text showing real data came back, or raises FetchError.

def check_alpaca_stocks():
    d = net.get_json(f"{ALPACA_DATA}/v2/stocks/bars/latest",
                     params={"symbols": "AAPL,GLD", "feed": "iex"}, headers=alpaca_headers())
    bars = d["bars"]
    return f"AAPL {bars['AAPL']['c']}, GLD {bars['GLD']['c']} (latest 1-min bar, IEX)"


def check_alpaca_crypto():
    d = net.get_json(f"{ALPACA_DATA}/v1beta3/crypto/us/latest/bars",
                     params={"symbols": "BTC/USD,PAXG/USD"}, headers=alpaca_headers())
    bars = d["bars"]
    return f"BTC/USD {bars['BTC/USD']['c']}, PAXG/USD {bars['PAXG/USD']['c']}"


def check_alpaca_news():
    d = net.get_json(f"{ALPACA_DATA}/v1beta1/news",
                     params={"symbols": "AAPL", "limit": 1}, headers=alpaca_headers())
    item = d["news"][0]
    return f"\"{item['headline'][:60]}\" ({item['created_at'][:10]})"


def check_binance():
    d = net.get_json("https://api.binance.com/api/v3/ticker/price", params={"symbol": "BTCUSDT"})
    return f"BTCUSDT {float(d['price']):.2f}"


def check_twelvedata():
    d = net.get_json("https://api.twelvedata.com/price",
                     params={"symbol": "EUR/USD", "apikey": env.get("TWELVEDATA_API_KEY")})
    if d.get("status") == "error":                      # Twelve Data reports errors inside a normal reply
        raise FetchError(env.scrub(d.get("message", "unknown error")))
    return f"EUR/USD {d['price']}"


def check_coingecko():
    d = net.get_json("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": "bitcoin,pax-gold", "vs_currencies": "usd"},
                     headers={"x-cg-demo-api-key": env.get("COINGECKO_API_KEY")})
    return f"bitcoin {d['bitcoin']['usd']}, pax-gold {d['pax-gold']['usd']}"


def check_finnhub():
    d = net.get_json("https://finnhub.io/api/v1/news",
                     params={"category": "general", "token": env.get("FINNHUB_API_KEY")})
    return f"\"{d[0]['headline'][:60]}\""


def check_fred():
    d = net.get_json("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": "DTWEXBGS", "api_key": env.get("FRED_API_KEY"),
                             "file_type": "json", "sort_order": "desc", "limit": 1})
    o = d["observations"][0]
    return f"US dollar index {o['value']} ({o['date']})"


# (name, function, keys it needs, required for the dashboard to work at all?)
CHECKS = [
    ("Alpaca stocks + GLD", check_alpaca_stocks, ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"], True),
    ("Alpaca crypto + PAXG", check_alpaca_crypto, ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"], True),
    ("Alpaca news", check_alpaca_news, ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"], True),
    ("Binance (backup crypto)", check_binance, [], False),
    ("Twelve Data (forex)", check_twelvedata, ["TWELVEDATA_API_KEY"], False),
    ("CoinGecko", check_coingecko, ["COINGECKO_API_KEY"], False),
    ("Finnhub (news)", check_finnhub, ["FINNHUB_API_KEY"], False),
    ("FRED (macro)", check_fred, ["FRED_API_KEY"], False),
]


def main():
    print("signal-dashboard setup check (read-only, keys are never shown)\n")
    failed_required = 0
    for name, fn, keys, required in CHECKS:
        missing = [k for k in keys if not env.get(k)]
        if missing:
            status, detail = "NO KEY", "add " + ", ".join(missing) + " to .env"
            failed_required += required
        else:
            try:
                status, detail = "OK", fn()
            except (FetchError, KeyError, IndexError, TypeError) as e:
                status, detail = "FAIL", env.scrub(e)[:120]
                failed_required += required
        print(f"  {status:<7} {name:<26} {detail}")
    print()
    if failed_required:
        print("Something the dashboard needs isn't working yet: fix the rows above, then run this again.")
        return 1
    print("The required sources work. Rows marked NO KEY are optional for now: add those keys when you have them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
