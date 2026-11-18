"""Carga compacta de trades y quotes de un (símbolo, día) a partir de las unidades descargadas.

A diferencia de normalize.trades (pensado para validar una unidad), aquí se carga para analizar: lectura con pyarrow,
condiciones unidas a texto y etiquetadas una vez por combinación distinta (no por fila), tipos compactos.
Funciona con días completos de valores muy líquidos (NVDA ~10 M de trades) sin agotar la memoria.

Columnas de trades: t (ns UTC), price, size, exchange, tape, conditions, canceled, upd_oc, upd_hl, upd_vol,
auction, nonstandard, odd_lot, cond_odd_lot, trf, session ('pre'|'regular'|'post').
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from . import calendar, conditions
from .manifest import Manifest
from .normalize import CANCELED_UPDATES

TRADE_COLS = ["t", "p", "s", "x", "z", "c", "u"]
QUOTE_COLS = ["t", "bp", "bs", "bx", "ap", "as", "ax", "c"]


def _read(paths, cols):
    tabs = []
    for p in paths:
        t = pq.read_table(p)
        t = t.set_column(t.schema.get_field_index("t"), "t", t.column("t").cast(pa.timestamp("ns", tz="UTC")))
        keep = [c for c in cols if c in t.column_names]
        t = t.select(keep)
        for c in cols:
            if c not in t.column_names:
                t = t.append_column(c, pa.nulls(t.num_rows, pa.string()))
        if "c" in t.column_names and pa.types.is_list(t.schema.field("c").type):
            t = t.set_column(t.schema.get_field_index("c"), "c", pc.binary_join(t.column("c"), "|"))
        for c in ("x", "z", "u", "bx", "ax"):
            if c in t.column_names:
                t = t.set_column(t.schema.get_field_index(c), c, t.column(c).cast(pa.string()))
        tabs.append(t.select(cols))
    if not tabs:
        return pd.DataFrame(columns=cols)
    return pa.concat_tables(tabs).to_pandas()


def units_for(symbol: str, day: str, kind: str, manifest: Manifest = None) -> list:
    """Unidades 'ok' de ese símbolo y día (cualquier ventana horaria o asof). Devuelve dicts del manifiesto."""
    m = manifest or Manifest()
    rows = m.rows("kind=? AND symbol=? AND period=? AND status='ok'", (kind, symbol, day))
    for r in rows:
        r["config"] = json.loads(r["config_json"])
    return rows


def coverage_windows(rows: list, day: str) -> list:
    """Ventanas UTC cubiertas por las unidades (fusionadas)."""
    from .download import _window
    w = sorted(_window(r["kind"], day, r["config"]) for r in rows)
    out = []
    for a, b in w:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _dedupe_overlap(df: pd.DataFrame, keys: list) -> pd.DataFrame:
    """Si dos ventanas descargadas se solapan, el mismo registro aparece dos veces: se deja uno."""
    return df.drop_duplicates(keys, keep="first")


def _overlapping(rows: list, day: str, window):
    """Solo las unidades cuya ventana se solapa con `window` (UTC). Sin ventana, todas."""
    if window is None:
        return rows
    from .download import _window
    a, z = window
    return [r for r in rows if _window(r["kind"], day, r["config"])[0] < z and _window(r["kind"], day, r["config"])[1] > a]


def _clip(df: pd.DataFrame, window):
    if window is None or df.empty:
        return df
    return df[(df["t"] >= window[0]) & (df["t"] < window[1])]


def load_trades(symbol: str, day: str, manifest: Manifest = None, window=None, dedupe_ids: bool = False):
    """window=(inicio, fin) UTC: lee solo las unidades que la tocan y recorta (memoria acotada en días grandes).

    dedupe_ids=True (línea de eventos, E1): quita además las repeticiones de una misma operación — mismo mercado,
    identificador, precio, tamaño y condiciones — difundidas con milisegundos de diferencia (NVDA 2020-11-27: la
    subasta de cierre aparece dos veces). Por defecto False para no cambiar la reproducibilidad de G1.5/G2A."""
    rows = _overlapping(units_for(symbol, day, "trades", manifest), day, window)
    if not rows:
        return pd.DataFrame(), []
    cols = TRADE_COLS + (["i"] if dedupe_ids else [])
    raw = _clip(_read([r["path"] for r in rows], cols), window)
    raw = _dedupe_overlap(raw, ["t", "x", "p", "s", "c", "z"]).sort_values("t", kind="stable").reset_index(drop=True)
    removed = 0
    if dedupe_ids:
        dup = raw["i"].notna() & raw.duplicated(["x", "i", "p", "s", "c"], keep="first")
        removed = int(dup.sum())
        raw = raw[~dup].drop(columns=["i"]).reset_index(drop=True)
    tr = label_trades(raw, day)
    tr.attrs["duplicate_ids_removed"] = removed
    return tr, coverage_windows(rows, day)


def label_trades(raw: pd.DataFrame, day: str) -> pd.DataFrame:
    tr = pd.DataFrame({"t": raw["t"], "price": raw["p"].astype("float64"), "size": raw["s"].astype("int64"),
                       "exchange": raw["x"].astype("category"), "tape": raw["z"].astype("category")})
    conds = raw["c"].fillna(" ").replace("", " ")
    key = conds + "#" + raw["z"].fillna("")
    cats = pd.Categorical(key)
    flags = {}
    for k in cats.categories:
        cs, tape = k.split("#")
        codes = cs.split("|")
        oc, hl, vol, _unk = conditions.minute_flags(codes, tape)
        flags[k] = (oc, hl, vol, bool(conditions.AUCTION.intersection(codes)),
                    bool(conditions.NON_STANDARD_PRICE.intersection(codes)), conditions.ODD_LOT in codes)
    f = pd.DataFrame([flags[k] for k in cats.categories], columns=["upd_oc", "upd_hl", "upd_vol", "auction",
                                                                   "nonstandard", "cond_odd_lot"])
    codes_idx = cats.codes
    for c in f.columns:
        tr[c] = f[c].to_numpy()[codes_idx]
    tr["conditions"] = pd.Categorical(conds)
    tr["canceled"] = raw["u"].isin(list(CANCELED_UPDATES)).to_numpy()
    tr["odd_lot"] = tr["size"] < 100
    tr["trf"] = (raw["x"] == "D").to_numpy()
    o, c = calendar.session_bounds(day, "regular")
    tr["session"] = pd.Categorical(np.where(tr["t"] < o, "pre", np.where(tr["t"] >= c, "post", "regular")),
                                   categories=["pre", "regular", "post"])
    return tr


def load_quotes(symbol: str, day: str, manifest: Manifest = None, window=None):
    rows = _overlapping(units_for(symbol, day, "quotes", manifest), day, window)
    if not rows:
        return pd.DataFrame(), []
    raw = _clip(_read([r["path"] for r in rows], QUOTE_COLS), window)
    raw = _dedupe_overlap(raw, ["t", "bp", "ap", "bs", "as", "bx", "ax"]).sort_values("t", kind="stable")
    q = pd.DataFrame({"t": raw["t"].to_numpy(), "bid": raw["bp"].astype("float64").to_numpy(),
                      "ask": raw["ap"].astype("float64").to_numpy(), "bid_size": raw["bs"].to_numpy(),
                      "ask_size": raw["as"].to_numpy()})
    return q, coverage_windows(rows, day)


def sizes(symbol: str, day: str) -> dict:
    out = {}
    for kind in ("trades", "quotes"):
        rows = units_for(symbol, day, kind)
        out[kind] = {"units": len(rows), "rows": int(sum(r["rows"] or 0 for r in rows)),
                     "file_bytes": int(sum(r["file_bytes"] or 0 for r in rows)),
                     "requests": int(sum(r["requests"] or 0 for r in rows)),
                     "seconds": round(float(sum(r["seconds"] or 0 for r in rows)), 1)}
    return out


# ── descarga acotada de un episodio (para el visor) ──
QUOTES_PER_TRADE_HIGH = 3.5      # cota alta medida en G0 (7 acciones); la mediana fue 1,3


def _hhmm(ts) -> str:
    return ts.tz_convert("America/New_York").strftime("%H:%M")


def trade_windows(day: str) -> list:
    """Ventanas de una hora en sesión regular (ancladas a la apertura) + premarket y postmarket enteros."""
    o, c = calendar.session_bounds(day, "regular")
    fo, fc = calendar.session_bounds(day, "full")
    w = [f"{_hhmm(fo)}-{_hhmm(o)}"]
    t = o
    while t < c:
        u = min(t + pd.Timedelta(hours=1), c)
        w.append(f"{_hhmm(t)}-{_hhmm(u)}")
        t = u
    w.append(f"{_hhmm(c)}-{_hhmm(fc)}")
    return w


def estimate(provider, symbol: str, day: str, quote_ranges: list = ()) -> dict:
    """Coste previsto a partir de la barra diaria (1 petición) y de las barras de 1 min de las ventanas de quotes."""
    from .providers.base import FetchStats
    fo, fc = calendar.session_bounds(day, "full")
    bars = []
    for pg in provider.fetch_pages("bars", symbol, calendar.iso(fo), calendar.iso(fc), timeframe="1Min", stats=FetchStats()):
        bars.extend(pg)
    if not bars:
        return {"symbol": symbol, "day": day, "trades": 0, "note": "sin barras ese día"}
    b = pd.DataFrame(bars)
    b["t"] = pd.to_datetime(b["t"], utc=True)
    n_day = int(b["n"].sum())
    out = {"symbol": symbol, "day": day, "trades_est": n_day, "trade_pages_est": math.ceil(n_day / 10000) + 7,
           "trade_GB_est": round(n_day * 10.71 / 1e9, 3), "quote_windows": []}
    for r in quote_ranges:
        a, z = calendar.ny_range(day, *r.split("-"))
        nw = int(b.loc[(b["t"] >= a) & (b["t"] < z), "n"].sum())
        out["quote_windows"].append({"range": r, "trades_in_window": nw,
                                     "quotes_est_median": int(nw * 1.3), "quotes_est_high": int(nw * QUOTES_PER_TRADE_HIGH),
                                     "pages_est_high": math.ceil(nw * QUOTES_PER_TRADE_HIGH / 10000)})
    return out


def fetch_day(provider, symbol: str, day: str, *, quote_ranges: list = (), asof=None, manifest: Manifest = None) -> list:
    """Descarga los trades del día por ventanas y las quotes de los tramos pedidos (idempotente)."""
    from . import download
    m = manifest or Manifest()
    res = []
    for w in trade_windows(day):
        cfg = download.config_for("trades", session="full", time_range=w)
        res.append(download.download_unit(provider, "trades", symbol, day, asof=asof, cfg=cfg, manifest=m))
    for r in quote_ranges:
        cfg = download.config_for("quotes", session="regular", time_range=r)
        res.append(download.download_unit(provider, "quotes", symbol, day, asof=asof, cfg=cfg, manifest=m))
    return res
