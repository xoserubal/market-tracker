"""Pruebas sin red de G1.5: clasificación de agresores, footprint, biblioteca y servidor del visor (modo ciego)."""
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
from micro import aggressor, calendar, episode, footprint  # noqa: E402
from micro.download import config_for, download_unit  # noqa: E402
from micro.library import Library, ts_iso  # noqa: E402
from micro.manifest import Manifest  # noqa: E402
from test_micro import Resp, data_dir, provider  # noqa: E402,F401

DAY = "2026-11-13"
T0 = pd.Timestamp("2026-11-13T14:30:00Z")      # 09:30 NY


def mk_trades(rows):
    """rows: (segundos desde 09:30, precio, tamaño[, condiciones[, exchange[, update]]])"""
    raw = pd.DataFrame([{"t": T0 + pd.Timedelta(seconds=r[0]), "p": r[1], "s": r[2],
                         "c": r[3] if len(r) > 3 else " ", "x": r[4] if len(r) > 4 else "Q", "z": "C",
                         "u": r[5] if len(r) > 5 else None} for r in rows])
    return episode.label_trades(raw, DAY)


def mk_quotes(rows):
    return pd.DataFrame([{"t": T0 + pd.Timedelta(seconds=s), "bid": b, "ask": a, "bid_size": 1, "ask_size": 1}
                         for s, b, a in rows])


# ── regla del tick ──
def test_tick_rule_with_zero_ticks(data_dir):
    tr = mk_trades([(0, 10.00, 100), (1, 10.01, 100), (2, 10.01, 100), (3, 10.00, 100), (4, 10.00, 100), (5, 10.02, 100)])
    c = aggressor.classify(tr)
    assert c["side_tick"].tolist() == [0, 1, 1, -1, -1, 1]
    assert c["tick_kind"].astype(str).tolist() == ["no_reference", "up", "zero_up", "down", "zero_down", "up"]


def test_auction_and_canceled_do_not_enter_reference(data_dir):
    tr = mk_trades([(0, 10.00, 100), (1, 11.00, 5000, "O"), (2, 10.01, 100), (3, 12.0, 100, " ", "Q", "canceled"),
                    (4, 10.00, 100)])
    c = aggressor.classify(tr)
    assert c["side_tick"].tolist() == [0, 0, 1, 0, -1]           # 10.01 se compara con 10.00, no con la subasta 11
    assert c["excluded_reason"].astype(str).tolist() == ["", "auction", "", "canceled", ""]


# ── reglas con quotes ──
def test_quote_rules_and_lee_ready_fallback(data_dir):
    q = mk_quotes([(0, 9.99, 10.01)])
    tr = mk_trades([(1, 10.00, 100), (2, 10.01, 100), (3, 10.00, 100), (4, 10.005, 100), (5, 9.99, 100)])
    c = aggressor.classify(tr, q, [(T0, T0 + pd.Timedelta(minutes=5))])
    assert c["side_bidask"].tolist() == [0, 1, 0, 0, -1]          # dentro del diferencial -> indeterminado
    assert c["side_lr"].tolist() == [0, 1, -1, 1, -1]             # punto medio -> regla del tick (10.00 < 10.01)
    assert c["side_emo"].tolist() == [0, 1, -1, 1, -1]            # dentro -> tick (10.005 > 10.00 sube)
    assert c["spread_zone"].astype(str).tolist() == ["at_mid", "at_ask", "at_mid", "inside_upper", "at_bid"]


