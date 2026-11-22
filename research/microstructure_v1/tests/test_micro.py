"""Pruebas sin red de la infraestructura G1.  py -3 -m pytest research/microstructure_v1/tests -q"""
import json
import multiprocessing as mp
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import calendar, conditions, identity, normalize, quality, sampling, storage  # noqa: E402
from micro.download import config_for, download_unit  # noqa: E402
from micro.manifest import Manifest  # noqa: E402
from micro.providers.alpaca import AlpacaProvider  # noqa: E402
from micro.providers.base import ProviderError  # noqa: E402
from micro.ratelimit import SharedRateLimiter  # noqa: E402


# ── utilidades ──
class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.content = json.dumps(self._body).encode()
        self.text = self.content.decode()
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "microdata"
    monkeypatch.setenv("MICRO_DATA_DIR", str(d))
    from micro import config
    monkeypatch.setattr(config, "MIN_FREE_GB", 0.5)     # las pruebas corren en C: (poco espacio libre)
    calendar.load.cache_clear()
    cal = pd.DataFrame([
        {"date": "2025-11-28", "open": "09:30", "close": "13:00", "session_open": "0400", "session_close": "1700"},
        {"date": "2026-03-06", "open": "09:30", "close": "16:00", "session_open": "0400", "session_close": "2000"},
        {"date": "2026-03-09", "open": "09:30", "close": "16:00", "session_open": "0400", "session_close": "2000"},
        {"date": "2026-11-13", "open": "09:30", "close": "16:00", "session_open": "0400", "session_close": "2000"},
    ])
    storage.write_parquet_atomic(cal, calendar.cache_path())
    calendar.load.cache_clear()
    yield d
    calendar.load.cache_clear()


def provider(script, window=60, per=1000):
    lim = SharedRateLimiter(storage.root() / "_state" / "rl.sqlite", per_window=per, window_s=window)
    return AlpacaProvider("k", "s", lim, session=FakeSession(script), base_backoff=0.001, max_retries=4)


def trade(t, p=10.0, s=100, x="Q", c=(" ",), z="C", i=1):
    return {"t": t, "p": p, "s": s, "x": x, "c": list(c), "z": z, "i": i}


# ── proveedor ──
def test_pagination_collects_all_pages(data_dir):
    pr = provider([Resp(200, {"trades": [trade("2026-11-13T15:00:00Z", i=1)], "next_page_token": "a"}),
                   Resp(200, {"trades": [trade("2026-11-13T15:00:01Z", i=2)], "next_page_token": "b"}),
                   Resp(200, {"trades": [trade("2026-11-13T15:00:02Z", i=3)], "next_page_token": None})])
    pages = list(pr.fetch_pages("trades", "AAA", "s", "e"))
    assert [len(p) for p in pages] == [1, 1, 1]
    assert pr.session.calls[1][1]["page_token"] == "a" and pr.session.calls[2][1]["page_token"] == "b"


def test_retry_on_429_5xx_and_network(data_dir):
    pr = provider([Resp(429, headers={}), Resp(500), requests.ConnectionError("x"), Resp(200, {"trades": []})])
    from micro.providers.base import FetchStats
    st = FetchStats()
    assert list(pr.fetch_pages("trades", "AAA", "s", "e", stats=st)) == [[]]
    assert st.retries == 3 and st.requests == 4


def test_non_retryable_403(data_dir):
    pr = provider([Resp(403, {"message": "subscription does not permit querying recent SIP data"})])
    with pytest.raises(ProviderError) as e:
        list(pr.fetch_pages("trades", "AAA", "s", "e"))
    assert e.value.status == 403 and not e.value.retryable
    assert len(pr.session.calls) == 1


def test_retries_exhausted(data_dir):
    pr = provider([Resp(500)] * 5)
    with pytest.raises(ProviderError):
        list(pr.fetch_pages("trades", "AAA", "s", "e"))


def test_asof_nan_is_not_sent(data_dir):
    pr = provider([Resp(200, {"bars": []})])
    list(pr.fetch_pages("bars", "X", "s", "e", asof=float("nan")))
    assert "asof" not in pr.session.calls[0][1]


def test_asof_passed(data_dir):
    pr = provider([Resp(200, {"bars": []})])
    list(pr.fetch_pages("bars", "ADT", "s", "e", asof="2016-03-01", timeframe="1Day"))
    p = pr.session.calls[0][1]
    assert p["asof"] == "2016-03-01" and p["timeframe"] == "1Day" and p["adjustment"] == "raw" and p["feed"] == "sip"


