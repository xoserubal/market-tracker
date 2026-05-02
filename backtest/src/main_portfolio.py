"""
Entrega 6B — Portfolio Simulado: ROT. TEMPRANA como Estrategia.
Runs 24 simulations, saves 3 parquets, prints sanity checks.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from portfolio.strategies import run_all_simulations, PERIODS

BASE = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed')
RPT  = os.path.join(os.path.dirname(__file__), '..', 'reports')


def main():
    print("=== ENTREGA 6B — Portfolio Simulado ROT. TEMPRANA ===\n")

    # Load data
    print("Cargando datos...")
    rotation_history = pd.read_parquet(os.path.join(BASE, 'rotation_history.parquet'))
    macro_history    = pd.read_parquet(os.path.join(BASE, 'macro_history.parquet'))
    prices_daily     = pd.read_parquet(os.path.join(BASE, 'prices_daily.parquet'))

    # Load confluence_score if available (for full_system COMPRA filter)
    conf_path = os.path.join(BASE, 'confluence_history.parquet')
    confluence_series = None
    if os.path.exists(conf_path):
        ch = pd.read_parquet(conf_path)
        # Use Mode A confluence score
        ch_a = ch[ch['mode'] == 'A'].set_index('date')['confluence_score'] \
               if 'mode' in ch.columns and 'confluence_score' in ch.columns else None
        if ch_a is not None:
            confluence_series = ch_a.sort_index()

    print(f"  rotation_history: {rotation_history.shape}")
    print(f"  macro_history:    {macro_history.shape}")
    print(f"  prices_daily:     {prices_daily.shape}")
    print(f"  confluence:       {'loaded' if confluence_series is not None else 'not available'}")
    print()

    # Run all 24 simulations
    print("Ejecutando 24 simulaciones (8 combinaciones x 3 periodos)...")
    equity_df, trades_df, metrics_df = run_all_simulations(
        rotation_history, macro_history, prices_daily, confluence_series
    )
    print()

    # ---- Sanity checks ----
    print("=== SANITY CHECKS ===")
    spy_metrics = metrics_df[metrics_df['strategy'] == 'spy_benchmark']

    # 1. SPY CAGR should be 8-11% for full period
    spy_full = spy_metrics[spy_metrics['period'] == '2005-2026']
    if not spy_full.empty:
        spy_cagr = float(spy_full.iloc[0]['cagr'])
        flag = " OK" if 0.08 <= spy_cagr <= 0.11 else " *** FUERA DE RANGO (esperado 8-11%) ***"
        print(f"  SPY CAGR 2005-2026: {spy_cagr*100:.2f}%{flag}")
    else:
        print("  SPY CAGR: no disponible")

    # 2. All equity values positive
    if not equity_df.empty:
        min_equity = equity_df['equity'].min()
        flag = " OK" if min_equity > 0 else " *** EQUITY NEGATIVA — BUG ***"
        print(f"  Min equity across all sims: ${min_equity:,.0f}{flag}")
    else:
        print("  Equity: DataFrame vacío")

    # 3. N trades for ROT. TEMPRANA pure Mode A should be <= 80
    rot_a_metrics = metrics_df[
        (metrics_df['strategy'] == 'rot_temprana_pure')
        & (metrics_df['mode'] == 'A')
        & (metrics_df['period'] == '2005-2026')
        & (metrics_df['include_btc'] == True)
    ]
    if not rot_a_metrics.empty:
        n_trades = int(rot_a_metrics.iloc[0]['n_trades'])
        flag = " OK" if n_trades <= 80 else f" *** ALTO (esperado <=80) ***"
        print(f"  ROT. TEMPRANA pura Modo A trades: {n_trades}{flag}")

    # 4. Alpha direction check (ROT. TEMPRANA vs SPY, Mode A, no BTC)
    rot_a_nobtc = metrics_df[
        (metrics_df['strategy'] == 'rot_temprana_pure')
        & (metrics_df['mode'] == 'A')
        & (metrics_df['period'] == '2005-2026')
        & (metrics_df['include_btc'] == False)
    ]
    if not rot_a_nobtc.empty:
        alpha = float(rot_a_nobtc.iloc[0]['alpha_annualized'])
        cagr_s = float(rot_a_nobtc.iloc[0]['cagr'])
        print(f"  ROT. TEMPRANA pura Modo A (sin BTC): CAGR={cagr_s*100:.2f}%  alpha={alpha*100:.2f}%")
        if alpha < 0:
            print("    *** NOTA: alpha negativo. Divergencia vs Entrega 4 t-stat=2.77. Ver reporte. ***")

    print()

    # ---- Summary table ----
    print("=== TABLA RESUMEN (8 combinaciones principales — período completo) ===")
    main_metrics = metrics_df[
        (metrics_df['period'] == '2005-2026')
        & (metrics_df['strategy'] != 'spy_benchmark')
    ].sort_values(['strategy', 'mode', 'include_btc'], ascending=[True, True, False])

    cols = ['strategy', 'mode', 'include_btc', 'cagr', 'sharpe', 'max_drawdown',
            'alpha_annualized', 'n_trades']
    if not main_metrics.empty:
        for _, row in main_metrics[cols].iterrows():
            btc = 'con BTC' if row['include_btc'] else 'sin BTC'
            print(f"  {row['strategy'][:20]:<20} Modo {row['mode']} {btc:<7} | "
                  f"CAGR={row['cagr']*100:5.2f}%  Sharpe={row['sharpe']:5.2f}  "
                  f"MaxDD={row['max_drawdown']*100:5.1f}%  "
                  f"alpha={row['alpha_annualized']*100:5.2f}%  "
                  f"N={int(row['n_trades']) if not pd.isna(row['n_trades']) else 'N/A'}")
    if not spy_full.empty:
        sr = spy_full.iloc[0]
        print(f"  {'SPY buy-and-hold':<20}              {'':7} | "
              f"CAGR={sr['cagr']*100:5.2f}%  Sharpe={sr['sharpe']:5.2f}  "
              f"MaxDD={sr['max_drawdown']*100:5.1f}%")
    print()

    # Save parquets
    print("Guardando parquets...")
    os.makedirs(BASE, exist_ok=True)

    equity_df.to_parquet(os.path.join(BASE, 'portfolio_rot_temprana_history.parquet'), index=False)
    print(f"  portfolio_rot_temprana_history.parquet ({len(equity_df)} rows)")

    if not trades_df.empty:
        trades_df.to_parquet(os.path.join(BASE, 'portfolio_trades.parquet'), index=False)
        print(f"  portfolio_trades.parquet ({len(trades_df)} rows)")
    else:
        pd.DataFrame().to_parquet(os.path.join(BASE, 'portfolio_trades.parquet'), index=False)
        print("  portfolio_trades.parquet (vacío)")

    metrics_df.to_parquet(os.path.join(BASE, 'portfolio_metrics.parquet'), index=False)
    print(f"  portfolio_metrics.parquet ({len(metrics_df)} rows)")
    print()
    print("Simulación completa.")

    return equity_df, trades_df, metrics_df


if __name__ == '__main__':
    main()
