"""
P0 — Persistencia completa diaria del estado de decisión (AI Picks Lab).

Fundación de la "Hoja de ruta consolidada — Auditoría de carteras IA"
(wiki/, firmada 2026-08-30, §2). Sin esto ningún experimento de la hoja de
ruta (P1A/P1B/P1C/P2/P3) es evaluable en vivo. Extiende, para el AI Picks
Lab, el mismo principio ya aplicado a Portfolio Tracker desde 2026-08-20
(portfolio_daily_snapshot.js) — que es un sistema DISTINTO (portfolio.json,
no ai_picks.json) y no cubre esto.

Mínimo viable v1 (no la versión "deseable" completa — el propio documento
avisa: "el schema no debe convertirse en proyecto"). Corre TARDE en el
pipeline, después de todos los pasos que mutan ai_picks.json (paper_trading,
cava_portfolio, mirror_portfolio, cruce_rojo_d_portfolio) — así el SELECT de
hoy ya está aplicado y esta captura recoge su primera fila el mismo día de
entrada, sin necesitar un hook aparte en cada script de cartera.

Nunca escribe en ai_picks.json — observación pura, igual que
koncorde_shadow_exits.py / cfl_followthrough_shadow.py.

Salida: docs/data/ai_picks_decision_state.jsonl — una fila por
(position_id, date). Dedup por esa clave (si ya hay fila de hoy para una
posición, se omite — el pipeline corre 2x/día).

Campos honestos, no inventados donde no hay dato limpio:
  - `trigger_threshold`/`trigger_threshold_source`: solo tiene sentido en
    carteras que usan PCS (T_active = max(62, pcs_min_entry si streak<=1),
    definición formal de la hoja de ruta §6). MIRROR_ESPEJO/CRUCE_ROJO_D no
    usan PCS — quedan explícitamente null con motivo documentado, no con un
    valor inventado.
  - `mechanical_exit_trigger`/`exit_rule_id`: replica la regla 13 real
    (ai_shared.py HARD_RULES) para carteras PCS-gated, el trailing 5% real
    para MIRROR_ESPEJO, y konc_d_trend_cross=="down" para CRUCE_ROJO_D — es
    una reimplementación en Python puro de lógica que hoy vive repartida
    entre paper_trading.py/cava_portfolio.py/mirror_portfolio.py, NO una
    importación directa (esa lógica no está factorizada en funciones puras
    reusables todavía). Riesgo de drift conocido y documentado aquí a
    propósito — el test de concordancia de P3 es precisamente lo que
    validaría (o desmentiría) que esta réplica coincide con la decisión real.
  - `prompt_version`/`scoring_version`/`data_version`: no existe todavía un
    sistema de versionado real en el proyecto — se taggean con constantes
    fijas ("v1") documentando que es un placeholder, no versionado de verdad.
  - `RS` (relative strength): se usa `ret_4w_vs_spy` de ai_candidates.json
    como proxy — es el campo más parecido a "fuerza relativa" que ya existe
    en el pipeline, no se ha inventado un cálculo nuevo.

Uso:
    py -3 scripts/ai_picks_decision_state.py               # captura real
    py -3 scripts/ai_picks_decision_state.py --dry-run      # no escribe
    py -3 scripts/ai_picks_decision_state.py --report       # resume el jsonl existente
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

PICKS_JSON       = DATA / "ai_picks.json"
CANDIDATES_JSON  = DATA / "ai_candidates.json"
SHADOW_PICKS     = DATA / "shadow_picks.jsonl"
OUT_PATH         = DATA / "ai_picks_decision_state.jsonl"

sys.path.insert(0, str(Path(__file__).parent))
from paper_trading import PORTFOLIOS  # pcs_min_entry por cartera PCS-gated

ABSOLUTE_FLOOR = 62.0

# Carteras que usan PCS con el esquema de paper_trading.py (rule 13 real).
PCS_GATED_PORTFOLIOS = [
    "HIGH_CONVICTION", "CONFIRMED_FLOW_LEADERS", "EARLY_ROTATION",
    "MACRO_THEMATIC_BENEFICIARIES", "MIMO_SHADOW",
]
ALL_LIVE_PORTFOLIOS = PCS_GATED_PORTFOLIOS + ["CAVA_MACRO", "MIRROR_ESPEJO", "CRUCE_ROJO_D"]

SCORING_VERSION = "v1"   # placeholder — no hay versionado real todavía
DATA_VERSION    = "v1"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _candidates_by_ticker(cands: dict) -> dict[str, dict]:
    items = cands.get("candidates", cands) if isinstance(cands, dict) else cands
    if isinstance(items, dict):
        items = list(items.values())
    return {c["ticker"]: c for c in items if c.get("ticker")}


def _shadow_model_lookup(shadow_rows: list[dict]) -> dict[tuple[str, str, str], str]:
    """(ticker, portfolio, entry_date) -> model. Prefiere la fila no-shadow (activa)."""
    out: dict[tuple[str, str, str], str] = {}
    for r in shadow_rows:
        key = (r.get("ticker"), r.get("portfolio"), r.get("date"))
        if key not in out or r.get("shadow") is False:
            out[key] = r.get("model")
    return out


def _prior_rows_by_position(existing: list[dict]) -> dict[str, list[dict]]:
    by_pos: dict[str, list[dict]] = {}
    for r in existing:
        by_pos.setdefault(r["position_id"], []).append(r)
    for pos_id in by_pos:
        by_pos[pos_id].sort(key=lambda r: r["date"])
    return by_pos


def _closest_at_or_before(rows: list[dict], target_date: str, field: str):
    """Valor de `field` en la fila más cercana a target_date (o antes), None si no hay."""
    candidates = [r for r in rows if r["date"] <= target_date]
    if not candidates:
        return None
    return candidates[-1].get(field)


def fetch_history(tickers: list[str]) -> dict[str, dict]:
    """OHLC de ~4 meses para todos los tickers de golpe. Necesario para
    ATR14, w1_ret_5d (retorno propio, no vs SPY), fromHigh52w (aprox sobre
    la ventana descargada, no 252 sesiones completas — 4 meses basta para
    ATR/w1, para fromHigh52w real haría falta más historial; se documenta
    la limitación en vez de fingir 52 semanas con 4 meses de datos)."""
    if not tickers:
        return {}
    out: dict[str, dict] = {}
    try:
        raw = yf.download(tickers, period="4mo", auto_adjust=True, progress=False,
                           group_by="ticker", threads=True)
    except Exception as e:
        print(f"  ⚠ fetch_history error: {e}")
        return out
    for tk in tickers:
        try:
            sub = raw[tk] if len(tickers) > 1 else raw
            sub = sub.dropna(subset=["Close"])
            if len(sub) < 5:
                continue
            out[tk] = {
                "close": sub["Close"].to_numpy(dtype=float),
                "high":  sub["High"].to_numpy(dtype=float),
                "low":   sub["Low"].to_numpy(dtype=float),
            }
        except Exception:
            continue
    return out


def _atr14(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float | None:
    if len(close) < 15:
        return None
    prev_c = np.roll(close, 1)
    prev_c[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))
    atr = np.mean(tr[-14:])
    return round(float(atr), 4) if not np.isnan(atr) else None


def _w1_ret_5d(close: np.ndarray) -> float | None:
    if len(close) < 6:
        return None
    return round(float((close[-1] / close[-6] - 1) * 100), 2)


def _from_high_window(close: np.ndarray) -> float | None:
    """Distancia al máximo de la ventana descargada (~4 meses) — ver
    limitación en fetch_history(), no es un 52w real."""
    if len(close) < 2:
        return None
    hi = float(np.max(close))
    return round(float((close[-1] / hi - 1) * 100), 2) if hi else None


def compute_t_active(portfolio: str, streak_weeks: float | None) -> tuple[float | None, str]:
    """T_active = max(62, pcs_min_entry si streak<=1) — definición formal
    de la hoja de ruta §6. Solo aplica a carteras PCS-gated."""
    if portfolio not in PCS_GATED_PORTFOLIOS:
        return None, "not_pcs_gated"
    pcs_min_entry = PORTFOLIOS.get(portfolio, {}).get("pcs_min_entry", ABSOLUTE_FLOOR)
    if streak_weeks is not None and streak_weeks <= 1:
        t = max(ABSOLUTE_FLOOR, pcs_min_entry)
        return t, "portfolio_min_entry" if t > ABSOLUTE_FLOOR else "absolute_floor_62"
    return ABSOLUTE_FLOOR, "absolute_floor_62"


def compute_mechanical_exit(portfolio: str, cand: dict | None, pos: dict,
                             current_price: float | None) -> tuple[bool | None, str | None]:
    """Réplica en Python puro de la regla mecánica real de cada tipo de
    cartera — ver docstring del módulo sobre el riesgo de drift conocido."""
    if portfolio in PCS_GATED_PORTFOLIOS:
        if cand is None:
            return True, "left_universe"
        pcs = cand.get("pcs")
        rot = cand.get("rot_score")
        streak = cand.get("streak_weeks")
        if pcs is not None and pcs < ABSOLUTE_FLOOR:
            return True, "pcs_below_absolute_floor"
        if rot is not None and rot <= 2:
            return True, "rot_score_le_2"
        pcs_min_entry = PORTFOLIOS.get(portfolio, {}).get("pcs_min_entry", ABSOLUTE_FLOOR)
        if pcs is not None and streak is not None and pcs < pcs_min_entry and streak <= 1:
            return True, "pcs_below_min_entry_low_streak"
        return False, None
    if portfolio == "CAVA_MACRO":
        pcs = cand.get("pcs") if cand else None
        if cand is None:
            return True, "left_universe"
        if pcs is not None and pcs < ABSOLUTE_FLOOR:
            return True, "pcs_below_absolute_floor"
        return False, None
    if portfolio == "MIRROR_ESPEJO":
        hwm = pos.get("high_water_mark") or pos.get("entry_price")
        if hwm and current_price is not None and current_price <= hwm * 0.95:
            return True, "trailing_stop_5pct_from_high"
        return False, None
    if portfolio == "CRUCE_ROJO_D":
        cross = cand.get("konc_d_trend_cross") if cand else None
        if cross == "down":
            return True, "konc_d_trend_cross_down"
        return False, None
    return None, "unknown_portfolio_type"


def build_rows(picks: dict, cand_by_ticker: dict[str, dict], shadow_lookup: dict,
               price_hist: dict[str, dict], prior_by_position: dict[str, list[dict]],
               today: str) -> list[dict]:
    rows = []
    for portfolio in ALL_LIVE_PORTFOLIOS:
        ptf = picks.get("portfolios", {}).get(portfolio, {})
        for pos in ptf.get("positions", []):
            ticker = pos["ticker"]
            entry_date = pos.get("entry_date")
            entry_price = pos.get("entry_price")
            if not entry_date:
                continue
            position_id = f"{ticker}__{entry_date}"
            event_id = f"{ticker}_{entry_date}"
            prior_rows = prior_by_position.get(position_id, [])

            hist = price_hist.get(ticker)
            current_price = float(hist["close"][-1]) if hist else None
            atr = _atr14(hist["high"], hist["low"], hist["close"]) if hist else None
            atr_pct = round(atr / current_price * 100, 2) if (atr and current_price) else None
            w1_ret_5d = _w1_ret_5d(hist["close"]) if hist else None
            from_high_window = _from_high_window(hist["close"]) if hist else None

            prev_running_high = _closest_at_or_before(prior_rows, today, "running_high")
            prev_running_low  = _closest_at_or_before(prior_rows, today, "running_low")
            base_high = prev_running_high if prev_running_high is not None else entry_price
            base_low  = prev_running_low  if prev_running_low  is not None else entry_price
            running_high = max(base_high, current_price) if (base_high and current_price) else base_high
            running_low  = min(base_low,  current_price) if (base_low  and current_price) else base_low
            mfe = round((running_high / entry_price - 1) * 100, 2) if (running_high and entry_price) else None
            mae = round((running_low  / entry_price - 1) * 100, 2) if (running_low  and entry_price) else None

            cand = cand_by_ticker.get(ticker)
            left_universe = cand is None
            pcs = cand.get("pcs") if cand else None
            rot_score = cand.get("rot_score") if cand else None
            streak_weeks = cand.get("streak_weeks") if cand else None
            rs = cand.get("ret_4w_vs_spy") if cand else None  # proxy de RS, ver docstring
            extension_risk = cand.get("extension_risk") if cand else None
            extension_points = cand.get("extension_points") if cand else None

            pcs_1d = _closest_at_or_before(prior_rows, (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"), "PCS")
            pcs_3d = _closest_at_or_before(prior_rows, (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d"), "PCS")
            pcs_5d = _closest_at_or_before(prior_rows, (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d"), "PCS")
            pcs_delta_1d = round(pcs - pcs_1d, 2) if (pcs is not None and pcs_1d is not None) else None
            pcs_delta_3d = round(pcs - pcs_3d, 2) if (pcs is not None and pcs_3d is not None) else None
            pcs_delta_5d = round(pcs - pcs_5d, 2) if (pcs is not None and pcs_5d is not None) else None

            t_active, t_source = compute_t_active(portfolio, streak_weeks)
            mech_trigger, exit_rule_id = compute_mechanical_exit(portfolio, cand, pos, current_price)

            if portfolio in PCS_GATED_PORTFOLIOS:
                model = shadow_lookup.get((ticker, portfolio, entry_date))
            elif portfolio == "CAVA_MACRO":
                model = "cava-engine-1.1.0"
            elif portfolio == "MIRROR_ESPEJO":
                model = "x-ai/grok-4.3-espejo"
            elif portfolio == "CRUCE_ROJO_D":
                model = "mechanical-no-model"
            else:
                model = None

            days_in_trade = (datetime.strptime(today, "%Y-%m-%d")
                              - datetime.strptime(entry_date, "%Y-%m-%d")).days

            rows.append({
                "ticker": ticker, "date": today,
                "portfolio": portfolio, "position_id": position_id, "trade_id": position_id,
                "entry_price": entry_price, "current_price": current_price,
                "running_high": running_high, "running_low": running_low,
                "MFE": mfe, "MAE": mae, "ATR": atr, "days_in_trade": days_in_trade,
                "PCS": pcs,
                # ai_candidates.json expone A-F como top-level component_A.._F (Fase 0.2 del
                # Ranking Score, 2026-08-07) además del dict anidado pcs_components (claves
                # largas, "A_macro_permission" etc.) — se usa el campo plano, más simple.
                "comp_A": cand.get("component_A") if cand else None,
                "comp_B": cand.get("component_B") if cand else None,
                "comp_C": cand.get("component_C") if cand else None,
                "comp_D": cand.get("component_D") if cand else None,
                "comp_E": cand.get("component_E") if cand else None,
                "comp_F": cand.get("component_F") if cand else None,
                "PCS_delta_1d": pcs_delta_1d, "PCS_delta_3d": pcs_delta_3d, "PCS_delta_5d": pcs_delta_5d,
                "rot_score": rot_score, "streak_weeks": streak_weeks, "RS": rs,
                "left_universe": left_universe,
                "w1_ret_5d": w1_ret_5d, "atrPct": atr_pct,
                "extension_risk_level": extension_risk, "extension_risk_points": extension_points,
                "fromHigh52w": from_high_window,  # ver limitación en fetch_history()
                "trigger_threshold": t_active, "trigger_threshold_source": t_source,
                "event_id": event_id,
                "portfolio_threshold": PORTFOLIOS.get(portfolio, {}).get("pcs_min_entry"),
                "absolute_floor": ABSOLUTE_FLOOR,
                "mechanical_exit_trigger": mech_trigger, "exit_rule_id": exit_rule_id,
                "model": model, "prompt_version": "v1",
                "scoring_version": SCORING_VERSION, "data_version": DATA_VERSION,
            })
    return rows


def print_report():
    rows = _load_jsonl(OUT_PATH)
    if not rows:
        print("Sin datos todavía en", OUT_PATH)
        return
    dates = sorted(set(r["date"] for r in rows))
    positions = set(r["position_id"] for r in rows)
    portfolios = set(r["portfolio"] for r in rows)
    print(f"ai_picks_decision_state.jsonl — {len(rows)} filas")
    print(f"  rango de fechas: {dates[0]} -> {dates[-1]} ({len(dates)} días distintos)")
    print(f"  posiciones distintas: {len(positions)}  |  carteras: {sorted(portfolios)}")
    with_mech = sum(1 for r in rows if r.get("mechanical_exit_trigger") is not None)
    print(f"  filas con mechanical_exit_trigger evaluable: {with_mech}/{len(rows)}")


def run(dry_run: bool) -> int:
    today = str(date.today())
    picks = _load(PICKS_JSON)
    cands = _load(CANDIDATES_JSON)
    if not picks or not cands:
        print("ai_picks.json o ai_candidates.json vacíos/no encontrados.")
        return 1

    cand_by_ticker = _candidates_by_ticker(cands)
    shadow_lookup = _shadow_model_lookup(_load_jsonl(SHADOW_PICKS))
    existing = _load_jsonl(OUT_PATH)
    prior_by_position = _prior_rows_by_position(existing)
    already_today = {r["position_id"] for r in existing if r["date"] == today}

    all_tickers = sorted({
        pos["ticker"]
        for pf in ALL_LIVE_PORTFOLIOS
        for pos in picks.get("portfolios", {}).get(pf, {}).get("positions", [])
    })
    print(f"Posiciones abiertas a capturar: {len(all_tickers)} tickers únicos en {len(ALL_LIVE_PORTFOLIOS)} carteras.")
    if not all_tickers:
        print("Sin posiciones abiertas en ninguna cartera — nada que capturar hoy.")
        return 0

    price_hist = fetch_history(all_tickers)
    print(f"  precio descargado: {len(price_hist)}/{len(all_tickers)} tickers")

    rows = build_rows(picks, cand_by_ticker, shadow_lookup, price_hist, prior_by_position, today)
    rows = [r for r in rows if r["position_id"] not in already_today]

    print(f"Filas nuevas a escribir hoy ({today}): {len(rows)}")
    for r in rows[:10]:
        print(f"  {r['portfolio']:24s} {r['ticker']:10s} PCS={r['PCS']} T_active={r['trigger_threshold']} "
              f"mech_exit={r['mechanical_exit_trigger']}({r['exit_rule_id']}) MFE={r['MFE']} MAE={r['MAE']}")
    if len(rows) > 10:
        print(f"  ... y {len(rows) - 10} más")

    if dry_run:
        print("\nDry-run: no se ha escrito nada.")
        return 0

    if rows:
        _append_jsonl(OUT_PATH, rows)
        print(f"\n{len(rows)} fila(s) añadida(s) a {OUT_PATH}")
    else:
        print("\nSin filas nuevas (ya capturado hoy o sin posiciones).")
    return 0


if __name__ == "__main__":
    if "--report" in sys.argv:
        print_report()
    else:
        sys.exit(run(dry_run="--dry-run" in sys.argv))
