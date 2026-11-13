"""When can you trade, and is the overall market risk-on or risk-off?

Session names (US stocks and GLD, all times New York):
  overnight 20:00-04:00 | pre-market 04:00-open | regular open-close | after-hours close-20:00 | closed
Trading days and early closes come from Alpaca's calendar, so holidays are handled.
Crypto and PAXG are always "24/7".
"""
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import env, net

NY = ZoneInfo("America/New_York")
BANGKOK = ZoneInfo("Asia/Bangkok")
CALENDAR_URL = "https://paper-api.alpaca.markets/v2/calendar"


def _t(hhmm):
    h, m = hhmm.split(":")
    return dtime(int(h), int(m))


def trading_days(start, days=8):
    """{date: (open, close)} for US trading days from `start` (a date) for the next `days` days."""
    d = net.get_json(CALENDAR_URL, params={"start": str(start), "end": str(start + timedelta(days=days))},
                     headers={"APCA-API-KEY-ID": env.get("APCA_API_KEY_ID") or "",
                              "APCA-API-SECRET-KEY": env.get("APCA_API_SECRET_KEY") or ""})
    return {datetime.strptime(c["date"], "%Y-%m-%d").date(): (_t(c["open"]), _t(c["close"])) for c in d}


def stock_session(now_utc, days):
    """Which US stock session is running at `now_utc`."""
    et = now_utc.astimezone(NY)
    today, t = et.date(), et.time()
    tomorrow = today + timedelta(days=1)
    if today in days:
        open_, close = days[today]
        if dtime(4, 0) <= t < open_:
            return "pre-market"
        if open_ <= t < close:
            return "regular"
        if close <= t < dtime(20, 0):
            return "after-hours"
        if t < dtime(4, 0):
            return "overnight"
    if t >= dtime(20, 0) and tomorrow in days:   # e.g. Sunday 20:00 opens the week
        return "overnight"
    return "closed"


def session_fraction(now_utc, days):
    """Share of today's regular session that has passed (0.05-1), used for the volume pace."""
    et = now_utc.astimezone(NY)
    if et.date() not in days:
        return None
    open_, close = days[et.date()]
    start = et.replace(hour=open_.hour, minute=open_.minute, second=0, microsecond=0)
    length = (close.hour * 60 + close.minute - open_.hour * 60 - open_.minute) * 60
    return min(1.0, max(0.05, (et - start).total_seconds() / length))


def bangkok(dt):
    return dt.astimezone(BANGKOK).strftime("%Y-%m-%d %H:%M")


def ny_date(iso_time):
    """The New York calendar date of an archive timestamp."""
    return datetime.fromisoformat(iso_time.replace("Z", "+00:00")).astimezone(NY).date()


def utc_date(iso_time):
    return datetime.fromisoformat(iso_time.replace("Z", "+00:00")).astimezone(timezone.utc).date()
