# Eventos intradía — E1: informe de entrega (2026-11-18)

Autorizado el 2026-11-17 (ver [EVENTOS_PROPUESTA.md](EVENTOS_PROPUESTA.md) y la autorización del usuario: universo,
tramos, catálogo, integridad, umbrales, desglose, laboratorio, protección del periodo de prueba).
**Observacional:** registra y describe fenómenos intradía; no predice ni interpreta intención.
**No se ha activado** ninguna captura automática ni tarea programada, no se ha tocado producción y no hay estudios
predictivos. G2A y su prueba confirmatoria siguen intactos.

## 0. Resumen

1. **El recorrido completo funciona y está probado:** barras → medidas → alertas → episodios → registro → desglose
   con trades y quotes → ficha → laboratorio con enlace directo, en 7 días × 3 valores, incluidos controles ordinarios
   y un cierre anticipado.
2. **Las cuotas de volumen ya tienen denominadores explícitos.** En PLTR (17-nov) la subasta de cierre es el 15,2 % del
   volumen continuo y el 13,0 % de la sesión regular con subastas. El «18 %» de la ficha manual era la barra mixta de
   las 16:00; la ficha está corregida.
3. **Las referencias iniciales marcan demasiado.** El 14,5 % de las medidas por valor y día superan la referencia
   (por azar, con 40-60 sesiones de base, cabría esperar del orden de un 2 %). La causa principal es la regla
   «o z robusto ≥ 4» en medidas de rachas y cocientes con MAD pequeña: 75 de 248 alertas salen solo por el z y
   29 de ellas con percentil < 95. Calibrarlo es el primer objetivo de E2.
4. Cuatro fallos de datos o de diseño encontrados y corregidos al probar con datos reales (§6).
5. Coste diario estimado del registro de ~620 valores: unas 620 peticiones (o ~60 con la petición múltiple),
   15-25 min de proceso en un núcleo, ~20 MB/día de barras y ~4 MB/día de registro (§8).

## 1. Qué se ha construido

| Pieza | Fichero | Qué hace |
|---|---|---|
| 4.1 Tramos | `micro/sessions.py` | Premercado, subasta de apertura, continua, subasta de cierre, after hours, comunicación tardía (+ reapertura tras suspensión, otras no estándar, impresiones oficiales informativas, anuladas). Exacto con trades; con barras, marca las dos barras mixtas. Denominadores explícitos. Minutos sin barra: sin operaciones frente a dato ausente |
| 4.2 Medidas | `micro/intraday_features.py` | ~45 medidas por valor y día a partir de barras de 1 minuto, normalizadas frente a las sesiones previas del propio valor (perfil por minuto, sigma por bloques de 30 min) |
| 4.3 Catálogo | `micro/event_catalog.py` | `cat-v0`, versionado: códigos, familias, fuentes (barras/trades/quotes), estados, umbrales, episodios, selección diaria para el desglose, extensiones previstas |
| Registro | `micro/event_store.py` | Tablas por día en `MICRO_DATA_DIR/events/`: medidas (todas), contexto por valor y día, alertas, episodios, desgloses |
| Escaneo | `micro/event_scan.py`, `ev_scan.py` | Escaneo manual de un día: descarga solo lo que falta, línea base sin el periodo reservado, alertas con instante de inicio y de detección, contexto (SPY, QQQ, ETF sectorial, simultaneidad, eventos corporativos, repetición en 5 sesiones) |
| 4.5 Desglose | `micro/drilldown.py`, `ev_drilldown.py` | Trades (y quotes si aportan) de la ventana del episodio o de cualquier valor/fecha/ventana; tramos exactos; comprobación de cada alerta con trades; perfil, niveles, operaciones grandes, comunicaciones tardías; clasificadores de agresor con indeterminado; ficha en Markdown |
| 4.6 Laboratorio | `lab/server.py`, `lab/app.js`, `lab/index.html` | Enlaces directos, panel de acontecimientos, gráfico de precio y volumen con las anomalías, modo ciego por defecto en episodios históricos, perfil bajo demanda, datos y versiones |
| Universo | `micro/event_universe.py` | Actual ≈ 620 valores; histórico solo verificado; ampliación por liquidez preparada, sin conectar |
| Bloqueo | `micro/test_guard.py` | Periodo reservado de G2A (2021-10-29 a 2026-09-14) bloqueado por defecto en todo lo nuevo y en el laboratorio |

