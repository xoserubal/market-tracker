"""Pruebas de micro/features.py: percentiles sin futuro, área de valor, equivalencia de splits (enmienda 4.4) y
ausencia de información futura en el índice de anomalía."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import features as F  # noqa: E402


def series(n=420, seed=1, scale=1.0, vscale=1.0):
    rng = np.random.default_rng(seed)
    c = 50 * np.exp(np.cumsum(rng.normal(0, 0.015, n))) * scale
    h = c * (1 + rng.uniform(0, 0.02, n))
    l = c * (1 - rng.uniform(0, 0.02, n))
    o = (h + l) / 2
    v = rng.lognormal(13, 0.4, n) * vscale
    er = rng.uniform(0.02, 0.6, n)
    s = pd.DataFrame({"date": pd.bdate_range("2017-01-02", periods=n).strftime("%Y-%m-%d"),
                      "o": o, "h": h, "l": l, "c": c, "v": v, "er": er})
    bins = np.floor(np.log(c) / F.LOG_STEP).astype(int)
    b0 = bins.min() - 5
    vap = np.zeros((n, bins.max() - b0 + 6))
    for i, b in enumerate(bins):
        vap[i, b - b0 - 2:b - b0 + 3] = v[i] / 5
    return s, vap, b0


def test_pct_prev():
    x = np.array([1, 2, 3, 4, 2.0])
    p = F.pct_prev(x, n=4)
    assert np.isnan(p[:4]).all() and p[4] == pytest.approx((1 + 0.5) / 4)
    y = x.copy()
    y[-1] = np.nan
    assert np.isnan(F.pct_prev(y, 4)[4])


def test_value_area_contiguous():
    poc, w = F.value_area(np.array([0, 1, 10, 3, 0, 0, 5.0]))
    assert poc == 2 and w == 3                     # 10 + 3 + 1 = 14 >= 0,7 × 19


def test_split_scale_invariance():
    s1, vap1, b1 = series()
    s2, _, _ = series(scale=0.5, vscale=2.0)        # mismo valor con un split 2:1 aplicado a toda la historia
    # el volumen por precio ajustado es la misma matriz desplazada un número entero de celdas (redondeo <= 1/2 celda)
    shift = int(round(np.log(0.5) / F.LOG_STEP))
    vap2, b2 = vap1 * 2.0, b1 + shift
    a1, a2 = F.awd(s1), F.awd(s2)
    c1 = F.family_c(s1, vap1, b1, a1, 40)
    c2 = F.family_c(s2, vap2, b2, a2, 40)
    pd.testing.assert_frame_equal(a1, a2, rtol=1e-9)
    for col in ("range_40", "ai_40_80", "ai_40_90"):
        np.testing.assert_allclose(c1[col].to_numpy(), c2[col].to_numpy(), rtol=1e-6, atol=0.02, equal_nan=True)
    # la posición del POC solo difiere por el redondeo del desplazamiento de celdas
    np.testing.assert_allclose(c1["c4_40"].to_numpy(), c2["c4_40"].to_numpy(), atol=0.05, equal_nan=True)
    assert abs(shift) > 0


def test_no_future_information():
    s, vap, b0 = series()
    a = F.awd(s)
    full = F.family_c(s, vap, b0, a, 40)
    k = 380
    s2, vap2 = s.copy(), vap.copy()
    s2.loc[k:, ["c", "h", "l", "o"]] *= 3
    s2.loc[k:, "v"] *= 10
    vap2[k:] *= 10
    cut = F.family_c(s2, vap2, b0, F.awd(s2), 40)
    pd.testing.assert_frame_equal(full.iloc[:k], cut.iloc[:k])
    assert full["ai_40_80"].notna().sum() > 0


def test_momentum_filters_no_future():
    s, _, _ = series(n=320)
    spy = pd.Series(np.linspace(200, 260, len(s)), index=s["date"])
    m = F.momentum_filters(s, spy)
    s2 = s.copy()
    s2.loc[300:, "c"] *= 5
    m2 = F.momentum_filters(s2, spy)
    pd.testing.assert_frame_equal(m.iloc[:300], m2.iloc[:300])


def test_intraday_outage_day_is_not_a_session():
    """Enmienda 8: un día de caída de datos no anula 120 percentiles; equivale a quitar el día de la serie intradía."""
    rng = np.random.default_rng(3)
    n = 400
    s = pd.DataFrame({"v": rng.lognormal(10, 0.3, n), "c": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                      "er": rng.uniform(0.05, 0.6, n)})
    skip = np.zeros(n, bool)
    skip[250] = True
    s.loc[250, "er"] = 0.0                       # dato basura del día caído
    a = F.awd(s, intraday_skip=skip)
    assert np.isnan(a["p_awd_i"].iloc[250])
    assert a["p_awd_i"].iloc[251:].notna().all()
    # sin el día: la ER y su mediana coinciden con la serie quitada (rv usa el volumen diario de todas las sesiones)
    keep = ~skip
    er_k = s["er"].to_numpy()[keep]
    ref_desp = er_k / F.prev_median(er_k)
    rv_k = a["rv"].to_numpy()[keep]
    ref = np.log(rv_k) - np.log(ref_desp + F.EPS_DESP)
    got = a["awd_i"].to_numpy()[keep]
    m = ~np.isnan(ref)
    assert np.allclose(got[m], ref[m])
