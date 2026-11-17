"""Footprint: volumen ejecutado por (vela, nivel de precio) con compras/ventas agresivas estimadas e indeterminado.

Entrada: trades clasificados (aggressor.classify). Salida: estructura serializable a JSON para el visor.
- Velas de `tf_minutes` ancladas a la apertura regular (09:30 NY): la vela de 60 min es 09:30-10:30, como en las
  plataformas habituales. Antes de la apertura las velas siguen la misma rejilla hacia atrás.
- OHLC con las reglas oficiales de barras (solo trades que actualizan precio); volumen con la regla de volumen.
- Niveles: suelo(precio / paso) × paso, en céntimos enteros para no acumular error de coma flotante.
- Cada nivel: total, compra, venta, indeterminado (desglosado en subasta / sin clasificar), delta = compra - venta.
- `cursor`: solo se usan trades estrictamente anteriores al cursor (modo ciego, sin información futura).
"""
import math

import numpy as np
import pandas as pd

from . import calendar

NICE_STEPS = [0.01, 0.02, 0.05, 0.10, 0.20, 0.25, 0.50, 1.0, 2.0, 2.5, 5.0, 10.0, 25.0, 50.0]


def auto_step(lo: float, hi: float, target_levels: int = 30) -> float:
    rng = max(hi - lo, 0.01)
    for s in NICE_STEPS:
        if rng / s <= target_levels:
            return s
    return NICE_STEPS[-1]


def level_of(price: np.ndarray, step: float) -> np.ndarray:
    """Nivel (precio inferior del tramo) de cada precio, calculado en unidades de 1/10000 para evitar error."""
    ticks = int(round(step * 10000))
    p = np.floor(np.round(price * 10000, 4) / ticks + 1e-9).astype("int64") * ticks
    return p / 10000.0


def bar_start(t: pd.Series, day: str, tf_minutes: int) -> np.ndarray:
    """Inicio de la vela de cada trade, en nanosegundos UTC (int64; evita convertir millones de Timestamps)."""
    anchor = calendar.session_bounds(day, "regular")[0].value
    ns = t.dt.as_unit("ns").astype("int64").to_numpy()
    width = tf_minutes * 60 * 1_000_000_000
    return anchor + np.floor_divide(ns - anchor, width) * width


def select(tr: pd.DataFrame, *, start=None, end=None, cursor=None, sessions=("pre", "regular", "post"),
           exclude_trf=False, exclude_odd=False, exclude_nonbar=False) -> pd.DataFrame:
    """Trades vivos de la ventana con los filtros de sensibilidad. `exclude_nonbar` quita los que no actualizan
    máximo/mínimo según las reglas oficiales (odd lots, comunicaciones tardías y precios no estándar)."""
    d = tr[~tr["canceled"]]
    d = d[d["session"].isin(list(sessions))]
    if start is not None:
        d = d[d["t"] >= start]
    if end is not None:
        d = d[d["t"] < end]
    if cursor is not None:
        d = d[d["t"] < cursor]
    if exclude_trf:
        d = d[~d["trf"]]
    if exclude_odd:
        d = d[~d["odd_lot"]]
    if exclude_nonbar:
        d = d[d["upd_hl"].astype(bool)]
    return d


