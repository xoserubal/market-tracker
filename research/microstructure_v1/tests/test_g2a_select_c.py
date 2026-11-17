"""Lógica de tratados y controles de la familia C (g2a_select_c.evaluate) con un caso resuelto a mano."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import g2a_select_c as SC  # noqa: E402


def _frame():
    # fecha 2018-01-02: tratado T (sector A) y candidatos A1, A2 (sector A, AI bajo), B1 (sector B, AI bajo), A3 (AI medio)
    # episodio de T: alta también al día siguiente -> solo cuenta la primera
    rows = [  # entity, date, ai, range, dur, lnliq, sector, ex40, ep
        ("T", "2018-01-02", 0.9, 3.0, 5, 10.0, "A", 0.05, 1),
        ("T", "2018-01-03", 0.95, 3.0, 6, 10.0, "A", 0.07, 1),
        ("A1", "2018-01-02", 0.1, 3.1, 5, 10.0, "A", 0.01, 2),
        ("A2", "2018-01-02", 0.1, 4.0, 9, 11.0, "A", 0.03, 3),
        ("B1", "2018-01-02", 0.1, 3.0, 5, 10.0, "B", -0.10, 4),
        ("A3", "2018-01-02", 0.5, 3.0, 5, 10.0, "A", 0.20, 5),
        ("U", "2018-01-02", 0.9, 3.0, 5, 10.0, "C", 0.02, 6),     # sector C sin candidatos -> cualquier sector
    ]
    e = pd.DataFrame(rows, columns=["entity", "date", "ai", "range", "dur", "lnliq", "sector", "ex40", "ep"])
    e = e.sort_values(["ep", "date"]).reset_index(drop=True)
    e["liq_tercile"] = 2
    return e


def test_first_treated_and_sector_rule():
    e = _frame()
    Z = e[["range", "dur", "lnliq"]].to_numpy(float)
    VI = np.eye(3)
    n = len(e)
    nbs, nba = np.full((n, n), -1), np.full((n, n), -1)
    for i in range(n):
        same = [j for j in range(n) if j != i and e["date"][j] == e["date"][i]]
        order = sorted(same, key=lambda j: ((Z[i] - Z[j]) @ VI @ (Z[i] - Z[j]), j))
        nba[i, :len(order)] = order
        s = [j for j in order if e["sector"][j] == e["sector"][i]]
        nbs[i, :len(s)] = s
    d, S, sel = SC.evaluate(e, e["ai"].to_numpy(float), 0.8, 0.2, nbs, nba, detail=True)
    tr = e["entity"].to_numpy()[d["row"]]
    assert sorted(tr) == ["T", "U"]                       # solo la primera fecha alta del episodio de T
    dt = d[tr == "T"].iloc[0]
    assert not dt["sector_relaxed"] and dt["nctl"] == 2    # A1 y A2 (mismo sector); B1 no entra
    assert np.isclose(dt["delta"], 0.05 - (0.01 + 0.03) / 2)
    du = d[tr == "U"].iloc[0]
    assert du["sector_relaxed"] and du["nctl"] == 3        # cualquier sector: A1, B1 y A2 por cercanía
