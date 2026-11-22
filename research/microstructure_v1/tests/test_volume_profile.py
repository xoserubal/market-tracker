"""Pruebas sin red de micro/volume_profile.py (VP1, 2026-11-21)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import volume_profile as VP  # noqa: E402


def _tr(rows):
    return pd.DataFrame([{"price": p, "size": s, "upd_vol": v, "canceled": False, "segment": seg}
                         for p, s, v, seg in rows])


def test_observed_respects_volume_rule_and_variants():
    tr = _tr([(100.00, 100, True, "continuous"), (100.04, 50, True, "late_report"), (100.30, 999, False, "official_print"),
              (100.20, 300, True, "close_auction")])
    o = VP.observed(tr, 0.10)
    assert o.sum() == 450 and 1003 not in o.index                # la impresión oficial no suma
    assert VP.observed(tr, 0.10, exclude_late=True).sum() == 400
    assert VP.observed(tr, 0.10, exclude_auctions=True).sum() == 150


def test_estimated_methods_conserve_volume_and_match_single_trade_bars():
    bars = pd.DataFrame({"o": [10.0, 10.5], "h": [10.4, 10.9], "l": [9.9, 10.5], "c": [10.2, 10.6], "v": [1000, 3000],
                         "vw": [10.1, 10.7]})
    for m in VP.METHODS:
        e = VP.estimated(bars, 0.1, m)
        assert abs(e.sum() - 4000) < 1e-6, m
    assert VP.estimated(bars, 0.1, "close").to_dict() == {102: 1000.0, 106: 3000.0}
    u = VP.estimated(bars.iloc[:1], 0.1, "uniform")
    assert list(u.index) == [99, 100, 101, 102, 103, 104] and np.allclose(u.to_numpy(), 1000 / 6)
    t = VP.estimated(bars.iloc[:1].assign(vw=10.13), 0.1, "triangular")
    assert t.idxmax() == 101 and abs(t.sum() - 1000) < 1e-6       # pico en el nivel que contiene el VWAP (10,13)


def test_value_area_and_identical_profiles():
    p = pd.Series({100: 10.0, 101: 50.0, 102: 30.0, 103: 5.0, 104: 5.0})
    lo, hi, poc = VP.value_area(p)
    assert poc == 101 and (lo, hi) == (101, 102)                  # 80 de 100 ya supera el 70 %
    c = VP.compare(p, p, 0.1, 10.0)
    assert c["poc_same"] and c["tvd"] == 0 and c["va_jaccard"] == 1 and c["hvn_jaccard"] == 1


def test_compare_detects_shifted_poc():
    a = pd.Series({100: 10.0, 101: 80.0, 102: 10.0})
    b = pd.Series({100: 10.0, 101: 10.0, 102: 80.0})
    c = VP.compare(a, b, 0.05, 10.0)
    assert not c["poc_same"] and c["poc_diff_levels"] == 1 and c["poc_diff_bps"] == 50.0 and c["tvd"] == 0.7


def test_split_factor_common_scale():
    sp = pd.DataFrame([{"ex_date": "2026-06-10", "factor": 4.0, "type": "forward_splits"},
                       {"ex_date": "2026-09-01", "factor": 0.1, "type": "reverse_splits"}])
    assert VP.split_factor(sp, "2026-06-01", "2026-06-20") == 0.25          # 400 $ antes del 4:1 -> 100 $
    assert VP.split_factor(sp, "2026-06-01", "2026-09-10") == 2.5           # y después del 1:10 -> 1000 $
    assert VP.split_factor(sp, "2026-09-10", "2026-06-01") == 0.4
    assert VP.split_factor(sp, "2026-07-01", "2026-08-01") == 1.0
    assert VP.split_factor(None, "2026-07-01", "2026-08-01") == 1.0


def test_grid_step():
    assert VP.grid_step(150.0, 0.001) == 0.15 and VP.grid_step(3.0, 0.0005) == 0.01
