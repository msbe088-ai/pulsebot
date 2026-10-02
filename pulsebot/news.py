"""Optional news (OFF by default). Any failure is ignored silently (log only)."""
import logging, datetime as dt
log = logging.getLogger("pulsebot.news")

def _norm(sym, it):
    c = it.get("content", it)
    title = c.get("title"); link = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
    pub = (c.get("provider") or {}).get("displayName") or c.get("publisher") or "غير معروف"
    ts = c.get("pubDate") or c.get("providerPublishTime")
    uid = it.get("id") or c.get("id") or it.get("uuid") or link
    if not title or not link:
        return None
    if isinstance(ts, (int, float)):
        ts = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {"id": str(uid), "sym": sym, "title": title, "link": link, "publisher": pub, "time_txt": str(ts or "")}

def fetch_news(symbols, getter=None, per_symbol=3):
    out = []
    for s in symbols:
        try:
            items = getter(s) if getter else __import__("yfinance").Ticker(s).news
            for it in (items or [])[:per_symbol]:
                n = _norm(s, it)
                if n: out.append(n)
        except Exception as e:
            log.info("news %s ignored: %s", s, e)
    return out
