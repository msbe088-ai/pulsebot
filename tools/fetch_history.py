"""Build-time helper: download history for the hit-rate statistics and the offline dry-run replay (not used by the live bot)."""
import sys, time, yfinance as yf, pandas as pd
sys.path.insert(0, '.')
from pulsebot.config import SYMBOLS
OUT = 'data_cache'
for interval, period in (('1d', '20y'), ('60m', '730d'), ('5m', '60d')):
    for i in range(0, len(SYMBOLS), 10):
        batch = SYMBOLS[i:i+10]
        df = yf.download(batch, period=period, interval=interval, group_by='ticker', progress=False, auto_adjust=False, prepost=False, threads=True)
        for s in batch:
            x = df[s].dropna(subset=['Open', 'High', 'Low', 'Close'])[['Open', 'High', 'Low', 'Close', 'Volume']]
            x.to_pickle(f'{OUT}/{s}_{interval}.pkl'); print(s, interval, len(x), x.index[0], x.index[-1], flush=True)
        time.sleep(1)
