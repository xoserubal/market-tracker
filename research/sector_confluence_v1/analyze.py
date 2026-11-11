"""
Confluencia sectorial v1 — paso 2: contraste preregistrado (wiki/PREREGISTRO_CONFLUENCIA_SECTORIAL_V1.md).

Primario: régimen con desfase, H=20, coste 0,1 %. Todo lo demás son sensibilidades.
Salida: results.json + texto por pantalla.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
WORK = HERE / "_work"
SECTORS = ['XLK', 'XLC', 'XLY', 'XLF', 'XLI', 'XLB', 'XLE', 'XLV', 'XLRE', 'XLP', 'XLU']
BUY = {'ACUMULAR', 'ACUMULAR*', 'COMPRA'}
DEV = ('2006-01-01', '2015-12-31')
TEST_START = '2016-01-01'
SUBPERIODS = [('2016-01-01', '2018-12-31'), ('2019-01-01', '2020-12-31'),
              ('2021-01-01', '2023-12-31'), ('2024-01-01', '2026-12-31')]
EMI = 0.5
Z975 = 2.241  # dos colas al 97,5 % (Bonferroni para A y B)
RNG = np.random.default_rng(20261111)
N_RANDOM = 1000


def nw_se(x: np.ndarray, lag: int = 4) -> float:
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return np.nan
    e = x - x.mean()
    s = e @ e / n
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        s += 2 * w * (e[k:] @ e[:-k]) / n
    return float(np.sqrt(max(s, 0) / n))


def summ(series: pd.Series) -> dict:
    x = series.dropna().values
    if len(x) == 0:
        return {'n_dates': 0}
    m, se = float(x.mean()), nw_se(x)
    return {'n_dates': int(len(x)), 'mean': round(m, 3), 'se_nw4': round(se, 3),
            't': round(m / se, 2) if se else None,
            'ci975': [round(m - Z975 * se, 3), round(m + Z975 * se, 3)]}


def load():
    sig = pd.read_parquet(WORK / 'signals_weekly.parquet')
    px = pd.read_parquet(WORK / 'prices_adj.parquet')
    cal = px[('SPY', 'close')].dropna().index
    close = pd.DataFrame({t: px[(t, 'close')] for t in SECTORS + ['SPY']}).reindex(cal)
    opn = pd.DataFrame({t: px[(t, 'open')] for t in SECTORS + ['SPY']}).reindex(cal)
    return sig, close, opn, cal


def build_panel(sig, close, opn, cal, regime_col_suffix=''):
    # Fecha de decisión: último día bursátil <= etiqueta semanal (viernes).
    wk = pd.Series(sorted(sig['date'].unique()))
    pos = cal.searchsorted(wk, side='right') - 1
    dmap = {w: (int(p) if p >= 0 else None) for w, p in zip(wk, pos)}
    ratio = close[SECTORS].div(close['SPY'], axis=0)
    r = lambda n: ratio / ratio.shift(n) - 1
    fc = (r(5) - (ratio.shift(5) / ratio.shift(10) - 1)) * 100
    alpha = (0.7 * r(63) + 0.3 * r(21)) * 100
    rs63 = r(63) * 100
    spy_up = close['SPY'] > close['SPY'].rolling(200).mean()

    rows = []
    fitc, sigc = 'fit' + regime_col_suffix, 'signal' + regime_col_suffix
    for rec in sig.itertuples(index=False):
        di = dmap[rec.date]
        if di is None:
            continue
        t = rec.ticker
        d = cal[di]
        if pd.isna(close.at[d, t]):
            continue
        rows.append((rec.date, di, t, bool(getattr(rec, fitc)), getattr(rec, sigc) in BUY,
                     fc.at[d, t], alpha.at[d, t], rs63.at[d, t], bool(spy_up.at[d])))
    p = pd.DataFrame(rows, columns=['week', 'di', 'ticker', 'fit', 'F', 'fc', 'alpha', 'rs63', 'spy_up'])
    p['L'] = p['fit'] & (p['alpha'] > 0)
    p['LF'] = p['L'] & p['F']
    p['A'] = p['LF'] & (p['fc'] > 0)
    p['B'] = p['LF'] & (p['fc'] < 0)
    return p


def add_targets(p, close, opn, cal, H):
    n = len(cal)
    ent = p['di'] + 1
    ex = p['di'] + H
    ok = ex < n
    p = p[ok].copy()
    ent, ex = ent[ok].values, ex[ok].values
    cl, op = close[SECTORS].values, opn[SECTORS].values
    col = {t: i for i, t in enumerate(SECTORS)}
    ci = p['ticker'].map(col).values
    retm = cl[ex] / op[ent] - 1  # matriz eventos × sectores
    own = retm[np.arange(len(p)), ci]
    avg = np.nanmean(retm, axis=1)
    p['excess'] = (own - avg) * 100
    return p.dropna(subset=['excess'])


def per_date(p, flag, cost):
    q = p[p[flag]]
    return (q.groupby('week')['excess'].mean() - cost * 100 / 100)


def evaluate(p, flag, cost=0.1, extended=True):
    out = {}
    s_all = p[p[flag]].groupby('week')['excess'].mean() - cost
    dev = s_all[(s_all.index >= DEV[0]) & (s_all.index <= DEV[1])]
    test = s_all[s_all.index >= TEST_START]
    out['dev'] = summ(dev)
    out['test'] = summ(test)
    out['n_events_test'] = int(p[p[flag] & (p['week'] >= TEST_START)].shape[0])
    if not extended:
        return out
    pt = p[p['week'] >= TEST_START]
    # Referencia 1: L y F sin condición de flow change (mismas fechas)
    lf = pt[pt['LF']].groupby('week')['excess'].mean() - cost
    d1 = (test - lf.reindex(test.index)).dropna()
    out['vs_LF'] = summ(d1)
    # Referencia 2: top-k por RS63, k = nº de sectores de la señal esa fecha
    k = pt[pt[flag]].groupby('week').size()
    topk = {}
    rand_mat = []
    for w, kk in k.items():
        g = pt[pt['week'] == w].dropna(subset=['rs63'])
        topk[w] = g.nlargest(kk, 'rs63')['excess'].mean() - cost
        ex = g['excess'].values
        rand_mat.append([ex[RNG.choice(len(ex), size=min(kk, len(ex)), replace=False)].mean() - cost
                         for _ in range(N_RANDOM)])
    topk = pd.Series(topk)
    out['vs_topk_rs63'] = summ((test - topk.reindex(test.index)).dropna())
    rand_means = np.array(rand_mat).mean(axis=0)
    out['random'] = {'mean_of_random': round(float(rand_means.mean()), 3),
                     'p975': round(float(np.percentile(rand_means, 97.5)), 3),
                     'percentile_of_signal': round(float((rand_means < test.mean()).mean() * 100), 1)}
    # Sin el 1 % mejor de eventos
    ev = pt[pt[flag]]
    cut = ev['excess'].quantile(0.99)
    out['test_without_top1pct'] = summ(ev[ev['excess'] <= cut].groupby('week')['excess'].mean() - cost)
    # Subperiodos
    out['subperiods'] = {f"{a[:4]}-{b[:4]}": summ(test[(test.index >= a) & (test.index <= b)])
                         for a, b in SUBPERIODS}
    # No solapado: 4 rejillas (una semana de cada cuatro)
    allweeks = sorted(pt['week'].unique())
    grids = []
    for g in range(4):
        sel = set(allweeks[g::4])
        x = test[test.index.isin(sel)]
        grids.append({'n': int(len(x)), 'mean': round(float(x.mean()), 3) if len(x) else None})
    out['nonoverlap_grids'] = grids
    # Clasificación
    t = out['test']
    c = {}
    c['1_mean_ge_EMI_and_lower_gt0'] = bool(t['mean'] >= EMI and t['ci975'][0] > 0)
    c['2_beats_refs'] = bool((out['vs_LF'].get('t') or 0) >= 2 and out['vs_LF']['mean'] > 0
                             and (out['vs_topk_rs63'].get('t') or 0) >= 2 and out['vs_topk_rs63']['mean'] > 0
                             and t['mean'] > out['random']['p975'])
    c['3_same_sign_dev'] = bool(out['dev'].get('mean', 0) > 0)
    c['4_without_top1pct_positive'] = bool(out['test_without_top1pct']['mean'] > 0)
    c['5_subperiods_3of4'] = bool(sum((v.get('mean') or -1) > 0 for v in out['subperiods'].values()) >= 3)
    c['6_nonoverlap_4of4'] = bool(all((g['mean'] or -1) > 0 for g in grids))
    out['criteria'] = c
    if all(c.values()):
        out['classification'] = 'VALIDADO'
    elif t['ci975'][1] < EMI:
        out['classification'] = 'NO SOPORTADO'
    else:
        out['classification'] = 'INCONCLUYENTE'
    return out


def main():
    sig, close, opn, cal = load()
    res = {}
    base = build_panel(sig, close, opn, cal)
    last_ok = len(cal) - 41  # decisión con 40 sesiones de futuro
    base = base[base['di'] <= last_ok]
    res['test_last_decision'] = str(cal[last_ok].date())

    p20 = add_targets(base, close, opn, cal, 20)
    p20 = p20[p20['week'] >= DEV[0]]
    res['primary'] = {f: evaluate(p20, f) for f in ['A', 'B']}
    res['reference_LF'] = evaluate(p20, 'LF', extended=False)

    # B − A en fechas con ambas
    pt = p20[p20['week'] >= TEST_START]
    a = pt[pt['A']].groupby('week')['excess'].mean()
    b = pt[pt['B']].groupby('week')['excess'].mean()
    res['B_minus_A_test'] = summ((b - a).dropna())
    pd_ = p20[(p20['week'] >= DEV[0]) & (p20['week'] <= DEV[1])]
    a = pd_[pd_['A']].groupby('week')['excess'].mean()
    b = pd_[pd_['B']].groupby('week')['excess'].mean()
    res['B_minus_A_dev'] = summ((b - a).dropna())

    # Sensibilidades
    sens = {}
    nl = build_panel(sig, close, opn, cal, regime_col_suffix='_nolag')
    nl = add_targets(nl[nl['di'] <= last_ok], close, opn, cal, 20)
    nl = nl[nl['week'] >= DEV[0]]
    sens['regime_nolag'] = {f: evaluate(nl, f, extended=False) for f in ['A', 'B']}
    for H in [5, 10, 40]:
        ph = add_targets(base, close, opn, cal, H)
        ph = ph[ph['week'] >= DEV[0]]
        sens[f'H{H}'] = {f: evaluate(ph, f, extended=False) for f in ['A', 'B']}
    sens['cost_0.2'] = {f: evaluate(p20, f, cost=0.2, extended=False) for f in ['A', 'B']}
    for lab, mask in [('spy_above_sma200', p20['spy_up']), ('spy_below_sma200', ~p20['spy_up'])]:
        sens[lab] = {f: evaluate(p20[mask], f, extended=False) for f in ['A', 'B']}
    # Eventos independientes: primera semana que cumple tras >= 4 semanas sin cumplir
    ind = {}
    for f in ['A', 'B']:
        q = p20.sort_values(['ticker', 'week']).copy()
        wk_index = {w: i for i, w in enumerate(sorted(p20['week'].unique()))}
        q['wi'] = q['week'].map(wk_index)
        keep = []
        for t, g in q.groupby('ticker'):
            last = -99
            for row in g.itertuples():
                if getattr(row, f):
                    keep.append(row.Index if row.wi - last > 4 else None)
                    last = row.wi
        keep = [k for k in keep if k is not None]
        qq = p20.loc[keep]
        qq = qq.assign(**{f: True})
        ind[f] = {'dev': summ(qq[(qq['week'] <= DEV[1])].groupby('week')['excess'].mean() - 0.1),
                  'test': summ(qq[qq['week'] >= TEST_START].groupby('week')['excess'].mean() - 0.1),
                  'n_events_test': int((qq['week'] >= TEST_START).sum())}
    sens['independent_events'] = ind
    res['sensitivities'] = sens

    (HERE / 'results.json').write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(res, indent=1, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
