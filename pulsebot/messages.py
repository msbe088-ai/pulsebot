import re
# -*- coding: utf-8 -*-
"""Arabic display text for every message. Pure functions: payload dict -> str. Logic stays in rules.py/engine.py."""
from .market_time import hhmm
from .config import P

DISCLAIMER = "ℹ️ معلومة تعليمية وليست توصية شراء أو بيع."
REF_LABEL = "⚠️ مستويات مرجعية، مو توقع مضمون."
DIR_ICON = {"up": "🟢", "down": "🔴", "neutral": "⚪", "na": "❔"}
DIR_WORD = {"up": "صاعد", "down": "هابط", "neutral": "محايد", "na": "بيانات غير كافية"}
TF_WORD = {"M": "الشهري", "W": "الأسبوعي", "D": "اليومي", "H": "الساعة"}
TF_UNIT = {"M": "شهر", "W": "أسبوع", "D": "يوم", "H": "ساعة"}
SRC_WORD = {"round": "رقم دائري", "pdh": "قمة أمس", "pdl": "قاع أمس", "pwh": "قمة الأسبوع الماضي", "pwl": "قاع الأسبوع الماضي",
            "open_atr": "افتتاح اليوم ± ATR اليومي"}
WEEKDAY = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
T_WORD = {"T1": "الهدف الأول T1", "T2": "الهدف الثاني T2", "T3": "الهدف الثالث T3"}
FEATURE_WORD = {"morning_heartbeat": "رسالة الصباح", "hourly_summary": "الملخص كل ساعة", "trend_change": "تغيّر الاتجاه",
                "big_move": "تنبيه الحركة الكبيرة", "stop_notes": "ملاحظات الوقف", "targets": "الأهداف المرجعية",
                "trail_stop_after_targets": "رفع الوقف بعد الأهداف", "show_hit_stats": "إحصائيات الأهداف التاريخية",
                "news": "الأخبار", "eod_summary": "ملخص نهاية اليوم", "tech_alerts": "تنبيهات المشاكل التقنية", "commands": "الأوامر",
                "summary_consolidated": "الملخص كل ساعة في رسالة واحدة", "notable_only": "الوقف والأهداف للأسهم البارزة فقط",
                "notes_consolidated": "الوقف والأهداف في رسالة واحدة لكل ساعة", "batch_events": "تجميع الأحداث في رسالة واحدة لكل تشغيل"}

def money(sym, x, signed=False):
    if x is None:
        return "غير متاح"
    unit = " نقطة" if sym.startswith("^") else ""
    sign = ("+" if x > 0 else "−" if x < 0 else "") if signed else ""
    v = abs(x) if signed else x
    return f"{sign}{v:,.2f}{unit}" if unit else f"{sign}${v:,.2f}"

def pct(x, signed=True):
    sign = ("+" if x > 0 else "−" if x < 0 else "") if signed else ""
    return f"{sign}{abs(x):.2f}%"

def t(ts):
    return f"{hhmm(ts)} بتوقيت نيويورك"

def count_line(trends):
    ups = sum(1 for v in trends.values() if v["dir"] == "up"); dns = sum(1 for v in trends.values() if v["dir"] == "down")
    neu = sum(1 for v in trends.values() if v["dir"] == "neutral"); tot = len(trends)
    parts = []
    if ups: parts.append(f"{ups} من {tot} صاعدة 🟢")
    if dns: parts.append(f"{dns} من {tot} هابطة 🔴")
    if neu: parts.append(f"{neu} من {tot} محايدة ⚪")
    na = tot - ups - dns - neu
    if na: parts.append(f"{na} من {tot} بدون بيانات كافية")
    return "، ".join(parts)

# ---------------- 1 ----------------
def _morning_plain(p):
    d = p["date"]
    lines = [f"☀️ صباح الخير — البوت شغّال",
             f"اليوم: {WEEKDAY[d.weekday()]} {d.isoformat()} (يوم تداول، الافتتاح 09:30 والإغلاق {p['close']} بتوقيت نيويورك)",
             f"الوقت الآن: {t(p['now'])}",
             f"عدد الأسهم المتابعة: {p['n_symbols']}",
             f"البيانات: {p['data_ok']} من {p['n_symbols']} وصلت بنجاح (المصدر: {p['source']})"]
    if p["big"]:
        lines.append(f"⚡ تقلب أعلى من المعتاد اليوم ({len(p['big'])} من {p['n_symbols']} سهم): " + "، ".join(p["big"]))
    else:
        lines.append("⚡ لا يوجد سهم بتقلب ضمن أعلى 20% اليوم.")
    on = [FEATURE_WORD[k] for k, v in p["toggles"].items() if v]; off = [FEATURE_WORD[k] for k, v in p["toggles"].items() if not v]
    lines.append("المفعّل: " + "، ".join(on))
    if off: lines.append("المتوقف: " + "، ".join(off))
    lines.append("الملخصات تصل بعد إغلاق كل شمعة ساعة: 10:30، 11:30، 12:30، 13:30، 14:30، 15:30، 16:00.")
    return "\n".join(lines)

# ---------------- 2 ----------------
def trend_line(tf, v, sym):
    if v["dir"] == "na":
        return f"• {TF_WORD[tf]}: ❔ بيانات غير كافية (يلزم 25 شمعة، المتوفر {v.get('n', 0)})"
    rel = "فوق" if v["close"] > v["sma"] else "تحت" if v["close"] < v["sma"] else "عند"
    slope = "صاعد" if v["sma"] > v["sma_prev"] else "هابط" if v["sma"] < v["sma_prev"] else "ثابت"
    return (f"• {TF_WORD[tf]}: {DIR_ICON[v['dir']]} {DIR_WORD[v['dir']]} — آخر إغلاق {money(sym, v['close'])} {rel} متوسط 20 {TF_UNIT[tf]} "
            f"{money(sym, v['sma'])}، والمتوسط {slope} مقارنة بقبل 5 شموع ({money(sym, v['sma_prev'])})")

