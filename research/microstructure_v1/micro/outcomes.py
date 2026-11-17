"""Resultados de G2 (G2A_PROTOCOLO §2): ajuste por splits sin información futura, rentabilidad total con dividendos,
liquidación de salidas de cotización y protección del periodo de prueba.

Protección: toda función que produce un resultado recibe la fecha de decisión y llama a `guard`. Con fecha posterior
a la última de desarrollo se detiene, salvo en modo confirmatorio, que exige el preregistro definitivo congelado y con
hash coincidente (no existe hasta tu aprobación).
"""
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

DEV_LAST_DECISION = "2021-10-29"
STUDY = Path(__file__).resolve().parents[1]
FINAL_PREREG = STUDY / "PREREGISTRO_G2_DEFINITIVO.md"
FINAL_HASH = STUDY / "PREREGISTRO_G2_DEFINITIVO.sha256"

BANKRUPTCY_RETURN = -0.30          # sensibilidades 0 y -1 (G2A_PROTOCOLO §2)


class TestPeriodLocked(RuntimeError):
    pass


def confirmatory_allowed() -> bool:
    if not (FINAL_PREREG.exists() and FINAL_HASH.exists()):
        return False
    want = FINAL_HASH.read_text(encoding="utf-8").split()[0]
    return hashlib.sha256(FINAL_PREREG.read_bytes()).hexdigest() == want


def guard(decision_date: str, confirmatory: bool = False):
    if decision_date <= DEV_LAST_DECISION:
        return
    if confirmatory and confirmatory_allowed():
        return
    raise TestPeriodLocked(f"fecha de decisión {decision_date} > {DEV_LAST_DECISION}: prueba cerrada")


# ── acciones corporativas ──
def parse_actions(ca: pd.DataFrame) -> dict:
    """corporate_actions.parquet -> {'splits': df, 'dividends': df, 'exits': df} con campos normalizados."""
    sp, dv, ex = [], [], []
    for r in ca.itertuples():
        a = json.loads(r.json)
        t = r.type
        if t in ("forward_splits", "reverse_splits"):
            new, old = float(a.get("new_rate") or 0), float(a.get("old_rate") or 0)
            if new > 0 and old > 0 and a.get("ex_date"):
                sp.append({"symbol": a.get("symbol"), "ex_date": a["ex_date"], "factor": new / old})
        elif t == "cash_dividends":
            if a.get("ex_date") and a.get("rate") is not None:
                dv.append({"symbol": a.get("symbol"), "ex_date": a["ex_date"], "rate": float(a["rate"]),
                           "special": bool(a.get("special")), "foreign": bool(a.get("foreign"))})
        elif t in ("cash_mergers", "stock_mergers", "stock_and_cash_mergers", "worthless_removals"):
            ex.append({"type": t, "symbol": a.get("acquiree_symbol") or a.get("symbol"),
                       "date": a.get("effective_date") or a.get("process_date") or a.get("ex_date"),
                       "acquirer": a.get("acquirer_symbol"),
                       "cash": float(a.get("rate") if t == "cash_mergers" else a.get("cash_rate") or 0) or 0.0,
                       "acquirer_rate": float(a.get("acquirer_rate") or 0),
                       "acquiree_rate": float(a.get("acquiree_rate") or 0)})
    cols = {"splits": ["symbol", "ex_date", "factor"], "dividends": ["symbol", "ex_date", "rate", "special", "foreign"],
            "exits": ["type", "symbol", "date", "acquirer", "cash", "acquirer_rate", "acquiree_rate"]}
    return {k: pd.DataFrame(v, columns=cols[k]).drop_duplicates() for k, v in
            (("splits", sp), ("dividends", dv), ("exits", ex))}


def split_factor_between(splits: pd.DataFrame, after: str, upto: str) -> float:
    """Producto de factores (nuevas/antiguas) con ex_date en (after, upto]."""
    s = splits[(splits["ex_date"] > after) & (splits["ex_date"] <= upto)]
    return float(s["factor"].prod()) if len(s) else 1.0


