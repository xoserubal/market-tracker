"""
P1A — libros de cartera en sombra: PORTFOLIO_CONTROL, PORTFOLIO_P1A_FIXED y PORTFOLIO_P1A_ATR.

La parte decisiva del criterio de P1A (wiki/PREREGISTRO_P1A_PROFIT_PROTECTION_V1.md §5-§6, diferida en §8).
Solo lee: ai_picks.json, el log de p1a_profit_protection_v1_shadow.py y precios de yfinance. No toca ningún
parámetro de los brazos.

Reglas del libro, fijadas el 2026-11-22 antes de mirar ningún resultado de libro:
  - Universo: todas las posiciones del ámbito (HC/CFL/ER/MTB/CAVA) abiertas en algún momento desde la firma
    (2026-08-30): cerradas con close_date >= firma y las que siguen abiertas.
  - Tamaño: el size_pct contabilizado de cada posición (5 % si falta), sobre un capital inicial de 1. Sin
    reinversión: el libro suma el resultado de cada posición (NAV = 1 + Σ peso × retorno acumulado). La
    exposición bruta puede pasar del 100 %: el libro sirve para comparar brazos, no como cartera ejecutable.
  - Inicio de cada posición: su fecha de entrada, o la firma si entró antes (marcada a mercado ese día).
  - Salida: control = cierre real (o sigue abierta hoy); brazo = primer disparo del log shadow si es anterior al
    cierre real, si no, la salida del control. Se cobra el retorno del día de salida (salida al cierre).
    Sin reentrada: si la cartera real vuelve a entrar después, es otro episodio, igual en los tres libros.
  - Fricción: 0,10 % por salida en los tres libros (mismo número de salidas en todos: un brazo solo adelanta).
    El margen del §6 queda así en 0: el brazo debe superar al control después de fricción.
  - Efectivo al 0 %. Retornos en moneda local, sin cambio de divisa.
  - Precios: cierres ajustados de yfinance; días sin cotización del valor = retorno 0.

Métricas: excess_CAGR_calendar del brazo frente al control (CAGR sobre el calendario completo firma→hoy),
caída máxima, Sortino diario anualizado, exposición bruta media y número de salidas.
Criterio §6: excess_CAGR ≥ control + fricción (aquí: excess > 0 después de fricción) y caída máxima no peor que
la del control en más de 2 pp.

Uso:
    py -3 scripts/p1a_shadow_books.py            # informe por consola
    py -3 scripts/p1a_shadow_books.py --save     # + docs/data/p1a_shadow_books.json
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from p1_readiness_monitor import FIRMA_DATE, P1A_P1C_SCOPE  # noqa: E402
from p1_trade_level_analysis import P1A_LOG, PICKS_JSON, _load_jsonl, fetch_closes  # noqa: E402

DATA = Path(__file__).parent.parent / "docs" / "data"
OUT_JSON = DATA / "p1a_shadow_books.json"
DEFAULT_SIZE_PCT = 5.0
EXIT_COST = 0.0010
BOOKS = {"PORTFOLIO_CONTROL": None, "PORTFOLIO_P1A_FIXED": "exit_fixed", "PORTFOLIO_P1A_ATR": "exit_atr"}
MAX_DD_TOLERANCE_PP = 2.0


def load_positions(today: str) -> list[dict]:
    picks = json.loads(PICKS_JSON.read_text(encoding="utf-8"))
    out = []
    for pf in P1A_P1C_SCOPE:
        ptf = picks.get("portfolios", {}).get(pf, {})
        items = [(h, h["close_date"]) for h in ptf.get("history", [])
                 if h.get("event") == "close" and h.get("close_date") and h["close_date"] >= FIRMA_DATE]
        items += [(p, None) for p in ptf.get("positions", [])]
        for h, close_date in items:
            if not h.get("entry_date"):
                continue
            out.append({"portfolio": pf, "ticker": h["ticker"], "entry_date": h["entry_date"],
                        "close_date": close_date, "open": close_date is None,
                        "size_pct": h.get("size_pct") or DEFAULT_SIZE_PCT,
                        "position_id": f"{h['ticker']}__{h['entry_date']}"})
    return out


def arm_exit_dates(positions: list[dict], today: str) -> None:
    logs: dict[tuple, list[dict]] = {}
    for r in _load_jsonl(P1A_LOG):
        logs.setdefault((r["portfolio"], r["position_id"]), []).append(r)
    for p in positions:
        real_exit = p["close_date"] or today
        rows = sorted(logs.get((p["portfolio"], p["position_id"]), []), key=lambda r: r["date"])
        for flag in ("exit_fixed", "exit_atr"):
            fire = next((r["date"] for r in rows if r.get(flag) and r["date"] <= real_exit), None)
            p[flag] = fire if (fire and fire < real_exit) else None


def build_books(positions: list[dict], closes: dict[str, pd.Series], today: str) -> dict[str, pd.DataFrame]:
    cal = pd.bdate_range(FIRMA_DATE, today)
    books = {}
    for book, flag in BOOKS.items():
        value = pd.Series(0.0, index=cal)          # Σ peso × (precio / precio de inicio − 1), sin reinversión
        gross = pd.Series(0.0, index=cal)
        n_exits = 0
        for p in positions:
            s = closes.get(p["ticker"])
            if s is None:
                continue
            start = pd.Timestamp(max(p["entry_date"], FIRMA_DATE))
            exit_day = (p.get(flag) if flag else None) or p["close_date"]
            end = pd.Timestamp(exit_day or today)
            px = s.reindex(cal.union(s.index)).ffill().reindex(cal)
            p0 = s.loc[:start]
            if p0.empty:
                continue
            w = p["size_pct"] / 100
            path = w * (px / float(p0.iloc[-1]) - 1)
            path = path.where(cal >= start, 0.0)
            path = path.where(cal <= end, np.nan).ffill()     # tras salir, el resultado queda fijo
            if exit_day:
                n_exits += 1
                path = path - w * EXIT_COST * (cal >= end)
            value += path.fillna(0.0)
            gross += w * ((cal >= start) & (cal <= end)).astype(float)
        nav = 1 + value
        books[book] = pd.DataFrame({"nav": nav, "daily_pnl": nav.diff().fillna(nav.iloc[0] - 1),
                                    "gross": gross}).assign(n_exits=n_exits)
    return books


def metrics(df: pd.DataFrame, days: int) -> dict:
    nav = df["nav"]
    cagr = nav.iloc[-1] ** (365 / days) - 1 if nav.iloc[-1] > 0 else float("nan")
    dd = (nav / nav.cummax() - 1).min()
    downside = df["daily_pnl"][df["daily_pnl"] < 0]
    sortino = (df["daily_pnl"].mean() / downside.std() * np.sqrt(252)) if len(downside) > 1 else float("nan")
    return {"nav_end": float(nav.iloc[-1]), "cagr_calendar": float(cagr), "max_drawdown": float(dd),
            "sortino": float(sortino), "gross_exposure_mean": float(df["gross"].mean()),
            "n_exits": int(df["n_exits"].iloc[0])}


def report(positions: list[dict], closes, today: str, label: str) -> dict:
    books = build_books(positions, closes, today)
    days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(FIRMA_DATE, "%Y-%m-%d")).days
    m = {b: metrics(df, days) for b, df in books.items()}
    ctrl = m["PORTFOLIO_CONTROL"]
    print(f"\n== {label}: {len(positions)} posiciones ({sum(p['open'] for p in positions)} abiertas) ==")
    print(f"  {'libro':22s} {'NAV':>7s} {'CAGR cal.':>9s} {'excess':>8s} {'caída máx':>9s} {'Δ caída':>8s} {'Sortino':>8s} {'expos.':>6s} disparos")
    for b, x in m.items():
        flag = BOOKS[b]
        fired = sum(1 for p in positions if flag and p.get(flag))
        x["excess_cagr_vs_control"] = x["cagr_calendar"] - ctrl["cagr_calendar"]
        x["dd_diff_vs_control_pp"] = (x["max_drawdown"] - ctrl["max_drawdown"]) * 100
        x["n_fired_before_real_exit"] = fired
        x["criterion_met"] = (None if flag is None else bool(x["excess_cagr_vs_control"] > 0
                              and x["dd_diff_vs_control_pp"] >= -MAX_DD_TOLERANCE_PP))
        print(f"  {b:22s} {x['nav_end']:7.4f} {x['cagr_calendar']*100:+8.2f}% {x['excess_cagr_vs_control']*100:+7.2f}pp "
              f"{x['max_drawdown']*100:8.2f}% {x['dd_diff_vs_control_pp']:+7.2f}pp {x['sortino']:8.2f} "
              f"{x['gross_exposure_mean']*100:5.0f}% {fired if flag else '-'}")
    return {"metrics": m, "nav": {b: [round(v, 5) for v in df["nav"].tolist()] for b, df in books.items()},
            "dates": [d.strftime("%Y-%m-%d") for d in next(iter(books.values())).index]}


def main():
    today = str(date.today())
    positions = load_positions(today)
    arm_exit_dates(positions, today)
    start = (min(datetime.strptime(max(p["entry_date"], FIRMA_DATE), "%Y-%m-%d") for p in positions)
             - timedelta(days=10)).strftime("%Y-%m-%d")
    closes = fetch_closes(sorted({p["ticker"] for p in positions}), start)
    missing = sorted({p["ticker"] for p in positions} - set(closes))
    print(f"Libros P1A desde la firma ({FIRMA_DATE}) hasta {today}. Fricción {EXIT_COST*100:.2f} % por salida.")
    if missing:
        print(f"  sin precios (fuera de los libros): {missing}")
    out = {"generated": datetime.now().isoformat(timespec="seconds"), "firma_date": FIRMA_DATE,
           "exit_cost": EXIT_COST, "missing_prices": missing, "groups": {}}
    for label, sub in [("Todos", positions),
                       ("CAVA_MACRO", [p for p in positions if p["portfolio"] == "CAVA_MACRO"]),
                       ("Grok/Mimo (HC/CFL/ER/MTB)", [p for p in positions if p["portfolio"] != "CAVA_MACRO"])]:
        if sub:
            out["groups"][label] = report(sub, closes, today, label)
    print("\nCriterio §6 (libro): excess_CAGR del brazo > 0 tras fricción y caída máxima no peor que el control en > 2 pp.")
    print("Muestra de un solo régimen (mercado a la baja) y dominada por Cava: no basta para promover.")
    if "--save" in sys.argv:
        OUT_JSON.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"\nGuardado en {OUT_JSON}")


if __name__ == "__main__":
    main()