def summary(p):
    s = p["sym"]; chg = p["price"] - p["day_open"]; chg_p = 100 * chg / p["day_open"]
    icon = "🟢" if chg > 0 else "🔴" if chg < 0 else "⚪"
    L = [f"📊 ملخص {s} — شمعة الساعة {hhmm(p['bar_start'])}-{hhmm(p['bar_end'])} يوم {p['bar_start'].strftime('%Y-%m-%d')} (أُغلقت {t(p['bar_end'])})",
         f"السعر: {money(s, p['price'])} — {icon} {money(s, chg, True)} ({pct(chg_p)}) عن افتتاح اليوم {money(s, p['day_open'])}",
         "الاتجاه:"]
    for tf in ("M", "W", "D", "H"):
        L.append(trend_line(tf, p["trends"][tf], s))
    L.append(f"الخلاصة: {count_line(p['trends'])}")
    L.append("السبب: الفريم يُحسب صاعداً إذا الإغلاق فوق متوسط 20 شمعة والمتوسط أعلى من قيمته قبل 5 شموع، وهابطاً بالعكس، وغير ذلك محايد.")
    L.append("المستويات:")
    up = "، ".join(f"{money(s, x)} ({SRC_WORD[k]})" for k, x in p["levels_up"]) or "لا يوجد"
    dn = "، ".join(f"{money(s, x)} ({SRC_WORD[k]})" for k, x in p["levels_dn"]) or "لا يوجد"
    L += [f"• فوق السعر: {up}", f"• تحت السعر: {dn}",
          f"• افتتاح اليوم {money(s, p['day_open'])} — افتتاح الشهر {money(s, p['month_open'])}"]
    a = p["atr_d"]
    used = p["day_high"] - p["day_low"]
    L.append(f"الحركة المعتادة لليوم (ATR14 يومي): ±{money(s, a)} ({pct(100 * a / p['price'], False)} من السعر)")
    L.append(f"تحرّك اليوم حتى الآن (القمة − القاع): {money(s, used)} = {100 * used / a:.0f}% من المعتاد؛ المتبقي المعتاد تقريباً {money(s, max(0.0, a - used))}")
    L.append(f"ATR14 لفريم الساعة: {money(s, p['atr_h'])}")
    L.append(f"أقرب هدف مرجعي: صعوداً {money(s, p['t_up'])} ({money(s, p['t_up'] - p['price'], True)}) — هبوطاً {money(s, p['t_dn'])} ({money(s, p['t_dn'] - p['price'], True)})")
    L.append(DISCLAIMER)
    return "\n".join(L)

# ---------------- 3 ----------------
def trend_change(p):
    s = p["sym"]; up = p["dir"] == "up"
    dist = p["close"] - p["level"]
    return "\n".join([
        f"{'🟢' if up else '🔴'} {s} — تغيّر الاتجاه على فريم الساعة إلى {'صاعد' if up else 'هابط'} (تأكيد بإغلاق شمعة كاملة)",
        f"الشمعة: {hhmm(p['bar_start'])}-{hhmm(p['bar_end'])} أغلقت عند {money(s, p['close'])}",
        f"المستوى المكسور: {'آخر قمة متأرجحة' if up else 'آخر قاع متأرجح'} {money(s, p['level'])}",
        f"المسافة بعد الكسر: {money(s, dist, True)} ({pct(100 * dist / p['level'])})",
        f"الوقت: {t(p['bar_end'])}",
        "القاعدة: القمة/القاع المتأرجح = أعلى/أدنى شمعة من 3 شموع قبلها و3 بعدها، ولا يُعتمد إلا بعد اكتمال الشموع الثلاث.",
        DISCLAIMER])

# ---------------- 4 ----------------
def big_move(p):
    s = p["sym"]; st = p.get("stats") or {}
    L = [f"⚡ {s} — تقلب أعلى من المعتاد اليوم (بدون اتجاه)",
         f"مؤشر التقلب: ATR14 ÷ ATR100 = {money(s, p['atr14'])} ÷ {money(s, p['atr100'])} = {p['ratio']:.2f}",
         f"ترتيبه: أعلى من {100 * p['score']:.0f}% من آخر {p['n']} يوم لنفس السهم (التنبيه عند 80% أو أكثر)",
         f"الحركة المعتادة اليوم: ±{money(s, p['atr14'])} ({pct(100 * p['atr14'] / p['price'], False)} من سعر {money(s, p['price'])})"]
    if st:
        L.append(f"تاريخياً (20 سنة، {st['n_syms']} سهم): متوسط مدى اليوم في هذه الحالة {st['top']['mean_range_pct']:.1f}% من السعر مقابل "
                 f"{st['other']['mean_range_pct']:.1f}% في باقي الأيام.")
        L.append(f"بصراحة: مقارنةً بـATR نفسه الفرق صغير — مدى ≥ 1.5×ATR حصل في {100 * st['top']['p_range_ge_15atr']:.1f}% من هذه الأيام "
                 f"مقابل {100 * st['other']['p_range_ge_15atr']:.1f}% في غيرها. يعني: الحركة بالدولار أكبر لأن ATR نفسه مرتفع، وليس توقع حركة استثنائية.")
    L += ["الاتجاه غير معروف: التنبيه عن حجم الحركة فقط، لا عن صعود أو هبوط.", "ينتهي هذا التنبيه بنهاية جلسة اليوم.", DISCLAIMER]
    return "\n".join(L)

# ---------------- 5 ----------------
def stop_note(p):
    s = p["sym"]; up = p["side"] == "up"
    ext = "قاع اليوم حتى الآن" if up else "قمة اليوم حتى الآن"
    L = [f"🛡️ {s} — ملاحظة وقف بعد الساعة {'الأولى' if p['k'] == 1 else 'الثانية'} ({t(p['time_end'])})",
         f"افتتاح اليوم: {money(s, p['open'])}",
         f"السعر عند إغلاق الساعة: {money(s, p['price'])} — {'🟢 فوق' if up else '🔴 تحت'} الافتتاح بـ {money(s, abs(p['price'] - p['open']))}",
         f"{ext}: {money(s, p['stop'])} ← وقف مقترح {'تحته' if up else 'فوقه'}",
         f"المسافة من السعر للوقف: {money(s, abs(p['price'] - p['stop']))} ({pct(100 * abs(p['price'] - p['stop']) / p['price'], False)})",
         f"الإحصائية: لما يكون السعر {'فوق' if up else 'تحت'} الافتتاح بعد الساعة {p['k']}، {'كان قاع اليوم قد تكوّن' if up else 'كانت قمة اليوم قد تكوّنت'} فعلاً في "
         f"{p['stat']:.0f}% من الأيام، مقابل {p['base']:.0f}% في كل الأيام ({p['stat_src']}).",
         f"معنى ذلك: الوقف {'تحت القاع' if up else 'فوق القمة'} صمد لنهاية اليوم في {p['stat']:.0f}% من الحالات تاريخياً — هذا لا يعني أن السعر سيكمل {'صعوداً' if up else 'هبوطاً'}.",
         f"تبطل الملاحظة إذا رجع السعر {'تحت' if up else 'فوق'} الافتتاح {money(s, p['open'])}.",
         DISCLAIMER]
    return "\n".join(L)

