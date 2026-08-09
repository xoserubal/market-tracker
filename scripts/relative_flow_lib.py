"""
relative_flow_lib.py
    — funciones puras (sin I/O de red) que reproducen el pipeline de scoring
      de Relative Flow Lab (relative.html, líneas ~143-219: alignRatio, ret,
      retWindow, sma, calcRSI, buildRow, classify) en Python vectorizado.

Por qué vectorizado y no "un buildRow por día en un loop": la página en vivo
solo calcula "hoy" (una llamada, un resultado). Para reconstruir el historial
completo necesitamos, para cada día t, el resultado que buildRow habría dado
si "hoy" hubiera sido t — usando solo datos <= t (sin mirar al futuro). Las
funciones vectorizadas de este módulo producen esa serie completa de una vez,
apoyándose en que calcRSI, llamado una sola vez sobre la serie completa desde
el origen, converge (memoria de Wilder ~14 barras de vida media) al mismo
valor que recalcularlo desde cero en cada t — ver wiki/PLAN_RELATIVE_FLOW_LAB_BACKTEST.md
decisión #2. Por eso wilder_rsi_expanding es un único pase hacia adelante, no
una ventana re-sembrada.

Ninguna función aquí hace red ni decide "dev/test" — eso vive en
reconstruct_relative_flow_historical.py y analyze_relative_flow_signal.py.
Importado por ambos y por test_relative_flow_lib.py para que la lógica no
pueda desincronizarse entre el script de reconstrucción y sus tests (mismo
principio que ai_shared.py).
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent

RSI_PERIOD = 14
SMA_SHORT = 20
SMA_LONG = 63
MIN_ALIGNED_BARS = 70   # buildRow: ratio.length < 70 -> error:true, sin score
BURN_IN_BARS = 300      # decisión #2/#7: primeras 300 sesiones, marcadas no descartadas


# ── Registry ─────────────────────────────────────────────────────────────
def load_ratio_registry() -> list[dict]:
    """Carga shared/relative-ratio-registry.js vía Node (nunca copiado a mano
    — ver decisión #3 del plan). Filtra enabled===false igual que relative.html."""
    proc = subprocess.run(
        [
            "node", "-e",
            "global.window=global; require('./shared/relative-ratio-registry.js'); "
            "console.log(JSON.stringify(RATIO_REGISTRY))",
        ],
        cwd=str(ROOT), capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"no se pudo cargar el registry via node: {proc.stderr}")
    entries = json.loads(proc.stdout)
    return [e for e in entries if e.get("enabled") is not False]


# ── Redondeo fiel a JS ───────────────────────────────────────────────────
def js_round(x: float) -> float:
    """Math.round de JS redondea .5 siempre hacia +Infinity (incluso en
    negativos: Math.round(-1.5) === -1). Python round() usa banker's
    rounding — no sirve para un puerto literal. floor(x+0.5) sí coincide."""
    return math.floor(x + 0.5)


# ── Alineación de series ─────────────────────────────────────────────────
def align_ratio(a_close: "pd.Series", b_close: "pd.Series") -> "pd.Series":
    """Inner join por fecha exacta (normalizada a día, sin hora/tz) — replica
    alignRatio(aSeries, bSeries): bMap por fecha, ratio = a.close/b.close,
    se descartan fechas sin ambos lados y valores no finitos."""
    import numpy as np
    import pandas as pd

    a = a_close.copy()
    b = b_close.copy()
    a.index = pd.to_datetime(a.index).normalize()
    b.index = pd.to_datetime(b.index).normalize()

    common = a.index.intersection(b.index).sort_values()
    a2 = a.reindex(common)
    b2 = b.reindex(common)
    ratio = a2 / b2
    return ratio[np.isfinite(ratio)]


# ── Retornos vectorizados ────────────────────────────────────────────────
def vectorized_ret_window(values: "pd.Series", end_offset: int, bars: int) -> "pd.Series":
    """retWindow(arr, endOffset, bars): (end/start - 1)*100, null si falta
    historia o si end/start es 0 (replica el `end && start` falsy de JS)."""
    import numpy as np

    end = values.shift(end_offset)
    start = values.shift(end_offset + bars)
    result = (end / start - 1) * 100
    invalid = end.isna() | start.isna() | (end == 0) | (start == 0)
    result[invalid] = np.nan
    return result


def vectorized_ret(values: "pd.Series", bars: int) -> "pd.Series":
    """ret(arr, bars) es retWindow(arr, 0, bars) — mismo cuerpo en la JS
    original, aquí expresado como caso particular en vez de duplicar código."""
    return vectorized_ret_window(values, 0, bars)


def rolling_sma(values: "pd.Series", length: int) -> "pd.Series":
    """sma(values, len): media simple de los últimos `len` valores, null si
    aún no hay `len` observaciones — min_periods=length replica eso."""
    return values.rolling(window=length, min_periods=length).mean()


# ── RSI de Wilder — pase único expandible ────────────────────────────────
def wilder_rsi_expanding(values: "pd.Series", period: int = RSI_PERIOD) -> "pd.Series":
    """Puerto literal de calcRSI: semilla = media simple (por separado gain/
    loss) de los primeros `period` deltas de TODA la serie desde su origen,
    luego suavizado recursivo (prev*(period-1)+actual)/period. calcRSI en la
    JS se llama una vez con el historial completo y devuelve solo el último
    valor; aquí devolvemos el valor en cada punto de la recursión — como la
    semilla siempre se ancla al mismo origen (índice 0 de la serie), un único
    pase hacia adelante reproduce exactamente lo que calcRSI(values[0:t+1])
    habría devuelto para cada t."""
    import numpy as np
    import pandas as pd

    v = values.dropna()
    n = len(v)
    rsi = pd.Series(np.nan, index=values.index, dtype=float)
    if n < period + 1:
        return rsi

    vals = v.to_numpy(dtype=float)
    idx = v.index

    gain = 0.0
    loss = 0.0
    for i in range(1, period + 1):
        d = vals[i] - vals[i - 1]
        if d > 0:
            gain += d / period
        else:
            loss += -d / period
    rsi.loc[idx[period]] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)

    for i in range(period + 1, n):
        d = vals[i] - vals[i - 1]
        gain = (gain * (period - 1) + max(d, 0.0)) / period
        loss = (loss * (period - 1) + max(-d, 0.0)) / period
        rsi.loc[idx[i]] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)

    return rsi


