"""
Entrega 4 -- Pipeline completo de backtest de performance.

Orden de ejecucion:
  1. Carga datos (prices_daily, rotation_history, macro_history)
  2. Forward returns todos los tickers
  3. Alpha vs SPY
  4. Join signals + alphas -> signal_alphas
  5. Performance summary (3 niveles de agregacion)
  6. Lead times (ROT. TEMPRANA)
  7. Recession basket validation
  8. Sanity checks S12
  9. Guardar 4 parquets de output
 10. Generar reporte Markdown
"""

import sys
from pathlib import Path

# Permite ejecutar desde cualquier directorio
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src.performance.forward_returns import compute_forward_returns
from src.performance.alpha import compute_alpha
from src.performance.aggregation import (
    join_signals_with_alphas,
    build_performance_summary,
)
from src.performance.lead_time import compute_all_lead_times
from src.performance.recession_basket import build_recession_basket_validation
from src.performance.reports import generate_report


DATA_DIR   = ROOT / 'data' / 'processed'
OUTPUT_DIR = ROOT / 'data' / 'processed'
REPORT_DIR = ROOT / 'reports'


# -- S12 Sanity checks ---------------------------------------------------------

def sanity_checks(
    signal_alphas: pd.DataFrame,
    rotation_history: pd.DataFrame,
    alphas: pd.DataFrame,
) -> bool:
    print('\n-- S12 Sanity Checks --------------------------------------------')
    ok = True

    # 1. SPY alpha = 0 (+/-0.1%)
    # SPY no esta en rotation_history, verificar directamente en alphas
    spy_alpha = (
        alphas.xs('SPY', level='ticker')['alpha_13w'].dropna()
        if 'SPY' in alphas.index.get_level_values('ticker') else pd.Series(dtype=float)
    )
    mean_spy = float(spy_alpha.mean()) if not spy_alpha.empty else np.nan
    check1   = abs(mean_spy) < 1e-9 if not np.isnan(mean_spy) else False
    status1  = 'OK' if check1 else 'FALLO'
    print(f'  [S12.1] SPY alpha_13w medio (en alphas): {mean_spy:.2e}  -> {status1}')
    if not check1:
        ok = False

    # 2. IGNORAR alpha ~= 0 (su alpha deberia ser ~= mercado = SPY, ~= 0)
    ignorar_rows = signal_alphas[signal_alphas['signal'].isna()]
    vig_rows     = signal_alphas[signal_alphas['signal'] == 'VIGILAR']
    a13_ig  = ignorar_rows['alpha_13w'].dropna().mean() if not ignorar_rows.empty else np.nan
    a13_vig = vig_rows['alpha_13w'].dropna().mean()     if not vig_rows.empty     else np.nan
    print(f'  [S12.2] IGNORAR (NaN) alpha_13w medio: {a13_ig:.4%}  VIGILAR: {a13_vig:.4%}')

    # 3. n_observations en signal_alphas coincide con rotation_history
    n_sa = len(signal_alphas)
    n_rh = len(rotation_history)
    check3 = (n_sa == n_rh)
    status3 = 'OK' if check3 else f'FALLO (signal_alphas={n_sa}, rh={n_rh})'
    print(f'  [S12.3] N filas signal_alphas={n_sa}  rotation_history={n_rh}  -> {status3}')
    if not check3:
        ok = False

    # 4. Distribucion COMPRA en el tiempo (conteo por ano)
    compra = signal_alphas[signal_alphas['signal'] == 'COMPRA'].copy()
    if not compra.empty:
        compra['year'] = pd.to_datetime(compra['date']).dt.year
        annual = compra.groupby('year').size()
        print(f'  [S12.4] COMPRA por ano (modo A+B):')
        for y, cnt in annual.items():
            print(f'           {y}: {cnt}')

    # 5. COMPRA alpha_13w positivo (senal principal del backtest)
    compra_a = compra[compra['mode'] == 'A']['alpha_13w'].dropna()
    mean_compra = compra_a.mean() if not compra_a.empty else np.nan
    print(f'  [S12.5] COMPRA Modo A alpha_13w medio: {mean_compra:.4%}  n={len(compra_a)}')

    print('-----------------------------------------------------------------')
    return ok


# -- Pipeline principal --------------------------------------------------------