def test_quote_strictly_before_and_invalid_quotes(data_dir):
    q = mk_quotes([(0, 9.99, 10.01), (2, 10.05, 10.05), (4, 10.10, 10.00), (6, 0.0, 10.02)])
    tr = mk_trades([(2, 10.01, 100), (3, 10.01, 100), (5, 10.01, 100), (7, 10.01, 100)])
    c = aggressor.classify(tr, q, [(T0, T0 + pd.Timedelta(minutes=1))])
    # t=2 usa la quote de t=0 (la de t=2 es simultánea y se excluye); t=3 la bloqueada; t=5 la cruzada; t=7 lado 0
    assert c["quote_state"].astype(str).tolist() == ["ok", "locked", "crossed", "zero_side"]
    assert c["side_lr"].tolist() == [1, 0, 0, 0]
    c2 = aggressor.classify(tr, q, [(T0, T0 + pd.Timedelta(minutes=1))], strict_before=False)
    assert c2["quote_state"].astype(str).tolist()[0] == "locked"


def test_no_coverage_and_stale(data_dir):
    q = mk_quotes([(0, 9.99, 10.01)])
    tr = mk_trades([(5, 10.01, 100), (30, 10.01, 100), (120, 10.01, 100)])
    c = aggressor.classify(tr, q, [(T0, T0 + pd.Timedelta(seconds=60))], max_quote_age_s=10)
    assert c["quote_state"].astype(str).tolist() == ["ok", "stale", "no_coverage"]
    assert c["side_lr"].tolist() == [1, 0, 0]


def test_summary_shares_add_up(data_dir):
    q = mk_quotes([(0, 9.99, 10.01)])
    tr = mk_trades([(1, 10.01, 300), (2, 9.99, 100), (3, 10.00, 100, " ", "D"), (4, 10.5, 500, "O")])
    s = aggressor.summary(aggressor.classify(tr, q, [(T0, T0 + pd.Timedelta(minutes=1))]))
    for m in aggressor.METHODS:
        v = s["methods"][m]
        assert abs(v["buy_share"] + v["sell_share"] + v["undetermined_share"] - 1) < 1e-3
    assert s["by_venue"]["trf"]["volume_share"] == pytest.approx(0.1)


# ── footprint ──
def test_level_of_is_exact_on_boundaries():
    p = np.array([149.80, 149.7999, 150.00, 0.30, 149.85])
    assert footprint.level_of(p, 0.10).tolist() == [149.8, 149.7, 150.0, 0.3, 149.8]
    assert footprint.level_of(np.array([150.24, 150.25]), 0.25).tolist() == [150.0, 150.25]


def test_footprint_sums_bars_and_cursor(data_dir):
    q = mk_quotes([(0, 9.99, 10.01)])
    rows = [(10, 10.01, 100), (20, 9.99, 200), (3599, 10.01, 50), (3600, 10.20, 300), (3700, 10.10, 100),
            (3800, 10.15, 400, "Q")]                                      # Q no cuenta como volumen
    c = aggressor.classify(mk_trades(rows), q, [(T0, T0 + pd.Timedelta(hours=2))], max_quote_age_s=1e9)
    fp = footprint.build(c, DAY, method="lr", tf_minutes=60, step=0.10)
    assert [pd.Timestamp(b["t"], unit="ms", tz="UTC") for b in fp["bars"]] == [T0, T0 + pd.Timedelta(hours=1)]
    for b in fp["bars"]:
        assert b["buy"] + b["sell"] + b["auction"] + b["unclassified"] == b["vol"]
        assert sum(l["vol"] for l in fp["levels"] if l["t"] == b["t"]) == b["vol"]
    assert fp["bars"][0]["vol"] == 350 and fp["bars"][1]["vol"] == 400
    assert fp["bars"][-1]["cum_delta"] == sum(b["delta"] for b in fp["bars"])
    cut = footprint.build(c, DAY, method="lr", tf_minutes=60, step=0.10, cursor=T0 + pd.Timedelta(seconds=3600))
    assert len(cut["bars"]) == 1 and cut["quality"]["volume"] == 350        # nada a partir del cursor


