"""Segmentación de la sesión en tramos que no deben mezclarse (eventos intradía, E1).

Tramos: premercado, subasta de apertura, negociación continua, subasta de cierre, after hours y comunicaciones
tardías. Además, dos categorías que no son tramos de negociación: impresiones oficiales informativas (M, Q, 9: no suman
volumen) y operaciones anuladas.

**Con trades** la separación es exacta (condiciones de cada operación, reglas oficiales de barras de micro/conditions).
**Con barras de 1 minuto** solo se puede estimar: la barra que empieza a la hora de apertura mezcla la subasta de
apertura con el primer minuto continuo, y la que empieza a la hora de cierre mezcla la subasta de cierre con el primer
minuto de after hours (caso PLTR 2026-11-17: la barra de las 16:00 tenía 2,53 M acciones, de las que 2,01 M eran la
subasta). Esas dos barras se marcan como mixtas y quedan fuera de las medidas de negociación continua.

Horarios: siempre del calendario de Alpaca (cierres anticipados) y convertidos con zoneinfo (horario de verano). Las
posiciones de minuto se cuentan en hora de Nueva York desde las 04:00, así que no se desplazan con el cambio de hora.
"""
from datetime import datetime, time

import numpy as np
import pandas as pd

from . import calendar

NY = calendar.NY
SLOT_ORIGIN = time(4, 0)        # minuto 0 = 04:00 NY
N_SLOTS = 16 * 60               # 04:00-20:00

TRADE_SEGMENTS = ("pre", "open_auction", "continuous", "close_auction", "post", "late_report",
                  "halt_reopen", "nonstandard")
INFORMATIONAL = ("official_print", "canceled")
SEGMENT_LABELS = {
    "pre": "premercado", "open_auction": "subasta de apertura", "continuous": "negociación continua",
    "close_auction": "subasta de cierre", "post": "after hours", "late_report": "comunicación tardía",
    "halt_reopen": "reapertura tras suspensión", "nonstandard": "otras condiciones no estándar",
    "official_print": "impresión oficial informativa", "canceled": "anulada",
    "open_mixed": "barra mixta de apertura", "close_mixed": "barra mixta de cierre",
}

# Comunicadas con retraso o a un precio que no es el del mercado en ese instante (guía CTS/UTP):
# L sold last, Z sold out of sequence, U extended hours sold out of sequence, P prior reference price,
# W/B average price, 4 derivatively priced.
LATE_OR_REFERENCE = {"L", "Z", "U", "P", "W", "B", "4"}
OTHER_NONSTANDARD = {"C", "G", "H", "N", "R", "V", "7"}
OFFICIAL_INFO = {"M", "Q", "9"}          # cierre oficial, apertura oficial, cierre consolidado corregido: sin volumen


