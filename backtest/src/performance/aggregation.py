"""
Agrega alphas por (señal, regimen, cluster, horizonte, modo).

Nota sobre independencia de observaciones:
  Las señales persistentes generan multiples filas correlacionadas para el mismo ticker.
  Se reporta n_raw (todas) y n_independent (solo la primera fila de cada bloque
  continuo de la misma señal para el mismo ticker+mode). El t-stat usa n_independent.
"""

import pandas as pd
import numpy as np
from scipy import stats


def _n_independent(df: pd.DataFrame) -> int:
    """
    Cuenta señales independientes: primer punto de cada bloque continuo
    de (ticker, mode, signal) sin interrupcion.
    """
    if df.empty:
        return 0
    # Ordenar por ticker, mode, date
    s = df.sort_values(['ticker', 'mode', 'date'] if 'date' in df.columns
                       else ['ticker', 'mode'])
    # Detectar cambios en la señal
    key = s['ticker'].astype(str) + '|' + s['mode'].astype(str)
    sig = s['signal'].fillna('')
    changed = (key != key.shift(1)) | (sig != sig.shift(1))
    return int(changed.sum())


def compute_group_stats(df: pd.DataFrame, alpha_col: str) -> dict:
    """
    Estadisticas de alpha para un grupo de observaciones.

    Args:
        df:         DataFrame con columna alpha_col y columnas ticker, mode, signal.
        alpha_col:  nombre de la columna de alpha (p.ej. 'alpha_13w').

    Returns dict con:
      n_raw, n_independent, mean_alpha, median_alpha, std_alpha,
      se_alpha, t_stat, hit_rate, hit_rate_se,
      percentile_25, percentile_75, min_alpha, max_alpha
    """
    vals = df[alpha_col].dropna()
    n_raw = len(vals)
    n_ind = _n_independent(df[df[alpha_col].notna()])

    if n_raw == 0:
        return {
            'n_raw': 0, 'n_independent': 0,
            'mean_alpha': np.nan, 'median_alpha': np.nan,
            'std_alpha': np.nan, 'se_alpha': np.nan, 't_stat': np.nan,
            'hit_rate': np.nan, 'hit_rate_se': np.nan,
            'percentile_25': np.nan, 'percentile_75': np.nan,
            'min_alpha': np.nan, 'max_alpha': np.nan,
        }

    v = vals.values
    mean   = float(np.mean(v))
    median = float(np.median(v))
    std    = float(np.std(v, ddof=1)) if n_raw > 1 else np.nan
    se     = std / np.sqrt(n_ind) if (n_ind > 0 and not np.isnan(std)) else np.nan
    t_stat = mean / se if (se and se > 0) else np.nan
    hit    = float(np.mean(v > 0))
    hit_se = float(np.sqrt(hit * (1 - hit) / n_raw)) if n_raw > 0 else np.nan

    return {
        'n_raw':        n_raw,
        'n_independent': n_ind,
        'mean_alpha':   mean,
        'median_alpha': median,
        'std_alpha':    std,
        'se_alpha':     se,
        't_stat':       t_stat,
        'hit_rate':     hit,
        'hit_rate_se':  hit_se,
        'percentile_25': float(np.percentile(v, 25)),
        'percentile_75': float(np.percentile(v, 75)),
        'min_alpha':    float(np.min(v)),
        'max_alpha':    float(np.max(v)),
    }


