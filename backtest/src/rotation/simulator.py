"""
Motor de simulación semanal para el RotationScore + señales históricas.

Flujo:
  1. Pre-calcular indicadores DIARIOS para todos los tickers,
     luego muestrear al viernes (W-FRI).
  2. Pre-calcular contexto macro semanal.
  3. Bucle semanal:
       a. Calcular scores + componentes completos para todos los tickers
       b. Actualizar streaks early rotation
       c. Segunda pasada: fit + señales (streaks ya actualizados)
       d. Cluster health scores
  4. Devolver (rotation_df, cluster_health_df)
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .clusters import TICKERS_NO_SPY, CLUSTERS, compute_cluster_health
from .indicators import load_daily_ohlcv, compute_daily_indicators, sample_to_friday
from .score import rotation_score
from .fit import get_effective_leaders, determine_fit
from .signals import determine_signal
from .early_rotation import update_streak, evaluate_early_rotation

logger = logging.getLogger(__name__)


def _safe(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _build_macro_context(
    macro_history: pd.DataFrame,
    macro_daily: pd.DataFrame,
    prices_daily: pd.DataFrame,
    mode: str,
) -> pd.DataFrame:
    """
    Construye DataFrame semanal con contexto macro completo.

    prices_daily: DataFrame diario multi-ticker (columnas = tickers, close prices).
                  Usado para DXY ret_63d y SPY SMA200 como señal de contexto.
    """
    mh = macro_history[macro_history['mode'] == mode].sort_index()

    ctx = pd.DataFrame(index=mh.index)
    ctx['regime']                    = mh['regime']
    ctx['flag_credit_complacency']   = mh['flag_credit_complacency'].fillna(False).astype(bool)
    ctx['flag_inflation_overlay']    = mh['flag_inflation_overlay'].fillna(False).astype(bool)
    ctx['flag_term_premium_extreme'] = mh['flag_term_premium_extreme'].fillna(False).astype(bool)
    ctx['flag_emergency_mode']       = mh['flag_emergency_mode'].fillna(False).astype(bool)
    ctx['hy_bps']                    = mh['hy_bps'].fillna(999.0)
    ctx['t10y3m_pct']                = mh['t10y3m_bps'].fillna(0.0) / 100.0
    ctx['curve_d13w_pct']            = ctx['t10y3m_pct'].diff(13)
    ctx['netliq_d13w_b']             = mh['netliq_usd'].diff(13) / 1000.0

    # DFII10 semanal desde macro_daily
    md_weekly = macro_daily['DFII10'].resample('W-FRI').last()
    ctx['dfii10'] = md_weekly.reindex(ctx.index).ffill().fillna(99.0)

    # DXY retorno 63 días hábiles (≈13w) muestreado al viernes
    if 'DX-Y.NYB' in prices_daily.columns:
        dxy_daily = prices_daily['DX-Y.NYB'].dropna()
        dxy_ret63 = dxy_daily.pct_change(63) * 100.0
        dxy_weekly = dxy_ret63.resample('W-FRI').last()
        ctx['dxy_ret_13w'] = dxy_weekly.reindex(ctx.index).fillna(0.0)
    else:
        ctx['dxy_ret_13w'] = 0.0

    return ctx


def simulate_rotation_history(
    prices_daily: pd.DataFrame,
    macro_history: pd.DataFrame,
    macro_daily: pd.DataFrame,
    raw_dir: Path,
    mode: str = 'A',
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ejecuta la simulación completa para un modo (A o B).

    Args:
        prices_daily: DataFrame diario multi-ticker (columnas = tickers).
        macro_history: historial de macroscore/régimen/flags.
        macro_daily:  series FRED diarias (DFII10, etc.).
        raw_dir:      directorio con parquets OHLCV crudos.
        mode:         'A' o 'B'.

    Returns:
        (rotation_df, cluster_health_df)
    """
    logger.info(f"[{mode}] Cargando indicadores OHLCV diarios...")

    # ── 1. Pre-calcular indicadores diarios → muestrear al viernes ───────────
    indicators: dict[str, pd.DataFrame] = {}
    for ticker in TICKERS_NO_SPY + ['SPY']:
        daily_ohlcv = load_daily_ohlcv(ticker, raw_dir)
        if daily_ohlcv is None or daily_ohlcv.empty:
            logger.warning(f"  [{ticker}] sin datos OHLCV, se omite")
            continue
        daily_ind = compute_daily_indicators(daily_ohlcv)
        indicators[ticker] = sample_to_friday(daily_ind)

    spy_ind = indicators.get('SPY')
    if spy_ind is None:
        raise RuntimeError("SPY necesario como benchmark")

    # ── 2. Contexto macro ────────────────────────────────────────────────────
    logger.info(f"[{mode}] Construyendo contexto macro...")
    ctx = _build_macro_context(macro_history, macro_daily, prices_daily, mode)

    # SPY > SMA200 (diario muestreado al viernes)
    spy_sma200 = spy_ind['sma200'].reindex(ctx.index)
    spy_close  = spy_ind['close'].reindex(ctx.index)
    valid_mask = spy_close.notna() & spy_sma200.notna()
    ctx['spy_above_sma200'] = pd.Series(
        np.where(valid_mask, spy_close > spy_sma200, None),
        index=ctx.index,
        dtype=object,
    )

    # ── 3. Bucle semanal ─────────────────────────────────────────────────────
    er_state: dict[str, dict] = {
        t: {'streak': 0, 'last_score': None} for t in TICKERS_NO_SPY
    }

    rotation_rows: list[dict]       = []
    cluster_health_rows: list[dict] = []

    logger.info(f"[{mode}] Simulando {len(ctx)} semanas...")

    for date in ctx.index:
        macro_row = ctx.loc[date]
        regime    = macro_row['regime']
        if pd.isna(regime):
            continue

        spy_row = spy_ind.loc[date] if date in spy_ind.index else None

        curve_d13w = _safe(macro_row['curve_d13w_pct']) or 0.0
        netliq_b   = _safe(macro_row['netliq_d13w_b'])  or 0.0
        effective_leaders = get_effective_leaders(
            regime            = str(regime),
            hy_bps            = float(macro_row['hy_bps']),
            t10y3m_pct        = float(macro_row['t10y3m_pct']),
            curve_d13w_pct    = curve_d13w,
            dfii10            = float(macro_row['dfii10']),
            dxy_ret_13w       = float(macro_row['dxy_ret_13w']),
            flag_inflation    = bool(macro_row['flag_inflation_overlay']),
            netliq_d13w_b     = netliq_b,
            flag_term_premium = bool(macro_row['flag_term_premium_extreme']),
        )

        raw_spy_above = macro_row['spy_above_sma200']
        spy_above: bool | None = (
            None if raw_spy_above is None or (isinstance(raw_spy_above, float) and np.isnan(raw_spy_above))
            else bool(raw_spy_above)
        )

        # ── Pasada 1: scores + componentes + retornos + streaks ───────────────
        week_scores:     dict[str, float | None] = {}
        week_components: dict[str, dict]         = {}
        week_returns:    dict[str, dict]          = {}

        for ticker in TICKERS_NO_SPY:
            ind = indicators.get(ticker)
            if ind is None or date not in ind.index or spy_row is None:
                week_scores[ticker]     = None
                week_components[ticker] = {}
                week_returns[ticker]    = {
                    'ret_2w_vs_spy':  None,
                    'ret_4w_vs_spy':  None,
                    'ret_13w_vs_spy': None,
                }
                update_streak(ticker, None, er_state)
                continue

            t_row = ind.loc[date]
            rs    = rotation_score(t_row, spy_row)

            week_scores[ticker]     = rs['total']
            week_components[ticker] = rs['components']

            def _rel(key: str) -> float | None:
                tv = _safe(t_row.get(key))
                sv = _safe(spy_row.get(key))
                return (tv - sv) if tv is not None and sv is not None else None

            week_returns[ticker] = {
                'ret_2w_vs_spy':  _rel('ret_2w'),
                'ret_4w_vs_spy':  _rel('ret_4w'),
                'ret_13w_vs_spy': _rel('ret_13w'),
            }

            update_streak(ticker, rs['total'], er_state)

        # ── Pasada 2: fit + señales ───────────────────────────────────────────
        netliq_d13w_b = _safe(macro_row['netliq_d13w_b'])

        for ticker in TICKERS_NO_SPY:
            ind = indicators.get(ticker)
            if ind is None or date not in ind.index:
                continue

            t_row = ind.loc[date] if date in ind.index else None
            score = week_scores.get(ticker)
            comp  = week_components.get(ticker, {})
            fit   = determine_fit(ticker, effective_leaders)

            er = evaluate_early_rotation(
                ticker           = ticker,
                fit              = fit,
                state            = er_state,
                spy_above_sma200 = spy_above,
                netliq_d13w_b    = netliq_d13w_b,
            )

            signal_label, signal_note = determine_signal(
                rot_score               = score,
                fit                     = fit,
                is_early_rotation       = er['is_early_rotation'],
                flag_credit_complacency = bool(macro_row['flag_credit_complacency']),
                flag_emergency          = bool(macro_row['flag_emergency_mode']),
                spy_above_sma200        = spy_above,
                er_validated_by_netliq  = er['er_validated_by_netliq'],
            )

            cluster = next((c for c, m in CLUSTERS.items() if ticker in m), None)

            def _fi(col: str) -> float | None:
                return _safe(t_row.get(col)) if t_row is not None else None

            rotation_rows.append({
                'date':               date,
                'ticker':             ticker,
                'mode':               mode,
                'close':              _fi('close'),
                'sma200':             _fi('sma200'),
                'sma50':              _fi('sma50'),
                'sma20':              _fi('sma20'),
                'atr14':              _fi('atr14'),
                'obv':                _fi('obv'),
                'obv_sma50':          _fi('obv_sma50'),
                'cmf20':              _fi('cmf20'),
                'macd_hist':          _fi('macd_hist'),
                'rsi14':              _fi('rsi14'),
                'vol4w':              _fi('vol4w'),
                'vol12w':             _fi('vol12w'),
                'rot_score':          score,
                'rs_13w_pts':         comp.get('rs_13w_pts'),
                'rs_4w_pts':          comp.get('rs_4w_pts'),
                'trend_abs_pts':      comp.get('trend_abs_pts'),
                'cmf_pts':            comp.get('cmf_pts'),
                'obv_pts':            comp.get('obv_pts'),
                'vol_rel_pts':        comp.get('vol_rel_pts'),
                'macd_pts':           comp.get('macd_pts'),
                'rsi_pts':            comp.get('rsi_pts'),
                'no_ext_pts':         comp.get('no_ext_pts'),
                'ret_4w_vs_spy':      week_returns[ticker]['ret_4w_vs_spy'],
                'ret_13w_vs_spy':     week_returns[ticker]['ret_13w_vs_spy'],
                'ret_2w_vs_spy':      week_returns[ticker]['ret_2w_vs_spy'],
                'regime':             regime,
                'fit':                fit,
                'cluster':            cluster,
                'signal':             signal_label,
                'signal_notes':       signal_note,
                'early_rotation_streak':  er_state.get(ticker, {}).get('streak', 0),
                'is_early_rotation':      er['is_early_rotation'],
                'er_cluster_peers':       ','.join(er['cluster_qualifying_peers']),
                'er_benchmark_condition': er['benchmark_condition'] or '',
            })

        # ── Cluster health ────────────────────────────────────────────────────
        for cluster_name, members in CLUSTERS.items():
            ch = compute_cluster_health(
                cluster_name, members,
                week_scores, week_returns, date,
            )
            cluster_health_rows.append({'date': date, 'mode': mode, **ch})

    logger.info(
        f"[{mode}] Listo: {len(rotation_rows)} filas rotacion, "
        f"{len(cluster_health_rows)} filas cluster health"
    )

    rotation_df = pd.DataFrame(rotation_rows).set_index('date')
    cluster_df  = pd.DataFrame(cluster_health_rows).set_index('date')

    return rotation_df, cluster_df