# ── descarga idempotente / reanudable ──
def _pages():
    return [Resp(200, {"trades": [trade("2026-11-13T15:00:00Z", i=1), trade("2026-11-13T15:00:01Z", i=2)],
                       "next_page_token": "a"}),
            Resp(200, {"trades": [trade("2026-11-13T15:01:00Z", i=3)], "next_page_token": None})]


def test_download_idempotent_and_checksum(data_dir):
    m = Manifest()
    pr = provider(_pages())
    r1 = download_unit(pr, "trades", "AAA", "2026-11-13", manifest=m)
    assert r1["status"] == "ok" and r1["rows"] == 3
    df = pd.read_parquet(r1["path"])
    assert len(df) == 3 and str(df["t"].dtype).startswith("datetime64")
    r2 = download_unit(pr, "trades", "AAA", "2026-11-13", manifest=m)
    assert r2["status"] == "skipped" and len(pr.session.calls) == 2      # sin peticiones nuevas
    Path(r1["path"]).write_bytes(b"corrupto")                               # checksum roto -> se descarga de nuevo
    pr.session.script = _pages()
    r3 = download_unit(pr, "trades", "AAA", "2026-11-13", manifest=m)
    assert r3["status"] == "ok"
    assert any(e for e in m._c().execute("SELECT * FROM events WHERE event='checksum_mismatch'"))


def test_failure_mid_pagination_leaves_no_file_then_resumes(data_dir):
    m = Manifest()
    pr = provider([Resp(200, {"trades": [trade("2026-11-13T15:00:00Z")], "next_page_token": "a"}), Resp(403)])
    with pytest.raises(ProviderError):
        download_unit(pr, "trades", "BBB", "2026-11-13", manifest=m)
    row = m.rows("symbol='BBB'")[0]
    assert row["status"] == "failed" and row["path"] is None
    assert not list((storage.root() / "raw").rglob("*BBB*/*.parquet"))
    assert not list((storage.root() / "tmp").iterdir())
    pr.session.script = _pages()
    assert download_unit(pr, "trades", "BBB", "2026-11-13", manifest=m)["status"] == "ok"
    assert m.rows("symbol='BBB'")[0]["attempts"] == 2


def test_non_trading_day_skipped(data_dir):
    pr = provider([])
    assert download_unit(pr, "trades", "AAA", "2026-11-14", manifest=Manifest())["status"] == "not_trading_day"


def test_disk_guard(data_dir):
    with pytest.raises(storage.DiskGuardError):
        storage.disk_guard(0, min_free_gb=10 ** 9)


def test_data_dir_rejects_dropbox(monkeypatch):
    from micro import config
    monkeypatch.setenv("MICRO_DATA_DIR", "C:/Users/x/Dropbox/data")
    with pytest.raises(config.ConfigError):
        config.data_dir(create=False)


# ── limitador compartido ──
def _max_in_window(ts, w):
    ts = sorted(ts)
    j = 0
    best = 0
    for i, t in enumerate(ts):
        while ts[j] < t - w + 1e-6:
            j += 1
        best = max(best, i - j + 1)
    return best


def test_rate_limiter_threads(tmp_path):
    lim = SharedRateLimiter(tmp_path / "rl.sqlite", per_window=4, window_s=1.0)
    ts, lock = [], threading.Lock()

    def worker():
        for _ in range(3):
            t = lim.acquire()                     # hora de la concesión: medir después de acquire dependía de la
            with lock:                            # carga del equipo (fallo intermitente identificado 2026-11-21)
                ts.append(t)

    th = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert len(ts) == 12 and _max_in_window(ts, 1.0) <= 4


def _proc(db, q):
    lim = SharedRateLimiter(Path(db), per_window=4, window_s=1.0)
    for _ in range(3):
        q.put(lim.acquire())


def test_rate_limiter_processes(tmp_path):
    db = tmp_path / "rl.sqlite"
    SharedRateLimiter(db, per_window=4, window_s=1.0)
    q = mp.get_context("spawn").Queue()
    ps = [mp.get_context("spawn").Process(target=_proc, args=(str(db), q)) for _ in range(3)]
    [p.start() for p in ps]
    [p.join(60) for p in ps]
    ts = [q.get() for _ in range(9)]
    assert _max_in_window(ts, 1.0) <= 4


