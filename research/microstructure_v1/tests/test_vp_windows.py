"""Pruebas sin red de micro/vp_windows.py (VP2, 2026-11-22): escala común, splits y desplazamientos materiales."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import vp_store as S, vp_windows as W  # noqa: E402


def _day(date, center, vol=1000.0, factor=1.0, width=0.6, peak=None):
    """Perfil base sintético: una campana alrededor de `center` (precio sin ajustar)."""
    ref = center
    fine = S.step_for(ref, S.PARAMS["fine_rel"])
    x = np.arange(center - width, center + width, fine)
    w = np.exp(-0.5 * ((x - (peak or center)) / (width / 4)) ** 2)
    v = w / w.sum() * vol
    lvl0 = int(np.floor(x[0] / fine + 1e-9))
    return {"date": date, "symbol": "X", "ref_price": ref, "fine_step": fine, "lvl0": lvl0, "vols": v.astype(np.float32),
            "o": center, "h": center + width, "l": center - width, "c": center, "cov": 1.0, "split_factor_to_last": factor,
            "source": S.PARAMS["source"], "version": S.PARAMS["version"], "corp_event": False, "split_day": False,
            "outage": False}


def test_split_puts_days_on_common_scale():
    # antes del split 2:1 el precio es 200 y el volumen la mitad en acciones; después, 100 y el doble
    df = pd.DataFrame([_day("2019-03-04", 200.0, 500.0, factor=0.5), _day("2019-03-05", 200.0, 500.0, factor=0.5),
                       _day("2019-03-06", 100.0, 1000.0, factor=1.0)])
    w = W.window(df, "2019-03-06", 5)
    pocs = [d["poc"] for d in w["days"]]
    assert max(pocs) - min(pocs) <= w["grid_step"] + 1e-9           # mismo nivel tras el ajuste
    vols = [d["volume"] for d in w["days"]]
    assert np.allclose(vols, 1000.0, rtol=1e-6)                    # volumen en acciones comparable
    assert w["poc_material_shifts"] == 0


def test_material_shift_counts_only_clear_moves():
    df = pd.DataFrame([_day(f"2019-03-{4 + i:02d}", 100.0 + 2.0 * i) for i in range(5)])
    w = W.window(df, "2019-03-08", 5)
    assert w["poc_material_shifts"] == 4 and w["poc_material_consistency"] == 1.0 and w["poc_material_net_bps"] > 0
    flat = pd.DataFrame([_day(f"2019-03-{4 + i:02d}", 100.0, width=3.0) for i in range(5)])
    for i in range(5):                       # perfiles casi planos con el máximo moviéndose dentro de la meseta
        v = np.ones(len(flat.at[i, "vols"]), dtype=np.float32)
        v[i * 3] = 1.02
        flat.at[i, "vols"] = v
    wf = W.window(flat, "2019-03-08", 5)
    assert wf["poc_material_shifts"] == 0                           # casi empates: no son migración


def test_persistent_concentration_and_flags():
    days = [_day(f"2019-03-{4 + i:02d}", 100.0, peak=100.3 if i % 2 else 99.7) for i in range(6)]
    days[2]["corp_event"] = True
    w = W.window(pd.DataFrame(days), "2019-03-11", 10)
    assert w["n"] == 6 and "corp_event" in w["quality_flags"]
    assert len(w["persistent"]) >= 1
