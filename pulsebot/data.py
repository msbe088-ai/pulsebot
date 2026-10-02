"""Market data. Live: yfinance only (batched, 3 retries with backoff). Offline: cached history replayed at a
simulated time (dry-run samples / tests). Every frame: columns Open High Low Close Volume.
Daily index = naive dates (datetime.date); intraday index = tz-aware America/New_York bar START times."""
import logging, time, datetime as dt
import pandas as pd
from .config import DATA
from .market_time import ET

log = logging.getLogger("pulsebot.data")
COLS = ["Open", "High", "Low", "Close", "Volume"]

def _clean(df):
    df = df[COLS].dropna(subset=["Open", "High", "Low", "Close"]).copy()
    df["Volume"] = df["Volume"].fillna(0)
    return df

class YFProvider:
    name = "yfinance"
    def __init__(self, sleep=time.sleep):
        self.sleep = sleep
    def _download(self, batch, interval, period):
        import yfinance as yf
        return yf.download(batch, period=period, interval=interval, group_by="ticker", progress=False, auto_adjust=False,
                           prepost=False, threads=True)
    def fetch(self, symbols, interval, period):
        out, failed = {}, []
        for i in range(0, len(symbols), DATA["batch"]):
            batch = symbols[i:i + DATA["batch"]]; todo = list(batch)
            for attempt in range(DATA["retries"]):
                try:
                    raw = self._download(todo, interval, period)
                    for s in list(todo):
                        try:
                            df = _clean(raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw)
                        except Exception:
                            continue
                        if len(df):
                            if interval == "1d":
                                df.index = [x.date() for x in pd.to_datetime(df.index)]
                            else:
                                idx = pd.to_datetime(df.index)
                                df.index = idx.tz_convert(ET) if idx.tz is not None else idx.tz_localize("UTC").tz_convert(ET)
                            out[s] = df; todo.remove(s)
                except Exception as e:
                    log.warning("yfinance %s %s attempt %d failed: %s", interval, batch, attempt + 1, e)
                if not todo:
                    break
                self.sleep(DATA["backoff_s"] * (attempt + 1))
            failed += todo
        return out, failed

class LiveData:
    """yfinance only (decision 2026-10-02: no Stooq fallback). 3 retries with backoff inside YFProvider; whatever is still
    missing is recorded in .failed and the engine sends the Arabic technical-problem message (msg 15)."""
    source = "yfinance"
    def __init__(self, primary=None):
        self.primary = primary or YFProvider(); self.failed = {}
    def fetch(self, symbols, interval, period):
        out, failed = self.primary.fetch(symbols, interval, period)
        if failed:
            self.failed[interval] = failed
        return out

class OfflineData:
    """Replays cached history at a simulated `now` (no network). Only bars that existed at `now` are returned:
    daily = completed days + today's partial (from closed 5m bars); 60m = closed bars + forming bar from closed 5m bars;
    5m = closed bars of today and earlier."""
    def __init__(self, cache_dir, now):
        self.dir = cache_dir; self.now = now; self.failed = {}; self._c = {}
    source = "بيانات مخزنة (تشغيل تجريبي)"
    def _load(self, s, iv):
        k = (s, iv)
        if k not in self._c:
            df = pd.read_pickle(f"{self.dir}/{s}_{iv}.pkl")
            if iv == "1d":
                df.index = [x.date() for x in pd.to_datetime(df.index)]
            self._c[k] = df
        return self._c[k]
    def _m5(self, s):
        m = self._load(s, "5m")
        return m[m.index + pd.Timedelta(minutes=5) <= self.now]
    def fetch(self, symbols, interval, period=None):
        out = {}
        today = self.now.date()
        for s in symbols:
            try:
                m5 = self._m5(s); m5t = m5[m5.index.date == today]
                if interval == "5m":
                    out[s] = m5; continue
                if interval == "60m":
                    h = self._load(s, "60m")
                    h = h[(h.index >= self.now - pd.Timedelta(days=60)) & (h.index < self.now)]   # same depth as live (60d)
                    closed = h[[(b + pd.Timedelta(minutes=60) <= self.now) or (b.hour == 15 and b.minute == 30 and self.now.hour >= 16) for b in h.index]]
                    closed = closed[closed.index < self.now]
                    if len(m5t):
                        start = m5t.index[-1].floor("60min") + pd.Timedelta(minutes=30)
                        if start > m5t.index[-1]: start -= pd.Timedelta(minutes=60)
                        part = m5t[m5t.index >= start]
                        if len(part) and start not in closed.index and start + pd.Timedelta(minutes=60) > self.now:
                            row = pd.DataFrame({"Open": [part.Open.iloc[0]], "High": [part.High.max()], "Low": [part.Low.min()],
                                                "Close": [part.Close.iloc[-1]], "Volume": [part.Volume.sum()]}, index=[start])
                            closed = pd.concat([closed, row])
                    out[s] = closed; continue
                d = self._load(s, "1d"); d = d[[(today - dt.timedelta(days=3 * 366)) <= x < today for x in d.index]]   # same depth as live (3y)
                if len(m5t):
                    row = pd.DataFrame({"Open": [m5t.Open.iloc[0]], "High": [m5t.High.max()], "Low": [m5t.Low.min()], "Close": [m5t.Close.iloc[-1]],
                                        "Volume": [m5t.Volume.sum()]}, index=[today])
                    d = pd.concat([d, row])
                out[s] = d
            except Exception as e:
                log.warning("offline %s %s: %s", s, interval, e)
                self.failed.setdefault(interval, []).append(s)
        return out
