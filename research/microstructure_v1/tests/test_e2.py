"""E2: las versiones rápidas reproducen cat-v0 y la normalización M0 reproduce intraday_features.normalize."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import calendar, download, e2_fast as X, intraday_features as F, sessions  # noqa: E402
import e2_normalize as N  # noqa: E402


def _synthetic_bars(days, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    px = 100.0
    for d in days:
        b = sessions.bounds(d)
        for s in range(b["start_slot"], b["end_slot"]):
            if s < b["open_slot"] or s >= b["close_slot"]:
                if rng.random() > 0.3:            # horario extendido con huecos
                    continue
            elif rng.random() < 0.03:             # algún minuto sin barra en continua
                continue
            r = rng.normal(0, 0.001)
            o = px
            px = px * np.exp(r)
            v = float(rng.integers(100, 5000)) * (5 if s in (b["open_slot"], b["close_slot"]) else 1)
            rows.append({"t": sessions.slot_time(b, s), "o": o, "h": max(o, px) * 1.0005, "l": min(o, px) * 0.9995,
                         "c": px, "v": v, "n": float(rng.integers(1, 50)), "vw": (o + px) / 2, "_unit": "u"})
    df = pd.DataFrame(rows)
    df["_day"] = df["t"].dt.tz_convert(F.NY).dt.strftime("%Y-%m-%d")
    return df


@pytest.fixture(scope="module")
def data():
    days = calendar.trading_days("2018-11-01", "2019-01-31")     # incluye cierres anticipados (23-nov, 24-dic)
    bars = _synthetic_bars(days)
    return days, bars


def test_matrix_fast_equal(data):
    days, bars = data
    M, M2 = F.build_matrix(bars, days), X.build_matrix_fast(bars, days)
    for k in ("O", "H", "L", "C", "V", "N", "VW"):
        assert np.array_equal(getattr(M, k), getattr(M2, k), equal_nan=True)
    assert M.units == M2.units


def test_profile_and_measures_equal(data):
    days, bars = data
    M = F.build_matrix(bars, days)
    rows = list(range(5, 45))
    P = F.build_profile(M, rows)
    P2 = X.profile_from_parts([X.day_parts(M, i) for i in rows])
    for k in P.__dataclass_fields__:
        a, b = getattr(P, k), getattr(P2, k)
        if np.ndim(a):
            assert np.array_equal(np.asarray(a, float), np.asarray(b, float), equal_nan=True), k
        else:
            assert a == b or (a != a and b != b), k
    for i in (45, 50, 55):
        m1, m2 = F.day_measures(M, i, P, 100.0), F.day_measures(M, i, P2, 100.0)
        for k in m1:
            if k == "_quality":
                continue
            x, y = m1[k]["value"], m2[k]["value"]
            assert x == y or (x != x and y != y), k


def test_m0_equals_normalize():
    rng = np.random.default_rng(3)
    n = 400
    x = rng.lognormal(0, 1, n)
    x[rng.random(n) < 0.1] = np.nan
    x[rng.random(n) < 0.05] = 1.0                                   # empates
    dates = (np.datetime64("2018-01-01") + np.arange(n) * np.timedelta64(1, "D")).astype("datetime64[D]")
    base_ok = rng.random(n) > 0.05
    W = N.windows(x, dates, base_ok)
    nn, pct, z, flag, _, _ = N.m0(x, W)
    for i in range(100, n):
        if not np.isfinite(x[i]):
            continue
        prior = [j for j in range(i) if np.isfinite(x[j]) and base_ok[j]][-N.WIN:]
        prior = [j for j in prior if (dates[i] - dates[j]).astype(int) <= N.MAX_AGE]
        r = F.normalize(x[i], x[prior])
        assert r["flag"] == bool(flag[i])
        assert abs(r["pct"] - pct[i]) < 0.011
        assert (r["z"] is None and not np.isfinite(z[i])) or abs(r["z"] - z[i]) < 0.011


def test_month_window_requires_cap_when_unfinished():
    cur = pd.Timestamp.now("UTC").strftime("%Y-%m")
    with pytest.raises(ValueError):
        download._window("bars", cur, download.config_for("bars"))
    s, e = download._window("bars", cur, download.config_for("bars", cap=pd.Timestamp.now("UTC").floor("D").isoformat()))
    assert e <= pd.Timestamp.now("UTC")
    s, e = download._window("bars", "2019-03", download.config_for("bars"))
    assert e == pd.Timestamp("2019-04-01", tz="UTC")
