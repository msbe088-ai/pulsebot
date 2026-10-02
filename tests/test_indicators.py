import datetime as dt
import numpy as np, pandas as pd
from pulsebot import indicators as I

def frame(closes, spread=1.0):
    c = np.asarray(closes, float)
    idx = pd.date_range("2025-01-01", periods=len(c), freq="D")
    return pd.DataFrame({"Open": c, "High": c + spread, "Low": c - spread, "Close": c, "Volume": 1}, index=[x.date() for x in idx])

def test_wilder_atr_constant_range():
    df = frame([100] * 30, spread=1.0)            # TR = 2 every bar
    a = I.wilder_atr(df, 14)
    assert np.isnan(a.iloc[12]) and abs(a.iloc[13] - 2.0) < 1e-12 and abs(a.iloc[-1] - 2.0) < 1e-12

def test_wilder_atr_uses_prev_close_gap():
    df = frame([100] * 20); df.iloc[-1, :4] = [110, 111, 109, 110]   # gap: TR = max(2, |111-100|, |109-100|) = 11
    a = I.wilder_atr(df, 14)
    assert abs(a.iloc[-1] - (a.iloc[-2] * 13 + 11) / 14) < 1e-9

def test_trend_up_down_neutral_na():
    assert I.trend(frame(range(100, 140)))["dir"] == "up"
    assert I.trend(frame(range(140, 100, -1)))["dir"] == "down"
    assert I.trend(frame(list(range(100, 135)) + [100]))["dir"] == "neutral"   # close < SMA but SMA still rising
    assert I.trend(frame(range(10)))["dir"] == "na"

def test_pivots_confirmed_k_bars_later():
    h = [1, 2, 3, 9, 3, 2, 1, 2, 3]
    df = pd.DataFrame({"High": h, "Low": [x - 1 for x in h]})
    hs, ls = I.pivots(df, 3)
    assert hs == [(6, 3, 9.0)]

def test_structure_first_break_initialises_then_event():
    # swings (k=3): low 95 (bar 3, known at bar 6), high 110 (bar 8, known at 11), low 103 (bar 11, known at 14).
    # bar 12 closes 111 > 110 -> first break only initialises 'up'; bar 17 closes 102 < 103 -> event 'down'
    closes = [100, 99, 98, 95, 98, 99, 100, 105, 110, 106, 104, 103, 111, 108, 107, 106, 104, 102, 101, 103, 104, 105, 100, 98]
    df = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes}, index=range(len(closes)))
    ev, st = I.structure_events(df, 3)
    assert [e["dir"] for e in ev] == ["down"]
    e = ev[0]; assert (e["bar"], e["level"], e["close"]) == (17, 103.0, 102.0) and st == "down"

def test_round_numbers():
    assert I.round_step(30) == 0.5          # 1% of 30 = 0.3 < 0.5 -> smallest step
    assert I.round_step(250) == 2.5 and I.round_step(773) == 5 and I.round_step(7600) == 50
    assert I.next_round(773.54, 1) == 775 and I.next_round(773.54, -1) == 770 and I.next_round(775, 1) == 780

def test_monthly_weekly_grouping():
    idx = pd.bdate_range("2026-01-01", "2026-03-31")
    df = pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 1}, index=[x.date() for x in idx])
    assert len(I.to_monthly(df)) == 3
    assert len(I.to_weekly(df)) == len({x.isocalendar()[:2] for x in df.index})

def test_vol_score_rank():
    rng = np.random.default_rng(0); c = 100 + np.cumsum(rng.normal(0, 1, 500))
    df = frame(c); df["High"] = df["Close"] + 1; df["Low"] = df["Close"] - 1
    df.iloc[-5:, 1] += 15                         # last days much wider range -> top rank
    v = I.vol_score(df)
    assert v["score"] == 1.0 and v["ratio"] > 1 and v["n"] == 252
    assert I.vol_score(frame(range(50))) is None
