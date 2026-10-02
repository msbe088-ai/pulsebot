"""Offline dry-run: replays a historical trading day through the real engine every 10 minutes (09:00..16:30 ET),
with commands injected from a fixture. Nothing is sent anywhere."""
import os, json, datetime as dt, shutil
from .market_time import ET
from .data import OfflineData
from .telegram import Telegram
from .engine import Engine

def replay_day(day, out_dir="samples/replay", cache="data_cache", commands=None, toggles=None, symbols=None, keep_state=False, news_getter=None):
    news_getter = news_getter or (lambda sym: [])   # offline: never touch the network
    os.makedirs(out_dir, exist_ok=True)
    state_path = os.path.join(out_dir, "state.json")
    if not keep_state and os.path.exists(state_path):
        os.remove(state_path)
    if toggles:
        from . import state as S
        st = S.new_state(); st["toggles"].update(toggles); S.save(st, state_path)
    log = []
    t = dt.datetime(day.year, day.month, day.day, 9, 0, tzinfo=ET)
    end = dt.datetime(day.year, day.month, day.day, 16, 30, tzinfo=ET)
    fixture = os.path.join(out_dir, "updates.json")
    while t <= end:
        upd = [c for c in (commands or []) if c["at"] == t.strftime("%H:%M")]
        if upd:
            json.dump([{"update_id": c["update_id"], "message": {"chat": {"id": 12345}, "text": c["text"]}} for c in upd], open(fixture, "w", encoding="utf-8"), ensure_ascii=False)
        elif os.path.exists(fixture):
            os.remove(fixture)
        tg = Telegram(token=None, chat_id=12345, live=False, updates_fixture=fixture if upd else None)
        Engine(OfflineData(cache, t), tg, t, state_path=state_path, symbols=symbols, news_getter=news_getter, heartbeat_path=os.path.join(out_dir, "heartbeat.txt")).run()
        for kind, text in tg.sent:
            log.append({"time": t.strftime("%H:%M"), "kind": kind, "text": str(text), "html": type(text).__name__ == "Html"})
        t += dt.timedelta(minutes=10)
    with open(os.path.join(out_dir, "messages.jsonl"), "w", encoding="utf-8") as f:
        for m in log:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return log