Uso:
```
py -3 ev_scan.py --day 2026-11-17 --symbols PLTR,NVDA,GOOGL [--pass regular|full] [--dry-run]
py -3 ev_drilldown.py --day 2026-11-17 --list
py -3 ev_drilldown.py --day 2026-11-17 --episode <id> [--focus auto|open|close|peak] [--quotes auto|yes|no]
py -3 ev_drilldown.py --day 2026-11-17 --symbol PLTR --window 15:30-17:00          # cualquier valor y ventana
py -3 lab/server.py   ->  http://127.0.0.1:8765/?day=2026-11-10&episode=0c4dfdb850128661
```

## 2. Catálogo `cat-v0` implementado

| Código | Familia | Medidas (barras) | Estado en E1 |
|---|---|---|---|
| D1 | Desplazamiento | retorno en 1/5/15/30 min en sigmas propias (alcista y bajista) | implementada |
| D2 | Desplazamiento | rango de una vela / rango típico de su franja | implementada |
| D3 | Desplazamiento | salto entre velas; minutos seguidos sin barra | implementada (el hueco solo alerta en valores líquidos) |
| D4 | Desplazamiento | distancia al VWAP acumulado de la continua | implementada |
| V1 | Volumen | volumen de 1/5/15 min / perfil propio por minuto | implementada |
| V2 | Volumen | tamaño medio por operación (15 min) / propio, al alza y a la baja | implementada |
| V3 / C2 | Volumen / cierre | subasta de apertura y de cierre | con barras solo **estimada** (barras mixtas); exacta con trades, sin historia comparable |
| I1 | Volumen/precio | desplazamiento de 15 min con volumen ≤ el esperado | implementada como condición conjunta (sin cocientes) |
| I2 | Volumen/precio | volumen de 15 min con desplazamiento ≤ 0,5 σ | implementada como condición conjunta |
| I3 | Volumen/precio | cierre de la ventana frente a su VWAP | implementada |
| N1, N3 | Niveles | concentración por nivel, operaciones grandes | solo en el desglose con trades, **descriptivas** (sin historia de trades) |
| N2 | Niveles | toques repetidos de un nivel | definida, sin implementar |
| C1 | Cierre | últimos 5/10/30 min de la continua | implementada (magnitud con signo aparte) |
| C3 | Cierre | after hours a +30/+60 min, recorrido 0-35 min, volumen | implementada; volumen estimado (incluye comunicaciones tardías) |
| C4 | Cierre | comunicaciones tardías a precio de referencia | en el desglose con trades, descriptiva |
| C5 | Apertura | hueco de apertura, primeros 5 min | implementada |
| PM1, PM2 | Premercado | movimiento y volumen del premercado | implementada (añadida a cat-v0: el premercado se pidió como tramo) |
| P1, P2, P3 | Persistente | racha de velas, eficiencia direccional 30/60 min, minutos seguidos con volumen ≥ 2× | implementadas |
| P4 | Persistente | repetición del mismo código en las 5 sesiones previas | campo `recurrence_5d` en cada alerta (necesita historia del registro) |
| X1-X6 | Previstas | barridas, divergencia sectorial, compresión/expansión de volatilidad, migración del POC, asimetría, persistencia de concentraciones 5-60 sesiones | declaradas en `PLANNED`, sin implementar |

