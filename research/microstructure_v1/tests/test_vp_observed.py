"""Pruebas sin red de micro/vp_observed.py y de la corrección del cargador de trades (2026-11-22)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import episode, vp_observed as O  # noqa: E402
from micro.download import config_for, download_unit  # noqa: E402
from micro.manifest import Manifest  # noqa: E402
from test_micro import Resp, data_dir, provider  # noqa: E402,F401

DAY = "2026-11-13"
T0 = pd.Timestamp("2026-11-13T14:30:00Z")


def _t(sec, p, s=100, c=(" ",), i=1):
    return {"t": (T0 + pd.Timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "p": p, "s": s, "x": "Q",
            "c": list(c), "z": "C", "i": i}


def _unit(trades, rng):
    pr = provider([Resp(200, {"trades": trades, "next_page_token": None})])
    download_unit(pr, "trades", "TST", DAY, cfg=config_for("trades", session="full", time_range=rng), manifest=Manifest())


def test_identical_trades_with_distinct_ids_are_kept(data_dir):
    _unit([_t(5, 100.0, 100, i=1), _t(5, 100.0, 100, i=2), _t(5, 100.0, 100, i=3), _t(23400, 101, 500, ("6",), 4)],
          "09:30-16:30")
    tr, _ = episode.load_trades("TST", DAY)
    assert len(tr) == 4                                             # antes se quedaban 2
    old, _ = episode.load_trades("TST", DAY, legacy_overlap_dedupe=True)
    assert len(old) == 2
    r = O.build("TST", DAY, save=False)
    assert r["ok"] and r["profile_volume"] == 300 and r["close_auction_shares"] == 500 and r["complete_regular_session"]


def test_overlapping_units_are_not_double_counted(data_dir):
    a = [_t(5, 100.0, 100, i=1), _t(3700, 100.5, 200, i=2)]
    _unit(a, "09:30-10:30")
    _unit(a + [_t(7000, 101.0, 300, i=3)], "09:30-11:30")             # se solapa con la primera
    tr, _ = episode.load_trades("TST", DAY)
    assert tr["size"].sum() == 600
    assert O.build("TST", DAY, save=False)["profile_volume"] == 600
