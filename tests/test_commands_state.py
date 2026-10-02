import datetime as dt
from pulsebot import commands as C, state as S

def test_arabic_and_english_aliases():
    assert C.parse("/الأخبار تشغيل") == ("news", "on")
    assert C.parse("/الاخبار إيقاف") == ("news", "off")
    assert C.parse("/news on") == ("news", "on") and C.parse("/NEWS OFF") == ("news", "off")
    assert C.parse("/التنبيهات")[0] == "alerts" and C.parse("/alerts")[0] == "alerts"
    assert C.parse("/الوقف")[0] == "stops" and C.parse("/الملخص")[0] == "summary"
    assert C.parse("/الأسهم")[0] == "symbols" and C.parse("/الاسهم")[0] == "symbols"
    assert C.parse("/الحالة")[0] == "status" and C.parse("/status@PulseBot")[0] == "status"
    assert C.parse("/مساعدة")[0] == "help" and C.parse("/start")[0] == "help"
    assert C.parse("/xyz")[0] == "unknown" and C.parse("hello") == (None, None) and C.parse("") == (None, None)

def test_state_dedupe_and_roll(tmp_path):
    st = S.new_state(); d = dt.date(2026, 9, 30)
    assert S.roll_day(st, d) and not S.roll_day(st, d)
    assert S.once(st, "k1", d) and not S.once(st, "k1", d)
    st["plans"] = [{"x": 1}]; st["sent"]["old"] = "2026-09-01"
    S.save(st, str(tmp_path / "s.json")); st2 = S.load(str(tmp_path / "s.json"))
    assert st2["plans"] == [{"x": 1}] and "k1" in st2["sent"]
    assert S.roll_day(st2, dt.date(2026, 10, 1))
    assert st2["plans"] == [] and "old" not in st2["sent"] and "k1" in st2["sent"]
    assert st2["toggles"]["news"] is False                    # news OFF by default

def test_state_load_corrupt_file(tmp_path):
    p = tmp_path / "bad.json"; p.write_text("{not json")
    assert S.load(str(p))["version"] == 1

def test_toggle_command_parse():
    assert C.parse("/تبديل big_move إيقاف") == ("toggle", ("big_move", "off"))
    assert C.parse("/toggle hourly_summary on") == ("toggle", ("hourly_summary", "on"))
    assert C.parse("/تبديل") == ("toggle", (None, None))
    assert C.parse("/الميزات")[0] == "features" and C.parse("/features")[0] == "features"

def test_summary_symbol_argument():
    assert C.parse("/الملخص nvda") == ("summary", "NVDA") and C.parse("/summary ^gspc") == ("summary", "^GSPC")
    assert C.parse("/الملخص") == ("summary", None)
