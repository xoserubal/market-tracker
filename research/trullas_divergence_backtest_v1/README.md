# Backtest — sistema de divergencias MACD/Volumen/RSI + Fibonacci (David Trullás)

Investigación previa a construir la nueva pestaña "Trullás" en market-tracker
+ una cartera IA conectada en AI Picks Lab. Universo: los 118 tickers de
`portfolio.json` (Portfolio Tracker), diario, 2019-01-01 → hoy (yfinance,
`auto_adjust=False`). Solo largos (divergencias alcistas en mínimos) — ver
metodología completa y justificación de cada decisión no especificada por el
texto original en el docstring de `backtest.py`.

## Actualización 2026-09-20 — script reescrito sobre `scripts/trullas_lib.py`

A raíz de una revisión de un asesor externo (ver `CLAUDE.md`, sección
"Sistema Trullás") que señaló correctamente que `backtest.py` y
`scripts/trullas_signal_calculator.py` tenían cada uno su propia copia de
`ema`/`rsi`/`find_pivots_low` (riesgo de deriva ya sufrido antes en este
proyecto con `calcCMF`/`HARD_RULES`), ambos se reescribieron para importar
la misma librería (`scripts/trullas_lib.py`). De paso se cerró un hueco real
de reproducibilidad: el **Modelo B** (el que de verdad implementa
producción) solo existía como comandos sueltos de terminal, nunca como un
script guardado — ahora `simulate_model_b_eod()` en `backtest.py` es la
misma función `find_entry_v1()` que llama `trullas_signal_calculator.py` en
vivo, y genera `trades_eod.json` de forma reproducible.

**Corrección de parámetro detectada en el proceso:** el TP de Fibonacci
tenía dos valores ligeramente distintos entre archivos — `0.38` en el
`backtest.py` original (Modelo A) vs `0.382` en las pruebas posteriores de
Modelo B/escalera Fibonacci y en el sistema en vivo. Unificado a `0.382` en
`trullas_lib.py` (el valor real del nivel de Fibonacci, no un redondeo).
Efecto sobre los resultados ya reportados: Modelo B **idéntico** (ya usaba
0.382); Modelo A se mueve de forma marginal (mean 0.78%→0.80%, best
36.64%→37.12%, resto sin cambios apreciables) — no cambia ninguna
conclusión del análisis original.

## Resumen — dos modelos de ejecución, resultados muy distintos

### Modelo A: fills intradía (toca la zona de entrada/TP/stop con High/Low)

| Nivel | n | tickers | media | mediana | win% | peor | mejor | hold mediana |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T1+T2+T3 (todas) | 514 | 112 | +0.78% | +0.80% | 76.5% | -12.78% | +36.64% | 1d |
| T2+T3 (MACD+RSI) | 232 | 93 | +0.59% | +0.72% | 75.0% | -8.87% | +8.67% | 1d |
| **T3 (MACD+RSI+Vol)** | 123 | 69 | +0.73% | +0.74% | 74.8% | -3.78% | +8.67% | 1d |
| T1 solo (MACD) | 282 | 99 | +0.94% | +0.88% | 77.7% | -12.78% | +36.64% | 1d |

**Se evapora con coste de transacción realista.** Sensibilidad (coste
ida+vuelta asumido, todas las señales):

| Coste/operación | media | win% |
|---|---:|---:|
| 0.0pp | +0.78% | 76.5% |
| 0.3pp | +0.48% | 76.5% |
| 0.5pp | +0.28% | 72.6% |
| **1.0pp** | **-0.22%** | **40.5%** |
| 1.5pp | -0.72% | 26.5% |

Con `median(swing_pct)=6.4%`, la distancia entrada→TP es solo ~13-15% de
ese swing (≈0.8-1pp de precio) — del mismo orden que el spread real en
muchos de los tickers .V/.TO de este universo. No hay diferencia relevante
por precio de entrada (penny vs resto) ni por sufijo `.V` — el problema no
es "son solo microcaps", es que el objetivo de beneficio (franja 23%→38%)
es estructuralmente estrecho.

**Además, requiere ejecución intradía con límite en un precio exacto** —
este proyecto no tiene eso en ningún sitio: todas las carteras IA existentes
(CAVA_MACRO, MIRROR_ESPEJO, CRUCE_ROJO_D, las 4 clásicas) deciden y ejecutan
a cierre, 2×/día. El modelo A no es replicable con la arquitectura actual
sin construir infraestructura de órdenes límite nueva.

### Modelo B: fills solo a cierre diario (mismo patrón de ejecución que el resto del pipeline)

Exige que el **cierre** (no el máximo/mínimo intradía) caiga dentro de la
banda de entrada 23-25% — mucho más restrictivo, bastantes menos señales,
pero mucho más robusto:

