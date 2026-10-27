"""Evaluacion retroactiva de las senales estructuradas de Sol (market_analysis_llm.jsonl).

Lo que mide: retorno de la cesta resuelta desde el cierre de la sesion SIGUIENTE a la fecha
del informe, a 1/3/5/10 sesiones, menos el retorno de SPY en la misma ventana.
Lo que NO mide: calidad de la narrativa, condiciones trigger/invalidation, subjects sin ticker.
Eventos independientes: mismo (ticker primario, conviccion) dentro de 5 sesiones cuenta una vez.
"""
import json, sys, statistics as st, collections, pathlib
import pandas as pd, yfinance as yf
from resolve import resolve

ROOT = pathlib.Path(__file__).resolve().parents[2]
rows = [json.loads(l) for l in open(ROOT/'docs/data/market_analysis_llm.jsonl', encoding='utf-8')]
H = [1, 3, 5, 10]
events = []
for r in rows:
    for s in r['structured']['signals']:
        tk = resolve(s['subject'])[:6]
        events.append(dict(date=r['date'], conv=s['conviction'], subject=s['subject'], tk=tk,
                           conf=s.get('confidence_pct')))
alltk = sorted({t for e in events for t in e['tk']} | {'SPY'})
px = yf.download(alltk, start='2026-09-01', auto_adjust=True, progress=False)['Close']
if isinstance(px, pd.Series): px = px.to_frame()
px = px.dropna(how='all')
missing = [t for t in alltk if t not in px.columns or px[t].dropna().empty]
print('sin precio:', missing)
dates = list(px.index.strftime('%Y-%m-%d'))

def entry_idx(d):
    for i, x in enumerate(dates):
        if x > d: return i
    return None

def ret(t, i0, h):
    if t not in px.columns: return None
    s = px[t]
    if i0 + h >= len(s): return None
    a, b = s.iloc[i0], s.iloc[i0 + h]
    if pd.isna(a) or pd.isna(b): return None
    return (b / a - 1) * 100

for e in events:
    e['i0'] = entry_idx(e['date'])
    for h in H:
        e[f'r{h}'] = None
        if e['i0'] is None or not e['tk']: continue
        rs = [ret(t, e['i0'], h) for t in e['tk']]; rs = [x for x in rs if x is not None]
        sp = ret('SPY', e['i0'], h)
        if rs and sp is not None: e[f'r{h}'] = sum(rs)/len(rs) - sp

# independencia
last = {}
for e in sorted(events, key=lambda x: (x['date'])):
    key = (e['tk'][0] if e['tk'] else e['subject'], e['conv'])
    e['indep'] = key not in last or (e['i0'] is not None and last[key] is not None and e['i0'] - last[key] > 5)
    if e['indep'] or key not in last: last[key] = e['i0']

def summ(sel, label):
    out = [label.ljust(28)]
    for h in H:
        v = [e[f'r{h}'] for e in sel if e['indep'] and e[f'r{h}'] is not None]
        if len(v) < 3: out.append(f'h{h}: n={len(v)}'.ljust(30)); continue
        m = st.mean(v); sd = st.pstdev(v); t = m/(sd/len(v)**.5) if sd else 0
        win = sum(1 for x in v if x > 0)/len(v)*100
        out.append(f'h{h}: n={len(v)} a={m:+.2f} med={st.median(v):+.2f} w={win:.0f}% t={t:+.1f}'.ljust(44))
    print(' '.join(out))

meas = [e for e in events if e['tk'] and e['i0'] is not None]
print('senales', len(events), 'con ticker', sum(1 for e in events if e['tk']), 'independientes', sum(1 for e in meas if e['indep']))
print('--- alfa vs SPY (cesta resuelta, entrada = cierre siguiente), eventos independientes ---')
for c in ['EARLY','CONFIRMED','WATCH','MATURE','EXTENDED','DISTRIBUTION','INVALIDATED']:
    summ([e for e in meas if e['conv'] == c], c)
summ([e for e in meas if e['conv'] in ('EARLY','CONFIRMED')], 'EARLY+CONFIRMED')
summ([e for e in meas if e['conv'] in ('DISTRIBUTION','INVALIDATED','EXTENDED')], 'bajistas (DIST/INVAL/EXT)')
# tickers individuales vs cestas
summ([e for e in meas if e['conv']=='EARLY' and len(e['tk'])==1], 'EARLY ticker unico')
summ([e for e in meas if e['conv']=='EARLY' and len(e['tk'])>1], 'EARLY cesta')
# por confianza
for lo, hi in [(0,55),(55,70),(70,101)]:
    summ([e for e in meas if e['conv'] in ('EARLY','CONFIRMED') and e['conf'] is not None and lo<=e['conf']<hi], f'EARLY+CONF conf {lo}-{hi}')
json.dump([{k:v for k,v in e.items()} for e in events], open(pathlib.Path(__file__).parent/'events_measured.json','w',encoding='utf-8'), ensure_ascii=False, indent=0)
