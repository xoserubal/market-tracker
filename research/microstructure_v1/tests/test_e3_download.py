"""Pruebas sin red de la descarga múltiple diaria de E3 (micro/download.download_bars_multi_day) y del control de
series mezcladas (micro/dq_checks.mixed_series)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micro import calendar, download, dq_checks  # noqa: E402
from micro.manifest import Manifest  # noqa: E402
from micro.providers.base import ProviderError  # noqa: E402

DAY = "2019-06-03"


class FakeProv:
    name = "alpaca"

    def __init__(self, fail_batches=0, fail_symbol=None):
        self.calls = []
        self.fail_batches = fail_batches
        self.fail_symbol = fail_symbol

    def _bars(self, sym):
        if sym.startswith("EMPTY"):
            return []
        t0 = pd.Timestamp(f"{DAY} 13:30", tz="UTC")
        return [{"t": (t0 + pd.Timedelta(minutes=i)).isoformat().replace("+00:00", "Z"), "o": 10, "h": 10.1, "l": 9.9,
                 "c": 10, "v": 100 + i, "n": 5, "vw": 10} for i in range(30)]

    def fetch_bars_multi(self, symbols, start, end, stats=None, **k):
        self.calls.append(list(symbols))
        if self.fail_batches > 0 or (self.fail_symbol and self.fail_symbol in symbols):
            self.fail_batches -= 1
            raise ProviderError("simulado")
        if stats is not None:
            stats.requests += 1
            stats.pages += 1
        return {**{s: self._bars(s) for s in symbols}, "_pages": 1}

    def fetch_pages(self, kind, symbol, start, end, **k):
        yield self._bars(symbol)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MICRO_DATA_DIR", str(tmp_path / "md"))
    from micro import config
    monkeypatch.setattr(config, "MIN_FREE_GB", 0.0)
    monkeypatch.setattr(calendar, "is_trading_day", lambda d: True)
    monkeypatch.setattr(download, "_window", lambda kind, period, cfg: (pd.Timestamp(f"{DAY} 08:00", tz="UTC"),
                                                                        pd.Timestamp(f"{DAY} 23:59", tz="UTC")))
    monkeypatch.setattr(download, "assess", lambda *a, **k: {"grade": "A", "issues": []})
    return Manifest(tmp_path / "m.sqlite")


def test_multi_writes_units_and_is_idempotent(env):
    p = FakeProv()
    r = download.download_bars_multi_day(p, ["AAA", "BBB", "EMPTY1"], DAY, manifest=env, batch=2)
    assert (r["ok"], r["empty"], r["failed"]) == (2, 1, [])
    cfg = download.config_for("bars", bars_window="day")
    for s in ("AAA", "BBB", "EMPTY1"):
        assert env.is_done(download.unit_key("alpaca", "bars", s, None, DAY, cfg))
    r2 = download.download_bars_multi_day(p, ["AAA", "BBB", "EMPTY1"], DAY, manifest=env, batch=2)
    assert r2["already_done"] == 3 and r2["ok"] == 0 and len(p.calls) == 2      # nada nuevo pedido


def test_batch_retry_then_success(env):
    p = FakeProv(fail_batches=1)
    r = download.download_bars_multi_day(p, ["AAA", "BBB"], DAY, manifest=env, batch=10, batch_retries=1)
    assert r["ok"] == 2 and r["batch_retries"] == 1 and r["splits"] == 0


def test_split_and_single_fallback(env):
    p = FakeProv(fail_symbol="BAD")
    r = download.download_bars_multi_day(p, ["AAA", "BAD", "CCC", "DDD"], DAY, manifest=env, batch=4, batch_retries=0)
    assert r["splits"] >= 1 and r["fallback_single"] == 1 and r["ok"] == 4     # BAD se baja sola con fetch_pages


def test_mixed_series_rule():
    a = np.r_[np.full(30, 47.0), np.full(30, 63.7)]
    assert not dq_checks.mixed_series(a)["flag"]                                 # un salto que se mantiene: 1 cambio
    b = np.tile([47.0, 47.1, 63.7], 40)
    r = dq_checks.mixed_series(b)
    assert r["flag"] and r["switches"] >= 6 and r["levels"][1] > 60
    c = np.r_[np.full(200, 50.0), [56.0, 50.0] * 3]                              # pocas barras en el otro nivel
    assert not dq_checks.mixed_series(c)["flag"]