| Nivel | n | tickers | media | mediana | win% | peor | mejor |
|---|---:|---:|---:|---:|---:|---:|---:|
| Todas las señales | 82 | 55 | +2.47% | +2.77% | 69.5% | -19.40% | +39.49% |
| **T3 (MACD+RSI+Vol)** | **16** | **14** | **+4.14%** | **+3.39%** | **75.0%** | -7.56% | +28.57% |

Sensibilidad a coste (todas las señales): +2.47%→+1.47% de 0 a 1.0pp de
coste, ganador se mantiene positivo con win% cayendo solo 76.5%→67.1% —
mucho más resistente que el modelo A.

## Lectura honesta

1. **El modelo A (el más parecido a "seguir a Trullás al pie de la letra
   con ejecución intradía perfecta") no sobrevive a costes de transacción
   realistas** y no es implementable con la arquitectura de este proyecto
   sin construir órdenes límite — descartado como base de la cartera IA.
2. **El modelo B (ejecución EOD, como el resto del pipeline) muestra un
   perfil bastante mejor** — pero con **n=82 (16 en el nivel de máxima
   confianza T3)**, muy por debajo del umbral que este proyecto ya se exige
   antes de prometer nada (~40-150 eventos independientes en varios
   preregistros: `PREREGISTRO_PCS_FLOOR_FACTORIAL_V1.md`,
   `PREREGISTRO_RANKING_SCORE_V0.md`). No hay potencia suficiente para
   distinguir señal real de suerte todavía.
3. El stop usado (ruptura del mínimo que originó la divergencia, ≈23-25%
   de riesgo por 13-15% de objetivo) **no está especificado por Trullás** —
   es mi propia decisión para poder backtestear, y es asimétrico en contra
   del trade en términos de R:R. Con un stop más ajustado el perfil podría
   mejorar más — no probado en esta primera pasada.
4. La frecuencia de señales es baja (~12-13/año sobre los 118 tickers
   combinados en el modelo B) — consistente con el propio espíritu de
   Trullás ("solo cuando los tres indicadores confirman") y con el patrón ya
   aceptado en este proyecto para señales exigentes (Cruce Rojo D percentil
   ≤10: ~10 señales/año sobre 198 tickers).

## Variante: dejar correr la tendencia (salida por cruce MACD bajista) en vez de TP fijo al 38%

A petición del usuario: misma entrada exacta que el modelo B (mismo gate
MACD, mismos niveles de confianza, mismo fill EOD en la zona 23-25%), pero
sin TP fijo — se mantiene la posición hasta el primer cruce de la línea MACD
por debajo de su señal (EMA9 del MACD), que por construcción coincide con el
histograma pasando a negativo. Sin stop de por medio en esta variante (se
deja correr literalmente hasta el cruce, tal como se pidió) y sin límite de
tiempo — las 82 señales cerraron todas dentro del histórico (0 posiciones
abiertas al final).

| Modelo | n | media | mediana | win% | std | peor | mejor | hold mediana | Sharpe-like (media/std) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Fibonacci TP 38% (original) | 82 | +2.47% | **+2.77%** | **69.5%** | 8.43 | -19.40% | +39.49% | corto | **0.293** |
| **Trend-exit (cruce MACD bajista)** | 82 | **+4.25%** | **-1.52%** | **41.5%** | **17.39** | **-31.24%** | +64.69% | 18d | 0.245 |

**Sí produce más retorno medio (+4.25% vs +2.47%, ≈+72% relativo), pero con
un perfil de riesgo notablemente peor** — firma clásica de un sistema
"dejar correr ganadores": la mediana se vuelve negativa (la mayoría de
operaciones individuales pierden dinero; el promedio lo salvan pocas
grandes), la volatilidad casi se duplica (std 17.4 vs 8.4) y el peor caso
empeora de -19% a -31%. En términos ajustados a riesgo (media/std), el
Fibonacci TP 38% es ligeramente mejor (0.293 vs 0.245) pese a tener menor
retorno bruto.

**Ambos modelos dependen de un puñado de operaciones grandes** — el top-5 de
82 operaciones explica el 60-64% de la suma total de retornos en los dos
casos (`GGAL 2019-04-30 +64.7%`, `IRS 2023-11-01 +45.5%`, `TLW.L 2020-04-03
+38.8%`... en el trend-exit). Con n=82 y esta concentración, ninguno de los
dos números de "media" es todavía fiable — un backtest futuro con más
historia/universo podría moverlo bastante en cualquier dirección.

Fichero: `trades_trend_exit.json`.

## Variante: escalera completa de niveles Fibonacci como TP fijo

A petición del usuario: ¿mejora usar el siguiente nivel de Fibonacci (50%)
como punto de cierre en vez del 38.2% original? Misma entrada/stop que el
modelo B, TP movido a cada nivel estándar de la escalera:

| TP | n | media | mediana | win% | std | Sharpe-like | peor | % cierre por stop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **38.2% (original)** | 82 | **+2.47%** | +2.77% | **69.5%** | 8.43 | **0.293** | -19.4% | 30% |
| 50% (siguiente nivel) | 82 | +1.82% | +3.24% | 59.8% | 9.88 | 0.184 | -23.4% | 39% |
| 61.8% | 82 | +1.54% | +2.60% | 52.4% | 10.20 | 0.151 | -23.4% | 46% |
| 78.6% | 82 | +2.08% | -1.50% | 47.6% | 12.59 | 0.165 | -23.4% | 51% |
| 100% | 82 | +1.86% | -1.60% | 45.1% | 12.42 | 0.150 | -23.4% | 54% |

**No mejora — empeora de forma monótona en casi todas las métricas.** Cuanto
más lejos se pone el TP en la escalera, más cae el win rate (69.5%→45.1%) y
más sube el % de operaciones que terminan cerradas por stop (30%→54%),
porque el precio tiene más recorrido para volver a tocar el stop (=c2) antes
de alcanzar un TP lejano. La media no mejora de forma consistente (fluctúa
entre 1.5% y 2.1%) y el ratio riesgo/retorno (Sharpe-like) empeora en cada
paso: **el 38.2% original sigue siendo el mejor punto de todo el barrido**,
incluso mejor que dejar correr la tendencia hasta el cruce MACD (Sharpe
0.245, ver variante anterior). Fichero: `trades_fib_ladder.json`.

## Recomendación

Construir la pestaña + la cartera IA **sobre el modelo B (fills EOD)**, no
el A — es el único ejecutable de verdad con esta arquitectura y el único que
sobrevive a costes. Pero lanzar la cartera **en modo shadow desde el primer
día** (mismo patrón que Ranking Score/P1A/P1B/P1C) — con n=82 no hay base
para operar capital real todavía, solo para empezar a acumular muestra en
paralelo mientras se usa la pestaña de forma discrecional.

## Ficheros

| Fichero | Contenido | En git |
|---|---|---|
| `backtest.py` | Script completo, metodología documentada en el docstring | Sí |
| `trades.json` | 514 operaciones del modelo A (intradía) | Sí |
| `trades_eod.json` | 82 operaciones del modelo B (EOD-only) | Sí |
| `summary.json` | Tabla resumen del modelo A por nivel | Sí |
| `ohlcv_cache.json` | OHLCV crudo cacheado, 117/118 tickers (falló `BNKR.TO`, sin histórico suficiente) | No (gitignorable, regenerable con `--force`) |

Regenerar: `py -3 backtest.py --force` (descarga fresca) o `py -3 backtest.py`
(usa la caché si existe).

## Sensibilidad de PIVOT_WINDOW (2/3/4/5 sesiones) — pedido por el usuario 2026-09-20

¿Acortar la ventana de confirmación del pivote de mínimo (menos lag,
reacciona antes) mejora el resultado del Modelo B ya validado? Script:
`pivot_window_sensitivity.py`, mismo universo/caché, todo lo demás fijo
(MIN_SWING_PCT, niveles Fibonacci, ventanas de entrada/time-stop) — solo
varía `PIVOT_WINDOW`.

| Ventana | n (todas) | media | mediana | win% | Sharpe-like | n (T3) | media T3 | win% T3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 sesiones | 91 | +0.99% | +1.43% | 62.6% | 0.191 | 12 | +1.88% | 75.0% |
| 3 sesiones | 83 | +0.60% | +1.54% | 65.1% | 0.111 | 15 | +0.04% | 60.0% |
| 4 sesiones | 85 | +1.53% | +1.82% | 69.4% | 0.244 | 17 | +4.39% | 82.4% |
| **5 sesiones (validado)** | 82 | **+2.47%** | +2.77% | **69.5%** | **0.293** | 16 | +4.14% | 75.0% |

**No ayuda — acortar la ventana no mejora el resultado.** Sobre el conjunto
completo de señales, 5 sesiones sigue siendo la mejor de las cuatro en
media, win rate y Sharpe-like; 3 sesiones es la peor con diferencia
(colapsa especialmente en el subconjunto T3: media +0.04%, prácticamente
plano). 4 sesiones queda muy cerca de 5 — incluso marginalmente mejor en el
subconjunto T3 (n=17, media +4.39% vs +4.14%) — pero con n=12-17 en T3 por
ventana, esa diferencia entra dentro del ruido, no es una señal fiable de
que 4 bata a 5.

**Lectura consistente con el hallazgo del detector anticipado** (ver
`research/trullas_early_detector_v1/`): menos confirmación tiende a
producir peor calidad de señal, no solo cuando se elimina la confirmación
fractal por completo (B0/B1), sino también al acortarla parcialmente. No se
cambia `PIVOT_WINDOW` en producción — 5 sesiones sigue siendo el mejor
punto de todo lo probado hasta ahora.

Ficheros: `trades_by_pivot_window.json`, `pivot_window_sensitivity_summary.json`.
