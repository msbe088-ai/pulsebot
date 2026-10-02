"""Pure indicator formulas. Inputs: pandas DataFrames with columns Open, High, Low, Close, Volume."""
import math
import numpy as np
import pandas as pd
from .config import P

def wilder_atr(df, n=None):
    """ATR_n (Wilder): TR = max(H-L, |H-C_prev|, |L-C_prev|); ATR_n = SMA_n(TR) for the first value, then (ATR*(n-1)+TR)/n."""
    n = n or P["ATR_N"]
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = np.empty(len(df))
    for i in range(len(df)):
        tr[i] = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = np.full(len(df), np.nan)
    if len(df) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(df)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return pd.Series(out, index=df.index)

def _group(daily, keys):
    keys = np.asarray(keys, dtype=np.int64)      # integer period ids (a list of tuples would be read as column names)
    g = daily.groupby(keys, sort=False)
    out = pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(), "Low": g["Low"].min(), "Close": g["Close"].last(), "Volume": g["Volume"].sum()})
    out.index = pd.Index(daily.index.to_series().groupby(keys, sort=False).first().values)
    return out

def to_weekly(daily):
    """weekly candles (ISO week) built from daily bars; index = first trading day of the week."""
    return _group(daily, [d.isocalendar()[0] * 100 + d.isocalendar()[1] for d in daily.index])

def to_monthly(daily):
    """monthly candles built from daily bars; index = first trading day of the month."""
    return _group(daily, [d.year * 100 + d.month for d in daily.index])

def trend(df):
    """Trend of a series of COMPLETED candles.
    up   : close[-1] > SMA_N[-1]  and  SMA_N[-1] > SMA_N[-1-K]
    down : close[-1] < SMA_N[-1]  and  SMA_N[-1] < SMA_N[-1-K]
    else neutral.  Returns dict(dir, close, sma, sma_prev) or dir='na' when fewer than N+K candles."""
    n, k = P["TREND_SMA_N"], P["TREND_SLOPE_K"]
    if df is None or len(df) < n + k:
        return {"dir": "na", "n": 0 if df is None else len(df)}
    s = df["Close"].rolling(n).mean()
    c, sm, sp = float(df["Close"].iloc[-1]), float(s.iloc[-1]), float(s.iloc[-1 - k])
    d = "up" if (c > sm and sm > sp) else "down" if (c < sm and sm < sp) else "neutral"
    return {"dir": d, "close": c, "sma": sm, "sma_prev": sp}

def pivots(df, k=None):
    """Swing highs/lows. A swing high at bar i: High[i] > max(High[i-k..i-1]) and High[i] >= max(High[i+1..i+k]).
    It becomes KNOWN only at bar i+k (confirmation). Returns lists of (confirm_index, pivot_index, price)."""
    k = k or P["PIVOT_K"]
    H, L = df["High"].values, df["Low"].values
    hs, ls = [], []
    for i in range(k, len(df) - k):
        if H[i] > H[i - k:i].max() and H[i] >= H[i + 1:i + k + 1].max():
            hs.append((i + k, i, float(H[i])))
        if L[i] < L[i - k:i].min() and L[i] <= L[i + 1:i + k + 1].min():
            ls.append((i + k, i, float(L[i])))
    return hs, ls

def structure_events(df, k=None):
    """Trend-change events on CLOSED 1H bars.
    Walk bars in order; keep the latest confirmed swing high SH and swing low SL (confirmed before the bar).
    Event 'up'   at bar j: structure != 'up'   and Close[j] > SH (bar fully closed beyond the swing).
    Event 'down' at bar j: structure != 'down' and Close[j] < SL.
    The first break only sets the initial structure (no event). Returns list of dicts."""
    hs, ls = pivots(df, k)
    hs_by = {}; ls_by = {}
    for c, i, p in hs: hs_by.setdefault(c, []).append(p)
    for c, i, p in ls: ls_by.setdefault(c, []).append(p)
    sh = sl = None; st = None; ev = []
    C = df["Close"].values
    for j in range(len(df)):
        if j in hs_by: sh = hs_by[j][-1]
        if j in ls_by: sl = ls_by[j][-1]
        if sh is not None and C[j] > sh and st != "up":
            if st is not None:
                ev.append({"bar": j, "time": df.index[j], "dir": "up", "level": sh, "close": float(C[j])})
            st = "up"
        elif sl is not None and C[j] < sl and st != "down":
            if st is not None:
                ev.append({"bar": j, "time": df.index[j], "dir": "down", "level": sl, "close": float(C[j])})
            st = "down"
    return ev, st

def round_step(price):
    st = P["ROUND_STEPS"][0]
    for s in P["ROUND_STEPS"]:
        if s <= P["ROUND_FRAC"] * price:
            st = s
    return st

def next_round(price, direction):
    """next round number strictly above (direction=+1) or below (-1) the price."""
    st = round_step(price)
    if direction > 0:
        r = math.floor(price / st) * st + st
        return round(r, 4)
    r = math.ceil(price / st) * st - st
    return round(r, 4)

def vol_score(daily_completed):
    """Big-move score. ratio_t = ATR14_t / ATR100_t on completed daily bars.
    score = share of the last VOL_LOOKBACK ratios that are <= today's ratio (percentile rank, 0..1).
    Returns dict(score, ratio, atr14, atr100) or None if history is too short."""
    a14 = wilder_atr(daily_completed, P["ATR_N"]); a100 = wilder_atr(daily_completed, P["ATR_LONG_N"])
    r = (a14 / a100).dropna()
    if len(r) < 60:
        return None
    w = r.iloc[-P["VOL_LOOKBACK"]:]
    score = float((w <= w.iloc[-1]).mean())
    return {"score": score, "ratio": float(w.iloc[-1]), "atr14": float(a14.iloc[-1]), "atr100": float(a100.iloc[-1]), "n": len(w)}