# ---------------- 6 ----------------
def stop_cancel(p):
    s = p["sym"]; up = p["side"] == "up"
    return "\n".join([f"↩️ {s} — أُلغيت ملاحظة الوقف",
                      f"السبب: السعر رجع {'تحت' if up else 'فوق'} افتتاح اليوم {money(s, p['open'])}",
                      f"السعر الآن: {money(s, p['price'])} — الوقت {t(p['time'])}",
                      "الإحصائية السابقة لم تعد تنطبق على اليوم."])

# ---------------- 7 ----------------
def _plan_block(s, pl, st, atr_d=None, aligned=True):
    up = pl["dir"] == "up"
    risk = abs(pl["entry"] - pl["stop"])
    L = [f"{'🟢 سيناريو الصعود' if up else '🔴 سيناريو الهبوط'} (مرجع فقط) — {'مع اتجاه اليوم حتى الآن' if aligned else 'عكس اتجاه اليوم حتى الآن'}:",
         f"  الدخول المرجعي: {money(s, pl['entry'])} — الوقف: {money(s, pl['stop'])} ({'قاع' if up else 'قمة'} اليوم حتى الآن) — مسافة الوقف {money(s, risk)}"]
    if atr_d and risk < P["TINY_STOP_ATR"] * atr_d:
        L.append(f"  ⚠️ مسافة الوقف صغيرة جداً: {money(s, risk)} = {100 * risk / atr_d:.0f}% من الحركة اليومية المعتادة {money(s, atr_d)} "
                 f"(أقل من {100 * P['TINY_STOP_ATR']:.0f}%) — أي تذبذب بسيط يضربه، والمضاعفات هنا كبيرة بشكل مضلل.")
    for tg in pl["targets"]:
        if tg["price"] is None:
            L.append(f"  {tg['name']}: غير متاح (السعر تجاوز افتتاح اليوم ± ATR)")
            continue
        mult = f"{tg['mult']:.2f} × مسافة الوقف" if tg.get("mult") is not None else "—"
        L.append(f"  {tg['name']}: {money(s, tg['price'])} ({SRC_WORD[tg['src']]}) — يبعد {money(s, tg['dist'])} = {mult}")
        if st and tg["name"] in st:
            r = st[tg["name"]]
            ch = f"، والصدفة لهذه المسافة بالذات = 1 ÷ (1 + {tg['mult']:.2f}) = {100 / (1 + tg['mult']):.0f}%" if tg.get("mult") is not None else ""
            L.append(f"     تاريخياً ({r['n']:,} حالة مشابهة): وصل قبل الوقف خلال اليوم {100 * r['day']:.0f}%، خلال أسبوع {100 * r['week']:.0f}% "
                     f"— نسبة الصدفة لمتوسط تلك الحالات ≈ {100 * r['chance']:.0f}%{ch}")
    order = [tg for tg in pl["targets"] if tg["price"] is not None]
    if len(order) == 3 and not (order[2]["dist"] > order[1]["dist"] and order[2]["dist"] > order[0]["dist"]):
        L.append("  ملاحظة: T3 (افتتاح اليوم ± ATR) أقرب من T1 أو T2 هنا، كل هدف يُحسب لما يلمسه السعر بغض النظر عن الترتيب.")
    return L

def targets(p):
    s = p["sym"]
    L = [f"🎯 {s} — أهداف مرجعية للسيناريوهين ({t(p['time'])})", REF_LABEL]
    for pl in p["plans"]:
        al = pl["dir"] == p["side"]
        L += _plan_block(s, pl, p.get("stats", {}).get("aligned" if al else "reverse"), p.get("atr_d"), al)
    L.append("القواعد: T1 = أقرب رقم دائري أو قمة/قاع أمس بعد السعر؛ T2 = قمة/قاع الأسبوع الماضي (أو الرقم الدائري التالي)؛ T3 = افتتاح اليوم ± ATR14 اليومي.")
    L.append("المضاعف = بُعد الهدف ÷ مسافة الوقف. نسبة الصدفة = 1 ÷ (1 + المضاعف) = احتمال الوصول قبل الوقف لو الحركة عشوائية تماماً.")
    if p.get("stats"):
        L.append("بصراحة: النسب التاريخية قريبة من نسبة الصدفة (أو أقل خلال اليوم)، يعني الأهداف لا تعطي أفضلية إحصائية — هي مسافات مرجعية لإدارة المخاطرة.")
    L.append(DISCLAIMER)
    return "\n".join(L)

# ---------------- 8 / 9 / 10 ----------------
def target_hit(p):
    s = p["sym"]; up = p["dir"] == "up"
    L = [f"✅ {s} — تحقق {T_WORD[p['target']]} ({'سيناريو الصعود 🟢' if up else 'سيناريو الهبوط 🔴'})",
         f"الوقت: {t(p['time'])} — السعر المستهدف: {money(s, p['price'])}",
         f"{'الربح للصعود' if up else 'الربح للهبوط'} من الدخول المرجعي {money(s, p['entry'])}: {money(s, (p['price'] - p['entry']) * (1 if up else -1), True)}"]
    if p["target"] == "T1":
        L.append(f"اقتراح: انقل الوقف إلى سعر الدخول المرجعي {money(s, p['entry'])} (حتى لا تتحول لخسارة).")
    elif p["target"] == "T2":
        L.append(f"اقتراح: انقل الوقف إلى T1 {money(s, p['t1'])} لحماية جزء من الربح.")
    if p.get("new_stop") is not None:
        L.append(f"(في المتابعة الآلية صار الوقف {money(s, p['new_stop'])})")
    rem = p.get("remaining", [])
    if rem:
        L.append("الأهداف الباقية: " + "، ".join(f"{n} {money(s, x)}" for n, x in rem) + (f" — الوقف الحالي {money(s, p['stop'])}" if p.get("stop") is not None else ""))
    else:
        L.append("وصلت كل الأهداف المرجعية — انتهت الخطة.")
    return "\n".join(L)

