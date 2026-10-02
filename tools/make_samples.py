"""Builds samples/ from the dry-run replay (samples/replay/all_messages.jsonl) plus two engine runs with simulated
conditions: mocked news items (message 13) and a simulated data failure (message 15). No network, nothing sent."""
import sys, os, json, datetime as dt, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pulsebot.market_time import ET
from pulsebot.data import OfflineData
from pulsebot.telegram import Telegram
from pulsebot.engine import Engine
from pulsebot import state as S

OUT = "samples"; REP = "samples/replay/all_messages.jsonl"
msgs = [json.loads(l) for l in open(REP, encoding="utf-8")]

def first(kind, cond=lambda m: True):
    for m in msgs:
        if m["kind"] == kind and cond(m):
            return m
    return None

def run_once(when, tag, data_cls=OfflineData, toggles=None, news_getter=None, commands=None, pre_runs=()):
    d = f"/tmp/pulse_{tag}"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    st = S.new_state(); st["toggles"].update(toggles or {}); S.save(st, f"{d}/state.json")
    got = []
    for w in list(pre_runs) + [when]:
        fx = None
        if commands and w == when:
            fx = f"{d}/upd.json"
            json.dump([{"update_id": i + 1, "message": {"chat": {"id": 12345}, "text": c}} for i, c in enumerate(commands)], open(fx, "w", encoding="utf-8"), ensure_ascii=False)
        tg = Telegram(token=None, chat_id=12345, live=False, updates_fixture=fx)
        Engine(data_cls("data_cache", w), tg, w, state_path=f"{d}/state.json", news_getter=news_getter or (lambda s: []),
               heartbeat_path=f"{d}/hb.txt").run()
        got += [{"kind": k, "text": str(t), "html": type(t).__name__ == "Html", "date": w.date().isoformat(), "time": w.strftime("%H:%M")} for k, t in tg.sent]
    return got

# --- 13: news with MOCKED items (real news is never fetched in the dry-run)
def fake_news(sym):
    if sym != "NVDA":
        return []
    return [{"id": "demo-1", "content": {"title": "Nvidia shares move as chipmakers react to new export rules (عنوان تجريبي)",
             "canonicalUrl": {"url": "https://example.com/demo-news-1"}, "provider": {"displayName": "Demo Wire"}, "pubDate": "2026-10-01T15:05:00Z"}}]
when = dt.datetime(2026, 10, 1, 11, 10, tzinfo=ET)
PRE = [dt.datetime(2026, 10, 1, 9, 0, tzinfo=ET) + dt.timedelta(minutes=10 * i) for i in range(13)]   # 09:00 .. 11:00
news = [m for m in run_once(when, "news", toggles={"news": True}, news_getter=fake_news, pre_runs=PRE) if m["kind"] == "news"]

# --- 15: simulated data failure (3 symbols missing on 1H, then everything missing)
class PartialFail(OfflineData):
    def fetch(self, symbols, interval, period=None):
        out = super().fetch(symbols, interval, period)
        for s in ("TSLA", "AMD", "SPCX"):
            if interval == "60m": out.pop(s, None); self.failed.setdefault(interval, []).append(s)
        return out
class AllFail(OfflineData):
    def fetch(self, symbols, interval, period=None):
        self.failed[interval] = list(symbols); return {}
tech_part = run_once(when, "tech1", data_cls=PartialFail, commands=["/الحالة"], pre_runs=PRE)
tech_all = run_once(when, "tech2", data_cls=AllFail)
# --- /الملخص SYMBOL for a notable symbol (META, big-move day) so the plan / note lines are visible
noon = dt.datetime(2026, 10, 1, 12, 0, tzinfo=ET)
PRE2 = [dt.datetime(2026, 10, 1, 9, 0, tzinfo=ET) + dt.timedelta(minutes=10 * i) for i in range(18)]   # 09:00 .. 11:50
detail_meta = [m for m in run_once(noon, "detail", commands=["/الملخص META"], pre_runs=PRE2) if m["kind"] == "cmd_summary" and m["time"] == "12:00"]
# --- constructed (formatter only): hour-1 board when no symbol is notable (did not happen in the 8 replayed days)
from pulsebot import messages as M
no_notable = [{"kind": "notes_board", "date": "مُنشأ", "time": "10:30",
               "html": True, "text": str(M.notes_board({"k": 1, "time": dt.datetime(2026, 10, 1, 10, 30, tzinfo=ET), "items": [], "n_other": 19, "stats": {}})[0])}]