**Estados:** `candidate_bars` (barras), `characterized_trades` (desglosada con trades), `enriched_quotes` (además con
quotes), `indeterminate` (línea base < 30 sesiones o datos insuficientes), `artifact` (división u otro evento
corporativo ese día, barra mixta, movimiento que con trades es < 50 % del de las barras).

**Umbrales:** percentil ≥ 99 o z robusto ≥ 4 frente a la línea base, **solo como referencia inicial**. Se compara el
extremo del día con los extremos de las sesiones previas, no cada minuto con un umbral fijo: así se tiene en cuenta
que se examinan cientos de ventanas. Con 60 sesiones, el percentil 99 equivale a superar el máximo de la base
(resolución 1,7 puntos); el registro guarda `resolution_pct` y `exceeds_baseline_max`.

**Episodios:** las alertas del mismo valor y día que se solapan o distan ≤ 10 min forman un episodio. Las alertas
individuales se conservan con su `episode_id`.

**Tiempos de cada alerta:** `t_start_utc` (inicio de la ventana), `t_detectable_utc` (fin de la primera vela que
supera la referencia, usando solo datos hasta entonces; la referencia sale de sesiones anteriores), `t_end_utc`,
`t_peak_utc` y `t_available_free_plan_utc` (+15 min, retraso del plan gratuito). Hay una prueba que borra los datos
posteriores al cruce y comprueba que el instante detectado no cambia.

## 3. Registro

`MICRO_DATA_DIR/events/` (privado; la licencia de Alpaca no permite publicarlo):

| Tabla | Una fila por | Campos principales |
|---|---|---|
| `measures/` | valor × día × pasada × medida, **haya o no anomalía** | valor, percentil, z, n, mediana, umbral, marca, regla, `estimated`, `exceeds_baseline_max`, `resolution_pct`, `baseline_short` |
| `symbol_days/` | valor × día × pasada | línea base (n, fechas, regla), calidad (cobertura de barras, huecos, cierre anticipado), operaciones/min, eventos corporativos, sector y ETF, unidades de datos, versiones (catálogo, detector, código), tiempo de cálculo, orígenes en el universo |
| `alerts/` | anomalía individual | código, familia, medida, dirección, tramo, tiempos (inicio, detectable, pico, fin, disponible), valor y pico, umbral, percentil, z, n, regla, estado y nota, contexto (SPY, QQQ, ETF sectorial en la misma ventana), simultaneidad, repetición, `episode_id`, `lab_url` |
| `episodes/` | episodio | valor, día, inicio, fin, detectable, códigos, familias, nº de alertas, tramos, prioridad, estado, `lab_url` |
| `drilldowns/` | desglose | JSON con tramos exactos, comprobaciones, perfil, operaciones grandes, agresor, unidades (clave + sha256) |

Reescribir un día para los mismos valores y pasada es idempotente: también desaparecen las alertas de un valor que
deja de tenerlas (fallo encontrado y corregido, con prueba).

**Dos pasadas por día, preparadas pero no programadas:** `regular` (tras el cierre + 20 min; las medidas de after hours
quedan pendientes) y `full` (tras el fin del after hours + 20 min). El escaneo se niega a correr antes de tiempo.

## 4. Laboratorio

- **Enlace directo:** `?day=…&episode=…` o `?symbol=…&day=…&start=…&end=…&tf=…&session=…&blind=…&cursor=…`. La URL se
  actualiza al navegar.
- **Panel de acontecimientos:** episodios del día (de todos los valores o del elegido), ordenados por prioridad, con
  estado; tabla de alertas del episodio con tiempos, valor, percentil, z, n y estado.
- **Gráfico de precio y volumen** de 1 minuto con todos los tramos: premercado y after hours sombreados, barras mixtas
  en morado, cada anomalía con su ventana (línea) y su instante detectable (triángulo), y el cursor del modo ciego.
- **Modo ciego por defecto** al abrir un episodio histórico, con el cursor en su instante detectable. El servidor no
  envía barras, alertas ni operaciones posteriores al cursor (probado).
