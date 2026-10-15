import json, datetime as dt
import pytest
import pandas as pd
from helpers import make_cache
from pulsebot.market_time import ET
from pulsebot.data import OfflineData
from pulsebot.telegram import Telegram
from pulsebot.engine import Engine
from pulsebot import state as S

DAY = dt.date(2026, 9, 30)
SYMS = ["AAA", "BBB"]

@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    d = tmp_path_factory.mktemp("cache"); make_cache(str(d), SYMS, DAY); return str(d)

def no_net(req): raise AssertionError("network used")

def run(cache, tmp, t, fixture=None, data=None):
    tg = Telegram(None, 12345, live=False, opener=no_net, updates_fixture=fixture)
    Engine(data or OfflineData(cache, t), tg, t, state_path=str(tmp / "state.json"), symbols=SYMS,
           heartbeat_path=str(tmp / "hb.txt")).run()
    return tg.sent

def at(h, m, day=DAY): return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=ET)

def full_day(cache, tmp, **kw):
    out = []; t = at(9, 0)
    while t <= at(16, 30):
        out += [(t, k, x) for k, x in run(cache, tmp, t, **kw)]; t += dt.timedelta(minutes=10)
    return out

def test_full_day_consolidated_defaults(cache, tmp_path):
    msgs = full_day(cache, tmp_path)
    kinds = [k for _, k, _ in msgs]
    assert kinds.count("morning") == 1 and kinds.count("eod") == 1
    assert kinds.count("summary") == 7                               # ONE board per closed 1H bar (10:30 .. 15:30, 16:00)
    boards = [x for _, k, x in msgs if k == "summary"]
    assert all("AAA" in b and "BBB" in b for b in boards)
    assert kinds.count("notes_board") == 2                           # one after hour 1, one after hour 2
    assert not any(k in ("stop_note", "targets", "target_T1", "stop_hit", "stop_cancel") for k in kinds)   # no per-item messages
    per_run = {}
    for t, k, _ in msgs: per_run.setdefault(t, []).append(k)
    assert all(v.count("events") <= 1 for v in per_run.values())     # hits/stops of one run = one message
    st = json.load(open(tmp_path / "state.json", encoding="utf-8"))
    assert all(p["status"] != "open" for p in st["plans"])
    c = st["counts"]
    assert c["plans"] == c["stop"] + c["expired"] + sum(1 for p in st["plans"] if p["status"] in ("done", "ended"))
    assert set(st["detail"]) == set(SYMS) and (tmp_path / "hb.txt").exists()
    again = full_day(cache, tmp_path)                                # dedupe through state: nothing is re-sent
    assert [k for _, k, _ in again if k in ("morning", "summary", "eod", "notes_board", "events")] == []

def test_toggles_off_restore_one_message_per_item(cache, tmp_path):
    st = S.new_state()
    st["toggles"].update({"summary_consolidated": False, "notable_only": False, "notes_consolidated": False, "batch_events": False})
    S.save(st, str(tmp_path / "state.json"))
    kinds = [k for _, k, _ in full_day(cache, tmp_path)]
    assert kinds.count("summary") == 7 * len(SYMS)
    assert kinds.count("stop_note") == 2 * len(SYMS) and kinds.count("targets") == len(SYMS)
    assert "notes_board" not in kinds and "events" not in kinds

def test_notable_formula(cache, tmp_path):
    from pulsebot import config as C
    tg = Telegram(None, 12345, live=False, opener=no_net)
    e = Engine(OfflineData(cache, at(10, 40)), tg, at(10, 40), state_path=str(tmp_path / "s.json"), symbols=SYMS)
    e.st = S.new_state(); e.big_syms = set(); bar = pd.Timestamp(at(9, 30))
    assert e.notable_reasons("AAA", bar) == []
    e.big_syms = {"AAA"}; assert e.notable_reasons("AAA", bar) == ["⚡ تقلب عالٍ اليوم"]
    e.big_syms = set(); e.st["trend_today"]["AAA"] = at(10, 30).isoformat()
    assert e.notable_reasons("AAA", bar) == []                       # trend change AFTER this bar does not count
    assert e.notable_reasons("AAA", pd.Timestamp(at(10, 30))) == ["🔀 تغيّر اتجاه الساعة اليوم"]
    e.st["trend_today"] = {}; e.st["plans"] = [{"sym": "AAA", "status": "open"}, {"sym": "BBB", "status": "stopped"}]
    assert e.notable_reasons("AAA", bar) == ["📋 خطة مفتوحة"] and e.notable_reasons("BBB", bar) == []
    assert C.NOTABLE_RULE == "big_move_active OR trend_change_today OR open_plan"

