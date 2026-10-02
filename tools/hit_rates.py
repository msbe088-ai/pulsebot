"""Historical hit rates of the bot's own target/stop formulas (same functions as the live bot).
1H data (~730 days, Yahoo limit) for the intraday plan; 20y daily for the big-move score and T3 reach.
Writes pulsebot/stats.json and tools/hit_rates_report.txt."""
import sys, json, collections, numpy as np, pandas as pd
sys.path.insert(0, '.')
from pulsebot.config import SYMBOLS, P
from pulsebot import indicators as I, rules as R
C = 'data_cache'
agg = collections.defaultdict(lambda: collections.defaultdict(float))
def add(key, **kv):
    a = agg[key]; a['n'] += 1
    for k, v in kv.items(): a[k] += v
for sym in SYMBOLS:
    d = pd.read_pickle(f'{C}/{sym}_1d.pkl'); h = pd.read_pickle(f'{C}/{sym}_60m.pkl')
    d.index = pd.to_datetime(d.index).date; d['ATR'] = I.wilder_atr(d).values
    days = sorted(set(h.index.date)); di = {x: i for i, x in enumerate(d.index)}
    byday = {x: h[h.index.date == x] for x in days}
    half = days[len(days) // 2]
    for j, day in enumerate(days):
        hb = byday[day]
        if len(hb) != 7 or day not in di or di[day] < 15: continue
        i = di[day]; prev = d.iloc[:i]; atr = float(prev['ATR'].iloc[-1])
        if not np.isfinite(atr): continue
        pdh, pdl = float(prev['High'].iloc[-1]), float(prev['Low'].iloc[-1]); pwh, pwl = R.prev_week_hl(prev.iloc[-15:], day)
        dl, dh = float(hb.Low.min()), float(hb.High.max())
        for k in (1, 2):
            nk = R.stop_note(hb, k)
            if nk is None: continue
            ok_ = (nk['low'] <= dl) if nk['side'] == 'up' else (nk['high'] >= dh)
            base_ = (float(hb.Low.iloc[:k].min()) <= dl) if nk['side'] == 'up' else (float(hb.High.iloc[:k].max()) >= dh)
            add(('NOTE', nk['side'], k), held=float(ok_))
            add(('BASE', 'up', k), held=float(float(hb.Low.iloc[:k].min()) <= dl)); add(('BASE', 'down', k), held=float(float(hb.High.iloc[:k].max()) >= dh))
        note = R.stop_note(hb, 1)
        if note is None: continue
        fut_day = hb.iloc[1:]; wk = [byday[x] for x in days[j + 1:j + 5] if len(byday[x]) > 0]
        fut_week = pd.concat([fut_day] + wk)
        for scen in ('aligned', 'reverse'):
            s = 1 if note['side'] == 'up' else -1
            if scen == 'reverse': s = -s
            stop = note['low'] if s > 0 else note['high']
            entry = note['price']
            if abs(entry - stop) < 1e-9: continue
            tg = R.targets(entry, stop, s, note['open'], atr, pdh, pdl, pwh, pwl)
            res = {}
            for horizon, bars in (('day', fut_day), ('week', fut_week)):
                hit = {t['name']: 0 for t in tg}; stopped = 0
                for _, b in bars.iterrows():
                    st_hit = (b.Low <= stop) if s > 0 else (b.High >= stop)
                    if st_hit: stopped = 1; break                     # conservative: stop wins same-bar conflicts
                    for t in tg:
                        if t['price'] is not None and not hit[t['name']] and ((b.High >= t['price']) if s > 0 else (b.Low <= t['price'])):
                            hit[t['name']] = 1
                res[horizon] = (hit, stopped)
            per = 'H1' if day < half else 'H2'
            for t in tg:
                if t['price'] is None: continue
                for p_ in ('ALL', per):
                    add((scen, t['name'], p_), day=res['day'][0][t['name']], week=res['week'][0][t['name']], chance=1 / (1 + t['mult']),
                        mult=t['mult'], stop_day=res['day'][1], stop_week=res['week'][1])
            add((scen, 'STOP', 'ALL'), day=res['day'][1], week=res['week'][1])
# 20y daily: big-move score & T3 reach
big = collections.defaultdict(lambda: collections.defaultdict(float))
for sym in SYMBOLS:
    d = pd.read_pickle(f'{C}/{sym}_1d.pkl')
    if len(d) < 400: continue
    a14 = I.wilder_atr(d, 14); a100 = I.wilder_atr(d, 100); r = a14 / a100
    sc = r.rolling(P['VOL_LOOKBACK'], min_periods=60).apply(lambda w: (w <= w[-1]).mean(), raw=True)
    prev_sc = sc.shift(1); prev_atr = a14.shift(1)
    rng = (d.High - d.Low) / prev_atr; up_t3 = (d.High >= d.Open + prev_atr); dn_t3 = (d.Low <= d.Open - prev_atr)
    ok = prev_sc.notna() & prev_atr.notna()
    fh = pd.concat([d.High.shift(-j) for j in range(0, 5)], axis=1).max(axis=1); fl = pd.concat([d.Low.shift(-j) for j in range(0, 5)], axis=1).min(axis=1)
    big5 = ((fh - d.Open) >= 2 * prev_atr) | ((d.Open - fl) >= 2 * prev_atr); ok5 = ok & fh.notna() & d.Low.shift(-4).notna()
    for grp, m in (('top20', ok & (prev_sc >= P['VOL_TOP_PCT'])), ('other', ok & (prev_sc < P['VOL_TOP_PCT']))):
        b = big[grp]; b['n'] += int(m.sum()); b['r1'] += float((rng[m] >= 1.0).sum()); b['r15'] += float((rng[m] >= 1.5).sum())
        b['rng'] += float(rng[m].sum()); b['t3u'] += float(up_t3[m].sum()); b['t3d'] += float(dn_t3[m].sum()); m5 = m & ok5; b['n5'] += int(m5.sum()); b['b5'] += float(big5[m5].sum()); b['rpct'] += float(((d.High - d.Low) / d.Close * 100)[m].sum())
out = {'targets': {}, 'big_move': {}, 'meta': {'symbols': len(SYMBOLS), 'hourly_days_approx': 725, 'window': 'conflict in the same 1H bar = stop'}}
lines = ['Historical hit rates of PulseBot plans (hour-1 note; entry = close of 10:30 bar; original stop, no trailing; 1H bars, same-bar conflict = stop)',
         '%-8s %-3s %-4s | %6s | %7s %7s | %7s | %6s | %7s %7s' % ('scenario', 'T', 'per', 'n', 'day%', 'week%', 'chance%', 'mult', 'stopD%', 'stopW%')]
out['stop_notes'] = {}
for side in ('up', 'down'):
    for k in (1, 2):
        a = agg[('NOTE', side, k)]; bb = agg[('BASE', side, k)]
        out['stop_notes'][f'{side}_{k}'] = {'n': int(a['n']), 'held': a['held'] / a['n'], 'base': bb['held'] / bb['n']}
        lines.append('stop note %-4s hour %d: n=%5d  extreme already in (stop survives the day) %.1f%%  vs all days %.1f%%' % (side, k, a['n'], 100 * a['held'] / a['n'], 100 * bb['held'] / bb['n']))
for (scen, t, per), a in sorted((k_, v) for k_, v in agg.items() if k_[0] not in ('NOTE', 'BASE')):
    n = a['n']
    if t == 'STOP':
        lines.append('%-8s %-4s %-4s | %6d | stop within day %.1f%%, within week %.1f%%' % (scen, t, per, n, 100 * a['day'] / n, 100 * a['week'] / n)); continue
    row = dict(n=int(n), day=a['day'] / n, week=a['week'] / n, chance=a['chance'] / n, mult=a['mult'] / n, stop_day=a['stop_day'] / n, stop_week=a['stop_week'] / n)
    if per == 'ALL': out['targets'].setdefault(scen, {})[t] = row
    else: out['targets'].setdefault(scen + '_' + per, {})[t] = row
    lines.append('%-8s %-3s %-4s | %6d | %6.1f%% %6.1f%% | %6.1f%% | %6.2f | %6.1f%% %6.1f%%' % (scen, t, per, n, 100 * row['day'], 100 * row['week'], 100 * row['chance'], row['mult'], 100 * row['stop_day'], 100 * row['stop_week']))
lines.append('\nBig-move score (20y daily, %d symbols with >=400 days): day range in units of the previous ATR14' % len([s for s in SYMBOLS if len(pd.read_pickle(f"{C}/{s}_1d.pkl")) >= 400]))
for g, b in big.items():
    n = b['n']; out['big_move'][g] = {'n': int(n), 'p_range_ge_1atr': b['r1'] / n, 'p_range_ge_15atr': b['r15'] / n, 'mean_range_atr': b['rng'] / n, 'p_t3_up': b['t3u'] / n, 'p_t3_down': b['t3d'] / n, 'p_2atr_5d': b['b5'] / b['n5'], 'mean_range_pct': b['rpct'] / n}
    lines.append('  %-6s n=%6d  P(range>=1 ATR)=%.1f%%  P(range>=1.5 ATR)=%.1f%%  mean range=%.2f ATR  P(high>=open+ATR)=%.1f%%  P(low<=open-ATR)=%.1f%%  P(2 ATR either way within 5 days)=%.1f%%  mean range=%.2f%% of price' % (
        g, n, 100 * b['r1'] / n, 100 * b['r15'] / n, b['rng'] / n, 100 * b['t3u'] / n, 100 * b['t3d'] / n, 100 * b['b5'] / b['n5'], b['rpct'] / n))
json.dump(out, open('pulsebot/stats.json', 'w'), indent=1)
open('tools/hit_rates_report.txt', 'w').write('\n'.join(lines) + '\n'); print('\n'.join(lines))
