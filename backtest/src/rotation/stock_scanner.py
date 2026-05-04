"""
Scanner de acciones individuales por cluster.

Criterios relajados vs rot_temprana_pure:
  - Score >= 6/10 durante >= 2 semanas consecutivas  (vs 8 durante 3)
  - Sin confirmación de cluster
  - Beta 52w vs SPY calculada sobre retornos semanales

Señales de salida:
  CANDIDATO  : streak >= 2 semanas + cluster ETF con ROT.TEMPRANA activa → máxima convicción
  EN_RADAR   : streak >= 2 semanas, cluster sin ROT.TEMPRANA todavía
  VIGILAR    : score >= 6 pero streak < 2
  IGNORAR    : score < 6
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .indicators import (
    compute_daily_indicators,
    load_daily_ohlcv,
    sample_to_friday,
)
from .score import rotation_score

SCORE_THRESHOLD = 6.0
STREAK_MIN      = 2
BETA_WEEKS      = 52
SCORE_HISTORY   = 8   # semanas hacia atrás para calcular streak


def load_stock_config(config_path: Path) -> dict[str, list[dict]]:
    """Carga individual_stocks.yaml y devuelve {cluster: [{ticker, note}]}."""
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    raw = data.get("clusters", {}) if data else {}
    result: dict[str, list[dict]] = {}
    for cluster, stocks in raw.items():
        entries = []
        for item in (stocks or []):
            if isinstance(item, dict):
                entries.append({"ticker": item.get("ticker", ""), "note": item.get("note", "")})
            elif isinstance(item, str):
                entries.append({"ticker": item, "note": ""})
        result[cluster] = [e for e in entries if e["ticker"]]
    return result


def _compute_streak(scores: list[float], threshold: float) -> int:
    """Semanas consecutivas recientes con score >= threshold."""
    streak = 0
    for s in reversed(scores):
        if s >= threshold:
            streak += 1
        else:
            break
    return streak


def _compute_beta(ticker_weekly: pd.Series, spy_weekly: pd.Series) -> float | None:
    """Beta del ticker vs SPY sobre los últimos BETA_WEEKS semanas."""
    aligned = pd.DataFrame({"t": ticker_weekly, "spy": spy_weekly}).dropna()
    if len(aligned) < 20:
        return None
    tail = aligned.tail(BETA_WEEKS)
    var_spy = tail["spy"].var()
    if var_spy == 0:
        return None
    return round(tail["t"].cov(tail["spy"]) / var_spy, 3)


def scan_stocks(
    active_rot_temprana_clusters: set[str],
    spy_weekly_ind: pd.DataFrame,
    config_path: Path,
    raw_dir: Path,
) -> list[dict]:
    """
    Escanea todas las acciones del config y devuelve candidatos ordenados.

    Args:
        active_rot_temprana_clusters: clusters con ROT.TEMPRANA activa en el ETF
        spy_weekly_ind: indicadores semanales de SPY (mismo formato que indicators.py)
        config_path: ruta a individual_stocks.yaml
        raw_dir: directorio data/raw/ con los parquets de precios
    """
    stock_config = load_stock_config(config_path)
    if not stock_config:
        return []

    spy_ret_series = spy_weekly_ind["ret_4w"].dropna() if "ret_4w" in spy_weekly_ind.columns else pd.Series(dtype=float)

    results: list[dict] = []

    for cluster_name, stocks in stock_config.items():
        cluster_active = cluster_name in active_rot_temprana_clusters

        for stock in stocks:
            ticker = stock["ticker"]
            note   = stock["note"]

            daily = load_daily_ohlcv(ticker, raw_dir)
            if daily is None or len(daily) < 60:
                print(f"    ⚠ {ticker}: datos insuficientes o no encontrados")
                continue

            try:
                daily_ind  = compute_daily_indicators(daily)
                weekly_ind = sample_to_friday(daily_ind)
            except Exception as exc:
                print(f"    ⚠ {ticker}: error al calcular indicadores: {exc}")
                continue

            if len(weekly_ind) < 4:
                continue

            # Alinear SPY con el índice del ticker
            spy_aligned = spy_weekly_ind.reindex(weekly_ind.index, method="ffill")

            # Calcular scores para las últimas SCORE_HISTORY semanas
            recent_weeks = weekly_ind.index[-SCORE_HISTORY:]
            score_history: list[float] = []
            latest_components: dict = {}

            for date in recent_weeks:
                if date not in spy_aligned.index:
                    continue
                try:
                    result = rotation_score(weekly_ind.loc[date], spy_aligned.loc[date])
                    if result["total"] is not None:
                        score_history.append(result["total"])
                        if date == recent_weeks[-1]:
                            latest_components = result.get("components", {})
                except Exception:
                    continue

            if not score_history:
                continue

            latest_score = score_history[-1]
            streak       = _compute_streak(score_history, SCORE_THRESHOLD)

            # Beta 52w
            ticker_ret = weekly_ind["ret_4w"].dropna() if "ret_4w" in weekly_ind.columns else pd.Series(dtype=float)
            beta = _compute_beta(ticker_ret, spy_ret_series)

            amplifier = round(beta * latest_score, 2) if beta is not None else None

            # Retornos vs SPY
            def _vs_spy(ret_col: str) -> float | None:
                if ret_col not in weekly_ind.columns or ret_col not in spy_aligned.columns:
                    return None
                t_val = weekly_ind[ret_col].iloc[-1]
                s_val = spy_aligned[ret_col].iloc[-1]
                if pd.isna(t_val) or pd.isna(s_val):
                    return None
                return round(float(t_val) - float(s_val), 4)

            ret_4w_vs_spy  = _vs_spy("ret_4w")
            ret_13w_vs_spy = _vs_spy("ret_13w")

            # RS Momentum: mejora del diferencial RS en las últimas 4 semanas
            # Positivo = RS mejorando aunque el precio esté lateral → acumulación en relativo
            rs_momentum = None
            if len(weekly_ind) >= 5 and "ret_4w" in weekly_ind.columns and "ret_4w" in spy_aligned.columns:
                curr_rs = weekly_ind["ret_4w"].iloc[-1] - spy_aligned["ret_4w"].iloc[-1]
                prev_rs = weekly_ind["ret_4w"].iloc[-5] - spy_aligned["ret_4w"].iloc[-5]
                if not pd.isna(curr_rs) and not pd.isna(prev_rs):
                    rs_momentum = round(float(curr_rs - prev_rs), 4)

            # ATR contraction rank: percentil del ATR% actual vs últimos 252 días
            # Valor bajo (< 25) = volatilidad contraída = posible pre-breakout
            atr_pct_rank = None
            if "atr14" in daily_ind.columns:
                atr_pct_series = (daily_ind["atr14"] / daily_ind["close"] * 100).dropna()
                if len(atr_pct_series) >= 20:
                    tail_atr = atr_pct_series.tail(252)
                    current_atr = float(atr_pct_series.iloc[-1])
                    atr_pct_rank = round(float((tail_atr < current_atr).sum() / len(tail_atr) * 100), 1)

            # Distancia al máximo de 52 semanas (%) — negativo = por debajo del high
            # Cerca de 0 = precio rozando resistencia → setup pre-breakout
            # Usa precios sin ajustar (high y close_raw) para coincidir con charts.
            dist_52w_high = None
            high_252 = daily["high"].tail(252) if "high" in daily.columns else pd.Series(dtype=float)
            if len(high_252) > 0:
                high_52w = float(high_252.max())
                close_col = "close_raw" if "close_raw" in daily.columns else "close"
                current_close = float(daily[close_col].iloc[-1])
                if high_52w > 0:
                    dist_52w_high = round((current_close / high_52w - 1) * 100, 2)

            # Señal
            if streak >= STREAK_MIN and cluster_active:
                signal = "CANDIDATO"
            elif streak >= STREAK_MIN:
                signal = "EN_RADAR"
            elif latest_score >= SCORE_THRESHOLD:
                signal = "VIGILAR"
            else:
                signal = "IGNORAR"

            latest_date = weekly_ind.index[-1]

            results.append({
                "ticker":                    ticker,
                "cluster":                   cluster_name,
                "cluster_has_rot_temprana":  cluster_active,
                "signal":                    signal,
                "rot_score":                 round(float(latest_score), 2),
                "streak_weeks":              streak,
                "beta_52w":                  beta,
                "amplifier_score":           amplifier,
                "ret_4w_vs_spy":             ret_4w_vs_spy,
                "ret_13w_vs_spy":            ret_13w_vs_spy,
                "rs_momentum":               rs_momentum,
                "atr_pct_rank":              atr_pct_rank,
                "dist_52w_high":             dist_52w_high,
                "components": {
                    k: (round(float(v), 1) if v is not None else None)
                    for k, v in latest_components.items()
                },
                "note":   note,
                "as_of":  str(latest_date.date()) if hasattr(latest_date, "date") else str(latest_date),
            })

    # Orden: CANDIDATO primero, luego EN_RADAR, luego por amplifier desc
    _signal_order = {"CANDIDATO": 0, "EN_RADAR": 1, "VIGILAR": 2, "IGNORAR": 3}
    results.sort(key=lambda x: (
        _signal_order.get(x["signal"], 9),
        -(x["amplifier_score"] or 0),
    ))

    return results