def test_notable_only_filters_hour1_board(cache, tmp_path):
    msgs = full_day(cache, tmp_path)
    st = json.load(open(tmp_path / "state.json", encoding="utf-8"))
    big = [x for _, k, x in msgs if k == "big_move"]
    board1 = [x for _, k, x in msgs if k == "notes_board"][0]
    planned = {p["sym"] for p in st["plans"]}
    for s in SYMS:
        if s in planned:
            assert f"<b>{s}</b>" in board1 and "السبب:" in board1
    if not big and not st["trend_today"]:
        assert planned == set() and "لا يوجد سهم بارز" in board1

def test_summary_symbol_detail_reply(cache, tmp_path):
    full_day(cache, tmp_path)
    fx = tmp_path / "u.json"
    fx.write_text(json.dumps([{"update_id": 1, "message": {"chat": {"id": 12345}, "text": "/الملخص aaa"}},
                              {"update_id": 2, "message": {"chat": {"id": 12345}, "text": "/summary ZZZ"}},
                              {"update_id": 3, "message": {"chat": {"id": 12345}, "text": "/الملخص"}}], ensure_ascii=False), encoding="utf-8")
    sent = run(cache, tmp_path, at(16, 40), fixture=str(fx))
    rep = [x for k, x in sent if k == "cmd_summary"]
    assert rep[0].startswith("<b>📊 AAA · تحليل مختصر</b>") and "15:30-16:00 يوم 2026-09-30" in rep[0]
    assert "الشهري" in rep[0] and "ليست لحظية" in rep[0]
    assert len(rep[0]) < 1600 and "متوسط 20" not in rep[0]
    assert "لا تتوفر بيانات محفوظة" in rep[1] and rep[2].startswith("<b>📊 الملخص السريع")

def test_events_batch_one_message_per_run(cache, tmp_path):
    from pulsebot import messages as M
    ev = [{"type": "target", "p": {"sym": "AAA", "dir": "up", "target": "T1", "price": 101.0, "entry": 100.0, "t1": 101.0, "remaining": [("T2", 102.0)], "stop": 100.0}},
          {"type": "stop", "p": {"sym": "BBB", "dir": "down", "stop": 205.0, "entry": 200.0, "stop_kind": "orig", "hit": [], "conflict": True}},
          {"type": "cancel", "p": {"sym": "AAA", "side": "up", "open": 99.0, "price": 98.5}}]
    out = M.events_batch(at(10, 40), ev)
    assert len(out) == 1 and "🔢 3 أحداث: 1 هدف · 1 وقف · 1 إلغاء ملاحظة" in out[0]
    assert "✅ <b>AAA</b> 🟢 صعود\nتحقق T1: $101.00\nالربح للصعود من الدخول $100.00: +$1.00\n💡 انقل الوقف إلى الدخول $100.00" in out[0]
    assert "⛔ <b>BBB</b> 🔴 هبوط\nضُرب الوقف الأصلي: $205.00\nالربح للهبوط من الدخول $200.00: −$5.00" in out[0] and "احتياطاً" in out[0]
    assert out[0].count(M.sep()) == 4                 # 3 blocks + footer

def test_down_scenario_profit_is_positive_when_price_falls():
    from pulsebot import messages as M
    ev = [{"type": "target", "p": {"sym": "AMZN", "dir": "down", "target": "T1", "price": 248.0, "entry": 249.18, "t1": 248.0,
                                   "remaining": [("T2", 244.30), ("T3", 247.36)], "stop": 249.18}}]
    out = M.events_batch(at(13, 10), ev)[0]
    assert "✅ <b>AMZN</b> 🔴 هبوط\nتحقق T1: $248.00\nالربح للهبوط من الدخول $249.18: +$1.18\n💡 انقل الوقف إلى الدخول $249.18\nالباقي: T2 $244.30 · T3 $247.36" in out

