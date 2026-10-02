"""All settings and every formula parameter in one place. Logic identifiers are ASCII; display text is Arabic (messages.py)."""
import json, os

BASE_SYMBOLS = ["SPY", "QQQ", "IWM", "^GSPC", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "JPM"]
# Top 15 US companies by market cap, fetched at build time 2026-10-02 from companiesmarketcap.com:
# NVDA AAPL GOOG MSFT AMZN SPCX META AVGO TSLA MU BRK-B LLY AMD JPM WMT  (GOOG deduped against GOOGL = same company)
TOP15_AT_BUILD = ["NVDA", "AAPL", "GOOG", "MSFT", "AMZN", "SPCX", "META", "AVGO", "TSLA", "MU", "BRK-B", "LLY", "AMD", "JPM", "WMT"]
SAME_COMPANY = {"GOOG": "GOOGL"}

def build_symbols():
    out = []
    for s in BASE_SYMBOLS + [SAME_COMPANY.get(x, x) for x in TOP15_AT_BUILD]:
        if s not in out:
            out.append(s)
    return out

SYMBOLS = build_symbols()

# ---- feature toggles (every feature can be switched off). news is OFF by default. ----
DEFAULT_TOGGLES = {
    "morning_heartbeat": True,   # msg 1
    "hourly_summary": True,      # msg 2
    "trend_change": True,        # msg 3
    "big_move": True,            # msg 4
    "stop_notes": True,          # msg 5 / 6
    "targets": True,             # msg 7..12
    "trail_stop_after_targets": True,  # after T1 stop->entry, after T2 stop->T1 (tracking + suggestion)
    "show_hit_stats": True,      # historical hit rates inside msg 7
    "news": False,               # msg 13
    "eod_summary": True,         # msg 14
    "tech_alerts": True,         # msg 15
    "commands": True,            # getUpdates command handling
    # ---- delivery / volume (added 2026-10-02: ~280 -> ~20-40 messages/day) ----
    "summary_consolidated": True,  # msg 2 = ONE message per closed 1H bar for all symbols (off = one message per symbol)
    "notable_only": True,          # msgs 5/7 only for NOTABLE symbols (formula: NOTABLE_RULE below; off = all symbols)
    "notes_consolidated": True,    # msgs 5+7 = ONE message after hour 1 and ONE after hour 2 (off = one per symbol)
    "batch_events": True,          # msgs 3/4/6/8-12 produced in the same run are combined into one message per group
}

# NOTABLE (used when notable_only is on), evaluated for symbol s when its hour-k bar (k = 1, 2) closes:
#   notable(s) = big_move_active(s) OR trend_change_today(s) OR open_plan(s)
#   big_move_active(s)    : vol_score(s).score >= P["VOL_TOP_PCT"]  (the msg-4 condition, completed daily bars, all day)
#   trend_change_today(s) : a msg-3 event (1H close beyond the last confirmed swing) today at or before this bar
#   open_plan(s)          : s has a target plan with status 'open' (plans are created at hour 1, so this matters at hour 2)
NOTABLE_RULE = "big_move_active OR trend_change_today OR open_plan"

P = {
    # trend per timeframe: up if close > SMA(N) and SMA(N) > SMA(N) SLOPE_K bars earlier; down = mirror; else neutral
    "TREND_SMA_N": 20, "TREND_SLOPE_K": 5,
    # swing (pivot) on 1H: high[i] > highs of PIVOT_K bars on each side; confirmed only PIVOT_K bars later
    "PIVOT_K": 3,
    "ATR_N": 14,
    # big-move score: ratio = ATR14 / ATR100 (completed daily bars); alert if percentile rank of today's ratio within the
    # last VOL_LOOKBACK ratios >= VOL_TOP_PCT (top 20%)
    "ATR_LONG_N": 100, "VOL_LOOKBACK": 252, "VOL_TOP_PCT": 0.80,
    # round-number grid: step = largest s in ROUND_STEPS with s <= ROUND_FRAC * price
    "ROUND_STEPS": [0.5, 1, 2.5, 5, 10, 25, 50, 100, 250], "ROUND_FRAC": 0.01,
    # a target must be at least T_MIN_DIST_ATR * daily ATR away from the entry
    "T_MIN_DIST_ATR": 0.10,
    "TINY_STOP_ATR": 0.05,      # warn when |entry - stop| < 0.05 * daily ATR
    # stop-note statistics (research2, 50 US symbols, 2023-11..2026-10, out-of-sample): P(day low already in | close of hour k > open)
    "STOP_STATS": {"up": {1: (70.9, 52.4), 2: (81.7, 62.0)}, "down": {1: (70.5, 50.4), 2: (81.6, 60.3)}},
    # big-move statistic shown in msg 4 is loaded from stats.json (computed by tools/hit_rates.py)
    "PLAN_HOURS": [1],          # targets/plans are created at the hour-1 stop note (one plan pair per symbol per day)
    "NOTE_HOURS": [1, 2],       # stop notes after hour 1 and hour 2
}

MARKET = {"open": (9, 30), "close": (16, 0), "run_end": (16, 30), "morning_from": (9, 0)}
# separator line between symbol blocks in consolidated messages: SEPARATOR_LEN x '━' (user picks 20 / 24 / 28)
SEPARATOR_LEN = int(os.environ.get("PULSEBOT_SEPARATOR_LEN", "24"))
TELEGRAM = {"min_interval_s": 1.2, "max_per_run": 60, "max_len": 3900, "retries": 3}   # max_len in UTF-16 units of the RAW text incl. HTML tags (Telegram limit 4096)
DATA = {"batch": 10, "retries": 3, "backoff_s": 4, "daily_period": "3y", "hourly_period": "60d", "check_period": "1d"}
STATE_PATH = os.environ.get("PULSEBOT_STATE", "state/state.json")
STATS_PATH = os.path.join(os.path.dirname(__file__), "stats.json")

def load_stats():
    try:
        return json.load(open(STATS_PATH))
    except Exception:
        return {}
