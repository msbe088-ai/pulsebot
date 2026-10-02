"""Sends the review set in samples/telegram_review_set.json to Telegram ONCE.
DRY-RUN unless --live is given. Separator lines are re-drawn with --sep N (20 / 24 / 28) without re-running the replay.
Uses pulsebot.telegram.Telegram: parse_mode=HTML, 1.2 s spacing, 429 retry_after handled, plain-text fallback on 400.
    python3 tools/send_samples.py --sep 24                 # preview only
    TELEGRAM_BOT_TOKEN=... python3 tools/send_samples.py --sep 24 --chat <CHAT_ID> --live
"""
import sys, os, re, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pulsebot.telegram import Telegram, Html, tg_len

ap = argparse.ArgumentParser()
ap.add_argument("--sep", type=int, default=24); ap.add_argument("--chat", default=os.environ.get("CHAT_ID"))
ap.add_argument("--live", action="store_true")
a = ap.parse_args()
items = json.load(open(os.path.join(os.path.dirname(__file__), "..", "samples", "telegram_review_set.json"), encoding="utf-8"))
redraw = lambda s: re.sub(r"(?m)^━+$", "━" * a.sep, s)
token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
tg = Telegram(token, a.chat, live=a.live)
if a.live and not tg.live:
    sys.exit("missing token or --chat; nothing sent")
for it in items:
    body = redraw(it["text"]); body = Html(body) if it["html"] else body
    print(f"--- {it['label']} ({tg_len(body)} UTF-16 units, html={it['html']})"); print(body if not a.live else "")
    tg.send(body, it["label"])
print(f"{'LIVE' if tg.live else 'DRY-RUN'}: {len(items)} messages, ok={tg.ok}, failed={tg.failed}")
