# Preregistro — Precursores de rebote tras capitulación (v1)

**Fecha de firma:** 2026-08-12, antes de construir el dataset completo de eventos
o mirar ningún resultado con grupo de control.

## Origen

Exploración puntual del mismo día (sin grupo de control): sobre 21 tickers del
Portfolio Tracker que capitularon y luego rebotaron en los últimos 6 meses, ni
RSI, ni volumen, ni forma de vela mostraban un aviso previo fiable — la única
señal consistente era retrospectiva (vela fuerte al día *siguiente* del suelo).
Limitación reconocida en ese momento: sin capitulaciones que *no* rebotaron para
comparar, nada de eso podía llamarse "discrimina un rebote", solo "acompaña a
los rebotes que hubo". Este documento congela cómo se cierra esa laguna.

## Pregunta

¿Alguna característica medible en el momento del suelo de una capitulación (o
en los días previos) tiene poder discriminante real entre capitulaciones que
después rebotan y las que no?

## Universo y datos

Los 112 tickers de `portfolio.json` (mismo universo que la exploración
puntual). Descarga yfinance `period="5y"`, diario, `auto_adjust=True` — cada
ticker usa el historial que Yahoo tenga disponible (algunos small caps/venture
tendrán bastante menos de 5 años; se incluyen igual si superan el mínimo de
barras exigido más abajo).

## Definición de "evento de capitulación" (congelada, solo mira hacia atrás)

Idéntica a la de la exploración puntual, para no cambiar de definición a mitad
de camino:

```
LOOKBACK_PEAK = 40 sesiones (ventana para buscar el pico previo)
MAX_DROP_WINDOW = 15 sesiones (la caída debe completarse en esta ventana)
MIN_DROP_PCT = 18% (caída mínima pico->suelo)
```

En la sesión `i`: `peak = max(close[i-40:i])`, `pos_gap = i - argmax(...)`. Evento
válido si `1 <= pos_gap <= 15` y `close[i]/peak - 1 <= -18%`, y `close[i]` es un
mínimo local corto (no cae >1% más en las 2 sesiones siguientes — el único uso
de datos "futuros", limitado a 2 sesiones, para fijar dónde está el suelo, sin
tocar el resultado a largo plazo que se etiqueta después).

**No solapamiento:** tras registrar un evento en `i`, no se busca el siguiente
hasta pasada la ventana de resultado (`i + RALLY_WINDOW`), para no contar varias
veces el mismo episodio de caída/recuperación en el mismo ticker.

## Definición de "rebote" (outcome, mira hacia adelante — solo para la etiqueta)

Idéntica a la exploración puntual:

```
RALLY_WINDOW = 45 sesiones tras el suelo
MIN_RALLY_PCT = 18% de subida mínima desde el suelo
MIN_RALLY_SUSTAIN_DAYS = 5 sesiones sosteniendo >= suelo+10%
```

`rebote = 1` si se cumplen las tres condiciones dentro de la ventana; si no,
`rebote = 0`. Esta etiqueta **nunca** se usa para calcular las features de la
sección siguiente — separación estricta pasado/futuro por diseño.

## Features candidatas (lista cerrada, 9 — no se añaden más después de ver datos)

Todas calculadas con datos disponibles hasta `T0` (el suelo) inclusive:

1. `rsi14_T0` — nivel de RSI(14) en el suelo
2. `rsi14_delta_T-5_T0` — cambio de RSI en los 5 días previos (deceleración/aceleración del momentum bajista)
3. `bullish_divergence` — bool: precio hace mínimo más bajo que el mínimo previo de las últimas 20-3 sesiones, pero RSI no
4. `vol_ratio_max_T-2_T0` — mayor ratio volumen/media-20 en las 3 sesiones hasta el suelo inclusive
5. `down_day_streak_into_trough` — racha de cierres a la baja hasta el suelo
6. `worst_single_day_pct_T-5_T0` — la peor caída diaria en la última semana antes del suelo
7. `atr_pct_ratio_vs_avg60` — ATR% del suelo frente a su propia media de 60 sesiones (expansión de volatilidad)
8. `drop_pct` — magnitud de la caída pico->suelo (variable de control)
9. `days_peak_to_trough` — velocidad de la caída (variable de control)

Tickers con volumen no fiable en Yahoo (serie de volumen toda a cero) quedan
`NaN` en las features 4, no se imputan a 0 — ya se vio en la exploración puntual
que algunos small caps europeos devuelven volumen vacío.

## Split dev/test

Corte por **fecha única** (mismo criterio que
`wiki/PREREGISTRO_RELATIVE_FLOW_LAB_V0.md` — no un porcentaje por ticker):
eventos con `trough_date` en los últimos 6 meses naturales antes de hoy
(2026-02-12 a 2026-08-12) → **TEST**; todo lo anterior → **DEV**. El corte se
fija por estructura temporal, antes de calcular ninguna estadística, no se
ajusta después de ver cuántos eventos caen en cada lado.

## Plan de análisis

1. **Tasa base de rebote en DEV** (descriptivo, sin condicionar en nada).
2. **Comparación por feature** (solo en DEV): Mann-Whitney U para las 7
   features continuas (rebote=1 vs rebote=0), test exacto de Fisher para
   `bullish_divergence`. Corrección Bonferroni sobre 9 comparaciones
   (`alpha = 0.05/9 ≈ 0.0056`).
3. **Rejilla pequeña, congelada aquí, no ampliable después:** 7 reglas
   univariantes/combinadas evaluadas en DEV por tasa de rebote vs tasa base:
   - R1: `rsi14_T0` en banda moderada [30,45] vs fuera
   - R2: `vol_ratio_max_T-2_T0 >= 1.5` vs `< 1.5`
   - R3: `down_day_streak_into_trough <= 1` vs `>= 2`
   - R4: `bullish_divergence == True` vs `False/NA`
   - R5: `atr_pct_ratio_vs_avg60 >= 1.3` vs `< 1.3`
   - R6: R1 AND R2
   - R7: R2 AND R3
4. **Confirmación única en TEST**, solo de lo que sobrevivió a Bonferroni en
   DEV (paso 2) y de las reglas de la rejilla que batieron la tasa base en DEV
   (paso 3) — nada que no haya sobrevivido a DEV se evalúa en TEST.

## Criterio de "plausible" (modesto, mismo listón que RFL v0)

Una feature o regla cuenta como precursor plausible solo si, en **TEST**:
mismo signo del efecto que en DEV, p<0.05, y n>=15 por brazo. Si ninguna de
las 9 features sobrevive Bonferroni en DEV, o ninguna de las supervivientes
replica en TEST, la conclusión es "sin precursor fiable identificado con estas
features" — no se amplía la rejilla ni se prueban features nuevas a posteriori.

## Fuera de alcance

No se integra nada en `paper_trading.py`, `koncorde_calculator.py` ni ninguna
cartera real a partir de este preregistro — es investigación, mismo criterio
que el resto de exploraciones de esta naturaleza en el proyecto. Si algo
sobrevive, el siguiente paso sería diseñarlo como señal shadow (mismo patrón
que `pcs_floor_whipsaw_shadow.py`), no una regla operativa directa.
