# Microestructura v1 — Puerta G1: infraestructura (2026-11-15)

Autorización: «Market Tracker — Autorización G1». Esta fase construye y verifica la infraestructura. **No** hay
descargas históricas, variables de acumulación, contrastes, captura activa, commit ni cambios en producción.
G0: [G0_INFORME.md](G0_INFORME.md). G1.5 (laboratorio y agresor): [G15_INFORME.md](G15_INFORME.md). Cambios aprobados tras G1.5: [G2_CAMBIOS.md](G2_CAMBIOS.md). Propuesta para G2: [G2_PROPUESTA.md](G2_PROPUESTA.md). Preregistro para aprobación: [PREREGISTRO_G2.md](PREREGISTRO_G2.md).

**Resumen.** La infraestructura funciona y está verificada con datos reales:
- La conciliación trades↔barras cuadra al 100 % del volumen en los 6 casos difíciles probados.
- Los tickers reutilizados se separan.
- El 99,7 % de los días de pertenencia al S&P 500 2016-2026 tiene datos, y el 99,0 % en las empresas que salieron.

Tres supuestos de G0 eran incorrectos (§10). El más importante: el nivel A cuesta unas **14-20 h y ≤ 36 GB**, no
5 h y 21 GB.

---

## 1. Arquitectura implementada

Paquete `micro/`, aislado de producción (no lo importa nada del Market Tracker). Datos en `MICRO_DATA_DIR`
(`D:/backup market tracker/microstructure`). El código se niega a arrancar si esa ruta cae dentro del repo o de Dropbox.

| Módulo | Función |
|---|---|
| `config.py` | Rutas, credenciales desde `.env`, límites y `code_version` (hash del código, guardado en cada unidad). |
| `ratelimit.py` | Límite **compartido entre hilos y procesos** (ventana deslizante en SQLite con `BEGIN IMMEDIATE`) y pausa global tras un 429. |
| `providers/base.py` | Interfaz neutra `fetch_pages / calendar / corporate_actions`. Un adaptador de Databento implementaría lo mismo. |
| `providers/alpaca.py` | Paginación completa. Reintentos con espera exponencial ante 429/5xx/red. 4xx no reintentable. `asof` saneado. |
| `download.py` | Unidad = (proveedor, tipo, símbolo, asof, periodo, hash de configuración). Idempotente por checksum, reanudable, sin ficheros parciales, parada segura de disco. |
| `manifest.py` | SQLite: estado, filas, páginas, peticiones, bytes, segundos, reintentos, ruta, SHA-256, calidad, versión de código, intentos y registro de eventos. |
| `storage.py` | Capas `raw / normalized / features / datasets / results / reference / manifest / samples / _state / tmp`. Escritura atómica en el mismo disco. Guardián de espacio. |
| `calendar.py` | Calendario oficial de Alpaca (festivos y 21 cierres anticipados 2016-2026). Conversión NY↔UTC con cambio de hora. |
| `conditions.py` | Reglas oficiales de agregación de barras de 1 min por condición y cinta (FAQ de Alpaca). |
| `normalize.py` | Vistas tipadas de trades/barras/quotes: sesión (pre/regular/post), regla de cada trade, odd lot, TRF, horario extendido, cruces de quotes. |
| `quality.py` | Calificación A/B/C/F: duplicados, ventana, orden, condiciones desconocidas, huecos, conciliación con barras, calidad de quotes. |
| `identity.py` | Épocas por ticker (tramos de relleno con volumen 0 y saltos sin split), splits desde acciones corporativas. |
| `universe.py` | S&P 500 a fecha con CIK (reutiliza `research/sector_breadth_v1`) + valores EE. UU. del proyecto. |
| `sampling.py` | Planes congelados con hash antes de descargar (B1, quotes, muestra diaria en sombra) y potencia preliminar. |
| `retention.py` | Política configurable; por defecto conservarlo todo. |
| `shadow.py` | Captura prospectiva, **desactivada**. |

Reutilizado del proyecto:
- composición del S&P 500 y verificación de nombres (`sector_breadth_v1/build_panel.py`, importado, no copiado);
- metodología de preregistro y referencias de `early_flow7_validation_v1` / `macd_combo_filters_v1` (para G2).