def join_signals_with_alphas(
    rotation_history: pd.DataFrame,
    alphas: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge rotation_history con alphas por (date, ticker, mode).

    rotation_history: indexed by date, columnas incluyen ticker, mode, signal, regime, cluster.
    alphas:           MultiIndex (date, ticker), columnas alpha_4w, alpha_13w, alpha_26w.

    Returns DataFrame con una fila por señal con alphas adjuntados.
    """
    rh = rotation_history.reset_index().rename(columns={'index': 'date'})
    if 'date' not in rh.columns:
        rh = rotation_history.reset_index()
        rh.columns = ['date'] + list(rh.columns[1:])

    alpha_df = alphas.reset_index()  # columns: date, ticker, ...

    merged = rh.merge(
        alpha_df[['date', 'ticker'] + [c for c in alpha_df.columns if c.startswith('alpha_')]],
        on=['date', 'ticker'],
        how='left',
    )
    return merged


def aggregate_by_signal(
    signal_alphas: pd.DataFrame,
    horizons: list[str] | None = None,
) -> pd.DataFrame:
    """
    Agrega por (signal, horizon, mode).
    """
    if horizons is None:
        horizons = ['4w', '13w', '26w']

    rows = []
    for mode in signal_alphas['mode'].unique():
        for signal in signal_alphas['signal'].fillna('IGNORAR').unique():
            mask = (
                (signal_alphas['mode'] == mode) &
                (signal_alphas['signal'].fillna('IGNORAR') == signal)
            )
            grp = signal_alphas[mask]
            for hz in horizons:
                col = f'alpha_{hz}'
                if col not in signal_alphas.columns:
                    continue
                stats_d = compute_group_stats(grp, col)
                rows.append({
                    'group_by_level': 'by_signal',
                    'signal': signal, 'regime': None, 'cluster': None,
                    'horizon': hz, 'mode': mode,
                    **stats_d,
                })
    return pd.DataFrame(rows)


def aggregate_by_signal_regime(
    signal_alphas: pd.DataFrame,
    horizons: list[str] | None = None,
) -> pd.DataFrame:
    """Agrega por (signal, regime, horizon, mode)."""
    if horizons is None:
        horizons = ['4w', '13w', '26w']

    rows = []
    for mode in signal_alphas['mode'].unique():
        for signal in signal_alphas['signal'].fillna('IGNORAR').unique():
            for regime in signal_alphas['regime'].dropna().unique():
                mask = (
                    (signal_alphas['mode'] == mode) &
                    (signal_alphas['signal'].fillna('IGNORAR') == signal) &
                    (signal_alphas['regime'] == regime)
                )
                grp = signal_alphas[mask]
                for hz in horizons:
                    col = f'alpha_{hz}'
                    if col not in signal_alphas.columns:
                        continue
                    stats_d = compute_group_stats(grp, col)
                    rows.append({
                        'group_by_level': 'by_signal_regime',
                        'signal': signal, 'regime': regime, 'cluster': None,
                        'horizon': hz, 'mode': mode,
                        **stats_d,
                    })
    return pd.DataFrame(rows)


def aggregate_by_signal_cluster(
    signal_alphas: pd.DataFrame,
    horizons: list[str] | None = None,
) -> pd.DataFrame:
    """Agrega por (signal, cluster, horizon, mode)."""
    if horizons is None:
        horizons = ['4w', '13w', '26w']

    rows = []
    for mode in signal_alphas['mode'].unique():
        for signal in signal_alphas['signal'].fillna('IGNORAR').unique():
            for cluster in signal_alphas['cluster'].dropna().unique():
                mask = (
                    (signal_alphas['mode'] == mode) &
                    (signal_alphas['signal'].fillna('IGNORAR') == signal) &
                    (signal_alphas['cluster'] == cluster)
                )
                grp = signal_alphas[mask]
                for hz in horizons:
                    col = f'alpha_{hz}'
                    if col not in signal_alphas.columns:
                        continue
                    stats_d = compute_group_stats(grp, col)
                    rows.append({
                        'group_by_level': 'by_signal_cluster',
                        'signal': signal, 'regime': None, 'cluster': cluster,
                        'horizon': hz, 'mode': mode,
                        **stats_d,
                    })
    return pd.DataFrame(rows)


def build_performance_summary(signal_alphas: pd.DataFrame) -> pd.DataFrame:
    """Combina las tres agregaciones en un unico DataFrame."""
    parts = [
        aggregate_by_signal(signal_alphas),
        aggregate_by_signal_regime(signal_alphas),
        aggregate_by_signal_cluster(signal_alphas),
    ]
    return pd.concat(parts, ignore_index=True)