# ---------------- 11 ----------------
def stop_hit(p):
    s = p["sym"]; up = p["dir"] == "up"
    kind = {"orig": "الوقف الأصلي", "entry": "الوقف عند سعر الدخول", "t1": "الوقف عند T1"}[p["stop_kind"]]
    L = [f"⛔ {s} — ضُرب الوقف ({'سيناريو الصعود' if up else 'سيناريو الهبوط'})",
         f"الوقت: {t(p['time'])} — {kind}: {money(s, p['stop'])}",
         f"النتيجة من الدخول المرجعي {money(s, p['entry'])}: {money(s, (p['stop'] - p['entry']) * (1 if up else -1), True)}",
         f"الأهداف المتحققة قبلها: {'، '.join(p['hit']) if p['hit'] else 'لا شيء'}"]
    if p.get("conflict"):
        L.append("ملاحظة: الوقف وهدف لُمسا في نفس فترة الفحص، فاحتُسب وقفاً (احتياطاً).")
    return "\n".join(L)

# ---------------- 12 ----------------
def plan_expired(p):
    s = p["sym"]
    return "\n".join([f"⌛ {s} — انتهت خطة {'الصعود' if p['dir'] == 'up' else 'الهبوط'} المرجعية بنهاية اليوم بدون هدف ولا وقف",
                      f"الدخول المرجعي: {money(s, p['entry'])} — سعر الإغلاق: {money(s, p['close'])} ({money(s, (p['close'] - p['entry']) * (1 if p['dir'] == 'up' else -1), True)})",
                      f"الوقف كان: {money(s, p['stop'])} — T1 كان: {money(s, p['t1'])}"])

# ---------------- 13 ----------------
def news(p):
    from .telegram import Html
    import html as _h
    e = lambda x: _h.escape(str(x), quote=False)
    S = "━" * __import__("pulsebot.config", fromlist=["SEPARATOR_LEN"]).SEPARATOR_LEN
    return Html("\n".join([f"📰 <b>{e(p['sym'])}</b> · خبر", S, e(p["title"]), S,
                           f"المصدر: {e(p['publisher'])}", f"الوقت: {e(p['time_txt'])}", e(p["link"]),
                           "(الأخبار تُعرض كما هي بدون تحليل)"]))

# ---------------- 14 ----------------
def _eod_plain(p):
    c = p["counts"]
    L = [f"🌙 ملخص نهاية اليوم {p['date'].isoformat()} (الإغلاق {p['close_time']} بتوقيت نيويورك)",
         f"تنبيهات الحركة الكبيرة: {c['big_move']} — تغيّر الاتجاه: {c['trend_change']} (🟢 {c['trend_up']} / 🔴 {c['trend_down']})",
         f"ملاحظات الوقف: {c['notes']} — صمدت حتى الإغلاق: {c['notes_held']} من {c['notes']} — أُلغيت (رجوع للافتتاح): {c['notes_cancelled']} — ضُربت: {c['notes_broken']}",
         f"الخطط المرجعية: {c['plans']} (سيناريوهان لكل سهم)",
         f"• وصلت T1: {c['T1']} من {c['plans']}",
         f"• وصلت T2: {c['T2']} من {c['plans']}",
         f"• وصلت T3: {c['T3']} من {c['plans']}",
         f"• ضُرب الوقف: {c['stop']} من {c['plans']} (منها {c['stop_after_t1']} بعد تحقق T1)",
         f"• انتهت بدون هدف ولا وقف: {c['expired']} من {c['plans']}",
         f"الرسائل المرسلة اليوم: {c['messages']}"]
    if p.get("movers"):
        L.append("أكبر تحرك اليوم: " + "، ".join(f"{s} {DIR_ICON['up' if v > 0 else 'down']} {pct(v)}" for s, v in p["movers"]))
    return "\n".join(L)

# ---------------- 15 ----------------
def _tech_plain(p):
    L = ["🛠️ مشكلة تقنية", f"الوقت: {t(p['time'])}", f"المشكلة: {p['what']}"]
    if p.get("symbols"):
        L.append(f"الأسهم المتأثرة ({len(p['symbols'])}): " + "، ".join(p["symbols"]))
    L.append(f"ما تم: {p['action']}")
    L.append("البوت سيحاول تلقائياً في التشغيل القادم (كل 10 دقائق).")
    return "\n".join(L)

# ---------------- command replies ----------------
def _status_plain(p):
    L = ["🩺 حالة البوت",
         f"الوقت: {p['now'].strftime('%Y-%m-%d')} {t(p['now'])}",
         f"حالة السوق: {p['phase_word']}",
         f"آخر تشغيل: {p['last_run']}",
         f"البيانات: {p['data_ok']} من {p['n_symbols']} سهم تمام — المصدر: {p['source']}",
         f"آخر مشكلة: {p['last_error'] or 'لا يوجد'}",
         f"الأخبار: {'تعمل ✅' if p['toggles']['news'] else 'متوقفة ⛔'}",
         f"اليوم: {p['counts']['messages']} رسالة، {p['counts']['notes']} ملاحظة وقف، {p['open_plans']} خطة مفتوحة",
         f"وضع الإرسال: {'حقيقي' if p['live'] else 'تجريبي (لا يُرسل شيء)'}",
         "التشغيل: كل 10 دقائق أيام التداول من 09:00 إلى 16:30 بتوقيت نيويورك (التوقيت الصيفي محسوب تلقائياً)."]
    return "\n".join(L)

def _help_text_plain():
    return "\n".join(["🤖 الأوامر المتاحة:",
                      "/الأخبار تشغيل — أو /news on : تشغيل الأخبار",
                      "/الأخبار إيقاف — أو /news off : إيقاف الأخبار",
                      "/التنبيهات — أو /alerts : تنبيهات اليوم",
                      "/الوقف — أو /stops : ملاحظات الوقف والخطط المفتوحة",
                      "/الملخص — أو /summary : ملخص سريع لكل الأسهم",
                      "/الملخص NVDA — أو /summary NVDA : التفاصيل الكاملة لسهم واحد (آخر شمعة ساعة مغلقة)",
                      "/الأسهم — أو /symbols : قائمة الأسهم",
                      "/الحالة — أو /status : حالة البوت",
                      "/الميزات — أو /features : كل الميزات وحالتها (تشغيل/إيقاف)",
                      "/تبديل اسم_الميزة تشغيل|إيقاف — أو /toggle name on|off : تشغيل أو إيقاف أي ميزة",
                      "/مساعدة — أو /help : هذه القائمة",
                      "ملاحظة: الرد يصل خلال 10 دقائق تقريباً (البوت يعمل بالجدولة وليس باستمرار)."])