Scripts: `g1_live_checks.py` (comprobaciones reales), `g1_universe_coverage.py` (universo y cobertura),
`g1_plans.py` (planes). G0: `alpaca_g0_probe.py`, `g0_budget.py`.

## 2. Pruebas

**Sin red** (`py -3 -m pytest research/microstructure_v1/tests -q`): **24 pruebas, todas pasan.**
- Paginación.
- Reintentos ante 429, 500 y caída de red. Reintentos agotados. 403 no reintentable.
- `asof` NaN que no se envía.
- Idempotencia: la segunda descarga no hace peticiones. Un fichero corrupto se detecta por checksum y se vuelve a descargar.
- Fallo a mitad de la paginación: no queda fichero ni temporal, y reintentar lo completa.
- Días sin mercado.
- Guardián de disco. Rechazo de rutas dentro de Dropbox.
- Limitador con 4 hilos y con 3 procesos: nunca más de N por ventana.
- Reglas de condiciones con los ejemplos del FAQ.
- Calendario con cambio de hora y cierre anticipado.
- Épocas por relleno. Saltos con y sin split.
- Conciliación consistente y rota.
- Duplicados.
- Muestreo reproducible y bloques sin solaparse ni cruzar la frontera desarrollo/prueba.
- Retención: con `keep_all` no se borra nada. Simulación frente a borrado real.
- La captura en sombra se niega a correr desactivada.

**Reales y acotadas** (~3 000 peticiones en total, ~30 MB de crudo):

| Caso | Trades | Conciliación (volumen / nº trades) | Barras esperadas que faltan | Nota |
|---|---:|---|---:|---|
| AAPL 2026-11-13 | 679 551 | 0 / 0,0004 % | 0 | A |
| HIMS 2026-11-13 | 85 513 | 0 / 0,002 % | 0 | A |
| VFF 2026-11-13 (poco líquido) | 5 904 | 0 / 0 | 0 | A (86 % de minutos con barra: minutos sin trades) |
| URI 2025-11-28 (**cierre 13:00**) | 12 045 | 0,0009 % / 0,018 % | 0 | A (210 minutos de sesión) |
| OSCR 2026-03-09 (**día de cambio de hora**) | 50 783 | 0 / 0,002 % | 0 | A (apertura 13:30 UTC) |
| ADT 2016-03-01 (**empresa absorbida**, asof) | 14 892 | 0 / 0 | 0 | A |

- **Reanudación e idempotencia en real:** volver a lanzar AAPL no hizo ninguna petición.
- **Paralelismo** (supuesto de G0 a comprobar): 3 descargas simultáneas dieron **130 páginas/min** sin ningún 429,
  frente a 95 en serie. No se llega a las 180/min (latencia del servidor).

## 3. Informe de integridad

**Conciliación trades↔barras.** Se aplican las reglas oficiales:
- volumen y nº de trades = trades con regla de volumen «Y»;
- una barra solo existe si algún trade mueve precio;
- un minuto con solo odd lots no genera barra;
- las condiciones M, Q y 9 no cuentan.

Con ellas, los 6 casos cuadran al 100 % del volumen. No se exige ninguna igualdad que las reglas no garanticen.

**Splits y acciones corporativas.** El endpoint `/v1/corporate-actions` funciona: NVDA ×4 (2021) y ×10 (2024),
AAPL ×4 (2020), GE inverso 1:8 (2021), fusiones y spin-offs.
- Los trades y quotes se guardan **sin ajustar**; los factores se aplicarán en la capa de variables (pendiente).
- El detector de saltos no marca un split registrado (NVDA 2024).
- Sí marca los spin-offs y los hundimientos reales (DowDuPont, Dr Pepper, PG&E, SVB, First Republic, Globe Life):
  quedan como «a revisar», no como errores.

**TRF y odd lots** (por volumen, en los 6 casos):
- Fuera de mercado (`D`): 35-51 %.
- Odd lots: 21 % de los trades en 2016 frente a 43-96 % en 2025-26. **La composición de los trades no es
  estacionaria**: cualquier variable de tamaño o recuento debe normalizarse frente a la historia del propio valor o
  del momento.

