"""Persistent JSON state (dedupe keys, open notes/plans, counters, toggles, command offset)."""
import json, os, datetime as dt
from .config import DEFAULT_TOGGLES

def new_state():
    return {"version": 1, "day": None, "last_run": None, "sent": {}, "last_bar": {}, "last_trend": {}, "notes": {}, "plans": [],
            "counts": {}, "alerts": [], "toggles": dict(DEFAULT_TOGGLES), "update_offset": 0, "news_seen": [], "pending": [],
            "errors": {}, "last_error": None, "last_summary": {}, "heartbeat_week": None, "data_ok": 0, "source": "",
            "trend_today": {}, "detail": {}}

def zero_counts():
    return {k: 0 for k in ("big_move", "trend_change", "trend_up", "trend_down", "notes", "notes_held", "notes_cancelled", "notes_broken",
                           "plans", "T1", "T2", "T3", "stop", "stop_after_t1", "expired", "messages")}

def load(path):
    if os.path.exists(path):
        try:
            st = json.load(open(path, encoding="utf-8"))
            base = new_state(); base.update(st)
            for k, v in DEFAULT_TOGGLES.items():
                base["toggles"].setdefault(k, v)
            return base
        except Exception:
            pass
    return new_state()

def save(st, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)

def roll_day(st, today):
    """new trading day: clear intraday objects, keep toggles/offset/news_seen; prune dedupe keys older than 7 days."""
    if st["day"] == today.isoformat():
        return False
    st["day"] = today.isoformat(); st["notes"] = {}; st["plans"] = []; st["alerts"] = []; st["counts"] = zero_counts(); st["trend_today"] = {}
    cutoff = (today - dt.timedelta(days=7)).isoformat()
    st["sent"] = {k: v for k, v in st["sent"].items() if v >= cutoff}
    st["news_seen"] = st["news_seen"][-500:]
    return True

def once(st, key, today):
    """dedupe: True the first time a key is seen."""
    if key in st["sent"]:
        return False
    st["sent"][key] = today.isoformat(); return True