def _features_list_plain(toggles):
    L = ["⚙️ الميزات (الاسم للأمر /تبديل — الحالة):"]
    for k, v in toggles.items():
        L.append(f"• {k} — {FEATURE_WORD.get(k, k)}: {'مفعّلة ✅' if v else 'متوقفة ⛔'}")
    L.append("مثال: /تبديل big_move إيقاف")
    return "\n".join(L)

def toggle_usage():
    return "الصيغة: /تبديل اسم_الميزة تشغيل أو /تبديل اسم_الميزة إيقاف (مثال: /تبديل big_move إيقاف). اكتب /الميزات لعرض الأسماء."

def toggle_done(name, on):
    return f"⚙️ {FEATURE_WORD.get(name, name)} ({name}): {'تم التشغيل ✅' if on else 'تم الإيقاف ⛔'}"

def news_toggle(on):
    return "📰 تم تشغيل الأخبار ✅" if on else "📰 تم إيقاف الأخبار ⛔"

def symbols_list(syms):
    return f"📋 الأسهم المتابعة ({len(syms)}):\n" + "، ".join(syms)

def alerts_list(items):
    if not items:
        return "🔔 لا توجد تنبيهات اليوم حتى الآن."
    return "🔔 تنبيهات اليوم:\n" + "\n".join(f"• {x}" for x in items)

def stops_list(notes, plans):
    if not notes and not plans:
        return "🛡️ لا توجد ملاحظات وقف أو خطط مفتوحة الآن."
    L = ["🛡️ ملاحظات الوقف:"]
    for n in notes:
        L.append(f"• {n['sym']}: {'🟢' if n['side'] == 'up' else '🔴'} وقف {money(n['sym'], n['stop'])} (الساعة {n['k']}) — {n['status_word']}")
    if plans:
        L.append("الخطط المفتوحة:")
        for p in plans:
            L.append(f"• {p['sym']} {'🟢 صعود' if p['dir'] == 'up' else '🔴 هبوط'}: دخول مرجعي {money(p['sym'], p['entry'])}، وقف {money(p['sym'], p['stop'])}، المتحقق: {'، '.join(p['hit']) or 'لا شيء'}")
    return "\n".join(L)

def quick_summary(rows):
    if not rows:
        return "📊 لا يوجد ملخص بعد (يصل أول ملخص بعد إغلاق شمعة 10:30)."
    L = ["📊 ملخص سريع (آخر شمعة ساعة مغلقة):"]
    for r in rows:
        L.append(f"• {r['sym']}: {money(r['sym'], r['price'])} {('🟢' if r['chg'] > 0 else '🔴' if r['chg'] < 0 else '⚪')} {pct(r['chg'])} من الافتتاح — {r['count']}")
    L.append("للتفاصيل: /الملخص NVDA")
    return "\n".join(L)


# =====================================================================================================
# Consolidated / batched formats (toggles summary_consolidated, notes_consolidated, batch_events)
# Sent with parse_mode=HTML: every dynamic value goes through esc(); symbols in <b>; one fact per line;
# a separator line (config.SEPARATOR_LEN x '━') between symbol blocks; header line, then a count line.
# =====================================================================================================
import html as _html
from .telegram import Html

def esc(x):
    return _html.escape(str(x), quote=False)

def sep():
    from .config import SEPARATOR_LEN
    return "━" * SEPARATOR_LEN

def b(x):
    return f"<b>{esc(x)}</b>"

NOTABLE_TEXT = "السهم البارز = تقلب عالٍ اليوم (درجة ≥ 80%) أو تغيّر اتجاه الساعة اليوم أو عنده خطة مفتوحة."

def pnl_label(direction):
    """profit label by scenario: positive amount = in favour of that scenario (down scenario: price fell)."""
    return "الربح للصعود" if direction == "up" else "الربح للهبوط"

def pnl(direction, entry, price):
    return (price - entry) * (1 if direction == "up" else -1)

def pack(header, blocks, footer, limit=None):
    """Pack symbol blocks into as few HTML messages as possible. `header` may be several lines; the part label goes on
    its first line. Split only BETWEEN blocks; each block is preceded by the separator line; footer once at the end.
    Length is measured on the RAW HTML (tags included) in UTF-16 units, so the visible text is always well under 4096."""
    from .telegram import tg_len
    from .config import TELEGRAM
    limit = limit or TELEGRAM["max_len"]
    hl = header.split("\n")
    def head(i, n):
        first = hl[0] if n == 1 else f"{hl[0]} (جزء {i} من {n})"
        return "\n".join([first] + hl[1:])
    S = sep()
    body = lambda bl: [x for blk in bl for x in (S, blk)]
    size = lambda bl, foot: tg_len("\n".join([head(99, 99)] + body(bl) + ([S, foot] if foot else [])))
    msgs, cur = [], []
    for blk in blocks:
        if cur and size(cur + [blk], "") > limit:
            msgs.append(cur); cur = []
        cur.append(blk)
    msgs.append(cur)
    while len(msgs[-1]) > 1 and size(msgs[-1], footer) > limit:     # make room for the footer in the last part
        msgs.append([msgs[-1].pop()])
    if footer and size(msgs[-1], footer) > limit:
        msgs.append([])
    n = len(msgs)
    return [Html("\n".join([head(i + 1, n)] + body(bl) + ([S, footer] if (i == n - 1 and footer) else [])))
            for i, bl in enumerate(msgs)]

def trend_majority(trends):
    """colour = 🟢 if #up > #down, 🔴 if #down > #up, else ⚪.  Text names the majority count out of 4."""
    ups = sum(1 for v in trends.values() if v["dir"] == "up"); dns = sum(1 for v in trends.values() if v["dir"] == "down")
    tot = len(trends)
    if ups > dns:
        return f"🟢 {ups} من {tot} صاعدة"
    if dns > ups:
        return f"🔴 {dns} من {tot} هابطة"
    neu = sum(1 for v in trends.values() if v["dir"] == "neutral")
    return f"⚪ متعادل ({ups} صاعدة، {dns} هابطة، {neu} محايدة من {tot})"

def _lvl(s, price, lv, arrow):
    if not lv:
        return f"{arrow} لا يوجد مستوى"
    k, x = lv
    return f"{arrow} {esc(money(s, x))} {SRC_WORD[k]} ({esc(money(s, x - price, True))})"

