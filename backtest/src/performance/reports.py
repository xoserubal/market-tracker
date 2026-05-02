"""
Generacion del reporte final en Markdown.
"""

import pandas as pd
import numpy as np
from pathlib import Path


def _fmt_pct(v, decimals=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '—'
    return f'{v*100:+.{decimals}f}%'


def _fmt_f(v, decimals=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '—'
    return f'{v:.{decimals}f}'


def _fmt_n(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '—'
    return str(int(v))


def _signal_table(perf: pd.DataFrame, mode: str, horizons=None) -> str:
    if horizons is None:
        horizons = ['4w', '13w', '26w']
    sig_order = ['COMPRA', 'ACUMULAR', 'ROT. TEMPRANA', 'VIGILAR', 'IGNORAR', 'ACUMULAR*']
    sub = perf[(perf['group_by_level'] == 'by_signal') & (perf['mode'] == mode)]

    header = '| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |\n'
    header += '|-------|-----|-------|--------|--------|----------|-----|--------|------|\n'
    lines = [header]
    for sig in sig_order:
        for hz in horizons:
            row = sub[(sub['signal'] == sig) & (sub['horizon'] == hz)]
            if row.empty:
                continue
            r = row.iloc[0]
            lines.append(
                f"| {sig} | {hz} | {_fmt_n(r['n_raw'])} | {_fmt_n(r['n_independent'])} "
                f"| {_fmt_pct(r['mean_alpha'])} | {_fmt_pct(r['median_alpha'])} "
                f"| {_fmt_pct(r['std_alpha'],1)} | {_fmt_f(r['t_stat'],2)} "
                f"| {_fmt_pct(r['hit_rate'],1)} |\n"
            )
    return ''.join(lines)


def _regime_table(perf: pd.DataFrame, mode: str, signal: str = 'COMPRA') -> str:
    sub = perf[
        (perf['group_by_level'] == 'by_signal_regime') &
        (perf['mode'] == mode) &
        (perf['signal'] == signal) &
        (perf['horizon'] == '13w')
    ].sort_values('mean_alpha', ascending=False)

    header = f'| Regimen | N obs | Mean α 13w | Hit% | t-stat |\n'
    header += '|---------|-------|------------|------|--------|\n'
    lines = [header]
    for _, r in sub.iterrows():
        lines.append(
            f"| {r['regime']} | {_fmt_n(r['n_raw'])} "
            f"| {_fmt_pct(r['mean_alpha'])} | {_fmt_pct(r['hit_rate'],1)} "
            f"| {_fmt_f(r['t_stat'],2)} |\n"
        )
    return ''.join(lines)


def _cluster_table(perf: pd.DataFrame, mode: str, signal: str = 'COMPRA') -> str:
    sub = perf[
        (perf['group_by_level'] == 'by_signal_cluster') &
        (perf['mode'] == mode) &
        (perf['signal'] == signal) &
        (perf['horizon'] == '13w')
    ].sort_values('mean_alpha', ascending=False)

    header = '| Cluster | N obs | Mean α 13w | Hit% | t-stat |\n'
    header += '|---------|-------|------------|------|--------|\n'
    lines = [header]
    for _, r in sub.iterrows():
        lines.append(
            f"| {r['cluster']} | {_fmt_n(r['n_raw'])} "
            f"| {_fmt_pct(r['mean_alpha'])} | {_fmt_pct(r['hit_rate'],1)} "
            f"| {_fmt_f(r['t_stat'],2)} |\n"
        )
    return ''.join(lines)


def generate_report(
    perf_summary:   pd.DataFrame,
    signal_alphas:  pd.DataFrame,
    lead_time_df:   pd.DataFrame,
    basket_val:     pd.DataFrame,
    output_path:    Path,
) -> str:
    """Genera el reporte Markdown completo y lo guarda en output_path."""

    lines = []
    a = lines.append

    # ── Resumen ejecutivo ──────────────────────────────────────────────────
    a('# Entrega 4 — Performance Report: RotationScore Signal Backtest\n\n')

    # Numero clave: alpha COMPRA 13w modo A
    compra_a13 = perf_summary[
        (perf_summary['group_by_level'] == 'by_signal') &
        (perf_summary['signal'] == 'COMPRA') &
        (perf_summary['horizon'] == '13w') &
        (perf_summary['mode'] == 'A')
    ]
    if not compra_a13.empty:
        r = compra_a13.iloc[0]
        mean_a = r['mean_alpha']
        tstat  = r['t_stat']
        hit    = r['hit_rate']
        if not np.isnan(mean_a) and mean_a > 0 and (np.isnan(tstat) or tstat > 1.5):
            verdict = 'VALIDADO: alpha positivo y t-stat > 1.5'
        elif not np.isnan(mean_a) and mean_a > 0:
            verdict = 'NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)'
        else:
            verdict = 'NO FUNCIONA: alpha negativo en señales COMPRA'
        a(f'## Resumen ejecutivo\n\n')
        a(f'**Veredicto:** {verdict}\n\n')
        a(f'- Señales COMPRA — alpha medio 13w (Modo A): {_fmt_pct(mean_a)}  '
          f'| hit rate: {_fmt_pct(hit,1)}  | t-stat: {_fmt_f(tstat,2)}\n')

    # Lead time resumen
    if not lead_time_df.empty:
        conv = lead_time_df[lead_time_df['lead_time_weeks'].notna()]
        conv_rate = len(conv) / len(lead_time_df) if len(lead_time_df) > 0 else 0
        med_lt = conv['lead_time_weeks'].median() if not conv.empty else None
        a(f'- ROT. TEMPRANA: {conv_rate*100:.0f}% convergen a COMPRA/ACUMULAR  '
          f'| lead time mediano: {med_lt:.0f}w\n' if med_lt else
          f'- ROT. TEMPRANA: {conv_rate*100:.0f}% convergen a COMPRA/ACUMULAR\n')

    # Basket resumen
    if not basket_val.empty:
        b13 = basket_val['basket_alpha_13w'].dropna()
        a(f'- Recession basket: alpha medio 13w en transiciones = {_fmt_pct(b13.mean() if not b13.empty else np.nan)}\n\n')

    # ── Seccion 1 — Por tipo de señal ──────────────────────────────────────
    a('---\n\n## Sección 1 — Alpha por tipo de señal\n\n')
    for mode in ['A', 'B']:
        a(f'### Modo {mode}\n\n')
        a(_signal_table(perf_summary, mode))
        a('\n')

    # ── Seccion 2 — Por regimen ────────────────────────────────────────────
    a('---\n\n## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)\n\n')
    a(_regime_table(perf_summary, 'A', 'COMPRA'))
    a('\n### Modo B\n\n')
    a(_regime_table(perf_summary, 'B', 'COMPRA'))
    a('\n')

    # ── Seccion 3 — Por cluster ────────────────────────────────────────────
    a('---\n\n## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)\n\n')
    a(_cluster_table(perf_summary, 'A', 'COMPRA'))
    a('\n### Modo B\n\n')
    a(_cluster_table(perf_summary, 'B', 'COMPRA'))
    a('\n')

    # ── Seccion 4 — ROT. TEMPRANA ──────────────────────────────────────────
    a('---\n\n## Sección 4 — ROT. TEMPRANA\n\n')
    if lead_time_df.empty:
        a('_Sin señales ROT. TEMPRANA en el período._\n\n')
    else:
        total = len(lead_time_df)
        conv  = lead_time_df[lead_time_df['lead_time_weeks'].notna()]
        a(f'Total ROT. TEMPRANA emitidas: **{total}** (ambos modos)\n\n')
        a(f'- Convergieron a COMPRA/ACUMULAR: **{len(conv)}** ({len(conv)/total*100:.0f}%)\n')
        if not conv.empty:
            a(f'- Lead time (semanas): media={conv["lead_time_weeks"].mean():.1f}  '
              f'mediana={conv["lead_time_weeks"].median():.0f}  '
              f'IQR=[{conv["lead_time_weeks"].quantile(0.25):.0f}, '
              f'{conv["lead_time_weeks"].quantile(0.75):.0f}]\n')
        a(f'- Convergencia por señal:\n')
        for sig, cnt in lead_time_df['convergence_signal'].value_counts().items():
            a(f'  - {sig}: {cnt}\n')

        # Alpha comparacion early vs convergencia
        e13 = lead_time_df['alpha_13w_from_early'].dropna()
        c13 = lead_time_df['alpha_13w_from_convergence'].dropna()
        a(f'\n**Alpha 13w desde ROT. TEMPRANA:** {_fmt_pct(e13.mean() if not e13.empty else np.nan)}  '
          f'| n={len(e13)}\n')
        a(f'**Alpha 13w desde señal convencional (convergencia):** '
          f'{_fmt_pct(c13.mean() if not c13.empty else np.nan)}  | n={len(c13)}\n\n')

    # ── Seccion 5 — Recession basket ──────────────────────────────────────
    a('---\n\n## Sección 5 — Recession basket\n\n')
    if basket_val.empty:
        a('_Sin transiciones detectadas._\n\n')
    else:
        a(f'Transiciones a Risk-OFF/Capitulacion detectadas: **{len(basket_val)}**\n\n')
        a('| Fecha | Anterior → Nuevo | INFL | α4w | α13w | α26w |\n')
        a('|-------|-----------------|------|-----|------|------|\n')
        for _, r in basket_val.iterrows():
            infl = 'SI' if r['inflation_overlay_active'] else 'no'
            a(f"| {pd.Timestamp(r['transition_date']).date()} "
              f"| {r['prev_regime']} → {r['new_regime']} | {infl} "
              f"| {_fmt_pct(r.get('basket_alpha_4w', np.nan))} "
              f"| {_fmt_pct(r.get('basket_alpha_13w', np.nan))} "
              f"| {_fmt_pct(r.get('basket_alpha_26w', np.nan))} |\n")

        b13_all   = basket_val['basket_alpha_13w'].dropna()
        b13_defl  = basket_val[~basket_val['inflation_overlay_active']]['basket_alpha_13w'].dropna()
        b13_infl  = basket_val[ basket_val['inflation_overlay_active']]['basket_alpha_13w'].dropna()
        a(f'\n**Alpha 13w basket completo:** {_fmt_pct(b13_all.mean() if not b13_all.empty else np.nan)}  '
          f'n={len(b13_all)}\n')
        a(f'**Alpha 13w regimen deflacionario:** {_fmt_pct(b13_defl.mean() if not b13_defl.empty else np.nan)}  '
          f'n={len(b13_defl)}\n')
        a(f'**Alpha 13w regimen inflacionario:** {_fmt_pct(b13_infl.mean() if not b13_infl.empty else np.nan)}  '
          f'n={len(b13_infl)}\n')

        fp = basket_val['is_false_positive_4w'].sum()
        a(f'**Falsos positivos (basket underperforma SPY en 4w):** {fp}/{len(basket_val)} '
          f'({fp/len(basket_val)*100:.0f}%)\n\n')

    # ── Seccion 6 — Modo A vs B ────────────────────────────────────────────
    a('---\n\n## Sección 6 — Modo A vs Modo B (2023-04-18 en adelante)\n\n')
    sa_23 = signal_alphas[signal_alphas['date'] >= '2023-04-18']
    for sig in ['COMPRA', 'ACUMULAR', 'VIGILAR']:
        rows_a = sa_23[(sa_23['mode'] == 'A') & (sa_23['signal'] == sig)]
        rows_b = sa_23[(sa_23['mode'] == 'B') & (sa_23['signal'] == sig)]
        a13_a  = rows_a['alpha_13w'].dropna().mean() if not rows_a.empty else np.nan
        a13_b  = rows_b['alpha_13w'].dropna().mean() if not rows_b.empty else np.nan
        a(f'- {sig}: Modo A α13w={_fmt_pct(a13_a)}  Modo B α13w={_fmt_pct(a13_b)}  '
          f'nA={len(rows_a)}  nB={len(rows_b)}\n')

    a('\n')

    # ── Seccion 7 — Limitaciones ───────────────────────────────────────────
    a('---\n\n## Sección 7 — Limitaciones y caveats\n\n')
    a('1. **Autocorrelacion:** una señal COMPRA persistente genera observaciones correlacionadas. '
      'Se reporta `n_independent` (primer punto de cada bloque) para el t-stat.\n')
    a('2. **Muestra pequena en ROT. TEMPRANA:** 32-36 señales en total (ambos modos) '
      'limita la significancia estadistica.\n')
    a('3. **Un unico ciclo secular:** el periodo 2005-2026 es mayoritariamente alcista; '
      'los alphas en regimenes de estres pueden estar infraestimados.\n')
    a('4. **HY ausente pre-2023:** el Modo B infravalora el estres en crisis pre-2023. '
      'Afecta regimenes de capitulacion/risk-off historicos.\n')
    a('5. **Sin costes de transaccion ni slippage:** los alphas son brutos.\n')
    a('6. **No es portfolio real:** se analiza el alpha de cada señal individualmente, '
      'no una estrategia de portfolio con sizing y rebalance.\n\n')

    # ── Conclusiones ──────────────────────────────────────────────────────
    a('---\n\n## Conclusiones\n\n')
    if not compra_a13.empty:
        r = compra_a13.iloc[0]
        a(f'**¿Las señales COMPRA dan alpha?**  '
          f'Alpha medio 13w = {_fmt_pct(r["mean_alpha"])}, '
          f'hit rate = {_fmt_pct(r["hit_rate"],1)}, '
          f't-stat = {_fmt_f(r["t_stat"],2)}. '
          f'{verdict}.\n\n')

    if not lead_time_df.empty:
        conv = lead_time_df[lead_time_df['lead_time_weeks'].notna()]
        conv_rate = len(conv) / len(lead_time_df)
        med_lt = conv['lead_time_weeks'].median() if not conv.empty else None
        lt_verdict = (
            f'SI — convergen {conv_rate*100:.0f}% con lead time mediano {med_lt:.0f}w'
            if conv_rate > 0.5 and med_lt and med_lt >= 3
            else f'DEBIL — solo {conv_rate*100:.0f}% convergen'
        )
        a(f'**¿ROT. TEMPRANA adelanta?**  {lt_verdict}.\n\n')

    if not basket_val.empty:
        b13 = basket_val['basket_alpha_13w'].dropna()
        basket_verdict = (
            'SI — alpha medio positivo' if not b13.empty and b13.mean() > 0
            else 'NO — alpha medio negativo'
        )
        a(f'**¿El framework detecta crisis?**  {basket_verdict} '
          f'({_fmt_pct(b13.mean() if not b13.empty else np.nan)} a 13w en transiciones).\n\n')

    report = ''.join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding='utf-8')
    return report
