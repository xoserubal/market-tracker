"""Pruebas de las correcciones pedidas tras G1.5 (2026-11-15): comparación de métodos, sensibilidad a trades que no
actualizan barras, controles de memoria y corrección de planes por identidad."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
from micro import aggressor, footprint, storage  # noqa: E402
from test_lab import DAY, T0, mk_quotes, mk_trades  # noqa: E402
from test_micro import data_dir  # noqa: E402,F401


def test_compare_methods_flags_sign_disagreement(data_dir):
    # quote 9.99/10.01; trades dentro del diferencial bajando (tick: venta) pero sin tocar bid/ask
    q = mk_quotes([(0, 9.99, 10.01)])
    tr = mk_trades([(1, 10.01, 100), (2, 10.004, 500), (3, 10.002, 500), (4, 10.001, 500)])
    c = aggressor.classify(tr, q, [(T0, T0 + pd.Timedelta(minutes=5))])
    rows = footprint.compare_methods(c, DAY, tf_minutes=60)
    assert len(rows) == 1
    r = rows[0]
    assert r["methods"]["bidask"]["delta"] == 100 and r["methods"]["bidask"]["undetermined"] == 1500
    assert r["methods"]["tick"]["delta"] < 0 and r["methods"]["bidask"]["sign"] == 1
    assert r["sign_disagreement"] is True
    for m in aggressor.METHODS:            # compra + venta + indeterminado = volumen, con cualquier método
        v = r["methods"][m]
        assert v["buy"] + v["sell"] + v["undetermined"] == r["vol"]


def test_exclude_nonbar_drops_odd_lots_and_reference_option(data_dir):
    # el odd lot (I) a 12.00 no actualiza máximo/mínimo: crea un tick falso hacia arriba y su vuelta
    tr = mk_trades([(0, 10.00, 100), (1, 12.00, 10, "I"), (2, 10.01, 100), (3, 10.00, 100)])
    base = aggressor.classify(tr)
    alt = aggressor.classify(tr, ref_exclude_nonbar=True)
    assert base["side_tick"].tolist()[2] == -1              # 10.01 tras el 12.00 falso: «baja»
    assert alt["side_tick"].tolist()[2] == 1                # comparado con 10.00: sube
    sel = footprint.select(base, sessions=("regular",), exclude_nonbar=True)
    assert 12.00 not in sel["price"].tolist() and len(sel) == 3
    fp = footprint.build(base, DAY, exclude_nonbar=True, sessions=("regular",))
    assert fp["filters"]["exclude_nonbar"] is True and fp["quality"]["volume"] == 300


def test_lab_memory_guard_refuses_instead_of_loading(data_dir, monkeypatch):
    import server
    monkeypatch.setattr(server, "_avail_mb", lambda: 1000.0)
    monkeypatch.setattr(server, "estimate_peak_mb", lambda s, d: 600.0)
    monkeypatch.setattr(server, "RESERVE_MB", 2500)
    loaded = []
    monkeypatch.setattr(server, "_load_classified", lambda *a: loaded.append(a))
    server._cache[("X", DAY, ())] = {"tr": None}
    out = server.api_footprint({"symbol": "TST", "day": DAY})
    assert out.get("memory_guard") is True and "memoria insuficiente" in out["error"]
    assert not loaded and not server._cache          # se vació la caché antes de rechazar
    monkeypatch.setattr(server, "_avail_mb", lambda: 10000.0)
    assert server.ensure_memory("TST", DAY) == 600.0


def test_download_waits_for_memory(data_dir, monkeypatch):
    import g2_downloads as g
    (storage.root() / "results").mkdir(parents=True, exist_ok=True)
    seq = iter([500.0, 500.0, 5000.0, 5000.0, 5000.0])
    monkeypatch.setattr(g, "free_mem_mb", lambda: next(seq))
    monkeypatch.setattr(g, "MIN_FREE_MEM_MB", 1500)
    monkeypatch.setattr(g.time, "sleep", lambda s: None)
    g.wait_for_memory("A")
    log = (storage.root() / "results" / "g2_download_log.jsonl").read_text(encoding="utf-8")
    assert '"memory_wait"' in log and '"memory_resume"' in log


def _plan(symbol, asof, start, end):
    return pd.DataFrame([{"block_id": "dev-001", "period": "dev", "entity": "E1", "symbol": symbol, "asof": asof,
                          "start": start, "end": end, "eligible_start": start, "eligible_sessions": 3}])


def test_plan_remap_uses_identity_and_needs_evidence(monkeypatch):
    import g2_plan_corrections as pc
    days = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    ua = pd.DataFrame({"entity": "E1", "date": days, "symbol": ["NEW"] * 4, "asof": [None] * 4})
    monkeypatch.setattr(pc, "SYMBOL_CHANGES", [{"entity": "E1", "company": "Co", "old": "OLD", "new": "NEW",
                                                "first_session": "2019-12-01", "evidence": "test"}])
    out, ch, un = pc.remap(_plan("OLD", "2021-01-01", days[0], days[2]), ua, days)
    assert out.loc[0, "symbol"] == "NEW" and out.loc[0, "symbol_v1"] == "OLD" and len(ch) == 1 and not un
    assert "OLD->NEW" in out.loc[0, "correction"]
    monkeypatch.setattr(pc, "SYMBOL_CHANGES", [])
    with pytest.raises(RuntimeError, match="sin evidencia"):
        pc.remap(_plan("OLD", "2021-01-01", days[0], days[2]), ua, days)
    ua2 = ua.copy()
    ua2.loc[2, "symbol"] = "OTHER"
    with pytest.raises(RuntimeError, match="varios tickers"):
        pc.remap(_plan("NEW", None, days[0], days[3]), ua2, days)
    # tras la salida no hay asignación: se registra, no se rellena ni se sustituye
    out, ch, un = pc.remap(_plan("NEW", None, days[0], days[3]), ua.iloc[:2], days)
    assert out.loc[0, "symbol"] == "NEW" and not ch and un[0]["sessions"] == 2 and un[0]["first"] == days[2]


def test_exposure_windows_are_proportional():
    from micro.exposure import Exposure, exclusion_windows, is_excluded
    days = [f"2020-01-{d:02d}" for d in range(1, 31)]
    ex = [Exposure("E1", "AAA", days[10], days[12], "estadística", "t"),
          Exposure("E3", "BBB", days[10], days[10], "resultado visto", "t"),
          Exposure("M", "*", days[20], days[20], "dato de mercado", "t")]
    w = exclusion_windows(ex, days, lookback=5, horizon=3)
    assert [x["symbol"] for x in w] == ["BBB", "*"]                 # E1 no excluye
    assert w[0]["from"] == days[7] and w[0]["to"] == days[15]       # [d - H, d + L]
    assert is_excluded("BBB", days[8], w) and not is_excluded("CCC", days[8], w)   # solo ese valor
    assert is_excluded("CCC", days[20], w)                          # la de mercado afecta a todos
    with pytest.raises(ValueError):
        Exposure("M", "AAA", days[0], days[0], "x", "t")
