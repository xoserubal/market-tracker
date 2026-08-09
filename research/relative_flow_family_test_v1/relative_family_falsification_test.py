"""
relative_family_falsification_test.py
    — Relative Flow Family Falsification Test v1 (versión acotada: Capa 1+2).

Ver wiki/PREREGISTRO_RELATIVE_FLOW_FAMILY_TEST_V1.md para el preregistro
completo (hipótesis, universo, regla, métricas, criterios de interpretación,
lo que está diferido a v1 completo). Este script NO debe modificarse para
optimizar el resultado tras verlo — cualquier cambio de metodología después
de ejecutar esto por primera vez debe documentarse como una versión nueva,
no como un ajuste silencioso.

Investigación pura, aislada de producción (research/, no scripts/ ni
docs/data/ de producción). No toca paper_trading.py, pcs_calculator.py,
ninguna cartera ni el motor IA.

Reads:
  backtest/config/relative_family_test_v1.yaml   (universo congelado)

Writes (bajo research/relative_flow_family_test_v1/outputs/):
  relative_family_test_v1_results.json
  relative_family_test_v1_trades.csv
  relative_family_test_v1_asset_summary.csv
  relative_family_test_v1_family_summary.csv
  relative_family_test_v1_leave_one_out.csv
  relative_family_test_v1_informe.md

Usage:
  py -3 relative_family_falsification_test.py --dry-run --symbols GLD,SLV,CPER
  py -3 relative_family_falsification_test.py                  # descarga + corre todo
  py -3 relative_family_falsification_test.py --no-fetch        # usa cache de precios
  py -3 relative_family_falsification_test.py --save-cache
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from relative_flow_lib import compute_pair_series  # noqa: E402 — reuso directo, no reimplementar

CONFIG_PATH = ROOT / "backtest" / "config" / "relative_family_test_v1.yaml"
OUT_DIR = HERE / "outputs"
PRICE_CACHE = HERE / "_price_cache.parquet"

WINDOW_DAYS = 730
BLOCK_SIZE = 20
N_RANDOM_SIMS = 100
LAGS = [-1, 1, 5]  # -1 = imposible, control anti-lookahead
RNG_SEED = 20260810  # fijado por escrito en el preregistro — no cambiar tras ejecutar
BONFERRONI_N = 4  # H1 (retorno propio), H2 (sin rendimiento intrinseco), H3 (tipos/divisa), H4 (refugio/industrial)


# ── carga de config y precios ────────────────────────────────────────────
def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def load_or_fetch_prices(symbols: list[str], use_cache: bool, save_cache: bool) -> dict:
    if use_cache:
        if not PRICE_CACHE.exists():
            print(f"ERROR: --no-fetch pero no existe {PRICE_CACHE}", file=sys.stderr)
            sys.exit(1)
        wide = pd.read_parquet(PRICE_CACHE)
        return {c: wide[c].dropna() for c in wide.columns}

    import yfinance as yf
    symbols = sorted(set(symbols))
    print(f"Descargando {len(symbols)} símbolos (period=max, auto_adjust=True)...")
    raw = yf.download(symbols, period="max", auto_adjust=True, threads=True, progress=False)
    closes = {}
    if isinstance(raw.columns, pd.MultiIndex):
        close_df = raw["Close"] if "Close" in raw.columns.get_level_values(0) else pd.DataFrame()
    else:
        close_df = raw[["Close"]].rename(columns={"Close": symbols[0]}) if "Close" in raw.columns else pd.DataFrame()
    for s in symbols:
        if s in close_df.columns:
            ser = close_df[s].dropna()
            if not ser.empty:
                ser.index = pd.to_datetime(ser.index).normalize()
                closes[s] = ser
    missing = [s for s in symbols if s not in closes]
    if missing:
        print(f"  AVISO: sin datos para {missing}")
    if save_cache:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(closes).to_parquet(PRICE_CACHE)
    return closes


# ── métricas base ─────────────────────────────────────────────────────────
def cagr(total_return_frac: float, calendar_days: int) -> float | None:
    if calendar_days <= 0 or total_return_frac <= -1:
        return None
    return (1 + total_return_frac) ** (365.25 / calendar_days) - 1


def max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1
    return float(dd.min())


def build_exposure_mask(scores: np.ndarray) -> np.ndarray:
    """Día k está 'expuesto' (cuenta el retorno de ese día, es decir
    price[k]/price[k-1]) si la posición ya estaba abierta ANTES de ese día
    — se entra al cierre del día que cruza >=3 (expuesto desde el día
    SIGUIENTE, el día de entrada en sí NO cuenta — su retorno ya ocurrió
    antes de comprar) y se sale al cierre del día que cruza el umbral de
    salida (ese día SÍ cuenta, se vende a su cierre). Composición de los
    días expuestos == exactamente price[exit]/price[entry]-1 (verificado
    con test manual, ver test_relative_family_falsification.py)."""
    n = len(scores)
    exposed = np.zeros(n, dtype=bool)
    in_pos = False
    prev_score = None
    for i in range(n):
        s = scores[i]
        s_valid = s is not None and not (isinstance(s, float) and np.isnan(s))
        just_entered = False
        if prev_score is not None and s_valid:
            if not in_pos:
                if prev_score < 3 and s >= 3:
                    in_pos = True
                    just_entered = True
            else:
                if (prev_score >= 8 and s < 8) or (prev_score >= 3 and s < 3):
                    exposed[i] = True  # el día del cruce de salida SÍ cuenta (se vende a su cierre)
                    in_pos = False
                    if s_valid:
                        prev_score = s
                    continue
        if in_pos and not just_entered:
            exposed[i] = True
        if s_valid:
            prev_score = s
    return exposed


def extract_trades(dates: np.ndarray, scores: np.ndarray, prices: np.ndarray) -> list[dict]:
    trades = []
    in_pos = False
    entry_i = None
    prev_score = None
    for i in range(len(scores)):
        s = scores[i]
        s_valid = s is not None and not (isinstance(s, float) and np.isnan(s))
        if prev_score is not None and s_valid:
            if not in_pos:
                if prev_score < 3 and s >= 3:
                    in_pos = True
                    entry_i = i
            else:
                if (prev_score >= 8 and s < 8) or (prev_score >= 3 and s < 3):
                    trades.append({
                        "entry_date": str(dates[entry_i])[:10], "exit_date": str(dates[i])[:10],
                        "entry_price": float(prices[entry_i]), "exit_price": float(prices[i]),
                        "ret_pct": (float(prices[i]) / float(prices[entry_i]) - 1) * 100,
                        "bars": i - entry_i, "closed": True,
                    })
                    in_pos = False
        if s_valid:
            prev_score = s
    if in_pos and entry_i is not None:
        last_i = len(prices) - 1
        trades.append({
            "entry_date": str(dates[entry_i])[:10], "exit_date": str(dates[last_i])[:10],
            "entry_price": float(prices[entry_i]), "exit_price": float(prices[last_i]),
            "ret_pct": (float(prices[last_i]) / float(prices[entry_i]) - 1) * 100,
            "bars": last_i - entry_i, "closed": False,
        })
    return trades


def equity_from_mask(daily_ret: np.ndarray, exposed: np.ndarray) -> np.ndarray:
    """Equity curve (empieza en 1.0): compone daily_ret solo en días expuestos, flat (x1) el resto."""
    factors = np.where(exposed, 1 + daily_ret, 1.0)
    return np.cumprod(factors)


def compute_metrics_from_mask(dates: pd.DatetimeIndex, daily_ret: np.ndarray, exposed: np.ndarray,
                               bh_daily_ret: np.ndarray) -> dict:
    calendar_days = (dates[-1] - dates[0]).days
    strat_equity = equity_from_mask(daily_ret, exposed)
    bh_equity = np.cumprod(1 + bh_daily_ret)
    total_ret_strat = strat_equity[-1] - 1
    total_ret_bh = bh_equity[-1] - 1
    cagr_strat = cagr(total_ret_strat, calendar_days)
    cagr_bh = cagr(total_ret_bh, calendar_days)
    return {
        "total_return_strategy": round(total_ret_strat * 100, 2),
        "total_return_buy_hold": round(total_ret_bh * 100, 2),
        "excess_total_return": round((total_ret_strat - total_ret_bh) * 100, 2),
        "CAGR_strategy": round(cagr_strat * 100, 2) if cagr_strat is not None else None,
        "CAGR_buy_hold": round(cagr_bh * 100, 2) if cagr_bh is not None else None,
        "excess_CAGR_calendar": round((cagr_strat - cagr_bh) * 100, 2) if (cagr_strat is not None and cagr_bh is not None) else None,
        "max_drawdown_strategy": round(max_drawdown(strat_equity) * 100, 2),
        "max_drawdown_buy_hold": round(max_drawdown(bh_equity) * 100, 2),
        "exposure_pct": round(float(exposed.mean()) * 100, 1),
        "calendar_days": calendar_days,
    }


# ── placebos ──────────────────────────────────────────────────────────────
def inverted_mask(exposed: np.ndarray) -> np.ndarray:
    return ~exposed


def lagged_mask(exposed: np.ndarray, lag: int) -> np.ndarray:
    """lag>0: retrasa la exposicion (ejecucion realista con delay).
    lag<0: adelanta la exposicion (imposible — control anti-lookahead)."""
    n = len(exposed)
    out = np.zeros(n, dtype=bool)
    if lag >= 0:
        if lag < n:
            out[lag:] = exposed[:n - lag]
    else:
        k = -lag
        if k < n:
            out[:n - k] = exposed[k:]
    return out


def momentum_baseline_mask(prices: np.ndarray, window: int = 200) -> np.ndarray:
    s = pd.Series(prices)
    sma = s.rolling(window, min_periods=window).mean().to_numpy()
    with np.errstate(invalid="ignore"):
        mask = prices > sma
    mask = np.nan_to_num(mask, nan=0.0).astype(bool)
    mask[np.isnan(sma)] = False
    return mask


def block_bootstrap_percentile(daily_ret: np.ndarray, open_days: int, real_total_return: float,
                                n_sims: int, block_size: int, rng: np.random.Generator) -> dict:
    """Distribución nula: concatenar bloques de `block_size` sesiones de la
    propia serie de retornos del activo (con reemplazo) hasta acumular
    `open_days` días de exposición, componer. Repetir n_sims veces.
    Devuelve el percentil del retorno real dentro de esa distribución."""
    n = len(daily_ret)
    if open_days <= 0 or n < block_size:
        return {"percentile": None, "n_sims": 0, "sim_mean": None, "sim_median": None}
    n_blocks_needed = int(np.ceil(open_days / block_size))
    max_start = n - block_size
    sim_returns = []
    for _ in range(n_sims):
        starts = rng.integers(0, max_start + 1, size=n_blocks_needed)
        chunks = [daily_ret[s:s + block_size] for s in starts]
        synth = np.concatenate(chunks)[:open_days]
        sim_returns.append(float(np.prod(1 + synth) - 1))
    sim_returns = np.array(sim_returns)
    percentile = float((sim_returns < real_total_return).mean() * 100)
    return {
        "percentile": round(percentile, 1), "n_sims": n_sims,
        "sim_mean": round(float(sim_returns.mean()) * 100, 2),
        "sim_median": round(float(np.median(sim_returns)) * 100, 2),
    }


# ── por activo ────────────────────────────────────────────────────────────
def analyze_asset(asset: dict, closes: dict, cutoff_date: date, rng: np.random.Generator) -> dict | None:
    symbol = asset["symbol"]
    a_close = closes.get(symbol)
    spy_close = closes.get("SPY")
    if a_close is None or spy_close is None:
        return None

    df = compute_pair_series(a_close, spy_close)
    if df.empty:
        return None
    df = df[pd.to_datetime(df["date"]) >= pd.Timestamp(cutoff_date)].reset_index(drop=True)
    df = df[~df["burn_in"]].reset_index(drop=True)
    if len(df) < 60:
        return None

    dates = pd.to_datetime(df["date"]).to_numpy()
    scores = df["score"].to_numpy()

    # precio real del activo alineado a esas mismas fechas (index del ratio, no del activo per se)
    a_series = a_close.copy()
    a_series.index = pd.to_datetime(a_series.index).normalize()
    prices = np.array([a_series.get(pd.Timestamp(d), np.nan) for d in dates], dtype=float)
    valid = ~np.isnan(prices)
    if valid.sum() < 60:
        return None
    dates, scores, prices = dates[valid], scores[valid], prices[valid]

    daily_ret = np.diff(prices) / prices[:-1]
    daily_ret = np.concatenate([[0.0], daily_ret])  # dia 0 sin retorno previo

    exposed_primary = build_exposure_mask(scores)
    trades = extract_trades(dates, scores, prices)
    open_days = int(exposed_primary.sum())

    primary = compute_metrics_from_mask(pd.DatetimeIndex(dates), daily_ret, exposed_primary, daily_ret)
    n_trades = len(trades)
    closed = [t for t in trades if t["closed"]]
    hit_rate = round(sum(1 for t in closed if t["ret_pct"] > 0) / len(closed) * 100, 1) if closed else None
    avg_holding_days = round(float(np.mean([t["bars"] for t in trades])), 1) if trades else None

    inv = compute_metrics_from_mask(pd.DatetimeIndex(dates), daily_ret, inverted_mask(exposed_primary), daily_ret)

    lag_results = {}
    for lag in LAGS:
        m = lagged_mask(exposed_primary, lag)
        lag_results[f"lag_{lag:+d}d".replace("+", "p").replace("-", "m")] = \
            compute_metrics_from_mask(pd.DatetimeIndex(dates), daily_ret, m, daily_ret)["excess_CAGR_calendar"]

    mom_mask = momentum_baseline_mask(prices, window=200)
    momentum = compute_metrics_from_mask(pd.DatetimeIndex(dates), daily_ret, mom_mask, daily_ret)

    real_total_return = primary["total_return_strategy"] / 100
    boot = block_bootstrap_percentile(daily_ret[1:], open_days, real_total_return, N_RANDOM_SIMS, BLOCK_SIZE, rng)

    return {
        "id": asset["id"], "symbol": symbol, "family": asset["family"],
        "subfamily": asset.get("subfamily"), "seen_in_exploration": asset["seen_in_exploration"],
        "seen_direction_biased": asset["seen_direction_biased"],
        "include_in_primary_analysis": asset["include_in_primary_analysis"],
        "liquidity_bucket": asset.get("liquidity_bucket"), "known_duplicate_of": asset.get("known_duplicate_of"),
        "n_trades": n_trades, "hit_rate": hit_rate, "avg_holding_days": avg_holding_days,
        "n_days": len(dates), "daily_returns": daily_ret,  # se usa para correlacion intra-familia, no se serializa
        **primary,
        "inverted_excess_CAGR": inv["excess_CAGR_calendar"],
        "momentum_baseline_excess_CAGR": momentum["excess_CAGR_calendar"],
        "random_block_bootstrap": boot,
        "lag_excess_CAGR": lag_results,
        "trades": trades,
    }


# ── agregados por familia ────────────────────────────────────────────────
def family_summary(results: list[dict], family: str) -> dict:
    subset = [r for r in results if r["family"] == family and r["include_in_primary_analysis"]]
    vals = [r["excess_CAGR_calendar"] for r in subset if r["excess_CAGR_calendar"] is not None]
    if not vals:
        return {"family": family, "n": 0}
    return {
        "family": family, "n": len(vals),
        "mean_excess_CAGR": round(float(np.mean(vals)), 2),
        "median_excess_CAGR": round(float(np.median(vals)), 2),
        "pct_positive": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
        "symbols": [r["symbol"] for r in subset],
    }


def leave_one_out(results: list[dict], family: str) -> list[dict]:
    subset = [r for r in results if r["family"] == family and r["include_in_primary_analysis"]]
    out = []
    for excl in subset:
        rest = [r["excess_CAGR_calendar"] for r in subset if r["id"] != excl["id"] and r["excess_CAGR_calendar"] is not None]
        if rest:
            out.append({"family": family, "excluded": excl["symbol"],
                        "median_excess_CAGR_without": round(float(np.median(rest)), 2), "n": len(rest)})
    return out


def intra_family_correlation(results: list[dict], family: str) -> float | None:
    subset = [r for r in results if r["family"] == family and r["include_in_primary_analysis"]]
    if len(subset) < 2:
        return None
    min_len = min(len(r["daily_returns"]) for r in subset)
    mat = np.array([r["daily_returns"][-min_len:] for r in subset])
    corr = np.corrcoef(mat)
    iu = np.triu_indices_from(corr, k=1)
    return round(float(corr[iu].mean()), 3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--symbols", type=str, default=None, help="lista de símbolos, ej: GLD,SLV,CPER")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--save-cache", action="store_true")
    args = ap.parse_args()

    config = load_config()
    assets = config["assets"]
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",")}
        assets = [a for a in assets if a["symbol"].upper() in wanted]

    all_symbols = sorted({a["symbol"] for a in assets} | {"SPY"})
    closes = load_or_fetch_prices(all_symbols, use_cache=args.no_fetch, save_cache=args.save_cache)

    cutoff_date = date.today().replace(year=date.today().year) - pd.Timedelta(days=WINDOW_DAYS)
    cutoff_date = (pd.Timestamp.today() - pd.Timedelta(days=WINDOW_DAYS)).date()
    rng = np.random.default_rng(RNG_SEED)

    results = []
    for asset in assets:
        res = analyze_asset(asset, closes, cutoff_date, rng)
        if res is None:
            print(f"  saltando {asset['symbol']}: sin datos suficientes")
            continue
        results.append(res)
        marker = "*" if res["seen_direction_biased"] else (" " if res["include_in_primary_analysis"] else "-")
        print(f"  {marker} {res['symbol']:<10} fam={res['family']} n_trades={res['n_trades']:>3} "
              f"excess_CAGR={res['excess_CAGR_calendar']}")

    if args.dry_run:
        print(f"\n(dry-run, {len(results)} activos procesados, nada escrito)")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── resumen por familia + leave-one-out + correlación ──
    fam_summaries = {f: family_summary(results, f) for f in ["A", "B"]}
    loo = {f: leave_one_out(results, f) for f in ["A", "B"]}
    intra_corr = {f: intra_family_correlation(results, f) for f in ["A", "B"]}

    a_vals = [r["excess_CAGR_calendar"] for r in results if r["family"] == "A" and r["include_in_primary_analysis"] and r["excess_CAGR_calendar"] is not None]
    b_vals = [r["excess_CAGR_calendar"] for r in results if r["family"] == "B" and r["include_in_primary_analysis"] and r["excess_CAGR_calendar"] is not None]

    stat_test = {}
    if len(a_vals) >= 2 and len(b_vals) >= 2:
        u_stat, p_raw = stats.mannwhitneyu(a_vals, b_vals, alternative="greater")
        # permutation test
        combined = np.array(a_vals + b_vals)
        n_a = len(a_vals)
        real_diff = np.median(a_vals) - np.median(b_vals)
        n_perm = 10000
        rng_perm = np.random.default_rng(RNG_SEED + 1)
        count_ge = 0
        for _ in range(n_perm):
            perm = rng_perm.permutation(combined)
            diff = np.median(perm[:n_a]) - np.median(perm[n_a:])
            if diff >= real_diff:
                count_ge += 1
        p_perm = count_ge / n_perm
        stat_test = {
            "mannwhitney_u": float(u_stat), "p_raw_mannwhitney": float(p_raw),
            "p_bonferroni_mannwhitney": min(1.0, float(p_raw) * BONFERRONI_N),
            "median_diff_A_minus_B": round(float(real_diff), 2),
            "p_permutation": round(p_perm, 5),
            "p_bonferroni_permutation": round(min(1.0, p_perm * BONFERRONI_N), 5),
            "n_permutations": n_perm,
        }

    # ── serializar (sin daily_returns, no cabe en JSON limpio) ──
    def clean(r):
        d = {k: v for k, v in r.items() if k not in ("daily_returns", "trades")}
        return d

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config_version": config["version"], "frozen_date": config["frozen_date"],
        "window_days": WINDOW_DAYS, "n_random_sims": N_RANDOM_SIMS, "block_size": BLOCK_SIZE,
        "rng_seed": RNG_SEED,
        "assets": [clean(r) for r in results],
        "family_summary": fam_summaries,
        "leave_one_out": loo,
        "intra_family_correlation": intra_corr,
        "statistical_test": stat_test,
    }
    (OUT_DIR / "relative_family_test_v1_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # asset summary csv
    asset_rows = [clean(r) for r in results]
    pd.DataFrame(asset_rows).drop(columns=["lag_excess_CAGR", "random_block_bootstrap"], errors="ignore") \
        .to_csv(OUT_DIR / "relative_family_test_v1_asset_summary.csv", index=False)

    # family summary csv
    pd.DataFrame(list(fam_summaries.values())).to_csv(OUT_DIR / "relative_family_test_v1_family_summary.csv", index=False)

    # leave-one-out csv
    loo_rows = [row for fam_rows in loo.values() for row in fam_rows]
    pd.DataFrame(loo_rows).to_csv(OUT_DIR / "relative_family_test_v1_leave_one_out.csv", index=False)

    # trades csv
    trade_rows = []
    for r in results:
        for t in r["trades"]:
            trade_rows.append({"symbol": r["symbol"], "family": r["family"], **t})
    pd.DataFrame(trade_rows).to_csv(OUT_DIR / "relative_family_test_v1_trades.csv", index=False)

    print(f"\nResultados -> {OUT_DIR}")
    print(f"Familia A (n={fam_summaries['A'].get('n')}): mediana excess_CAGR = {fam_summaries['A'].get('median_excess_CAGR')}")
    print(f"Familia B (n={fam_summaries['B'].get('n')}): mediana excess_CAGR = {fam_summaries['B'].get('median_excess_CAGR')}")
    if stat_test:
        print(f"Mann-Whitney p_raw={stat_test['p_raw_mannwhitney']:.4f}  p_bonferroni={stat_test['p_bonferroni_mannwhitney']:.4f}")
        print(f"Permutation p_raw={stat_test['p_permutation']:.4f}  p_bonferroni={stat_test['p_bonferroni_permutation']:.4f}")


if __name__ == "__main__":
    main()
