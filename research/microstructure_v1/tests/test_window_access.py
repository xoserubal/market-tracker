"""Pruebas sin red del acceso libre (micro/window_access.py, 2026-11-21)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import window_access as W  # noqa: E402
from micro.download import config_for, download_unit  # noqa: E402
from micro.manifest import Manifest  # noqa: E402
from test_micro import Resp, data_dir, provider  # noqa: E402,F401

DAY = "2026-11-13"
T0 = pd.Timestamp("2026-11-13T14:30:00Z")      # 09:30 NY


def _t(sec, p, s=100, c=(" ",), i=1, x="Q"):
    return {"t": (T0 + pd.Timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "p": p, "s": s, "x": x,
            "c": list(c), "z": "C", "i": i}


def _load(trades):
    pr = provider([Resp(200, {"trades": trades, "next_page_token": None})])
    download_unit(pr, "trades", "TST", DAY, cfg=config_for("trades", session="full", time_range="09:30-16:30"),
                  manifest=Manifest())


def test_tape_segments_by_condition_and_counts_everything(data_dir):
    _load([_t(0, 100.0, 5000, ("O",), 1), _t(60, 100.5, 100, (" ",), 2), _t(120, 99.0, 300, ("Z",), 3),
           _t(23400, 101.0, 9000, ("6",), 4), _t(23400, 101.0, 9000, ("M",), 5), _t(24000, 101.2, 50, ("T",), 6)])
    t = W.tape("TST", DAY, "09:30", "16:30")
    s = t["summary"]
    assert s["open_auction"]["shares"] == 5000 and s["continuous"]["trades"] == 1
    assert s["late_report"]["shares"] == 300 and s["close_auction"]["shares"] == 9000
    assert s["official_print"]["shares_counted_in_volume"] == 0           # M no suma volumen
    assert s["post"]["trades"] == 1
    assert s["_all"]["shares_counted_in_volume"] == 5000 + 100 + 300 + 9000 + 50
    assert {x["seg"] for x in t["trades"]} >= {"open_auction", "late_report", "close_auction"}


def test_tape_is_locked_in_reserved_period(data_dir):
    with pytest.raises(W.test_guard.TestPeriodLocked):
        W.tape("TST", "2024-03-05", "09:30", "10:00")


def test_estimate_discounts_downloaded_ranges_and_checks_limits(data_dir, monkeypatch):
    _load([_t(0, 100.0)])
    mins = pd.date_range(T0 - pd.Timedelta(hours=5, minutes=30), T0 + pd.Timedelta(hours=10, minutes=30), freq="1min")
    monkeypatch.setattr(W, "_minute_trades", lambda *a, **k: (pd.DataFrame({"t": mins, "n": 2000}), "capa1_barras"))
    e = W.estimate("TST", DAY, "09:30", "10:30", quotes=True)
    assert e["kinds"]["trades"]["missing_ranges"] == [] and e["kinds"]["trades"]["requests_est"] == 0
    assert e["kinds"]["quotes"]["missing_ranges"] == ["09:30-10:30"]
    assert e["kinds"]["quotes"]["rows_est_high"] == int(60 * 2000 * 3.5) and not e["blocked"]
    big = W.estimate("TST", DAY, "04:00", "20:00", quotes=True)
    rules = {b["rule"] for b in big["blocked"]}
    assert "ventana_quotes" in rules                       # 960 min de quotes: bloqueado
    monkeypatch.setattr(W, "requests_last_24h", lambda: 5990)
    assert "presupuesto_diario" in {b["rule"] for b in W.estimate("TST", DAY, "16:30", "17:30", quotes=False)["blocked"]}


def test_fetch_needs_confirmation_above_threshold(data_dir, monkeypatch):
    monkeypatch.setattr(W, "estimate", lambda *a, **k: {"blocked": [], "needs_confirmation": True,
                                                         "in_reserved_period": False})
    assert W.fetch("TST", DAY, "09:30", "10:30")["status"] == "needs_confirmation"