# ---- 2 board
def hourly_board(p):
    """ONE message per closed 1H bar (split between symbols only if the Telegram limit requires)."""
    b0, b1 = p["bar_start"], p["bar_end"]
    header = (f"📊 <b>ملخص الساعة {hhmm(b0)}-{hhmm(b1)}</b>\n"
              f"📅 {b0.strftime('%Y-%m-%d')} · أُغلقت {t(b1)}\n"
              f"🔢 {len(p['rows'])} سهم")
    blocks = []
    for r in p["rows"]:
        s = r["sym"]; chg = r["price"] - r["day_open"]; icon = "🟢" if chg > 0 else "🔴" if chg < 0 else "⚪"
        blocks.append("\n".join([
            f"{b(s)} {esc(money(s, r['price']))}",
            f"{icon} {esc(money(s, chg, True))} ({pct(100 * chg / r['day_open'])}) عن الافتتاح",
            f"الاتجاه: {trend_majority(r['trends'])}",
            _lvl(s, r["price"], r["up"], "⬆️"),
            _lvl(s, r["price"], r["dn"], "⬇️")]))
    foot = []
    if p.get("missing"):
        foot.append(f"⚠️ بدون بيانات هذه الساعة ({len(p['missing'])}): " + "، ".join(b(x) for x in p["missing"]))
    foot += ["الاتجاه = عدد الفريمات الصاعدة/الهابطة من 4 (شهري، أسبوعي، يومي، ساعة).",
             "الفريم صاعد إذا الإغلاق فوق متوسط 20 والمتوسط أعلى من قبل 5 شموع.",
             "⬆️/⬇️ = أقرب مستوى فوق/تحت السعر.",
             "🔎 التفاصيل: /الملخص NVDA",
             DISCLAIMER]
    return pack(header, blocks, "\n".join(foot))

# ---- /الملخص SYMBOL
def detail_reply(text, sym, plans, notes):
    """HTML version of the per-symbol summary (stored plain in state) + this symbol's notes and open plans."""
    body = text[: -len(DISCLAIMER)].rstrip("\n") if text.endswith(DISCLAIMER) else text
    lines = body.split("\n")
    out = [f"📊 <b>ملخص {esc(sym)}</b>", esc(lines[0].split("—", 1)[1].strip()) if "—" in lines[0] else ""]
    for ln in lines[1:]:
        if ln in ("الاتجاه:", "المستويات:"):
            out += [sep(), f"<b>{esc(ln.rstrip(':'))}</b>"]
        else:
            out.append(esc(ln))
    if notes or plans:
        out += [sep(), "<b>الوقف والخطط</b>"]
    for n in notes:
        out.append(f"🛡️ ملاحظة الساعة {n['k']}: {'🟢' if n['side'] == 'up' else '🔴'} وقف {esc(money(sym, n['stop']))} ({esc(n['status_word'])})")
    for pl in plans:
        rem = [f"{x['name']} {esc(money(sym, x['price']))}" for x in pl["targets"] if x["price"] is not None and x["name"] not in pl["hit"]]
        out += [f"📋 خطة {'🟢 الصعود' if pl['dir'] == 'up' else '🔴 الهبوط'}:",
                f"الدخول: {esc(money(sym, pl['entry']))}",
                f"الوقف الحالي: {esc(money(sym, pl['stop']))}",
                f"المتحقق: {'، '.join(pl['hit']) or 'لا شيء'}",
                f"الباقي: {' · '.join(rem) or 'لا شيء'}"]
    out += [sep(), DISCLAIMER]
    return Html("\n".join(x for x in out if x != ""))

def detail_missing(arg, syms):
    return Html(f"لا يوجد ملخص لـ {b(arg)}.\nالأسهم المتاحة: " + "، ".join(esc(x) for x in syms) + "\nمثال: /الملخص NVDA")

# ---- 4 batched
def big_moves_batch(items):
    st = (items[0].get("stats") or {}) if items else {}
    header = f"⚡ <b>تقلب أعلى من المعتاد اليوم</b>\n🔢 {len(items)} سهم · بدون اتجاه"
    blocks = ["\n".join([f"⚡ {b(x['sym'])}",
                         f"درجة التقلب: {100 * x['score']:.0f}%",
                         f"ATR14 ÷ ATR100 = {esc(money(x['sym'], x['atr14']))} ÷ {esc(money(x['sym'], x['atr100']))} = {x['ratio']:.2f}",
                         f"الحركة المعتادة اليوم: ±{esc(money(x['sym'], x['atr14']))} ({pct(100 * x['atr14'] / x['price'], False)})"]) for x in items]
    foot = ["القاعدة: درجة التقلب = نسبة آخر 252 يوم التي كانت نسبتها ≤ نسبة اليوم؛ التنبيه عند 80% أو أكثر."]
    if st:
        foot += [f"بصراحة: مدى ≥ 1.5×ATR حصل في {100 * st['top']['p_range_ge_15atr']:.1f}% من هذه الأيام مقابل {100 * st['other']['p_range_ge_15atr']:.1f}% في غيرها (20 سنة، {st['n_syms']} سهم).",
                 "يعني: الحركة أكبر بالدولار لأن ATR نفسه مرتفع، وليس توقع حركة استثنائية."]
    foot += ["الاتجاه غير معروف، وينتهي التنبيه بنهاية الجلسة.", DISCLAIMER]
    return pack(header, blocks, "\n".join(foot))

# ---- 3 batched
def trend_batch(items):
    header = f"🔀 <b>تغيّر الاتجاه على فريم الساعة</b>\n🔢 {len(items)} سهم · تأكيد بإغلاق شمعة كاملة"
    blocks = []
    for e in items:
        s = e["sym"]; up = e["dir"] == "up"; dist = e["close"] - e["level"]
        blocks.append("\n".join([f"{'🟢' if up else '🔴'} {b(s)} → {'صاعد' if up else 'هابط'}",
                                 f"الشمعة: {hhmm(e['bar_start'])}-{hhmm(e['bar_end'])}",
                                 f"الإغلاق: {esc(money(s, e['close']))}",
                                 f"{'آخر قمة متأرجحة' if up else 'آخر قاع متأرجح'}: {esc(money(s, e['level']))}",
                                 f"الفارق: {esc(money(s, dist, True))} ({pct(100 * dist / e['level'])})"]))
    foot = "القاعدة: القمة/القاع المتأرجح = أعلى/أدنى شمعة من 3 قبلها و3 بعدها، ويُعتمد بعد اكتمال الثلاث.\n" + DISCLAIMER
    return pack(header, blocks, foot)

# ---- 5 + 7 consolidated
def _tgt_line(s, tg):
    if tg["price"] is None:
        return f"{tg['name']}: غير متاح (السعر تجاوز الافتتاح ± ATR)"
    m = tg.get("mult")
    tail = f" · {m:.2f}× الوقف · صدفة {100 / (1 + m):.0f}%" if m is not None else ""
    return f"{tg['name']} {esc(money(s, tg['price']))} {SRC_WORD[tg['src']]}\n   يبعد {esc(money(s, tg['dist']))}{tail}"

