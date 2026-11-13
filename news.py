"""Phase 4: collect headlines and upcoming market events -> data/news.json (signals.py reads it).

    python news.py

- Per symbol: Alpaca/Benzinga headlines from the last 3 days, each with a sentiment score.
  Round-up articles that tag many tickers ("Stock Market Today: ...") are kept out of the
  per-symbol lists, because they are rarely about that one company.
- Gold (GLD, PAXG): headlines mentioning gold/bullion, from Alpaca and Finnhub.
- Market: the latest general headlines from Finnhub.
- Events: next CPI, jobs report, GDP, PCE inflation, PPI, retail sales (FRED) and Fed decisions.
Read-only: nothing here can place an order.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sd import config, env, sentiment, store
from sd.net import FetchError
from sd.sources import news as src

env.load()

OUT = store.DATA / "news.json"
NY, BKK = ZoneInfo("America/New_York"), ZoneInfo("Asia/Bangkok")
DAYS_BACK = 3
MAX_TICKERS = 3        # an article tagging more tickers than this counts as a round-up
PER_SYMBOL = 8
GOLD = {"GLD", "PAXG/USD"}
GOLD_RE = re.compile(r"\b(gold|bullion|precious metals?)\b", re.I)   # whole words only

# Forex: words that show a headline is about a currency (or its central bank).
CURRENCY_WORDS = {
    "USD": ["dollar", "Fed", "Federal Reserve", "Powell", "Treasury yields", "FOMC"],
    "EUR": ["euro", "ECB", "Lagarde", "eurozone", "euro zone"],
    "GBP": ["pound", "sterling", "BoE", "Bank of England"],
    "JPY": ["yen", "BOJ", "Bank of Japan", "Ueda"],
    "AUD": ["Australian dollar", "Aussie", "RBA", "Reserve Bank of Australia"],
    "CHF": ["Swiss franc", "franc", "SNB"],
    "CAD": ["Canadian dollar", "loonie", "Bank of Canada"],
    "NZD": ["New Zealand dollar", "kiwi", "RBNZ"],
    "XAU": ["gold", "bullion"],
}


def word_re(words):
    return re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(w) for w in words) + r")(?![A-Za-z])", re.I)


# FRED release id -> (name, usual release time in New York, importance)
RELEASES = {10: ("US CPI inflation", "08:30", "high"), 50: ("US jobs report", "08:30", "high"),
            53: ("US GDP", "08:30", "medium"), 54: ("US PCE inflation", "08:30", "medium"),
            46: ("US PPI inflation", "08:30", "medium"), 9: ("US retail sales", "08:30", "medium")}
EVENT_DAYS = 30


def scored(item):
    s, label = sentiment.score(item["headline"])
    return {**item, "sentiment": s, "label": label}


def events(cfg, now):
    today = now.astimezone(NY).date()
    horizon = today + timedelta(days=EVENT_DAYS)
    out = []
    for rid, (name, hhmm, imp) in RELEASES.items():
        try:
            dates = src.fred_next_dates(rid, str(today))
        except FetchError as e:
            print(f"  (could not load {name} dates: {e})")
            continue
        for d in dates:
            if str(today) <= d <= str(horizon):
                out.append((d, hhmm, name, imp))
    for d in cfg["fomc_decision_days"]["dates"]:
        if str(today) <= d <= str(horizon):
            out.append((d, "14:00", "Fed interest-rate decision", "high"))
    result = []
    for d, hhmm, name, imp in sorted(out):
        et = datetime.fromisoformat(f"{d}T{hhmm}").replace(tzinfo=NY)
        result.append({"date": d, "time_et": hhmm, "bangkok": et.astimezone(BKK).strftime("%a %d %b %H:%M"),
                       "time_utc": et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "name": name, "importance": imp, "usual_time": True})
    return result


def main(quiet=False):
    cfg = config.load()
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    symbols = cfg["stocks"] + cfg["crypto"]
    problems = []

    try:
        items = [scored(i) for i in src.alpaca(symbols, start)]
    except FetchError as e:
        items, problems = [], problems + [f"Alpaca news: {e}"]
    try:
        market = [scored(i) for i in src.finnhub("general")]
    except FetchError as e:
        market, problems = [], problems + [f"Finnhub news: {e}"]

    by_symbol = {}
    for s in symbols:
        tag = src.alpaca_symbol(s)
        if s in GOLD:   # gold: any headline that is actually about gold, from both sources
            mine = [i for i in items + market if GOLD_RE.search(i["headline"])]
        else:
            mine = [i for i in items if tag in i["symbols"] and len(i["symbols"]) <= MAX_TICKERS]
        seen, unique = set(), []
        for i in sorted(mine, key=lambda i: i["time"], reverse=True):
            if i["headline"] not in seen:
                seen.add(i["headline"])
                unique.append({k: i[k] for k in ("time", "headline", "url", "source", "sentiment", "label")}
                              | {"tickers": len(i["symbols"])})
        by_symbol[s] = unique[:PER_SYMBOL]

    # Forex: Finnhub's forex + general feeds and the Alpaca items, matched by currency words.
    try:
        market_fx = [scored(i) for i in src.finnhub("forex")]
    except FetchError as e:
        market_fx, problems = [], problems + [f"Finnhub forex news: {e}"]
    pool, seen = [], set()
    for i in sorted(market + market_fx + items, key=lambda i: i["time"], reverse=True):
        if i["headline"] not in seen:
            seen.add(i["headline"])
            pool.append({k: i[k] for k in ("time", "headline", "url", "source", "sentiment", "label")})
    forex_news = {"USD": [i for i in pool if word_re(CURRENCY_WORDS["USD"]).search(i["headline"])][:PER_SYMBOL]}
    for pair in cfg["forex"]["pairs"]:
        cur = [c for c in pair["symbol"].split("/") if c != "USD"][0]
        forex_news[pair["symbol"]] = [i for i in pool if word_re(CURRENCY_WORDS[cur]).search(i["headline"])][:PER_SYMBOL]

    ev = events(cfg, now)
    data = {"fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "problems": problems,
            "by_symbol": by_symbol,
            "market": [{k: i[k] for k in ("time", "headline", "url", "source", "sentiment", "label")}
                       for i in market[:12]],
            "events": ev, "forex": forex_news}
    store.DATA.mkdir(exist_ok=True)
    store.write_text(OUT, json.dumps(data, indent=2))
    if quiet:
        return data

    print(f"News at {now.astimezone(BKK):%Y-%m-%d %H:%M} Bangkok ({len(items)} symbol headlines, last {DAYS_BACK} days)\n")
    for s, lst in by_symbol.items():
        neg = sum(1 for i in lst if i["label"] == "negative")
        top = f"{lst[0]['label'][:3]} {lst[0]['sentiment']:+.2f}  {lst[0]['headline'][:70]}" if lst else "-"
        print(f"  {s:<9} {len(lst):>2} items, {neg} negative | {top}")
    print("\nForex headlines: " + ", ".join(f"{k} {len(v)}" for k, v in forex_news.items()))
    print("\nUpcoming events (Bangkok time, usual release times):")
    for e in ev:
        print(f"  {e['bangkok']:<17} {e['name']} [{e['importance']}]")
    for p in problems:
        print("  PROBLEM:", p)
    print(f"\nSaved {OUT}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