- **Perfil de volumen bajo demanda** (POC, área de valor), **footprint** (ya existía, ahora carga solo la ventana:
  antes un día de NVDA no cabía en memoria) y **comparación de clasificadores** con el volumen indeterminado.
- **Datos y versiones:** línea base, pasada, unidades, versiones del catálogo, del detector y del código, y resumen
  del desglose.
- **Periodo reservado bloqueado** en todas las rutas de datos (incluido el footprint existente); con `allow_test=1` se
  permite y queda anotado.
- Pendiente para más adelante (aprobado como futuro): comparar episodios entre sí y la evolución del perfil entre
  sesiones.

## 5. Casos de prueba

Escaneados PLTR, NVDA y GOOGL (más SPY, QQQ, XLK y XLC como contexto) en:

| Día | Papel | Resultado |
|---|---|---|
| 2026-11-17 | caso PLTR | pasada `regular` hecha; pasada `full` → §5.1 |
| 2026-11-12 | caso NVDA (hueco −13 %) | 36 alertas en 1 episodio de día entero: premercado, hueco, apertura, volumen, cierre y after hours |
| 2026-10-29 | caso GOOGL (hueco −11,6 %) | 25 alertas; subasta de apertura exacta 2 837 030 acciones a 287,22 (coincide con G1.5) |
| 2026-11-10 | control ordinario (regla fija: 5 sesiones antes de cada caso) | PLTR 1 alerta (I1), GOOGL 5, NVDA 25 |
| 2026-11-05 | control ordinario | 12 episodios; varios simultáneos en los tres valores entre 15:46 y 16:38 (movimiento de mercado) |
| 2026-10-22 | control ordinario | línea base de 27 sesiones → todas las alertas `indeterminate` (comprobado) |
| 2020-11-27 | cierre anticipado (13:00) | NVDA y GOOGL sin alertas; PLTR 26 (su primer mes cotizando). Subasta de cierre a las 13:00 separada correctamente |

Fichas generadas (`fichas/`, solo agregados):
- `PLTR_2026-11-10_…` — control: I1 15:41-15:56; subasta de cierre real 2 189 538 frente a 3 137 077 en la barra mixta;
  1 566 841 acciones de comunicaciones tardías en la ventana.
- `NVDA_2026-11-12_…` — foco en cierre y after hours: subasta 19 425 706 acciones; C3 +1,2 % a +30 min.
- `GOOGL_2026-10-29_…` — foco en la apertura: los métodos de agresor no coinciden en el signo en 5 de las 12 alertas.
- `NVDA_2020-11-27_…` — cierre anticipado; reveló la subasta duplicada (§6).
- `SPY_2026-11-05_…` — ventana de control al azar (selección diaria con semilla fija).

### 5.1 PLTR 2026-11-17 (pasada completa)

**Pendiente.** La pasada `full` del 17-nov solo puede correr tras el fin del after hours + retraso (01:20 UTC del
18-nov). Quedó lanzada en segundo plano (escaneo + desglose del episodio de after hours de PLTR con `--focus close`).
Se revisará su resultado y la ficha generada en `fichas/` en la siguiente sesión.

## 6. Integridad y normalización (punto 5 de la autorización)

