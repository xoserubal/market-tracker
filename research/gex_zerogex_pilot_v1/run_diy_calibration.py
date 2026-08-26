"""
ZeroGEX Fase 2 — DIY calibration collector, research pilot (NOT wired into the
main pipeline). See wiki/PREREGISTRO_GEX_ZEROGEX_V1.md section 2 for the
frozen definitions this script implements.

Fase 1 (provider quality, gex-zerogex-fase1.yml) passed cleanly for both SPX
and QQQ (0% stale, p90 spot_diff_bps well under the 10bps threshold across 5
trading days, 98 snapshots) — decision made with the user 2026-08-26 to
proceed to Fase 2 rather than let the trial lapse unused.

Purpose: decide whether the free DIY gamma-flip estimate (research/gex_monitor_
pilot/gex_pilot.py — Black-Scholes over yfinance option-chain OI) tracks
ZeroGEX's (paid) gamma_flip closely enough to replace the subscription, per
the criteria in preregistro section 2.3.

Reuses gex_pilot.py's fetch_chain_rows()/find_gamma_flip() by direct import —
the methodology is not reimplemented or tuned mid-calibration (preregistro 2).

Single reference spot per symbol (preregistro 2, "nunca el spot que reporta
cada proveedor"): the session close of ^GSPC (SPX) / QQQ (QQQ) via yfinance,
used to classify BOTH the DIY flip and the ZeroGEX flip into the same regime
bucket. Each source's own internally-reported spot (gex_pilot's ^SPX close,
ZeroGEX's `spot` field) is recorded for reference only, never used to compute
distance_to_flip_pct.

Meant to run once/day near session close (15:50-16:00 ET), not the Fase 1
every-20-min cadence — the option-chain OI that drives both DIY and (presumably)
ZeroGEX updates at session granularity, not intraday (preregistro 0.3).

Usage:
    py -3 research/gex_zerogex_pilot_v1/run_diy_calibration.py             # collect today's snapshot (both symbols), no-op outside 15:30-16:15 ET
    py -3 research/gex_zerogex_pilot_v1/run_diy_calibration.py --force     # bypass the time window (manual test)
    py -3 research/gex_zerogex_pilot_v1/run_diy_calibration.py --report    # print/save Fase 2 metrics + verdict
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf
from dotenv import load_dotenv

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "outputs"
CALIB_PATH = OUT_DIR / "fase2_calibration.jsonl"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_zerogex_snapshot import fetch_levels, STALE_AGE_SECONDS  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gex_monitor_pilot"))
from gex_pilot import fetch_chain_rows, find_gamma_flip  # noqa: E402

ET = ZoneInfo("America/New_York")

# ZeroGEX symbol -> (yfinance market-spot ticker for the single reference close,
#                     yfinance option-chain ticker passed to gex_pilot.py)
SYMBOLS = {
    "SPX": ("^GSPC", "^SPX"),
    "QQQ": ("QQQ", "QQQ"),
}

# Frozen in wiki/PREREGISTRO_GEX_ZEROGEX_V1.md section 2.1 — do not tune post-hoc.
TRANSITION_BAND_PCT = 0.5
FAIL_REGIME_AGREEMENT_RATE = 85.0


def is_near_close_now(now_et: datetime) -> bool:
    """Guards against accidentally seeding the (symbol, date) dedup key with a
    stale/pre-market snapshot — found the hard way: a manual test run at
    ~05:17 ET (before open) wrote ZeroGEX data ~13h stale for SPX under
    *today's* date, which would have silently blocked the real EOD collection
    for the rest of the day. Window is wider than the target 15:50-16:00 ET
    (preregistro 0.3) to tolerate a slow cron/runner, not to loosen intent."""
    if now_et.weekday() >= 5:
        return False
    open_t = now_et.replace(hour=15, minute=30, second=0, microsecond=0)
    close_t = now_et.replace(hour=16, minute=15, second=0, microsecond=0)
    return open_t <= now_et <= close_t


def _dedup_key(row: dict) -> tuple[str, str]:
    return (row["symbol"], row["date"])


def _load_rows() -> list[dict]:
    if not CALIB_PATH.exists():
        return []
    rows = []
    with CALIB_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _append_row(row: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with CALIB_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def classify_bucket(distance_pct: float | None, is_stale: bool) -> str:
    if distance_pct is None or is_stale:
        return "uncertain"
    if distance_pct >= TRANSITION_BAND_PCT:
        return "positive_gamma"
    if distance_pct <= -TRANSITION_BAND_PCT:
        return "negative_gamma"
    return "transition"


def collect_one_symbol(api_key: str, symbol: str, market_ticker: str, gex_ticker: str, today: str) -> dict | None:
    # Single reference spot: today's session close of market_ticker (yfinance).
    try:
        hist = yf.Ticker(market_ticker).history(period="1d", auto_adjust=True)
        if hist.empty:
            print(f"{symbol}: no yfinance close for {market_ticker} today, skipping.")
            return None
        market_spot = float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"{symbol}: failed to fetch market spot ({market_ticker}): {e}")
        return None

    # DIY flip — direct import of gex_pilot.py, same defaults as its CLI (no retuning).
    try:
        diy_spot_internal, diy_rows = fetch_chain_rows(gex_ticker, horizon_days=60)
        diy_flip = find_gamma_flip(diy_rows, diy_spot_internal, grid_pct=15.0, grid_step_pct=0.5)
    except Exception as e:
        print(f"{symbol}: DIY calc failed: {e}")
        diy_spot_internal, diy_flip = None, None

    # ZeroGEX flip — same fetch_levels() Fase 1 already uses, no reimplementation.
    try:
        levels = fetch_levels(api_key, symbol)
        zerogex_spot = levels.get("spot")
        zerogex_flip = (levels.get("levels") or {}).get("gamma_flip")
        zerogex_age = levels.get("age_seconds")
        zerogex_is_stale = zerogex_age is not None and zerogex_age > STALE_AGE_SECONDS
    except Exception as e:
        print(f"{symbol}: ZeroGEX fetch failed: {e}")
        levels, zerogex_spot, zerogex_flip, zerogex_age, zerogex_is_stale = {}, None, None, None, True

    dist_diy = (market_spot - diy_flip) / market_spot * 100 if diy_flip is not None else None
    dist_zerogex = (market_spot - zerogex_flip) / market_spot * 100 if zerogex_flip is not None else None

    bucket_diy = classify_bucket(dist_diy, False)  # DIY has no independent staleness concept
    bucket_zerogex = classify_bucket(dist_zerogex, zerogex_is_stale)

    abs_flip_diff = abs(diy_flip - zerogex_flip) if (diy_flip is not None and zerogex_flip is not None) else None

    row = {
        "date": today,
        "symbol": symbol,
        "collected_at": datetime.now(ET).isoformat(),
        "market_spot": market_spot,
        "market_spot_source": market_ticker,
        "diy_gamma_flip": diy_flip,
        "diy_spot_internal": diy_spot_internal,
        "distance_to_flip_pct_diy": dist_diy,
        "bucket_diy": bucket_diy,
        "zerogex_gamma_flip": zerogex_flip,
        "zerogex_spot": zerogex_spot,
        "zerogex_as_of": levels.get("as_of"),
        "zerogex_age_seconds": zerogex_age,
        "zerogex_is_stale": zerogex_is_stale,
        "distance_to_flip_pct_zerogex": dist_zerogex,
        "bucket_zerogex": bucket_zerogex,
        "abs_flip_diff": abs_flip_diff,
        "flip_diff_signed": (diy_flip - zerogex_flip) if abs_flip_diff is not None else None,
        "raw_zerogex": levels,
    }
    print(
        f"{symbol}: market_spot={market_spot:.2f} diy_flip={diy_flip} ({bucket_diy}) "
        f"zerogex_flip={zerogex_flip} ({bucket_zerogex}) abs_diff={abs_flip_diff}"
    )
    return row


def collect_snapshot(force: bool = False) -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("ZEROGEX_API_KEY")
    if not api_key:
        print("ZEROGEX_API_KEY not set — aborting.")
        return

    now_et = datetime.now(ET)
    if not force and not is_near_close_now(now_et):
        print(f"[{now_et.isoformat()}] fuera de la ventana 15:30-16:15 ET, no se recoge (usa --force para saltarte esto en pruebas manuales).")
        return

    today = date.today().isoformat()
    existing_keys = {_dedup_key(r) for r in _load_rows()}

    for symbol, (market_ticker, gex_ticker) in SYMBOLS.items():
        if (symbol, today) in existing_keys:
            print(f"{symbol}: already collected for {today}, skipping (dedup).")
            continue
        row = collect_one_symbol(api_key, symbol, market_ticker, gex_ticker, today)
        if row is not None:
            _append_row(row)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def generate_report() -> None:
    rows = _load_rows()
    if not rows:
        print("No Fase 2 snapshots collected yet.")
        return

    symbols_seen = sorted({r["symbol"] for r in rows})
    lines = [
        "# Fase 2 — informe de calibración DIY vs ZeroGEX",
        "",
        f"Generado: {datetime.now(ET).isoformat()}",
        f"Total snapshots: {len(rows)}  |  Símbolos: {', '.join(symbols_seen)}",
        "",
    ]

    for symbol in symbols_seen:
        srows = [r for r in rows if r["symbol"] == symbol]
        n_sessions = len(srows)
        lines.append(f"## {symbol} — {n_sessions} sesión(es)")

        valid = [r for r in srows if r.get("abs_flip_diff") is not None]
        diffs = [r["abs_flip_diff"] for r in valid]
        median_diff = statistics.median(diffs) if diffs else None
        p90_diff = _percentile(diffs, 90)

        comparable = [r for r in srows if r["bucket_diy"] != "uncertain" and r["bucket_zerogex"] != "uncertain"]
        agree = sum(1 for r in comparable if r["bucket_diy"] == r["bucket_zerogex"])
        regime_agreement_rate = (agree / len(comparable) * 100) if comparable else None

        near_flip = [r for r in comparable if "transition" in (r["bucket_diy"], r["bucket_zerogex"])]
        opposite = [
            r for r in near_flip
            if {r["bucket_diy"], r["bucket_zerogex"]} == {"positive_gamma", "negative_gamma"}
        ]
        near_flip_agreement = ((len(near_flip) - len(opposite)) / len(near_flip) * 100) if near_flip else None

        signed = [r["flip_diff_signed"] for r in valid]
        bias_mean = statistics.mean(signed) if signed else None
        bias_stdev = statistics.stdev(signed) if len(signed) >= 2 else None

        if n_sessions < 10:
            lines.append(f"- Sesiones insuficientes ({n_sessions}/10 mínimo) — seguir recolectando antes de aplicar el criterio de decisión.")
        lines.append(f"- median_abs_flip_diff: {median_diff:.2f}" if median_diff is not None else "- median_abs_flip_diff: n/a")
        lines.append(f"- p90_abs_flip_diff: {p90_diff:.2f}" if p90_diff is not None else "- p90_abs_flip_diff: n/a")
        lines.append(
            f"- regime_agreement_rate: {regime_agreement_rate:.1f}% (n={len(comparable)})"
            if regime_agreement_rate is not None else "- regime_agreement_rate: n/a (0 sesiones comparables)"
        )
        lines.append(
            f"- near_flip_agreement: {near_flip_agreement:.1f}% (n={len(near_flip)} sesiones con al menos una fuente en transition)"
            if near_flip_agreement is not None else "- near_flip_agreement: n/a (ninguna sesión cerca del flip todavía)"
        )
        if signed:
            lines.append(f"- bias_stability: mean={bias_mean:.2f} stdev={bias_stdev:.2f}" if bias_stdev is not None else f"- bias_stability: mean={bias_mean:.2f} (n=1, sin stdev)")
            lines.append(f"  serie completa (diy_flip - zerogex_flip): {[round(x, 2) for x in signed]}")
        else:
            lines.append("- bias_stability: n/a")

        lines.append("")
        lines.append("### Detalle por sesión")
        lines.append("| Fecha | Market Spot | DIY Flip | DIY Bucket | ZeroGEX Flip | ZeroGEX Bucket | Abs Diff |")
        lines.append("|---|---:|---:|---|---:|---|---:|")
        for r in srows:
            diy_f = f"{r['diy_gamma_flip']:.1f}" if r.get("diy_gamma_flip") is not None else "n/a"
            zg_f = f"{r['zerogex_gamma_flip']:.1f}" if r.get("zerogex_gamma_flip") is not None else "n/a"
            ad = f"{r['abs_flip_diff']:.2f}" if r.get("abs_flip_diff") is not None else "n/a"
            lines.append(
                f"| {r['date']} | {r['market_spot']:.2f} | {diy_f} | {r['bucket_diy']} | {zg_f} | {r['bucket_zerogex']} | {ad} |"
            )
        lines.append("")

        if n_sessions >= 10 and regime_agreement_rate is not None:
            if regime_agreement_rate >= FAIL_REGIME_AGREEMENT_RATE:
                lines.append(
                    f"**VEREDICTO {symbol} (revisar bias_stability a ojo antes de confirmar):** "
                    f"regime_agreement_rate={regime_agreement_rate:.1f}% >= {FAIL_REGIME_AGREEMENT_RATE}% "
                    "→ calibración candidata a PASAR — decidir con el usuario si bias_stability no muestra deriva clara (sección 2.3)."
                )
            else:
                lines.append(
                    f"**VEREDICTO {symbol}:** regime_agreement_rate={regime_agreement_rate:.1f}% < {FAIL_REGIME_AGREEMENT_RATE}% "
                    "→ DIY no replica. Si ZeroGEX pasó Fase 1 (sí, para ambos símbolos) → decisión de juicio con el usuario: "
                    "mantener suscripción para este símbolo, o descartarlo (sección 2.3)."
                )
        else:
            lines.append(f"**VEREDICTO {symbol}:** pendiente — faltan sesiones (mínimo 10, hay {n_sessions}).")
        lines.append("")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "fase2_informe.md"
    report_text = "\n".join(lines)
    report_path.write_text(report_text, encoding="utf-8")
    print(report_text)
    print(f"\nGuardado: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", action="store_true", help="generate/print the Fase 2 calibration report from collected snapshots")
    parser.add_argument("--force", action="store_true", help="bypass the 15:30-16:15 ET window check (manual test outside that window)")
    args = parser.parse_args()

    if args.report:
        generate_report()
        return

    collect_snapshot(force=args.force)


if __name__ == "__main__":
    main()
