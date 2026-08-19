"""
ZeroGEX Fase 1 snapshot collector — research pilot, NOT wired into the main
market-update pipeline (runs as its own GitHub Actions workflow instead).

See wiki/PREREGISTRO_GEX_ZEROGEX_V1.md for the frozen thresholds/criteria this
script implements (section 1 — Provider quality). Purpose: decide, over the
7-day ZeroGEX trial, whether the provider's spot/timestamp are genuinely live
(vs. the FlashAlpha dashboard, which failed this exact check — see
research/gex_monitor_pilot/HALLAZGOS.md).

Covers SPX and QQQ (added 2026-08-19, "ya puestos" — the marginal cost of a
second symbol is one extra API call per cycle). Each symbol is checked and
reported independently — one symbol failing Fase 1 does not fail the other.

Meant to run every ~20 min during RTH (09:30-16:00 ET) via a scheduled GitHub
Actions workflow (or manual invocation). Each run is a no-op outside RTH
(prints and exits 0) so it's safe to schedule "every 20 min, all day" without
separate market-hours cron logic.

Usage:
    py -3 research/gex_zerogex_pilot_v1/fetch_zerogex_snapshot.py            # normal run (no-op outside RTH)
    py -3 research/gex_zerogex_pilot_v1/fetch_zerogex_snapshot.py --force    # bypass RTH check (manual test)
    py -3 research/gex_zerogex_pilot_v1/fetch_zerogex_snapshot.py --report   # print/save Fase 1 pass/fail verdict
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from dotenv import load_dotenv

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "outputs"
SNAPSHOTS_PATH = OUT_DIR / "fase1_snapshots.jsonl"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
API_BASE = "https://api.zerogex.io"

# ZeroGEX symbol -> yfinance ticker used for the independent market-spot cross-check.
SYMBOLS = {
    "SPX": "^GSPC",
    "QQQ": "QQQ",
}

# Frozen in wiki/PREREGISTRO_GEX_ZEROGEX_V1.md section 1 — do not tune post-hoc.
STALE_AGE_SECONDS = 180
FAIL_SPOT_DIFF_BPS_P90 = 10.0
FAIL_STALE_PCT = 20.0


def is_rth_now(now_et: datetime) -> bool:
    if now_et.weekday() >= 5:
        return False
    open_t = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now_et <= close_t


def fetch_levels(api_key: str, symbol: str) -> dict:
    resp = requests.get(
        f"{API_BASE}/api/v1/levels/{symbol}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_market_spot(as_of_iso: str, market_ticker: str) -> tuple[float | None, str | None]:
    """Nearest 1-minute bar of market_ticker to as_of. None if no bar within 2 minutes.

    yfinance only serves 1m history for the trailing ~7 days — fine here since
    this is always called near "now" during live collection, never backfilled
    later.
    """
    try:
        as_of = datetime.fromisoformat(as_of_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None, None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    start = as_of - timedelta(minutes=10)
    end = as_of + timedelta(minutes=10)
    hist = yf.Ticker(market_ticker).history(start=start, end=end, interval="1m")
    if hist.empty:
        return None, None

    idx_utc = hist.index.tz_convert("UTC")
    as_of_utc = as_of.astimezone(UTC)
    deltas = [abs((t.to_pydatetime() - as_of_utc).total_seconds()) for t in idx_utc]
    best_i = min(range(len(deltas)), key=lambda i: deltas[i])
    if deltas[best_i] > 120:
        return None, None

    bar_time = idx_utc[best_i].isoformat()
    close = float(hist["Close"].iloc[best_i])
    return close, bar_time


def collect_one_symbol(api_key: str, symbol: str, market_ticker: str, now_et: datetime) -> dict | None:
    try:
        levels = fetch_levels(api_key, symbol)
    except Exception as e:
        print(f"ERROR fetching ZeroGEX levels for {symbol}: {e}")
        return None

    spot_provider = levels.get("spot")
    as_of = levels.get("as_of")
    age_seconds = levels.get("age_seconds")
    dealer_levels = levels.get("levels") or {}

    spot_market, market_bar_time = (None, None)
    if as_of:
        spot_market, market_bar_time = fetch_market_spot(as_of, market_ticker)

    spot_diff_bps = None
    if spot_provider is not None and spot_market:
        spot_diff_bps = abs(spot_provider - spot_market) / spot_market * 10000

    is_stale = age_seconds is not None and age_seconds > STALE_AGE_SECONDS

    row = {
        "collected_at": now_et.isoformat(),
        "symbol": symbol,
        "spot_provider": spot_provider,
        "as_of": as_of,
        "age_seconds": age_seconds,
        "spot_market": spot_market,
        "market_bar_time": market_bar_time,
        "spot_diff_bps": spot_diff_bps,
        "is_stale": is_stale,
        "gamma_flip": dealer_levels.get("gamma_flip"),
        "call_wall": dealer_levels.get("call_wall"),
        "put_wall": dealer_levels.get("put_wall"),
        "max_pain": dealer_levels.get("max_pain"),
        "net_gex_at_spot": levels.get("net_gex_at_spot"),
        "raw": levels,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with SNAPSHOTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    diff_str = f"{spot_diff_bps:.2f}bps" if spot_diff_bps is not None else "n/a"
    print(
        f"[{now_et.strftime('%Y-%m-%d %H:%M:%S')} ET] {symbol}: "
        f"spot_provider={spot_provider} spot_market={spot_market} diff={diff_str} "
        f"age_s={age_seconds} stale={is_stale} flip={dealer_levels.get('gamma_flip')}"
    )
    return row


def collect_snapshot(force: bool = False) -> list[dict]:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("ZEROGEX_API_KEY")
    if not api_key:
        print("ZEROGEX_API_KEY not set — aborting.")
        return []

    now_et = datetime.now(ET)
    if not force and not is_rth_now(now_et):
        print(f"[{now_et.isoformat()}] outside RTH, skipping (use --force to override).")
        return []

    rows = []
    for symbol, market_ticker in SYMBOLS.items():
        row = collect_one_symbol(api_key, symbol, market_ticker, now_et)
        if row is not None:
            rows.append(row)
    return rows


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _load_snapshots() -> list[dict]:
    if not SNAPSHOTS_PATH.exists():
        return []
    rows = []
    with SNAPSHOTS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def generate_report() -> None:
    rows = _load_snapshots()
    if not rows:
        print("No snapshots collected yet.")
        return

    by_symbol_session: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        key = (r.get("symbol", "?"), r["collected_at"][:10])
        by_symbol_session.setdefault(key, []).append(r)

    symbols_seen = sorted({r.get("symbol", "?") for r in rows})
    lines = [
        "# Fase 1 — informe de calidad del proveedor (ZeroGEX)",
        "",
        f"Generado: {datetime.now(ET).isoformat()}",
        f"Total snapshots: {len(rows)}  |  Símbolos: {', '.join(symbols_seen)}",
        "",
    ]

    fail_by_symbol: dict[str, list[str]] = {s: [] for s in symbols_seen}
    for (symbol, session), srows in sorted(by_symbol_session.items()):
        diffs = [r["spot_diff_bps"] for r in srows if r.get("spot_diff_bps") is not None]
        stale_count = sum(1 for r in srows if r.get("is_stale"))
        pct_stale = stale_count / len(srows) * 100
        p90 = _percentile(diffs, 90)

        as_of_values = [r["as_of"] for r in srows if r.get("as_of")]
        frozen = len(as_of_values) >= 2 and len(set(as_of_values)) == 1

        fail = []
        if p90 is not None and p90 > FAIL_SPOT_DIFF_BPS_P90:
            fail.append(f"p90_spot_diff_bps={p90:.2f}>{FAIL_SPOT_DIFF_BPS_P90}")
        if pct_stale > FAIL_STALE_PCT:
            fail.append(f"pct_stale={pct_stale:.1f}%>{FAIL_STALE_PCT}%")
        if frozen:
            fail.append("as_of_frozen_across_snapshots")

        status = "FAIL" if fail else "ok"
        p90_str = f"{p90:.2f}" if p90 is not None else "n/a"
        detail = f" ({', '.join(fail)})" if fail else ""
        lines.append(f"- {symbol} {session}: n={len(srows)} p90_diff_bps={p90_str} pct_stale={pct_stale:.1f}% status={status}{detail}")
        fail_by_symbol.setdefault(symbol, []).extend(f"{session}: {x}" for x in fail)

    lines.append("")
    any_fail = any(reasons for reasons in fail_by_symbol.values())
    if any_fail:
        lines.append("## VEREDICTO por símbolo")
        for symbol in symbols_seen:
            reasons = fail_by_symbol.get(symbol, [])
            if reasons:
                lines.append(f"- {symbol}: FALLA Fase 1 — cancelar/descartar este símbolo")
                lines.extend(f"  - {r}" for r in reasons)
            else:
                lines.append(f"- {symbol}: sin fallos detectados hasta ahora")
    else:
        lines.append("## VEREDICTO (provisional): sin fallos detectados en ningún símbolo hasta ahora — seguir recolectando hasta cubrir el trial completo (7 días) antes de dar Fase 1 por pasada")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "fase1_informe.md"
    report_text = "\n".join(lines)
    report_path.write_text(report_text, encoding="utf-8")
    print(report_text)
    print(f"\nGuardado: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="bypass the RTH check (manual test outside market hours)")
    parser.add_argument("--report", action="store_true", help="generate/print the Fase 1 pass/fail report from collected snapshots")
    args = parser.parse_args()

    if args.report:
        generate_report()
        return

    collect_snapshot(force=args.force)


if __name__ == "__main__":
    main()
