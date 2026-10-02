import datetime as dt
from zoneinfo import ZoneInfo
from pulsebot import market_time as T

UTC = ZoneInfo("UTC")

def test_dst_summer_and_winter_open_in_utc():
    o, c = T.session_bounds(dt.date(2026, 7, 15))            # EDT: 09:30 ET = 13:30 UTC
    assert o.astimezone(UTC).hour == 13 and o.astimezone(UTC).minute == 30 and c.astimezone(UTC).hour == 20
    o, c = T.session_bounds(dt.date(2026, 12, 15))           # EST: 09:30 ET = 14:30 UTC
    assert o.astimezone(UTC).hour == 14 and c.astimezone(UTC).hour == 21

def test_phase_from_utc_clock_both_seasons():
    # same UTC time 13:40 -> open in summer, pre-market in winter
    s = dt.datetime(2026, 7, 15, 13, 40, tzinfo=UTC).astimezone(T.ET)
    w = dt.datetime(2026, 12, 15, 13, 40, tzinfo=UTC).astimezone(T.ET)
    assert T.phase(s) == "open" and T.phase(w) == "pre"
    assert T.phase(dt.datetime(2026, 7, 15, 16, 10, tzinfo=T.ET)) == "post"
    assert T.phase(dt.datetime(2026, 7, 15, 16, 40, tzinfo=T.ET)) == "closed"

def test_dst_switch_days():
    # 2026-03-08 and 2026-11-01 are the US DST switch Sundays; the following Mondays must open 09:30 ET
    for d, utc_h in ((dt.date(2026, 3, 9), 13), (dt.date(2026, 11, 2), 14)):
        o, _ = T.session_bounds(d)
        assert o.astimezone(UTC).hour == utc_h

def test_holidays_weekends_early_close():
    assert not T.is_trading_day(dt.date(2026, 11, 26))       # Thanksgiving
    assert not T.is_trading_day(dt.date(2026, 10, 3))        # Saturday
    assert T.is_trading_day(dt.date(2026, 10, 2))
    assert T.phase(dt.datetime(2026, 12, 25, 11, 0, tzinfo=T.ET)) == "holiday"
    _, c = T.session_bounds(dt.date(2026, 11, 27)); assert c.hour == 13
    assert T.phase(dt.datetime(2026, 11, 27, 13, 10, tzinfo=T.ET)) == "post"

def test_closed_bar_last_hour_capped_at_close():
    b = dt.datetime(2026, 9, 30, 15, 30, tzinfo=T.ET)
    assert not T.is_closed_bar(b, 60, dt.datetime(2026, 9, 30, 15, 59, tzinfo=T.ET))
    assert T.is_closed_bar(b, 60, dt.datetime(2026, 9, 30, 16, 0, tzinfo=T.ET))   # 15:30-16:00 bar closes at 16:00
    assert not T.is_closed_bar(dt.datetime(2026, 9, 30, 10, 30, tzinfo=T.ET), 60, dt.datetime(2026, 9, 30, 11, 20, tzinfo=T.ET))