def test_separator_len_configurable(monkeypatch):
    from pulsebot import messages as M, config as C
    for n in (20, 24, 28):
        monkeypatch.setattr(C, "SEPARATOR_LEN", n)
        assert M.sep() == "━" * n
        assert "\n" + "━" * n + "\n" in M.pack("h", ["a", "b"], "f")[0]
    monkeypatch.undo(); assert C.SEPARATOR_LEN == 24

def test_dynamic_text_is_html_escaped():
    from pulsebot import messages as M
    out = M.detail_missing("<x&y>", ["A&B"])
    assert "&lt;x&amp;y&gt;" in out and "A&amp;B" in out and "<x" not in out

def test_every_rendered_message_is_valid_telegram_html(cache, tmp_path):
    from html.parser import HTMLParser
    from pulsebot.telegram import tg_len
    class P(HTMLParser):
        def __init__(s): super().__init__(); s.stack = []; s.bad = []
        def handle_starttag(s, tag, a): s.stack.append(tag); s.bad += [tag] if tag not in ("b", "i", "code") else []
        def handle_endtag(s, tag): assert s.stack and s.stack.pop() == tag
    msgs = full_day(cache, tmp_path)
    assert msgs
    for _, k, x in msgs:
        if getattr(x, "is_html", False) or type(x).__name__ == "Html":
            p = P(); p.feed(x); p.close()
            assert not p.stack and not p.bad, k
            assert "&" not in x.replace("&lt;", "").replace("&gt;", "").replace("&amp;", "").replace("&quot;", ""), k
        assert tg_len(x) <= 4096

def test_pack_splits_only_between_blocks_under_telegram_limit():
    from pulsebot import messages as M
    from pulsebot.telegram import tg_len
    blocks = [f"• SYM{i} 🟢 " + "س" * 300 for i in range(40)]
    parts = M.pack("📊 رأس", blocks, "تذييل")
    assert len(parts) > 1 and all(tg_len(p) <= 3900 for p in parts) and parts[-1].endswith("تذييل")
    assert sum(p.count("• SYM") for p in parts) == 40 and "(جزء 1 من" in parts[0]
    S = M.sep()
    assert M.pack("رأس", ["a", "b"], "ذيل") == [f"رأس\n{S}\na\n{S}\nb\n{S}\nذيل"]

def test_repeated_run_same_time_no_duplicate(cache, tmp_path):
    a = run(cache, tmp_path, at(10, 40)); b = run(cache, tmp_path, at(10, 40))
    assert any(k == "summary" for k, _ in a) and not any(k == "summary" for k, _ in b)

def test_commands_work_and_news_command_is_removed(cache, tmp_path):
    fx = tmp_path / "u.json"
    fx.write_text(json.dumps([
        {"update_id": 5, "message": {"chat": {"id": 12345}, "text": "/الحالة"}},
        {"update_id": 6, "message": {"chat": {"id": 999}, "text": "/الحالة"}},
        {"update_id": 7, "message": {"chat": {"id": 12345}, "text": "/الأخبار تشغيل"}},
    ], ensure_ascii=False), encoding="utf-8")
    sent = run(cache, tmp_path, at(9, 10), fixture=str(fx))
    st = S.load(str(tmp_path / "state.json"))
    assert st["update_offset"] == 8 and "news" not in st["toggles"]
    assert [k for k, _ in sent if k.startswith("cmd_")] == ["cmd_status", "cmd_unknown"]
    status = [x for k, x in sent if k == "cmd_status"][0]
    assert "<b>🩺 حالة البوت</b>" in status and "الأخبار" not in status
    unknown = [x for k, x in sent if k == "cmd_unknown"][0]
    assert "غير معروف" in unknown