**Quotes.** VFF y URI: 0 % cruzadas, 0 % con un lado a cero, horquilla mediana de 41 y 14 pb. Unos 10 bytes por
quote, igual que los trades.

**Calendario.** Festivos correctos (Juneteenth, 3-jul-2026 observado). Cambio de hora correcto (13:30 frente a
14:30 UTC). 21 cierres anticipados en 2016-2026.

## 4. Identidad de los valores (lo más delicado)

Verificado con datos reales:
1. **Tickers reutilizados.** Sin `asof`, o con uno posterior, `ADT` devuelve ADT Corp (hasta el 29-abr-2016), 433
   barras de **relleno con volumen 0** que repiten el último cierre, y ADT Inc (desde el 19-ene-2018). El corte por
   épocas lo separa en 2 épocas, también sin `asof`.
2. **`asof` antiguo corta la serie en eventos corporativos** aunque la empresa siga cotizando: CB hasta el
   14-ene-2016, WMB hasta el 28-jun-2016, LMT hasta el 15-ago-2016 (canje con Leidos), JCI hasta el 2-sep-2016.
   Con un `asof` posterior la serie es continua.
3. **Regla implementada:** `asof` = última fecha en que se observó el ticker (sesión previa a la baja; ninguno si sigue
   vigente), y se usa solo la época que contiene esa fecha. La entidad es el CIK de Wikipedia.
4. Renombrados: FB y META forman una sola serie. Los renombrados que Wikipedia tarda en reflejar (MHFI→SPGI) se
   cubren por CIK.
5. **Residuo conocido:** en fusiones donde el superviviente hereda el ticker (JCI/Tyco), la serie es la del
   superviviente, que es la entidad del CIK. Puede no coincidir con quién estaba en el índice antes de la fusión.

## 5. Cobertura del universo (nivel A)

885 intervalos de pertenencia (774 del S&P 500 a fecha + 111 valores EE. UU. del proyecto), 824 entidades, barras
diarias con la regla de §4:

| Grupo | Intervalos | Cobertura ≥ 95 % | < 50 % | Sin datos |
|---|---:|---:|---:|---:|
| S&P 500 vigentes | 525 | 521 | 0 | 0 |
| S&P 500 que salieron | 249 | 213 (por entidad: 188 de 194) | 6 | 2 |
| Proyecto (desde su salida a bolsa) | 111 | 108 | — | 2 |

**Por entidad-día:** el 99,7 % de los 1,37 millones de días de pertenencia tiene datos con volumen; en las
empresas que salieron, el 99,0 %.
- Sin datos en Alpaca: C.R. Bard (BCR, absorbida en 2017), Newfield (NFX, 2019), la antigua Baker Hughes de 2017 y
  los OTC del proyecto PLNH y GTBIF.
- **Pendiente:** 22 empresas que salieron del índice en 2026 sin fecha conocida. La página actual de Wikipedia ya no
  publica la tabla de cambios. Quedan marcadas `end_uncertain` y siguen como miembros hasta el final: afecta a los
  últimos 10 meses de la prueba.

## 6. Almacenamiento, retención y disco

- **Disco D:** 145 GB libres. Parada segura si la escritura dejaría menos de **40 GB** (`MICRO_MIN_FREE_GB`). Todo,
  incluidos los temporales, va a `MICRO_DATA_DIR/tmp` en D:, nunca a C: (9,9 GB libres).
- **Formato:** Parquet zstd sin pérdida (timestamps en ns UTC, condiciones como lista). Los JSON del API **nunca se
  escriben a disco**.
- **Checksums:** SHA-256 de cada fichero en el manifiesto, junto con la versión del código y la configuración.
- **Retención** (`retention_config.json`): `keep_all` para barras, trades y quotes, como se decidió (100 % del piloto
  B1). La política `sample_fraction` existe para el futuro, simula por defecto y deja constancia de cada borrado.
