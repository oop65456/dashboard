"""Forex and gold setups for trading yourself on XM: both directions, ATR-based stops.

Why different from the stock rules: a 1% day is huge for EUR/USD but ordinary for a stock, so every
threshold here is measured in ATR (Average True Range: the pair's average daily range over 14 days).
The structure mirrors your agent's three styles, in BOTH directions, because forex can be sold short:

  trend     LONG:  price > SMA20 > SMA50, SMA5 > SMA20, price at most 1.5 ATR above SMA20
            SHORT: price < SMA20 < SMA50, SMA5 < SMA20, price at most 1.5 ATR below SMA20
  momentum  LONG:  price within 0.25 ATR of the 20-day high and up at least 0.5 ATR today
            SHORT: price within 0.25 ATR of the 20-day low and down at least 0.5 ATR today
  dip       LONG:  SMA50 < price < SMA20 and (1 ATR below SMA20, or down 0.75 ATR today)
            SHORT: SMA20 < price < SMA50 and (1 ATR above SMA20, or up 0.75 ATR today)

Every setup gets a FIXED stop-loss 1.5 ATR away and a take-profit 2x that distance (2R), because
a fixed SL/TP sits on XM's server, while MetaTrader trailing stops only work while your terminal runs.
These rules are adapted and NOT backtested: confidence is always low until Phase 8 tests them.
"""
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from .indicators import sma
from .styles import r

STOP_ATR = 1.5
TARGET_R = 2.0
NY = ZoneInfo("America/New_York")

RISK = {
    "trend": "Trends in currencies can reverse sharply on a central-bank surprise or data release.",
    "momentum": "Breakouts often fail and snap back, especially outside the London/New York sessions.",
    "dip": "The pullback may be the start of a reversal, not a pause.",
}
LEVERAGE_NOTE = "Leveraged CFD: a stop can be skipped over (slippage) when the price gaps, e.g. at news or the weekly open."


