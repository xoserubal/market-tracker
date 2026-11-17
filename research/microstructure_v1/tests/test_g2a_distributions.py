"""Enmienda 7: splits coherentes, eventos y ventana de exclusión (sin red ni datos de mercado)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from micro import distributions as D  # noqa: E402


def _bars(prices, start="2020-01-02", symbol="X", asof=None):
    dates = pd.bdate_range(start, periods=len(prices)).strftime("%Y-%m-%d")
    return pd.DataFrame({"date": dates, "c": prices, "symbol": symbol, "asof": asof})


def _splits(rows):
    return pd.DataFrame(rows, columns=["symbol", "ex_date", "factor"])


def test_true_split_is_applied():
    g = _bars([100, 101, 50.6, 51])            # 2:1 el tercer día
    st = D.split_status(g, _splits([("X", g["date"][2], 2.0)]))
    assert st["status"].iloc[0] == "applied"


def test_spin_ratio_coded_as_split_is_rejected():
    g = _bars([60, 60.5, 39.0, 39.2])          # escisión: cae un 35 %, Alpaca dice «split 1:3»
    st = D.split_status(g, _splits([("X", g["date"][2], 1 / 3)]))
    assert st["status"].iloc[0] == "incoherent"


def test_split_on_wrong_entity_is_rejected():
    g = _bars([50, 50.1, 50.0, 50.2])          # sin salto; el registro (0,8824) era de otra empresa
    st = D.split_status(g, _splits([("X", g["date"][2], 0.8824)]))
    assert st["status"].iloc[0] == "incoherent"


def test_value_split_within_tolerance_is_applied():
    g = _bars([100, 100, 67.2, 67])            # DWDP: factor 1,487 con cociente 0,672
    st = D.split_status(g, _splits([("X", g["date"][2], 1.487)]))
    assert st["status"].iloc[0] == "applied"


def test_excluded_mask_window():
    cal = list(pd.bdate_range("2019-01-01", periods=1000).strftime("%Y-%m-%d"))
    pos = {d: i for i, d in enumerate(cal)}
    ev = [cal[500]]
    m = D.excluded_mask(cal, ev, pos)
    idx = np.where(m)[0]
    # (e, t) fuera si el evento cae en [t - 259, t + 40]  ->  t en [500 - 40, 500 + 259]
    assert idx.min() == 500 - D.HORIZON and idx.max() == 500 + D.LOOKBACK
    assert m.sum() == D.LOOKBACK + D.HORIZON + 1


def test_switch_with_jump_is_identity_break_but_rename_is_not():
    a = _bars([20.0] * 5, symbol="AA", asof="2016-10-28")
    b = _bars([12.3] * 5, start="2020-01-09", symbol="ARNC", asof="2020-03-30")   # salto 0,615 al cambiar de tramo
    g = pd.concat([a, b], ignore_index=True)
    act = {"splits": _splits([]), "dividends": pd.DataFrame(columns=["symbol", "ex_date", "rate", "special", "foreign"])}
    spin = pd.DataFrame(columns=["source_symbol", "new_symbol", "ex_date"])
    cur = pd.DataFrame(columns=["entity", "ex_date", "parent", "child", "source"])
    _, ev = D.entity_events("E", g, {"AA", "ARNC"}, act, spin, cur)
    assert (ev["kind"] == "E3_cambio_tramo").sum() == 1
    r = pd.concat([_bars([30.0] * 5, symbol="FB", asof="2023-01-12"),
                   _bars([30.3] * 5, start="2020-01-09", symbol="META")], ignore_index=True)
    _, ev2 = D.entity_events("E", r, {"FB", "META"}, act, spin, cur)
    assert ev2.empty


def test_big_dividend_is_event():
    g = _bars([125.0, 125.0, 22.0, 22.1])
    dv = pd.DataFrame([("X", g["date"][2], 103.75, False, False)], columns=["symbol", "ex_date", "rate", "special", "foreign"])
    act = {"splits": _splits([]), "dividends": dv}
    spin = pd.DataFrame(columns=["source_symbol", "new_symbol", "ex_date"])
    cur = pd.DataFrame(columns=["entity", "ex_date", "parent", "child", "source"])
    _, ev = D.entity_events("E", g, {"X"}, act, spin, cur)
    assert list(ev["kind"]) == ["E1_dividendo_grande"]
