"""US market clock. All times are America/New_York via zoneinfo, so EST/EDT (DST) is handled automatically.
The GitHub cron runs in UTC over a window wide enough for both EST and EDT; this module decides whether to work."""
import functools
import datetime as dt
from zoneinfo import ZoneInfo
from .config import MARKET

ET = ZoneInfo("America/New_York")
# NYSE full-day holidays (official calendar). Must be extended each year (README explains).
NYSE_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
    "2027-11-25", "2027-12-24",
}
# early close 13:00 ET
NYSE_EARLY_CLOSE = {"2026-11-27", "2026-12-24", "2027-11-26"}

def now_et(override=None):
    if override is not None:
        return override.astimezone(ET) if override.tzinfo else override.replace(tzinfo=ET)
    return dt.datetime.now(ET)

def is_trading_day(d):
    return d.weekday() < 5 and d.isoformat() not in NYSE_HOLIDAYS

@functools.lru_cache(maxsize=4096)
def session_bounds(d):
    o = dt.datetime(d.year, d.month, d.day, *MARKET["open"], tzinfo=ET)
    c = dt.datetime(d.year, d.month, d.day, 13, 0, tzinfo=ET) if d.isoformat() in NYSE_EARLY_CLOSE else \
        dt.datetime(d.year, d.month, d.day, *MARKET["close"], tzinfo=ET)
    return o, c

def phase(now):
    """'holiday' | 'pre' (before 09:30) | 'open' | 'post' (close .. close+30m: EOD work) | 'closed'"""
    d = now.date()
    if not is_trading_day(d):
        return "holiday"
    o, c = session_bounds(d)
    if now < o:
        return "pre"
    if now < c:
        return "open"
    if now < c + dt.timedelta(minutes=30):
        return "post"
    return "closed"

def bar_end(start, minutes, d_close):
    """end time of an intraday bar starting at `start`, capped at the session close (last 1H bar is 15:30-16:00)."""
    return min(start + dt.timedelta(minutes=minutes), d_close)

def is_closed_bar(start, minutes, now):
    _, c = session_bounds(start.date())
    return bar_end(start, minutes, c) <= now

def hhmm(t):
    return t.strftime("%H:%M")
