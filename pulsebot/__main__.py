"""CLI: python -m pulsebot run            (GitHub Actions; live only if PULSEBOT_LIVE=1 + secrets)
       python -m pulsebot replay DATE     (offline dry-run of a whole historical day from data_cache)"""
import os, sys, logging, datetime as dt
from .market_time import now_et, ET
from .telegram import Telegram
from .engine import Engine
from .data import LiveData, OfflineData

def main(argv=None):
    argv = argv or sys.argv[1:]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cmd = argv[0] if argv else "run"
    if cmd == "run":
        live = os.environ.get("PULSEBOT_LIVE") == "1"
        force = os.environ.get("PULSEBOT_FORCE_TEST") == "1" or "--test" in argv
        token = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat = os.environ.get("CHAT_ID")
        missing = [n for n, v in (("TELEGRAM_TOKEN", token), ("CHAT_ID", chat)) if not v]
        kw = {}
        if live and missing:
            # misconfigured CI: run as a dry-run on a throw-away state so nothing is marked "sent", then fail loudly
            print(f"::error::PULSEBOT_LIVE=1 but secret(s) missing: {', '.join(missing)} -> dry-run only, nothing sent")
            import tempfile
            kw["state_path"] = os.path.join(tempfile.mkdtemp(), "state.json")
        tg = Telegram(token, chat, live=live and not missing, outbox_path=None if live else "samples/outbox_live_dryrun.jsonl")
        Engine(LiveData(), tg, now_et(), force_test=force, **kw).run()
        for k, t in tg.sent:
            print(f"[{k}] {t.splitlines()[0] if t else ''}")
        print(f"messages: {len(tg.sent)} | live={tg.live} | ok={tg.ok} | failed={tg.failed}")
        if (live and missing) or tg.failed:
            sys.exit(1)
    elif cmd == "replay":
        from .replay import replay_day
        replay_day(dt.date.fromisoformat(argv[1]), out_dir=argv[2] if len(argv) > 2 else "samples/replay")
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