def adjust_window(bars: pd.DataFrame, splits: pd.DataFrame, t: str) -> pd.DataFrame:
    """Precios y volúmenes de los días d <= t en unidades de t, solo con splits de ex_date <= t (sin futuro).

    bars: columnas date, o, h, l, c, vw (opcionales) y v. Devuelve una copia ajustada.
    """
    b = bars[bars["date"] <= t].copy()
    s = splits[splits["ex_date"] <= t].sort_values("ex_date")
    f = pd.Series(1.0, index=b.index)
    for r in s.itertuples():
        f[b["date"] < r.ex_date] *= r.factor
    for col in ("o", "h", "l", "c", "vw", "vwap"):
        if col in b.columns:
            b[col] = b[col] / f
    if "v" in b.columns:
        b["v"] = b["v"] * f
    return b


def total_return(bars: pd.DataFrame, splits: pd.DataFrame, divs: pd.DataFrame, days: list, t: str, h: int,
                 confirmatory: bool = False):
    """Rentabilidad de la apertura de t+1 al cierre de t+h, con splits y dividendos en (t+1, t+h].

    `splits` deben ser solo los splits coherentes de la entidad (distributions.applied_splits_by_entity, enmienda 7);
    las observaciones con un evento en su ventana se excluyen antes de llamar aquí.

    Devuelve (R, estado): estado 'ok', 'missing' (faltan barras sin salida) o 'beyond_data' (la serie termina antes:
    posible salida; la liquida `liquidate_exit`).
    """
    guard(t, confirmatory)
    i = days.index(t)
    if i + h >= len(days):
        return math.nan, "beyond_calendar"
    d1, dh = days[i + 1], days[i + h]
    bx = bars.set_index("date")
    if d1 not in bx.index:
        return math.nan, "missing" if bars["date"].max() >= dh else "beyond_data"
    if dh not in bx.index:
        return math.nan, "beyond_data" if bars["date"].max() < dh else "missing"
    o1 = float(bx.at[d1, "o"])
    s = split_factor_between(splits, d1, dh)
    dv = divs[(divs["ex_date"] > d1) & (divs["ex_date"] <= dh)]
    d_sum = sum(r.rate * split_factor_between(splits, d1, r.ex_date) for r in dv.itertuples())
    return (float(bx.at[dh, "c"]) * s + d_sum) / o1 - 1, "ok"


def liquidate_exit(entry_open: float, last_close: float, exit_row, acquirer_return_after: float = None,
                   bankruptcy: float = BANKRUPTCY_RETURN):
    """Rentabilidad total de una posición abierta a `entry_open` cuya cotización termina dentro del horizonte.

    exit_row: fila de parse_actions()['exits'] o None (sin acción identificable -> último cierre, 0 después).
    acquirer_return_after: rentabilidad del comprador desde el canje hasta t+h (fusiones en acciones o mixtas).
    """
    if exit_row is None:
        return last_close / entry_open - 1, "unknown_last_close"
    t = exit_row["type"]
    if t == "cash_mergers":
        return exit_row["cash"] / entry_open - 1, "cash"
    if t in ("stock_mergers", "stock_and_cash_mergers"):
        if acquirer_return_after is None or not exit_row["acquiree_rate"]:
            return math.nan, "stock_missing_acquirer"
        # El canje vale lo que cotizaba el adquirido en su último cierre (arbitraje de fusión ya cerrado); desde ahí
        # la parte en acciones sigue la rentabilidad del comprador y la parte en efectivo rinde 0.
        stock_part = (last_close - exit_row["cash"]) if t == "stock_and_cash_mergers" else last_close
        value = stock_part * (1 + acquirer_return_after) + exit_row["cash"]
        return value / entry_open - 1, t
    if t == "worthless_removals":
        return (last_close * (1 + bankruptcy)) / entry_open - 1, "bankruptcy"
    return last_close / entry_open - 1, "unknown_last_close"