def ev_with(word, prefer_multi=True):
    c = [m for m in msgs if m["kind"] == "events" and word in m["text"]]
    if prefer_multi:
        c.sort(key=lambda m: (-min(m["text"].count("━\n✅") + m["text"].count("━\n⛔") + m["text"].count("━\n↩️"), 4), m["date"], m["time"]))
    return c[0] if c else None

pick = {
    "01_morning": [first("morning")],
    "02_hourly_summary_board": [first("summary")],
    "02b_summary_SYMBOL_reply": detail_meta[:1] + [first("cmd_summary", lambda m: m["text"].startswith("📊 <b>ملخص NVDA</b>")),
                                 first("cmd_summary", lambda m: "ملخص سريع" in m["text"].split("\n")[0])],
    "03_trend_change": [first("trend_change", lambda m: m["text"].count("━\n🟢") + m["text"].count("━\n🔴") >= 2) or first("trend_change")],
    "04_big_move": [first("big_move")],
    "05_07_stop_notes_targets_hour1": [first("notes_board", lambda m: "بعد الساعة الأولى" in m["text"] and "السبب:" in m["text"])],
    "05_stop_notes_hour2": [first("notes_board", lambda m: "بعد الساعة الثانية" in m["text"] and "السبب:" in m["text"])],
    "05_no_notable_example": [x for x in [first("notes_board", lambda m: "لا يوجد سهم بارز" in m["text"])] if x] or no_notable,
    "06_stop_cancel_in_batch": [ev_with("↩️")],
    "08_target_T1_in_batch": [ev_with("تحقق T1")],
    "09_target_T2_in_batch": [ev_with("تحقق T2")],
    "10_target_T3_in_batch": [ev_with("تحقق T3")],
    "11_stop_hit_in_batch": [ev_with("⛔")],
    "12_plan_expired": [first("plan_expired")],
    "13_news": news[:1],
    "14_eod_summary": [first("eod", lambda m: m["date"] == "2026-10-01")],
    "15_tech_problem": [m for m in tech_part if m["kind"] == "tech"][:1] + [m for m in tech_all if m["kind"] == "tech"][:1],
    "status": [first("cmd_status")] + [m for m in tech_part if m["kind"] == "cmd_status"][:1],
    "commands_other": [first(k) for k in ("cmd_help", "cmd_features", "cmd_toggle", "cmd_symbols", "cmd_news", "cmd_alerts", "cmd_stops", "cmd_unknown")],
}
# messages per day (automatic messages only; command replies excluded because they depend on what you type)
import collections
per_day = collections.Counter(m["date"] for m in msgs if not m["kind"].startswith("cmd_"))
kinds_day = collections.defaultdict(collections.Counter)
for m in msgs:
    if not m["kind"].startswith("cmd_"): kinds_day[m["date"]][m["kind"]] += 1
with open(f"{OUT}/messages_per_day.txt", "w", encoding="utf-8") as f:
    for d in sorted(per_day):
        f.write(f"{d}: {per_day[d]}  {dict(kinds_day[d])}\n")
    v = list(per_day.values())
    f.write(f"min {min(v)}  avg {sum(v) / len(v):.1f}  max {max(v)}  (days: {len(v)})\n")
print(open(f"{OUT}/messages_per_day.txt", encoding="utf-8").read())
NOTE = {"05_no_notable_example": "⚠️ مثال مُنشأ بالدالة نفسها (لم يحصل يوم بدون سهم بارز في الأيام الثمانية).",
        "13_news": "⚠️ عيّنة بأخبار وهمية (مصدر أخبار مُحاكى، لا اتصال بالإنترنت) — المنطق والتنسيق حقيقيان.",
        "15_tech_problem": "⚠️ عيّنة بفشل بيانات مُحاكى (yfinance فقط، بدون مصدر بديل) (3 أسهم بدون بيانات 1H، ثم كل الأسهم) — المنطق والتنسيق حقيقيان.",
        "status": "الأولى من التشغيل التجريبي العادي، الثانية بعد فشل البيانات المُحاكى."}
