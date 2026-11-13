"""The three trading styles, as rules in code.

DAILY rules are copied from your agent's Tools/Signals.py (v6) so the dashboard and the agent
always agree on what a signal means:
  trend    buy:  price > SMA20 > SMA50, SMA5 > SMA20, price no more than 5% above SMA20   stop 8%
  momentum buy:  price within 1% of the 20-day high, up >= 1% today, volume pace >= 1.0x  stop 5%
  dip      buy:  SMA50 < price < SMA20 and (>= 3% below SMA20 or down >= 2.5% today)       stop 8%
  trend exit:    SMA5 below SMA20 and price below SMA20 ("trend broken")
INTRADAY momentum (15-minute bars) is NEW and EXPERIMENTAL: always low confidence until the
backtester (Phase 8) has tested it.

Confidence: low by default. Medium only when the wider market agrees (see `confidence`).
High is deliberately never given yet: it is earned only after a style passes the backtest.
Every signal is a small edge, not a prediction.
"""
from .indicators import pct, sma

TRAIL = {"trend": 8.0, "momentum": 5.0, "dip": 8.0}

RISK = {
    "trend": "Buying after a long rise: a reversal can quickly take back recent gains.",
    "momentum": "Breakouts often fail and snap back into the old range.",
    "dip": "A dip can turn into a real downtrend (a 'falling knife').",
    "intraday": "Short-term moves reverse fast, and this rule is not backtested yet.",
}


def r(x):
    """Round a price sensibly: 2 decimals for prices of 10 or more, 4 for small ones."""
    if x is None:
        return None
    return round(x, 2) if abs(x) >= 10 else round(x, 4)


def daily_indicators(completed, price, today_volume, session_frac):
    """Indicators from COMPLETED daily bars (today's still-forming bar excluded) + the latest price."""
    if len(completed) < 60:
        return {"error": f"only {len(completed)} completed daily bars (need 60)"}
    closes = [float(b["close"]) for b in completed]
    vols = [float(b["volume"] or 0) for b in completed[-20:]]
    avg_vol = sum(vols) / 20
    pace = None
    if session_frac and avg_vol and today_volume is not None:
        pace = round(today_volume / (avg_vol * session_frac), 2)
    return {
        "price": r(price),
        "prev_close": r(closes[-1]),
        "change_pct": round(pct(price, closes[-1]), 2),
        "sma5": r(sma(closes, 5)), "sma20": r(sma(closes, 20)), "sma50": r(sma(closes, 50)),
        "sma50_10d_ago": r(sma(closes[:-10], 50)),
        "high20": r(max(float(b["high"]) for b in completed[-20:])),
        "volume_pace": pace,
        "last_completed_day": completed[-1]["time"][:10],
    }


def confidence(style, ind, regime_ok):
    """('low' | 'medium', why). Medium needs the market backdrop AND a style-specific confirmation."""
    rising50 = ind["sma50_10d_ago"] is not None and ind["sma50"] > ind["sma50_10d_ago"]
    if style in ("trend", "dip") and regime_ok and rising50:
        return "medium", "market backdrop is positive and the 50-day average is rising"
    if style == "momentum" and regime_ok and (ind["volume_pace"] or 0) >= 1.5:
        return "medium", "market backdrop is positive and volume is 1.5x+ normal"
    missing = [] if regime_ok else ["market backdrop is negative"]
    if style in ("trend", "dip") and not rising50:
        missing.append("50-day average not rising")
    if style == "momentum" and (ind["volume_pace"] or 0) < 1.5:
        missing.append("volume not clearly above normal")
    return "low", "default; " + ("; ".join(missing) or "no extra confirmation")


def daily_signals(ind, regime_ok):
    """Buy signals per style + exit notes, using exactly the agent's daily rules."""
    p, c, s5, s20, s50, h20, pace = (ind["price"], ind["change_pct"], ind["sma5"], ind["sma20"],
                                       ind["sma50"], ind["high20"], ind["volume_pace"])
    buys = []

    def add(style, reason, wrong_if):
        conf, why = confidence(style, ind, regime_ok)
        buys.append({"style": style, "timeframe": "daily", "confidence": conf, "confidence_why": why,
                     "reason": reason, "risk": RISK[style], "wrong_if": wrong_if,
                     "trail_pct": TRAIL[style], "stop_price": r(p * (1 - TRAIL[style] / 100))})

    if p > s20 > s50 and s5 > s20 and p <= s20 * 1.05:
        add("trend", f"price {p} > SMA20 {s20} > SMA50 {s50}, SMA5 {s5} > SMA20, "
                     f"{pct(p, s20):.1f}% above SMA20",
            f"a daily close below SMA20 ({s20}), or the 8% trailing stop is hit")
    if p >= 0.99 * h20 and c >= 1.0 and (pace is None or pace >= 1.0):
        add("momentum", f"price {p} within 1% of 20-day high {h20}, up {c}% today, volume pace "
                        + (f"{pace}x" if pace is not None else "n/a (outside the session)"),
            f"a daily close below SMA5 ({s5}), or the 5% trailing stop is hit")
    depth = pct(p, s20)
    if s50 < p < s20 and (depth <= -3.0 or c <= -2.5):
        add("dip", f"between SMA50 {s50} and SMA20 {s20}; {depth:.1f}% vs SMA20, {c}% today",
            f"a daily close below SMA50 ({s50}), or the 8% trailing stop is hit")

    exits = []
    if s5 < s20 and p < s20:
        exits.append({"style": "trend", "reason": f"trend broken: SMA5 {s5} < SMA20 {s20} and price {p} < SMA20"})
    if p < s5:
        exits.append({"style": "momentum", "reason": f"momentum lost: price {p} < SMA5 {s5}"})
    return buys, exits


def intraday_momentum(bars15):
    """EXPERIMENTAL 15-minute momentum. `bars15` = completed 15-min bars, oldest first.

    Fires when: close > its 20-bar average, that average is rising (vs 4 bars ago),
    close within 0.5% of the highest high of the last 32 bars (8 hours), and the last bar's
    volume is at least 1.2x the average of the 20 bars before it.
    """
    if len(bars15) < 40:
        return None
    closes = [float(b["close"]) for b in bars15]
    vols = [float(b["volume"] or 0) for b in bars15]
    last = closes[-1]
    m20, m20_prev = sma(closes, 20), sma(closes[:-4], 20)
    hi32 = max(float(b["high"]) for b in bars15[-32:])
    avg_v = sum(vols[-21:-1]) / 20
    vol_x = vols[-1] / avg_v if avg_v else 0
    if last > m20 > m20_prev and last >= 0.995 * hi32 and vol_x >= 1.2:
        return {"style": "momentum", "timeframe": "15min", "confidence": "low",
                "confidence_why": "experimental intraday rule, not backtested yet",
                "reason": f"15-min close {r(last)} > 20-bar avg {r(m20)} (rising), within 0.5% of 8-hour high "
                          f"{r(hi32)}, volume {vol_x:.1f}x normal",
                "risk": RISK["intraday"],
                "wrong_if": f"a 15-min close below its 20-bar average ({r(m20)}), or the 5% trailing stop is hit",
                "trail_pct": TRAIL["momentum"], "stop_price": r(last * 0.95)}
    return None
