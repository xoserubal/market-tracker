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

## Corrección 2026-09-21 — bug real en V1_OPEN, encontrado por una revisión externa

Un tercer asesor externo señaló como "prioridad máxima" comprobar si la
apertura de la sesión siguiente (usada como fill homogéneo, ver sección
más abajo) era en sí misma una entrada válida según las reglas originales
— V1_OPEN (ahora renombrado `V1_OPEN_NAIVE`) rellenaba a esa apertura
**sin comprobar nada**. Verificado contra datos reales antes de corregir:
de las 82 operaciones originales, **solo 34 (41%) tenían la apertura
siguiente realmente dentro de la zona 23-25%** — 41 (50%) abrían ya por
encima de la zona (perseguir un precio que la regla dice que no hay que
perseguir) y 7 (8.5%) abrían ya por debajo del stop (un trade que nace
invalidado).

**`V1_EXECUTABLE`** (nuevo, `simulate_v1_executable()`): una orden límite
real, activa desde que la divergencia MACD confirma hasta que expira la
ventana de 15 sesiones, evaluada día a día por la **apertura** (no el
cierre) — solo rellena si `entry_low <= open <= entry_high`, exactamente
la misma zona que exige la regla original, sin perseguir precios por
encima ni aceptar precios muy por debajo (una primera versión de este fix
aceptaba cualquier apertura ≤ entry_high, lo que colaba entradas casi al
mismo mínimo — un perfil de riesgo distinto, no lo que V1 especifica;
corregido a la zona estricta antes de reportar nada).

| Variante | n | media | mediana | win% | Sharpe-like | % stop |
|---|---:|---:|---:|---:|---:|---:|
| V1 original (fill al mismo cierre que genera la señal) | 82 | +2.47% | +2.77% | 69.5% | **0.293** | 30.5% |
| V1_OPEN_NAIVE (apertura siguiente, sin comprobar elegibilidad — con bug) | 82 | +1.98% | +1.77% | 64.6% | 0.234 | 30.5% |
| **V1_EXECUTABLE (orden límite real, corregido)** | **54** | **+1.27%** | +2.02% | 66.7% | **0.151** | 33.3% |

**El coste real de una ejecución honesta es mayor del que se había
reportado.** No son 82 operaciones ejecutables, son 54 (28 de las 82
señales originales nunca llegan a rellenar dentro de la ventana bajo una
disciplina de ejecución real) y el Sharpe-like cae a **casi la mitad**
(0.293→0.151) frente al modelo idealizado que sigue operando
`TRULLAS_SHADOW` hoy en producción. La dirección sigue siendo positiva —
la señal no se invalida — pero es notablemente más débil de lo que
mostraba el número original. Ficheros:
`trades_v1_open_naive.json` (con el bug, conservado por trazabilidad),
`trades_v1_executable.json` (el corregido).

**Pendiente de decisión del usuario, no aplicado todavía:** ¿corregir
`trullas_shadow_portfolio.py` para que entre igual que `V1_EXECUTABLE`
(orden límite por apertura, no fill al mismo cierre)? Cambiaría el
comportamiento de una cartera ya en marcha — no se toca sin aprobación
explícita.

## Resultado B0/B1 — hipótesis NO respaldada

| Variante | n | tickers | media | mediana | win% | peor | mejor | Sharpe-like | % stop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 (anticipado, sin RVOL) | 2722 | 116 | +0.34% | **-0.55%** | 40.2% | -38.8% | +211.1% | 0.045 | 66.4% |
| B1 (anticipado, RVOL≥4.0) | 141 | 68 | **-0.15%** | -0.12% | 36.2% | -38.8% | +29.2% | **-0.016** | 66.0% |

**B1 (la variante que el asesor proponía llevar a producción) tiene media y
Sharpe-like negativos.** B0 (el control sin filtro de volumen) tampoco
muestra ventaja real — Sharpe-like prácticamente cero (0.045), con la
mediana ya en negativo. Filtrar a solo el primer evento por episodio (evita
contar varias veces una misma caída prolongada) no cambia la conclusión
(B0: mean +0.28%/mediana -0.10%; B1: mean -0.22%/mediana -0.13%).

**Aclaración metodológica (señalada por un tercer asesor externo, válida):
V1 y B0 NO son las mismas oportunidades comparadas con distinto lag.**
V1 exige un segundo pivote confirmado Y un retroceso posterior a la zona
23-25% (82 señales); B0 evalúa CADA sesión contra el último pivote ya
confirmado, sin exigir ningún retroceso a una zona concreta (2.722
candidatos — un conjunto de oportunidades bastante más amplio y laxo, no
un subconjunto de las 82 de V1 desplazado en el tiempo). La conclusión
("B0/B1 no compensan el riesgo") sigue sosteniéndose porque se evalúa en
términos absolutos (¿es rentable operar así?), no relativos a V1 — pero no
debe leerse como "B0 es V1 cinco sesiones antes con peor resultado", son
poblaciones de señales distintas.

## Por qué falla — mecanismo, no solo el número

**Solo el 23-26% de los candidatos B0/B1 llegan a confirmarse como pivote
fractal real con la divergencia todavía sostenida.** El 74-77% restante es
una falsa alarma: o aparece un mínimo todavía más bajo antes de que el
pivote pueda confirmarse, o la divergencia se diluye contra el pivote real
que termina formándose. Esto se refleja directamente en la tasa de cierre
por stop: **66%** en B0/B1 frente al **33.3%** de V1_EXECUTABLE — entrar
sobre un mínimo sin confirmar es, mecánicamente, entrar sobre una moneda al
aire sobre si ese mínimo aguanta.

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

## Coste real de la ejecución homogénea — ver "Corrección 2026-09-21" arriba

(Sección fusionada con la corrección de V1_OPEN al principio de este
documento — el hallazgo original de esta sección, media 2.47%→1.98%, se
quedaba corto: la cifra corregida de verdad ejecutable es 2.47%→1.27%,
n=82→54, Sharpe 0.293→0.151.)

## Conclusión y siguiente paso

**No se implementa el detector anticipado.** Ni B0 ni B1 (con ningún umbral
de RVOL probado) muestran ventaja neta sobre esperar la confirmación
fractal completa — al contrario, entrar antes de la confirmación es
mecánicamente entrar sobre una probabilidad de acierto mucho más baja
(**23-26% de confirmación real**, ver tabla de arriba — corregido
2026-09-21: esta frase decía antes "34%", un error propio que mezclaba esa
cifra con el complementario del % de cierre por stop (100-66=34), una
estadística distinta; detectado en una revisión externa posterior) sin que
el volumen extraordinario compense esa pérdida de precisión. Mismo patrón
que otras hipótesis descartadas en este proyecto tras contrastarlas con
datos (Capitulación Precursores, Relative
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
| `trades_v1_open_naive.json` | 82 operaciones V1, fill a apertura siguiente SIN comprobar elegibilidad (con bug, conservado por trazabilidad) |
| `trades_v1_executable.json` | 54 operaciones V1, orden límite real corregida |
| `trades_b0.json` / `trades_b1.json` | Operaciones de cada variante anticipada |
| `summary.json` | Todas las tablas de arriba en formato máquina |

Regenerar: `py -3 backtest.py` (usa el `ohlcv_cache.json` ya descargado de
`research/trullas_divergence_backtest_v1/`, no vuelve a descargar nada).
