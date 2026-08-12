# Hallazgos — Precursores de rebote tras capitulación (v1)

**Estado: sin precursor fiable identificado (NOT SUPPORTED), 2026-08-12.**
Preregistro: `wiki/PREREGISTRO_CAPITULACION_PRECURSORES_V1.md`. Reproducible en
`research/capitulation_precursors_v1/`.

## Contexto

Una exploración puntual sobre 21 capitulaciones que rebotaron (sin grupo de
control) no encontró ningún aviso previo fiable en RSI, volumen o forma de
vela — el único patrón era retrospectivo (vela fuerte al día siguiente del
suelo). Esta prueba cierra esa laguna con grupo de control real: **todas** las
capitulaciones detectadas en el universo (rebotaran o no), no solo las que
rebotaron.

## Dataset

112 tickers de `portfolio.json`, 5 años de histórico diario (yfinance).
**590 eventos** de capitulación detectados (caída ≥18% desde un máximo de 40
sesiones, completada en ≤15 sesiones) entre 2021-10-08 y 2026-07-30. Tasa base
de rebote (subida posterior ≥18% sostenida ≥5 sesiones) = **52%** — casi
equilibrado, como debía esperarse dado que ambas definiciones (caída y rebote)
usan umbrales de magnitud parecidos sin relación causal impuesta entre ellas.

Split temporal congelado: DEV = 529 eventos (2021-10-08→2026-02-05, 52.2% de
rebote), TEST = 61 eventos (2026-02-17→2026-07-30, 50.8% de rebote).

## Resultado — Paso 2: 9 features candidatas, comparación en DEV

| Feature | mediana rebote=1 | mediana rebote=0 | p (DEV) | ¿sobrevive Bonferroni? |
|---|---|---|---|---|
| **rsi14_T0** | 40.87 | 38.18 | **0.0033** | **Sí** |
| worst_single_day_pct_T-5_T0 | -8.98% | -7.74% | 0.034 | No (umbral 0.0056) |
| rsi14_delta_T-5_T0 | -13.69 | -14.53 | 0.59 | No |
| vol_ratio_max_T-2_T0 | 1.35× | 1.37× | 0.61 | No |
| down_day_streak_into_trough | 3 | 3 | 0.56 | No |
| atr_pct_ratio_vs_avg60 | 1.32× | 1.27× | 0.32 | No |
| drop_pct | -22.2% | -21.4% | 0.17 | No |
| days_peak_to_trough | 13 | 14 | 0.25 | No |
| bullish_divergence (n=16 con señal) | 43.8% rebote | 48.8% rebote | 0.80 | No |

Solo `rsi14_T0` sobrevive la corrección Bonferroni (9 comparaciones,
α=0.0056) — pero con un tamaño de efecto pequeño (rank-biserial = -0.148):
las capitulaciones con RSI algo más alto en el suelo (mediana 40.9 vs 38.2)
rebotan un poco más a menudo. La dirección tiene sentido intuitivo (RSI
extremo puede indicar una caída todavía en marcha, no agotada), pero la
diferencia entre medianas es de menos de 3 puntos de RSI — poca separación
práctica.

**Volumen no discrimina en absoluto** (p=0.61) — confirma con n grande lo que
ya sugería la exploración puntual: no hay un patrón de "pico de volumen en el
suelo" que distinga capitulaciones que rebotan de las que no. Tampoco la
divergencia alcista de RSI, ni la racha de días a la baja, ni la velocidad de
la caída.

## Resultado — Paso 3: rejilla de 7 reglas congeladas, en DEV

Ninguna de las 7 reglas (RSI moderado, pico de volumen, caída rápida,
divergencia, expansión de ATR, y dos combinaciones) bate la tasa base de
rebote con significación en DEV. La que más se acerca —expansión de ATR
≥1.3×— da +6.3 puntos porcentuales de tasa de rebote, pero con p=0.16, lejos
del umbral.

## Resultado — Paso 4: confirmación única en TEST

`rsi14_T0` (el único superviviente de DEV) se evaluó una sola vez en los 61
eventos de TEST (31 con rebote, 30 sin rebote): mismo signo que en DEV
(mediana 41.1 vs 38.6, rebote > no-rebote) pero **p=0.27 — no replica** al
nivel exigido (p<0.05). No cumple el criterio de "precursor plausible" fijado
en el preregistro.

## Conclusión

**Ninguna de las 9 features ni las 7 reglas candidatas pasa la barra
preregistrada de "precursor plausible".** Con 590 eventos y grupo de control
real, RSI, volumen, forma de la caída, divergencia y velocidad de la caída no
distinguen de forma fiable qué capitulaciones van a rebotar de cuáles no. Esto
confirma con rigor estadístico lo que la exploración puntual ya insinuaba: no
hay una señal de aviso previo utilizable con estos datos.

Como en el resto de exploraciones similares del proyecto (PCS↔rendimiento,
Relative Flow Lab↔alfa), el patrón visible a simple vista en un puñado de
casos (los 21 originales) no sobrevivió al añadir un grupo de control con
n mucho mayor — la razón por la que este proyecto exige preregistro y
confirmación en test antes de llamar "señal" a nada.

## Fuera de alcance / sin cambios

No se toca `paper_trading.py`, `koncorde_calculator.py`, `pcs_calculator.py`
ni ninguna cartera. No se crea ninguna señal shadow nueva — el preregistro
solo contemplaba promover algo a shadow si sobrevivía esta prueba, y nada lo
hizo.
