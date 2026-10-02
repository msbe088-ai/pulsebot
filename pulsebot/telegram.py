"""Telegram Bot API via urllib. DRY-RUN by default: nothing is sent unless PULSEBOT_LIVE=1 and a token is present."""
import html as _html, json, logging, re, time, urllib.error, urllib.parse, urllib.request
from .config import TELEGRAM

log = logging.getLogger("pulsebot.telegram")

def tg_len(s):
    """length as Telegram counts it (UTF-16 code units; most emoji count 2)."""
    return len(s.encode("utf-16-le")) // 2

def split_text(text, n=None):
    """split on line boundaries so every part is <= n UTF-16 units (Telegram hard limit 4096)."""
    n = n or TELEGRAM["max_len"]
    parts, cur = [], ""
    for line in text.split("\n"):
        while tg_len(line) > n:                      # a single over-long line (never produced by messages.py)
            parts.append(line[: n // 2]); line = line[n // 2:]
        if cur and tg_len(cur) + tg_len(line) + 1 > n:
            parts.append(cur); cur = ""
        cur = (cur + "\n" + line) if cur else line
    if cur: parts.append(cur)
    return parts

class Html(str):
    """A message body already formatted for parse_mode=HTML (all dynamic text escaped by messages.py)."""

def strip_html(s):
    return _html.unescape(re.sub(r"</?(b|i|u|code|pre)>", "", s))

class Telegram:
    def __init__(self, token=None, chat_id=None, live=False, sleep=time.sleep, clock=time.monotonic, opener=None, outbox_path=None, updates_fixture=None):
        self.token, self.chat_id, self.live = token, str(chat_id) if chat_id else None, bool(live and token and chat_id)
        self.sleep, self.clock = sleep, clock
        self.opener = opener or (lambda req: urllib.request.urlopen(req, timeout=20).read())
        self.outbox_path = outbox_path; self.updates_fixture = updates_fixture
        self._last = None; self.sent = []      # list of (kind, text)
        self.sent_html = []; self.ok = 0; self.failed = 0
    def _api(self, method, params):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        data = urllib.parse.urlencode(params).encode()
        try:
            return json.loads(self.opener(urllib.request.Request(url, data=data)))
        except urllib.error.HTTPError as e:      # 429 / 400 arrive as HTTPError; the JSON body carries retry_after
            try:
                return json.loads(e.read())
            except Exception:
                return {"ok": False, "error_code": e.code}
    def _rate(self):
        if self._last is not None:
            wait = TELEGRAM["min_interval_s"] - (self.clock() - self._last)
            if wait > 0: self.sleep(wait)
        self._last = self.clock()
    def send(self, text, kind="msg", html=None):
        """Send one message (split on line boundaries if needed). html=None -> HTML iff text is an Html instance.
        Returns True if every part was accepted (dry-run: always True)."""
        html = isinstance(text, Html) if html is None else html
        all_ok = True
        for part in split_text(text):
            self.sent.append((kind, Html(part) if html else part)); self.sent_html.append(bool(html))
            if not self.live:
                if self.outbox_path:
                    with open(self.outbox_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"kind": kind, "html": bool(html), "text": part}, ensure_ascii=False) + "\n")
                continue
            self._rate()
            ok = False; body, mode = part, ("HTML" if html else None)
            for attempt in range(TELEGRAM["retries"]):
                try:
                    params = {"chat_id": self.chat_id, "text": body, "disable_web_page_preview": "true"}
                    if mode: params["parse_mode"] = mode
                    r = self._api("sendMessage", params)
                    if r.get("ok"):
                        log.info("sendMessage ok:true kind=%s message_id=%s html=%s", kind, (r.get("result") or {}).get("message_id"), mode == "HTML")
                        ok = True; break
                    log.warning("sendMessage ok:false kind=%s error_code=%s %s", kind, r.get("error_code"), r.get("description", ""))
                    ra = (r.get("parameters") or {}).get("retry_after")
                    desc = str(r.get("description", ""))
                    if ra:
                        self.sleep(min(float(ra), 30))
                    elif r.get("error_code") == 400 and mode and "parse" in desc.lower():   # HTML rejected: resend as plain text
                        log.warning("HTML rejected (%s), resending as plain text", desc); body, mode = strip_html(part), None
                    elif r.get("error_code") in (400, 401, 403):     # bad chat id / token: retrying will not help
                        log.error("telegram refused: %s", desc); break
                except Exception as e:
                    log.warning("send failed (attempt %d): %s", attempt + 1, e); self.sleep(2 * (attempt + 1))
            if not ok: log.error("sendMessage FAILED kind=%s after %d attempts", kind, TELEGRAM["retries"])
            self.ok += ok; self.failed += (not ok); all_ok &= ok
        return all_ok
    def get_updates(self, offset):
        if not self.live:
            if self.updates_fixture:
                try:
                    return [u for u in json.load(open(self.updates_fixture, encoding="utf-8")) if u["update_id"] >= (offset or 0)]
                except Exception:
                    return []
            return []
        try:
            r = self._api("getUpdates", {"offset": offset or 0, "timeout": 0, "allowed_updates": json.dumps(["message"])})
            return r.get("result", []) if r.get("ok") else []
        except Exception as e:
            log.warning("getUpdates failed: %s", e); return []
