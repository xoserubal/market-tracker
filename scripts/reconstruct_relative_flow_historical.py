"""
reconstruct_relative_flow_historical.py
    — reconstruye, día a día y desde precios reales de yfinance, el scoring
      de Relative Flow Lab (relative.html: 45 ratios, Score/Leader-Improving-
      Weakening-Laggard/Trend) para poder comprobar si predice alfa vs SPY.

Ver wiki/PLAN_RELATIVE_FLOW_LAB_BACKTEST.md para el contexto completo y las
decisiones de diseño (por qué auto_adjust=True, por qué el registry se carga
vía Node y no se copia a mano, por qué el corte dev/test es una fecha única
y no un % por par, por qué esto reconstruye TODO en cada ejecución en vez de
ser append-only).

Reads:
  shared/relative-ratio-registry.js   (vía Node — decisión #3 del plan)

Writes:
  docs/data/relative_ratio_registry_export.json         (volcado del registry;
                                                           su diff delata drift)
  docs/data/relative_flow_history_reconstructed.jsonl    (reconstrucción
                                                           completa en cada
                                                           ejecución, no
                                                           append-only —
                                                           decisión #4)

Campos por fila (una por par+día): pair_id, type, cluster, a, b, date,
ratio_value, r1w, r1m, r3m, r6m, flow_change, rsi, trend, score, label,
fwd_ret_a_{1w,1m,3m}, fwd_ret_spy_{1w,1m,3m}, fwd_alpha_{1w,1m,3m}, burn_in,
split, bars_in_aligned_series, reconstructed_at.

Usage:
  py -3 scripts/reconstruct_relative_flow_historical.py --dry-run --pairs xlk_spy
  py -3 scripts/reconstruct_relative_flow_historical.py --report
  py -3 scripts/reconstruct_relative_flow_historical.py                 # full run
  py -3 scripts/reconstruct_relative_flow_historical.py --save-cache    # guarda cache de precios
  py -3 scripts/reconstruct_relative_flow_historical.py --no-fetch      # usa esa cache
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from relative_flow_lib import compute_pair_series, load_ratio_registry  # noqa: E402

DATA = ROOT / "docs" / "data"
OUT_LOG = DATA / "relative_flow_history_reconstructed.jsonl"
REGISTRY_EXPORT = DATA / "relative_ratio_registry_export.json"
PRICE_CACHE = DATA / "_relative_flow_price_cache.parquet"

HORIZONS = {"1w": 5, "1m": 21, "3m": 63}
DEV_TEST_CUTOFF_DAYS = 365
# Aviso explícito (--report) de pares con historial corto — para que no se
# descubran solos más tarde al interpretar resultados con poca n.
SHORT_HISTORY_HINT = {"AMR", "HCC", "CCJ", "URNM", "XLC", "XLRE", "URA", "BTC-USD"}


def _finite_or_none(v):
    if v is None:
        return None
    fv = float(v)
    return None if fv != fv else fv  # NaN != NaN


def extract_close_series(raw, symbols: list[str]) -> dict:
    import pandas as pd
    closes = {}
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            return closes
        close_df = raw["Close"]
        for s in symbols:
            if s in close_df.columns:
                series = close_df[s].dropna()
                if not series.empty:
                    series.index = pd.to_datetime(series.index).normalize()
                    closes[s] = series
    else:
        if "Close" in raw.columns and len(symbols) == 1:
            series = raw["Close"].dropna()
            series.index = pd.to_datetime(series.index).normalize()
            closes[symbols[0]] = series
    return closes


def load_or_fetch_closes(symbols: list[str], use_cache: bool, save_cache: bool) -> dict:
    import pandas as pd

    if use_cache:
        if not PRICE_CACHE.exists():
            print(f"ERROR: --no-fetch pero no existe {PRICE_CACHE}", file=sys.stderr)
            sys.exit(1)
        wide = pd.read_parquet(PRICE_CACHE)
        return {c: wide[c].dropna() for c in wide.columns}

    import yfinance as yf
    raw = yf.download(sorted(symbols), period="max", auto_adjust=True,
                       threads=True, progress=False)
    if raw is None or raw.empty:
        print("ERROR: yfinance no devolvió datos.", file=sys.stderr)
        sys.exit(1)

    closes = extract_close_series(raw, symbols)
    if save_cache:
        DATA.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(closes).to_parquet(PRICE_CACHE)
    return closes


def _nearest_future_return(close, asof_pos: int, bars: int):
    """Retorno desde `asof_pos` hasta `bars` sesiones después, sobre el
    propio calendario de cotización de esa serie (no el del ratio alineado).
    None si no hay suficientes sesiones futuras todavía — nunca se aproxima."""
    target_pos = asof_pos + bars
    if target_pos >= len(close):
        return None
    base = float(close.iloc[asof_pos])
    fut = float(close.iloc[target_pos])
    if base == 0:
        return None
    return round((fut / base - 1) * 100, 4)


def compute_forward_returns(close, dates_needed) -> dict:
    """Para cada fecha del ratio alineado, busca la barra más cercana <= esa
    fecha en `close` (su propio calendario) y calcula el retorno a
    5/21/63 sesiones desde ahí."""
    idx = close.index
    out = {}
    for d in dates_needed:
        pos = idx.searchsorted(d, side="right") - 1
        if pos < 0:
            out[d] = {h: None for h in HORIZONS}
        else:
            out[d] = {h: _nearest_future_return(close, pos, bars) for h, bars in HORIZONS.items()}
    return out


def reconstruct_pair(entry: dict, closes: dict, cutoff_date, now_iso: str) -> list[dict]:
    a_sym, b_sym = entry["pair"]
    a_close, b_close, spy_close = closes.get(a_sym), closes.get(b_sym), closes.get("SPY")
    if a_close is None or b_close is None or spy_close is None:
        return []

    df = compute_pair_series(a_close, b_close)
    if df.empty:
        return []

    dates_needed = list(df["date"])
    fwd_a = compute_forward_returns(a_close, dates_needed)
    fwd_spy = compute_forward_returns(spy_close, dates_needed)

    rows = []
    for _, r in df.iterrows():
        d = r["date"]
        split = "test" if d.date() >= cutoff_date else "dev"
        fa, fs = fwd_a[d], fwd_spy[d]
        alpha = {
            h: round(fa[h] - fs[h], 4) if (fa[h] is not None and fs[h] is not None) else None
            for h in HORIZONS
        }
        rows.append({
            "pair_id": entry["id"], "type": entry["type"], "cluster": entry["cluster"],
            "a": a_sym, "b": b_sym, "date": d.strftime("%Y-%m-%d"),
            "ratio_value": _finite_or_none(r["ratio_value"]),
            "r1w": _finite_or_none(r["r1w"]), "r1m": _finite_or_none(r["r1m"]),
            "r3m": _finite_or_none(r["r3m"]), "r6m": _finite_or_none(r["r6m"]),
            "flow_change": _finite_or_none(r["flow_change"]),
            "rsi": _finite_or_none(r["rsi"]),
            "trend": str(r["trend"]), "score": _finite_or_none(r["score"]), "label": str(r["label"]),
            "fwd_ret_a_1w": fa["1w"], "fwd_ret_a_1m": fa["1m"], "fwd_ret_a_3m": fa["3m"],
            "fwd_ret_spy_1w": fs["1w"], "fwd_ret_spy_1m": fs["1m"], "fwd_ret_spy_3m": fs["3m"],
            "fwd_alpha_1w": alpha["1w"], "fwd_alpha_1m": alpha["1m"], "fwd_alpha_3m": alpha["3m"],
            "burn_in": bool(r["burn_in"]), "split": split,
            "bars_in_aligned_series": int(r["bars_in_aligned_series"]),
            "reconstructed_at": now_iso,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pairs", type=str, default=None,
                     help="ids separados por coma, ej: xlk_spy,ura_urnm")
    ap.add_argument("--no-fetch", action="store_true", help="usa la cache de precios en vez de descargar")
    ap.add_argument("--save-cache", action="store_true", help="guarda la descarga para --no-fetch futuro")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    registry = load_ratio_registry()
    DATA.mkdir(parents=True, exist_ok=True)
    REGISTRY_EXPORT.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.pairs:
        wanted_ids = {p.strip() for p in args.pairs.split(",") if p.strip()}
        filtered = [e for e in registry if e["id"] in wanted_ids]
        missing = wanted_ids - {e["id"] for e in filtered}
        if missing:
            print(f"WARNING: pair ids no encontrados en el registry: {sorted(missing)}", file=sys.stderr)
        registry = filtered

    if not registry:
        print("Nada que reconstruir (registry vacío tras filtrar --pairs).", file=sys.stderr)
        sys.exit(1)

    all_syms = sorted({s for e in registry for s in e["pair"]} | {"SPY"})
    print(f"{'Usando cache de' if args.no_fetch else 'Descargando'} {len(all_syms)} símbolos "
          f"(period=max, auto_adjust=True)...")
    closes = load_or_fetch_closes(all_syms, use_cache=args.no_fetch, save_cache=args.save_cache)

    skipped = [s for s in all_syms if s not in closes]
    if skipped:
        print(f"  sin datos para: {', '.join(skipped)}")

    cutoff_date = date.today() - timedelta(days=DEV_TEST_CUTOFF_DAYS)
    now_iso = datetime.now().isoformat(timespec="seconds")

    all_rows: list[dict] = []
    summary = []
    for entry in registry:
        rows = reconstruct_pair(entry, closes, cutoff_date, now_iso)
        all_rows.extend(rows)
        is_short = bool(set(entry["pair"]) & SHORT_HISTORY_HINT)
        if rows:
            dts = [r["date"] for r in rows]
            summary.append((
                entry["id"], len(rows), dts[0], dts[-1],
                sum(r["burn_in"] for r in rows),
                sum(r["split"] == "dev" for r in rows),
                sum(r["split"] == "test" for r in rows),
                is_short,
            ))
        else:
            summary.append((entry["id"], 0, None, None, 0, 0, 0, is_short))

    if args.report:
        print(f"\n{'pair_id':<16} {'rows':>6} {'first':>12} {'last':>12} {'burn_in':>8} {'dev':>6} {'test':>6}")
        for pid, n, first, last, n_burn, n_dev, n_test, is_short in summary:
            flag = "  *short history*" if is_short else ""
            print(f"{pid:<16} {n:>6} {first or '-':>12} {last or '-':>12} "
                  f"{n_burn:>8} {n_dev:>6} {n_test:>6}{flag}")
        n_zero = sum(1 for _, n, *_ in summary if n == 0)
        print(f"\nTotal filas: {len(all_rows)}  |  pares sin datos: {n_zero}  |  "
              f"corte dev/test: {cutoff_date.isoformat()}")
        return

    if args.dry_run:
        print(f"\nWould write {len(all_rows)} rows -> {OUT_LOG} (dry-run, nada guardado)")
        for r in all_rows[-5:]:
            print(f"  {r['pair_id']} {r['date']} score={r['score']} label={r['label']} split={r['split']}")
        return

    with OUT_LOG.open("w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Escritas {len(all_rows)} filas -> {OUT_LOG}")


if __name__ == "__main__":
    main()
