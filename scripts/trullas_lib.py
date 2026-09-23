"""
Librería compartida del sistema Trullás (divergencias MACD/Volumen/RSI +
ejecución Fibonacci) — matemática de indicadores, detección de pivotes y la
lógica de "gate" de divergencia, usadas IDÉNTICAS por el calculador en vivo
(`scripts/trullas_signal_calculator.py`) y por el backtest
(`research/trullas_divergence_backtest_v1/backtest.py`).

Extraída 2026-09-20 a raíz de una revisión de un asesor externo (ver
CLAUDE.md, sección "Sistema Trullás") que señaló correctamente que ambos
scripts tenían cada uno su propia copia de `ema`/`rsi`/`find_pivots_low` —
mismo patrón de deriva ya sufrido antes en este proyecto (`calcCMF`
duplicado, `HARD_RULES` duplicadas antes de `ai_shared.py`). Con esta
extracción, los parámetros (`PIVOT_WINDOW`, `MIN_SWING_PCT`, niveles
Fibonacci...) tienen una única fuente de verdad — no pueden desincronizarse
entre lo que se valida en el backtest y lo que corre en producción.

Todos los parámetros son los mismos con los que se validó el backtest
2026-09-20 (research/trullas_divergence_backtest_v1/README.md) — no
recalibrados aquí.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── Parámetros — fuente única de verdad ─────────────────────────────────────
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL_SPAN = 9
RSI_PERIOD = 14
PIVOT_WINDOW = 5
MIN_SWING_PCT = 3.0
RETR_ENTRY_LOW = 0.23
RETR_ENTRY_HIGH = 0.25
RETR_TP = 0.382
ENTRY_WINDOW_BARS = 15
TIME_STOP_BARS = 20
RVOL_WINDOW = 20
EARLY_VOLUME_SPIKE_THRESHOLD = 4.0  # punto de partida de investigación, no calibrado (ver advisor externo)

# Escala GBX/GBp — algunos tickers .L de Yahoo vienen en peniques, no libras.
# Mismo hallazgo que research/koncorde_cross_backtest_2026-08/README.md.
GBX_SUFFIX = ".L"
GBX_THRESHOLD = 1000.0


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd_full(close: pd.Series):
    """Devuelve (línea MACD, línea señal, histograma) — EMA 12/26/9 estándar."""
    m = ema(close, MACD_FAST) - ema(close, MACD_SLOW)
    sig = ema(m, MACD_SIGNAL_SPAN)
    hist = m - sig
    return m, sig, hist


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.where(avg_loss != 0, 100.0)


def find_pivots_low(close: np.ndarray, window: int = PIVOT_WINDOW) -> list[int]:
    """Índices donde close[i] es el mínimo estricto en [i-window, i+window].
    Un pivote no se confirma hasta `window` barras después — lag real, no bug."""
    n = len(close)
    idx = []
    for i in range(window, n - window):
        seg = close[i - window:i + window + 1]
        if close[i] == seg.min() and (seg == close[i]).sum() == 1:
            idx.append(i)
    return idx


def rvol(volume: np.ndarray, idx: int, window: int = RVOL_WINDOW) -> float | None:
    """Volumen relativo de la sesión `idx` frente a la media de las `window`
    sesiones ANTERIORES (excluye la propia sesión `idx` de la media — mismo
    criterio que pidió el asesor externo, evita que un pico de hoy infle su
    propia referencia). `None` si no hay suficiente histórico previo.

    No se usa todavía en ninguna señal — se calcula y persiste para poder
    estudiar más adelante la hipótesis de detección anticipada mediante
    volumen extraordinario (ver CLAUDE.md, revisión del asesor externo
    2026-09-20), sin esperar meses adicionales a que exista histórico una
    vez se decida construir esa parte."""
    if idx < window:
        return None
    window_vals = volume[idx - window:idx]
    mean_vol = window_vals.mean()
    if mean_vol <= 0 or np.isnan(mean_vol):
        return None
    return float(volume[idx] / mean_vol)


def apply_gbx_scale_fix(ticker: str, df: pd.DataFrame, price_cols: list[str],
                         log_fn=print) -> None:
    """Corrige in-place el hallazgo de escala GBX/GBp en tickers .L —
    mismo criterio ya usado en cruce_rojo_d_portfolio.py y el backtest."""
    if ticker.endswith(GBX_SUFFIX) and df[price_cols[0]].mean() > GBX_THRESHOLD:
        for c in price_cols:
            df[c] = df[c] / 100.0
        log_fn(f"  [scale-fix] {ticker}: dividido por 100 (GBX->GBP sospechoso)")


def evaluate_pivot_pair(close: np.ndarray, macd_arr: np.ndarray, rsi_arr: np.ndarray,
                         vol: np.ndarray, a: int, b: int) -> dict | None:
    """Evalúa el par de pivotes de mínimo (a=más antiguo, b=más reciente):
    ¿hay divergencia MACD (gate obligatorio)? ¿RSI/Volumen confirman (tier)?
    Devuelve None si no pasa el gate MACD o el swing mínimo — en ese caso no
    hay señal, el resto de indicadores ni se consulta (literal del método).

    No decide si hay entrada HOY — eso lo resuelve find_entry_v1() escaneando
    hacia delante desde `b`, porque la zona de entrada puede tardar varias
    sesiones en alcanzarse."""
    c1, c2 = float(close[a]), float(close[b])
    if not (c2 < c1):
        return {"reason": "no_lower_low", "pivot1_close": c1, "pivot2_close": c2}

    swing_pct = (c1 - c2) / c1 * 100
    if swing_pct < MIN_SWING_PCT:
        return {"reason": "swing_too_small", "pivot1_close": c1, "pivot2_close": c2,
                "swing_pct": swing_pct}

    if np.isnan(macd_arr[a]) or np.isnan(macd_arr[b]):
        return {"reason": "insufficient_history", "pivot1_close": c1, "pivot2_close": c2,
                "swing_pct": swing_pct}

    macd_div = bool(macd_arr[b] > macd_arr[a])
    if not macd_div:
        return {"reason": "no_macd_divergence", "pivot1_close": c1, "pivot2_close": c2,
                "swing_pct": swing_pct, "macd_div": False}

    rsi_div = bool(not np.isnan(rsi_arr[a]) and not np.isnan(rsi_arr[b]) and rsi_arr[b] > rsi_arr[a])
    vol_div = bool(vol[b] > vol[a])  # Método A: volumen de la vela exacta del pivote
    # (no el pico del tramo — ver revisión del asesor externo, "Método B" sin
    # implementar, ambigüedad documentada en CLAUDE.md, no resuelta aquí)
    tier = 1
    if rsi_div:
        tier = 2
    if rsi_div and vol_div:
        tier = 3

    swing = c1 - c2
    entry_low = c2 + RETR_ENTRY_LOW * swing
    entry_high = c2 + RETR_ENTRY_HIGH * swing
    tp = c2 + RETR_TP * swing
    stop = c2

    return {
        "reason": None, "qualifies": True,
        "pivot1_close": c1, "pivot2_close": c2, "swing_pct": swing_pct,
        "macd_div": True, "rsi_div": rsi_div, "vol_div": vol_div, "tier": tier,
        "entry_low": entry_low, "entry_high": entry_high, "tp": tp, "stop": stop,
    }


def find_entry_v1(close: np.ndarray, entry_low: float, entry_high: float, stop: float,
                   start_idx: int, max_idx_exclusive: int) -> dict:
    """Escanea close[start_idx:max_idx_exclusive] buscando el primer cierre
    que caiga en [entry_low, entry_high] (fill EOD — el modelo validado en
    el backtest, no el de fills intradía). Si el precio rompe `stop` antes
    de entrar, la señal queda invalidada en ese punto.

    Devuelve {"outcome": "entry"|"invalidated"|"no_entry_yet", "idx": int|None}."""
    for j in range(start_idx, max_idx_exclusive):
        if close[j] <= stop:
            return {"outcome": "invalidated", "idx": j}
        if entry_low <= close[j] <= entry_high:
            return {"outcome": "entry", "idx": j}
    return {"outcome": "no_entry_yet", "idx": None}


def find_entry_executable(open_: np.ndarray, entry_low: float, entry_high: float, stop: float,
                           start_idx: int, max_idx_exclusive: int) -> dict:
    """Orden límite real (corregido 2026-09-21 a raíz de una revisión
    externa, ver CLAUDE.md — reemplaza al modelo `find_entry_v1` de fill al
    mismo cierre que genera la señal, que sobreestimaba el resultado real
    ejecutable). Evalúa cada sesión por su APERTURA, no su cierre — es el
    único precio sobre el que se puede actuar de verdad con la cadencia de
    este pipeline (decisiones una vez al día sobre datos ya cerrados, sin
    monitorización intradía).

    Rellena si entry_low <= open <= entry_high (la misma zona 23-25% que
    exige la regla original — NO cualquier apertura por debajo del techo:
    una primera versión de este fix aceptaba eso y colaba entradas casi al
    mismo mínimo, un perfil de riesgo distinto, corregido antes de usarse).
    Invalidada si open <= stop. Si la apertura está fuera de la zona (por
    encima o por debajo) sin haber invalidado, la orden sigue activa y se
    prueba la sesión siguiente — no se persigue el precio por encima ni se
    acepta uno por debajo de la zona.

    Verificado contra 82 señales reales de V1 antes de adoptarlo: con
    find_entry_v1 + fill ingenuo a la apertura siguiente, solo 34/82 (41%)
    tenían una apertura siguiente realmente válida — 41 (50%) ya habían
    rebasado la zona y 7 (8.5%) ya habían roto el stop. find_entry_executable
    filtra esos casos correctamente en vez de rellenar a un precio que la
    regla original no habría aceptado.

    Devuelve {"outcome": "entry"|"invalidated"|"no_entry_yet", "idx": int|None}."""
    for j in range(start_idx, max_idx_exclusive):
        if open_[j] <= stop:
            return {"outcome": "invalidated", "idx": j}
        if entry_low <= open_[j] <= entry_high:
            return {"outcome": "entry", "idx": j}
    return {"outcome": "no_entry_yet", "idx": None}


# ── Detector anticipado (B0/B1) — investigación, no en producción ──────────
# Añadido 2026-09-20 a raíz de la propuesta de un asesor externo: identificar
# un posible mínimo ANTES de que el pivote fractal se confirme 5 sesiones
# después (ver CLAUDE.md, sección "Sistema Trullás — revisión de un asesor
# externo"). Ninguna función de aquí abajo se usa en
# trullas_signal_calculator.py ni en trullas_shadow_portfolio.py todavía —
# solo en research/trullas_early_detector_v1/.


def reference_confirmed_pivot_asof(pivots: list[int], t: int, window: int = PIVOT_WINDOW) -> int | None:
    """Último pivote de mínimo YA CONFIRMADO a fecha `t` (pivote p tal que
    p + window <= t, es decir, sus `window` barras de confirmación a la
    derecha ya han pasado en o antes de `t`). None si no hay ninguno.

    `pivots` puede ser la lista completa calculada sobre toda la serie —
    filtrar por `p + window <= t` es equivalente a recomputar find_pivots_low
    solo con datos hasta `t` (un pivote confirmado con datos futuros a t no
    pudo haber usado ninguna barra posterior a p+window para confirmarse),
    pero muchísimo más barato que repetir el escaneo día a día."""
    candidates = [p for p in pivots if p + window <= t]
    return candidates[-1] if candidates else None


def evaluate_early_candidate_b0(close: np.ndarray, macd_arr: np.ndarray,
                                 t: int, ref_pivot_idx: int | None) -> dict | None:
    """Variante B0 (control, SIN exigir volumen extraordinario) — aísla si
    anticiparse por sí solo (antes de la confirmación fractal) aporta algo,
    independientemente del volumen. Condición literal (asesor externo,
    sección 8.3-8.4): nuevo mínimo de 5 sesiones + inferior al pivote de
    referencia + divergencia MACD provisional contra ese mismo pivote.

    None si no califica. El pivote de referencia debe estar YA CONFIRMADO
    antes de `t` (nunca un pivote futuro) — responsabilidad del caller pasar
    el resultado de reference_confirmed_pivot_asof()."""
    if ref_pivot_idx is None or t < 5:
        return None
    c1, c2 = float(close[ref_pivot_idx]), float(close[t])
    if not (c2 < c1):
        return None
    if not (c2 < close[t - 5:t].min()):
        return None  # no es un mínimo nuevo de 5 sesiones
    swing_pct = (c1 - c2) / c1 * 100
    if swing_pct < MIN_SWING_PCT:
        return None
    if np.isnan(macd_arr[ref_pivot_idx]) or np.isnan(macd_arr[t]):
        return None
    if not (macd_arr[t] > macd_arr[ref_pivot_idx]):
        return None

    swing = c1 - c2
    return {
        "ref_pivot_idx": ref_pivot_idx, "t": t,
        "ref_pivot_close": c1, "provisional_low_close": c2, "swing_pct": swing_pct,
        "tp": c2 + RETR_TP * swing, "stop": c2,
    }


# ── Divergencia con ventana extendida (6 meses) — investigación, no en ─────
# producción. Añadido 2026-09-23 a petición del usuario tras revisar QXO:
# el gate estándar (evaluate_pivot_pair) solo compara el pivote inmediatamente
# anterior — un rebote intermedio "resetea" la cadena y esconde una
# divergencia real de varios meses (caso real: QXO marzo-agosto 2026, ver
# CLAUDE.md). Ninguna función de aquí abajo se usa en
# trullas_signal_calculator.py ni en trullas_shadow_portfolio.py todavía —
# solo en research/trullas_extended_divergence_v1/.
EXTENDED_LOOKBACK_BARS = 126     # ~6 meses de sesiones (21 x 6) — pedido literal del usuario
EXTENDED_STALL_FRACTION = 0.25  # sin calibrar, primera pasada (mismo estilo que EARLY_VOLUME_SPIKE_THRESHOLD)


def find_extended_reference(close: np.ndarray, pivots: list[int],
                             a_idx: int, b_idx: int,
                             lookback_bars: int = EXTENDED_LOOKBACK_BARS) -> int | None:
    """El pivote con el PRECIO más bajo (no el MACD más negativo — ver nota)
    entre los que caen en la ventana de `lookback_bars` antes de `b_idx`,
    exigiendo que sea estrictamente anterior a `a_idx` (el predecesor
    inmediato ya evaluado por el método estándar) — así solo se considera
    si de verdad aporta algo "más allá" de lo que
    evaluate_pivot_pair(a_idx, b_idx) ya comprueba. None si no hay ningún
    candidato en esa ventana.

    Bug real encontrado y corregido en la propia verificación (2026-09-23):
    la primera versión seleccionaba el pivote de MACD MÁS NEGATIVO como
    referencia — pero entonces "macd_higher" (¿el MACD de hoy es mayor que
    el de la referencia?) es casi una tautología, porque la referencia YA
    ES el mínimo por construcción. Sobre el universo real esto disparó
    "divergencia" en 896 casos con 100% de acierto a 5 días — imposible
    para una señal de mercado real, señal inequívoca de un sesgo de
    diseño. Seleccionar por PRECIO más bajo (eje independiente del que se
    prueba, el MACD) evita la tautología: que el precio de hoy sea más
    bajo que el mínimo histórico NO está garantizado por construcción (b
    puede o no superar ese mínimo), y que el MACD de hoy sea más alto que
    el de aquel mínimo de precio tampoco lo está — es la comparación real
    que la divergencia técnica clásica exige."""
    window_start = max(0, b_idx - lookback_bars)
    candidates = [p for p in pivots if window_start <= p < a_idx]
    if not candidates:
        return None
    return min(candidates, key=lambda p: close[p])


def classify_extended_divergence(close: np.ndarray, macd_arr: np.ndarray,
                                  r_idx: int, b_idx: int,
                                  min_swing_pct: float = MIN_SWING_PCT) -> tuple[str, float]:
    """Clasifica la relación entre el pivote de referencia extendida `r_idx`
    y el pivote actual `b_idx` — devuelve (categoria, swing_pct_ref_a_pivote).

    Categorías (documentadas explícitamente para no dejarlas ambiguas):
      "FULL"                                precio hace mínimo MÁS BAJO que
                                             la referencia Y el MACD es MÁS
                                             ALTO — divergencia completa,
                                             misma definición que
                                             evaluate_pivot_pair, aplicada a
                                             un par más separado en el tiempo.
      "PARTIAL_FLAT_PRICE_RISING_MOMENTUM"  precio prácticamente IGUAL (doble
                                             suelo, dentro de min_swing_pct)
                                             pero el MACD sí mejora con
                                             claridad — sin caída de precio
                                             que retraceder, no forma una
                                             estructura Fibonacci válida.
      "PARTIAL_LOWER_LOW_STALLING_MOMENTUM" precio hace mínimo más bajo, el
                                             MACD no llega a ser más alto,
                                             pero cae mucho menos de lo que
                                             cabría esperar dado su propio
                                             rango en la ventana — el
                                             momentum se "resiste" a
                                             confirmar la caída de precio
                                             sin llegar a formar un mínimo
                                             más alto en términos absolutos.
      "NONE"                                nada de lo anterior.
    """
    c_r, c_b = float(close[r_idx]), float(close[b_idx])
    macd_r, macd_b = float(macd_arr[r_idx]), float(macd_arr[b_idx])
    swing_pct_rb = (c_r - c_b) / c_r * 100  # positivo si b_idx está más bajo que r_idx

    price_lower = swing_pct_rb >= min_swing_pct
    price_flat = abs(swing_pct_rb) < min_swing_pct
    macd_higher = macd_b > macd_r

    if np.isnan(macd_r) or np.isnan(macd_b):
        return "NONE", swing_pct_rb

    if price_lower and macd_higher:
        return "FULL", swing_pct_rb
    if price_flat and macd_higher:
        return "PARTIAL_FLAT_PRICE_RISING_MOMENTUM", swing_pct_rb
    if price_lower and not macd_higher:
        window = macd_arr[r_idx:b_idx + 1]
        window = window[~np.isnan(window)]
        macd_range = float(window.max() - window.min()) if len(window) else 0.0
        if macd_range > 0 and (macd_r - macd_b) < EXTENDED_STALL_FRACTION * macd_range:
            return "PARTIAL_LOWER_LOW_STALLING_MOMENTUM", swing_pct_rb
    return "NONE", swing_pct_rb


# ── "Fallo de MACD" / fallo bajista de implicaciones alcistas — ────────────
# investigación, no en producción. Añadido 2026-09-23 a petición del usuario
# (descripción literal del método Trullás, ver CLAUDE.md "Detector MACD
# Failure Swing"). Ninguna función de aquí abajo se usa en
# trullas_signal_calculator.py ni en trullas_shadow_portfolio.py todavía —
# solo en research/trullas_macd_failure_swing_v1/, pendiente de decidir tras
# el backtest si se expone como panel en trullas.html.

def find_bullish_cross_between(macd_line: np.ndarray, signal_line: np.ndarray,
                                start_idx_exclusive: int, end_idx_inclusive: int) -> int | None:
    """Primer índice en (start_idx_exclusive, end_idx_inclusive] donde la
    línea MACD cruza de por debajo a por encima/igual de su señal (línea[i-1]
    < señal[i-1] y línea[i] >= señal[i]). None si no hay ningún cruce en ese
    tramo."""
    for i in range(start_idx_exclusive + 1, end_idx_inclusive + 1):
        if macd_line[i - 1] < signal_line[i - 1] and macd_line[i] >= signal_line[i]:
            return i
    return None


def evaluate_macd_failure_swing(close: np.ndarray, macd_line: np.ndarray, signal_line: np.ndarray,
                                 a_idx: int, b_idx: int, require_turn_up: bool = True,
                                 strict_stretch: bool = True) -> dict | None:
    """"Fallo bajista de implicaciones alcistas" (Trullás) — mismo par de
    pivotes de mínimo CONSECUTIVOS (a=más antiguo, b=más reciente) que
    evaluate_pivot_pair(), pero un gate DISTINTO: en vez de comparar el
    valor crudo del MACD entre los dos pivotes (macd[b] > macd[a]), exige
    una secuencia concreta sobre la RELACIÓN línea-vs-señal:

      1. En el pivote `a`, la línea MACD está por debajo de su señal
         (estado bajista de partida).
      2. Entre `a` y `b` la línea cruza al ALZA sobre su señal (recuperación).
      3. El precio cae de nuevo y marca un mínimo más bajo en `b`.
      4. La línea MACD, aunque retrocede, no vuelve a mostrar la
         configuración bajista de partida. Dos lecturas posibles de esto,
         controladas por `strict_stretch` — la pregunta quedó explícita
         con el usuario tras el primer backtest (2026-09-23/24), que solo
         probó la estricta:
           - `strict_stretch=True` (por defecto, versión ya validada): la
             línea permanece por encima/igual de su señal en TODO el tramo
             entre el cruce alcista y `b` — cualquier cruce por debajo en
             medio invalida el patrón.
           - `strict_stretch=False` (versión laxa, 2026-09-24): solo se
             exige que, EN EL INSTANTE de `b`, la línea siga por
             encima/igual de su señal — permite que haya oscilado por
             debajo en algún punto intermedio del tramo, mientras no esté
             por debajo justo cuando el precio marca el nuevo mínimo.
      5. Para el momento en que el pivote `b` queda confirmado
         (b + PIVOT_WINDOW, mismo lag de confirmación que el resto del
         sistema), la línea MACD ya ha vuelto a girar al alza
         (macd[b+PIVOT_WINDOW] > macd[b]) — la parte "vuelve a girarse al
         alza" de la descripción. `require_turn_up=False` la desactiva,
         para el análisis de sensibilidad.

    Devuelve None si no hay suficiente historia para evaluar el tramo
    completo (nunca False encubierto en None — mismo principio que el resto
    de evaluadores del proyecto). Si no califica, un dict con "reason". Si
    califica, un dict con "qualifies": True y los índices relevantes.
    """
    c1, c2 = float(close[a_idx]), float(close[b_idx])
    if not (c2 < c1):
        return {"reason": "no_lower_low"}
    swing_pct = (c1 - c2) / c1 * 100
    if swing_pct < MIN_SWING_PCT:
        return {"reason": "swing_too_small", "swing_pct": swing_pct}

    seg_macd, seg_sig = macd_line[a_idx:b_idx + 1], signal_line[a_idx:b_idx + 1]
    if np.isnan(seg_macd).any() or np.isnan(seg_sig).any():
        return {"reason": "insufficient_history", "swing_pct": swing_pct}

    if not (macd_line[a_idx] < signal_line[a_idx]):
        return {"reason": "no_bearish_anchor_at_a", "swing_pct": swing_pct}

    cross_idx = find_bullish_cross_between(macd_line, signal_line, a_idx, b_idx)
    if cross_idx is None:
        return {"reason": "no_bullish_cross_between", "swing_pct": swing_pct}

    if strict_stretch:
        stretch_macd = macd_line[cross_idx:b_idx + 1]
        stretch_sig = signal_line[cross_idx:b_idx + 1]
        if not np.all(stretch_macd >= stretch_sig):
            return {"reason": "macd_crossed_back_below", "swing_pct": swing_pct, "cross_idx": int(cross_idx)}
    else:
        if not (macd_line[b_idx] >= signal_line[b_idx]):
            return {"reason": "macd_below_signal_at_b", "swing_pct": swing_pct, "cross_idx": int(cross_idx)}

    if require_turn_up:
        confirm_idx = b_idx + PIVOT_WINDOW
        if confirm_idx >= len(macd_line) or np.isnan(macd_line[confirm_idx]) or np.isnan(macd_line[b_idx]):
            return {"reason": "not_confirmable_yet", "swing_pct": swing_pct, "cross_idx": int(cross_idx)}
        if not (macd_line[confirm_idx] > macd_line[b_idx]):
            return {"reason": "macd_not_turning_up", "swing_pct": swing_pct, "cross_idx": int(cross_idx)}

    return {
        "reason": None, "qualifies": True,
        "pivot_a_close": c1, "pivot_b_close": c2, "swing_pct": swing_pct,
        "cross_idx": int(cross_idx),
    }
