"""Universo elegible de la línea de eventos (aprobado el 2026-11-17).

- **Actual (registro diario):** S&P 500 vigente + Nasdaq 100 vigente + acciones de EE. UU. de Market Tracker
  (portfolio.json, universe.json) + ETFs de EE. UU. de Market Tracker (las secciones de index.html, tal como las
  guarda market_equities_daily_snapshot.jsonl) + SPY y QQQ como contexto. ≈ 650 valores. Sin ningún filtro de
  Flow Score, Early Flow, momentum ni fuerza relativa.
- **Histórico (búsquedas retrospectivas):** SOLO pertenencias verificadas a la fecha. Hoy eso es el S&P 500 histórico
  reconstruido en G1 (instantáneas anuales de Wikipedia + tabla de cambios, reference/universe_intervals.parquet).
  El Nasdaq 100 histórico y las listas del proyecto no están verificadas a fecha: usarlas sería reconstruir el pasado
  con los miembros de hoy, así que quedan fuera hasta tener una fuente verificada.
- **Ampliación por liquidez (preparada, no ejecutada):** `liquidity_expansion` calcula la regla mecánica sobre barras
  diarias que se le pasen; no está conectada al escaneo.
"""
import json

import pandas as pd

from . import config, storage, universe

NDX_SOURCE = config.STUDY_DIR.parent / "macd_combo_sp500_ndx_v1" / "constituents.json"
MT_SNAPSHOT = config.REPO_ROOT / "docs" / "data" / "market_equities_daily_snapshot.jsonl"
CONTEXT = ("SPY", "QQQ")
LIQUIDITY_RULE = {"min_price": 5.0, "min_adv_usd": 20e6, "window_sessions": 60, "status": "preparada, no ejecutada"}


def _us(t: str) -> bool:
    return isinstance(t, str) and bool(t) and not any(x in t for x in (".", "^", "=", "-USD", " "))


def _alp(t: str) -> str:
    return universe.to_alpaca(t)


def sp500_current() -> list:
    iv = pd.read_parquet(storage.root() / "reference" / "universe_intervals.parquet")
    sp = iv[iv["source"] == "sp500"]
    last = sp["end"].max()
    cur = sp[(sp["end"] == last) & ~sp["end_uncertain"].fillna(False).astype(bool)]
    return sorted(set(cur["symbol"]))


def ndx_current() -> tuple:
    c = json.loads(NDX_SOURCE.read_text(encoding="utf-8"))
    return sorted({_alp(t) for t in c["ndx"]}), {"source": c.get("source"), "fetched": c.get("fetched")}


def market_tracker_us() -> list:
    if not MT_SNAPSHOT.exists():
        return []
    rows = [json.loads(line) for line in MT_SNAPSHOT.read_text(encoding="utf-8").splitlines() if line.strip()]
    last = max(r["date"] for r in rows)
    return sorted({_alp(r["ticker"]) for r in rows if r["date"] == last and _us(r["ticker"])})


def current_universe() -> dict:
    """{símbolo: [orígenes]} + metadatos de las fuentes."""
    src = {}

    def add(syms, tag):
        for s in syms:
            src.setdefault(s, []).append(tag)
    add(sp500_current(), "sp500")
    ndx, ndx_meta = ndx_current()
    add(ndx, "ndx")
    add([_alp(t) for t in universe.project_us_tickers()], "project")
    add(market_tracker_us(), "market_tracker")
    add(CONTEXT, "context")
    return {"symbols": src, "n": len(src), "ndx_source": ndx_meta,
            "rule": "S&P 500 + Nasdaq 100 + EE. UU. del proyecto + ETFs/acciones de Market Tracker; sin filtros técnicos"}


def historical_universe(day: str) -> dict:
    """Miembros VERIFICADOS a la fecha (solo S&P 500 histórico). Devuelve también lo que queda fuera y por qué."""
    iv = pd.read_parquet(storage.root() / "reference" / "universe_intervals.parquet")
    sp = iv[(iv["source"] == "sp500") & (iv["start"] <= day) & (iv["end"] >= day)]
    rows = sp[["symbol", "entity", "asof", "cik"]].drop_duplicates("symbol")
    return {"symbols": rows.to_dict("records"), "n": len(rows),
            "excluded_sources": {"ndx": "sin pertenencia histórica verificada",
                                 "project/market_tracker": "listas actuales: usarlas en el pasado sería sesgo de "
                                                           "supervivencia"}}


def liquidity_expansion(daily: pd.DataFrame, day: str, rule: dict = None) -> list:
    """Regla mecánica de ampliación (NO conectada al escaneo): precio >= 5 $ y volumen medio >= 20 M$ en las 60
    sesiones estrictamente anteriores. `daily`: symbol, date, c, v (barras diarias)."""
    r = {**LIQUIDITY_RULE, **(rule or {})}
    d = daily[daily["date"] < day].sort_values("date")
    g = d.groupby("symbol").tail(r["window_sessions"])
    agg = g.assign(dv=g["c"] * g["v"]).groupby("symbol").agg(last_c=("c", "last"), adv=("dv", "mean"), n=("dv", "size"))
    ok = agg[(agg["last_c"] >= r["min_price"]) & (agg["adv"] >= r["min_adv_usd"]) & (agg["n"] >= r["window_sessions"] // 2)]
    return sorted(ok.index)
