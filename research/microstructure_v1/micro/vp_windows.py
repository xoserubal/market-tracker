"""Evolución del perfil de volumen entre sesiones (VP2, 2026-11-22): ventanas de 5, 10, 20, 40 y 60 sesiones.

Sobre la tabla de la capa 2 (vp_build.py). Todo descriptivo: no interpreta acumulación ni distribución.

Escala común dentro de cada ventana:
- precios del día × (factor_día / factor_último_día): todo en la escala del último día de la ventana (splits validados);
- volumen en acciones ÷ ese mismo factor (tras un split 2:1, una acción de antes equivale a dos de después);
- una sola rejilla para toda la ventana: 0,10 % del precio de referencia del último día (≥ tick). Cada día se lleva a
  ella desde su perfil base fino (vp_store.rebin): un cambio de rejilla no crea desplazamientos.
- Eventos que no se pueden reconstruir (escisiones, splits incoherentes, caídas de datos) no se corrigen: se señalan.

Medidas de la ventana:
- por día (en la rejilla común): POC, área de valor, zona del 90 % (segmentos), confianza del POC; precio, rango, volumen;
- solapamiento entre días consecutivos: Jaccard del área de valor y distancia de variación total de los perfiles;
- migración del POC: neta (primer → último día), y desplazamientos MATERIALES: al menos 2 niveles de la rejilla común
  (≈ 0,2 % del precio), el POC nuevo fuera de la zona del 90 % del día anterior y el anterior fuera de la del nuevo,
  y ninguno de los dos días con confianza «baja». Lo demás son cambios entre casi empates o de un nivel y no se suman
  como movimiento;
- concentraciones persistentes: niveles que están en la zona del 90 % de su día en al menos la mitad de los días,
  agrupados en tramos contiguos;
- persistencia por área de valor (añadida tras ver los datos): niveles dentro del área de valor del 70 % de su día en
  al menos la mitad de las sesiones;
- perfil compuesto de la ventana, con sus propias estadísticas.
"""
import json
from functools import lru_cache

import numpy as np
import pandas as pd

from . import calendar, storage, vp_store as S

WINDOWS = (5, 10, 20, 40, 60)
PERSIST_FRAC = 0.5
MIN_MATERIAL_LEVELS = 2         # un salto de un solo nivel (≈ 0,1 %) no cuenta como desplazamiento material
ROOT = lambda: storage.root() / "features" / "vp_profiles"  # noqa: E731


@lru_cache(maxsize=1)
def index() -> pd.DataFrame:
    return pd.read_parquet(ROOT() / "_index.parquet")


@lru_cache(maxsize=16)
def load_file(rel: str) -> pd.DataFrame:
    return pd.read_parquet(ROOT() / rel).sort_values("date").reset_index(drop=True)


def resolve(symbol: str, end_day: str) -> tuple:
    """(fichero, entidad, periodo) del símbolo vigente en end_day; si no lo cubre, el tramo más cercano anterior."""
    ix = index()
    r = ix[ix["symbol"] == symbol.upper()]
    if not len(r):
        raise KeyError(f"sin perfiles de {symbol}")
    inside = r[(r["first"] <= end_day) & (r["last"] >= end_day)]
    row = inside.iloc[0] if len(inside) else r[r["first"] <= end_day].sort_values("last").iloc[-1] \
        if (r["first"] <= end_day).any() else r.sort_values("first").iloc[0]
    return row["file"], row["entity"], row["period"]


