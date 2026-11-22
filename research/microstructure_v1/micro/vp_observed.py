"""Perfiles de volumen OBSERVADOS con trades, por lotes (VP2, 2026-11-22). Tabla aparte de la de perfiles estimados:
nunca se mezclan ni se sobrescriben.

Fuente `observed_trades_ex_close_auction`: trades de la sesión regular [apertura, cierre) que suman volumen según las
reglas oficiales de las barras (upd_vol) y no están cancelados — la misma definición que las barras, para poder
compararlos. La subasta de cierre (16:00) se guarda aparte (acciones y precio), no dentro del perfil.

Agregación incremental: cada unidad de trades se lee por lotes de filas (pyarrow iter_batches) y se suma en la rejilla
fina del día; la memoria no depende del número de operaciones. Si dos unidades se solapan en el tiempo, de la segunda
solo se toma lo que la primera no cubre (sin quitar duplicados por contenido: en 2016-2017 hay operaciones legítimas
idénticas salvo el identificador).

Cobertura: el perfil observado solo se marca `complete` si las unidades cubren toda la sesión regular.
"""
import json
import time

import numpy as np
import pandas as pd


import pyarrow.parquet as pq

from . import episode, sessions, storage, test_guard, vp_store as S
from .manifest import Manifest

SOURCE = "observed_trades_ex_close_auction"
BATCH = 500_000


def build(symbol: str, day: str, *, fine_step: float = None, manifest: Manifest = None, save: bool = True) -> dict:
    if test_guard.reserved(day):
        raise test_guard.TestPeriodLocked("fecha del periodo reservado de G2A")
    t0 = time.time()
    m = manifest or Manifest()
    b = sessions.bounds(day)
    o, c = b["open"], b["close"]
    units = episode.units_for(symbol, day, "trades", m)
    if not units:
        return {"ok": False, "reason": "sin trades descargados"}
    wins = [(episode.coverage_windows([u], day)[0], u) for u in units]
    wins.sort(key=lambda x: x[0][0])
    covered, acc, lvl_min = [], {}, None
    close_sh, close_px, n_rows, n_used = 0, None, 0, 0
    fine = fine_step
    for (wa, wz), u in wins:
        pf = pq.ParquetFile(u["path"])
        for batch in pf.iter_batches(batch_size=BATCH, columns=[x for x in ("t", "p", "s", "x", "z", "c", "u")
                                                                 if x in pf.schema_arrow.names]):
            t = batch.to_pandas()
            n_rows += len(t)
            t["t"] = pd.to_datetime(t["t"], utc=True)
            t = t[(t["t"] >= wa) & (t["t"] < wz)]                  # cada unidad, solo dentro de su ventana
            for a, z in covered:                                   # lo ya cubierto por una unidad anterior
                t = t[(t["t"] < a) | (t["t"] >= z)]
            if "c" in t and len(t) and isinstance(t["c"].iloc[0], (list, np.ndarray)):
                t["c"] = t["c"].map(lambda x: "|".join(x) if x is not None else " ")
            for col in ("x", "z", "u"):
                if col not in t:
                    t[col] = None
            tr = episode.label_trades(t, day)
            seg = sessions.classify_trades(tr, day).astype(str).to_numpy()
            ca = seg == "close_auction"
            if ca.any():
                close_sh += int(tr.loc[ca, "size"].sum())
                close_px = float(tr.loc[ca, "price"].iloc[-1])
            sel = tr[(tr["t"] >= o) & (tr["t"] < c) & tr["upd_vol"] & ~tr["canceled"] & ~ca]
            if sel.empty:
                continue
            if fine is None:
                fine = S.step_for(float(sel["price"].median()), S.PARAMS["fine_rel"])
            lv = np.floor(sel["price"].to_numpy() / fine + 1e-9).astype(np.int64)
            base = int(lv.min())
            add = np.bincount(lv - base, weights=sel["size"].to_numpy(dtype=float))
            for k, v in zip(range(base, base + len(add)), add):
                if v:
                    acc[k] = acc.get(k, 0.0) + v
            n_used += len(sel)
        covered.append((wa, wz))
    if not acc:
        return {"ok": False, "reason": "sin trades en la sesión regular"}
    lvl0 = min(acc)
    vols = np.zeros(max(acc) - lvl0 + 1)
    for k, v in acc.items():
        vols[k - lvl0] = v
    full = sorted(covered)
    t, complete = o, False
    for a, z in full:
        if a <= t:
            t = max(t, z)
    complete = t >= c
    ref = float(np.average((np.arange(len(vols)) + lvl0 + 0.5) * fine, weights=vols))
    g = S.step_for(ref, S.PARAMS["canonical_rel"])
    c0, cv = S.rebin(lvl0, vols, fine, 1.0, g)
    st = S.stats(c0, cv, g)
    row = {"symbol": symbol, "date": day, "source": SOURCE, "fine_step": fine, "lvl0": lvl0,
           "vols": vols.astype(np.float32), "profile_volume": float(vols.sum()), "trades_read": n_rows,
           "trades_used": n_used, "complete_regular_session": complete,
           "close_auction_shares": close_sh, "close_auction_price": close_px,
           "units": json.dumps([{"unit_key": u["unit_key"], "sha256": u["sha256"]} for _, u in wins]),
           "params_sha256": S.PARAMS_SHA256, "seconds": round(time.time() - t0, 1),
           **{k: v for k, v in st.items() if k != "ok"}}
    if save:
        p = storage.root() / "features" / "vp_profiles_observed" / f"{symbol}_{day}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        storage.write_parquet_atomic(pd.DataFrame([row]), p)
    return {"ok": True, **{k: v for k, v in row.items() if k != "vols"}}