# ── Trend / score / label ────────────────────────────────────────────────
def trend_label_series(values: "pd.Series", s20: "pd.Series", s63: "pd.Series") -> "pd.Series":
    """trend: last>s20>s63 -> Up; last<s20<s63 -> Down; si no (incluido
    s20/s63 aun sin definir) -> Mixed."""
    import numpy as np
    import pandas as pd

    up = (values > s20) & (s20 > s63)
    down = (values < s20) & (s20 < s63)
    label = np.where(up, "Up", np.where(down, "Down", "Mixed"))
    return pd.Series(label, index=values.index)


def compute_score(
    r1w: "pd.Series", r1m: "pd.Series", r3m: "pd.Series",
    trend: "pd.Series", rsi: "pd.Series", flow_change: "pd.Series",
) -> "pd.Series":
    """score = round(((r1w??0)*0.5 + (r1m??0)*0.7 + (r3m??0)*0.25
                       + trendAdj + rsiAdj + flowChangeAdj) * 10) / 10
    trendAdj: Up=+2 Down=-2 Mixed=0
    rsiAdj:   >65=+1.5 >55=+0.8 <35=-1.5 <45=-0.8 si no 0 (NaN rsi -> 0, igual
              que `undefined > 65` siendo false en cascada hasta el else)
    flowChangeAdj: clip(flowChange*0.4, -3, 3), 0 si flowChange es null."""
    import numpy as np
    import pandas as pd

    trend_adj = trend.map({"Up": 2.0, "Down": -2.0, "Mixed": 0.0}).astype(float)

    rsi_np = rsi.to_numpy(dtype=float)
    rsi_adj = np.select(
        [rsi_np > 65, rsi_np > 55, rsi_np < 35, rsi_np < 45],
        [1.5, 0.8, -1.5, -0.8],
        default=0.0,
    )
    rsi_adj = pd.Series(rsi_adj, index=rsi.index)

    flow_adj = (flow_change * 0.4).clip(lower=-3, upper=3).fillna(0.0)

    raw = (
        r1w.fillna(0) * 0.5
        + r1m.fillna(0) * 0.7
        + r3m.fillna(0) * 0.25
        + trend_adj
        + rsi_adj
        + flow_adj
    )
    return raw.apply(lambda x: js_round(x * 10) / 10)