def window(df: pd.DataFrame, end_day: str, n: int, *, with_matrix: bool = False) -> dict:
    d = df[df["date"] <= end_day].tail(n)
    if len(d) < 2:
        return {"ok": False, "reason": "menos de 2 sesiones con perfil"}
    d = d.reset_index(drop=True)
    last = d.iloc[-1]
    fac = (d["split_factor_to_last"] / last["split_factor_to_last"]).to_numpy()
    g = S.step_for(float(last["ref_price"]), S.PARAMS["canonical_rel"])
    rows = []
    for i, r in d.iterrows():
        b0, v = S.rebin(int(r["lvl0"]), np.asarray(r["vols"], dtype=float), float(r["fine_step"]), fac[i], g)
        rows.append((b0, v / fac[i]))
    lo = min(b for b, _ in rows)
    hi = max(b + len(v) for b, v in rows)
    M = np.zeros((len(rows), hi - lo))
    for i, (b, v) in enumerate(rows):
        M[i, b - lo:b - lo + len(v)] = v
    days = []
    for i in range(len(rows)):
        st = S.stats(lo, M[i], g)
        r = d.iloc[i]
        days.append({"date": r["date"], "symbol": r["symbol"], "poc": st.get("poc_price"), "va_low": st.get("va_low"),
                     "va_high": st.get("va_high"), "zone90": json.loads(st["zone90_segments"]) if st.get("ok") else [],
                     "conf": st.get("poc_confidence"), "top1": st.get("top1_share"),
                     "o": r["o"] * fac[i], "h": r["h"] * fac[i], "l": r["l"] * fac[i], "c": r["c"] * fac[i],
                     "volume": float(M[i].sum()), "cov": float(r["cov"]),
                     "flags": [k for k in ("corp_event", "split_day", "outage") if bool(r.get(k))] +
                              (["low_cov"] if r["cov"] < 0.5 else [])})
    # solapamiento entre días consecutivos
    over = []
    for i in range(1, len(days)):
        a, b = days[i - 1], days[i]
        inter = max(0.0, min(a["va_high"], b["va_high"]) - max(a["va_low"], b["va_low"]))
        union = max(a["va_high"], b["va_high"]) - min(a["va_low"], b["va_low"])
        pa, pb = M[i - 1] / M[i - 1].sum(), M[i] / M[i].sum()
        over.append({"date": b["date"], "va_jaccard": round(inter / union, 4) if union > 0 else None,
                     "tvd": round(0.5 * float(np.abs(pa - pb).sum()), 4)})
    # migración del POC: solo desplazamientos materiales
    inzone = lambda p, z: any(x[0] <= p < x[1] for x in z)  # noqa: E731
    shifts = []
    for i in range(1, len(days)):
        a, b = days[i - 1], days[i]
        dp = b["poc"] - a["poc"]
        mat = (abs(dp) >= MIN_MATERIAL_LEVELS * g - 1e-9 and not inzone(b["poc"], a["zone90"])
               and not inzone(a["poc"], b["zone90"])
               and "baja" not in (a["conf"], b["conf"]))
        shifts.append({"date": b["date"], "shift_bps": round(dp / last["ref_price"] * 1e4, 2), "material": bool(mat)})
    mat = [s["shift_bps"] for s in shifts if s["material"]]
    # concentraciones persistentes
    zmask = np.zeros_like(M, dtype=bool)
    for i, dd in enumerate(days):
        for a, b, _ in dd["zone90"]:
            ia, ib = int(round(a / g)) - lo, int(round(b / g)) - lo
            zmask[i, max(0, ia):max(0, ib)] = True
    pers = zmask.mean(axis=0)
    comp = M.sum(axis=0)
    persistent = []
    for a, b in S._segments(pers >= PERSIST_FRAC):
        persistent.append({"low": round((lo + a) * g, 6), "high": round((lo + b + 1) * g, 6),
                           "max_persistence": round(float(pers[a:b + 1].max()), 3),
                           "composite_share": round(float(comp[a:b + 1].sum() / comp.sum()), 4)})
    # persistencia por área de valor (añadida 2026-11-22 tras ver que la de la zona del 90 % casi nunca aparece: la zona
    # de un día ocupa 1-2 niveles y el precio se mueve más que eso). Nivel persistente = dentro del área de valor del
    # 70 % de su día en al menos la mitad de las sesiones de la ventana.
    vmask = np.zeros_like(M, dtype=bool)
    for i, dd in enumerate(days):
        if dd["va_low"] is None:
            continue
        ia, ib = int(round(dd["va_low"] / g)) - lo, int(round(dd["va_high"] / g)) - lo
        vmask[i, max(0, ia):max(0, ib)] = True
    pers_va = vmask.mean(axis=0)
    persistent_va = []
    for a, b in S._segments(pers_va >= PERSIST_FRAC):
        persistent_va.append({"low": round((lo + a) * g, 6), "high": round((lo + b + 1) * g, 6),
                              "max_persistence": round(float(pers_va[a:b + 1].max()), 3),
                              "composite_share": round(float(comp[a:b + 1].sum() / comp.sum()), 4)})
    cst = S.stats(lo, comp, g)
    trading = calendar.trading_days(d["date"].iloc[0], d["date"].iloc[-1])
    out = {"ok": True, "n": int(len(d)), "requested_n": n, "start": d["date"].iloc[0], "end": d["date"].iloc[-1],
           "grid_step": g, "price_scale": f"escala del {last['date']} (splits validados aplicados)",
           "source": str(last["source"]), "version": str(last["version"]),
           "missing_sessions": [x for x in trading if x not in set(d["date"])],
           "quality_flags": sorted({f for x in days for f in x["flags"]}),
           "days": days, "overlap": over, "poc_shifts": shifts,
           "poc_net_shift_bps": round((days[-1]["poc"] - days[0]["poc"]) / last["ref_price"] * 1e4, 2),
           "poc_material_shifts": len(mat), "poc_material_path_bps": round(float(np.sum(np.abs(mat))), 2) if mat else 0.0,
           "poc_material_net_bps": round(float(np.sum(mat)), 2) if mat else 0.0,
           "poc_material_consistency": round(abs(float(np.sum(mat))) / float(np.sum(np.abs(mat))), 3) if mat else None,
           "va_jaccard_mean": round(float(np.mean([o["va_jaccard"] for o in over if o["va_jaccard"] is not None])), 4),
           "tvd_mean": round(float(np.mean([o["tvd"] for o in over])), 4),
           "va_width_first_last_bps": [round((x["va_high"] - x["va_low"]) / last["ref_price"] * 1e4, 1)
                                       for x in (days[0], days[-1])],
           "persistent": persistent, "persistent_va": persistent_va,
           "max_persistence_zone90": round(float(pers.max()), 3), "max_persistence_va": round(float(pers_va.max()), 3),
           "max_persistence_va_price": round((lo + int(np.argmax(pers_va)) + 0.5) * g, 6),
           "composite": {k: v for k, v in cst.items() if k != "ok"},
           "price_change_pct": round((days[-1]["c"] / days[0]["o"] - 1) * 100, 3),
           "range_pct": round((max(x["h"] for x in days) / min(x["l"] for x in days) - 1) * 100, 3)}
    if with_matrix:
        out["levels"] = [round((lo + i + 0.5) * g, 6) for i in range(M.shape[1])]
        out["matrix"] = [[round(float(x), 1) for x in row] for row in M]
        out["persistence"] = [round(float(x), 3) for x in pers]
        out["persistence_va"] = [round(float(x), 3) for x in pers_va]
    return out