def compare_methods(tr: pd.DataFrame, day: str, *, tf_minutes: int = 60, methods=None, **sel) -> list:
    """Por vela: compra, venta, indeterminado y delta con cada método, y si el signo del delta discrepa.

    Indeterminado = volumen sin lado (subastas, precios no estándar, sin quote válida o sin referencia). Un delta
    cuyo valor absoluto es menor que el 5 % del volumen clasificado cuenta como «≈0» y no rompe el acuerdo.
    """
    from .aggressor import METHODS
    methods = methods or METHODS
    d = select(tr, **sel)
    if d.empty:
        return []
    vol = np.where(d["upd_vol"].to_numpy(), d["size"].to_numpy(), 0)
    bs = bar_start(d["t"], day, tf_minutes)
    cols = {"bar": bs, "vol": vol}
    for m in methods:
        s = d[f"side_{m}"].to_numpy()
        cols[f"{m}_buy"] = np.where(s > 0, vol, 0)
        cols[f"{m}_sell"] = np.where(s < 0, vol, 0)
        cols[f"{m}_und"] = np.where(s == 0, vol, 0)
    g = pd.DataFrame(cols).groupby("bar", sort=True).sum()
    out = []
    for bar, r in g.iterrows():
        row = {"t": int(bar // 1_000_000), "vol": int(r["vol"]), "methods": {}}
        signs = []
        for m in methods:
            buy, sell, und = int(r[f"{m}_buy"]), int(r[f"{m}_sell"]), int(r[f"{m}_und"])
            delta = buy - sell
            cls = buy + sell
            sg = 0 if cls == 0 or abs(delta) < 0.05 * cls else int(np.sign(delta))
            signs.append(sg)
            row["methods"][m] = {"buy": buy, "sell": sell, "undetermined": und, "delta": delta, "sign": sg,
                                 "undetermined_share": round(und / r["vol"], 4) if r["vol"] else None}
        row["sign_disagreement"] = (1 in signs) and (-1 in signs)
        out.append(row)
    return out


def build(tr: pd.DataFrame, day: str, *, method: str = "lr", tf_minutes: int = 60, step: float = None,
          start=None, end=None, cursor=None, sessions=("pre", "regular", "post"), exclude_trf=False,
          exclude_odd=False, exclude_nonbar=False, value_area=0.70) -> dict:
    d = select(tr, start=start, end=end, cursor=cursor, sessions=sessions, exclude_trf=exclude_trf,
               exclude_odd=exclude_odd, exclude_nonbar=exclude_nonbar)
    filters = {"exclude_trf": exclude_trf, "exclude_odd": exclude_odd, "exclude_nonbar": exclude_nonbar}
    if d.empty:
        return {"bars": [], "levels": [], "profile": [], "step": step, "method": method, "filters": filters,
                "quality": {}, "empty": True}
    side = d[f"side_{method}"].to_numpy()
    vol_rule = d["upd_vol"].to_numpy()
    size = np.where(vol_rule, d["size"].to_numpy(), 0)          # volumen oficial (excluye M, Q, 9)
    if step is None:
        step = auto_step(float(d["price"].quantile(0.001)), float(d["price"].quantile(0.999)))
    lv = level_of(d["price"].to_numpy(), step)
    bs = bar_start(d["t"], day, tf_minutes)
    auction = d["auction"].to_numpy()
    f = pd.DataFrame({"bar": bs, "level": lv, "vol": size,
                      "buy": np.where(side > 0, size, 0), "sell": np.where(side < 0, size, 0),
                      "auction": np.where(auction, size, 0),
                      "unclassified": np.where((side == 0) & ~auction, size, 0),
                      "trf": np.where(d["trf"].to_numpy(), size, 0), "odd": np.where(d["odd_lot"].to_numpy(), size, 0),
                      "quote_ok": np.where((d["quote_state"] == "ok").to_numpy(), size, 0),
                      "n": vol_rule.astype(int)})
    lev = f.groupby(["bar", "level"], sort=True).sum().reset_index()
    lev["delta"] = lev["buy"] - lev["sell"]

    # OHLC por vela con las reglas de barras
    px = pd.DataFrame({"bar": bs, "price": d["price"].to_numpy(), "upd_oc": d["upd_oc"].to_numpy(),
                       "upd_hl": d["upd_hl"].to_numpy()})
    oc = px[px["upd_oc"] != "N"]
    hl = px[px["upd_hl"]]
    ohlc = pd.DataFrame({"open": oc.groupby("bar")["price"].first(), "close": oc.groupby("bar")["price"].last(),
                         "high": hl.groupby("bar")["price"].max(), "low": hl.groupby("bar")["price"].min()})
    agg = f.groupby("bar").sum(numeric_only=True)
    bars = agg.join(ohlc, how="left").reset_index()
    bars["delta"] = bars["buy"] - bars["sell"]
    bars["cum_delta"] = bars["delta"].cumsum()
    bars = bars.sort_values("bar")
    # POC por vela y desequilibrios diagonales (compra en p frente a venta en p - paso, ratio >= 3)
    pocs = lev.loc[lev.groupby("bar")["vol"].idxmax(), ["bar", "level"]].set_index("bar")["level"]
    bars["poc"] = bars["bar"].map(pocs)
    lev = lev.sort_values(["bar", "level"])
    prev_sell = lev.groupby("bar")["sell"].shift(1)
    nxt_buy = lev.groupby("bar")["buy"].shift(-1)
    lev["imb_buy"] = (lev["buy"] >= 3 * prev_sell.fillna(0)) & (lev["buy"] > 0) & prev_sell.notna()
    lev["imb_sell"] = (lev["sell"] >= 3 * nxt_buy.fillna(0)) & (lev["sell"] > 0) & nxt_buy.notna()

    prof = f.groupby("level").sum(numeric_only=True).reset_index().sort_values("level")
    prof["delta"] = prof["buy"] - prof["sell"]
    va = _value_area(prof, value_area)
    tot = float(f["vol"].sum()) or 1.0
    quality = {"volume": int(f["vol"].sum()), "trades": int(f["n"].sum()),
               "classified_share": round(float((f["buy"].sum() + f["sell"].sum()) / tot), 4),
               "auction_share": round(float(f["auction"].sum() / tot), 4),
               "unclassified_share": round(float(f["unclassified"].sum() / tot), 4),
               "trf_share": round(float(f["trf"].sum() / tot), 4), "odd_lot_share": round(float(f["odd"].sum() / tot), 4),
               "quote_coverage_share": round(float(f["quote_ok"].sum() / tot), 4)}
    to_ms = lambda s: (np.asarray(s, dtype="int64") // 1_000_000).tolist()
    return {
        "method": method, "tf_minutes": tf_minutes, "step": step, "filters": filters, "empty": False,
        "first_trade": str(d["t"].iloc[0]), "last_trade": str(d["t"].iloc[-1]),
        "bars": [dict(zip(["t", "open", "high", "low", "close", "vol", "buy", "sell", "auction", "unclassified",
                           "delta", "cum_delta", "poc", "trf", "odd", "quote_ok"], r))
                 for r in zip(to_ms(bars["bar"]), *(bars[c].tolist() for c in
                                                    ["open", "high", "low", "close", "vol", "buy", "sell", "auction",
                                                     "unclassified", "delta", "cum_delta", "poc", "trf", "odd",
                                                     "quote_ok"]))],
        "levels": [dict(zip(["t", "p", "vol", "buy", "sell", "auction", "unclassified", "delta", "imb_buy", "imb_sell"], r))
                   for r in zip(to_ms(lev["bar"]), *(lev[c].tolist() for c in
                                                     ["level", "vol", "buy", "sell", "auction", "unclassified", "delta",
                                                      "imb_buy", "imb_sell"]))],
        "profile": [dict(zip(["p", "vol", "buy", "sell", "delta"], r)) for r in
                    zip(*(prof[c].tolist() for c in ["level", "vol", "buy", "sell", "delta"]))],
        "value_area": va, "quality": quality,
    }


def _value_area(prof: pd.DataFrame, share: float) -> dict:
    if prof.empty:
        return {}
    p = prof.reset_index(drop=True)
    i = int(p["vol"].idxmax())
    lo = hi = i
    acc = float(p.loc[i, "vol"])
    tot = float(p["vol"].sum())
    while acc < share * tot and (lo > 0 or hi < len(p) - 1):
        up = float(p.loc[hi + 1, "vol"]) if hi < len(p) - 1 else -1
        dn = float(p.loc[lo - 1, "vol"]) if lo > 0 else -1
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    return {"poc": float(p.loc[i, "level"]), "val": float(p.loc[lo, "level"]), "vah": float(p.loc[hi, "level"]),
            "share": round(acc / tot, 4) if tot else None}


def timeline(tr: pd.DataFrame, *, method: str = "lr", seconds: int = 60, start=None, end=None, cursor=None) -> list:
    """Serie temporal fina (por defecto 1 min) de compra, venta, delta y delta acumulado para el panel inferior."""
    d = tr[~tr["canceled"] & tr["upd_vol"]]
    if start is not None:
        d = d[d["t"] >= start]
    if end is not None:
        d = d[d["t"] < end]
    if cursor is not None:
        d = d[d["t"] < cursor]
    if d.empty:
        return []
    s = d[f"side_{method}"].to_numpy()
    g = pd.DataFrame({"t": d["t"].dt.floor(f"{seconds}s"), "buy": np.where(s > 0, d["size"], 0),
                      "sell": np.where(s < 0, d["size"], 0), "vol": d["size"], "price": d["price"]})
    a = g.groupby("t").agg(buy=("buy", "sum"), sell=("sell", "sum"), vol=("vol", "sum"), close=("price", "last"))
    a["delta"] = a["buy"] - a["sell"]
    a["cum_delta"] = a["delta"].cumsum()
    a = a.reset_index()
    return [{"t": int(r.t.value // 1_000_000), "buy": int(r.buy), "sell": int(r.sell), "vol": int(r.vol),
             "close": float(r.close), "delta": int(r.delta), "cum_delta": int(r.cum_delta)} for r in a.itertuples()]
