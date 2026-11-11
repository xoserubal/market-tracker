"""Extensión sobre SMA20 en ATR — contraste preregistrado (wiki/PREREGISTRO_EXTENSION_SMA20_ATR_V1.md).
Ejecución única. Salida: results.json."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEV = ('2016-01-01', '2020-12-31')
TEST = '2021-01-01'
SUB = [('2021-01-01', '2022-12-31'), ('2023-01-01', '2023-12-31'),
       ('2024-01-01', '2024-12-31'), ('2025-01-01', '2026-12-31')]
EMI = -0.5


def nw(x, lag):
    x = np.asarray(x, float); x = x[~np.isnan(x)]; n = len(x)
    if n < 3: return dict(n_dates=n)
    e = x - x.mean(); s = e @ e / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    se = np.sqrt(max(s, 0) / n); m = x.mean()
    return dict(n_dates=int(n), mean=round(float(m), 3), se=round(float(se), 3),
                t=round(float(m / se), 2) if se else None,
                ci95=[round(float(m - 1.96 * se), 3), round(float(m + 1.96 * se), 3)])


def main():
    p = pd.read_parquet(HERE / '_work' / 'prices.parquet')
    w = lambda c: p.pivot(index='Date', columns='ticker', values=c).sort_index()
    C0, AC, O, H, L = w('Close'), w('Adj Close'), w('Open'), w('High'), w('Low')
    f = AC / C0
    O, H, L, C = O * f, H * f, L * f, AC
    cal = C['SPY'].dropna().index
    C, O, H, L = (x.reindex(cal) for x in (C, O, H, L))
    spy = C.pop('SPY'); O.pop('SPY'); H.pop('SPY'); L.pop('SPY')
    tickers = C.columns

    pc = C.shift(1)
    tr = pd.concat([(H - L), (H - pc).abs(), (L - pc).abs()]).groupby(level=0).max().reindex(cal)
    atr = tr.rolling(14).mean()
    sma20 = C.rolling(20).mean()
    X = (C - sma20) / atr
    X = X.where(atr > 0)
    rs63 = (C / C.shift(63) - 1) - (spy / spy.shift(63) - 1).values[:, None]
    spy_up = spy > spy.rolling(200).mean()

    sectors = json.load(open(HERE.parent / 'macd_combo_filters_v1' / 'sectors.json'))['sector']
    sec = pd.Series({t: sectors.get(t) for t in tickers})

    # Fechas de decisión: último día bursátil de cada semana
    wk = pd.Series(cal, index=cal).resample('W-FRI').last().dropna()
    di_all = cal.get_indexer(pd.DatetimeIndex(wk.values))

    Cv, Ov, Xv, RSv = C.values, O.values, X.values, rs63.values
    n = len(cal)

    def panel(Hh, sector_neutral=False):
        rows = []
        for di in di_all:
            if di < 0 or di + Hh >= n:
                continue
            d = cal[di]
            if d < pd.Timestamp(DEV[0]):
                continue
            ret = Cv[di + Hh] / Ov[di + 1] - 1
            ok = ~np.isnan(ret)
            if ok.sum() < 50:
                continue
            if sector_neutral:
                r = pd.Series(ret, index=tickers)
                avg = r.groupby(sec).transform('mean').values
            else:
                avg = np.nanmean(ret)
            exc = (ret - avg) * 100
            x = Xv[di]; rs = RSv[di]
            m = ok & ~np.isnan(x)
            if m.sum() < 50:
                continue
            df = pd.DataFrame({'date': d, 'ticker': tickers[m], 'x': x[m], 'rs': rs[m], 'exc': exc[m],
                               'spy_up': bool(spy_up.iloc[di])})
            df['dec'] = pd.qcut(df['x'].rank(method='first'), 10, labels=False) + 1
            k = len(df)
            df['rx'] = df['x'].rank() / k - 0.5
            df['rrs'] = df['rs'].rank() / k - 0.5
            rows.append(df)
        return pd.concat(rows, ignore_index=True)

    lag_of = {5: 1, 10: 2, 20: 4}

    def d10_series(pn):
        return pn[pn['dec'] == 10].groupby('date')['exc'].mean()

    def summary(pn, Hh, b=None, extended=False):
        lag = lag_of[Hh]
        s10 = d10_series(pn)
        dev = s10[(s10.index >= DEV[0]) & (s10.index <= DEV[1])]
        tst = s10[s10.index >= TEST]
        out = {'D10_dev': nw(dev.values, lag), 'D10_test': nw(tst.values, lag)}
        if b is not None:
            q = pn.assign(res=pn['rx'] - b * pn['rrs'])
            ic = q.groupby('date').apply(lambda g: g['res'].rank().corr(g['exc'].rank()))
            out['IC_resid_dev'] = nw(ic[(ic.index >= DEV[0]) & (ic.index <= DEV[1])].values, lag)
            out['IC_resid_test'] = nw(ic[ic.index >= TEST].values, lag)
        if not extended:
            return out
        icr = pn.groupby('date').apply(lambda g: g['x'].rank().corr(g['exc'].rank()))
        out['IC_raw_test'] = nw(icr[icr.index >= TEST].values, lag)
        out['IC_raw_dev'] = nw(icr[(icr.index >= DEV[0]) & (icr.index <= DEV[1])].values, lag)
        pt = pn[pn['date'] >= TEST]
        pdv = pn[(pn['date'] >= DEV[0]) & (pn['date'] <= DEV[1])]
        out['deciles_test'] = {int(k): round(float(v), 3) for k, v in
                               pt.groupby(['date', 'dec'])['exc'].mean().groupby('dec').mean().items()}
        out['deciles_dev'] = {int(k): round(float(v), 3) for k, v in
                              pdv.groupby(['date', 'dec'])['exc'].mean().groupby('dec').mean().items()}
        rest = pt[pt['dec'] < 10].groupby('date')['exc'].mean()
        out['D10_minus_D1to9_test'] = nw((tst - rest.reindex(tst.index)).values, lag)
        for thr in (2, 3):
            out[f'X_gt_{thr}_test'] = nw(pt[pt['x'] > thr].groupby('date')['exc'].mean().values, lag)
            out[f'X_gt_{thr}_events_test'] = int((pt['x'] > thr).sum())
        out['subperiods'] = {f'{a[:4]}-{b_[:4]}': nw(tst[(tst.index >= a) & (tst.index <= b_)].values, lag)
                             for a, b_ in SUB}
        ev = pt[pt['dec'] == 10]
        cut = ev['exc'].quantile(0.01)
        out['D10_without_worst1pct_test'] = nw(ev[ev['exc'] >= cut].groupby('date')['exc'].mean().values, lag)
        weeks = sorted(tst.index)
        out['nonoverlap_grids'] = [round(float(tst[tst.index.isin(set(weeks[g::4]))].mean()), 3) for g in range(4)]
        return out

    res = {}
    p20 = panel(20)
    dv = p20[(p20['date'] >= DEV[0]) & (p20['date'] <= DEV[1])]
    b = float((dv['rx'] * dv['rrs']).sum() / (dv['rrs'] ** 2).sum())
    res['b_frozen_dev'] = round(b, 4)
    res['corr_rankX_rankRS63_dev'] = round(float(dv['rx'].corr(dv['rrs'])), 3)
    prim = summary(p20, 20, b=b, extended=True)
    res['primary_H20'] = prim

    t = prim['D10_test']
    crit = {
        '1_D10_le_EMI_and_upper_lt0': t['mean'] <= EMI and t['ci95'][1] < 0,
        '2_resid_IC_neg_t_le_-2': (prim['IC_resid_test'].get('t') or 0) <= -2 and prim['IC_resid_test']['mean'] < 0,
        '3_same_sign_dev': prim['D10_dev']['mean'] < 0 and prim['IC_resid_dev']['mean'] < 0,
        '4_D10_below_D1to9': prim['D10_minus_D1to9_test']['mean'] < 0,
        '5_subperiods_3of4_neg': sum(v['mean'] < 0 for v in prim['subperiods'].values()) >= 3,
        '6_without_worst1pct_neg': prim['D10_without_worst1pct_test']['mean'] < 0,
        '7_nonoverlap_4of4_neg': all(g < 0 for g in prim['nonoverlap_grids']),
    }
    res['criteria'] = crit
    if all(crit.values()):
        res['classification'] = 'VALIDADO'
    elif t['ci95'][0] > EMI:
        res['classification'] = 'NO SOPORTADO'
    else:
        res['classification'] = 'INCONCLUYENTE'
        if all(v for k, v in crit.items() if not k.startswith('2_')):
            res['classification'] += ' (efecto existe pero es la misma reversión que RS63)'

    sens = {}
    for Hh in (5, 10):
        sens[f'H{Hh}'] = summary(panel(Hh), Hh, b=b)
    sens['spy_above_sma200'] = summary(p20[p20['spy_up']], 20, b=b)
    sens['spy_below_sma200'] = summary(p20[~p20['spy_up']], 20, b=b)
    sens['sector_neutral'] = summary(panel(20, sector_neutral=True), 20, b=b)
    res['sensitivities'] = sens
    res['n_stock_weeks_test'] = int((p20['date'] >= TEST).sum())
    res['last_decision'] = str(p20['date'].max().date())

    (HERE / 'results.json').write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(res, indent=1, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