# ── reglas de condiciones (ejemplos del FAQ de Alpaca) ──
def test_condition_rules():
    assert conditions.minute_flags(["@", "4", "I"], "C")[1:3] == (False, True)   # solo volumen
    assert conditions.minute_flags(["@"], "C")[:3] == ("Y", True, True)
    assert conditions.minute_flags(["M"], "A")[:3] == ("N", False, False)          # cierre oficial: nada
    assert conditions.minute_flags(["9"], "A")[2] is False
    assert conditions.minute_flags(["B"], "A")[:2] == ("N", False)                 # B depende de la cinta
    assert conditions.minute_flags(["B"], "C")[:2] == ("Y", True)
    assert conditions.minute_flags(["T"], "C")[:3] == ("Y", True, True)            # T actualiza barras de minuto
    assert conditions.minute_flags(["S"], "C")[3] == ["S"]                          # código desconocido se informa


# ── calendario ──
def test_calendar_dst_and_early_close(data_dir):
    o, c = calendar.session_bounds("2026-03-06")          # EST
    assert (o.hour, o.minute, c.hour) == (14, 30, 21)
    o, c = calendar.session_bounds("2026-03-09")          # EDT tras el cambio de hora
    assert (o.hour, o.minute, c.hour) == (13, 30, 20)
    o, c = calendar.session_bounds("2025-11-28")          # cierre anticipado 13:00 NY
    assert c.hour == 18 and calendar.is_early_close("2025-11-28")
    fo, fc = calendar.session_bounds("2026-03-09", "full")
    assert (fo.hour, fc.hour) == (8, 0)


# ── identidad ──
def test_epochs_split_on_filler_runs():
    dates = pd.bdate_range("2016-01-04", periods=30).strftime("%Y-%m-%d")
    v = [100] * 10 + [0] * 8 + [50] * 12
    c = [40.0] * 10 + [40.0] * 8 + [12.0] * 12
    d = identity.epochs(pd.DataFrame({"date": dates, "v": v, "c": c}))
    s = identity.epoch_summary(d)
    assert len(s) == 2 and s[0]["end"] == dates[9] and s[1]["start"] == dates[18]
    assert identity.epoch_of(d, dates[5])[0] == 0 and identity.epoch_of(d, dates[25])[0] == 1
    assert not d["suspicious_jump"].any()                 # el salto en la frontera de relleno no se marca


def test_unexplained_jump_flagged_but_split_not():
    dates = pd.bdate_range("2024-06-03", periods=6).strftime("%Y-%m-%d")
    d = pd.DataFrame({"date": dates, "v": [1] * 6, "c": [1200, 1210, 1205, 121, 122, 123]})
    assert identity.epochs(d)["suspicious_jump"].sum() == 1
    sp = pd.DataFrame([{"ex_date": dates[3], "factor": 10.0, "type": "forward_splits"}])
    assert identity.epochs(d, sp)["suspicious_jump"].sum() == 0


# ── conciliación trades ↔ barras ──
def test_reconcile_consistent_and_broken(data_dir):
    tr = [trade("2026-11-13T15:00:01Z", s=100, i=1), trade("2026-11-13T15:00:02Z", s=30, c=("@", "I"), i=2),
          trade("2026-11-13T15:01:00Z", s=50, c=("I",), i=3),                 # minuto solo odd lot: sin barra
          trade("2026-11-13T15:02:00Z", s=200, c=("M",), i=4),                # M: no cuenta en volumen
          trade("2026-11-13T15:02:05Z", s=10, i=5)]
    tdf = normalize.trades(normalize.records_to_frame("trades", tr), "2026-11-13")
    bars = normalize.records_to_frame("bars", [
        {"t": "2026-11-13T15:00:00Z", "o": 10, "h": 10, "l": 10, "c": 10, "v": 130, "n": 2, "vw": 10},
        {"t": "2026-11-13T15:02:00Z", "o": 10, "h": 10, "l": 10, "c": 10, "v": 10, "n": 1, "vw": 10}])
    bdf = normalize.bars(bars)
    r = quality.reconcile_trades_bars(tdf, bdf)
    assert r["grade"] == "A" and r["volume_rel_diff"] == 0 and r["bars_missing_vs_expected"] == 0
    r2 = quality.reconcile_trades_bars(tdf[tdf["trade_id"] != 1], bdf)       # falta un trade
    assert r2["grade"] in ("B", "C") and r2["volume_rel_diff"] > 0