def _plan_lines(s, pl, aligned, atr_d):
    up = pl["dir"] == "up"; risk = abs(pl["entry"] - pl["stop"])
    L = ["", f"{'🟢 <b>سيناريو الصعود</b>' if up else '🔴 <b>سيناريو الهبوط</b>'} ({'مع اتجاه اليوم' if aligned else 'عكس اتجاه اليوم'})",
         f"الدخول المرجعي: {esc(money(s, pl['entry']))}",
         f"الوقف: {esc(money(s, pl['stop']))} (المسافة {esc(money(s, risk))})"]
    if atr_d and risk < P["TINY_STOP_ATR"] * atr_d:
        L.append(f"⚠️ مسافة الوقف صغيرة جداً ({100 * risk / atr_d:.0f}% من ATR اليومي) — المضاعفات مضللة")
    L += [_tgt_line(s, tg) for tg in pl["targets"]]
    return L

def _stats_lines(stt):
    if not stt:
        return []
    def row(sc, k):
        r = stt[sc][k]
        return f"{k}: {100 * r['day']:.0f}% يوم · {100 * r['week']:.0f}% أسبوع · صدفة {100 * r['chance']:.0f}%"
    a, r = stt["aligned"]["T1"], stt["reverse"]["T1"]
    L = ["📈 <b>تاريخياً</b> (19 سهم، ~725 يوم، الوصول قبل الوقف):",
         f"مع الاتجاه ({a['n']:,} حالة، الوقف يُضرب خلال اليوم {100 * a['stop_day']:.0f}%):"]
    L += [row("aligned", k) for k in ("T1", "T2", "T3") if k in stt["aligned"]]
    L.append(f"عكس الاتجاه ({r['n']:,} حالة، الوقف يُضرب خلال اليوم {100 * r['stop_day']:.0f}%):")
    L += [row("reverse", k) for k in ("T1", "T2", "T3") if k in stt["reverse"]]
    L.append("بصراحة: النسب ≈ الصدفة أو أقل — الأهداف مسافات مرجعية لإدارة المخاطرة، لا أفضلية فيها.")
    return L

def notes_board(p):
    """ONE message after hour k (k = 1 or 2) for the notable symbols."""
    k = p["k"]; kw = "الأولى" if k == 1 else "الثانية"
    if not p["items"]:
        return [Html("\n".join([f"🛡️ <b>بعد الساعة {kw}</b>", f"🕐 {t(p['time'])}",
                                f"لا يوجد سهم بارز الآن، فلا ملاحظات وقف{' أو أهداف' if k == 1 else ''}.", NOTABLE_TEXT,
                                "لعرض كل الأسهم: /تبديل notable_only إيقاف"]))]
    header = (f"🛡️🎯 <b>{'الوقف والأهداف' if k == 1 else 'ملاحظات الوقف'} بعد الساعة {kw}</b>\n"
              f"🕐 {t(p['time'])}\n🔢 {len(p['items'])} سهم بارز · {p['n_other']} غير بارز")
    blocks = []
    for it in p["items"]:
        n = it["note"]; s = n["sym"]; up = n["side"] == "up"
        L = [f"{'🟢' if up else '🔴'} {b(s)}",
             f"السبب: {'، '.join(it['reasons'])}",
             f"الافتتاح: {esc(money(s, n['open']))}",
             f"السعر: {esc(money(s, n['price']))} ({'🟢 فوق' if up else '🔴 تحت'} الافتتاح بـ {esc(money(s, abs(n['price'] - n['open'])))})",
             f"🛡️ الوقف المقترح: {esc(money(s, n['stop']))} ({'تحت قاع' if up else 'فوق قمة'} اليوم)",
             f"المسافة: {esc(money(s, abs(n['price'] - n['stop'])))} ({pct(100 * abs(n['price'] - n['stop']) / n['price'], False)})",
             f"تاريخياً: {'القاع تكوّن' if up else 'القمة تكوّنت'} في {n['stat']:.0f}% مقابل {n['base']:.0f}% ({n['n']:,} حالة)",
             f"يبطل إذا رجع السعر {'تحت' if up else 'فوق'} {esc(money(s, n['open']))}"]
        for pl in it.get("plans", []):
            L += _plan_lines(s, pl, pl["dir"] == n["side"], it.get("atr_d"))
        for pl in it.get("open_plans", []):
            rem = [f"{x['name']} {esc(money(s, x['price']))}" for x in pl["targets"] if x["price"] is not None and x["name"] not in pl["hit"]]
            L += ["", f"📋 خطة {'🟢 الصعود' if pl['dir'] == 'up' else '🔴 الهبوط'} المفتوحة",
                  f"الدخول: {esc(money(s, pl['entry']))}",
                  f"الوقف الحالي: {esc(money(s, pl['stop']))}",
                  f"المتحقق: {'، '.join(pl['hit']) or 'لا شيء'}",
                  f"الباقي: {' · '.join(rem) or 'لا شيء'}"]
        if k == 2 and not it.get("open_plans"):
            L += ["", "📋 لا توجد خطة مفتوحة (الخطط تُبنى بعد الساعة الأولى فقط)."]
        blocks.append("\n".join(L))
    foot = ([REF_LABEL] if k == 1 else []) + [NOTABLE_TEXT]
    if k == 1:
        foot += ["القواعد: T1 = أقرب رقم دائري أو قمة/قاع أمس؛ T2 = قمة/قاع الأسبوع الماضي (أو الرقم الدائري التالي)؛ T3 = افتتاح اليوم ± ATR14 اليومي.",
                 "المضاعف = بُعد الهدف ÷ مسافة الوقف؛ الصدفة = 1 ÷ (1 + المضاعف)."]
        st_l = _stats_lines(p.get("stats"))
        if st_l:
            foot += [sep()] + st_l
    foot.append(DISCLAIMER)
    return pack(header, blocks, "\n".join(foot))