def atr(bars, n=14):
    """Average True Range of the last n completed bars (simple average of the true range)."""
    if len(bars) < n + 1:
        return None
    trs = []
    for prev, b in zip(bars[-n - 1:-1], bars[-n:]):
        h, l, pc = float(b["high"]), float(b["low"]), float(prev["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / n


def digits(symbol):
    """Decimals XM-style quotes use: gold 2, JPY pairs 3, other pairs 5."""
    return 2 if symbol.startswith("XAU") else 3 if "JPY" in symbol else 5


def rnd(symbol, x):
    return None if x is None else round(x, digits(symbol))


def pip_size(symbol):
    """Price step called a 'pip': 0.01 for JPY pairs, 0.0001 for others. Gold is shown in dollars."""
    if symbol.startswith("XAU"):
        return None
    return 0.01 if "JPY" in symbol else 0.0001


def indicators(completed, price):
    if len(completed) < 60:
        return {"error": f"only {len(completed)} completed daily bars (need 60)"}
    closes = [float(b["close"]) for b in completed]
    a = atr(completed)
    prev = closes[-1]
    return {"price": price, "prev_close": prev, "change": price - prev,
            "change_pct": round((price / prev - 1) * 100, 2),
            "sma5": sma(closes, 5), "sma20": sma(closes, 20), "sma50": sma(closes, 50),
            "high20": max(float(b["high"]) for b in completed[-20:]),
            "low20": min(float(b["low"]) for b in completed[-20:]),
            "atr": a, "atr_pct": round(a / price * 100, 2)}


def setups(i, symbol):
    p, ch, s5, s20, s50, A = i["price"], i["change"], i["sma5"], i["sma20"], i["sma50"], i["atr"]
    out = []

    def fmt(x):
        return f"{x:.{digits(symbol)}f}"

    def add(direction, style, reason, wrong_if):
        sign = 1 if direction == "long" else -1
        stop = p - sign * STOP_ATR * A
        target = p + sign * TARGET_R * STOP_ATR * A
        pip = pip_size(symbol)
        out.append({"direction": direction, "style": style, "timeframe": "daily", "confidence": "low",
                    "confidence_why": "forex rules adapted from the stock styles, not backtested yet; leveraged product",
                    "reason": reason, "risk": RISK[style] + " " + LEVERAGE_NOTE, "wrong_if": wrong_if,
                    "entry": rnd(symbol, p), "stop_price": rnd(symbol, stop), "target_price": rnd(symbol, target),
                    "stop_distance": STOP_ATR * A, "stop_pips": round(STOP_ATR * A / pip, 1) if pip else None,
                    "reward_risk": TARGET_R})

    # LONG
    if p > s20 > s50 and s5 > s20 and p <= s20 + 1.5 * A:
        add("long", "trend", f"price {fmt(p)} > SMA20 {fmt(s20)} > SMA50 {fmt(s50)}, SMA5 above SMA20, "
                             f"{(p - s20) / A:.1f} ATR above SMA20", f"a daily close below SMA20 ({fmt(s20)})")
    if p >= i["high20"] - 0.25 * A and ch >= 0.5 * A:
        add("long", "momentum", f"price within 0.25 ATR of the 20-day high {fmt(i['high20'])}, up {ch / A:.1f} ATR today",
            f"a daily close back below SMA5 ({fmt(s5)})")
    if s50 < p < s20 and (p <= s20 - A or ch <= -0.75 * A):
        add("long", "dip", f"pullback between SMA50 {fmt(s50)} and SMA20 {fmt(s20)}: {(p - s20) / A:.1f} ATR vs SMA20, "
                           f"{ch / A:+.1f} ATR today", f"a daily close below SMA50 ({fmt(s50)})")
    # SHORT (mirror image)
    if p < s20 < s50 and s5 < s20 and p >= s20 - 1.5 * A:
        add("short", "trend", f"price {fmt(p)} < SMA20 {fmt(s20)} < SMA50 {fmt(s50)}, SMA5 below SMA20, "
                              f"{(s20 - p) / A:.1f} ATR below SMA20", f"a daily close above SMA20 ({fmt(s20)})")
    if p <= i["low20"] + 0.25 * A and ch <= -0.5 * A:
        add("short", "momentum", f"price within 0.25 ATR of the 20-day low {fmt(i['low20'])}, down {-ch / A:.1f} ATR today",
            f"a daily close back above SMA5 ({fmt(s5)})")
    if s20 < p < s50 and (p >= s20 + A or ch >= 0.75 * A):
        add("short", "dip", f"rally between SMA20 {fmt(s20)} and SMA50 {fmt(s50)} in a downtrend: "
                            f"{(p - s20) / A:+.1f} ATR vs SMA20, {ch / A:+.1f} ATR today", f"a daily close above SMA50 ({fmt(s50)})")
    return out


SESSIONS = [("Tokyo", "Asia/Tokyo"), ("London", "Europe/London"), ("New York", "America/New_York")]


def market_status(now_utc):
    """Forex trades from Sunday 17:00 to Friday 17:00 New York time. Also which main centres are open now."""
    ny = now_utc.astimezone(NY)
    wd, t = ny.weekday(), ny.time()          # Monday = 0 ... Sunday = 6
    is_open = not (wd == 5 or (wd == 4 and t >= dtime(17)) or (wd == 6 and t < dtime(17)))
    active = []
    for name, tz in SESSIONS:
        local = now_utc.astimezone(ZoneInfo(tz))
        if local.weekday() < 5 and dtime(8) <= local.time() < dtime(17):
            active.append(name)
    if is_open and not active:
        active = ["Sydney / quiet hours"]
    # Next weekly change: Friday 17:00 New York close if open, else Sunday 17:00 reopen.
    days = (4 - wd) % 7 if is_open else (6 - wd) % 7
    nxt = (ny + timedelta(days=days)).replace(hour=17, minute=0, second=0, microsecond=0)
    return {"open": is_open, "sessions": active if is_open else [], "next_change": nxt.isoformat(),
            "note": "London + New York overlap (20:00-23:00 Bangkok in winter) is usually the busiest time."}


def lot_size(symbol, price, stop_distance, balance, risk_pct, units_per_lot, leverage):
    """Lots so that hitting the stop loses about risk_pct of the balance (account in USD).

    Loss per 1.00 lot at the stop = stop distance x units, in the QUOTE currency (the second one).
    Quote USD (EUR/USD, XAU/USD): already dollars. Base USD (USD/JPY): divide by the price to get dollars.
    """
    base, quote = symbol.split("/")
    loss_per_lot = stop_distance * units_per_lot
    if quote != "USD":
        loss_per_lot /= price
    risk_usd = balance * risk_pct / 100
    lots = int(risk_usd / loss_per_lot * 100) / 100            # round DOWN to 0.01 lot
    value_usd = lots * units_per_lot * (1 if base == "USD" else price)
    return {"lots": lots, "risk_usd": round(lots * loss_per_lot, 2), "margin_usd": round(value_usd / leverage, 2),
            "loss_per_lot_usd": round(loss_per_lot, 2)}
