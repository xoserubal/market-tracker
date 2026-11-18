"""Pruebas sin red de la línea de eventos intradía (E1).

Cubren: bloqueo del periodo reservado, tramos y denominadores, cierres anticipados y cambio de hora, minutos sin barra,
estabilidad de I1/I2, normalización y resolución de percentiles, ausencia de mirada al futuro en la detección,
episodios, selección diaria, idempotencia del registro, unidades sin cerrar, y el laboratorio (ciego y bloqueo).
"""
import json
import sys
import threading
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
from micro import calendar, download, episode, event_catalog as cat, event_scan, event_store, \
    intraday_features as F, sessions, storage, test_guard  # noqa: E402
from micro.manifest import Manifest  # noqa: E402


# ── calendario sintético: días hábiles 15-sep a 30-nov 2026, festivo 26-nov, cierre anticipado 27-nov ──
@pytest.fixture
def cal(tmp_path, monkeypatch):
    d = tmp_path / "microdata"
    monkeypatch.setenv("MICRO_DATA_DIR", str(d))
    from micro import config
    monkeypatch.setattr(config, "MIN_FREE_GB", 0.5)
    calendar.load.cache_clear()
    rows = []
    for x in pd.bdate_range("2026-09-01", "2026-11-30"):
        ds = x.strftime("%Y-%m-%d")
        if ds == "2026-11-26":
            continue
        early = ds == "2026-11-27"
        rows.append({"date": ds, "open": "09:30", "close": "13:00" if early else "16:00", "session_open": "0400",
                     "session_close": "1700" if early else "2000"})
    for ds in ("2021-10-28", "2021-10-29", "2026-03-06", "2026-03-09"):
        rows.append({"date": ds, "open": "09:30", "close": "16:00", "session_open": "0400", "session_close": "2000"})
    storage.write_parquet_atomic(pd.DataFrame(rows).sort_values("date"), calendar.cache_path())
    calendar.load.cache_clear()
    yield d
    calendar.load.cache_clear()


def synth_bars(day, seed, *, spike=None, thin=None, vol_mult=1.0):
    """Barras sintéticas de un día: continua cada minuto, pre/post cada 5 min, perfil de volumen en U."""
    rng = np.random.default_rng(seed)
    b = sessions.bounds(day)
    o, c, e = b["open_slot"], b["close_slot"], b["end_slot"]
    rows, px = [], 100.0
    for s in range(0, e):
        if s < o or s > c:
            if s % 5:
                continue
            v = 200.0
        else:
            k = (s - o) / max(1, c - o)
            v = 1000.0 * (1 + 3 * (k - 0.5) ** 2 * 4) * vol_mult
        r = rng.normal(0, 0.0005)
        if spike and spike[0] <= s < spike[1]:
            v *= 12
        if thin and thin[0] <= s < thin[1]:
            r, v = 0.003, v * 0.6
        px *= np.exp(r)
        t = sessions.slot_time(b, s)
        rows.append({"t": t, "o": px / np.exp(r), "h": px * 1.0003, "l": px / 1.0003, "c": px, "v": float(round(v)),
                     "n": max(1, round(v / 50)), "vw": px})
    df = pd.DataFrame(rows)
    df["_day"], df["_unit"] = day, f"synthetic|{day}"
    return df


def days_until(day, n):
    ds = [d for d in calendar.trading_days("2026-09-15", day) if d < day]
    return ds[-n:]


