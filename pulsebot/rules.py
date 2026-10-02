"""Explicit rules that turn data into message payloads. No buy/sell direction signals: plans are always given for BOTH
scenarios (up and down) and are reference levels only."""
from .config import P
from . import indicators as I

def prev_week_hl(daily_completed, today):
    """High/low of the last completed ISO week before `today`."""
    wk = today.isocalendar()[:2]
    d = daily_completed[[x.isocalendar()[:2] != wk for x in daily_completed.index]]
    if d.empty:
        return None, None
    last = d.index[-1].isocalendar()[:2]
    w = d[[x.isocalendar()[:2] == last for x in d.index]]
    return float(w["High"].max()), float(w["Low"].min())

def targets(entry, stop, direction, day_open, atr_d, pdh, pdl, pwh, pwl):
    """direction +1 (up scenario) or -1 (down scenario).
    min_dist = T_MIN_DIST_ATR * atr_d
    T1 = nearest of {next round number beyond entry, prior-day high (up) / low (down)} that is beyond entry + min_dist
    T2 = prior-week high (up) / low (down) if beyond T1 + min_dist, else the next round number beyond T1
    T3 = day_open + atr_d (up) / day_open - atr_d (down); None if the price is already beyond it
    For each target: dist = |T - entry| ($), mult = dist / |entry - stop| (multiple of the stop distance)."""
    md = P["T_MIN_DIST_ATR"] * atr_d
    s = direction
    beyond = lambda x, ref: x is not None and s * (x - ref) > md
    c1 = []
    r = I.next_round(entry, s)
    while not beyond(r, entry):
        r = I.next_round(r, s)
    c1.append((r, "round"))
    pd_ = pdh if s > 0 else pdl
    if beyond(pd_, entry):
        c1.append((pd_, "pdh" if s > 0 else "pdl"))
    t1, t1src = min(c1, key=lambda x: s * (x[0] - entry))
    pw = pwh if s > 0 else pwl
    if beyond(pw, t1):
        t2, t2src = pw, ("pwh" if s > 0 else "pwl")
    else:
        t2 = I.next_round(t1, s)
        while not beyond(t2, t1):
            t2 = I.next_round(t2, s)
        t2src = "round"
    t3 = day_open + s * atr_d
    t3src = "open_atr"
    if not s * (t3 - entry) > 0:
        t3 = None
    risk = abs(entry - stop)
    out = []
    for name, t, src in (("T1", t1, t1src), ("T2", t2, t2src), ("T3", t3, t3src)):
        if t is None:
            out.append({"name": name, "price": None, "src": src})
        else:
            dist = abs(t - entry)
            out.append({"name": name, "price": round(t, 2), "src": src, "dist": round(dist, 2), "mult": round(dist / risk, 2) if risk > 0 else None})
    return out

def stop_note(hour_bars_today, k):
    """Stop note after hour k (k=1 or 2) using today's CLOSED 1H bars.
    open = Open of bar 1; price = Close of bar k.
    price > open -> 'up' note: stop = min(Low of bars 1..k) (low so far); stats P(day low already in) from P['STOP_STATS'].
    price < open -> 'down' note: stop = max(High of bars 1..k) (high so far).
    price == open -> None."""
    if len(hour_bars_today) < k:
        return None
    b = hour_bars_today.iloc[:k]
    o = float(b["Open"].iloc[0]); px = float(b["Close"].iloc[-1])
    if px == o:
        return None
    side = "up" if px > o else "down"
    stop = float(b["Low"].min()) if side == "up" else float(b["High"].max())
    st, base = P["STOP_STATS"][side][k]
    return {"side": side, "k": k, "open": o, "price": px, "stop": stop, "low": float(b["Low"].min()), "high": float(b["High"].max()),
            "stat": st, "base": base, "time": b.index[-1]}

def check_window(plan, w_high, w_low):
    """Evaluate one check window (all bars since the last check) for a plan.
    Conservative: if the stop AND any untouched target were both touched in the same window -> stop.
    Returns list of events in order: ('stop', price) or ('T1', price) ... and updates plan['stop'] when trailing."""
    s = 1 if plan["dir"] == "up" else -1
    stop = plan["stop"]
    stop_hit = (w_low <= stop) if s > 0 else (w_high >= stop)
    pending = [t for t in plan["targets"] if t["price"] is not None and t["name"] not in plan["hit"]]
    t_hit = [t for t in pending if ((w_high >= t["price"]) if s > 0 else (w_low <= t["price"]))]
    if stop_hit:
        return [("stop", stop)]
    ev = []
    for t in sorted(t_hit, key=lambda t: s * t["price"]):
        ev.append((t["name"], t["price"]))
    return ev

def trailing_stop(plan, target_name):
    """after T1: stop -> entry; after T2: stop -> T1 price (only if it tightens the stop)."""
    s = 1 if plan["dir"] == "up" else -1
    new = None
    if target_name == "T1":
        new = plan["entry"]
    elif target_name == "T2":
        new = next(t["price"] for t in plan["targets"] if t["name"] == "T1")
    if new is not None and s * (new - plan["stop"]) > 0:
        return new
    return plan["stop"]
