"""Consulta de cualquier valor y sesión con cat-v1, tenga o no alertas (aprobación del usuario, 2026-11-21, §5).

Fuentes, por orden:
1. registro cat-v1 en vivo (events/cat-v1/measures): las 44 medidas del valor-día escaneado con ev_scan.py;
2. capa 2 histórica (features/e2_measures + e2_norm, S&P 500 2016-01-04 → 2021-10-28): se evalúa cada medida con
   catalog_v1.evaluate sobre su línea base guardada (mismas cifras que la reconstrucción cv1_build.py);
3. cálculo bajo demanda desde las barras locales (sin descargar ni escribir nada), si se pide.

Nada de esto escribe en las capas 1-3: solo lee o calcula en memoria.
"""
import sys
import threading
from pathlib import Path

import numpy as np
import pandas as pd

from . import catalog_v1 as V, event_store, storage

_IDX = {}
_LOCK = threading.Lock()


def _index() -> pd.DataFrame:
    with _LOCK:
        if "idx" not in _IDX:
            import pyarrow.dataset as ds
            d = storage.root() / "features" / "e2_measures"
            t = ds.dataset(str(d), format="parquet").to_table(columns=["entity", "symbol", "date"]).to_pandas()
            _IDX["idx"] = t.set_index(["symbol", "date"]).sort_index()
        return _IDX["idx"]


def layer2_entity(symbol: str, day: str):
    idx = _index()
    try:
        e = idx.loc[(symbol, day), "entity"]
    except KeyError:
        return None
    return str(e.iloc[0]) if isinstance(e, pd.Series) else str(e)


def from_layer2(entity: str, day: str) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import e2_normalize as N  # noqa: E402
    fn = f"{entity.replace(':', '_')}.parquet"
    df = pd.read_parquet(storage.root() / "features" / "e2_measures" / fn)
    norm = pd.read_parquet(storage.root() / "features" / "e2_norm" / fn)
    r = int(np.where(df["date"].to_numpy() == day)[0][0])
    dates = pd.to_datetime(df["date"]).to_numpy().astype("datetime64[D]")
    base_ok = (df["cov"] >= 0.2).to_numpy()
    elig_day = bool(df.at[r, "member"]) and df.at[r, "prof_n"] >= V.params()["baseline"]["min_n"] and not bool(df.at[r, "outage"])
    rows = []
    for c in sorted(c for c in df.columns if c.endswith("__v")):
        m = c[:-3]
        x = float(df.at[r, c]) if pd.notna(df.at[r, c]) else np.nan
        W = N.windows(df[c].to_numpy(float), dates, base_ok)[r]
        ev = V.evaluate(m, x, W, liq=float(df.at[r, "liq"]) if pd.notna(df.at[r, "liq"]) else None)
        m2 = norm.at[r, f"{m}__m2"] if f"{m}__m2" in norm else np.nan
        ev["score_m2"] = float(m2) if pd.notna(m2) and np.isfinite(m2) else None
        if not elig_day and ev["state"] == "flag":
            ev["state"], ev["reason"] = "below", "valor-día no elegible (fuera del S&P 500, base corta o caída de datos)"
        pk = df.at[r, f"{m}__p"] if f"{m}__p" in df else pd.NA
        ev["peak_slot"] = int(pk) if pd.notna(pk) else None
        rows.append(ev)
    meta = {k: (df.at[r, k].item() if hasattr(df.at[r, k], "item") else df.at[r, k])
            for k in ("entity", "symbol", "date", "cov", "prof_n", "member", "early_close", "corp_event", "split_day",
                      "outage", "liq", "longest_gap", "dollar_vol") if k in df}
    meta["eligible"] = elig_day
    return {"source": "capa 2 histórica (E2), evaluada con cat-v1", "meta": meta, "measures": rows}


def valor_day(symbol: str, day: str, *, compute: bool = False) -> dict:
    """Todas las medidas del valor-día con su estado cat-v1, más sus alertas si las hay."""
    symbol = symbol.upper()
    al = event_store.read("alerts", day, version="cat-v1")
    al = al[al["symbol"] == symbol] if len(al) else al
    out = {"symbol": symbol, "day": day, "catalog_version": V.CATALOG_VERSION, "params_sha256": V.PARAMS_SHA256,
           "threshold_knowledge": V.threshold_knowledge(day), "alerts": int(len(al))}
    ms = event_store.read("measures", day, version="cat-v1")
    ms = ms[ms["symbol"] == symbol] if len(ms) else ms
    if len(ms):
        last_pass = "full" if (ms["pass"] == "full").any() else ms["pass"].iloc[0]
        ms = ms[ms["pass"] == last_pass]
        return {**out, "source": f"registro cat-v1 (escaneo manual, pasada {last_pass})",
                "measures": ms.to_dict("records")}
    ent = layer2_entity(symbol, day)
    if ent is not None:
        return {**out, **from_layer2(ent, day)}
    if compute:
        from . import event_scan
        r = event_scan.scan_symbol(symbol, day, "full", catalog="cat-v1")
        sd = r["symbol_day"] or {}
        if sd.get("status") != "ok":
            return {**out, "source": "sin datos", "error": sd.get("note") or "sin barras locales para ese valor y día"}
        return {**out, "source": "calculado bajo demanda desde las barras locales (no se escribe en el registro)",
                "measures": r["measures"], "alerts_on_demand": len(r["alerts"]),
                "meta": {k: sd.get(k) for k in ("baseline_n", "minute_coverage", "early_close", "sector")}}
    return {**out, "source": "sin calcular", "measures": [],
            "hint": "ni en el registro ni en la capa 2: usa compute=1 para calcularlo desde las barras locales"}
