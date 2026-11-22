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


def registry_dir():
    return storage.root() / "reference" / "universe_registry"


def registry_available() -> bool:
    return (registry_dir() / "membership.parquet").exists() and (registry_dir() / "manifest.json").exists()


def _registry():
    r = registry_dir()
    man = json.loads((r / "manifest.json").read_text(encoding="utf-8"))
    memb = pd.read_parquet(r / "membership.parquet")
    succ = pd.read_parquet(r / "successions.parquet") if (r / "successions.parquet").exists() else pd.DataFrame()
    avail = pd.read_parquet(r / "provider_availability.parquet")
    return man, memb, succ, avail


def provider_status(symbol: str) -> dict:
    """Disponibilidad del símbolo en Alpaca según el registro (u1_universe_registry.py); {} si no está comprobado."""
    if not registry_available():
        return {}
    av = _registry()[3]
    row = av[av["symbol"] == symbol]
    return {} if not len(row) else {k: (None if pd.isna(v) else v) for k, v in row.iloc[0].to_dict().items()}


def resolve_successor(symbol: str, succ: pd.DataFrame, day: str) -> tuple:
    """Ticker vigente en `day` de un ticker antiguo del mismo emisor (EQR -> VMRK desde 2026-08-18). No reescribe el
    pasado: solo responde qué instrumento negocia hoy lo que el proyecto sigue llamando con el ticker antiguo."""
    seen, cur, chain = set(), symbol, []
    while len(succ) and cur not in seen:
        seen.add(cur)
        r = succ[(succ["from_ticker"].map(_alp) == cur) & (succ["effective"] <= day)]
        if not len(r):
            break
        r = r.sort_values("effective").iloc[-1]
        chain.append({"from": cur, "to": _alp(r["to_ticker"]), "effective": r["effective"], "issuer": r["issuer_key"],
                      "method": r["method"]})
        cur = _alp(r["to_ticker"])
    return cur, chain


def current_universe(use_registry: bool = True, day: str = None) -> dict:
    """{símbolo: [orígenes]} + metadatos de las fuentes.

    Con el registro del universo (U1, reference/universe_registry): S&P 500 y Nasdaq 100 vigentes según la última
    revisión de Wikipedia conciliada; los tickers del proyecto que cambiaron de ticker se sustituyen por el vigente
    del mismo emisor (constan en `superseded`); los que Alpaca no cubre se mantienen y quedan en `not_covered` con su
    estado, para registrarse como «no cubiertos por el proveedor», no como días sin negociación."""
    src = {}

    def add(syms, tag):
        for s in syms:
            src.setdefault(s, []).append(tag)
    meta = {}
    if use_registry and registry_available():
        man, memb, succ, avail = _registry()
        cur = memb[memb["end_method"] == "open"]
        add(sorted(set(cur[cur["index"] == "sp500"]["symbol"])), "sp500")
        add(sorted(set(cur[cur["index"] == "ndx"]["symbol"])), "ndx")
        day = day or man["end_day"]
        superseded = {}
        for tag, syms in (("project", [_alp(t) for t in universe.project_us_tickers()]),
                          ("market_tracker", market_tracker_us())):
            out = []
            for s in syms:
                new, chain = resolve_successor(s, succ, day)
                if chain:
                    superseded[s] = {"now": new, "chain": chain, "source": tag}
                out.append(new)
            add(out, tag)
        add(CONTEXT, "context")
        av = avail.set_index("symbol")
        not_cov = {s: (av.loc[s, "status"] if s in av.index else "not_checked") for s in src}
        not_cov = {s: st for s, st in not_cov.items() if st != "covered"}
        meta = {"registry": {"built_utc": man["built_utc"], "end_day": man["end_day"], "files_sha256": man["files_sha256"],
                             "sources": man["sources"]}, "superseded": superseded, "not_covered": not_cov}
        ndx_meta = {"source": "wikipedia revisions (universe_registry)", "fetched": man["sources"]["wikipedia"].get("ndx")}
    else:
        add(sp500_current(), "sp500")
        ndx, ndx_meta = ndx_current()
        add(ndx, "ndx")
        add([_alp(t) for t in universe.project_us_tickers()], "project")
        add(market_tracker_us(), "market_tracker")
        add(CONTEXT, "context")
    return {"symbols": src, "n": len(src), "ndx_source": ndx_meta, **meta,
            "rule": "S&P 500 + Nasdaq 100 + EE. UU. del proyecto + ETFs/acciones de Market Tracker; sin filtros técnicos"}


def historical_universe(day: str) -> dict:
    """Miembros VERIFICADOS a la fecha (solo S&P 500 histórico). Devuelve también lo que queda fuera y por qué."""
    if registry_available():
        man, memb, _, _ = _registry()
        sp = memb[memb["index"] == "sp500"]
        known_from = sp["known_from"].iloc[0]
        if day > known_from:
            # después de la instantánea de G1 (2026-01-14) manda el registro U1: ticker vigente en la fecha, sin los
            # tramos duplicados de los cambios de ticker que G1 no tenía fechados
            cur = sp[(sp["start"] <= day) & (sp["end"] >= day)]
            rows = pd.DataFrame({"symbol": cur["symbol"], "entity": cur["issuer"], "asof": None, "cik": cur["issuer"]})
            return {"symbols": rows.drop_duplicates("symbol").to_dict("records"), "n": int(rows["symbol"].nunique()),
                    "source": f"universe_registry (desde {known_from})",
                    "excluded_sources": {"ndx": "sin pertenencia histórica verificada antes de 2026-07-09",
                                         "project/market_tracker": "listas actuales: usarlas en el pasado sería sesgo de "
                                                                   "supervivencia"}}
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
