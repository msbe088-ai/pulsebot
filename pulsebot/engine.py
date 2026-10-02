"""One bot run (GitHub Actions calls this every 10 minutes). Deterministic: same data + same state -> same messages."""
import logging, datetime as dt, os
import pandas as pd
from . import config as C, indicators as I, rules as R, messages as M, state as S, commands as CMD, news as NEWS
from .market_time import phase, session_bounds, is_trading_day, is_closed_bar, ET

log = logging.getLogger("pulsebot.engine")
NOTE_WORD = {"active": "سارية", "cancelled": "ملغاة (رجوع للافتتاح)", "broken": "ضُربت", "held": "صمدت حتى الإغلاق"}
PHASE_WORD = {"holiday": "عطلة أو نهاية أسبوع", "pre": "قبل الافتتاح", "open": "مفتوح", "post": "بعد الإغلاق", "closed": "مغلق"}

class Engine:
    def __init__(self, data, tg, now, state_path=C.STATE_PATH, symbols=None, stats=None, news_getter=None, heartbeat_path=None, force_test=False):
        self.data, self.tg, self.now = data, tg, now
        self.state_path = state_path; self.symbols = symbols or C.SYMBOLS; self.force_test = force_test
        self.stats = C.load_stats() if stats is None else stats
        self.news_getter = news_getter; self.queue = []
        self.heartbeat_path = heartbeat_path or os.path.join(os.path.dirname(state_path) or ".", "heartbeat.txt")

    # ---------- output ----------
    def emit(self, kind, text, alert=None):
        from .telegram import Html
        self.queue.append({"kind": kind, "text": str(text), "html": isinstance(text, Html)})   # html flag survives the JSON 'pending' list
        if alert: self.st["alerts"].append(alert)
    def flush(self):
        q = self.st.get("pending", []) + self.queue
        cap = C.TELEGRAM["max_per_run"]
        for m in q[:cap]:
            self.tg.send(m["text"], m["kind"], html=m.get("html", False))
            if self.st.get("counts"): self.st["counts"]["messages"] = self.st["counts"].get("messages", 0) + 1
        self.st["pending"] = q[cap:]
        self.queue = []

    def on(self, f):
        return self.st["toggles"].get(f, False)

    # ---------- main ----------
    def run(self):
        self.st = st = S.load(self.state_path)
        now = self.now; today = now.date(); ph = phase(now)
        if is_trading_day(today):
            S.roll_day(st, today)
        if not st.get("counts"): st["counts"] = S.zero_counts()
        st["last_run"] = now.strftime("%Y-%m-%d %H:%M ET"); self.ph = ph
        if self.on("commands"):
            self.handle_commands()
        work = ph in ("pre", "open", "post") and now.time() >= dt.time(*C.MARKET["morning_from"])
        if work:
            try:
                self.work(today, ph)
            except Exception as e:                       # never crash silently: tell the user
                log.exception("run failed")
                st["last_error"] = f"{now:%H:%M} خطأ داخلي: {type(e).__name__}"
                if self.on("tech_alerts") and S.once(st, f"{today}|tech|crash|{now.hour}", today):
                    self.emit("tech", M.tech({"time": now, "what": f"خطأ داخلي في البوت ({type(e).__name__})", "action": "تم تسجيل الخطأ وسيُعاد التشغيل تلقائياً"}))
        self.weekly_heartbeat(now)
        if self.force_test:                              # manual GitHub run: always one message, even when the market is closed
            self.emit("test", M.test_ping(self.reply("status", "")))
        self.flush()
        S.save(st, self.state_path)
        return self.tg.sent

    def weekly_heartbeat(self, now):
        wk = "%d-W%02d" % now.isocalendar()[:2]
        if self.st.get("heartbeat_week") != wk:
            self.st["heartbeat_week"] = wk
            os.makedirs(os.path.dirname(self.heartbeat_path) or ".", exist_ok=True)
            open(self.heartbeat_path, "w").write(f"pulsebot weekly heartbeat {wk} {now:%Y-%m-%d %H:%M} ET\n")

    # ---------- data ----------
    def fetch(self, ph):
        daily = self.data.fetch(self.symbols, "1d", C.DATA["daily_period"])
        hourly, m5 = {}, {}
        if ph in ("open", "post"):
            hourly = self.data.fetch(self.symbols, "60m", C.DATA["hourly_period"])
            m5 = self.data.fetch(self.symbols, "5m", C.DATA["check_period"])
        return daily, hourly, m5

    def tech_check(self, today, daily, hourly, ph):
        st = self.st; now = self.now
        miss_d = [s for s in self.symbols if s not in daily]
        miss_h = [s for s in self.symbols if s not in hourly] if ph in ("open", "post") else []
        miss = sorted(set(miss_d) | set(miss_h), key=self.symbols.index)
        st["data_ok"] = len(self.symbols) - len(miss); st["source"] = getattr(self.data, "source", "")
        if miss:
            what = "تعذر جلب البيانات لكل الأسهم" if len(miss) == len(self.symbols) else "تعذر جلب البيانات لبعض الأسهم"
            st["last_error"] = f"{now:%H:%M} {what} ({len(miss)})"
            if self.on("tech_alerts") and S.once(st, f"{today}|tech|data|{now.hour}|{len(miss)}", today):
                self.emit("tech", M.tech({"time": now, "what": what, "symbols": miss,
                                          "action": f"أعيدت المحاولة {C.DATA['retries']} مرات على yfinance (المصدر الوحيد) وفشلت"}))
        return miss

    def context(self, sym, today, daily, hourly, m5):
        d = daily.get(sym)
        if d is None or len(d) < C.P["ATR_N"] + 2:
            return None
        comp = d[[x < today for x in d.index]]
        x = {"sym": sym, "comp": comp}
        x["atr_d"] = float(I.wilder_atr(comp).iloc[-1])
        x["pdh"], x["pdl"] = float(comp["High"].iloc[-1]), float(comp["Low"].iloc[-1])
        x["pwh"], x["pwl"] = R.prev_week_hl(comp.iloc[-15:], today)
        mon = [i for i in d.index if (i.year, i.month) == (today.year, today.month)]
        x["month_open"] = float(d.loc[mon[0], "Open"]) if mon else None
        m = I.to_monthly(comp); w = I.to_weekly(comp)
        if len(m) and (m.index[-1].year, m.index[-1].month) == (today.year, today.month): m = m.iloc[:-1]
        if len(w) and w.index[-1].isocalendar()[:2] == today.isocalendar()[:2]: w = w.iloc[:-1]
        x["tr"] = {"M": I.trend(m), "W": I.trend(w), "D": I.trend(comp)}
        h = hourly.get(sym)
        if h is not None and len(h):
            closed = h[[is_closed_bar(b, 60, self.now) for b in h.index]]
            x["h_closed"] = closed; x["h_all"] = h
            x["h_today"] = closed[[b.date() == today for b in closed.index]]
            x["tr"]["H"] = I.trend(closed)
            x["atr_h"] = float(I.wilder_atr(closed).iloc[-1]) if len(closed) > C.P["ATR_N"] else None
            tday = h[[b.date() == today for b in h.index]]
            x["day_open"] = float(tday["Open"].iloc[0]) if len(tday) else None
            x["day_high"] = float(tday["High"].max()) if len(tday) else None
            x["day_low"] = float(tday["Low"].min()) if len(tday) else None
            x["last"] = float(tday["Close"].iloc[-1]) if len(tday) else None
        mm = m5.get(sym)
        if mm is not None and len(mm):
            mt = mm[[b.date() == today for b in mm.index]]
            if len(mt):
                x["m5"] = mt; x["last"] = float(mt["Close"].iloc[-1])
                x["day_high"] = max(x.get("day_high") or -1e18, float(mt["High"].max())); x["day_low"] = min(x.get("day_low") or 1e18, float(mt["Low"].min()))
        return x

    # ---------- work ----------
    def work(self, today, ph):
        st = self.st
        # everything produced in this run is collected here first, then rendered (consolidated / batched or one-by-one)
        self.out = {"big": [], "trend": [], "summary": [], "notes": {1: [], 2: []}, "notes_time": {}, "notes_other": {1: 0, 2: 0},
                    "events": [], "expired": [], "eod": None}
        daily, hourly, m5 = self.fetch(ph)
        self.tech_check(today, daily, hourly, ph)
        ctx = {}
        for s in self.symbols:
            try:
                c = self.context(s, today, daily, hourly, m5)
                if c: ctx[s] = c
            except Exception as e:
                log.exception("context %s", s)
        self.ctx = ctx
        big = self.big_moves(today, ctx)
        self.big_syms = {b["sym"] for b in big}
        if self.on("morning_heartbeat") and S.once(st, f"{today}|morning", today):
            _, close = session_bounds(today)
            self.emit("morning", M.morning({"date": today, "now": self.now, "close": close.strftime("%H:%M"), "n_symbols": len(self.symbols),
                                            "data_ok": st["data_ok"], "source": st["source"], "big": [b["sym"] for b in big], "toggles": st["toggles"]}))
        for b in big:
            if self.on("big_move") and S.once(st, f"{today}|big|{b['sym']}", today):
                st["counts"]["big_move"] += 1; self.out["big"].append(b)
                st["alerts"].append(f"⚡ {b['sym']}: تقلب أعلى من المعتاد (أعلى من {100 * b['score']:.0f}% من آخر سنة)")
        if ph in ("open", "post"):
            self.check_plans(today)              # first: plan status is current when the hour-2 board lists open plans
            for s in self.symbols:
                c = ctx.get(s)
                if not c or "h_closed" not in c or c.get("day_open") is None:
                    continue
                try:
                    self.do_symbol(s, c, today)
                except Exception:
                    log.exception("symbol %s", s)
            _, close = session_bounds(today)
            if self.now >= close:
                self.end_of_day(today)
        self.render(today)
        if ph in ("open", "post") and self.on("news"):
            self.do_news(today)

    def big_moves(self, today, ctx):
        out = []
        bm = self.stats.get("big_move", {})
        stt = {"top": bm["top20"], "other": bm["other"], "n_syms": 18} if "top20" in bm else None
        for s, c in ctx.items():
            v = I.vol_score(c["comp"])
            if v and v["score"] >= C.P["VOL_TOP_PCT"]:
                out.append(dict(v, sym=s, price=float(c["comp"]["Close"].iloc[-1]), stats=stt))
        return out

    def notable_reasons(self, s, bar_start):
        """NOTABLE (config.NOTABLE_RULE): big_move_active OR trend_change_today (at/before this bar) OR open_plan."""
        out = []
        if s in self.big_syms:
            out.append("⚡ تقلب عالٍ اليوم")
        tt = self.st["trend_today"].get(s)
        if tt and pd.Timestamp(tt) <= pd.Timestamp(bar_start):
            out.append("🔀 تغيّر اتجاه الساعة اليوم")
        if any(p["sym"] == s and p["status"] == "open" for p in self.st["plans"]):
            out.append("📋 خطة مفتوحة")
        return out

    def do_symbol(self, s, c, today):
        st = self.st; now = self.now
        ht = c["h_today"]
        _, close = session_bounds(today)
        # ---- 3 trend change: 1H close beyond the last confirmed swing (first: 'notable' depends on it) ----
        ev, _ = I.structure_events(c["h_closed"])
        last = st["last_trend"].get(s)
        if last is None:
            st["last_trend"][s] = c["h_closed"].index[-1].isoformat() if len(c["h_closed"]) else None
        else:
            for e in ev:
                if e["time"].isoformat() > last and e["time"].date() == today:
                    st["last_trend"][s] = e["time"].isoformat()
                    st["trend_today"][s] = e["time"].isoformat()
                    if self.on("trend_change") and S.once(st, f"{today}|trend|{s}|{e['time'].isoformat()}", today):
                        st["counts"]["trend_change"] += 1; st["counts"]["trend_" + e["dir"]] += 1
                        be = min(e["time"] + pd.Timedelta(minutes=60), close)
                        self.out["trend"].append(dict(e, sym=s, bar_start=e["time"], bar_end=be))
                        st["alerts"].append(f"{'🟢' if e['dir'] == 'up' else '🔴'} {s}: تغيّر اتجاه الساعة إلى {'صاعد' if e['dir'] == 'up' else 'هابط'} عند {be:%H:%M}")
            if len(c["h_closed"]):
                st["last_trend"][s] = max(st["last_trend"][s] or "", c["h_closed"].index[-1].isoformat())
        # ---- 2 hourly summary on a NEW closed 1H bar (detail kept for /الملخص SYMBOL) ----
        if len(ht):
            b0 = ht.index[-1]; key = b0.isoformat()
            prev = st["last_bar"].get(s)
            if (prev is None or pd.Timestamp(key) > pd.Timestamp(prev)) and S.once(st, f"{today}|sum|{s}|{key}", today):   # strictly newer bar only
                st["last_bar"][s] = key
                pl = self.summary_payload(s, c, ht, close)
                st["detail"][s] = M.summary(pl)
                if self.on("hourly_summary"):
                    self.out["summary"].append(pl)
        # ---- 5 stop notes after hour 1 / hour 2, 7 targets at hour 1 (notable symbols only when notable_only) ----
        for k in C.P["NOTE_HOURS"]:
            if len(ht) >= k and S.once(st, f"{today}|note|{s}|{k}", today):
                n = R.stop_note(ht, k)
                if not n:
                    continue
                n_end = min(n["time"] + pd.Timedelta(minutes=60), close)
                self.out["notes_time"][k] = n_end
                reasons = self.notable_reasons(s, n["time"])
                if self.on("notable_only") and not reasons:
                    self.out["notes_other"][k] += 1; continue
                stn = self.stats.get("stop_notes", {}).get(f"{n['side']}_{k}")
                stat, base, src, nn = (100 * stn["held"], 100 * stn["base"], f"تاريخياً على أسهم البوت، {stn['n']:,} حالة", stn["n"]) if stn \
                    else (n["stat"], n["base"], "دراسة 50 سهماً أمريكياً", 0)
                item = {"note": dict(n, sym=s, time_end=n_end, stat=stat, base=base, stat_src=src, n=nn),
                        "reasons": reasons or ["كل الأسهم (notable_only متوقف)"], "atr_d": c["atr_d"]}
                if self.on("stop_notes"):
                    rec = {"sym": s, "k": k, "side": n["side"], "stop": n["stop"], "open": n["open"], "price": n["price"], "time": n_end.isoformat(), "status": "active"}
                    st["notes"].setdefault(s, []).append(rec); st["counts"]["notes"] += 1
                if self.on("targets") and k in C.P["PLAN_HOURS"]:
                    item["plans"] = self.make_plans(s, c, n, n_end)
                else:
                    item["open_plans"] = [p for p in st["plans"] if p["sym"] == s and p["status"] == "open"]
                if self.on("stop_notes") or item.get("plans"):
                    self.out["notes"][k].append(item)
        # ---- 6 note cancelled / broken ----
        for rec in st["notes"].get(s, []):
            if rec["status"] != "active":
                continue
            hi, lo = self.window(s, c, pd.Timestamp(rec["time"]))
            up = rec["side"] == "up"
            if hi is not None and ((lo <= rec["stop"]) if up else (hi >= rec["stop"])):
                rec["status"] = "broken"; continue
            px = c.get("last")
            if px is not None and ((px < rec["open"]) if up else (px > rec["open"])):
                rec["status"] = "cancelled"; st["counts"]["notes_cancelled"] += 1
                if S.once(st, f"{today}|cancel|{s}|{rec['k']}", today):
                    self.out["events"].append({"type": "cancel", "kind": "stop_cancel",
                                               "p": {"sym": s, "side": rec["side"], "open": rec["open"], "price": px, "time": now}})
                    st["alerts"].append(f"↩️ {s}: أُلغيت ملاحظة الوقف (الساعة {rec['k']})")

    def summary_payload(self, s, c, ht, close):
        b0 = ht.index[-1]; price = float(ht["Close"].iloc[-1])
        tu = R.targets(price, price - c["atr_d"], 1, c["day_open"], c["atr_d"], c["pdh"], c["pdl"], c["pwh"], c["pwl"])[0]["price"]
        td = R.targets(price, price + c["atr_d"], -1, c["day_open"], c["atr_d"], c["pdh"], c["pdl"], c["pwh"], c["pwl"])[0]["price"]
        ups = sorted([(k, v) for k, v in (("round", I.next_round(price, 1)), ("pdh", c["pdh"]), ("pwh", c["pwh"])) if v is not None and v > price], key=lambda x: x[1])
        dns = sorted([(k, v) for k, v in (("round", I.next_round(price, -1)), ("pdl", c["pdl"]), ("pwl", c["pwl"])) if v is not None and v < price], key=lambda x: -x[1])
        p = {"sym": s, "bar_start": b0, "bar_end": min(b0 + pd.Timedelta(minutes=60), close), "price": price, "day_open": c["day_open"],
             "month_open": c["month_open"], "trends": c["tr"], "levels_up": ups, "levels_dn": dns, "atr_d": c["atr_d"], "atr_h": c.get("atr_h"),
             "day_high": float(ht["High"].max()), "day_low": float(ht["Low"].min()), "t_up": tu, "t_dn": td}
        self.st["last_summary"][s] = {"price": price, "chg": 100 * (price - c["day_open"]) / c["day_open"], "count": M.count_line(c["tr"])}
        return p

    def make_plans(self, s, c, n, n_end):
        st = self.st; plans = []
        for d_ in (n["side"], "down" if n["side"] == "up" else "up"):
            sgn = 1 if d_ == "up" else -1
            stop = n["low"] if d_ == "up" else n["high"]
            if abs(n["price"] - stop) < 1e-9:
                continue
            tg = R.targets(n["price"], stop, sgn, n["open"], c["atr_d"], c["pdh"], c["pdl"], c["pwh"], c["pwl"])
            pl = {"id": f"{s}|{n_end.date()}|{d_}", "sym": s, "dir": d_, "entry": n["price"], "stop": stop, "orig_stop": stop, "stop_kind": "orig",
                  "targets": tg, "hit": [], "status": "open", "created": n_end.isoformat(), "last_check": n_end.isoformat()}
            plans.append(pl)
        st["plans"] += plans; st["counts"]["plans"] += len(plans)
        return plans

    def window(self, s, c, since):
        """high/low of all bars since `since` (5m bars; falls back to 1H bars incl. the forming one)."""
        if "m5" in c:
            w = c["m5"][c["m5"].index >= since.floor("5min")]
        else:
            h = c.get("h_all"); w = h[[b + pd.Timedelta(minutes=60) > since for b in h.index]] if h is not None else None
            if w is not None: w = w[[b.date() == since.date() for b in w.index]]
        if w is None or not len(w):
            return None, None
        return float(w["High"].max()), float(w["Low"].min())

    def check_plans(self, today):
        st = self.st; now = self.now
        for pl in st["plans"]:
            if pl["status"] != "open":
                continue
            c = self.ctx.get(pl["sym"])
            if not c:
                continue
            hi, lo = self.window(pl["sym"], c, pd.Timestamp(pl["last_check"]))
            pl["last_check"] = now.isoformat()
            if hi is None:
                continue
            ev = R.check_window(pl, hi, lo)
            up = pl["dir"] == "up"
            pending_touch = [t for t in pl["targets"] if t["price"] is not None and t["name"] not in pl["hit"] and ((hi >= t["price"]) if up else (lo <= t["price"]))]
            for kind, price in ev:
                if kind == "stop":
                    pl["status"] = "stopped"; st["counts"]["stop"] += 1
                    if "T1" in pl["hit"]: st["counts"]["stop_after_t1"] += 1
                    self.out["events"].append({"type": "stop", "kind": "stop_hit", "p": {"sym": pl["sym"], "dir": pl["dir"], "time": now, "stop": pl["stop"],
                                               "entry": pl["entry"], "stop_kind": pl["stop_kind"], "hit": list(pl["hit"]), "conflict": bool(pending_touch)}})
                    st["alerts"].append(f"⛔ {pl['sym']} ({'صعود' if up else 'هبوط'}): ضُرب الوقف {M.money(pl['sym'], pl['stop'])}")
                    break
                pl["hit"].append(kind); st["counts"][kind] += 1
                new_stop = None
                if self.on("trail_stop_after_targets") and kind in ("T1", "T2"):
                    ns = R.trailing_stop(pl, kind)
                    if ns != pl["stop"]:
                        pl["stop"] = ns; pl["stop_kind"] = "entry" if kind == "T1" else "t1"; new_stop = ns
                t1 = next(t["price"] for t in pl["targets"] if t["name"] == "T1")
                remaining = [(t["name"], t["price"]) for t in pl["targets"] if t["price"] is not None and t["name"] not in pl["hit"]]
                self.out["events"].append({"type": "target", "kind": "target_" + kind, "p": {"sym": pl["sym"], "dir": pl["dir"], "target": kind, "time": now,
                                           "price": price, "entry": pl["entry"], "t1": t1, "new_stop": new_stop, "remaining": remaining, "stop": pl["stop"]}})
                st["alerts"].append(f"✅ {pl['sym']} ({'صعود' if up else 'هبوط'}): تحقق {kind} عند {M.money(pl['sym'], price)}")
                if not remaining:          # plan ends only when every available target was reached (T3 may be nearer than T1/T2)
                    pl["status"] = "done"; break

    def end_of_day(self, today):
        st = self.st; cnt = st["counts"]
        if not S.once(st, f"{today}|eod", today):
            return
        for pl in st["plans"]:
            if pl["status"] == "open":
                c = self.ctx.get(pl["sym"], {}); close_px = c.get("last", pl["entry"])
                if not pl["hit"]:
                    pl["status"] = "expired"; cnt["expired"] += 1
                    t1 = next(t["price"] for t in pl["targets"] if t["name"] == "T1")
                    self.out["expired"].append({"sym": pl["sym"], "dir": pl["dir"], "entry": pl["entry"], "close": close_px, "stop": pl["stop"], "t1": t1})
                else:
                    pl["status"] = "ended"
        for recs in st["notes"].values():
            for r in recs:
                if r["status"] == "active":
                    r["status"] = "held"; cnt["notes_held"] += 1
                elif r["status"] == "broken":
                    cnt["notes_broken"] += 1
        if self.on("eod_summary"):
            movers = sorted(((s, v["chg"]) for s, v in st["last_summary"].items()), key=lambda x: -abs(x[1]))[:3]
            _, close = session_bounds(today)
            self.out["eod"] = {"date": today, "close_time": close.strftime("%H:%M"), "movers": movers}

    # ---------- rendering: consolidated / batched (default) or one message per item (toggles off) ----------
    def render(self, today):
        st = self.st; o = self.out; B = self.on("batch_events")
        def many(kind, parts):
            for x in parts: self.emit(kind, x)
        if o["big"]:
            many("big_move", M.big_moves_batch(o["big"])) if B else [self.emit("big_move", M.big_move(b)) for b in o["big"]]
        if o["trend"]:
            many("trend_change", M.trend_batch(o["trend"])) if B else [self.emit("trend_change", M.trend_change(e)) for e in o["trend"]]
        if o["summary"]:
            if self.on("summary_consolidated"):
                groups = {}
                for r in o["summary"]:
                    groups.setdefault(r["bar_start"], []).append(r)
                for b0 in sorted(groups):
                    rows = groups[b0]; have = {r["sym"] for r in rows}
                    view = [{"sym": r["sym"], "price": r["price"], "day_open": r["day_open"], "trends": r["trends"],
                             "up": r["levels_up"][0] if r["levels_up"] else None, "dn": r["levels_dn"][0] if r["levels_dn"] else None} for r in rows]
                    many("summary", M.hourly_board({"bar_start": b0, "bar_end": rows[0]["bar_end"], "rows": view,
                                                    "missing": [x for x in self.symbols if x not in have]}))
            else:
                for r in o["summary"]:
                    self.emit("summary", M.summary(r))
        stt = (self.stats.get("targets") if self.on("show_hit_stats") else None) or {}
        for k in (1, 2):
            if k not in o["notes_time"] or not (self.on("stop_notes") or self.on("targets")):
                continue
            items = o["notes"][k]
            if self.on("notes_consolidated"):
                key = f"{today}|noteboard|{k}"
                if items:
                    S.once(st, key, today)
                elif not S.once(st, key, today):       # "nothing notable" is said once per hour-k, never after a real board
                    continue
                many("notes_board", M.notes_board({"k": k, "time": o["notes_time"][k], "items": items, "n_other": o["notes_other"][k], "stats": stt}))
            else:
                for it in items:
                    if self.on("stop_notes"):
                        self.emit("stop_note", M.stop_note(it["note"]))
                    if it.get("plans"):
                        self.emit("targets", M.targets({"sym": it["note"]["sym"], "time": it["note"]["time_end"], "plans": it["plans"],
                                                        "side": it["note"]["side"], "stats": stt, "atr_d": it["atr_d"]}))
        if o["events"]:
            if B:
                many("events", M.events_batch(self.now, o["events"]))
            else:
                fmt = {"cancel": M.stop_cancel, "target": M.target_hit, "stop": M.stop_hit}
                for e in o["events"]:
                    self.emit(e["kind"], fmt[e["type"]](e["p"]))
        if o["expired"]:
            many("plan_expired", M.expired_batch(o["expired"])) if B else [self.emit("plan_expired", M.plan_expired(x)) for x in o["expired"]]
        if o["eod"]:
            cnt = st["counts"]; view = dict(cnt)
            view["messages"] = cnt.get("messages", 0) + len(st.get("pending", [])) + len(self.queue) + 1
            self.emit("eod", M.eod(dict(o["eod"], counts=view)))

    def do_news(self, today):
        st = self.st; seen = set(st["news_seen"]); sent = 0
        try:
            items = NEWS.fetch_news(self.symbols, getter=self.news_getter)
        except Exception as e:
            log.info("news ignored: %s", e); return
        for n in items:
            if n["id"] in seen or sent >= 5:
                continue
            seen.add(n["id"]); st["news_seen"].append(n["id"]); sent += 1
            self.emit("news", M.news(n))
        st["news_seen"] = st["news_seen"][-500:]       # bounded dedupe list

    # ---------- commands ----------
    def handle_commands(self):
        st = self.st
        for u in self.tg.get_updates(st.get("update_offset", 0)):
            st["update_offset"] = max(st.get("update_offset", 0), u["update_id"] + 1)
            msg = u.get("message") or {}
            if self.tg.chat_id and str((msg.get("chat") or {}).get("id")) != str(self.tg.chat_id):
                log.info("ignored command from other chat"); continue
            cmd, arg = CMD.parse(msg.get("text", ""))
            if not cmd:
                continue
            self.emit("cmd_" + cmd, self.reply(cmd, arg))

    def find_symbol(self, arg):
        a = arg.upper().replace(".", "-").lstrip("^")
        return next((x for x in self.symbols if x.upper().lstrip("^") == a), None)

    def reply(self, cmd, arg):
        st = self.st
        if cmd == "news":
            if arg in ("on", "off"):
                st["toggles"]["news"] = arg == "on"; return M.news_toggle(arg == "on")
            return "اكتب: /الأخبار تشغيل أو /الأخبار إيقاف (/news on أو /news off)"
        if cmd == "alerts":
            return M.alerts_list(st["alerts"])
        if cmd == "stops":
            notes = []
            for recs in st["notes"].values():
                if recs:
                    r = recs[-1]
                    notes.append(dict(r, status_word=NOTE_WORD[r["status"]]))
            return M.stops_list(notes, [p for p in st["plans"] if p["status"] == "open"])
        if cmd == "summary":
            if arg:
                sym = self.find_symbol(arg)
                if not sym or sym not in st.get("detail", {}):
                    return M.detail_missing(arg, self.symbols)
                return M.detail_reply(st["detail"][sym], sym, [p for p in st["plans"] if p["sym"] == sym and p["status"] == "open"],
                                      [dict(r, status_word=NOTE_WORD[r["status"]]) for r in st["notes"].get(sym, [])])
            return M.quick_summary([dict(v, sym=s) for s, v in st["last_summary"].items()])
        if cmd == "symbols":
            return M.symbols_list(self.symbols)
        if cmd == "status":
            return M.status({"now": self.now, "phase_word": PHASE_WORD[phase(self.now)], "last_run": st.get("last_run"), "data_ok": st.get("data_ok", 0),
                             "n_symbols": len(self.symbols), "source": st.get("source") or "لم يُجلب بعد", "last_error": st.get("last_error"),
                             "toggles": st["toggles"], "counts": st.get("counts") or S.zero_counts(),
                             "open_plans": sum(1 for p in st["plans"] if p["status"] == "open"), "live": self.tg.live})
        if cmd == "help":
            return M.help_text()
        if cmd == "features":
            return M.features_list(st["toggles"])
        if cmd == "toggle":
            name, val = arg
            if name not in C.DEFAULT_TOGGLES or val not in ("on", "off"):
                return M.toggle_usage()
            if name == "commands" and val == "off":
                return "لا يمكن إيقاف الأوامر من داخل البوت (وإلا ما تقدر ترجّعها). عدّلها في config.py إن أردت."
            st["toggles"][name] = val == "on"
            return M.toggle_done(name, val == "on")
        return "أمر غير معروف. اكتب /مساعدة لعرض الأوامر."