def test_value_area_contains_poc(data_dir):
    tr = mk_trades([(i, 10 + (i % 7) * 0.01, 100 + (i % 7 == 3) * 900) for i in range(50)])
    fp = footprint.build(aggressor.classify(tr), DAY, method="tick", tf_minutes=60, step=0.01)
    va = fp["value_area"]
    assert va["val"] <= va["poc"] <= va["vah"] and va["share"] >= 0.70
    assert va["poc"] == pytest.approx(10.03)


# ── biblioteca ──
def test_library_retrospective_flag_from_access_log(data_dir, tmp_path):
    lib = Library(tmp_path / "lib.sqlite")
    acc = tmp_path / "acc.jsonl"
    eid = lib.add_episode({"symbol": "NVDA", "day": DAY, "start_utc": ts_iso(T0), "end_utc": ts_iso(T0 + pd.Timedelta(hours=1)),
                           "proposed_label": "absorption_buy", "outcome_known_at_selection": True})
    # sin accesos: no retrospectiva
    a0 = lib.annotate({"episode_id": eid, "label": "absorption_buy", "cursor_utc": ts_iso(T0)}, access_path=acc)
    Library.log_access({"symbol": "NVDA", "day": DAY, "max_t_returned": ts_iso(T0 + pd.Timedelta(hours=2))}, path=acc)
    a1 = lib.annotate({"episode_id": eid, "label": "absorption_buy", "cursor_utc": ts_iso(T0 + pd.Timedelta(hours=1))}, access_path=acc)
    a2 = lib.annotate({"episode_id": eid, "label": "no_pattern", "cursor_utc": ts_iso(T0 + pd.Timedelta(hours=3))}, access_path=acc)
    flags = {a["annotation_id"]: a["revealed_future"] for a in lib.annotations(eid)}
    assert flags == {a0: 0, a1: 1, a2: 0}
    with pytest.raises(ValueError):
        lib.annotate({"episode_id": eid, "label": "accumulation", "annotator_type": "ai"}, access_path=acc)
    with pytest.raises(ValueError):
        lib.annotate({"episode_id": eid, "label": "institutional_buying"}, access_path=acc)
    rows = lib.export_for_learning()
    assert not any(r["usable_as_confirmatory"] for r in rows)                # resultado conocido al elegirlo


def test_contaminated_test_dates(data_dir, tmp_path):
    acc = tmp_path / "acc.jsonl"
    Library.log_access({"symbol": "AAPL", "day": "2023-05-04"}, path=acc)
    Library.log_access({"symbol": "NVDA", "day": "2026-11-12"}, path=acc)
    Library.log_access({"symbol": "XOM", "day": "2019-03-01"}, path=acc)
    assert Library(tmp_path / "l.sqlite").contaminated_test_dates(path=acc) == [("AAPL", "2023-05-04")]


