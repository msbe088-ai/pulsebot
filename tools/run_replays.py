"""Replays the last N cached trading days (state carried across days) and stores every dry-run message."""
import sys, json, os, datetime as dt, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from pulsebot.replay import replay_day
from pulsebot.market_time import is_trading_day
days = sorted({d.date() for d in pd.read_pickle("data_cache/SPY_5m.pkl").index})
n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
days = [d for d in days if is_trading_day(d)][-n:]
out = "samples/replay"; os.makedirs(out, exist_ok=True)
if os.path.exists(f"{out}/state.json"): os.remove(f"{out}/state.json")
cmds = [{"at": "11:00", "update_id": 1, "text": "/الحالة"}, {"at": "11:00", "update_id": 2, "text": "/مساعدة"},
        {"at": "11:10", "update_id": 3, "text": "/الأسهم"}, {"at": "11:10", "update_id": 4, "text": "/التنبيهات"},
        {"at": "12:00", "update_id": 5, "text": "/الوقف"}, {"at": "12:00", "update_id": 6, "text": "/الملخص NVDA"}, {"at": "12:00", "update_id": 12, "text": "/summary"},
        {"at": "12:10", "update_id": 7, "text": "/news on"}, {"at": "12:20", "update_id": 8, "text": "/الأخبار إيقاف"},
        {"at": "12:30", "update_id": 9, "text": "/foo"},
        {"at": "12:40", "update_id": 10, "text": "/الميزات"}, {"at": "12:50", "update_id": 11, "text": "/تبديل big_move تشغيل"}]
for i, c in enumerate(sorted(cmds, key=lambda c: c["at"])):   # Telegram update ids always increase with time
    c["update_id"] = i + 1
allm = []
for i, d in enumerate(days):
    c = [dict(x, update_id=x["update_id"] + 100 * i) for x in cmds] if i == len(days) - 1 else []
    log = replay_day(d, out_dir=out, commands=c, keep_state=True)
    for m in log: m["date"] = d.isoformat()
    allm += log
    print(d, len(log), dict(collections.Counter(m["kind"] for m in log)), flush=True)
with open(f"{out}/all_messages.jsonl", "w", encoding="utf-8") as f:
    for m in allm: f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("TOTAL", dict(collections.Counter(m["kind"] for m in allm)))
