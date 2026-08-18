"""
GEX (dealer gamma exposure) pilot — research script, NOT wired into the pipeline.

Origin: an external analyst reviewing duration.html noted that assessing whether
a rates "de-anchoring" is strong or trivial requires knowing current dealer gamma
positioning (long vs short) — data this project doesn't have. This script is the
promised pilot: build the DIY estimate from free data (yfinance option chains),
verify it against a live third-party figure, and decide whether it's trustworthy
enough to integrate anywhere (duration.html / positioning.html).

Methodology (the standard "SqueezeMetrics-style" convention used by most public
GEX explainers and free tools — e.g. https://perfiliev.com/blog/how-to-calculate-
gamma-exposure-and-zero-gamma-level/):
    - Assume dealers are net LONG the calls customers buy from them, and net
      SHORT the puts customers buy from them (asymmetric on purpose — reflects
      structural flows: covered-call/overwriting supplies calls to dealers,
      portfolio-insurance put buying demands puts from dealers).
    - Per contract: GEX = Black-Scholes Gamma * OpenInterest * 100 * Spot^2 * 0.01
      ("$ dealer hedge flow per 1% move in the underlying").
    - Net GEX = sum(call GEX) - sum(put GEX). Positive = dealers net long gamma
      (they buy dips / sell rips -> dampens volatility). Negative = dealers net
      short gamma (they sell dips / buy rips -> amplifies volatility).
    - Gamma flip / zero-gamma level: the hypothetical spot price where Net GEX
      crosses zero, found by re-evaluating Net GEX at a grid of hypothetical
      spot levels (each option's OI/IV/strike held fixed, only the spot in the
      Black-Scholes gamma formula is swept).

Known simplifications (documented, not hidden):
    - r = q = 0 in Black-Scholes (no risk-free rate / dividend yield adjustment)
      — negligible effect on gamma for the horizon used here.
    - Time to expiry uses calendar days to an assumed 4pm ET close, floored at
      1 hour, not actual trading-day/hours math.
    - Horizon capped at --horizon-days (default 60) to bound the number of
      option-chain HTTP calls — far-dated OI contributes little to gamma anyway
      (BS gamma ~ 1/sqrt(T), decays for far expiries) and is thinner/noisier.
    - Every contract's own last-quoted impliedVolatility (from yfinance) is used
      directly, not a smoothed/interpolated vol surface.

RESULT OF THE 2026-08-18 VERIFICATION RUN (see HALLAZGOS.md for the full
writeup): net GEX sign came out NEGATIVE (~-$44B) on a day a live third-party
free source (FlashAlpha) reported POSITIVE (~+$87.6B) at essentially the same
spot/date. Root cause diagnosed below in `main()`'s per-expiration breakdown:
SPX put open interest structurally dominates call open interest at nearly
every expiration (index portfolio-insurance flow), and the naive convention
("all put OI = dealer short") has no way to tell that some of that put OI was
itself sold TO dealers by other customers (cash-secured put writers, yield
structures) rather than bought FROM dealers — that distinction requires OCC's
customer/firm/market-maker open-interest breakdown, which is not in yfinance's
option chain and is not free (Cboe Options Open-Close Volume Summary is a paid
DataShop product). Conclusion: this DIY approach is NOT trustworthy for sign,
only order-of-magnitude — not integrated anywhere in the live dashboards.

Usage:
    py -3 gex_pilot.py                          # ^SPX, 60-day horizon, prints + saves JSON
    py -3 gex_pilot.py --ticker ^SPX --horizon-days 60 --grid-pct 15 --grid-step-pct 0.5
    py -3 gex_pilot.py --no-save
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yfinance as yf

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OUT_DIR = Path(__file__).parent


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _valid(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def black_scholes_gamma(spot: float, strike: float, t_years: float, sigma: float) -> float:
    """r = q = 0, documented simplification — see module docstring."""
    if t_years <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * t_years) / (sigma * math.sqrt(t_years))
    return _norm_pdf(d1) / (spot * sigma * math.sqrt(t_years))


def fetch_chain_rows(ticker: str, horizon_days: int) -> tuple[float, list[dict]]:
    """Returns (spot, rows) where each row has strike/side/oi/iv/t_years/expiry."""
    tk = yf.Ticker(ticker)
    spot = float(tk.history(period="1d", auto_adjust=True)["Close"].iloc[-1])
    today_d = date.today()
    now = datetime.now()
    expirations = [
        e for e in tk.options
        if (datetime.strptime(e, "%Y-%m-%d").date() - today_d).days <= horizon_days
    ]

    rows: list[dict] = []
    for exp in expirations:
        expiry_dt = datetime.strptime(exp, "%Y-%m-%d") + timedelta(hours=16)  # approx 4pm ET close
        t_years = max((expiry_dt - now).total_seconds() / (365 * 24 * 3600), 1 / (365 * 24))
        chain = tk.option_chain(exp)
        for side, df in (("call", chain.calls), ("put", chain.puts)):
            for _, r in df.iterrows():
                oi, iv, k = r["openInterest"], r["impliedVolatility"], r["strike"]
                if not _valid(oi) or not _valid(iv) or oi <= 0 or iv <= 0.01:
                    continue
                rows.append({
                    "expiry": exp, "side": side, "strike": float(k),
                    "oi": float(oi), "iv": float(iv), "t_years": t_years,
                })
    return spot, rows


def net_gex_at_spot(rows: list[dict], eval_spot: float) -> float:
    total = 0.0
    for r in rows:
        g = black_scholes_gamma(eval_spot, r["strike"], r["t_years"], r["iv"])
        gex = g * r["oi"] * 100 * eval_spot * eval_spot * 0.01
        total += gex if r["side"] == "call" else -gex
    return total


def per_expiration_breakdown(rows: list[dict], spot: float) -> list[dict]:
    by_exp: dict[str, dict] = {}
    for r in rows:
        g = black_scholes_gamma(spot, r["strike"], r["t_years"], r["iv"])
        gex = g * r["oi"] * 100 * spot * spot * 0.01
        entry = by_exp.setdefault(r["expiry"], {"call_gex": 0.0, "put_gex": 0.0, "call_oi": 0, "put_oi": 0})
        if r["side"] == "call":
            entry["call_gex"] += gex
            entry["call_oi"] += r["oi"]
        else:
            entry["put_gex"] += gex
            entry["put_oi"] += r["oi"]
    out = []
    for exp, e in sorted(by_exp.items()):
        out.append({
            "expiry": exp,
            "call_gex": e["call_gex"], "put_gex": e["put_gex"],
            "net_gex": e["call_gex"] - e["put_gex"],
            "call_oi": e["call_oi"], "put_oi": e["put_oi"],
        })
    return out


def find_gamma_flip(rows: list[dict], spot: float, grid_pct: float, grid_step_pct: float) -> float | None:
    """Sweeps hypothetical spot levels and finds where Net GEX crosses zero."""
    lo_mult, hi_mult = 1 - grid_pct / 100, 1 + grid_pct / 100
    step_mult = grid_step_pct / 100
    levels = []
    m = lo_mult
    while m <= hi_mult + 1e-9:
        levels.append(spot * m)
        m += step_mult

    prev_level, prev_net = None, None
    for level in levels:
        net = net_gex_at_spot(rows, level)
        if prev_net is not None and (prev_net < 0) != (net < 0):
            # linear interpolation between prev_level and level
            frac = -prev_net / (net - prev_net) if net != prev_net else 0.5
            return prev_level + frac * (level - prev_level)
        prev_level, prev_net = level, net
    return None  # no sign change within the swept range


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", default="^SPX", help="yfinance symbol with a listed option chain (default ^SPX)")
    parser.add_argument("--horizon-days", type=int, default=60, help="max calendar days to expiry to include")
    parser.add_argument("--grid-pct", type=float, default=15.0, help="gamma-flip sweep range, +/- %% around spot")
    parser.add_argument("--grid-step-pct", type=float, default=0.5, help="gamma-flip sweep step, %% of spot")
    parser.add_argument("--no-save", action="store_true", help="don't write the JSON output file")
    args = parser.parse_args()

    print(f"Fetching {args.ticker} option chain (horizon {args.horizon_days}d)...")
    spot, rows = fetch_chain_rows(args.ticker, args.horizon_days)
    print(f"spot={spot:.2f}  contracts_used={len(rows)}  expirations={len({r['expiry'] for r in rows})}")

    call_gex = sum(black_scholes_gamma(spot, r["strike"], r["t_years"], r["iv"]) * r["oi"] * 100 * spot * spot * 0.01
                   for r in rows if r["side"] == "call")
    put_gex = sum(black_scholes_gamma(spot, r["strike"], r["t_years"], r["iv"]) * r["oi"] * 100 * spot * spot * 0.01
                  for r in rows if r["side"] == "put")
    net_gex = call_gex - put_gex

    flip = find_gamma_flip(rows, spot, args.grid_pct, args.grid_step_pct)
    breakdown = per_expiration_breakdown(rows, spot)

    regime = "positive (dealers net long gamma -> stabilizing)" if net_gex > 0 else "negative (dealers net short gamma -> amplifying)"
    print(f"\ncall_gex=${call_gex/1e9:,.2f}B  put_gex=${put_gex/1e9:,.2f}B  net_gex=${net_gex/1e9:,.2f}B")
    print(f"regime: {regime}")
    print(f"gamma flip (zero-gamma level): {flip:.1f} ({'above' if flip and spot > flip else 'below'} spot)" if flip else "gamma flip: no crossing found in swept range")

    result = {
        "generated_at": datetime.now().isoformat(),
        "ticker": args.ticker,
        "spot": spot,
        "horizon_days": args.horizon_days,
        "contracts_used": len(rows),
        "call_gex": call_gex,
        "put_gex": put_gex,
        "net_gex": net_gex,
        "gamma_flip": flip,
        "per_expiration": breakdown,
        "methodology": "call_gex - put_gex convention (dealers assumed long calls / short puts), "
                        "Black-Scholes gamma with r=q=0, per-contract yfinance impliedVolatility. "
                        "See gex_pilot.py module docstring and HALLAZGOS.md for known limitations.",
    }

    if not args.no_save:
        out_path = OUT_DIR / f"gex_pilot_output_{date.today().isoformat()}_{args.ticker.lstrip('^')}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