# ── servidor: el modo ciego no filtra datos posteriores ──
def _api_trade(sec, p, s=100, i=1):
    return {"t": (T0 + pd.Timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "p": p, "s": s, "x": "Q",
            "c": [" "], "z": "C", "i": i}


def test_server_blind_mode_never_returns_future(data_dir, monkeypatch):
    import server
    pr = provider([Resp(200, {"trades": [_api_trade(10, 100.0, i=1), _api_trade(1800, 101.0, i=2),
                                         _api_trade(4000, 105.0, i=3)], "next_page_token": None}),
                   Resp(200, {"quotes": [{"t": T0.strftime("%Y-%m-%dT%H:%M:%SZ"), "bp": 99.9, "bs": 1, "bx": "Q",
                                          "ap": 100.1, "as": 1, "ax": "Q", "c": ["R"], "z": "C"}], "next_page_token": None})])
    m = Manifest()
    download_unit(pr, "trades", "TST", DAY, cfg=config_for("trades", session="full", time_range="09:30-11:00"), manifest=m)
    download_unit(pr, "quotes", "TST", DAY, cfg=config_for("quotes", time_range="09:30-10:30"), manifest=m)
    srv = server.make_server(0, Library())
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    port = srv.server_address[1]
    try:
        def call(**q):
            url = f"http://127.0.0.1:{port}/api/footprint?" + "&".join(f"{k}={v}" for k, v in q.items())
            return json.loads(urllib.request.urlopen(url).read())
        base = dict(symbol="TST", day=DAY, start="09:30", end="11:00", tf="15", method="lr", step="auto")
        full = call(**base, blind="0")
        assert full["quality"]["volume"] == 300
        edge = call(**base, blind="1", cursor="10:00:00")          # el trade de las 10:00:00 no es anterior al cursor
        assert edge["quality"]["volume"] == 100
        blind = call(**base, blind="1", cursor="10:05:00")
        prices = {l["p"] for l in blind["levels"]}
        assert blind["quality"]["volume"] == 200 and max(prices) < 105
        lim = (T0 + pd.Timedelta(minutes=35)).value // 1_000_000
        assert all(b["t"] < lim for b in blind["bars"])
        assert max(r["t"] for r in blind["timeline"]) < lim
        assert blind["max_t_returned"] < ts_iso(T0 + pd.Timedelta(minutes=35))
        log = Library.accesses("TST", DAY)
        assert log[-1]["blind"] is True and log[-1]["max_t_returned"] == blind["max_t_returned"]
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode()
        assert "Laboratorio de microestructura" in page
        nodata = call(symbol="ZZZ", day=DAY, start="09:30", end="10:00")
        assert nodata.get("need_fetch") is True
    finally:
        srv.shutdown()
        srv.server_close()


def test_two_windows_same_day_do_not_overwrite(data_dir):
    """Regresión: la ruta no incluía la configuración y la segunda ventana del día pisaba a la primera."""
    from micro import storage
    pr = provider([Resp(200, {"trades": [_api_trade(10, 100.0, i=1)], "next_page_token": None}),
                   Resp(200, {"trades": [_api_trade(4000, 101.0, i=2), _api_trade(4001, 101.0, i=3)], "next_page_token": None})])
    m = Manifest()
    a = download_unit(pr, "trades", "TST", DAY, cfg=config_for("trades", session="full", time_range="09:30-10:30"), manifest=m)
    b = download_unit(pr, "trades", "TST", DAY, cfg=config_for("trades", session="full", time_range="10:30-11:30"), manifest=m)
    assert a["path"] != b["path"]
    assert m.is_done(a["unit_key"], verify_checksum=True) and m.is_done(b["unit_key"], verify_checksum=True)
    tr, cov = episode.load_trades("TST", DAY)
    assert len(tr) == 3 and len(cov) == 1                      # ventanas contiguas fusionadas


def test_episode_prices_follow_bar_rules(data_dir):
    """Regresión 2026-11-15: un trade comunicado tarde (cond. Z, no actualiza máx/mín) a un precio fuera de rango
    no debe entrar en el máximo del episodio guardado (pasó con GOOGL 2026-10-29: 323,94 frente a 288,33)."""
    import server
    late = _api_trade(1200, 130.0, i=2)
    late["c"] = ["Z"]
    pr = provider([Resp(200, {"trades": [_api_trade(10, 100.0, i=1), late, _api_trade(1800, 101.0, i=3)],
                              "next_page_token": None})])
    download_unit(pr, "trades", "TSZ", DAY, cfg=config_for("trades", session="full", time_range="09:30-11:00"),
                  manifest=Manifest())
    server.LIB = Library()
    eid = server.api_episode_create({"symbol": "TSZ", "day": DAY, "start": "09:30", "end": "11:00",
                                     "view": {"method": "tick", "tf": "60"}})["episode_id"]
    ep = [e for e in server.LIB.episodes("TSZ", DAY) if e["episode_id"] == eid][0]
    met = json.loads(ep["metrics_json"])
    assert met["price_max"] == 101.0 and met["price_min"] == 100.0
    assert met["price_first"] == 100.0 and met["price_last"] == 101.0
