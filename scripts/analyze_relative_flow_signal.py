"""
analyze_relative_flow_signal.py
    — la parte barata y re-ejecutable del backtest de Relative Flow Lab:
      baseline, correlación, stats por grupo y grid search sobre el jsonl ya
      reconstruido por reconstruct_relative_flow_historical.py. No descarga
      ni recalcula precios — todo pandas puro sobre un fichero local, por
      eso es seguro "jugar con combinaciones" aquí sin re-tocar el resto.

Ver wiki/PLAN_RELATIVE_FLOW_LAB_BACKTEST.md (contexto completo) y, tras el
paso 6 del orden de trabajo, wiki/PREREGISTRO_RELATIVE_FLOW_LAB_V0.md (el
GRID congelado y la regla de selección top-3 por horizonte).

Disciplina dev/test (decisión #8 del plan): el modo normal SOLO toca `dev`.
El tramo `test` reservado solo se evalúa con --confirm-test explícito
(imprime un aviso bien visible), aplicando las combinaciones YA congeladas
del preregistro — nunca una búsqueda nueva sobre test. Esto convierte el
acuerdo "no reajustar tras ver el test" en una barrera de código.

Reads:
  docs/data/relative_flow_history_reconstructed.jsonl
  wiki/PREREGISTRO_RELATIVE_FLOW_LAB_V0.md   (solo --confirm-test, parseo del
                                               bloque JSON congelado que ese
                                               documento incluye)

Writes:
  docs/data/relative_flow_signal_results.json

Usage:
  py -3 scripts/analyze_relative_flow_signal.py                 # baseline+correlacion+stats en dev
  py -3 scripts/analyze_relative_flow_signal.py --grid           # + grid search en dev
  py -3 scripts/analyze_relative_flow_signal.py --confirm-test   # evalua el preregistro sobre test (una vez)
  py -3 scripts/analyze_relative_flow_signal.py --no-resample    # desactiva el resampleo semanal
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
HISTORY = DATA / "relative_flow_history_reconstructed.jsonl"
OUT = DATA / "relative_flow_signal_results.json"
PREREGISTRO = ROOT / "wiki" / "PREREGISTRO_RELATIVE_FLOW_LAB_V0.md"

HORIZONS = ["1w", "1m", "3m"]
MIN_GROUP_N = 20  # fijado de antemano, antes de ver ningun resultado
LABELS = ["Leader", "Improving", "Neutral", "Weakening", "Laggard"]
TRENDS = ["Up", "Down", "Mixed"]
SCORE_MIN_GRID = list(range(-8, 9))  # -8..8, 17 valores


def load_history() -> "pd.DataFrame":
    import pandas as pd
    if not HISTORY.exists():
        print(f"ERROR: no existe {HISTORY} -> ejecutar reconstruct_relative_flow_historical.py primero.",
              file=sys.stderr)
        sys.exit(1)
    rows = [json.loads(l) for l in HISTORY.read_text(encoding="utf-8").splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df[~df["burn_in"]]  # burn-in marcado, no descartado en la reconstruccion; se excluye aqui
    return df


def resample_weekly(df: "pd.DataFrame") -> "pd.DataFrame":
    """Una fila por (par, semana ISO) — mitiga la autocorrelación por
    solapamiento de las ventanas de retorno futuro (decisión #5 del plan:
    con fila diaria, 1w/1m/3m se solapan casi por completo entre días
    consecutivos). Se queda con la última observación de cada semana."""
    df = df.sort_values("date").copy()
    iso = df["date"].dt.isocalendar()
    df["_iso_year"], df["_iso_week"] = iso["year"], iso["week"]
    out = df.groupby(["pair_id", "_iso_year", "_iso_week"], as_index=False).last()
    return out.drop(columns=["_iso_year", "_iso_week"])


def split_dev_test(df: "pd.DataFrame"):
    return df[df["split"] == "dev"].copy(), df[df["split"] == "test"].copy()


def _stats(series) -> dict:
    n = len(series)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "win_rate": None}
    return {
        "n": int(n),
        "mean": round(float(series.mean()), 4),
        "median": round(float(series.median()), 4),
        "win_rate": round(float((series > 0).mean()), 4),
    }


def compute_baseline(df: "pd.DataFrame") -> dict:
    """Alfa medio/mediana/win-rate incondicional — el punto de comparación
    obligatorio (mismo principio que baselines.jsonl: nunca reportar una
    correlación o un grupo sin su baseline mecánico al lado)."""
    out = {"pooled": {h: _stats(df[f"fwd_alpha_{h}"].dropna()) for h in HORIZONS}, "by_type": {}}
    for t, g in df.groupby("type"):
        out["by_type"][t] = {h: _stats(g[f"fwd_alpha_{h}"].dropna()) for h in HORIZONS}
    return out


def compute_correlation(df: "pd.DataFrame") -> dict:
    """Pearson r + Spearman rho, p-valor, IC95% vía Fisher z. Pooled y por type."""
    from scipy import stats as sstats
    import numpy as np

    def _corr(sub, h):
        pair = sub[["score", f"fwd_alpha_{h}"]].dropna()
        n = len(pair)
        if n < MIN_GROUP_N:
            return {"n": n, "pearson_r": None, "pearson_p": None, "ci95": None,
                    "spearman_rho": None, "spearman_p": None}
        r, p = sstats.pearsonr(pair["score"], pair[f"fwd_alpha_{h}"])
        rho, sp = sstats.spearmanr(pair["score"], pair[f"fwd_alpha_{h}"])
        z = np.arctanh(np.clip(r, -0.999999, 0.999999))
        se = 1 / np.sqrt(n - 3)
        lo, hi = np.tanh(z - 1.959964 * se), np.tanh(z + 1.959964 * se)
        return {"n": n, "pearson_r": round(float(r), 4), "pearson_p": round(float(p), 6),
                "ci95": [round(float(lo), 4), round(float(hi), 4)],
                "spearman_rho": round(float(rho), 4), "spearman_p": round(float(sp), 6)}

    out = {"pooled": {h: _corr(df, h) for h in HORIZONS}, "by_type": {}}
    for t, g in df.groupby("type"):
        out["by_type"][t] = {h: _corr(g, h) for h in HORIZONS}
    return out


def _group_stat_vs_baseline(sub: "pd.DataFrame", base_mean, h: str) -> dict:
    from scipy import stats as sstats
    valid = sub[f"fwd_alpha_{h}"].dropna()
    st = _stats(valid)
    if st["n"] >= MIN_GROUP_N and base_mean is not None:
        t, p = sstats.ttest_1samp(valid, popmean=base_mean)
        st["t_stat_vs_baseline"] = round(float(t), 4)
        st["t_p_vs_baseline"] = round(float(p), 6)
    else:
        st["t_stat_vs_baseline"] = None
        st["t_p_vs_baseline"] = None
    return st


def compute_group_stats(df: "pd.DataFrame", baseline: dict) -> dict:
    """Por (label, trend): n/media/mediana/win-rate/t-test de Welch de una
    muestra vs. la media del baseline, agrupado y por type."""
    out = {"pooled": {}, "by_type": {}}
    for (label, trend), g in df.groupby(["label", "trend"]):
        key = f"{label}|{trend}"
        out["pooled"][key] = {h: _group_stat_vs_baseline(g, baseline["pooled"][h]["mean"], h)
                               for h in HORIZONS}
    for t, gt in df.groupby("type"):
        base_t = baseline["by_type"].get(t, {})
        out["by_type"][t] = {}
        for (label, trend), g in gt.groupby(["label", "trend"]):
            key = f"{label}|{trend}"
            out["by_type"][t][key] = {h: _group_stat_vs_baseline(g, base_t.get(h, {}).get("mean"), h)
                                       for h in HORIZONS}
    return out


def build_grid() -> list[dict]:
    """~200 combinaciones congeladas de antemano (decisión #8): label×trend
    (15) + score_min×trend (17×3=51), × 3 horizontes = 198."""
    grid = []
    for label in LABELS:
        for trend in TRENDS:
            grid.append({"kind": "label_trend", "label": label, "trend": trend})
    for score_min in SCORE_MIN_GRID:
        for trend in TRENDS:
            grid.append({"kind": "score_min_trend", "score_min": score_min, "trend": trend})
    return grid


def _filter_combo(df: "pd.DataFrame", combo: dict) -> "pd.DataFrame":
    if combo["kind"] == "label_trend":
        return df[(df["label"] == combo["label"]) & (df["trend"] == combo["trend"])]
    return df[(df["score"] >= combo["score_min"]) & (df["trend"] == combo["trend"])]


def run_grid_search(dev_df: "pd.DataFrame") -> list[dict]:
    """Solo sobre dev. Descarta combinaciones con n<20 (fijado de antemano).
    Ordena por alfa medio, pero reporta tambien win-rate y t-stat — el
    ranking en dev es optimista por diseño (~200 combinaciones probadas),
    lo que importa es la confirmacion en test, hecha una sola vez."""
    grid = build_grid()
    results = []
    for combo in grid:
        sub = _filter_combo(dev_df, combo)
        for h in HORIZONS:
            valid = sub[f"fwd_alpha_{h}"].dropna()
            if len(valid) < MIN_GROUP_N:
                continue
            st = _stats(valid)
            results.append({**combo, "horizon": h, **st})
    results.sort(key=lambda r: r["mean"], reverse=True)
    return results


def evaluate_test(frozen_combos: list[dict], test_df: "pd.DataFrame") -> list[dict]:
    """Aplica EXACTAMENTE las combinaciones ya congeladas del preregistro
    sobre el tramo de test. Solo alcanzable con --confirm-test."""
    out = []
    for combo in frozen_combos:
        h = combo["horizon"]
        sub = _filter_combo(test_df, combo)
        valid = sub[f"fwd_alpha_{h}"].dropna()
        out.append({**combo, "test_n": len(valid), **_stats(valid)})
    return out


def _load_frozen_combos_from_preregistro() -> list[dict]:
    if not PREREGISTRO.exists():
        print(f"ERROR: {PREREGISTRO} no existe todavia — escribirlo (paso 6) antes de --confirm-test.",
              file=sys.stderr)
        sys.exit(1)
    text = PREREGISTRO.read_text(encoding="utf-8")
    marker = "```json-frozen-combos"
    if marker not in text:
        print(f"ERROR: {PREREGISTRO} no tiene el bloque ```json-frozen-combos``` con las combinaciones congeladas.",
              file=sys.stderr)
        sys.exit(1)
    block = text.split(marker, 1)[1].split("```", 1)[0]
    return json.loads(block)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true", help="ejecuta el grid search sobre dev")
    ap.add_argument("--confirm-test", action="store_true",
                     help="evalua las combinaciones YA congeladas del preregistro sobre test (una sola vez)")
    ap.add_argument("--no-resample", action="store_true", help="desactiva el resampleo semanal")
    args = ap.parse_args()

    df = load_history()
    if not args.no_resample:
        df = resample_weekly(df)

    dev_df, test_df = split_dev_test(df)
    print(f"dev: {len(dev_df)} filas  |  test: {len(test_df)} filas "
          f"({'resampleado a 1/semana' if not args.no_resample else 'diario, SIN resamplear'})")

    baseline = compute_baseline(dev_df)
    correlation = compute_correlation(dev_df)
    group_stats = compute_group_stats(dev_df, baseline)

    print("\n== Baseline incondicional (dev, pooled) ==")
    for h in HORIZONS:
        b = baseline["pooled"][h]
        print(f"  {h}: n={b['n']} mean={b['mean']} median={b['median']} win_rate={b['win_rate']}")

    print("\n== Correlacion score vs fwd_alpha (dev, pooled) ==")
    for h in HORIZONS:
        c = correlation["pooled"][h]
        print(f"  {h}: n={c['n']} pearson_r={c['pearson_r']} (p={c['pearson_p']}, "
              f"IC95={c['ci95']})  spearman_rho={c['spearman_rho']}")

    results = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "resampled_weekly": not args.no_resample,
        "n_dev": len(dev_df), "n_test": len(test_df),
        "baseline": baseline, "correlation": correlation, "group_stats": group_stats,
    }

    if args.grid:
        print(f"\n== Grid search en dev ({len(build_grid()) * len(HORIZONS)} combinaciones evaluadas) ==")
        grid_results = run_grid_search(dev_df)
        print(f"  {len(grid_results)} combinaciones con n>={MIN_GROUP_N}")
        for r in grid_results[:15]:
            desc = f"label={r['label']}" if r["kind"] == "label_trend" else f"score>={r['score_min']}"
            print(f"  [{r['horizon']}] {desc} trend={r['trend']}: n={r['n']} mean={r['mean']} "
                  f"median={r['median']} win_rate={r['win_rate']}")
        results["grid_search_dev"] = grid_results

    if args.confirm_test:
        print("\n" + "=" * 70)
        print("  *** EVALUANDO EL TRAMO DE TEST RESERVADO — SOLO UNA VEZ ***")
        print("  Aplicando las combinaciones ya congeladas en el preregistro.")
        print("  No re-ajustar nada tras ver estos numeros.")
        print("=" * 70)
        frozen = _load_frozen_combos_from_preregistro()
        test_results = evaluate_test(frozen, test_df)
        for r in test_results:
            desc = f"label={r.get('label')}" if r["kind"] == "label_trend" else f"score>={r.get('score_min')}"
            print(f"  [{r['horizon']}] {desc} trend={r['trend']}: test_n={r['test_n']} "
                  f"mean={r['mean']} median={r['median']} win_rate={r['win_rate']}")
        results["test_confirmation"] = test_results

    DATA.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nResultados -> {OUT}")


if __name__ == "__main__":
    main()
