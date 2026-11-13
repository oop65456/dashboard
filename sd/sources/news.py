"""News and events: Alpaca/Benzinga headlines per symbol, Finnhub market headlines, FRED release dates."""
from datetime import datetime, timezone

from .. import env, net

ALPACA_NEWS = "https://data.alpaca.markets/v1beta1/news"


def alpaca_symbol(symbol):
    """Alpaca's news uses "BTCUSD" for the "BTC/USD" pair."""
    return symbol.replace("/", "")


def alpaca(symbols, start, max_pages=12):
    """Headlines tagged with any of `symbols` since `start` (ISO time), newest first."""
    headers = {"APCA-API-KEY-ID": env.get("APCA_API_KEY_ID") or "",
               "APCA-API-SECRET-KEY": env.get("APCA_API_SECRET_KEY") or ""}
    params = {"symbols": ",".join(alpaca_symbol(s) for s in symbols), "start": start, "limit": 50,
              "sort": "desc", "include_content": "false"}
    items = []
    for _ in range(max_pages):
        d = net.get_json(ALPACA_NEWS, params=params, headers=headers)
        items += [{"time": n["created_at"], "headline": n["headline"], "url": n["url"],
                   "source": n["source"], "symbols": n["symbols"]} for n in d.get("news", [])]
        if not d.get("next_page_token"):
            break
        params["page_token"] = d["next_page_token"]
    return items


def finnhub(category="general"):
    """Latest market-wide headlines (category: general, forex, crypto)."""
    d = net.get_json("https://finnhub.io/api/v1/news",
                     params={"category": category, "token": env.get("FINNHUB_API_KEY")})
    return [{"time": datetime.fromtimestamp(x["datetime"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "headline": x["headline"], "url": x["url"], "source": x["source"], "symbols": []} for x in d]


def fred_next_dates(release_id, today):
    """Upcoming scheduled dates of a FRED release (e.g. 10 = CPI), from `today` (YYYY-MM-DD)."""
    d = net.get_json("https://api.stlouisfed.org/fred/release/dates",
                     params={"release_id": release_id, "api_key": env.get("FRED_API_KEY"),
                             "file_type": "json", "realtime_start": today, "realtime_end": "9999-12-31",
                             "include_release_dates_with_no_data": "true", "sort_order": "asc", "limit": 3})
    return [x["date"] for x in d.get("release_dates", [])]