- **Previsión si se aprueba todo:** nivel A ≤ 36 GB + B1 ~11 GB + quotes ≤ 1 GB ≈ 48 GB. Quedarían ~97 GB libres.
- **Licencia:** los datos y los resultados por valor y día se quedan en D:. En el repo solo hay código, configuración
  y agregados de este informe. Sigue **sin aclarar** si Alpaca permite publicar agregados derivados.

## 7. Plan de descarga del nivel A (barras de 1 minuto)

- **Universo:** S&P 500 a fecha + EE. UU. del proyecto. Ventana: pertenencia + 252 sesiones previas (consolidaciones
  largas) + 60 posteriores (horizontes de 20-40), dentro de la época de identidad y desde 2016-01-04.
- **Unidad:** (símbolo, asof, mes natural), con el horario extendido incluido y sin pérdida. Un único día por entidad
  aunque haya varios tickers.
- **Estimación** (cota alta: barras por día = las de AAPL, 848, la mitad en horario extendido):
  - 76 340 unidades, ~160 000 peticiones;
  - **~20 h con 3 hilos** (27 en serie), ≤ 36 GB;
  - en valores menos líquidos hay menos barras por día, así que lo realista son ~14-16 h.
  - Se puede repartir en varias noches: es reanudable.
- **Partición propuesta (fechas de decisión):** desarrollo 2017-01-03 → 2021-10-29 · embargo de 40 sesiones ·
  prueba 2022-01-03 → 2026-09-14. 2016 solo sirve de historia previa.

## 8. Plan del piloto B1 (ticks) — congelado, sin descargar

`samples/b1_plan_v1` (semilla 20261115, SHA-256 `72da1f76…`), creado antes de descargar nada:
- **200 bloques × 100 sesiones contiguas** (= 20 000 valor-días, el coste aprobado de «100 × 200»). Cada bloque tiene
  **40 sesiones de historia no elegibles + 60 elegibles**. Los resultados posteriores (hasta 40 sesiones) salen de las
  barras diarias. El bloque más el horizonte no cruza la frontera desarrollo/prueba.
- **Elección:** fecha aleatoria y valor aleatorio entre los miembros del S&P 500 **en esa fecha**, por tercil de
  liquidez medido con las 60 sesiones **previas**. Es independiente de cualquier señal del nivel A, y no se exige que
  el valor siga cotizando después.
- **Reparto:** 100 bloques en desarrollo y 100 en prueba, 34/33/33 por tercil. 168 entidades distintas (30 repetidas
  en bloques que no se solapan), **42 bloques de empresas que luego salieron del índice**. 61 valor-días sin datos se
  registran como tales.
- **Coste:** ~1 050 millones de trades, ~115 000 peticiones, **~15 h con 3 hilos**, ~11 GB.
- **Tamaño efectivo:** 12 000 valor-días elegibles nominales, pero en observaciones no solapadas son ≈ 2 400 a 5
  sesiones, 1 200 a 10, 600 a 20 y 400 a 40.
- **IC mínimo detectable** (80 % de potencia): 0,06 / 0,08 / 0,11 / 0,14 con una sola prueba; 0,07 / 0,10 / 0,14 /
  0,17 con Bonferroni ×6.

  **Es poca potencia para efectos realistas**: B1 sirve para comparar ticks frente a barras y para explorar. No
  puede confirmar efectos pequeños.
- **Desviación respecto al texto aprobado:** «100 valores × 200 sesiones» se ha interpretado como 200 bloques, no como
  100 valores fijos con 2 bloques cada uno. Así hay menos valores repetidos y menos dependencia del valor elegido, con
  el mismo coste. Si prefieres 100 valores fijos, se regenera con otra semilla.

## 9. Plan de quotes — congelado, sin descargar

`samples/quotes_plan_v1`:
- **Diseño:** 20 bloques de B1 (7/7/6 por tercil) × las 20 primeras sesiones elegibles contiguas. Reutiliza los trades
  de B1, así que solo se descargan quotes.