def test_trades_quality_flags(data_dir):
    tr = [trade("2026-11-13T15:00:01Z", s=50, x="D", i=1), trade("2026-11-13T15:00:01Z", s=50, x="D", i=1),
          trade("2026-11-13T15:00:02Z", s=300, i=2)]
    tdf = normalize.trades(normalize.records_to_frame("trades", tr), "2026-11-13")
    o, c = calendar.session_bounds("2026-11-13")
    q = quality.check_trades(tdf, "2026-11-13", (o, c))
    assert any(i["check"] == "duplicates" for i in q["issues"])
    assert q["share_trf_volume"] == round(100 / 400, 4) and q["share_odd_lot_trades"] == round(2 / 3, 4)


# ── muestreo ──
def test_shadow_sample_reproducible():
    u = [f"T{i}" for i in range(500)]
    a = sampling.shadow_sample(u, "2026-11-16", 7, 50)
    b = sampling.shadow_sample(list(reversed(u)), "2026-11-16", 7, 50)
    c = sampling.shadow_sample(u, "2026-11-17", 7, 50)
    assert a["selected"] == b["selected"] and a["selected"] != c["selected"]
    assert a["inclusion_probability"] == 0.1 and len(a["selected"]) == 50


def test_b1_plan_reproducible_and_blocks(data_dir):
    days = pd.bdate_range("2016-01-04", periods=700).strftime("%Y-%m-%d").tolist()
    ents = [f"E{i}" for i in range(60)]
    members = pd.DataFrame([{"entity": e, "symbol": e, "asof": days[0], "start": days[0], "end": days[-1]} for e in ents])
    daily = pd.DataFrame([{"entity": e, "date": d, "n": 1000 * (i + 1)} for i, e in enumerate(ents) for d in days])
    periods = {"dev": (days[0], days[349]), "test": (days[350], days[-1])}
    p1 = sampling.b1_plan(members, daily, days, periods, seed=1, blocks_per_period=9, block_len=50, burn_in=20)
    p2 = sampling.b1_plan(members, daily, days, periods, seed=1, blocks_per_period=9, block_len=50, burn_in=20)
    pd.testing.assert_frame_equal(p1, p2)
    assert len(p1) == 18 and p1.groupby(["period", "liq_tercile"]).size().eq(3).all()
    pos = {d: i for i, d in enumerate(days)}
    for r in p1.itertuples():
        assert pos[r.end] - pos[r.start] == 49 and pos[r.eligible_start] - pos[r.start] == 20
        lo, hi = periods[r.period]
        assert r.start >= lo and pos[r.end] + 40 <= pos[hi]                 # bloque + horizonte no cruzan la frontera
    for e, g in p1.groupby("entity"):                                        # sin solapes del mismo valor
        iv = sorted((pos[a], pos[b]) for a, b in zip(g.start, g.end))
        assert all(iv[k][1] < iv[k + 1][0] for k in range(len(iv) - 1))


def test_power_preview():
    assert 0.07 < sampling.power_preview(1200) < 0.09
    assert sampling.power_preview(1200, k_tests=6) > sampling.power_preview(1200)


# ── retención y captura sombra ──
def test_retention_default_keeps_everything_and_sampling_is_explicit(data_dir):
    from micro import retention
    m = Manifest()
    for i in range(20):
        pr = provider([Resp(200, {"trades": [trade("2026-11-13T15:00:00Z", i=i)]})])
        download_unit(pr, "trades", f"S{i}", "2026-11-13", manifest=m)
    assert retention.prune({"trades": {"policy": "keep_all"}}, m, dry_run=False)["deleted_units"] == 0
    pol = {"trades": {"policy": "sample_fraction", "fraction": 0.5, "seed": 3}}
    dry = retention.prune(pol, m, dry_run=True)
    assert dry["deleted_units"] + dry["kept_units"] == 20 and len(m.rows("status='ok'")) == 20   # simulación: nada borrado
    real = retention.prune(pol, m, dry_run=False)
    assert real["deleted_units"] == dry["deleted_units"] and len(m.rows("status='pruned'")) == dry["deleted_units"]


def test_shadow_refuses_when_disabled(data_dir, monkeypatch):
    from micro import shadow
    monkeypatch.setattr(shadow, "load_config", lambda: {**shadow.DEFAULT, "enabled": False})
    with pytest.raises(SystemExit):
        shadow.run("2026-11-13", provider=None, dry_run=False)
