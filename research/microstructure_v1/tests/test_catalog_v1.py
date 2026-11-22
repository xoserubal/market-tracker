"""Pruebas sin red de cat-v1 (micro/catalog_v1.py) y de la convivencia con cat-v0.

Cubren: hash de los parámetros congelados, transformaciones idénticas a E2, regla M1 con tolerancia de empate,
criterios de las medidas discretas, V3_close_est sin alerta, D3_gap con liquidez, línea base corta, ventanas reales
(rachas y medidas de resumen como punto), episodios por tramo, instantes, conocimiento del umbral, y que el registro
de cat-v1 no toca el de cat-v0.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import catalog_v1 as V, event_store, sessions  # noqa: E402

P = V.params()


def test_params_hash_and_tamper(tmp_path, monkeypatch):
    assert P["catalog_version"] == "cat-v1"
    bad = tmp_path / "cat_v1_params.json"
    bad.write_text(V.PARAMS_PATH.read_text(encoding="utf-8").replace('"min_n": 30', '"min_n": 29'), encoding="utf-8")
    monkeypatch.setattr(V, "PARAMS_PATH", bad)
    V.params.cache_clear()
    with pytest.raises(RuntimeError):
        V.params()
    monkeypatch.undo()
    V.params.cache_clear()
    assert V.params()["baseline"]["min_n"] == 30


def test_v0_params_frozen_and_untouched():
    import hashlib
    from micro import event_catalog as cat0
    p = V.PARAMS_PATH.parent / "cat_v0_params.json"
    h = (V.PARAMS_PATH.parent / "cat_v0_params.sha256").read_text().split()[0]
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h
    assert json.loads(p.read_text(encoding="utf-8"))["thresholds"] == cat0.THRESHOLDS


def test_transforms_match_e2():
    import e2_normalize as N
    for m in P["m1_thresholds"]:
        assert V.transform_kind(m) == N.transform_kind(m), m
    assert len(P["m1_thresholds"]) == 44


def test_general_rule_and_tie():
    m = "D1_5_up"
    base = np.linspace(0.5, 1.5, 60)
    th, fl = P["m1_thresholds"][m], P["m1_mad_floors"][m]
    med = np.median(base)
    sc = max(np.median(np.abs(base - med)) * 1.4826, fl)
    tie = med + th * sc                          # exactamente en el umbral: cuenta como marca (≥)
    assert V.evaluate(m, tie, base)["state"] == "flag"
    assert V.evaluate(m, tie - 0.01 * sc, base)["state"] == "below"
    e = V.evaluate(m, tie * 2, base)
    assert e["state"] == "flag" and e["threshold_series"] == pytest.approx(tie)


def test_special_discrete_needs_own_history_and_absolute():
    m = "P1_run_up"
    base = np.r_[np.full(55, 4.0), [5, 6, 7, 8, 14]]          # máximo de la base 14
    assert V.evaluate(m, 13.0, base)["state"] == "below"       # no supera su propia historia
    base2 = np.r_[np.full(59, 3.0), [6.0]]
    assert V.evaluate(m, 11.0, base2)["state"] == "below"      # supera su historia pero no el absoluto (> 12)
    assert V.evaluate(m, 13.0, base2)["state"] == "flag"


def test_v3_close_requires_trades_and_d3_liquidity_and_short_base():
    base = np.r_[np.zeros(30), np.full(30, 0.01)]
    e = V.evaluate("V3_close_est", 5.0, base)
    assert e["state"] == "requires_trades" and e["m1_exceeds"] in (True, False)
    e = V.evaluate("D3_gap", 40.0, np.zeros(60), liq=2.0)
    assert e["state"] == "not_evaluable" and "liquidez" in e["reason"]
    assert V.evaluate("D3_gap", 40.0, np.zeros(60), liq=50.0)["state"] == "flag"
    assert V.evaluate("D1_5_up", 9.9, np.ones(20))["state"] == "not_evaluable"


def _b(day="2019-06-03"):
    from micro import calendar
    return sessions.bounds(day)


def test_windows_run_and_point(monkeypatch):
    ser = np.zeros(960)
    ser[400:420] = np.arange(1, 21)                            # racha de 20 minutos
    w = V.windows("P1_run_up", {"series": ser, "k": 1}, 12.0)
    s0, sdet, speak, s1, pv = w[0]
    assert (s0, sdet, s1) == (400, 413, 420) and pv == 20      # empieza al iniciar la racha, se detecta al superar 12
    w = V.windows("PRE_vol", {"series": None, "window": (0, 330), "fixed_slot": 330, "value": 3.0}, 1.0)
    assert w == [(0, 330, None, 330, 3.0)]


def test_alert_rows_times_and_point_episodes():
    try:
        b = _b()
    except Exception:  # noqa: BLE001  (sin calendario local)
        pytest.skip("sin calendario")
    ev = {"family": "PM", "value": 3.0, "score_m1": 9.0, "pct_own": 100.0, "score_m2": None, "threshold_m1": 5.0,
          "threshold_series": 1.0, "n": 60, "rule": "x"}
    m = {"series": None, "window": (0, b["open_slot"]), "fixed_slot": b["open_slot"], "value": 3.0, "segment": "pre",
         "estimated": False}
    a = V.alert_rows("XYZ", "2019-06-03", "PRE_vol", m, ev, b)[0]
    assert a["representation"] == "point"
    assert a["episode_start_utc"] == a["episode_end_utc"] == a["t_detect_utc"]
    assert a["window_start_utc"] < a["t_detect_utc"]           # la ventana original se conserva
    assert a["t_available_utc"] - a["t_detect_utc"] == pd.Timedelta(minutes=15)
    assert a["threshold_knowledge"] == "in_sample_calibration"
    # dos medidas de resumen del premercado no encadenan una sesión: dos puntos en el mismo instante = un episodio
    a2 = dict(a, measure="PRE_ret_up", event_id="z")
    eps = V.group_episodes([a, a2])
    assert len(eps) == 1 and eps[0]["n_alerts"] == 2 and eps[0]["segment"] == "pre"


def test_episodes_split_by_segment_and_gap():
    t = pd.Timestamp("2019-06-03 14:00", tz="UTC")
    mk = lambda seg, s, e: {"symbol": "X", "day": "d", "segment": seg, "family": "D", "measure": "m", "code": "D1",  # noqa: E731
                            "score_m1": 1.0, "status": "candidate_bars", "threshold_knowledge": "x",
                            "t_start_utc": t + pd.Timedelta(minutes=s), "t_detect_utc": t + pd.Timedelta(minutes=s),
                            "t_end_utc": t + pd.Timedelta(minutes=e), "t_available_utc": t,
                            "episode_start_utc": t + pd.Timedelta(minutes=s), "episode_end_utc": t + pd.Timedelta(minutes=e)}
    al = [mk("continuous", 0, 5), mk("continuous", 14, 20), mk("continuous", 31, 40), mk("post", 6, 8)]
    eps = V.group_episodes(al)
    cont = sorted((e for e in eps if e["segment"] == "continuous"), key=lambda e: e["episode_start_utc"])
    assert [e["n_alerts"] for e in cont] == [2, 1]            # 14 ≤ 5+10 se une; 31 > 20+10 no
    assert any(e["segment"] == "post" for e in eps)            # otro tramo, otro episodio aunque se solape en el tiempo


def test_threshold_knowledge():
    assert V.threshold_knowledge("2018-05-01") == "in_sample_calibration"
    assert V.threshold_knowledge("2021-05-01") == "retrospective_out_of_sample"
    assert V.threshold_knowledge("2026-11-24") == "prospective"


def test_registry_versions_do_not_mix(tmp_path, monkeypatch):
    monkeypatch.setenv("MICRO_DATA_DIR", str(tmp_path / "md"))
    from micro import config
    monkeypatch.setattr(config, "MIN_FREE_GB", 0.0)
    event_store.write_day("alerts", "2026-11-20", pd.DataFrame([{"symbol": "A", "pass": "full", "x": 1}]))
    v0 = (event_store.root() / "alerts" / "2026-11-20.parquet").read_bytes()
    event_store.write_day("alerts", "2026-11-20", pd.DataFrame([{"symbol": "A", "pass": "full", "x": 2}]), version="cat-v1")
    assert (event_store.root() / "alerts" / "2026-11-20.parquet").read_bytes() == v0
    assert event_store.read("alerts", "2026-11-20")["x"].tolist() == [1]
    assert event_store.read("alerts", "2026-11-20", version="cat-v1")["x"].tolist() == [2]
    assert "cat-v1" not in event_store.days("alerts")[0]
