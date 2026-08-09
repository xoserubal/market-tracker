"""
Tests de scripts/relative_flow_lib.py — el puerto Python del scoring de
Relative Flow Lab (relative.html).

Se ejecutan sin pytest (mismo patrón que test_cava_mapping.py):
    py -3 scripts/test_relative_flow_lib.py

Cubre: RSI de Wilder (serie sintética monótona + cross-check independiente
vía pandas.ewm), align_ratio (fechas descuadradas, nulls, no-finitos),
trend_label (empates exactos), classify_label (fronteras exactas 7.9/8.0),
score end-to-end sobre una serie sintética calculada a mano, y la aserción
estructural de "no look-ahead" (cada fila solo pudo haber usado datos hasta
esa fecha). El chequeo dorado contra la página real en vivo se añade en el
paso 4 del plan (tras tener el script de reconstrucción), no aquí.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from relative_flow_lib import (  # noqa: E402
    ROOT, align_ratio, classify_labels, compute_pair_series, compute_score,
    js_round, rolling_sma, trend_label_series, vectorized_ret,
    vectorized_ret_window, wilder_rsi_expanding,
)

_passed = 0
_failed: list[str] = []


def check(name: str, got, want) -> None:
    global _passed
    ok = got == want
    if isinstance(got, float) and isinstance(want, float):
        ok = abs(got - want) < 1e-9
    if ok:
        _passed += 1
    else:
        _failed.append(f"{name}\n     esperado: {want!r}\n     obtenido: {got!r}")


def check_close(name: str, got: float, want: float, tol: float = 1e-6) -> None:
    global _passed
    if got is None or want is None:
        check(name, got, want)
        return
    if abs(got - want) <= tol:
        _passed += 1
    else:
        _failed.append(f"{name}\n     esperado: {want!r} (tol {tol})\n     obtenido: {got!r}")


def dates(n: int, start: str = "2020-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


# ── js_round ─────────────────────────────────────────────────────────────
check("js_round redondea .5 hacia arriba (positivo)", js_round(1.5), 2)
check("js_round redondea .5 hacia +Inf tambien en negativo (no banker's)", js_round(-1.5), -1)
check("js_round -2.5 -> -2 (igual que Math.round)", js_round(-2.5), -2)
check("js_round caso normal", js_round(3.14 * 10), 31)


# ── vectorized_ret / vectorized_ret_window ────────────────────────────────
idx = dates(10)
vals = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 110], index=idx)
r5 = vectorized_ret(vals, 5)
check("ret: null antes de tener `bars` barras", pd.isna(r5.iloc[4]), True)
check_close("ret: valor correcto en el primer punto valido",
            r5.iloc[5], (vals.iloc[5] / vals.iloc[0] - 1) * 100)
rw = vectorized_ret_window(vals, 2, 3)
check_close("retWindow: valor correcto", rw.iloc[6],
            (vals.iloc[4] / vals.iloc[1] - 1) * 100)

# ret/retWindow: division por 0 -> null (replica el `end && start` falsy de JS)
vals_zero = pd.Series([0, 1, 2, 3, 4, 5], index=dates(6))
r_zero = vectorized_ret(vals_zero, 1)
check("ret: prev=0 -> nan (replica falsy de JS)", pd.isna(r_zero.iloc[1]), True)


# ── rolling_sma ────────────────────────────────────────────────────────────
s = pd.Series(range(1, 11), index=dates(10))
sma5 = rolling_sma(s, 5)
check("sma: null antes de tener `len` valores", pd.isna(sma5.iloc[3]), True)
check_close("sma: media simple correcta", sma5.iloc[4], sum(range(1, 6)) / 5)


# ── wilder_rsi_expanding ────────────────────────────────────────────────────
# Serie monotona creciente -> RSI = 100 exacto (todas las perdidas son 0,
# calcRSI: `if (loss === 0) return 100`). Replica el quirk, no lo "corrige".
up_series = pd.Series(range(100, 140), index=dates(40), dtype=float)
rsi_up = wilder_rsi_expanding(up_series)
check("RSI monotono creciente -> 100 exacto", rsi_up.iloc[-1], 100.0)

# Serie monotona decreciente -> todas las ganancias son 0 -> RSI cerca de 0
down_series = pd.Series(range(140, 100, -1), index=dates(40), dtype=float)
rsi_down = wilder_rsi_expanding(down_series)
check_close("RSI monotono decreciente -> cerca de 0", rsi_down.iloc[-1], 0.0, tol=0.5)

# Cross-check independiente: ewm(alpha=1/period, adjust=False) sobre los
# deltas, sembrado con la MISMA semilla (media simple de los primeros
# `period` deltas) — si dos caminos independientes concuerdan, es más fuerte
# que confiar en uno solo.
np.random.seed(42)
noisy = pd.Series(100 + np.cumsum(np.random.randn(200)), index=dates(200))
rsi_mine = wilder_rsi_expanding(noisy, period=14)


def _rsi_ewm_crosscheck(values: pd.Series, period: int = 14) -> pd.Series:
    delta = values.diff()
    gain_first = delta.iloc[1:period + 1].clip(lower=0).sum() / period
    loss_first = (-delta.iloc[1:period + 1]).clip(lower=0).sum() / period
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    gains.iloc[period] = gain_first
    losses.iloc[period] = loss_first
    avg_gain = gains.iloc[period:].ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = losses.iloc[period:].ewm(alpha=1 / period, adjust=False).mean()
    rsi = 100 - 100 / (1 + avg_gain / avg_loss)
    rsi[avg_loss == 0] = 100.0
    out = pd.Series(np.nan, index=values.index)
    out.loc[avg_gain.index] = rsi
    return out


rsi_crosscheck = _rsi_ewm_crosscheck(noisy, period=14)
diffs = (rsi_mine - rsi_crosscheck).dropna().abs()
check("RSI cross-check (ewm alpha=1/14) coincide en toda la serie",
      bool((diffs < 1e-6).all()), True)

# Serie demasiado corta -> toda NaN
short = pd.Series([1.0, 2.0, 3.0], index=dates(3))
rsi_short = wilder_rsi_expanding(short)
check("RSI serie < period+1 -> toda NaN", bool(rsi_short.isna().all()), True)


# ── align_ratio ──────────────────────────────────────────────────────────
# Fechas descuadradas: 03 solo en a, 05 solo en b -> ninguna sobrevive al
# inner join; 01/02/04 estan en ambos lados.
a = pd.Series([10, 11, 12, 13], index=pd.to_datetime(
    ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]))
b = pd.Series([2, 2, 2, 4], index=pd.to_datetime(
    ["2024-01-01", "2024-01-02", "2024-01-05", "2024-01-04"]))
ratio = align_ratio(a, b)
check("align_ratio: solo quedan fechas presentes en ambos lados",
      list(ratio.index.strftime("%Y-%m-%d")), ["2024-01-01", "2024-01-02", "2024-01-04"])
check_close("align_ratio: valor correcto", ratio.iloc[0], 5.0)

# Division por 0 -> ratio no finito -> descartado (aunque la fecha exista en ambos)
a_z = pd.Series([10, 11], index=pd.to_datetime(["2024-03-01", "2024-03-02"]))
b_z = pd.Series([2, 0], index=pd.to_datetime(["2024-03-01", "2024-03-02"]))
ratio_z = align_ratio(a_z, b_z)
check("align_ratio: descarta division por 0 (no finito)", len(ratio_z), 1)

# nulls en una sola pata
a_with_nan = pd.Series([10, np.nan, 12], index=pd.to_datetime(
    ["2024-02-01", "2024-02-02", "2024-02-03"]))
b_clean = pd.Series([2, 2, 2], index=pd.to_datetime(
    ["2024-02-01", "2024-02-02", "2024-02-03"]))
ratio_nan = align_ratio(a_with_nan, b_clean)
check("align_ratio: descarta NaN en una sola pata", len(ratio_nan), 2)


# ── trend_label_series ───────────────────────────────────────────────────
vals_t = pd.Series([10.0, 5.0, 8.0])
s20_t = pd.Series([8.0, 5.0, 8.0])
s63_t = pd.Series([5.0, 5.0, 9.0])
trend = trend_label_series(vals_t, s20_t, s63_t)
check("trend: last>s20>s63 -> Up", trend.iloc[0], "Up")
check("trend: empate exacto last==s20==s63 -> Mixed", trend.iloc[1], "Mixed")
check("trend: last<s20 pero s20>s63 (no monotono) -> Mixed", trend.iloc[2], "Mixed")

# s20/s63 aun no definidos (NaN) -> Mixed, nunca error
trend_nan = trend_label_series(pd.Series([10.0]), pd.Series([np.nan]), pd.Series([np.nan]))
check("trend: s20/s63 NaN -> Mixed (no revienta)", trend_nan.iloc[0], "Mixed")


# ── classify_labels ──────────────────────────────────────────────────────
scores = pd.Series([8.0, 7.9, 3.0, 2.9, -3.0, -2.9, -8.0, -7.9, 0.0])
err = pd.Series([False] * 8 + [True])
labels = classify_labels(scores, err)
check("classify: 8.0 -> Leader", labels.iloc[0], "Leader")
check("classify: 7.9 -> Improving (frontera exacta)", labels.iloc[1], "Improving")
check("classify: 3.0 -> Improving", labels.iloc[2], "Improving")
check("classify: 2.9 -> Neutral (frontera exacta)", labels.iloc[3], "Neutral")
check("classify: -3.0 -> Weakening", labels.iloc[4], "Weakening")
check("classify: -2.9 -> Neutral (frontera exacta)", labels.iloc[5], "Neutral")
check("classify: -8.0 -> Laggard", labels.iloc[6], "Laggard")
check("classify: -7.9 -> Weakening (frontera exacta)", labels.iloc[7], "Weakening")
check("classify: error_mask gana sobre cualquier score", labels.iloc[8], "No data")


# ── compute_score end-to-end (calculado a mano) ───────────────────────────
r1w = pd.Series([10.0])
r1m = pd.Series([5.0])
r3m = pd.Series([-4.0])
trend_s = pd.Series(["Up"])
rsi_s = pd.Series([70.0])
flow_s = pd.Series([2.0])
# raw = 10*0.5 + 5*0.7 + (-4)*0.25 + 2 (Up) + 1.5 (rsi>65) + min(3,max(-3,2*0.4))
#     = 5 + 3.5 - 1 + 2 + 1.5 + 0.8 = 11.8 -> round(118)/10 = 11.8
score = compute_score(r1w, r1m, r3m, trend_s, rsi_s, flow_s)
check_close("compute_score end-to-end calculado a mano", score.iloc[0], 11.8)

# flow_change None -> flowAdj=0; rsi None -> rsiAdj=0; r3m None -> tratado como 0
r1w_b = pd.Series([0.0])
r1m_b = pd.Series([np.nan])
r3m_b = pd.Series([np.nan])
trend_b = pd.Series(["Mixed"])
rsi_b = pd.Series([np.nan])
flow_b = pd.Series([np.nan])
score_b = compute_score(r1w_b, r1m_b, r3m_b, trend_b, rsi_b, flow_b)
check_close("compute_score: todos los componentes ausentes -> 0.0", score_b.iloc[0], 0.0)


# ── compute_pair_series: no look-ahead + umbral de 70 barras ──────────────
np.random.seed(7)
n_days = 400
idx_full = dates(n_days)
a_full = pd.Series(100 + np.cumsum(np.random.randn(n_days) * 0.3), index=idx_full)
b_full = pd.Series(50 + np.cumsum(np.random.randn(n_days) * 0.2), index=idx_full)
df = compute_pair_series(a_full, b_full)

check("compute_pair_series: una fila por barra alineada", len(df), n_days)
check("compute_pair_series: score=None antes de 70 barras",
      pd.isna(df.iloc[68]["score"]), True)
check("compute_pair_series: label='No data' antes de 70 barras",
      df.iloc[68]["label"], "No data")
check("compute_pair_series: score SI definido en la barra 70 (index 69)",
      pd.isna(df.iloc[69]["score"]), False)
check("compute_pair_series: burn_in=True en las primeras 300 barras",
      bool(df.iloc[0]["burn_in"]), True)
check("compute_pair_series: burn_in=False pasada la barra 300",
      bool(df.iloc[300]["burn_in"]), False)

# Aserción estructural de no look-ahead: recalcular buildRow "como si hoy
# fuera la barra 150" usando solo esa porción, y comprobar que coincide con
# la fila 150 de la serie completa — si compute_pair_series mirara al futuro
# (p.ej. una rolling window centrada), esto fallaria.
cut = 150
df_partial = compute_pair_series(a_full.iloc[:cut + 1], b_full.iloc[:cut + 1])
row_full = df.iloc[cut]
row_partial = df_partial.iloc[-1]
for col in ["ratio_value", "r1w", "r1m", "r3m", "rsi", "trend", "score", "label"]:
    v_full, v_partial = row_full[col], row_partial[col]
    if isinstance(v_full, float) and pd.isna(v_full):
        check(f"no-look-ahead ({col}): ambos NaN", pd.isna(v_partial), True)
    else:
        check_close(f"no-look-ahead ({col})", v_partial, v_full) if isinstance(v_full, float) \
            else check(f"no-look-ahead ({col})", v_partial, v_full)


# ── Chequeo dorado contra la página real en vivo (paso 4 del plan) ────────
# Valores capturados ejecutando las funciones EXACTAS de relative.html
# (alignRatio/buildRow/classify, copiadas literalmente en un script Node
# aparte) contra /api/history/:symbol en el servidor local real, el
# 2026-08-08, para la última barra cerrada (2026-08-07). server.js sirve
# close SIN ajustar por dividendo con ~3 años de historia; esta
# reconstrucción usa auto_adjust=True + historia completa desde el origen.
# La pequeña divergencia esperada en r3m/r6m/score por el ajuste de
# dividendo (decisión #1 del plan) se ve en xlk_spy (score 3.9 aquí vs 4.0
# en vivo) pero NO en pares sin evento de dividendo relevante en la ventana
# (ura_urnm, gdxj_gdx: coincidencia casi exacta, r1w/r1m/rsi con diferencias
# de 4-5 decimales). Mismo trend y label en los 3 casos.
GOLDEN = {
    "xlk_spy":  {"a": "XLK", "b": "SPY", "date": "2026-08-07",
                 "r1w": 3.5608, "r1m": -1.4128, "rsi": 53.7052,
                 "trend": "Mixed", "score": 4.0, "label": "Improving", "score_tol": 0.2},
    "ura_urnm": {"a": "URA", "b": "URNM", "date": "2026-08-07",
                 "r1w": 2.3840, "r1m": 1.5331, "rsi": 60.9121,
                 "trend": "Mixed", "score": 3.7, "label": "Improving", "score_tol": 0.05},
    "gdxj_gdx": {"a": "GDXJ", "b": "GDX", "date": "2026-08-07",
                 "r1w": 1.6448, "r1m": 0.1588, "rsi": 53.6483,
                 "trend": "Mixed", "score": 1.5, "label": "Neutral", "score_tol": 0.05},
}

_price_cache = ROOT / "docs" / "data" / "_relative_flow_price_cache.parquet"
if _price_cache.exists():
    wide = pd.read_parquet(_price_cache)
    for pid, exp in GOLDEN.items():
        if exp["a"] not in wide.columns or exp["b"] not in wide.columns:
            _failed.append(f"golden {pid}: {exp['a']}/{exp['b']} no estan en la cache de precios")
            continue
        df_pair = compute_pair_series(wide[exp["a"]].dropna(), wide[exp["b"]].dropna())
        row = df_pair[df_pair["date"] == pd.Timestamp(exp["date"])]
        if row.empty:
            _failed.append(f"golden {pid}: no hay fila para {exp['date']} en la cache actual")
            continue
        row = row.iloc[0]
        check_close(f"golden {pid}: r1w", row["r1w"], exp["r1w"], tol=0.01)
        check_close(f"golden {pid}: r1m", row["r1m"], exp["r1m"], tol=0.01)
        check_close(f"golden {pid}: rsi", row["rsi"], exp["rsi"], tol=0.1)
        check(f"golden {pid}: trend", row["trend"], exp["trend"])
        check_close(f"golden {pid}: score (tolerancia por ajuste de dividendo)",
                    row["score"], exp["score"], tol=exp["score_tol"])
        check(f"golden {pid}: label", row["label"], exp["label"])
else:
    print(f"[aviso] {_price_cache} no existe todavia — chequeo dorado omitido "
          f"(ejecutar reconstruct_relative_flow_historical.py --save-cache primero)")


# ── Resultado ────────────────────────────────────────────────────────────
print(f"\n{_passed} tests pasados, {len(_failed)} fallidos")
if _failed:
    print("\nFALLOS:")
    for f in _failed:
        print(f"  - {f}")
    sys.exit(1)
