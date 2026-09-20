# Backtest — detector anticipado de mínimos (B0/B1), propuesta de un asesor externo

Investigación de la hipótesis planteada por un segundo asesor externo (ver
`CLAUDE.md`, sección "Sistema Trullás — revisión de un asesor externo"):
¿identificar un mínimo provisional (antes de que el pivote fractal se
confirme 5 sesiones después) mediante volumen extraordinario + divergencia
MACD provisional compensa el mayor riesgo de señales falsas con más
recorrido capturado?

Mismo universo/histórico que `research/trullas_divergence_backtest_v1/`
(117-118 tickers de Portfolio Tracker, 2019→hoy, `auto_adjust=False`,
reutiliza `ohlcv_cache.json` de esa carpeta). Metodología completa en el
docstring de `backtest.py`.

## Resultado — hipótesis NO respaldada

| Variante | n | tickers | media | mediana | win% | peor | mejor | Sharpe-like | % stop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **V1_OPEN** (baseline, misma ejecución) | 82 | 55 | **+1.98%** | +1.77% | **64.6%** | -19.4% | +39.4% | **0.234** | 30.5% |
| B0 (anticipado, sin RVOL) | 2722 | 116 | +0.34% | **-0.55%** | 40.2% | -38.8% | +211.1% | 0.045 | 66.4% |
| B1 (anticipado, RVOL≥4.0) | 141 | 68 | **-0.15%** | -0.12% | 36.2% | -38.8% | +29.2% | **-0.016** | 66.0% |

**B1 (la variante que el asesor proponía llevar a producción) tiene media y
Sharpe-like negativos.** B0 (el control sin filtro de volumen) tampoco
muestra ventaja real — Sharpe-like prácticamente cero (0.045), con la
mediana ya en negativo. Filtrar a solo el primer evento por episodio (evita
contar varias veces una misma caída prolongada) no cambia la conclusión
(B0: mean +0.28%/mediana -0.10%; B1: mean -0.22%/mediana -0.13%).

## Por qué falla — mecanismo, no solo el número

**Solo el 23-26% de los candidatos B0/B1 llegan a confirmarse como pivote
fractal real con la divergencia todavía sostenida.** El 74-77% restante es
una falsa alarma: o aparece un mínimo todavía más bajo antes de que el
pivote pueda confirmarse, o la divergencia se diluye contra el pivote real
que termina formándose. Esto se refleja directamente en la tasa de cierre
por stop: **66%** en B0/B1 frente al **30.5%** de V1_OPEN — entrar sobre un
mínimo sin confirmar es, mecánicamente, entrar sobre una moneda al aire
sobre si ese mínimo aguanta.

**El volumen extraordinario no discrimina entre las dos posibilidades.**
El propio asesor lo advertía (sección 8.1): "no asumir que el volumen
extraordinario implica por sí solo agotamiento vendedor... puede representar
capitulación, absorción, una noticia corporativa relevante o aceleración de
la tendencia bajista". Es exactamente lo que se observa: B1 (con RVOL≥4)
no mejora sobre B0 (sin filtro) — de hecho, sale ligeramente peor en media.

## Sensibilidad al umbral RVOL — descriptivo, confirma que no hay un punto ganador oculto

| Umbral | n | media | mediana | win% | Sharpe-like |
|---|---:|---:|---:|---:|---:|
| RVOL≥2.0 | 489 | -0.19% | -0.67% | 37.0% | -0.025 |
| RVOL≥3.0 | 232 | -0.27% | -0.56% | 34.9% | -0.030 |
| RVOL≥4.0 (propuesto) | 141 | -0.15% | -0.12% | 36.2% | -0.016 |
| RVOL≥5.0 | 86 | -0.21% | 0.00% | 38.4% | -0.023 |
| RVOL≥7.0 | 55 | +0.10% | 0.00% | 36.4% | 0.012 |

Ningún umbral entre 2x y 7x produce un Sharpe-like consistentemente
positivo — el mejor (7x) es prácticamente cero y con n=55, demasiado
pequeño para confiar en él. No hay un umbral "correcto" escondido que este
barrido no haya visto; tal como pedía el propio asesor, esto es descriptivo,
no se usa para fijar un parámetro nuevo.

## Coste real de la ejecución homogénea (hallazgo colateral)

Re-simular V1 con fill a apertura del día siguiente (en vez del mismo
cierre que genera la señal, como hacía el backtest original y como opera
hoy `TRULLAS_SHADOW`) cuesta de verdad: media 2.47%→1.98%, win 69.5%→64.6%,
Sharpe-like 0.293→0.234. Sigue siendo un resultado sólido, pero confirma que
la ejecución "al mismo cierre" de la cartera en producción hoy es una
idealización que sobreestima el resultado real esperable. No se ha tocado
`trullas_shadow_portfolio.py` en este cambio — queda anotado como pendiente.

## Conclusión y siguiente paso

**No se implementa el detector anticipado.** Ni B0 ni B1 (con ningún umbral
de RVOL probado) muestran ventaja neta sobre esperar la confirmación
fractal completa — al contrario, entrar antes de la confirmación es
mecánicamente entrar sobre una probabilidad de acierto mucho más baja (34%
de confirmación real) sin que el volumen extraordinario compense esa
pérdida de precisión. Mismo patrón que otras hipótesis descartadas en este
proyecto tras contrastarlas con datos (Capitulación Precursores, Relative
Flow Family Test): una idea intuitivamente atractiva que no sobrevive a una
prueba controlada.

No se construye B2 (confirmación por reacción del precio) — con B0/B1 ya
mostrando el problema de fondo (entrar sin confirmación es la causa
principal del mal resultado, no la ausencia de un trigger de reacción
concreto), añadir esa variante no habría cambiado la conclusión y se evita
seguir invirtiendo en una rama sin evidencia de que vaya a funcionar.

## Ficheros

| Fichero | Contenido |
|---|---|
| `backtest.py` | Script completo, reutiliza `scripts/trullas_lib.py` |
| `trades_v1_open.json` | 82 operaciones V1 con ejecución homogénea |
| `trades_b0.json` / `trades_b1.json` | Operaciones de cada variante anticipada |
| `summary.json` | Todas las tablas de arriba en formato máquina |

Regenerar: `py -3 backtest.py` (usa el `ohlcv_cache.json` ya descargado de
`research/trullas_divergence_backtest_v1/`, no vuelve a descargar nada).
