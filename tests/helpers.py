"""Synthetic market data for tests (no network, no cache). Writes pickles in the OfflineData layout."""
import datetime as dt
import numpy as np, pandas as pd
from pulsebot.market_time import ET, is_trading_day

def trading_days(end, n):
    out, d = [], end
    while len(out) < n:
        if is_trading_day(d): out.append(d)
        d -= dt.timedelta(days=1)
    return out[::-1]

def make_cache(dirpath, symbols, end_day, seed=1, n_daily=400, n_intraday=25, base=100.0):
    rng = np.random.default_rng(seed)
    for k, s in enumerate(symbols):
        days = trading_days(end_day, n_daily); iday = set(days[-n_intraday:])
        px = base * (1 + k); drows, m5rows = [], []
        for d in days:
            if d in iday:
                o = px; t = dt.datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET); c = o
                hi = lo = o
                for i in range(78):
                    op = c; c = op * (1 + rng.normal(0, 0.0015)); h = max(op, c) * (1 + abs(rng.normal(0, 0.0005)))
                    l = min(op, c) * (1 - abs(rng.normal(0, 0.0005)))
                    m5rows.append((t + dt.timedelta(minutes=5 * i), op, h, l, c, 1000)); hi, lo = max(hi, h), min(lo, l)
                drows.append((d, o, hi, lo, c, 78000)); px = c
            else:
                o = px; c = o * (1 + rng.normal(0, 0.012)); h = max(o, c) * (1 + abs(rng.normal(0, 0.004))); l = min(o, c) * (1 - abs(rng.normal(0, 0.004)))
                drows.append((d, o, h, l, c, 1e6)); px = c
        cols = ["Open", "High", "Low", "Close", "Volume"]
        dd = pd.DataFrame([r[1:] for r in drows], index=pd.DatetimeIndex([pd.Timestamp(r[0]) for r in drows]), columns=cols)
        m5 = pd.DataFrame([r[1:] for r in m5rows], index=pd.DatetimeIndex([r[0] for r in m5rows]), columns=cols)
        # 1H bars 09:30..15:30 from 5m
        key = [(t.date(), (t.hour * 60 + t.minute - 570) // 60) for t in m5.index]
        g = m5.groupby(pd.Index([f"{a}|{b}" for a, b in key]), sort=False)
        h = pd.DataFrame({"Open": g.Open.first(), "High": g.High.max(), "Low": g.Low.min(), "Close": g.Close.last(), "Volume": g.Volume.sum()})
        h.index = pd.DatetimeIndex([dt.datetime.fromisoformat(i.split("|")[0]).replace(hour=9, minute=30, tzinfo=ET) + dt.timedelta(hours=int(i.split("|")[1])) for i in h.index])
        dd.to_pickle(f"{dirpath}/{s}_1d.pkl"); m5.to_pickle(f"{dirpath}/{s}_5m.pkl"); h.to_pickle(f"{dirpath}/{s}_60m.pkl")
