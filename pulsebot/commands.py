# -*- coding: utf-8 -*-
"""Command parsing: Arabic + English aliases. Returns (command_id, argument) with ASCII ids."""
ALIASES = {
    "news": ["/الأخبار", "/الاخبار", "/news"],
    "alerts": ["/التنبيهات", "/alerts"],
    "stops": ["/الوقف", "/stops", "/stop"],
    "summary": ["/الملخص", "/summary"],
    "symbols": ["/الأسهم", "/الاسهم", "/symbols", "/stocks"],
    "status": ["/الحالة", "/status"],
    "help": ["/مساعدة", "/help", "/start"],
    "features": ["/الميزات", "/features"],
    "toggle": ["/تبديل", "/toggle"],
}
ON_WORDS = {"تشغيل", "on", "شغل", "تفعيل"}
OFF_WORDS = {"إيقاف", "ايقاف", "off", "وقف", "إيقاف"}
_LOOKUP = {a: k for k, v in ALIASES.items() for a in v}

def parse(text):
    if not text or not text.strip().startswith("/"):
        return None, None
    parts = text.strip().split()
    head = parts[0].split("@")[0]           # strip /cmd@BotName
    cmd = _LOOKUP.get(head) or _LOOKUP.get(head.lower())
    if not cmd:
        return "unknown", head
    onoff = lambda w: "on" if w in ON_WORDS else "off" if w in OFF_WORDS else w
    arg = None
    if cmd == "toggle":                    # /تبديل big_move إيقاف  ->  ("toggle", ("big_move", "off"))
        name = parts[1].strip().lower() if len(parts) > 1 else None
        val = onoff(parts[2].strip().lower()) if len(parts) > 2 else None
        return cmd, (name, val)
    if cmd == "summary":                   # /الملخص NVDA -> ("summary", "NVDA")
        return cmd, (parts[1].strip().upper() if len(parts) > 1 else None)
    if len(parts) > 1:
        arg = onoff(parts[1].strip().lower())
    return cmd, arg
