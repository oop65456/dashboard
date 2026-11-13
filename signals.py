"""Phase 3: turn the price archive into signals -> public/signals.json (what the dashboard shows).

    python signals.py            # compute, save public/signals.json, print a summary table
    python signals.py --json     # print the full JSON instead of the table

Run collect.py first so prices are fresh. Read-only: nothing here can place an order.
Each signal is a small edge, not a prediction; confidence defaults to low.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from sd import config, env, forex, market, sentiment, store, styles
from sd.indicators import floats, pct, sma
from sd.net import FetchError

env.load()

OUT = store.ROOT / "public" / "signals.json"
STALE_MINUTES = 30            # a price older than this during trading hours is flagged stale
MAX_DAY_MOVE_PCT = 25.0       # bigger moves are treated as bad data (same as the agent)
GOLD = {"GLD", "PAXG/USD"}    # gold judges its backdrop by its own trend, not by SPY/BTC
NEWS_FILE = store.DATA / "news.json"
NEWS_STALE_HOURS = 3
WARNING_HOURS = 24            # same window as the agent's "no buys with material negative news" rule


def ts(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def above_sma50(group, symbol):
    """Backdrop check: is this symbol above its own 50-day average? (None if no data)"""
    rows = store.read(store.path_for(group, symbol, "1Day"))
    closes = floats(rows, "close")
    if len(closes) < 50:
        return None, None, None
    s50 = sma(closes, 50)
    return closes[-1] > s50, styles.r(closes[-1]), styles.r(s50)


def load_news():
    if not NEWS_FILE.is_file():
        return None
    return json.loads(NEWS_FILE.read_text(encoding="utf-8"))


def mentions(headline, words):
    """Does the headline name this asset? ALL-CAPS words (tickers) must match exactly, others ignore case."""
    for w in words:
        flags = 0 if w.isupper() else re.I
        if re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", headline, flags):
            return True
    return False


ANALYST_VERBS = r"(downgrades|upgrades|maintains|reiterates|initiates|lowers|raises|cuts|adjusts)"


def is_broker_note(headline, words):
    """"JPMorgan Chase Downgrades Agility Robotics" is JPMorgan acting as the analyst, not news about JPMorgan."""
    for w in words:
        if re.match(re.escape(w) + r"(\s+[\w&.,']+){0,3}?\s+" + ANALYST_VERBS + r"\b", headline, 0 if w.isupper() else re.I):
            return True
    return False


def apply_news(a, news, names, now):
    """Attach the latest headlines; warn and lower confidence on strongly negative news from the last 24h."""
    if not news:
        return
    words = names.get(a["symbol"], [a["symbol"]])
    items = news["by_symbol"].get(a["symbol"], [])
    for i in items:
        i["about"] = mentions(i["headline"], words) and not is_broker_note(i["headline"], words)
    # Show headlines that name the asset first, newest first within each group.
    a["news"] = sorted(items, key=lambda i: (not i["about"], -ts(i["time"]).timestamp()))[:3]
    bad = [i for i in items if i["about"] and i["sentiment"] <= sentiment.STRONG_NEGATIVE
           and (now - ts(i["time"])).total_seconds() <= WARNING_HOURS * 3600]
    if not bad:
        return
    worst = min(bad, key=lambda i: i["sentiment"])
    a["news_warning"] = {"count": len(bad), "headline": worst["headline"], "url": worst["url"],
                         "sentiment": worst["sentiment"], "time": worst["time"]}
    a["flags"].append(f"negative news in the last 24h ({len(bad)}): check it before buying")
    for b in a["buys"]:
        if b["confidence"] == "medium":
            b["confidence"] = "low"
        b["confidence_why"] += "; negative news in the last 24h"


def build_asset(group, symbol, now, session, days, regime_ok):
    kind = "gold" if symbol in GOLD else ("crypto" if group == "crypto" else "stock")
    a = {"symbol": symbol, "group": group, "kind": kind,
         "session": session if group == "stocks" else "24/7",
         "signal": "none", "buys": [], "exits": [], "flags": []}
    daily = store.read(store.path_for(group, symbol, "1Day"))
    m15 = store.read(store.path_for(group, symbol, "15Min"))
    if not daily:
        a["flags"].append("no data in the archive yet: run collect.py")
        return a

    # "Today" is the New York date for stocks and the UTC date for crypto (its daily candles start 00:00 UTC).
    if group == "stocks":
        today = now.astimezone(market.NY).date()
        day_of = market.ny_date
        frac = market.session_fraction(now, days) if session == "regular" else None
    else:
        today = now.date()
        day_of = market.utc_date
        frac = max(0.05, (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() / 86400)
    completed = [b for b in daily if day_of(b["time"]) < today]
    today_bar = next((b for b in daily if day_of(b["time"]) == today), None)

    # Latest price: the newest 15-minute bar if it's at least as recent as the daily data.
    if m15 and day_of(m15[-1]["time"]) >= day_of(daily[-1]["time"]):
        price, price_end = float(m15[-1]["close"]), ts(m15[-1]["time"]) + timedelta(minutes=15)
    else:
        price, price_end = float(daily[-1]["close"]), ts(daily[-1]["time"]) + timedelta(days=1)
    price_end = min(price_end, now)
    a["price_time"] = price_end.strftime("%Y-%m-%dT%H:%M:%SZ")

    today_vol = float(today_bar["volume"] or 0) if today_bar else None
    ind = styles.daily_indicators(completed, price, today_vol, frac)
    if "error" in ind:
        a["flags"].append(ind["error"])
        return a
    if group == "crypto":
        # Volume pace from Binance (market-wide) instead of Alpaca's small venue, same formula.
        bn = store.read(store.path_for("crypto_binance", symbol, "1Day"))
        bn_done = [b for b in bn if day_of(b["time"]) < today][-20:]
        bn_today = next((b for b in bn if day_of(b["time"]) == today), None)
        if len(bn_done) == 20 and bn_today:
            avg = sum(float(b["volume"]) for b in bn_done) / 20
            ind["volume_pace"] = round(float(bn_today["volume"]) / (avg * frac), 2) if avg else None
            ind["volume_source"] = "Binance"
        else:
            ind["volume_pace"], ind["volume_source"] = None, "unavailable"
    a.update(price=ind["price"], change_pct=ind["change_pct"], indicators=ind)

    live = group == "crypto" or session == "regular"
    age_min = (now - price_end).total_seconds() / 60
    if live and age_min > STALE_MINUTES:
        a["flags"].append(f"price is {age_min:.0f} min old: run collect.py for fresh data")
    if abs(ind["change_pct"]) > MAX_DAY_MOVE_PCT:
        a["flags"].append(f"{ind['change_pct']}% move vs yesterday looks like bad data: no signals")
        return a

    a["buys"], a["exits"] = styles.daily_signals(ind, regime_ok)

    # Experimental intraday momentum: crypto any time, stocks only during the regular session,
    # and only on fresh, completed 15-minute bars.
    if live and m15:
        done = [b for b in m15 if ts(b["time"]) + timedelta(minutes=15) <= now]
        if group == "stocks":
            def regular(b):
                t = ts(b["time"]).astimezone(market.NY).time()
                return (t.hour, t.minute) >= (9, 30) and t.hour < 16
            done = [b for b in done if regular(b)]
        if done and (now - ts(done[-1]["time"])).total_seconds() / 60 <= STALE_MINUTES + 15:
            sig = styles.intraday_momentum(done)
            if sig:
                a["buys"].append(sig)

    # The headline signal comes from the DAILY rules only (the agent's tested rules). The experimental
    # 15-minute rule can never turn a card into BUY by itself: alone it shows WATCH, and against a
    # broken daily trend it is marked as a counter-trend bounce.
    daily_buys = [b for b in a["buys"] if b["timeframe"] == "daily"]
    trend_broken = any(e["style"] == "trend" for e in a["exits"])
    for b in a["buys"]:
        if b["timeframe"] != "daily":
            b["experimental"] = True
            if trend_broken:
                b["counter_trend"] = True
                b["confidence_why"] += "; AGAINST the daily trend (trend broken): a short bounce, not a trend change"
    if daily_buys:
        a["signal"] = "buy"
    elif trend_broken:
        a["signal"] = "sell"
    elif a["buys"]:
        a["signal"] = "watch"
    else:
        a["signal"] = "hold"
    return a


def build_forex(cfg, now, news, names):
    """Forex + gold setups for XM, the market status, and context-only pairs."""
    fx = cfg["forex"]
    today = now.date()
    assets = []
    for pair in fx["pairs"]:
        sym = pair["symbol"]
        a = {"symbol": sym, "xm": pair["xm"], "kind": pair.get("kind", "forex"), "setups": [], "flags": [],
             "signal": "none", "pip": forex.pip_size(sym)}
        daily = store.read(store.path_for("forex", sym, "1Day"))
        h1 = store.read(store.path_for("forex", sym, "1h"))
        if not daily:
            a["flags"].append("no data yet: run collect.py")
            assets.append(a)
            continue
        completed = [b for b in daily if market.utc_date(b["time"]) < today]
        if h1 and ts(h1[-1]["time"]) >= ts(daily[-1]["time"]):
            price, t = float(h1[-1]["close"]), ts(h1[-1]["time"]) + timedelta(hours=1)
        else:
            price, t = float(daily[-1]["close"]), ts(daily[-1]["time"]) + timedelta(days=1)
        a["price_time"] = min(t, now).strftime("%Y-%m-%dT%H:%M:%SZ")
        ind = forex.indicators(completed, price)
        if "error" in ind:
            a["flags"].append(ind["error"])
            assets.append(a)
            continue
        a.update(price=forex.rnd(sym, ind["price"]), change_pct=ind["change_pct"], atr=ind["atr"], atr_pct=ind["atr_pct"],
                 digits=forex.digits(sym),
                 indicators={k: (forex.rnd(sym, v) if k in ("price", "prev_close", "sma5", "sma20", "sma50", "high20", "low20")
                                 else v) for k, v in ind.items()})
        a["setups"] = forex.setups(ind, sym)
        dirs = {x["direction"] for x in a["setups"]}
        a["signal"] = "long" if dirs == {"long"} else "short" if dirs == {"short"} else "mixed" if dirs else "none"
        if (now - ts(a["price_time"])).total_seconds() / 60 > 150:
            a["flags"].append("price is more than 2.5 h old: run collect.py")
        if news:
            a["news"] = news.get("forex", {}).get(sym, [])[:3]
        assets.append(a)
    context = []
    for s_ in fx["context_only"]:
        closes = floats(store.read(store.path_for("forex", s_, "1Day")), "close")
        if len(closes) >= 50:
            p, s20, s50 = closes[-1], sma(closes, 20), sma(closes, 50)
            context.append({"symbol": s_, "price": styles.r(p), "change_1d_pct": round(pct(p, closes[-2]), 2),
                            "change_20d_pct": round(pct(p, closes[-21]), 2),
                            "trend": "up" if p > s20 > s50 else "down" if p < s20 < s50 else "mixed"})
    contract = {k: v for k, v in fx["contract"].items()}
    return {"market": forex.market_status(now), "assets": assets, "context": context, "contract": contract,
            "dollar_news": (news or {}).get("forex", {}).get("USD", [])[:5],
            "stop_atr": forex.STOP_ATR, "target_r": forex.TARGET_R}


def context_macro(cfg):
    out = []
    for sid, name in cfg["macro_fred"].items():
        rows = store.read(store.DATA / "macro" / f"{sid}.csv")
        if len(rows) < 21:
            out.append({"id": sid, "name": name, "error": "not enough data"})
            continue
        v, v20 = float(rows[-1]["value"]), float(rows[-21]["value"])
        out.append({"id": sid, "name": name, "value": v, "date": rows[-1]["time"][:10],
                    "change_20_obs": round(v - v20, 3)})
    return out


def run():
    cfg = config.load()
    now = datetime.now(timezone.utc)
    try:
        days = market.trading_days(now.astimezone(market.NY).date() - timedelta(days=1))
        session = market.stock_session(now, days)
    except FetchError as e:
        days, session = {}, "unknown"
        print(f"(could not load the market calendar: {e})")

    spy_ok, spy_p, spy_s50 = above_sma50("stocks", "SPY")
    btc_ok, btc_p, btc_s50 = above_sma50("crypto", "BTC/USD")
    regime = "risk_on" if spy_ok else "risk_off"
    assets = []
    for s in cfg["stocks"]:
        ok = above_sma50("stocks", s)[0] if s in GOLD else spy_ok
        assets.append(build_asset("stocks", s, now, session, days, bool(ok)))
    for s in cfg["crypto"]:
        ok = above_sma50("crypto", s)[0] if s in GOLD else btc_ok
        assets.append(build_asset("crypto", s, now, session, days, bool(ok)))

    news = load_news()
    names = {k: v for k, v in cfg.get("names", {}).items() if not k.startswith("_")}
    for a in assets:
        apply_news(a, news, names, now)
    news_note = "no news yet: run news.py"
    if news:
        age_h = (now - ts(news["fetched_at"])).total_seconds() / 3600
        news_note = f"news fetched {age_h:.1f} h ago" + (" (old: run news.py)" if age_h > NEWS_STALE_HOURS else "")

    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "news_status": news_note,
        "headlines": (news or {}).get("market", [])[:8],
        "events": (news or {}).get("events", []),
        "generated_at_bangkok": market.bangkok(now),
        "market": {
            "stock_session": session,
            "regime": regime,
            "spy_price": spy_p, "spy_sma50": spy_s50,
            "btc_price": btc_p, "btc_sma50": btc_s50, "crypto_backdrop": "positive" if btc_ok else "negative",
            "max_position_pct": 10 if spy_ok else 5,
            "cash_reserve_pct": 10,
            "note": "Rules from your agent: max 10% of the portfolio per position (5% while SPY is below its "
                    "50-day average), keep at least 10% cash. View only: you place trades in the Alpaca app.",
        },
        "assets": assets,
        "forex": build_forex(cfg, now, news, names),
        "context": {"macro": context_macro(cfg)},
        "disclaimer": "Signals are small statistical edges, not predictions. Confidence is low unless stated. "
                      "High confidence is only given after a style passes the backtest.",
    }


CHART_DAYS = 250             # daily candles shown on each chart
CHART_15M_DAYS = 3           # 15-minute candles shown on each chart
BKK_OFFSET = 7 * 3600        # charts show times in Bangkok (UTC+7)


def export_charts(cfg):
    """public/charts/<SYMBOL>.json: candles + SMA20/SMA50 for the dashboard's charts.

    Daily candles use plain dates; 15-minute candles use Unix seconds shifted to Bangkok time,
    because the chart library prints times as UTC.
    """
    out_dir = OUT.parent / "charts"
    out_dir.mkdir(exist_ok=True)
    groups = ([("stocks", s) for s in cfg["stocks"]] + [("crypto", s) for s in cfg["crypto"]]
              + [("forex", p["symbol"]) for p in cfg["forex"]["pairs"]])
    for group, sym in groups:
        daily = store.read(store.path_for(group, sym, "1Day"))
        if not daily:
            continue
        day_of = market.ny_date if group == "stocks" else market.utc_date
        rd = (lambda x: forex.rnd(sym, x)) if group == "forex" else styles.r
        closes = [float(b["close"]) for b in daily]
        candles, s20, s50 = [], [], []
        start = max(0, len(daily) - CHART_DAYS)
        for i in range(start, len(daily)):
            b, t = daily[i], str(day_of(daily[i]["time"]))
            candles.append({"time": t, "open": float(b["open"]), "high": float(b["high"]),
                            "low": float(b["low"]), "close": float(b["close"])})
            if i >= 19:
                s20.append({"time": t, "value": rd(sum(closes[i - 19:i + 1]) / 20)})
            if i >= 49:
                s50.append({"time": t, "value": rd(sum(closes[i - 49:i + 1]) / 50)})
        m15 = store.read(store.path_for(group, sym, "1h" if group == "forex" else "15Min"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=10 if group == "forex" else CHART_15M_DAYS)
        intraday = [{"time": int(ts(b["time"]).timestamp()) + BKK_OFFSET, "open": float(b["open"]),
                     "high": float(b["high"]), "low": float(b["low"]), "close": float(b["close"])}
                    for b in m15 if ts(b["time"]) >= cutoff]
        safe = sym.replace("/", "-")
        store.write_text(out_dir / f"{safe}.json",
                         json.dumps({"symbol": sym, "daily": candles, "sma20": s20, "sma50": s50, "m15": intraday},
                                    separators=(",", ":")))


def table(d):
    m = d["market"]
    print(f"Signals at {d['generated_at_bangkok']} Bangkok | US stocks: {m['stock_session']} | "
          f"market {m['regime'].replace('_', '-')} (SPY {m['spy_price']} vs 50-day {m['spy_sma50']}) | "
          f"crypto backdrop {m['crypto_backdrop']} | max position {m['max_position_pct']}%\n")
    print(f"{'symbol':<10}{'price':>11}{'chg%':>8}  {'signal':<6} details")
    order = {"buy": 0, "watch": 1, "sell": 2, "hold": 3, "none": 4}
    for a in sorted(d["assets"], key=lambda a: (order[a["signal"]], a["symbol"])):
        bits = [f"{b['style']}/{b['timeframe']} ({b['confidence']})" for b in a["buys"]]
        if a["signal"] == "sell":
            bits.append(next(e["reason"] for e in a["exits"] if e["style"] == "trend"))
        bits += [f"! {f}" for f in a["flags"]]
        if a.get("news"):
            n = a["news"][0]
            bits.append(f"news: {n['label']} \"{n['headline'][:55]}\"")
        price = a.get("price", "-")
        chg = f"{a['change_pct']:+.2f}" if "change_pct" in a else "-"
        print(f"{a['symbol']:<10}{price:>11}{chg:>8}  {a['signal']:<6} {'; '.join(bits)}")
    print("\nUpcoming events (Bangkok time):")
    for e in d["events"][:6]:
        print(f"  {e['bangkok']:<17} {e['name']}")
    print(f"({d['news_status']})")
    fx = d["forex"]
    print(f"\nForex & gold for XM ({'open' if fx['market']['open'] else 'closed'}; sessions: {', '.join(fx['market']['sessions']) or '-'}):")
    for a in fx["assets"]:
        sets = "; ".join(f"{x['direction']} {x['style']} SL {x['stop_price']} TP {x['target_price']}" for x in a["setups"])
        print(f"  {a['symbol']:<9}{a.get('price', '-'):>12}  {a.get('change_pct', 0):+.2f}%  ATR {a.get('atr_pct', '-')}%  "
              f"{a['signal']:<6} {sets} {'! ' + '; '.join(a['flags']) if a['flags'] else ''}")
    for c in fx["context"]:
        print(f"  {c['symbol']:<9}{c['price']:>12}  {c['change_1d_pct']:+.2f}%  (context only, trend {c['trend']})")
    print("\nContext (view only):")
    for x in d["context"]["macro"]:
        if "error" not in x:
            print(f"  {x['name']:<34}{x['value']:>9}  ({x['date']}, change over 20 readings {x['change_20_obs']:+})")
    print(f"\nSaved {OUT}")


def update():
    """Compute signals, save public/signals.json and the chart files. Used by run_scanner.py too."""
    d = run()
    store.write_text(OUT, json.dumps(d, indent=2))
    export_charts(config.load())
    return d


def main():
    d = update()
    if "--json" in sys.argv:
        print(json.dumps(d, indent=2))
    else:
        table(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