def bounds(day: str) -> dict:
    """Límites de la sesión en UTC y en minutos desde las 04:00 NY."""
    o, c = calendar.session_bounds(day, "regular")
    fo, fc = calendar.session_bounds(day, "full")
    base = pd.Timestamp(datetime.combine(datetime.strptime(day, "%Y-%m-%d").date(), SLOT_ORIGIN, NY))

    def slot(ts):
        return int((ts - base).total_seconds() // 60)
    return {"day": day, "full_open": fo, "open": o, "close": c, "full_close": fc, "base": base,
            "open_slot": slot(o), "close_slot": slot(c), "end_slot": slot(fc), "start_slot": slot(fo),
            "early_close": calendar.is_early_close(day)}


def slot_time(day_bounds: dict, slot) -> pd.Timestamp:
    """Inicio del minuto `slot` en UTC."""
    return (day_bounds["base"] + pd.Timedelta(minutes=int(slot))).tz_convert("UTC")


def slots_of(t_utc: pd.Series, day_bounds: dict) -> np.ndarray:
    return ((t_utc - day_bounds["base"]).dt.total_seconds() // 60).astype("int64").to_numpy()


def bar_segment(slot: int, b: dict) -> str:
    """Tramo de una barra de 1 minuto por su minuto de inicio."""
    if slot < b["open_slot"]:
        return "pre"
    if slot == b["open_slot"]:
        return "open_mixed"
    if slot < b["close_slot"]:
        return "continuous"
    if slot == b["close_slot"]:
        return "close_mixed"
    return "post"


# ── trades ──
def _codes(cond: str) -> set:
    return set(str(cond).split("|")) if cond is not None else set()


def classify_trades(tr: pd.DataFrame, day: str) -> pd.Series:
    """Tramo de cada operación (Serie categórica alineada con tr). Requiere las columnas de episode.label_trades."""
    b = bounds(day)
    cats = pd.Categorical(tr["conditions"].astype(str))
    kind = {}
    for k in cats.categories:
        cs = _codes(k)
        if "6" in cs:
            kind[k] = "close_auction"
        elif "O" in cs:
            kind[k] = "open_auction"
        elif "5" in cs:
            kind[k] = "halt_reopen"
        elif cs & OFFICIAL_INFO and not (cs - OFFICIAL_INFO - {"@", " ", "X", "", "F", "T"}):
            kind[k] = "official_print"
        elif cs & LATE_OR_REFERENCE:
            kind[k] = "late_report"
        elif cs & OTHER_NONSTANDARD:
            kind[k] = "nonstandard"
        else:
            kind[k] = "time"
    by_cond = np.array([kind[k] for k in cats.categories], dtype=object)[cats.codes]
    t = tr["t"]
    time_seg = np.where(t < b["open"], "pre", np.where(t >= b["close"], "post", "continuous"))
    seg = np.where(by_cond == "time", time_seg, by_cond)
    # Una impresión de apertura fuera de la sesión regular (aperturas de otros mercados en premercado) no es la subasta
    seg = np.where((seg == "open_auction") & ((t < b["open"]) | (t >= b["close"])).to_numpy(), time_seg, seg)
    seg = np.where(tr["canceled"].to_numpy(), "canceled", seg)
    return pd.Series(pd.Categorical(seg, categories=list(TRADE_SEGMENTS) + list(INFORMATIONAL)), index=tr.index)


def _px(d: pd.DataFrame, which: str):
    """Precio con las reglas de barras: primero/último con upd_oc != N, máximo/mínimo con upd_hl."""
    if d.empty:
        return None
    if which in ("first", "last"):
        x = d[d["upd_oc"] != "N"]
        if x.empty:
            return None
        return float(x["price"].iloc[0 if which == "first" else -1])
    x = d[d["upd_hl"]]
    if x.empty:
        return None
    return float(x["price"].max() if which == "high" else x["price"].min())


def segment_summary(tr: pd.DataFrame, day: str) -> dict:
    """Volumen y precios por tramo, con denominadores explícitos. Volumen = operaciones con upd_vol (regla oficial)."""
    tr = tr.sort_values("t", kind="stable")
    seg = classify_trades(tr, day)
    vol = np.where(tr["upd_vol"].to_numpy(), tr["size"].to_numpy(), 0)
    out = {"segments": {}}
    for s in list(TRADE_SEGMENTS) + list(INFORMATIONAL):
        m = (seg == s).to_numpy()
        d = tr[m]
        out["segments"][s] = {
            "shares": int(vol[m].sum()), "prints": int(m.sum()),
            "shares_all_prints": int(d["size"].sum()),
            "first": _px(d, "first"), "last": _px(d, "last"), "high": _px(d, "high"), "low": _px(d, "low"),
            "odd_lot_print_share": round(float(d["odd_lot"].mean()), 4) if len(d) else None,
            "trf_share_of_shares": round(float(vol[m & tr["trf"].to_numpy()].sum() / vol[m].sum()), 4)
            if vol[m].sum() else None,
            "median_print_size": float(d["size"].median()) if len(d) else None,
        }
    S = {k: v["shares"] for k, v in out["segments"].items()}
    cont, oa, ca = S["continuous"], S["open_auction"], S["close_auction"]
    regular_total = cont + oa + ca + S["halt_reopen"]
    day_total = sum(S[s] for s in TRADE_SEGMENTS)
    den = {"continuous": cont, "regular_with_auctions": regular_total, "day_total": day_total}
    shares = {}
    for name, num in (("close_auction", ca), ("open_auction", oa), ("late_report", S["late_report"]),
                      ("post", S["post"]), ("pre", S["pre"])):
        shares[name] = {f"vs_{k}": (round(num / v, 4) if v else None) for k, v in den.items()}
    off = tr[(seg == "official_print").to_numpy()]
    close_auc = tr[(seg == "close_auction").to_numpy()]
    open_auc = tr[(seg == "open_auction").to_numpy()]
    m_print = off[off["conditions"].astype(str).str.contains(r"(?:^|\|)M(?:\||$)")]
    q_print = off[off["conditions"].astype(str).str.contains(r"(?:^|\|)Q(?:\||$)")]
    cont_d = tr[(seg == "continuous").to_numpy()]
    out["denominators"] = den
    out["shares_of"] = shares
    out["prices"] = {
        # la impresión oficial del mercado de cotización es la de mayor tamaño (otros mercados publican la suya)
        "official_open": float(q_print.loc[q_print["size"].idxmax(), "price"]) if len(q_print) else
        (float(open_auc.loc[open_auc["size"].idxmax(), "price"]) if len(open_auc) else None),
        "official_open_source": "Q" if len(q_print) else ("O (mayor)" if len(open_auc) else None),
        "official_close": float(m_print.loc[m_print["size"].idxmax(), "price"]) if len(m_print) else
        (float(close_auc.loc[close_auc["size"].idxmax(), "price"]) if len(close_auc) else None),
        "official_close_source": "M" if len(m_print) else ("6 (mayor)" if len(close_auc) else None),
        "close_auction_price": float(close_auc.loc[close_auc["size"].idxmax(), "price"]) if len(close_auc) else None,
        "first_continuous": _px(cont_d, "first"), "last_continuous": _px(cont_d, "last"),
        "last_continuous_utc": str(cont_d.loc[cont_d["upd_oc"] != "N", "t"].iloc[-1])
        if len(cont_d[cont_d["upd_oc"] != "N"]) else None,
    }
    p = out["prices"]
    if p["official_close"] and p["last_continuous"]:
        p["close_vs_last_continuous_bps"] = round((p["official_close"] / p["last_continuous"] - 1) * 1e4, 2)
    out["segment_of"] = seg
    return out


def bar_estimates(bars_day: pd.DataFrame, day: str) -> dict:
    """Lo que las barras de 1 minuto permiten ESTIMAR (no medir) de los tramos. bars_day: t (UTC), o,h,l,c,v,n."""
    b = bounds(day)
    s = slots_of(bars_day["t"], b)
    seg = np.array([bar_segment(x, b) for x in s], dtype=object)
    v = bars_day["v"].to_numpy(dtype=float)
    est = {k: float(v[seg == k].sum()) for k in ("pre", "open_mixed", "continuous", "close_mixed", "post")}
    return {"volume_by_bar_segment": est,
            "close_mixed_bar_share_of_continuous": round(est["close_mixed"] / est["continuous"], 4)
            if est["continuous"] else None,
            "note": "estimaciones: la barra mixta de cierre incluye la subasta y el primer minuto de after hours; el "
                    "volumen de las barras de after hours incluye comunicaciones tardías (condición P/W)"}


def minute_status(bars_day: pd.DataFrame, day: str, trades: pd.DataFrame = None, trade_coverage: list = None,
                  window: tuple = None) -> dict:
    """Minutos sin barra en la negociación continua (de la ventana, si se da): con solo barras es ambiguo (sin
    operaciones o dato ausente); con trades se distingue."""
    b = bounds(day)
    have = set(slots_of(bars_day["t"], b).tolist()) if len(bars_day) else set()
    lo, hi = b["open_slot"] + 1, b["close_slot"]
    if window is not None:
        lo = max(lo, int((window[0] - b["base"]).total_seconds() // 60))
        hi = min(hi, int((window[1] - b["base"]).total_seconds() // 60))
    cont = range(lo, max(lo, hi))
    no_bar = [x for x in cont if x not in have]
    runs, cur = [], 0
    for x in cont:
        cur = cur + 1 if x not in have else 0
        runs.append(cur)
    res = {"continuous_minutes": len(cont), "continuous_without_bar": len(no_bar),
           "longest_gap_minutes": int(max(runs) if runs else 0)}
    if trades is not None and trade_coverage is not None:
        ts = trades[trades["upd_vol"] & ~trades["canceled"]]
        traded = set(slots_of(ts["t"], b).tolist())
        covered = lambda x: any(a <= slot_time(b, x) and slot_time(b, x) + pd.Timedelta(minutes=1) <= z
                                for a, z in trade_coverage)
        res["no_trade"] = sum(1 for x in no_bar if covered(x) and x not in traded)
        res["missing_data"] = sum(1 for x in no_bar if not covered(x))
        res["bar_missing_but_traded"] = sum(1 for x in no_bar if covered(x) and x in traded)
    else:
        res["note"] = "solo barras: un minuto sin barra puede ser ausencia de operaciones o dato ausente"
    return res
