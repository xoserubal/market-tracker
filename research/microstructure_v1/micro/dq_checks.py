"""Controles de integridad de los datos de minuto (no son alertas del catálogo: describen el dato, no la negociación).

mixed_series: series de precio mezcladas en un valor-día. Caso que lo motivó: JWN 2018-03-26, cuyas barras (y trades)
alternan toda la sesión entre ≈47 $ y ≈63,7 $ — casi con seguridad operaciones de otro instrumento asignadas al valor.

Regla (fijada antes de recorrer el histórico; parámetros en MIXED):
- Se ordenan los cierres de 1 minuto del día y se busca el mayor salto entre precios consecutivos de esa lista
  ordenada (en log). Si es ≥ `min_gap` (8 %), hay dos niveles separados.
- El nivel minoritario debe tener ≥ `min_share` (5 %) de las barras y ≥ `min_bars` (10) barras.
- Los dos niveles deben ALTERNAR en el tiempo: ≥ `min_switches` (6) cambios de nivel entre barras consecutivas. Un
  movimiento real (un salto por noticias que se mantiene, una caída) da 1-2 cambios, no decenas.
Descriptivo: no modifica las barras. Devuelve la evidencia (niveles, salto, cambios, reparto) para registrarla.
"""
import numpy as np

MIXED = {"min_gap": 0.08, "min_share": 0.05, "min_bars": 10, "min_switches": 6, "version": "dq-mixed-1"}


def mixed_series(closes) -> dict:
    c = np.asarray(closes, dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    out = {"n": int(len(c)), "flag": False, "gap": None, "switches": 0, "minority_share": None, "levels": None}
    if len(c) < 2 * MIXED["min_bars"]:
        return out
    lc = np.log(c)
    s = np.sort(lc)
    d = np.diff(s)
    k = int(np.argmax(d))
    gap = float(np.expm1(d[k]))
    cut = (s[k] + s[k + 1]) / 2
    hi = lc > cut
    n_hi = int(hi.sum())
    n_min = min(n_hi, len(c) - n_hi)
    switches = int(np.sum(hi[1:] != hi[:-1]))
    out.update(gap=round(gap, 4), switches=switches, minority_share=round(n_min / len(c), 4),
               levels=[round(float(np.median(c[~hi])), 4), round(float(np.median(c[hi])), 4)] if 0 < n_hi < len(c)
               else None)
    out["flag"] = bool(gap >= MIXED["min_gap"] and n_min >= MIXED["min_bars"] and
                       n_min / len(c) >= MIXED["min_share"] and switches >= MIXED["min_switches"])
    return out


def flagged_registry() -> dict:
    """{(entidad, fecha): evidencia} de los valor-días marcados en el recorrido histórico (dq_mixed_history.py)."""
    import pandas as pd
    from . import storage
    p = storage.root() / "results" / "dq_mixed_series.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    return {(str(r.entity), r.date): {"gap": r.gap, "switches": int(r.switches), "minority_share": r.minority_share,
                                      "levels": [r.level_lo, r.level_hi]} for r in df.itertuples()}