def main():
    print('=== Entrega 4 -- Backtest Performance Pipeline ===\n')

    # -- Paso 1: Cargar datos ---------------------------------------------------
    print('[1/7] Cargando datos...')
    prices_daily    = pd.read_parquet(DATA_DIR / 'prices_daily.parquet')
    rotation_history = pd.read_parquet(DATA_DIR / 'rotation_history.parquet')
    macro_history   = pd.read_parquet(DATA_DIR / 'macro_history.parquet')

    print(f'  prices_daily:     {prices_daily.shape}  '
          f'{prices_daily.index[0].date()} to {prices_daily.index[-1].date()}')
    print(f'  rotation_history: {rotation_history.shape}  '
          f'{rotation_history.index[0].date()} to {rotation_history.index[-1].date()}')
    print(f'  macro_history:    {macro_history.shape}')

    # -- Paso 2: Forward returns -----------------------------------------------
    print('\n[2/7] Calculando forward returns...')
    fwd_returns = compute_forward_returns(prices_daily)
    counts = fwd_returns.notna().sum()
    print(f'  MultiIndex size: {len(fwd_returns):,}  '
          f'ret_fwd_4w={counts.get("ret_fwd_4w",0):,}  '
          f'ret_fwd_13w={counts.get("ret_fwd_13w",0):,}  '
          f'ret_fwd_26w={counts.get("ret_fwd_26w",0):,}')

    # -- Paso 3: Alpha vs SPY --------------------------------------------------
    print('\n[3/7] Calculando alpha vs SPY...')
    alphas = compute_alpha(fwd_returns)
    print(f'  alpha_4w  notna: {alphas["alpha_4w"].notna().sum():,}')
    print(f'  alpha_13w notna: {alphas["alpha_13w"].notna().sum():,}')
    print(f'  alpha_26w notna: {alphas["alpha_26w"].notna().sum():,}')

    # spy_fwd para recession basket (DataFrame indexado por fecha con ret_fwd_Nw)
    spy_fwd = (
        alphas.xs('SPY', level='ticker')[['ret_fwd_4w', 'ret_fwd_13w', 'ret_fwd_26w']]
        if 'SPY' in alphas.index.get_level_values('ticker') else pd.DataFrame()
    )

    # -- Paso 4: Join signals + alphas -----------------------------------------
    print('\n[4/7] Uniendo senales con alphas...')
    signal_alphas = join_signals_with_alphas(rotation_history, alphas)
    print(f'  signal_alphas shape: {signal_alphas.shape}')
    print(f'  columnas: {[c for c in signal_alphas.columns if "alpha" in c]}')

    # -- Paso 5: Sanity checks -------------------------------------------------
    checks_ok = sanity_checks(signal_alphas, rotation_history, alphas)
    if not checks_ok:
        print('\n!SANITY CHECKS FALLARON! Deteniendo antes de generar outputs.')
        sys.exit(1)

    # -- Paso 6: Performance summary -------------------------------------------
    print('\n[5/7] Calculando performance summary...')
    perf_summary = build_performance_summary(signal_alphas)
    print(f'  perf_summary shape: {perf_summary.shape}')
    print(f'  group_by_level: {perf_summary["group_by_level"].value_counts().to_dict()}')

    # Preview key metric: COMPRA 13w Modo A
    compra_a13 = perf_summary[
        (perf_summary['group_by_level'] == 'by_signal') &
        (perf_summary['signal'] == 'COMPRA') &
        (perf_summary['horizon'] == '13w') &
        (perf_summary['mode'] == 'A')
    ]
    if not compra_a13.empty:
        r = compra_a13.iloc[0]
        print(f'\n  *** COMPRA Modo A alpha13w: {r["mean_alpha"]*100:+.2f}%  '
              f'hit={r["hit_rate"]*100:.1f}%  t={r["t_stat"]:.2f}  '
              f'n_raw={int(r["n_raw"])}  n_ind={int(r["n_independent"])} ***')

    # -- Paso 7: Lead times ----------------------------------------------------
    print('\n[6/7] Calculando lead times (ROT. TEMPRANA)...')
    # alphas tiene MultiIndex (date, ticker) unico -- correcto para lead_time lookup
    lead_time_df = compute_all_lead_times(rotation_history, alpha_df=alphas)
    if not lead_time_df.empty:
        conv = lead_time_df[lead_time_df['lead_time_weeks'].notna()]
        print(f'  Total ROT. TEMPRANA: {len(lead_time_df)}  '
              f'convergencia: {len(conv)} ({len(conv)/len(lead_time_df)*100:.0f}%)')
        if not conv.empty:
            print(f'  Lead time mediano: {conv["lead_time_weeks"].median():.0f}w  '
                  f'media: {conv["lead_time_weeks"].mean():.1f}w')
    else:
        print('  (ninguna ROT. TEMPRANA encontrada)')

    # -- Paso 8: Recession basket ----------------------------------------------
    print('\n[7/7] Calculando recession basket validation...')
    basket_val = build_recession_basket_validation(macro_history, prices_daily, spy_fwd)
    print(f'  Transiciones detectadas: {len(basket_val)}')
    if not basket_val.empty:
        b13 = basket_val['basket_alpha_13w'].dropna()
        print(f'  Basket alpha 13w: media={b13.mean()*100:+.2f}%  n={len(b13)}')
        fp  = basket_val['is_false_positive_4w'].sum()
        print(f'  Falsos positivos 4w: {fp}/{len(basket_val)}')

    # -- Guardar outputs -------------------------------------------------------
    print('\n[Outputs] Guardando parquets...')
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    perf_summary.to_parquet(OUTPUT_DIR / 'performance_summary.parquet', index=False)
    print(f'  performance_summary.parquet  ({len(perf_summary)} filas)')

    signal_alphas.to_parquet(OUTPUT_DIR / 'signal_alphas.parquet', index=False)
    print(f'  signal_alphas.parquet        ({len(signal_alphas)} filas)')

    if not lead_time_df.empty:
        lead_time_df.to_parquet(OUTPUT_DIR / 'lead_time_analysis.parquet', index=False)
        print(f'  lead_time_analysis.parquet   ({len(lead_time_df)} filas)')

    if not basket_val.empty:
        basket_val.to_parquet(OUTPUT_DIR / 'recession_basket_validation.parquet', index=False)
        print(f'  recession_basket_validation.parquet ({len(basket_val)} filas)')

    # -- Generar reporte Markdown ----------------------------------------------
    print('\n[Report] Generando Markdown...')
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / 'entrega_4_performance_report.md'
    generate_report(
        perf_summary   = perf_summary,
        signal_alphas  = signal_alphas,
        lead_time_df   = lead_time_df   if not lead_time_df.empty else pd.DataFrame(),
        basket_val     = basket_val     if not basket_val.empty else pd.DataFrame(),
        output_path    = report_path,
    )
    print(f'  Reporte guardado en: {report_path}')

    print('\n=== Pipeline completado con exito ===')


if __name__ == '__main__':
    main()
