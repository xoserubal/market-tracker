"""
Scanner de acciones individuales por cluster.

Criterios relajados vs rot_confirmada_pure:
  - Score >= 6/10 durante >= 2 semanas consecutivas  (vs 8 durante 3)
  - Sin confirmación de cluster
  - Beta 52w vs SPY calculada sobre retornos semanales

Señales de salida:
  CANDIDATO  : streak >= 2 semanas + cluster ETF con ROT.CONFIRMADA activa → máxima convicción
  EN_RADAR   : streak >= 2 semanas, cluster sin ROT.CONFIRMADA todavía
  VIGILAR    : score >= 6 pero streak < 2
  IGNORAR    : score < 6

Fase 6b (hoja sección 9.2/10): además de las señales de arriba (basadas en el
macro_cluster ETF vía individual_stocks.yaml), se calcula por separado una señal de
ROT. TEMPRANA por inflexión agrupando por subtheme_cluster (universe.json) — p.ej.
Crypto/Miners, AI Infrastructure, Uranium — que es independiente del macro_cluster y
se expone en los campos rotation_cluster_type/rotation_cluster_name cuando aplica.
No sustituye a signal/cluster_has_confirmed_rotation, es información adicional.
"""

from __future__ import annotations

import json
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

# Fase 6b — nueva ROT. TEMPRANA (inflexión) por subtheme_cluster
NEW_EARLY_SCORE_MIN   = 6.0
NEW_EARLY_INFLECTION  = 2.0


def _load_subtheme_map(universe_path: Path | None) -> dict[str, str]:
    """Ticker -> subtheme, leído de universe.json (campo 'subtheme' por ticker)."""
    if not universe_path or not universe_path.exists():
        return {}
    try:
        data = json.loads(universe_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        t.get("ticker", ""): t.get("subtheme", "")
        for t in data.get("tickers", [])
        if t.get("ticker") and t.get("subtheme")
    }


def _load_konc3d_map(koncorde_path: Path | None) -> dict[str, str]:
    """Ticker -> konc_3d_state, leído de koncorde_data.json."""
    if not koncorde_path or not koncorde_path.exists():
        return {}
    try:
        data = json.loads(koncorde_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        tk: v.get("konc_3d_state")
        for tk, v in data.get("tickers", {}).items()
    }


def _qualifies_new_early_rotation(
    latest_score: float | None,
    prev_score: float | None,
    ret_4w_vs_spy: float | None,
    konc_3d_state: str | None,
) -> bool:
    """Condiciones 1-4 de la hoja 9.2 para UN activo (independiente de sus peers)."""
    if latest_score is None or latest_score < NEW_EARLY_SCORE_MIN:
        return False
    if prev_score is None or (latest_score - prev_score) < NEW_EARLY_INFLECTION:
        return False
    if ret_4w_vs_spy is None or ret_4w_vs_spy <= 0:
        return False
    if konc_3d_state == "distribution":
        return False
    return True


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
    active_confirmed_rotation_clusters: set[str],
    spy_weekly_ind: pd.DataFrame,
    config_path: Path,
    raw_dir: Path,
    universe_path: Path | None = None,
    koncorde_path: Path | None = None,
) -> list[dict]:
    """
    Escanea todas las acciones del config y devuelve candidatos ordenados.

    Args:
        active_confirmed_rotation_clusters: clusters con ROT.CONFIRMADA activa en el ETF
        spy_weekly_ind: indicadores semanales de SPY (mismo formato que indicators.py)
        config_path: ruta a individual_stocks.yaml
        raw_dir: directorio data/raw/ con los parquets de precios
        universe_path: ruta a docs/data/universe.json (subtheme_cluster, Fase 6b)
        koncorde_path: ruta a docs/data/koncorde_data.json (gate Konc 3D, Fase 6b)
    """
    stock_config = load_stock_config(config_path)
    if not stock_config:
        return []

    subtheme_map = _load_subtheme_map(universe_path)
    konc3d_map   = _load_konc3d_map(koncorde_path)

    spy_ret_series = spy_weekly_ind["ret_4w"].dropna() if "ret_4w" in spy_weekly_ind.columns else pd.Series(dtype=float)

    results: list[dict] = []

    for cluster_name, stocks in stock_config.items():
        cluster_active = cluster_name in active_confirmed_rotation_clusters

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
            prev_score   = score_history[-2] if len(score_history) >= 2 else None
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
                "ticker":                        ticker,
                "cluster":                       cluster_name,
                "cluster_has_confirmed_rotation": cluster_active,
                "signal":                        signal,
                "rot_score":                     round(float(latest_score), 2),
                "streak_weeks":                  streak,
                "beta_52w":                      beta,
                "amplifier_score":               amplifier,
                "ret_4w_vs_spy":                 ret_4w_vs_spy,
                "ret_13w_vs_spy":                ret_13w_vs_spy,
                "rs_momentum":                   rs_momentum,
                "atr_pct_rank":                  atr_pct_rank,
                "dist_52w_high":                 dist_52w_high,
                "components": {
                    k: (round(float(v), 1) if v is not None else None)
                    for k, v in latest_components.items()
                },
                "note":   note,
                "as_of":  str(latest_date.date()) if hasattr(latest_date, "date") else str(latest_date),
                # Campo temporal para la Fase 6b (subtheme_cluster), eliminado antes de devolver.
                "_prev_score": prev_score,
            })

    # Fase 6b: ROT. TEMPRANA por subtheme_cluster (inflexión), independiente del
    # macro_cluster de arriba. Elegibilidad individual primero, luego exige >=1 peer
    # del mismo subtheme también elegible (hoja 9.2: "ambos" activos deben cumplir).
    qualifies: dict[str, bool] = {}
    for r in results:
        qualifies[r["ticker"]] = _qualifies_new_early_rotation(
            r["rot_score"], r["_prev_score"], r["ret_4w_vs_spy"], konc3d_map.get(r["ticker"]),
        )

    by_subtheme: dict[str, list[str]] = {}
    for r in results:
        sub = subtheme_map.get(r["ticker"])
        if sub:
            by_subtheme.setdefault(sub, []).append(r["ticker"])

    for r in results:
        r["rotation_cluster_type"] = None
        r["rotation_cluster_name"] = None
        if not qualifies.get(r["ticker"]):
            continue
        sub = subtheme_map.get(r["ticker"])
        if not sub:
            continue
        peers = [t for t in by_subtheme.get(sub, []) if t != r["ticker"] and qualifies.get(t)]
        if peers:
            r["rotation_cluster_type"] = "subtheme_cluster"
            r["rotation_cluster_name"] = sub

    for r in results:
        r.pop("_prev_score", None)

    # Orden: CANDIDATO primero, luego EN_RADAR, luego por amplifier desc
    _signal_order = {"CANDIDATO": 0, "EN_RADAR": 1, "VIGILAR": 2, "IGNORAR": 3}
    results.sort(key=lambda x: (
        _signal_order.get(x["signal"], 9),
        -(x["amplifier_score"] or 0),
    ))

    return results
