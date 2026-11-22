"""Pruebas sin red de micro/vp_store.py (VP2, 2026-11-22)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import volume_profile as VP, vp_store as S  # noqa: E402


def _bars(n=300, seed=1):
    r = np.random.default_rng(seed)
    c = 50 + np.cumsum(r.normal(0, 0.03, n))
    h = c + r.uniform(0, 0.08, n)
    l = c - r.uniform(0, 0.08, n)
    return pd.DataFrame({"o": c, "h": h, "l": l, "c": c, "v": r.integers(100, 5000, n).astype(float),
                         "vw": (h + l + c) / 3})


def test_vectorized_equals_reference_triangular():
    b = _bars()
    ref = VP.estimated(b, 0.0125, "triangular")
    lvl0, v, capped = S.allocate(b["l"], b["h"], b["vw"], b["c"], b["v"], 0.0125)
    got = pd.Series(v, index=np.arange(lvl0, lvl0 + len(v)))
    got = got[got > 0]
    assert capped == 0 and np.allclose(got.reindex(ref.index).to_numpy(), ref.to_numpy())


def test_rebin_conserves_volume_and_identity():
    lvl0, v, _ = S.allocate(*(_bars()[k] for k in ("l", "h", "vw", "c", "v")), 0.0125)
    a0, a = S.rebin(lvl0, v, 0.0125, 1.0, 0.0125)
    assert a0 == lvl0 and np.allclose(a[: len(v)], v)
    for g, f in ((0.05, 1.0), (0.05, 0.25), (0.07, 2.0)):
        _, r = S.rebin(lvl0, v, 0.0125, f, g)
        assert abs(r.sum() - v.sum()) < 1e-6 * v.sum()


def test_rebin_no_artificial_shift():
    # todo el volumen en [50,00; 50,0125): con rejilla 0,05 queda entero en el nivel [50,00; 50,05)
    i0, r = S.rebin(4000, np.array([10.0]), 0.0125, 1.0, 0.05)
    assert i0 == 1000 and np.allclose(r, [10.0])
    # tras un split 2:1 (factor 0,5) el mismo volumen cae en [25,00; 25,00625) -> nivel 500 de 0,05
    i0, r = S.rebin(4000, np.array([10.0]), 0.0125, 0.5, 0.05)
    assert i0 == 500 and np.allclose(r, [10.0])


def test_stats_segments_confidence_and_peaks():
    v = np.array([1, 2, 10, 2, 1, 1, 9.5, 2, 1], dtype=float)        # dos concentraciones casi iguales, separadas
    s = S.stats(1000, v, 0.1)
    segs = json.loads(s["zone90_segments"])
    assert s["zone90_n_segments"] == 2 and s["poc_confidence"] == "baja" and len(segs) == 2
    assert s["n_peaks"] == 2 and s["poc_price"] == round(100.25, 6)
    w = np.array([1, 2, 20, 3, 2, 1], dtype=float)                   # un pico claro
    s2 = S.stats(1000, w, 0.1)
    assert s2["poc_confidence"] == "alta" and s2["zone90_n_segments"] == 1 and s2["poc_prominence"] >= 0.8
    flat = np.ones(30)
    assert S.stats(0, flat, 0.1)["poc_confidence"] == "baja" and S.stats(0, flat, 0.1)["entropy_norm"] == 1.0


def test_steps_respect_tick():
    assert S.step_for(5.0, 0.001) == 0.01 and S.step_for(250.0, 0.001) == 0.25 and S.step_for(0.5, 0.001) == 0.0005
    assert S.step_for(250.0, 0.00025) == 0.06