| Pedido | Qué se ha hecho |
|---|---|
| Subasta real frente a barra mixta | Separadas: tramos exactos con trades; la barra mixta se marca `close_mixed`/`open_mixed`, queda fuera de las medidas continuas y sus estimaciones llevan `estimated=True` |
| Denominadores de las cuotas | Explícitos: continua, regular con subastas, total; corregida la ficha de PLTR (15,2 % / 13,0 %, no 18 %) |
| Cierre oficial frente a última continua | `official_close` (M, o la mayor condición 6), `last_continuous` y diferencia en pb |
| Sesiones reducidas y cambio de hora | Calendario de Alpaca y minutos en hora de Nueva York desde las 04:00; probado con 2026-11-27 (13:00) y el cambio de marzo; cierre anticipado real 2020-11-27 sin alertas espurias |
| Minutos sin negociación frente a datos ausentes | Con barras se declara ambiguo; con trades se separan «sin operaciones», «dato ausente» y «con operaciones pero sin barra» |
| Identidad histórica | Universo histórico solo con pertenencias verificadas (S&P 500 de G1); NDX y listas del proyecto, fuera hasta tener una fuente verificada |
| Divisiones de acciones | Eventos corporativos de Alpaca: el día de la división, el hueco se registra como `artifact`; las sesiones de la base afectadas no aportan valores de hueco |
| Condiciones, comunicaciones tardías y duplicados | Clasificación por condiciones (L, Z, U, P, W, B, 4 = tardía o a precio de referencia); impresiones M/Q/9 sin volumen; **operaciones repetidas con el mismo identificador eliminadas** (nuevo, ver abajo) |
| Medidas solo estimables con barras | Marcadas `estimated` y con nota; no se presentan como exactas |
| Referencia insuficiente | `baseline_short` si n < 30 → alertas `indeterminate`; resolución del percentil guardada |
| I1/I2 cerca de cero | Condiciones conjuntas, no cocientes; suelos en los denominadores de volumen; eficiencia direccional con recorrido mínimo; prueba con volumen cero y precio plano |

**Fallos encontrados al probar con datos reales (todos corregidos y con prueba):**
1. **Subasta duplicada.** En NVDA 2020-11-27 la subasta de cierre (155 375 acciones) aparecía dos veces, con el mismo
   identificador de operación y 7,9 ms de diferencia: su volumen se duplicaba. Es raro (2 en NVDA ese día, 20 de 28
   acciones en GOOGL 2026-10-29, ninguno en los otros días comprobados), pero puede tocar justo a la subasta. Nueva
   opción `dedupe_ids` en `episode.load_trades`, activada en la línea de eventos; desactivada por defecto para no
   cambiar la reproducibilidad de G1.5/G2A.
2. **Medidas fijas partidas con ceros.** Partir C1/C3/C5/PM1 en lado alcista y bajista con 0 en el contrario llenaba la
   línea base de ceros e inflaba el z (GOOGL salía marcado con percentil 59). Ahora se normaliza la magnitud y el
   signo va aparte.
3. **Unidades de sesión sin cerrar.** `download._window` aceptaba una unidad diaria de una sesión aún abierta y la
   habría guardado como completa. Ahora exige un tope explícito. Esto revela que **`micro/shadow.py` (desactivado)
   tenía ese fallo latente**: pedía la sesión completa 20 min después del cierre regular.
4. **Idempotencia del registro.** Un valor que dejaba de tener alertas conservaba las viejas. Corregido.

## 7. Calidad y limitaciones

**Lo medido en la prueba (21 valores-día, 248 alertas, 34 episodios):**
- Tasa de marcas: 14,5 % de las medidas. Las que más marcan: P3 (43 % de los valores-día), I2 (38 %), V1 (33 %),
  V2 (29 %), C3 (28 %). Muy por encima del ~2 % esperable por azar.
- 75 alertas salen solo por la regla del z (29 con percentil < 95). En rachas (P3) y cocientes, la MAD de la base es
  pequeña y el z se dispara (P3 de NVDA: z = 130). **La regla «o z ≥ 4» no sirve tal cual para estas medidas**.
- **Cambio de régimen:** tras el hueco del 12-nov, NVDA tiene volúmenes muy por encima de su base de septiembre-octubre
  y dispara alertas de volumen cada día. Una línea base que incluye días con eventos, o que va por detrás de un cambio
  de régimen, produce alertas repetidas del mismo fenómeno.
- **Episodios de día entero:** en días de hueco, la fusión por cercanía junta todo el día (máximo 781 min). Útil como
  resumen, pero para desglosar hay que elegir un foco (`--focus`).