# ---- 6 / 8-11 batched
def _event_block(e):
    p = e["p"]; s = p["sym"]
    if e["type"] == "cancel":
        up = p["side"] == "up"
        return "\n".join([f"↩️ {b(s)} أُلغيت ملاحظة الوقف",
                          f"السعر: {esc(money(s, p['price']))}",
                          f"رجع {'تحت' if up else 'فوق'} الافتتاح {esc(money(s, p['open']))}"])
    up = p["dir"] == "up"; sc = "🟢 صعود" if up else "🔴 هبوط"
    if e["type"] == "stop":
        kind = {"orig": "الوقف الأصلي", "entry": "الوقف عند الدخول", "t1": "الوقف عند T1"}[p["stop_kind"]]
        L = [f"⛔ {b(s)} {sc}",
             f"ضُرب {kind}: {esc(money(s, p['stop']))}",
             f"{pnl_label(p['dir'])} من الدخول {esc(money(s, p['entry']))}: {esc(money(s, pnl(p['dir'], p['entry'], p['stop']), True))}",
             f"المتحقق قبله: {'، '.join(p['hit']) or 'لا شيء'}"]
        if p.get("conflict"):
            L.append("⚠️ الوقف وهدف لُمسا في نفس الفترة، فاحتُسب وقفاً (احتياطاً)")
        return "\n".join(L)
    L = [f"✅ {b(s)} {sc}",
         f"تحقق {p['target']}: {esc(money(s, p['price']))}",
         f"{pnl_label(p['dir'])} من الدخول {esc(money(s, p['entry']))}: {esc(money(s, pnl(p['dir'], p['entry'], p['price']), True))}"]
    if p["target"] == "T1":
        L.append(f"💡 انقل الوقف إلى الدخول {esc(money(s, p['entry']))}")
    elif p["target"] == "T2":
        L.append(f"💡 انقل الوقف إلى T1 {esc(money(s, p['t1']))}")
    rem = p.get("remaining", [])
    if rem:
        L.append("الباقي: " + " · ".join(f"{n} {esc(money(s, x))}" for n, x in rem))
        L.append(f"🛡️ الوقف الحالي: {esc(money(s, p['stop']))}")
    else:
        L.append("🏁 وصلت كل الأهداف — انتهت الخطة")
    return "\n".join(L)

def events_batch(time, events):
    nh = sum(1 for e in events if e["type"] == "target"); ns = sum(1 for e in events if e["type"] == "stop"); nc = sum(1 for e in events if e["type"] == "cancel")
    parts = [f"{nh} هدف" if nh else "", f"{ns} وقف" if ns else "", f"{nc} إلغاء ملاحظة" if nc else ""]
    header = (f"🔔 <b>تحديثات المتابعة</b>\n🕐 {t(time)}\n"
              f"🔢 {len(events)} {'حدث' if len(events) in (1, 2) or len(events) > 10 else 'أحداث'}: " + " · ".join(x for x in parts if x))
    return pack(header, [_event_block(e) for e in events], "مستويات مرجعية فقط — ليست توصية شراء أو بيع.")

# ---- 12 batched
def expired_batch(items):
    header = f"⌛ <b>خطط انتهت بنهاية اليوم</b>\n🔢 {len(items)} خطة · بدون هدف ولا وقف"
    blocks = []
    for p in items:
        s = p["sym"]
        blocks.append("\n".join([f"⌛ {b(s)} {'🟢 صعود' if p['dir'] == 'up' else '🔴 هبوط'}",
                                 f"الدخول: {esc(money(s, p['entry']))}",
                                 f"الإغلاق: {esc(money(s, p['close']))}",
                                 f"{pnl_label(p['dir'])}: {esc(money(s, pnl(p['dir'], p['entry'], p['close']), True))}",
                                 f"الوقف كان: {esc(money(s, p['stop']))} · T1 كان: {esc(money(s, p['t1']))}"]))
    return pack(header, blocks, "")


# ---- single messages in the same HTML style: bold title, escaped lines, separators between sections
def _as_html(text, sep_before=()):
    lines = text.split("\n")
    out = [f"<b>{esc(lines[0])}</b>"]
    for ln in lines[1:]:
        if any(ln.startswith(x) for x in sep_before):
            out.append(sep())
        out.append(esc(ln))
    return Html("\n".join(out))

def morning(p):
    return _as_html(_morning_plain(p), ("⚡", "المفعّل"))

def eod(p):
    """same facts as the plain version, but 'a — b — c' lines become one fact per line."""
    out = []
    for ln in _eod_plain(p).split("\n"):
        if ln.startswith("تنبيهات الحركة") and " — " in ln:          # two independent counts: two lines
            out += ln.split(" — ")
        elif ln.startswith("ملاحظات الوقف") and " — " in ln:          # total, then its breakdown as bullets
            head, *rest = ln.split(" — ")
            out += [head] + [f"• {x}" for x in rest]
        else:
            out.append(ln)
    return _as_html("\n".join(out), ("ملاحظات الوقف", "الخطط المرجعية", "الرسائل المرسلة"))

def tech(p):
    return _as_html(_tech_plain(p), ("ما تم",))

def _split_facts(text, prefixes):
    """'a — b' / 'a، b، c' lines that hold several facts -> one fact per line."""
    out = []
    for ln in text.split("\n"):
        if ln.startswith(prefixes) and " — " in ln:
            out += ln.split(" — ")
        else:
            out.append(ln)
    return "\n".join(out)

def status(p):
    txt = _split_facts(_status_plain(p), ("البيانات",))
    out = []
    for ln in txt.split("\n"):
        if ln.startswith("اليوم: ") and "، " in ln:
            out += ["اليوم:"] + [f"• {x}" for x in ln[len("اليوم: "):].split("، ")]
        else:
            out.append(ln)
    return _as_html("\n".join(out), ("البيانات", "اليوم", "وضع الإرسال"))

def help_text():
    """each command: bold Arabic command + English alias on one line, what it does on the next."""
    lines = _help_text_plain().split("\n")
    out = [f"<b>{esc(lines[0])}</b>", f"🔢 {sum(1 for x in lines if x.startswith('/'))} أمر"]
    for ln in lines[1:]:
        m = re.match(r"^(/.+?) — أو (/.+?) : (.+)$", ln)
        if m:
            out += [sep(), f"<b>{esc(m.group(1))}</b>  ({esc(m.group(2))})", esc(m.group(3))]
        else:
            out += [sep(), esc(ln)]
    return Html("\n".join(out))

def features_list(toggles):
    return _as_html(_features_list_plain(toggles))


def test_ping(status_msg):
    """manual run (workflow_dispatch with force_test): proves the GitHub -> Telegram path works, then the status."""
    return Html("\n".join(["🧪 <b>رسالة اختبار — تشغيل يدوي من GitHub Actions</b>",
                           "وصول هذه الرسالة = الإرسال من GitHub يعمل ✅", sep(), str(status_msg)]))
