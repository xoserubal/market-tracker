"""Pruebas de micro/outcomes.py: prueba cerrada, ajuste por splits sin futuro, rentabilidad total y salidas."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import outcomes as oc  # noqa: E402

DAYS = ["2021-01-04", "2021-01-05", "2021-01-06", "2021-01-07", "2021-01-08", "2021-01-11"]


def bars(rows):
    return pd.DataFrame(rows, columns=["date", "o", "h", "l", "c", "v"])


def test_guard_blocks_test_period():
    oc.guard("2021-10-29")
    with pytest.raises(oc.TestPeriodLocked):
        oc.guard("2021-11-01")
    with pytest.raises(oc.TestPeriodLocked):          # sin preregistro definitivo congelado no hay modo confirmatorio
        oc.guard("2024-01-02", confirmatory=True)


def test_adjust_window_uses_only_past_splits():
    b = bars([(d, 100, 100, 100, 100, 10) for d in DAYS])
    sp = pd.DataFrame({"symbol": "X", "ex_date": ["2021-01-06", "2021-01-08"], "factor": [2.0, 4.0]})
    a = oc.adjust_window(b, sp, "2021-01-07")          # el split del 8 aún no ha ocurrido en t
    assert a["c"].tolist() == [50, 50, 100, 100] and a["v"].tolist() == [20, 20, 10, 10]


def test_total_return_with_split_and_dividend():
    b = bars([("2021-01-04", 10, 10, 10, 10, 1), ("2021-01-05", 10, 10, 10, 10, 1), ("2021-01-06", 5, 5, 5, 5, 1),
              ("2021-01-07", 5.5, 5.5, 5.5, 5.5, 1)])
    sp = pd.DataFrame({"symbol": "X", "ex_date": ["2021-01-06"], "factor": [2.0]})
    dv = pd.DataFrame({"symbol": "X", "ex_date": ["2021-01-07"], "rate": [0.1], "special": False, "foreign": False})
    r, st = oc.total_return(b, sp, dv, DAYS, "2021-01-04", 3)
    # 1 acción a 10 -> 2 acciones a 5,5 + 2 × 0,10 de dividendo = 11,2
    assert st == "ok" and r == pytest.approx(0.12)
    with pytest.raises(oc.TestPeriodLocked):
        oc.total_return(b, sp, dv, DAYS + ["2022-01-03"], "2022-01-03", 1)


def test_total_return_flags_end_of_series():
    b = bars([("2021-01-04", 10, 10, 10, 10, 1), ("2021-01-05", 10, 10, 10, 10, 1)])
    e = pd.DataFrame(columns=["symbol", "ex_date", "factor"])
    d = pd.DataFrame(columns=["symbol", "ex_date", "rate", "special", "foreign"])
    assert oc.total_return(b, e, d, DAYS, "2021-01-04", 3)[1] == "beyond_data"


def test_liquidate_exits():
    cash = {"type": "cash_mergers", "cash": 104.0, "acquirer_rate": 0, "acquiree_rate": 0}
    assert oc.liquidate_exit(100.0, 103.9, cash) == (pytest.approx(0.04), "cash")
    stk = {"type": "stock_mergers", "cash": 0.0, "acquirer_rate": 0.5, "acquiree_rate": 1.0}
    assert oc.liquidate_exit(100.0, 110.0, stk, acquirer_return_after=0.10)[0] == pytest.approx(0.21)
    mix = {"type": "stock_and_cash_mergers", "cash": 20.0, "acquirer_rate": 0.5, "acquiree_rate": 1.0}
    assert oc.liquidate_exit(100.0, 110.0, mix, acquirer_return_after=0.10)[0] == pytest.approx(0.19)
    wl = {"type": "worthless_removals", "cash": 0.0, "acquirer_rate": 0, "acquiree_rate": 0}
    assert oc.liquidate_exit(100.0, 10.0, wl)[0] == pytest.approx(-0.93)
    assert oc.liquidate_exit(100.0, 90.0, None) == (pytest.approx(-0.10), "unknown_last_close")
