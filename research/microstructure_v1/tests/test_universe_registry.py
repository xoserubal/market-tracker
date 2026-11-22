"""Pruebas sin red del registro del universo (u1_universe_registry.py, micro/event_universe.py), 2026-11-21."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import u1_universe_registry as U  # noqa: E402
from micro import event_universe as EU  # noqa: E402


@pytest.fixture
def cal(monkeypatch):
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-02", "2026-12-31")]
    monkeypatch.setattr(U, "trading_days", lambda a, b: [d for d in days if a <= d <= b])
    return days


def _closes(a, b, base=100.0):
    return {d.strftime("%Y-%m-%d"): base for d in pd.bdate_range(a, b)}


def test_rename_dated_by_new_ticker_and_old_ticker_reuse(cal):
    hist = {"OLD": {"no_asof": {"first": "2026-10-20", "last": "2026-11-20", "closes": _closes("2026-10-20", "2026-11-20", 5)},
                    "asof_start": {"first": "2026-01-02", "last": "2026-11-20"}},
            "NEW": {"no_asof": {"first": "2026-01-02", "last": "2026-11-20", "closes": _closes("2026-01-02", "2026-11-20")},
                    "asof_start": {"first": "2026-06-24", "last": "2026-11-20"}}}
    ev = [{"type": "rename", "key": "1|OLD", "new_key": "1|NEW", "issuer": "1", "old_ticker": "OLD", "ticker": "NEW",
           "rev_ts": "2026-06-25T10:00:00Z", "prev_rev_ts": "2026-06-20T10:00:00Z", "comment": ""}]
    e = U.date_events(ev, hist)[0]
    assert e["effective"] == "2026-06-24" and e["method"] == "alpaca_new_ticker_first_bar"
    assert e["old_ticker_reused_from"] == "2026-10-20"          # el ticker antiguo es hoy otro instrumento


def test_membership_rename_two_tranches_and_identity_correction_continuous(cal):
    first = pd.DataFrame([{"key": "1|OLD", "issuer": "1", "ticker": "OLD", "name": "A", "known_from": "2026-01-14T19:00:00Z"},
                          {"key": "9|X", "issuer": "9", "ticker": "X", "name": "X", "known_from": "2026-01-14T19:00:00Z"}])
    ev = [{"type": "rename", "key": "1|OLD", "new_key": "1|NEW", "issuer": "1", "old_ticker": "OLD", "ticker": "NEW",
           "name": "A", "effective": "2026-08-18", "method": "m", "revid": 2},
          {"type": "identity_correction", "key": "9|X", "new_key": "8|X", "issuer": "8", "old_issuer": "9", "ticker": "X",
           "name": "X", "effective": "2026-08-07", "method": "m", "revid": 3}]
    m = U.build_membership("sp500", ev, first, first, "2026-11-20")
    a = m[m["issuer"] == "1"].sort_values("start")
    assert a[["ticker", "start", "end"]].values.tolist() == [["OLD", "2026-01-14", "2026-08-17"], ["NEW", "2026-08-18", "2026-11-20"]]
    x = m[m["ticker"] == "X"]
    assert len(x) == 1 and x.iloc[0]["issuer"] == "8" and x.iloc[0]["end"] == "2026-11-20"


def test_resolve_successor_never_rewrites_before_effective():
    succ = pd.DataFrame([{"from_ticker": "EQR", "to_ticker": "VMRK", "effective": "2026-08-18", "issuer_key": "906107",
                          "method": "alpaca_new_ticker_first_bar"}])
    assert EU.resolve_successor("EQR", succ, "2026-08-17")[0] == "EQR"
    now, chain = EU.resolve_successor("EQR", succ, "2026-11-20")
    assert now == "VMRK" and chain[0]["issuer"] == "906107"
    assert EU.resolve_successor("AAPL", succ, "2026-11-20") == ("AAPL", [])


def test_cik_read_as_float_is_normalised():
    assert U.norm_cik("1000228.0") == "1000228" and U.norm_cik("0000906107") == "906107"


def test_no_bars_for_uncovered_symbol_is_not_an_ordinary_no_trading_day(monkeypatch):
    from micro import event_scan
    import numpy as np
    monkeypatch.setattr(event_scan.test_guard, "check", lambda *a, **k: [])
    monkeypatch.setattr(event_scan, "baseline_days", lambda d: ["2026-11-18", "2026-11-19"])

    class M:
        days = ["2026-11-18", "2026-11-19", "2026-11-20"]
        C = np.full((3, 5), np.nan)
        meta = [{"open_slot": 0, "close_slot": 4}] * 3

        def idx(self, d):
            return self.days.index(d)
    monkeypatch.setattr(event_scan.F, "load_bars", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(event_scan.F, "build_matrix", lambda *a, **k: M())
    monkeypatch.setattr(event_scan.event_universe, "provider_status",
                        lambda s: {"status": "provider_otc_not_covered", "checked_utc": "2026-11-21"})
    r = event_scan.scan_symbol("GTBIF", "2026-11-20", "full", catalog="cat-v1")
    assert r["symbol_day"]["status"] == "provider_not_covered"
    monkeypatch.setattr(event_scan.event_universe, "provider_status", lambda s: {"status": "covered"})
    assert event_scan.scan_symbol("AAPL", "2026-11-20", "full", catalog="cat-v1")["symbol_day"]["status"] == "no_data"