# ── bloqueo del periodo reservado ──
def test_guard_boundaries_and_logging(cal):
    assert not test_guard.reserved("2021-10-28") and test_guard.reserved("2021-10-29")
    assert test_guard.reserved("2026-09-14") and not test_guard.reserved("2026-09-15")
    assert test_guard.allowed(["2021-10-28", "2022-05-02", "2026-09-15"]) == ["2021-10-28", "2026-09-15"]
    with pytest.raises(test_guard.TestPeriodLocked):
        test_guard.check(["2024-01-02"], symbol="X", purpose="p", script="s")
    test_guard.check(["2024-01-02"], symbol="X", purpose="p", script="s", allow=True)
    log = (storage.root() / "library" / "test_period_usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(log[-1])["day"] == "2024-01-02"


def test_baseline_days_never_reserved(cal):
    assert all(not test_guard.reserved(d) for d in event_scan.baseline_days("2026-11-13"))
    assert event_scan.baseline_days("2026-11-13")[0] >= "2026-09-15"


# ── tramos ──
def mk_trades(day, rows):
    """rows: (HH:MM:SS NY, precio, tamaño, condiciones, mercado)"""
    raw = pd.DataFrame([{"t": pd.Timestamp(f"{day} {h}", tz="America/New_York").tz_convert("UTC"), "p": p, "s": s,
                         "c": c, "x": x, "z": "C", "u": None} for h, p, s, c, x in rows])
    return episode.label_trades(raw, day)


def test_segments_denominators_and_official_prints(cal):
    day = "2026-11-13"
    tr = mk_trades(day, [
        ("08:00:00", 99.0, 100, "@|T", "P"),            # premercado
        ("09:30:00", 100.0, 5000, "@|O|X", "Q"),        # subasta de apertura
        ("09:30:00", 100.0, 5000, "@|Q", "Q"),          # apertura oficial: informativa, sin volumen
        ("10:00:00", 101.0, 1000, "@", "Q"),            # continua
        ("11:00:00", 102.0, 1000, "@|F", "D"),          # continua TRF
        ("12:00:00", 150.0, 50, "@|I", "D"),            # odd lot: suma volumen, no actualiza máx./mín.
        ("13:00:00", 90.0, 300, "@|Z", "D"),            # comunicación tardía fuera de secuencia
        ("16:00:00", 103.0, 8000, "@|6|X", "Q"),        # subasta de cierre
        ("16:00:00", 103.0, 8000, "@|M", "Q"),          # cierre oficial: informativo
        ("16:05:00", 103.0, 700, "@|T|P", "D"),         # comunicación tardía a precio de referencia
        ("16:30:00", 104.0, 200, "@|T", "P"),           # after hours
    ])
    s = sessions.segment_summary(tr, day)
    S = s["segments"]
    assert S["open_auction"]["shares"] == 5000 and S["close_auction"]["shares"] == 8000
    assert S["official_print"]["shares"] == 0 and S["official_print"]["prints"] == 2
    assert S["continuous"]["shares"] == 2050 and S["continuous"]["high"] == 102.0     # el odd lot no fija el máximo
    assert S["late_report"]["shares"] == 1000 and S["post"]["shares"] == 200 and S["pre"]["shares"] == 100
    assert s["denominators"] == {"continuous": 2050, "regular_with_auctions": 15050, "day_total": 16350}
    assert s["shares_of"]["close_auction"]["vs_continuous"] == round(8000 / 2050, 4)
    assert s["prices"]["official_close"] == 103.0 and s["prices"]["last_continuous"] == 102.0


def test_early_close_and_dst_slots(cal):
    b = sessions.bounds("2026-11-27")
    assert b["early_close"] and b["close_slot"] == 9 * 60 and b["end_slot"] == 13 * 60
    a, c = sessions.bounds("2026-03-06"), sessions.bounds("2026-03-09")       # antes y después del cambio de hora
    assert a["open_slot"] == c["open_slot"] == 330
    assert (c["open"] - a["open"]).total_seconds() / 3600 == pytest.approx(71.0)   # 3 días menos 1 h
    assert sessions.bar_segment(b["close_slot"], b) == "close_mixed"
    assert sessions.bar_segment(b["open_slot"], b) == "open_mixed"


def test_minute_status_distinguishes_no_trade_from_missing(cal):
    day = "2026-11-13"
    bars = synth_bars(day, 1)
    b = sessions.bounds(day)
    drop = [sessions.slot_time(b, b["open_slot"] + 10), sessions.slot_time(b, b["open_slot"] + 200)]
    bars = bars[~bars["t"].isin(drop)]
    tr = mk_trades(day, [("10:00:00", 100, 100, "@", "Q")])
    cov = [(b["open"], b["open"] + pd.Timedelta(hours=1))]                      # trades solo de la primera hora
    ms = sessions.minute_status(bars, day, tr, cov)
    assert ms["continuous_without_bar"] == 2 and ms["no_trade"] == 1 and ms["missing_data"] == 1


# ── medidas ──
def build(day, extra=None, n=40, **kw):
    base = days_until(day, n)
    frames = [synth_bars(d, i) for i, d in enumerate(base)] + [synth_bars(day, 999, **kw)]
    bars = pd.concat(frames, ignore_index=True)
    M = F.build_matrix(bars, base + [day])
    prof = F.build_profile(M, list(range(len(base))))
    return M, prof, base


def test_thin_move_detected_and_not_volume(cal):
    day = "2026-11-13"
    M, prof, base = build(day, thin=(400, 415))
    di = M.idx(day)
    m = F.day_measures(M, di, prof, None)
    bv = [F.day_measures(M, i, prof, None)["I1_thin_up"]["value"] for i in range(len(base))]
    nm = F.normalize(m["I1_thin_up"]["value"], np.array(bv))
    assert nm["flag"] and nm["exceeds_baseline_max"]
    vv = [F.day_measures(M, i, prof, None)["V1_15"]["value"] for i in range(len(base))]
    assert not F.normalize(m["V1_15"]["value"], np.array(vv))["flag"]


def test_detection_uses_only_past_data(cal):
    """La primera vela que cruza la referencia es la misma aunque se borren los datos posteriores."""
    day = "2026-11-13"
    M, prof, base = build(day, spike=(500, 520))           # minutos 500-520 = 12:20-12:40 NY
    di = M.idx(day)
    bv = np.array([F.day_measures(M, i, prof, None)["V1_5"]["value"] for i in range(len(base))])
    full = F.day_measures(M, di, prof, None)["V1_5"]
    thr = F.normalize(full["value"], bv)["threshold"]
    first = F.crossings(full["series"], thr, 5)[0]["first"]
    for arr in (M.O, M.H, M.L, M.C, M.V, M.N, M.VW):
        arr[di, first + 1:] = np.nan
    trunc = F.day_measures(M, di, prof, None)["V1_5"]
    assert F.crossings(trunc["series"], thr, 5)[0]["first"] == first


def test_stability_with_zero_volume_and_flat_prices(cal):
    day = "2026-11-13"
    M, prof, base = build(day)
    di = M.idx(day)
    M.V[di, :] = 0.0
    M.C[di, :] = 100.0
    M.O[di, :] = M.H[di, :] = M.L[di, :] = 100.0
    m = F.day_measures(M, di, prof, None)
    for k, v in m.items():
        if k.startswith("_"):
            continue
        assert v["value"] is None or not np.isinf(v["value"]), k
        if v["series"] is not None:
            assert not np.isinf(v["series"][np.isfinite(v["series"]) | np.isinf(v["series"])]).any(), k


def test_early_close_measures_use_the_real_close(cal):
    day = "2026-11-27"
    M, prof, base = build(day)
    m = F.day_measures(M, M.idx(day), prof, None)
    b = sessions.bounds(day)
    assert m["C1_10"]["fixed_slot"] == b["close_slot"] and m["V3_close_est"]["window"][0] == b["close_slot"]
    assert m["_quality"]["early_close"] and m["_quality"]["continuous_minutes"] == b["close_slot"] - b["open_slot"] - 1


def test_normalize_resolution_and_degenerate_mad(cal):
    base = np.arange(60, dtype=float)
    nm = F.normalize(59.0, base)
    assert not nm["flag"] and nm["resolution_pct"] == round(100 / 60, 2)
    assert F.normalize(59.5, base)["flag"] and F.normalize(59.5, base)["exceeds_baseline_max"]
    zeros = np.zeros(60)
    z = F.normalize(0.0, zeros)
    assert z["z"] is None and not z["flag"]                      # MAD nula: sin z, solo percentil


def test_fixed_two_sided_uses_magnitude(cal):
    """Regresión: partir una medida fija en _up/_dn con ceros inflaba el z robusto."""
    out = {}
    F._fixed_two("C1_30", -2.0, 10, (0, 10), out, "continuous")
    assert out["C1_30"]["value"] == 2.0 and out["C1_30"]["sign"] == -1
    base = np.array([1.0, -1.2, 0.9, -1.1, 1.3, -0.8] * 10)
    assert not F.normalize(abs(-1.25), np.abs(base))["flag"]


# ── episodios, selección y registro ──
def alert(sym, code, st, en, z=5.0, status="candidate_bars"):
    t = lambda h: pd.Timestamp(f"2026-11-13 {h}", tz="America/New_York").tz_convert("UTC")
    return {"symbol": sym, "day": "2026-11-13", "code": code, "t_start_utc": t(st), "t_end_utc": t(en),
            "t_detectable_utc": t(en), "z": z, "segment": "continuous", "status": status}


def test_group_episodes_merges_nearby_and_keeps_alerts():
    al = [alert("A", "D1", "10:00", "10:05"), alert("A", "V1", "10:12", "10:20"), alert("A", "C1", "15:30", "16:00"),
          alert("B", "D1", "10:00", "10:05")]
    eps = cat.group_episodes(al)
    assert len(eps) == 3
    a = [e for e in eps if e["symbol"] == "A"]
    assert sorted(len(e["codes"]) for e in a) == [1, 2]
    assert all(x.get("episode_id") for x in al)


def test_select_for_drilldown_diversified_deterministic():
    al = [alert(s, c, "10:00", "10:05", z=z) for s, c, z in
          [("A", "D1", 9), ("A", "V1", 8), ("B", "D1", 7), ("C", "I1", 6), ("D", "P3", 5), ("E", "C1", 4), ("F", "D2", 3)]]
    for i, a in enumerate(al):
        a["t_start_utc"] += pd.Timedelta(hours=i % 2 * 3)
    eps = cat.group_episodes(al)
    s1 = cat.select_for_drilldown(eps, list("ABCDEFGH") + ["SPY"], "2026-11-13")
    s2 = cat.select_for_drilldown(eps, list("ABCDEFGH") + ["SPY"], "2026-11-13")
    syms = [e["symbol"] for e in s1["priority"]]
    assert len(syms) == len(set(syms)) <= 5 and s1 == s2 and len(s1["controls"]) == 2
    assert not set(c["symbol"] for c in s1["controls"]) & set(syms)


def test_store_write_day_replaces_scanned_symbols(cal):
    df1 = pd.DataFrame([{"symbol": "A", "pass": "full", "x": 1}, {"symbol": "B", "pass": "full", "x": 2}])
    event_store.write_day("alerts", "2026-11-13", df1)
    event_store.write_day("alerts", "2026-11-13", pd.DataFrame([{"symbol": "A", "pass": "full", "x": 3}]),
                          replace=[("A", "full"), ("B", "full")])          # B se queda sin alertas
    r = event_store.read("alerts", "2026-11-13")
    assert r.to_dict("records") == [{"symbol": "A", "pass": "full", "x": 3}]


def test_unclosed_session_unit_requires_cap(cal):
    today = pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")
    if not calendar.is_trading_day(today):
        pytest.skip("hoy no es sesión en el calendario sintético")
    b = sessions.bounds(today)
    if pd.Timestamp.now(tz="UTC") > b["full_close"] + pd.Timedelta(minutes=16):
        pytest.skip("la sesión de hoy ya está cerrada")
    with pytest.raises(ValueError):
        download._window("bars", today, download.config_for("bars", bars_window="day"))


def test_split_day_gap_is_artifact(cal, monkeypatch):
    day = "2026-11-13"
    base = event_scan.baseline_days(day)
    frames = [synth_bars(d, i) for i, d in enumerate(base)]
    tb = synth_bars(day, 5)
    for k in ("o", "h", "l", "c", "vw"):
        tb[k] = tb[k] / 4                                                      # división 4:1 sin ajustar
    bars = pd.concat(frames + [tb], ignore_index=True)
    monkeypatch.setattr(F, "load_bars", lambda s, d, m=None: bars[bars["_day"].isin(d)])
    monkeypatch.setattr(event_scan, "coverage", lambda s, m=None: {})
    r = event_scan.scan_symbol("X", day, "regular", corp={"X": [["forward_splits", day]]})
    gaps = [a for a in r["alerts"] if a["measure"] in ("C5_gap", "PRE_ret")]
    assert gaps and all(a["status"] == "artifact" for a in gaps)


# ── laboratorio ──
def _register_bars(df, symbol, day):
    m = Manifest()
    cfg = download.config_for("bars", bars_window="day")
    key = download.unit_key("alpaca", "bars", symbol, None, day, cfg)
    path = storage.raw_path("alpaca", "bars", symbol, None, day, download.config_hash(cfg))
    raw = df[["t", "o", "h", "l", "c", "v", "n", "vw"]].copy()
    raw["t"] = raw["t"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    digest, size = storage.write_parquet_atomic(raw, path)
    m.start(key, {"provider": "alpaca", "kind": "bars", "symbol": symbol, "asof": "-", "period": day,
                  "config_hash": download.config_hash(cfg), "config": cfg, "code_version": "t"})
    m.finish(key, "ok", path=str(path), sha256=digest, file_bytes=size, rows=len(raw))


def test_lab_bars_blind_and_test_lock(cal, tmp_path):
    import server
    from micro.library import Library
    day = "2026-11-13"
    _register_bars(synth_bars(day, 3), "ZZZ", day)
    srv = server.make_server(0, Library(tmp_path / "lib.sqlite") if "db_path" in Library.__init__.__code__.co_varnames
                             else Library())
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    port = srv.server_address[1]
    get = lambda q: json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{q}").read())
    try:
        full = get(f"/api/bars?symbol=ZZZ&day={day}")
        blind = get(f"/api/bars?symbol=ZZZ&day={day}&blind=1&cursor=11:00")
        cur = pd.Timestamp(f"{day} 11:00", tz="America/New_York").tz_convert("UTC").value // 1_000_000
        assert len(full["bars"]) > len(blind["bars"]) > 0
        assert max(b["t"] for b in blind["bars"]) + 60000 <= cur
        locked = get("/api/bars?symbol=ZZZ&day=2024-01-02")
        assert locked.get("test_period_locked") is True
        locked_fp = get("/api/footprint?symbol=ZZZ&day=2024-01-02")
        assert locked_fp.get("test_period_locked") is True
    finally:
        srv.shutdown()
