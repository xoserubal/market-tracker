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
