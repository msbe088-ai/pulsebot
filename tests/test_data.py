import datetime as dt
import pandas as pd
import pulsebot.data as D
from pulsebot.data import LiveData, YFProvider

def test_no_stooq_anywhere():
    assert not hasattr(D, "StooqProvider") and LiveData(primary=object()).source == "yfinance"

class Fake:
    def __init__(self, have): self.have = have; self.calls = []
    def fetch(self, symbols, interval, period=None):
        self.calls.append(list(symbols))
        df = pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]}, index=[dt.date(2026, 9, 30)])
        return {s: df for s in symbols if s in self.have}, [s for s in symbols if s not in self.have]

def test_livedata_records_failures_without_fallback():
    p = Fake({"A"})
    ld = LiveData(primary=p)
    out = ld.fetch(["A", "B"], "1d", "3y")
    assert set(out) == {"A"} and ld.failed == {"1d": ["B"]} and p.calls == [["A", "B"]]

def test_yfinance_three_retries_then_fail():
    sleeps = []; calls = []
    class YF(YFProvider):
        def _download(self, batch, interval, period):
            calls.append(list(batch)); raise RuntimeError("rate limited")
    out, failed = YF(sleep=sleeps.append).fetch(["A", "B"], "1d", "3y")
    assert out == {} and failed == ["A", "B"] and len(calls) == 3 and len(sleeps) == 3

def test_yfinance_batches_of_ten_and_retry_success():
    calls = []
    idx = pd.DatetimeIndex(["2026-09-30"])
    class YF(YFProvider):
        def _download(self, batch, interval, period):
            calls.append(list(batch))
            if len(calls) == 1: raise RuntimeError("temporary")
            cols = pd.MultiIndex.from_product([batch, ["Open", "High", "Low", "Close", "Volume"]])
            return pd.DataFrame([[1.0] * len(cols)], index=idx, columns=cols)
    syms = [f"S{i}" for i in range(12)]
    out, failed = YF(sleep=lambda s: None).fetch(syms, "1d", "3y")
    assert failed == [] and len(out) == 12 and [len(c) for c in calls] == [10, 10, 2]

def test_yfinance_retries_only_missing_symbols():
    calls = []
    idx = pd.DatetimeIndex(["2026-09-30"])
    class YF(YFProvider):
        def _download(self, batch, interval, period):
            calls.append(list(batch))
            ok = [b for b in batch if b != "B" or len(calls) >= 2]
            cols = pd.MultiIndex.from_product([batch, ["Open", "High", "Low", "Close", "Volume"]])
            row = [1.0 if c[0] in ok else float("nan") for c in cols]
            return pd.DataFrame([row], index=idx, columns=cols)
    out, failed = YF(sleep=lambda s: None).fetch(["A", "B"], "1d", "3y")
    assert failed == [] and calls == [["A", "B"], ["B"]]
