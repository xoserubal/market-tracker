"""Universo a fecha: S&P 500 histórico + valores de EE. UU. del Market Tracker.

Reutiliza la reconstrucción de research/sector_breadth_v1 (instantáneas anuales de Wikipedia + tabla de cambios,
con CIK y nombre). Sin precios aquí: la cobertura se mide aparte con Alpaca (coverage.py).
Limitaciones heredadas: precisión de las instantáneas (96,5-99,4 % de coincidencia con la tabla de cambios),
renombrados sin entrada en la tabla de cambios (el ticker antiguo se mantiene hasta la siguiente instantánea).
"""
import json
import sys
from collections import defaultdict

import pandas as pd

from . import config

SB = config.STUDY_DIR.parent / "sector_breadth_v1"


def _bp():
    if str(SB) not in sys.path:
        sys.path.insert(0, str(SB))
    import build_panel  # noqa: E402  (main() protegido por __name__)
    return build_panel


def _ok(x) -> bool:
    """Ticker válido (pandas 3 convierte None en NaN, que es verdadero)."""
    return isinstance(x, str) and bool(x.strip())


def to_alpaca(t: str) -> str:
    return t.replace("-", ".")


def sp500_membership(trading_days: list) -> pd.DataFrame:
    """Pertenencia diaria al S&P 500 -> intervalos (ticker, cik, name, start, end)."""
    bp = _bp()
    revs = json.load(open(SB / "data" / "wiki_revisions.json"))
    years = bp.YEARS
    ts = {y: pd.Timestamp(revs[str(y)]["timestamp"]).tz_localize(None) for y in years}
    snaps = {y: bp.read_snapshot(y)[0] for y in years}
    cur = bp.read_snapshot("current")[0]
    ch = bp.read_snapshot(2026)[1][1].copy()   # la página actual ya no publica la tabla de cambios
    ch.columns = ["date", "add_t", "add_n", "rem_t", "rem_n", "reason"]
    ch["date"] = pd.to_datetime(ch.date, errors="coerce")
    ch = ch[ch.date >= "2015-01-01"].sort_values("date")
    for c in ("add_t", "rem_t"):
        ch[c] = [bp.norm_t(x) if isinstance(x, str) and x.strip() else None for x in ch[c]]
    cik_of, name_of = {}, {}
    for y in years:
        for r in snaps[y].itertuples():
            if r.cik:
                cik_of[r.ticker] = r.cik
            name_of[r.ticker] = r.name
    for r in cur.itertuples():
        if r.cik:
            cik_of.setdefault(r.ticker, r.cik)
        name_of.setdefault(r.ticker, r.name)
    for r in ch.itertuples():
        if _ok(r.rem_t):
            name_of.setdefault(r.rem_t, r.rem_n)
        if _ok(r.add_t):
            name_of.setdefault(r.add_t, r.add_n)

    def members(d):
        if d < ts[years[0]]:      # antes de la primera instantánea: deshacer cambios entre d y la instantánea
            m = set(snaps[years[0]].ticker)
            for r in ch[(ch.date > d) & (ch.date <= ts[years[0]])].sort_values("date", ascending=False).itertuples():
                if _ok(r.add_t):
                    m.discard(r.add_t)
                if _ok(r.rem_t):
                    m.add(r.rem_t)
            return m
        y = max(yy for yy in years if ts[yy] <= d)
        m = set(snaps[y].ticker)
        for r in ch[(ch.date > ts[y]) & (ch.date <= d)].itertuples():
            if _ok(r.rem_t):
                m.discard(r.rem_t)
            if _ok(r.add_t):
                m.add(r.add_t)
        if y == years[-1]:
            for r in cur.itertuples():
                if r.ticker not in m and pd.notna(r.added) and r.added <= d:
                    m.add(r.ticker)
        return m

    rows = defaultdict(list)
    for d in trading_days:
        for t in members(pd.Timestamp(d)):
            rows[t].append(d)
    idx = {d: i for i, d in enumerate(trading_days)}
    out = []
    for t, ds in rows.items():
        ds = sorted(ds)
        start = prev = ds[0]
        for d in ds[1:] + [None]:
            if d is None or idx[d] != idx[prev] + 1:
                out.append({"ticker": t, "symbol": to_alpaca(t), "cik": cik_of.get(t, ""), "name": name_of.get(t, ""),
                            "source": "sp500", "start": start, "end": prev})
                if d is not None:
                    start = d
            prev = d if d is not None else prev
    df = pd.DataFrame(out)
    # Bajas posteriores a la instantánea de 2026 (14-ene) sin fecha en la tabla de cambios: siguen como miembros
    # hasta el último día. Se marcan: la fecha real de salida es desconocida (limitación documentada).
    cur_set = set(cur.ticker)
    df["end_uncertain"] = (df["end"] == trading_days[-1]) & ~df["ticker"].isin(cur_set)
    return df


def project_us_tickers() -> list:
    found = set()

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("ticker"), str):
                found.add(o["ticker"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads((config.REPO_ROOT / "portfolio.json").read_text(encoding="utf-8")))
    walk(json.loads((config.REPO_ROOT / "docs/data/universe.json").read_text(encoding="utf-8")))
    return sorted(t for t in found if "." not in t and not t.startswith("^") and "=" not in t and "-USD" not in t)