- La simultaneidad funciona: el 17-nov a las 12:06 ET los tres valores marcan D1 a la vez; el 5-nov hay un racimo
  entre las 15:46 y las 16:38.

**Limitaciones de diseño (conocidas, documentadas en el código):**
- **Línea base corta hasta ~diciembre de 2026:** al excluir el periodo reservado, ningún valor tiene más de ~45
  sesiones posteriores a la prueba. En el retrospectivo libre (2016 a 2021-10) no hay ese problema.
- **Perfil compartido:** las sesiones de la base se normalizan con el perfil del día evaluado (todo anterior a él). No
  mira al futuro, pero no es estrictamente lo que se habría visto cada día. El modo incremental propuesto para E2 lo
  resuelve.
- **Sin historia de trades ni de quotes:** N1, N3, C4, la cuota exacta de la subasta y el delta del agresor son
  descriptivos, no normalizados.
- **TRF:** llevan la hora de comunicación, no la de ejecución (ya visto en G1.5).
- **Contexto sectorial** solo para miembros del S&P (mapa GICS de G1); ETFs y valores fuera del índice, sin sector.
- **P4** necesita historia en el registro; hoy casi siempre vale `None` o 0.
- El universo actual son 620 valores, no ~650: los solapamientos entre índices y listas son mayores de lo previsto.

## 8. Rendimiento real y coste diario revisado

Medido en esta prueba:

| Paso | Medida |
|---|---|
| Barras, unidad diaria (04:00-20:00) | 1 petición, ~0,24 s de API, ~1,2 s por unidad en total (manifiesto, sha256, disco); ~29 KB (líquidos ~35 KB) |
| Cálculo por valor y día (61 sesiones) | 0,6-1,5 s, mediana ~0,9 s |
| Desglose de un episodio | PLTR (1 h + after hours): 5 + 4 peticiones, 2 s; NVDA cierre + after hours: 43 peticiones de quotes, 53 s; SPY 30 min: 19 peticiones, 21 s |
| Registro | ~5 KB por valor y día |

Estimación para el registro diario de ~620 valores (sin activar):

| | Estimación |
|---|---|
| Peticiones | ~620 (una unidad diaria por valor) o ~60-70 añadiendo la petición múltiple de barras al proveedor |
| Tiempo de descarga | ~13 min secuencial; ~4-5 min con 3 hilos (límite 180/min) |
| Tiempo de cálculo | ~9-10 min en un núcleo; ~3 min con 4 procesos |
| Disco | ~18-22 MB/día de barras (~5 GB/año) + ~3-4 MB/día de registro (~1 GB/año) |
| Desglose diario (5 episodios + 2 controles) | 50-300 peticiones y 1-5 min según los valores; tope configurable (`DEFAULT_BUDGET`: 400 peticiones, 900 s, 300 MB) |
| Arranque | ~130 valores del universo no están en el nivel A (NDX fuera del S&P, proyecto, ETFs): ~25 unidades cada uno para tener línea base (~3 300 peticiones, una vez) |

(La estimación de la propuesta, 2 GB/año, era baja: no contaba el premercado y el after hours.)

## 9. Pruebas automáticas

- `py -3 -m pytest research/microstructure_v1/tests`: **80 pasan** (63 anteriores + 17 nuevas en `tests/test_events.py`).
- `node tests/test_lab_layout.js`: 7 pasan (sin cambios).
- `tests/test_lab_events_visual.js` (Edge sin ventana, local): **10 comprobaciones pasan**: enlace al episodio, modo
  ciego por defecto con cursor, vela de 1 min y URL sincronizada, panel de acontecimientos y alertas, gráfico dibujado,
  ninguna barra posterior al cursor, datos y versiones, perfil calculado, fecha reservada bloqueada, sin errores de
  página.

## 10. Descargas históricas pendientes (sin reiniciar)

