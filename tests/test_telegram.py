import io, json, urllib.error
from pulsebot.telegram import Telegram, split_text

class Clock:
    def __init__(self): self.t = 0.0; self.sleeps = []
    def now(self): return self.t
    def sleep(self, s): self.sleeps.append(s); self.t += s

def test_dry_run_never_calls_network(tmp_path):
    def boom(req): raise AssertionError("network used in dry-run")
    tg = Telegram("TOKEN", "1", live=False, opener=boom, outbox_path=str(tmp_path / "o.jsonl"))
    tg.send("مرحبا", "x"); assert tg.get_updates(0) == []
    assert json.loads((tmp_path / "o.jsonl").read_text(encoding="utf-8"))["text"] == "مرحبا"
    assert not Telegram("TOKEN", None, live=True).live and not Telegram(None, "1", live=True).live

def test_rate_limit_spacing():
    c = Clock(); calls = []
    tg = Telegram("T", "1", live=True, sleep=c.sleep, clock=c.now, opener=lambda r: (calls.append(1), b'{"ok": true}')[1])
    for i in range(3): tg.send(f"m{i}")
    assert len(calls) == 3 and len(c.sleeps) == 2 and all(abs(s - 1.2) < 1e-9 for s in c.sleeps)

def test_429_retry_after_via_http_error():
    c = Clock(); n = {"i": 0}
    def opener(req):
        n["i"] += 1
        if n["i"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b'{"ok":false,"error_code":429,"parameters":{"retry_after":7}}'))
        return b'{"ok": true}'
    tg = Telegram("T", "1", live=True, sleep=c.sleep, clock=c.now, opener=opener)
    tg.send("x")
    assert n["i"] == 2 and 7 in c.sleeps

def test_split_long_text():
    text = "\n".join(["سطر " + str(i) * 50 for i in range(300)])
    parts = split_text(text, 3900)
    assert len(parts) > 1 and all(len(p) <= 3900 for p in parts) and "\n".join(parts) == text

def test_split_counts_utf16_like_telegram():
    from pulsebot.telegram import tg_len
    assert tg_len("🟢") == 2 and tg_len("س") == 1
    text = "\n".join(["🟢🔴" * 30 for _ in range(100)])          # 120 UTF-16 units per line, 60 python chars
    parts = split_text(text, 3900)
    assert all(tg_len(p) <= 3900 for p in parts) and "\n".join(parts) == text

def test_html_parse_mode_and_plain_fallback_on_400():
    import urllib.parse
    from pulsebot.telegram import Html
    c = Clock(); bodies = []
    def opener(req):
        q = dict(urllib.parse.parse_qsl(req.data.decode())); bodies.append(q)
        if len(bodies) == 1:
            raise urllib.error.HTTPError(req.full_url, 400, "Bad", {}, io.BytesIO(b'{"ok":false,"error_code":400,"description":"Bad Request: can\'t parse entities"}'))
        return b'{"ok": true}'
    tg = Telegram("T", "1", live=True, sleep=c.sleep, clock=c.now, opener=opener)
    assert tg.send(Html("<b>AMZN</b> &amp; x"))
    assert bodies[0]["parse_mode"] == "HTML" and bodies[0]["text"] == "<b>AMZN</b> &amp; x"
    assert "parse_mode" not in bodies[1] and bodies[1]["text"] == "AMZN & x" and tg.ok == 1 and tg.failed == 0

def test_plain_text_is_sent_without_parse_mode():
    import urllib.parse
    c = Clock(); bodies = []
    tg = Telegram("T", "1", live=True, sleep=c.sleep, clock=c.now,
                  opener=lambda r: (bodies.append(dict(urllib.parse.parse_qsl(r.data.decode()))), b'{"ok": true}')[1])
    tg.send("a < b"); assert "parse_mode" not in bodies[0]
