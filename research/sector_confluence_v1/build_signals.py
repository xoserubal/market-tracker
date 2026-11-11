"""
Confluencia sectorial v1 — paso 1: reconstruir régimen y señales (preregistro §3, §8.2).

1. Recalcula el MacroScore SIN desfase con backtest/src/macro y comprueba que reproduce
   el régimen guardado (macro_history.parquet, modo A). Si no, se para.
2. Recalcula el MacroScore CON desfase de publicación:
     - NetLiq (WALCL, WTREGEN, RRP): dato de la semana anterior (shift 1 semana).
     - CFNAI: el valor del mes M solo está disponible desde el primer viernes >= día 25 de M+1.
     - Series de mercado: sin cambios.
3. Reconstruye Flujos & Rotación (modo A) con cada régimen sobre los OHLCV de backtest/data/raw.
4. Guarda en _work/ las señales semanales de los 11 SPDR y los precios diarios ajustados.

No calcula ninguna rentabilidad futura.
"""
from __future__ import annotations
import sys, logging
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BT = ROOT / "backtest"
sys.path.insert(0, str(BT))
from src.macro.simulator import simulate_history            # noqa: E402
from src.rotation.simulator import simulate_rotation_history  # noqa: E402
from src.rotation.indicators import load_daily_ohlcv          # noqa: E402
from src.rotation.clusters import TICKERS_NO_SPY              # noqa: E402

logging.basicConfig(level=logging.WARNING)
PROC, RAW = BT / "data" / "processed", BT / "data" / "raw"
WORK = Path(__file__).resolve().parent / "_work"
WORK.mkdir(exist_ok=True)
SECTORS = ['XLK', 'XLC', 'XLY', 'XLF', 'XLI', 'XLB', 'XLE', 'XLV', 'XLRE', 'XLP', 'XLU']


def load_macro_inputs():
    return {
        'prices_weekly': pd.read_parquet(PROC / 'prices_weekly.parquet'),
        'macro_daily':   pd.read_parquet(PROC / 'macro_daily.parquet'),
        'macro_weekly':  pd.read_parquet(PROC / 'macro_weekly.parquet'),
        'hy_real':       pd.read_parquet(PROC / 'hy_spread_real_only.parquet'),
    }


def cfnai_point_in_time(cfnai_weekly: pd.Series) -> pd.Series:
    """El valor del mes M (marcado en las semanas de M) solo es conocido desde el primer
    viernes >= día 25 de M+1."""
    s = cfnai_weekly.dropna()
    monthly = s.groupby(s.index.to_period('M')).first()
    rel = {}
    for per, v in monthly.items():
        nxt = (per + 1).to_timestamp()
        d = nxt + pd.Timedelta(days=24)                  # día 25 de M+1
        d = d + pd.Timedelta(days=(4 - d.weekday()) % 7)  # primer viernes >= esa fecha
        rel[d] = v
    rel = pd.Series(rel).sort_index()
    return rel.reindex(cfnai_weekly.index.union(rel.index)).ffill().reindex(cfnai_weekly.index)


def lagged_inputs(data: dict) -> dict:
    d = {k: v.copy() for k, v in data.items()}
    mw = d['macro_weekly']
    mw['NetLiq'] = mw['NetLiq'].shift(1)
    mw['CFNAI'] = cfnai_point_in_time(mw['CFNAI'])
    d['macro_weekly'] = mw
    return d


def build_prices_daily() -> pd.DataFrame:
    frames = {}
    for t in TICKERS_NO_SPY + ['SPY', 'DX-Y.NYB']:
        o = load_daily_ohlcv(t, RAW)
        if o is not None:
            frames[t] = o['close']
    out = pd.DataFrame(frames)
    out.index.name = 'date'
    return out


def main():
    data = load_macro_inputs()
    stored_m = pd.read_parquet(PROC / 'macro_history.parquet')
    stored_m = stored_m[stored_m['mode'] == 'A']

    m0 = simulate_history(data, mode='A')
    m0['mode'] = 'A'
    common = m0.index.intersection(stored_m.index)
    agree = (m0.loc[common, 'regime'] == stored_m.loc[common, 'regime']).mean()
    sc = (m0.loc[common, 'macro_score'] - stored_m.loc[common, 'macro_score']).abs().max()
    print(f"[8.2] Régimen sin desfase vs guardado: coincidencia {agree:.4%} en {len(common)} semanas; "
          f"máx |Δ MacroScore| = {sc}")
    if agree < 0.999:
        diff = common[m0.loc[common, 'regime'].values != stored_m.loc[common, 'regime'].values]
        print("  Semanas distintas:", list(diff[:20]))
        raise SystemExit("El recálculo sin desfase no reproduce el régimen guardado: se para (§8.2).")

    mL = simulate_history(lagged_inputs(data), mode='A')
    mL['mode'] = 'A'
    chg = (mL.loc[common, 'regime'] != m0.loc[common, 'regime']).mean()
    print(f"Régimen con desfase distinto del sin desfase en {chg:.2%} de las semanas")

    prices_daily = build_prices_daily()
    md = data['macro_daily']
    out = {}
    for name, mh in [('nolag', m0), ('lag', mL)]:
        rot, _ = simulate_rotation_history(prices_daily=prices_daily, macro_history=mh,
                                           macro_daily=md, raw_dir=RAW, mode='A')
        rot = rot.reset_index()
        rot = rot[rot['ticker'].isin(SECTORS)][['date', 'ticker', 'regime', 'fit', 'signal', 'rot_score']]
        out[name] = rot

    # Comprobación: rotación sin desfase vs guardada
    stored_r = pd.read_parquet(PROC / 'rotation_history.parquet')
    stored_r = stored_r[(stored_r['mode'] == 'A') & stored_r['ticker'].isin(SECTORS)].reset_index()
    j = stored_r.merge(out['nolag'], on=['date', 'ticker'], suffixes=('_s', '_n'))
    j = j[j['date'] <= '2026-11-06']
    for c in ['fit', 'signal']:
        a = (j[f'{c}_s'].fillna('NA').astype(str) == j[f'{c}_n'].fillna('NA').astype(str)).mean()
        print(f"Rotación sin desfase vs guardada — {c}: coincidencia {a:.2%} (n={len(j)})")

    sig = out['lag'].merge(out['nolag'], on=['date', 'ticker'], suffixes=('', '_nolag'))
    sig.to_parquet(WORK / 'signals_weekly.parquet')

    # Precios diarios ajustados (apertura ajustada = Open × AdjClose / Close)
    px = {}
    for t in SECTORS + ['SPY']:
        df = pd.read_parquet(RAW / f"yahoo_{t}.parquet")
        df.index = pd.to_datetime(df.index).normalize()
        f = df['Adj Close'] / df['Close']
        px[(t, 'open')] = df['Open'] * f
        px[(t, 'close')] = df['Adj Close']
    px = pd.DataFrame(px)
    px.columns = pd.MultiIndex.from_tuples(px.columns)
    px.to_parquet(WORK / 'prices_adj.parquet')
    print("Guardado:", WORK / 'signals_weekly.parquet', WORK / 'prices_adj.parquet')


if __name__ == '__main__':
    main()