| Etapa | Estado |
|---|---|
| Nivel A (barras 1 min, 825 valores, 2016-01 a 2026-11) | 70 562 de 76 340 unidades (92,4 %); parada el 16-nov en febrero de 2026 (orden mes→valor). 3 fallidas por cortes de conexión (PSX, PTC, PYPL 2023-04) y 3 «en curso» que quedaron a medias (CCL, CDNS, CDW 2026-02); se rehacen solas al reanudar. Faltan ~5 800 unidades (~2 h al ritmo medido) |
| B1 (trades) y B1q / quotes | completos |
| Descargas de E1 | 167 unidades de barras (178 peticiones, 13 MB), 6 de trades (54 peticiones), 3 de quotes (50). Los meses completos usan la misma clave que el nivel A: no se repetirán al reanudarlo |

Reanudar el nivel A solo hace falta para E2 en el periodo 2026-02 a 2026-11, que en su mayor parte es periodo
reservado. **Para el retrospectivo de E2 en el periodo libre (2016 a 2021-10) el nivel A ya está completo.** No lo he
reanudado.

## 11. Propuesta para E2

**Objetivo:** conocer la distribución, frecuencia y diversidad de los fenómenos del catálogo, y fijar umbrales que den un
registro manejable. **Sin resultados posteriores ni predicción.**

1. **Datos y periodo:** nivel A (barras de 1 min) de los miembros del S&P 500 **a cada fecha** (pertenencia verificada
   de G1), 2016-01 a 2021-10-28 (~1 450 sesiones × ~500 valores). Nada del periodo reservado. Sin nuevas descargas.
2. **Modo incremental, estrictamente a fecha:** cada sesión se calcula una sola vez, con el perfil de sus 60 sesiones
   previas, y la línea base de cada día se forma con los valores ya guardados de los días anteriores. Coste estimado:
   ~1,5 min por valor → ~12 h en un núcleo, ~3 h con 4 procesos.
3. **Partición para calibrar sin sobreajustar:** fijar los umbrales en 2016-2019 y comprobar en 2020 a 2021-10 que la
   frecuencia por familia se mantiene. Es estabilidad de un recuento, no un contraste de rentabilidad.
4. **Qué medir:**
   - frecuencia por medida, familia, tramo, año y liquidez;
   - correlación entre medidas (para fusionar las redundantes);
   - simultaneidad entre valores, para separar los fenómenos de mercado de los de un valor;
   - persistencia: cuántas veces se repite el mismo código en días seguidos;
   - longitud de los episodios.
5. **Decisiones de diseño que E2 debe resolver con esos datos** (y que propondré, no aplicaré sin tu visto bueno):
   - sustituir «percentil o z» por una regla por tipo de medida (escala logarítmica en cocientes y rachas; quizá
     exigir percentil **y** z);
   - excluir de la línea base los días con eventos propios, o usar una base más corta tras un cambio de régimen;
   - agrupar episodios por tramo para que un día de hueco no sea un único episodio;
   - una frecuencia objetivo por familia (orientación: 1-3 % de los valores-día).
6. **Muestra para mirar, no para concluir:** una muestra aleatoria estratificada de episodios y de ventanas de control,
   abierta en el laboratorio en modo ciego, con la taxonomía descriptiva (no la de G1.5). Ningún resultado posterior se
   calcula en E2.
7. **Entregables:** tablas de frecuencia, propuesta de umbrales `cat-v1` con su justificación, informe y, si lo
   apruebas, la activación del registro diario en sombra (fase E3).

## 12. Decisiones que te tocan

1. Aprobar E2 tal como está en §11 (o cambiar periodo, universo o coste).
2. Si se añade ya la petición múltiple de barras al proveedor (reduce el coste diario 10 veces).
3. Qué hacer con `micro/shadow.py`: corregir su fallo latente (unidad sin tope) o retirarlo, ya que el registro de
   eventos lo sustituye.
4. Si reanudar el nivel A (solo hace falta para el periodo posterior a la prueba).