md = ["# PulseBot — عيّنات الرسائل (تشغيل تجريبي، لم يُرسل شيء)", "",
      "النصوص كما تُرسل بـ parse_mode=HTML: ما بين <b>…</b> يظهر عريضاً في تيليجرام، و&amp; يظهر &.", "",
      "المصدر: إعادة تشغيل المحرك الحقيقي كل 10 دقائق على بيانات مخزنة لـ 8 أيام تداول (2026-09-22 → 2026-10-01).", ""]
for name, items in pick.items():
    items = [x for x in items if x]
    with open(f"{OUT}/{name}.txt", "w", encoding="utf-8") as f:
        if name in NOTE: f.write(NOTE[name] + "\n\n")
        for x in items:
            f.write(f"--- [{x['kind']}] {x['date']} {x['time']} ET ---\n{x['text']}\n\n")
    md += [f"## {name}", ""] + ([NOTE[name], ""] if name in NOTE else [])
    for x in items:
        md += [f"`{x['kind']}` — {x['date']} {x['time']} ET", "```", x["text"], "```", ""]
    print(name, len(items))
open(f"{OUT}/ALL_SAMPLES.md", "w", encoding="utf-8").write("\n".join(md))

# --- review set for the one-time Telegram send (NOT sent here; tools/send_samples.py does it when asked)
def same_slot(m):     # all parts of a split message (same kind, date, time)
    if not m: return []
    parts = [x for x in msgs if x["kind"] == m["kind"] and x["date"] == m["date"] and x["time"] == m["time"]]
    return parts or [m]
P = lambda name: [x for x in pick[name] if x]
ev_main = first("events", lambda m: m["date"] == "2026-09-23" and m["time"] == "13:10")
order = [("morning", P("01_morning")[:1]), ("hourly_board", P("02_hourly_summary_board")[:1]),
         ("summary_symbol_reply", detail_meta[:1]), ("trend_change", P("03_trend_change")[:1]), ("big_move", P("04_big_move")[:1]),
         ("hour1_stop_targets", same_slot(first("notes_board", lambda m: "بعد الساعة الأولى" in m["text"] and "السبب:" in m["text"]))),
         ("hour2_stop_notes", same_slot(first("notes_board", lambda m: "بعد الساعة الثانية" in m["text"] and "السبب:" in m["text"]))),
         ("no_notable_example", P("05_no_notable_example")[:1]),
         ("events_T1_T3_stop_0923_1310", same_slot(ev_main)),
         ("events_stop_cancel", P("06_stop_cancel_in_batch")[:1]), ("events_T2", P("09_target_T2_in_batch")[:1]),
         ("events_T3", P("10_target_T3_in_batch")[:1]), ("events_stop_hit", P("11_stop_hit_in_batch")[:1]),
         ("plan_expired", P("12_plan_expired")[:1]), ("news_mock", news[:1]),
         ("eod", [first("eod", lambda m: m["date"] == "2026-10-01")]), ("tech_problem_simulated", P("15_tech_problem")[:1]),
         ("status", P("status")[:1]), ("help", [first("cmd_help")])]
review = [{"label": "header", "html": False, "text": "🧪 نماذج معدّلة (ترتيب جديد) — بيانات قديمة تجريبية"}]
seen = {}
for lab, ms in order:
    for i, m in enumerate(x for x in ms if x):
        key = m["text"]
        if key in seen:      # same message already in the set (e.g. one batch holds T1 + T3 + stop)
            print(f"skip {lab}: same message as {seen[key]}"); continue
        seen[key] = lab
        review.append({"label": lab if len(ms) == 1 else f"{lab}_{i + 1}", "html": bool(m.get("html", "<b>" in m["text"])),
                       "text": m["text"], "src": f"{m['date']} {m['time']}"})
json.dump(review, open(f"{OUT}/telegram_review_set.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("review set:", len(review), [(r["label"], r.get("src")) for r in review])