def classify_labels(score: "pd.Series", error_mask: "pd.Series") -> "pd.Series":
    """classify(row): >=8 Leader, >=3 Improving, <=-8 Laggard, <=-3 Weakening,
    si no Neutral; error (bars<70) -> "No data" (gana sobre cualquier score)."""
    import numpy as np
    import pandas as pd

    score_np = score.to_numpy(dtype=float)
    labels = np.select(
        [score_np >= 8, score_np >= 3, score_np <= -8, score_np <= -3],
        ["Leader", "Improving", "Laggard", "Weakening"],
        default="Neutral",
    )
    labels = pd.Series(labels, index=score.index)
    labels[error_mask] = "No data"
    return labels


# ── Orquestador ──────────────────────────────────────────────────────────
def compute_pair_series(a_close: "pd.Series", b_close: "pd.Series") -> "pd.DataFrame":
    """Reconstruye, día a día, lo que buildRow()+classify() habrían devuelto
    si esa fecha hubiera sido "hoy" — sin mirar al futuro: cada fila solo usa
    values[0:t+1]. Los campos fwd_* (retorno futuro, la etiqueta objetivo)
    NO se calculan aquí a propósito — eso sí necesita mirar adelante, y vive
    en el script de reconstrucción para que la frontera quede explícita."""
    import pandas as pd

    ratio = align_ratio(a_close, b_close)
    n = len(ratio)
    if n == 0:
        return pd.DataFrame(columns=[
            "date", "ratio_value", "r1w", "r1m", "r3m", "r6m", "flow_change",
            "rsi", "trend", "score", "label", "burn_in", "bars_in_aligned_series",
        ])

    bars = pd.Series(range(1, n + 1), index=ratio.index)
    s20 = rolling_sma(ratio, SMA_SHORT)
    s63 = rolling_sma(ratio, SMA_LONG)

    r1w = vectorized_ret(ratio, 5)
    r1m = vectorized_ret(ratio, 21)
    r3m = vectorized_ret(ratio, 63)
    r6m = vectorized_ret(ratio, 126)

    flow_now = vectorized_ret_window(ratio, 0, 5)
    flow_prev = vectorized_ret_window(ratio, 5, 5)
    flow_change = flow_now - flow_prev

    rsi = wilder_rsi_expanding(ratio, RSI_PERIOD)
    trend = trend_label_series(ratio, s20, s63)
    score = compute_score(r1w, r1m, r3m, trend, rsi, flow_change)

    # Solo score/label dependen del umbral de 70 barras (igual que buildRow:
    # "ratio.length<70 -> error:true", sin tocar los componentes crudos).
    # trend/rsi/r1w/etc se dejan como salgan de su propia ventana natural —
    # p.ej. trend ya es "Mixed" por defecto mientras s63 no tenga 63 barras.
    error_mask = bars < MIN_ALIGNED_BARS
    label = classify_labels(score, error_mask)
    score_out = score.mask(error_mask)

    return pd.DataFrame({
        "date": ratio.index,
        "ratio_value": ratio.to_numpy(),
        "r1w": r1w.to_numpy(),
        "r1m": r1m.to_numpy(),
        "r3m": r3m.to_numpy(),
        "r6m": r6m.to_numpy(),
        "flow_change": flow_change.to_numpy(),
        "rsi": rsi.to_numpy(),
        "trend": trend.to_numpy(),
        "score": score_out.to_numpy(),
        "label": label.to_numpy(),
        "burn_in": (bars <= BURN_IN_BARS).to_numpy(),
        "bars_in_aligned_series": bars.to_numpy(),
    })
