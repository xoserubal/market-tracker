"""
Entrega 5 — Detector de Confluencia Temprana.
Corre simulación completa, tests de validación y guarda 3 parquets.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from confluence.simulator   import simulate_confluence_history
from confluence.validation  import (run_lead_time_analysis, run_basket_alpha_analysis,
                                    run_false_positive_analysis)

BASE = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed')
RPT  = os.path.join(os.path.dirname(__file__), '..', 'reports')


def main():
    print("=== ENTREGA 5 — Detector de Confluencia Temprana ===\n")

    # Load data
    print("Cargando datos...")
    macro_history   = pd.read_parquet(os.path.join(BASE, 'macro_history.parquet'))
    cluster_health  = pd.read_parquet(os.path.join(BASE, 'cluster_health_history.parquet'))
    prices_daily    = pd.read_parquet(os.path.join(BASE, 'prices_daily.parquet'))
    recession_basket = pd.read_parquet(os.path.join(BASE, 'recession_basket_validation.parquet'))

    print(f"  macro_history:    {macro_history.shape}")
    print(f"  cluster_health:   {cluster_health.shape}")
    print(f"  prices_daily:     {prices_daily.shape}")
    print(f"  recession_basket: {recession_basket.shape}")
    print()

    # Simulate
    print("Ejecutando simulación...")
    history_df, alerts_df = simulate_confluence_history(
        macro_history, cluster_health, prices_daily, modes=('A', 'B')
    )
    print(f"  history rows:     {len(history_df)}")
    print(f"  alerts emitted:   {len(alerts_df)}")
    if not alerts_df.empty:
        print(f"  STRUCTURAL:       {(alerts_df['alert_type']=='STRUCTURAL').sum()}")
        print(f"  TACTICAL:         {(alerts_df['alert_type']=='TACTICAL').sum()}")
    print()

    # ---- Sanity checks ----
    print("=== SANITY CHECKS ===")
    for mode in ['A', 'B']:
        h = history_df[history_df['mode'] == mode]
        structural_pct = h['structural_active'].mean() * 100
        print(f"  Modo {mode} — % tiempo en STRUCTURAL: {structural_pct:.1f}%  "
              f"(limite: <15%)")

    # 2008 check
    for mode in ['A', 'B']:
        struct = alerts_df[
            (alerts_df['alert_type'] == 'STRUCTURAL')
            & (alerts_df['mode'] == mode)
        ] if not alerts_df.empty else pd.DataFrame()
        alerts_2008 = struct[
            struct['date'].between('2008-01-01', '2008-08-31')
        ] if not struct.empty else pd.DataFrame()
        if not alerts_2008.empty:
            print(f"  Modo {mode} — STRUCTURAL en 2008 (ene-ago): SI "
                  f"({alerts_2008.iloc[0]['date'].date()})")
        else:
            print(f"  Modo {mode} — STRUCTURAL en 2008 (ene-ago): NO (objetivo fallido)")

    # Bull market check
    for mode in ['A', 'B']:
        h = history_df[history_df['mode'] == mode]
        bull_years = [2013, 2014, 2017, 2019, 2021]
        for yr in bull_years:
            h_yr = h[h['date'].dt.year == yr]
            if h_yr.empty:
                continue
            pct = h_yr['structural_active'].mean() * 100
            flag = " *** PROBLEMA ***" if pct > 20 else ""
            print(f"  Modo {mode} — {yr}: STRUCTURAL activo {pct:.1f}%{flag}")
    print()

    # ---- Validation ----
    print("=== TEST 1 — LEAD TIME ===")
    if not alerts_df.empty:
        lead_time_df = run_lead_time_analysis(recession_basket, alerts_df)
        sys_trans = lead_time_df[lead_time_df['event_type'] == 'system_transition']
        real_peaks = lead_time_df[lead_time_df['event_type'] == 'real_peak']
        covid = lead_time_df[lead_time_df['event_type'] == 'real_peak_informative']

        print("  Transiciones sistema (14 eventos):")
        n_detected = sys_trans['lead_time_days'].notna().sum()
        n_gt30 = (sys_trans['lead_time_days'] > 30).sum()
        mean_lt = sys_trans['lead_time_days'].dropna().mean()
        print(f"    Detectadas: {n_detected}/14  |  Lead > 30d: {n_gt30}/14  "
              f"|  Lead medio: {mean_lt:.0f}d")

        print("\n  Picos reales con precursores:")
        for _, r in real_peaks.iterrows():
            lt = f"{r['lead_time_days']:.0f}d" if pd.notna(r['lead_time_days']) else "NO DETECTADO"
            print(f"    {r['classification']} ({r['event_date'].date()}) Modo {r['mode']}: "
                  f"alert {r['alert_date'].date() if pd.notna(r['lead_time_days']) else '—'} | lead={lt}")

        print("\n  COVID 2020 (informativo — no criterio):")
        for _, r in covid.iterrows():
            lt = f"{r['lead_time_days']:.0f}d" if pd.notna(r['lead_time_days']) else "NO DETECTADO"
            print(f"    Modo {r['mode']}: {lt}")
    else:
        lead_time_df = pd.DataFrame()
        print("  Sin alertas emitidas")
    print()

    print("=== TEST 2 — ALPHA BASKET ===")
    if not alerts_df.empty:
        basket_df = run_basket_alpha_analysis(alerts_df, prices_daily)
        if not basket_df.empty:
            for h in ['4w', '13w', '26w']:
                col = f'basket_alpha_{h}'
                valid = basket_df[col].dropna()
                n = len(valid)
                mean_a = valid.mean() * 100 if n > 0 else float('nan')
                se = valid.std() / np.sqrt(n) if n > 1 else float('nan')
                t = mean_a / (se * 100) if se > 0 else float('nan')
                print(f"  {h}: N={n}  mean alpha={mean_a:.2f}%  t-stat={t:.2f}")
        else:
            basket_df = pd.DataFrame()
    else:
        basket_df = pd.DataFrame()
        print("  Sin alertas")
    print()

    print("=== TEST 3 — FALSOS POSITIVOS ===")
    if not alerts_df.empty:
        fp_result = run_false_positive_analysis(alerts_df, prices_daily)
        print(f"  Total STRUCTURAL: {fp_result['total']}")
        print(f"  True positives:   {fp_result['true_positives']}")
        print(f"  False positives:  {fp_result['false_positives']}")
        fp_rate = fp_result['fp_rate']
        if fp_rate is not None:
            flag = " *** POBRE ***" if fp_rate > 0.6 else (
                   " OK" if fp_rate < 0.4 else " aceptable")
            print(f"  FP rate:          {fp_rate*100:.1f}%{flag}")
        fp_detail = fp_result['detail']
    else:
        fp_detail = pd.DataFrame()
    print()

    # ---- Save parquets ----
    print("Guardando parquets...")
    os.makedirs(BASE, exist_ok=True)
    history_df.to_parquet(os.path.join(BASE, 'confluence_history.parquet'), index=False)
    print(f"  confluence_history.parquet   ({len(history_df)} rows)")

    if not alerts_df.empty:
        alerts_df.to_parquet(os.path.join(BASE, 'confluence_alerts.parquet'), index=False)
        print(f"  confluence_alerts.parquet    ({len(alerts_df)} rows)")
    else:
        pd.DataFrame().to_parquet(os.path.join(BASE, 'confluence_alerts.parquet'), index=False)
        print("  confluence_alerts.parquet    (vacio)")

    # Validation combined
    val_frames = []
    if not lead_time_df.empty:
        val_frames.append(lead_time_df.assign(test='lead_time'))
    if not basket_df.empty:
        val_frames.append(basket_df.assign(test='basket_alpha'))
    if not fp_detail.empty:
        val_frames.append(fp_detail.assign(test='false_positive'))
    if val_frames:
        val_df = pd.concat(val_frames, ignore_index=True)
        val_df.to_parquet(os.path.join(BASE, 'confluence_validation.parquet'), index=False)
        print(f"  confluence_validation.parquet ({len(val_df)} rows)")
    print()
    print("Simulacion completa.")
    return history_df, alerts_df, lead_time_df if not alerts_df.empty else pd.DataFrame()


if __name__ == '__main__':
    main()