- **Coste:** 21-86 millones de quotes según el ratio quotes/trade medido (0,84-3,5), **0,3-1,1 h** y < 1 GB.
- **Objetivo:** comparar la regla del tick frente a Lee-Ready (bid/ask), medir la sincronización de timestamps, los
  casos no clasificables y el coste. **Sin uso predictivo.**

## 10. Supuestos de G0 incorrectos o no verificables

| Supuesto de G0 | Resultado en G1 |
|---|---|
| Nivel A en ~5 h y < 21 GB | **Incorrecto**: las barras incluyen el horario extendido (848/día en AAPL, no 390), más 252 sesiones de historia y las empresas que salieron. ~14-20 h y ≤ 36 GB. |
| «Alpaca resuelve los cambios de ticker» | **Solo en parte.** Resuelve renombrados, pero un `asof` antiguo corta la serie en eventos corporativos y un ticker reutilizado mezcla empresas con barras de relleno. Hizo falta la regla de §4. |
| Deslistados cubiertos al 98,6 % | La medición contaba barras de relleno con volumen 0. Repetida bien, el resultado es parecido: 99,0 % por entidad-día. |
| `n` de las barras difiere un 0-3 % de los trades | Era una comparación ingenua. Con las reglas oficiales cuadra (≤ 0,02 %). |
| Paralelismo de 3 llega a ~180 páginas/min | **No**: 130 (en serie 95, no los 42 de G0). |
| FAQ: «no se emite barra con volumen 0» | **No se cumple en las barras diarias**: Alpaca emite barras de relleno con volumen 0 para tickers inactivos. Se tratan como relleno. |
| Composición histórica completa del S&P 500 | 22 salidas de 2026 sin fecha (la tabla de cambios ya no se publica). |
| Licencia de agregados derivados | Sigue **sin verificar**. |

## 11. Limitaciones pendientes

1. Los factores de split no se aplican todavía a los trades (implementado solo el dato y la detección).
2. No hay fechas de resultados: Alpaca no las da y no hay fuente gratuita verificada. El análisis por eventos quedará
   como «desconocido».
3. 22 salidas de 2026 sin fecha. 5 entidades sin datos (3 del S&P 500, 2 OTC del proyecto).
4. Odd lots no estacionarios en el tiempo.
5. La regla de identidad no resuelve el caso «el superviviente hereda el ticker» (JCI).
6. Sin pruebas reales todavía del endpoint de barras de varios símbolos (no se usa) ni de la reanudación tras matar el
   proceso a mitad de unidad (cubierto por diseño y por la prueba simulada: la unidad se rehace entera).
7. La captura prospectiva solo se ha probado en modo simulado.

## 12. Captura prospectiva (desactivada)

`shadow.py` + `shadow_config.json` (`"enabled": false`). Cada noche, a mano (no hay tarea programada):
1. Espera 20 minutos tras el cierre.
2. Toma el universo elegible: miembros actuales del S&P 500 + EE. UU. del proyecto (599 valores).
3. **Registra antes de descargar** la selección: semilla derivada de (semilla maestra, fecha, hash del universo), 50
   valores y probabilidad de inclusión.
4. Descarga barras de 1 minuto de todo el universo y trades de los 50 seleccionados.

Coste estimado: ~975 peticiones y ~25 MB al día. Si se intenta lanzar con `enabled=false`, se niega.

## 13. Decisiones que requieren tu aprobación

1. **Descarga del nivel A** (~160 000 peticiones, 14-20 h en varias noches, ≤ 36 GB en D:).
2. **Descarga del piloto B1** con el plan congelado (~15 h, ~11 GB), o regenerarlo como 100 valores fijos.
3. **Descarga de quotes** (≤ 1,1 h).
4. **Partición desarrollo/prueba** propuesta (§7) y costes de transacción para G2.
5. **Fuente de fechas de resultados**, o aceptar que no haya análisis por eventos confirmatorio.
6. **Inicio de G2** (exploración en desarrollo y preregistro) con la propuesta de [G2_PROPUESTA.md](G2_PROPUESTA.md):
   4 hipótesis, prioridad a la familia C.
7. **Activación de la captura en sombra** (no recomendada hasta cerrar G2: no aporta nada sin hipótesis congeladas).
