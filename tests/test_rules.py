import datetime as dt
import pandas as pd
from pulsebot import rules as R
from pulsebot.market_time import ET

def by(ts): return {t["name"]: t for t in ts}

def test_targets_up_formula():
    t = by(R.targets(101.3, 100.8, 1, 100.5, 2.0, 101.9, 99.0, 104.0, 97.0))
    assert (t["T1"]["price"], t["T1"]["src"]) == (101.9, "pdh")        # nearer than round 102
    assert (t["T2"]["price"], t["T2"]["src"]) == (104.0, "pwh")
    assert (t["T3"]["price"], t["T3"]["src"]) == (102.5, "open_atr")   # open + ATR
    assert t["T1"]["dist"] == 0.6 and t["T1"]["mult"] == 1.2 and t["T2"]["mult"] == 5.4 and t["T3"]["mult"] == 2.4

def test_targets_down_formula():
    t = by(R.targets(101.3, 101.8, -1, 100.5, 2.0, 101.9, 99.0, 104.0, 97.0))
    assert (t["T1"]["price"], t["T1"]["src"]) == (101.0, "round")
    assert (t["T2"]["price"], t["T2"]["src"]) == (97.0, "pwl")
    assert t["T3"]["price"] == 98.5

def test_targets_min_distance_and_t3_none():
    t = by(R.targets(101.95, 101.5, 1, 100.5, 2.0, 101.0, 99.0, 102.05, 97.0))
    assert t["T1"]["price"] == 103.0             # 102 is only 0.05 away (< 0.1 * ATR = 0.2) -> next round
    assert t["T2"]["price"] == 104.0 and t["T2"]["src"] == "round"   # prior-week high not beyond T1 -> next round
    t = by(R.targets(103.0, 102.0, 1, 100.5, 2.0, 101.0, 99.0, 110.0, 97.0))
    assert t["T3"]["price"] is None              # price already beyond open + ATR

def hours(rows, day=dt.date(2026, 9, 30)):
    idx = [dt.datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET) + dt.timedelta(hours=i) for i in range(len(rows))]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)

def test_stop_note_up_and_down():
    n = R.stop_note(hours([(100, 102, 99.5, 101), (101, 103, 98.8, 102)]), 1)
    assert n["side"] == "up" and n["stop"] == 99.5 and n["open"] == 100 and n["price"] == 101
    n2 = R.stop_note(hours([(100, 102, 99.5, 101), (101, 103, 98.8, 102)]), 2)
    assert n2["stop"] == 98.8 and n2["k"] == 2
    d = R.stop_note(hours([(100, 100.4, 98, 99)]), 1)
    assert d["side"] == "down" and d["stop"] == 100.4
    assert R.stop_note(hours([(100, 101, 99, 100)]), 1) is None
    assert R.stop_note(hours([(100, 101, 99, 100.5)]), 2) is None

def plan(dir_="up"):
    tg = R.targets(101.3, 100.8 if dir_ == "up" else 101.8, 1 if dir_ == "up" else -1, 100.5, 2.0, 101.9, 99.0, 104.0, 97.0)
    return {"dir": dir_, "entry": 101.3, "stop": 100.8 if dir_ == "up" else 101.8, "targets": tg, "hit": []}

def test_check_window_conservative_conflict_is_stop():
    assert R.check_window(plan(), 102.0, 100.7) == [("stop", 100.8)]      # T1 and stop both touched -> stop
    assert R.check_window(plan("down"), 101.9, 100.9) == [("stop", 101.8)]

def test_check_window_targets_in_price_order():
    assert R.check_window(plan(), 102.6, 101.0) == [("T1", 101.9), ("T3", 102.5)]
    p = plan(); p["hit"] = ["T1"]
    assert R.check_window(p, 102.0, 101.0) == []
    assert R.check_window(plan("down"), 101.5, 98.0) == [("T1", 101.0), ("T3", 98.5)]

def test_trailing_stop():
    p = plan()
    assert R.trailing_stop(p, "T1") == 101.3
    p["stop"] = 101.3
    assert R.trailing_stop(p, "T2") == 101.9
    p["stop"] = 102.0
    assert R.trailing_stop(p, "T2") == 102.0   # never loosens the stop

def test_prev_week_hl():
    idx = pd.bdate_range("2026-09-14", "2026-09-29")
    d = pd.DataFrame({"Open": 1, "High": range(len(idx)), "Low": range(len(idx)), "Close": 1}, index=[x.date() for x in idx])
    h, l = R.prev_week_hl(d, dt.date(2026, 9, 30))          # last completed week = 21..25 Sep (rows 5..9)
    assert (h, l) == (9.0, 5.0)