def test_data_failure_sends_one_arabic_notice(cache, tmp_path):
    class Fail(OfflineData):
        def fetch(self, symbols, interval, period=None):
            self.failed[interval] = list(symbols); return {}
    a = run(cache, tmp_path, at(10, 40), data=Fail(cache, at(10, 40)))
    b = run(cache, tmp_path, at(10, 50), data=Fail(cache, at(10, 50)))
    tech = [x for k, x in a if k == "tech"]
    assert len(tech) == 1 and "تعذر" in tech[0] and not any(k == "tech" for k, _ in b)   # once per hour

def test_holiday_and_night_do_nothing(cache, tmp_path):
    assert run(cache, tmp_path, dt.datetime(2026, 11, 26, 11, 0, tzinfo=ET)) == []
    assert run(cache, tmp_path, at(8, 30)) == []

def test_rate_cap_moves_overflow_to_pending(cache, tmp_path, monkeypatch):
    from pulsebot import config as C
    monkeypatch.setitem(C.TELEGRAM, "max_per_run", 2)
    sent = run(cache, tmp_path, at(10, 40))
    st = S.load(str(tmp_path / "state.json"))
    assert len(sent) == 2 and len(st["pending"]) > 0

def test_toggle_any_feature_by_command(cache, tmp_path):
    fx = tmp_path / "u.json"
    fx.write_text(json.dumps([{"update_id": 1, "message": {"chat": {"id": 12345}, "text": "/تبديل big_move إيقاف"}},
                              {"update_id": 2, "message": {"chat": {"id": 12345}, "text": "/تبديل nothing on"}},
                              {"update_id": 3, "message": {"chat": {"id": 12345}, "text": "/toggle commands off"}},
                              {"update_id": 4, "message": {"chat": {"id": 12345}, "text": "/الميزات"}}], ensure_ascii=False), encoding="utf-8")
    sent = run(cache, tmp_path, at(9, 0), fixture=str(fx))
    st = S.load(str(tmp_path / "state.json"))
    assert st["toggles"]["big_move"] is False and st["toggles"]["commands"] is True
    assert not any(k == "big_move" for k, _ in sent)
    feats = [x for k, x in sent if k == "cmd_features"][0]
    assert "big_move" in feats and "⛔" in feats

def test_help_and_command_cards_are_html_without_news():
    from pulsebot import messages as M
    from pulsebot.telegram import Html
    h = M.help_text()
    assert isinstance(h, Html) and "<b>/الملخص AAPL</b>" in h and h.count(M.CARD_SEP) >= 9
    assert "/news" not in h and "الأخبار" not in h
    assert " — أو " not in h


def test_manual_preview_sends_compact_saved_symbol_analysis(cache, tmp_path):
    full_day(cache, tmp_path)
    tg = Telegram(None, 12345, live=False, opener=no_net)
    t = at(20, 0)
    Engine(OfflineData(cache, t), tg, t, state_path=str(tmp_path / "state.json"), symbols=SYMS,
           force_test=True, preview_symbol="AAA").run()
    assert len(tg.sent) == 1 and tg.sent[0][0] == "preview"
    assert "تحليل مختصر" in tg.sent[0][1] and "متوسط 20" not in tg.sent[0][1]


def test_force_test_sends_ping_even_when_closed(cache, tmp_path):
    tg = Telegram(None, 12345, live=False, opener=no_net)
    t = at(20, 0)                                   # after the session: no regular work
    Engine(OfflineData(cache, t), tg, t, state_path=str(tmp_path / "s.json"), symbols=SYMS, force_test=True).run()
    kinds = [k for k, _ in tg.sent]
    assert kinds == ["test"] and "رسالة اختبار" in tg.sent[0][1] and "حالة البوت" in tg.sent[0][1]

def test_half_hour_status_once_per_slot(cache, tmp_path):
    first = run(cache, tmp_path, at(10, 7))
    same_slot = run(cache, tmp_path, at(10, 25))
    next_slot = run(cache, tmp_path, at(10, 37))
    assert sum(k == "half_hour_status" for k, _ in first) == 1
    assert not any(k == "half_hour_status" for k, _ in same_slot)
    assert sum(k == "half_hour_status" for k, _ in next_slot) == 1
