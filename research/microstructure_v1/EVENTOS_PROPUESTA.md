# Eventos intradía — propuesta de arquitectura mínima (2026-11-17)

> **2026-11-18: E1 implementado** (piezas 4.1-4.3, 4.5-4.6 y escaneo manual de prueba). Ver
> [E1_INFORME.md](E1_INFORME.md). Lo que sigue es la propuesta tal como se aprobó.

**Estado:** propuesta, sin código de detector. Solo existe la ficha de PLTR
([EVENTOS_FICHA_PLTR_2026-11-17.md](EVENTOS_FICHA_PLTR_2026-11-17.md)) y su script (`ev_case_sheet.py`). No hay
capturas automáticas ni cambios en producción.

**Qué cambia frente a G2.** G2A probó hipótesis predictivas concretas y salió negativo. Sus resultados no se tocan y
su prueba confirmatoria sigue cerrada. Esta línea retrocede un paso: **observar, registrar, clasificar y contar**
fenómenos intradía antes de preguntar si predicen algo.

## 1. Principios

1. **Describir, no interpretar.** Un evento dice qué se ejecutó y cuánto se aparta de lo normal en ese valor. Nunca
   dice «compra institucional», «acumulación» ni «distribución». Esas palabras quedan fuera de los nombres, los campos
   y las etiquetas automáticas.
2. **Normalizar frente al propio valor.** Cada medida se compara con la historia intradía del valor: mismas franjas
   horarias, sesiones estrictamente anteriores. Los niveles absolutos no son comparables entre valores ni entre años.
   G1.5 vio que la composición del mercado cambia mucho: TRF del 28 % al 51 % entre 2017 y 2026.
3. **Separar los tramos de la sesión.** Premercado, subasta de apertura, negociación continua, subasta de cierre,
   *after hours* y comunicaciones tardías no se mezclan. En la ficha de PLTR, la barra de las 16:00 mezclaba la subasta
   con el *after hours*, y eso ya cambiaba la lectura del episodio.
4. **Medir ancho, marcar estrecho.**
   - Se guardan las medidas de **todos** los valores elegibles **todos** los días, con o sin evento. Sin ese
     denominador no se pueden contar frecuencias ni comparar después.
   - El evento es solo una marca sobre esa tabla.
   - Los umbrales se pueden revisar sin volver a descargar nada.
5. **Sin filtros de selección.** Ni Flow Score, ni Early Flow, ni momentum, ni PCS: solo elegibilidad mecánica
   (§5).
6. **Lo predictivo, después.** Ningún resultado posterior (retornos tras el evento) se calcula en esta fase. Cuando
   toque, irá en una tabla aparte y con preregistro (§7).

## 2. Qué se reutiliza de G1/G1.5 (casi todo)

| Pieza existente | Uso en eventos |
|---|---|
| `micro/providers/alpaca.py`, `ratelimit.py` | Descarga SIP gratuita, límite de 200 peticiones/min compartido |
| `micro/download.py` + `manifest.py` + `storage.py` | Unidades idempotentes con sha256, calidad y control de disco. Las barras diarias por sesión ya existen (`bars_window="day"`) |
| `micro/calendar.py` | Sesiones, cierres anticipados, límite de 15 min del plan gratuito |
| `micro/conditions.py` | Reglas oficiales de barras: subastas (O, Q, 5, 6), cierre oficial (M), precios no estándar (P, W…), *odd lots* |
| `micro/identity.py` | `asof` por fecha y épocas: un ticker no es una empresa permanente |
| `micro/episode.py` | Carga de trades y quotes de un día, ya probada con NVDA (~10 M de trades) |
| `micro/aggressor.py`, `footprint.py` | Desglose bajo demanda: agresor (con sus reservas), volumen por nivel de precio |
| `micro/library.py` | Episodios, anotaciones con procedencia, registro de accesos, `revealed_future` (modo ciego) |
| `micro/exposure.py`, `g2_test_exposure.py` | Registro de accesos al periodo de prueba de G2A |
| `micro/shadow.py` (desactivado) | Esqueleto de la captura diaria: universo elegible, espera de 20 min tras el cierre, barras del universo |
| `lab/` | Visor local en modo ciego |
| `ev_case_sheet.py` (nuevo hoy) | Separación de tramos, normalización frente a la propia historia y ficha de un episodio |

## 3. Catálogo inicial de anomalías (abierto, versión `cat-v0`)

Para cada medida se guardan tres cosas:
- el valor bruto;
- el percentil y el z robusto (mediana y MAD) frente a las sesiones previas del valor en la misma franja horaria;
- el número de sesiones de la línea base.

Franjas: minuto del día para el volumen (perfil en U), y bloques de 30 minutos para los retornos (más
observaciones). Línea base: 60 sesiones dentro de los últimos 180 días; si hay menos de 30, el evento se marca
`baseline_short`.

**Fuente:** **B** = barras de 1 minuto (barato, todo el universo); **T** = trades; **Q** = quotes. T y Q solo se usan
bajo demanda.

| Código | Familia | Anomalía (observable) | Medidas | Fuente |
|---|---|---|---|---|
| D1 | Desplazamiento | Retorno extraordinario en 1, 5, 15 o 30 minutos | Retorno, retorno en σ de 1 minuto del propio valor | B |
| D2 | Desplazamiento | Rango extraordinario de una vela | (máximo − mínimo) / mediana propia | B |
| D3 | Desplazamiento | Salto entre velas o hueco sin barras (posible suspensión) | Apertura frente al cierre anterior; minutos sin barra | B |
| D4 | Desplazamiento | Excursión extrema respecto al VWAP del día | (precio − VWAP) / σ | B |
| V1 | Volumen | Volumen de la ventana frente al perfil intradía propio | Volumen / mediana del mismo minuto | B |
| V2 | Volumen | Cambio del tamaño medio por operación | v / n frente a lo propio | B |
| V3 | Volumen | Subasta de apertura o cierre anómala | Cuota de la subasta, salto de precio frente a la última continua | T (B como aproximación) |
| I1 | Volumen/precio | Desplazamiento alto con volumen escaso | \|retorno\| / volumen relativo | B |
| I2 | Volumen/precio | Volumen alto sin desplazamiento | Volumen relativo / \|retorno\| | B |
| I3 | Volumen/precio | Cierre de la ventana lejos de su VWAP | (cierre − VWAP de la ventana) / σ | B |
| N1 | Niveles | Concentración de volumen en un nivel de precio | Cuota del nivel más negociado (±1 tick) | T |
| N2 | Niveles | Toques repetidos de un nivel sin romperlo | Nº de toques; tiempo en el nivel | B/T |
| N3 | Niveles | Operaciones grandes para el valor | Tamaño frente a su percentil propio, separando TRF y comunicaciones tardías | T |
| C1 | Cierre | Cambio brusco en los últimos 5, 10 o 30 min de la sesión regular | Como D1, en franjas de cierre | B |
| C2 | Cierre | Subasta de cierre anómala | Ver V3 | T |
| C3 | Cierre | Deriva extraordinaria en *after hours* (30/60 min) | Retorno y volumen frente a lo propio | B (T para limpiar) |
| C4 | Cierre | Comunicaciones tardías a precio de referencia (P/W) | Acciones, nº, tamaño máximo | T |
| C5 | Apertura | Hueco, subasta de apertura y primeros 5 minutos | Como V3/D1 | B/T |
| P1 | Persistente | Racha de velas en la misma dirección | Longitud de la racha frente a lo propio | B |
| P2 | Persistente | Recorrido muy direccional (eficiencia) en 30/60 min | \|retorno\| / suma de \|retornos de 1 minuto\| | B |
| P3 | Persistente | Volumen por encima del perfil durante ≥ k minutos seguidos | Duración | B |
| P4 | Persistente | Repetición en varios días (mismo valor, misma franja) | Nº de días de los últimos 5 | Registro |

**Campos de contexto, no anomalías:**
- calidad: suspensiones, cierre anticipado, eventos corporativos, días dominados por *odd lots*;
- mercado: retorno de SPY, QQQ y del ETF sectorial en la misma ventana;
- simultaneidad: cuántos valores disparan el mismo tipo de evento en el mismo minuto (separa lo del valor de lo de
  todo el mercado).

**Regla de marcado inicial:** percentil ≥ 99 o ≤ 1 frente a la línea base, o \|z robusto\| ≥ 4. Los minutos
contiguos se funden en un episodio con inicio y fin. **Es un punto de partida para contar, no un umbral calibrado:**
con ~20 medidas × varias ventanas habrá muchas marcas por azar. La primera tarea del retrospectivo (§6) es medir
la frecuencia por familia y ajustar el umbral para que cada familia marque una fracción manejable (orientación: 1-3 %
de los valores-día) antes de encender nada en vivo.

## 4. Piezas nuevas (mínimas)

1. **`micro/sessions.py`** — segmentación de la sesión.
   - Con trades: subastas por condición, M informativo, comunicaciones tardías (TRF con P/W después del cierre),
     *after hours*. Es la lógica de `ev_case_sheet.py`, extraída.
   - Con barras: la barra de las 16:00 se marca como mixta.
   - El cierre oficial se toma de la barra diaria, **pendiente de verificar** que en Alpaca coincide con la subasta
     (en NVDA y GOOGL coincidió).
2. **`micro/intraday_features.py`** — las medidas del §3 por (valor, día, franja), con su línea base propia y
   estrictamente anterior.
3. **`micro/event_catalog.py`** — definiciones versionadas (`cat-v0`), umbrales y fusión en episodios.
4. **`ev_scan_day.py DÍA`** — escaneo de un día:
   - descarga las barras del universo con el mismo esqueleto que `shadow.py`, por lo que la descarga no es nueva;
   - escribe la tabla de medidas completa y el registro de eventos;
   - se lanza a mano: no hay tarea programada.
5. **`ev_drilldown.py EVENT_ID`** — trades y quotes de la ventana del evento ± 30 min, desglose por tramos y
   niveles. Es `ev_case_sheet.py` generalizado.
6. **Laboratorio:**
   - leer parámetros de la URL, para que cada registro se abra con un enlace;
   - un panel «Eventos» con el registro del valor y día;
   - forzar el modo ciego hasta el final del evento al abrir desde el registro.

   Enlace:
   `http://127.0.0.1:8765/?symbol=PLTR&day=2026-11-17&start=15:30&end=16:40&tf=1&session=extended&event=<id>`
7. **`ev_search.py`** — búsqueda histórica de episodios parecidos (§6).
8. **Proveedor:** añadir la petición de barras de varios símbolos a la vez (`/v2/stocks/bars?symbols=…`). Baja el
   escaneo diario de ~650 peticiones a ~60.

Todo vive en `research/microstructure_v1/` (código) y en `MICRO_DATA_DIR/events/` (datos). **Nada en `docs/data`:** la
licencia de Alpaca no permite publicar los registros.

### Registro de un evento (`events/registry.parquet`)

| Grupo | Campos |
|---|---|
| Identidad | `event_id` = hash(símbolo, día, código, inicio, versión del detector); `symbol`; `entity` (CIK o época); `asof` |
| Tiempo | `day`, `t_start_utc`, `t_end_utc`, `t_start_ny`, `segment` (pre / apertura / continua / cierre / post / tardía) |
| Clasificación | `code` (D1…P4), `family`, `direction` (+/−/0, solo del precio) |
| Medidas | brutas; percentil, z robusto y n de la línea base; fechas de la línea base |
| Contexto | retorno del día hasta el evento, distancia al VWAP, SPY/QQQ/ETF sectorial en la misma ventana, simultaneidad, eventos corporativos o resultados conocidos **a esa fecha** |
| Calidad | `baseline_short`, `bar_mixed_segment`, huecos, cierre anticipado, cuota de *odd lots* |
| Procedencia | `unit_key` + sha256 de cada unidad, feed, `detector_version`, `catalog_version`, `code_version`, `created_utc` |
| Laboratorio | `lab_url` |

Los resultados posteriores (lo que pasó después) **no** van aquí: irían en una tabla aparte en la fase predictiva.

## 5. Universo elegible y operación diaria

- **Universo, a fecha:** miembros vigentes del S&P 500 y del Nasdaq 100, más los valores de EE. UU. del proyecto y
  los ETFs del Market Tracker (≈ 650). Es el mismo criterio de `shadow.py`, ampliado al Nasdaq 100.
- **Ampliación opcional:** todo valor de EE. UU. con precio ≥ 5 $ y volumen medio ≥ 20 M$/día en sus 60 sesiones
  previas. Es la única condición, y es mecánica.
- **Coste diario solo con barras:**
  - ~60 peticiones con la petición múltiple, o ~650 sin ella (unos 3-4 min a 200/min);
  - unos 8 MB/día comprimidos, ~2 GB/año en D:.
- **Hora:** después de las 20:20 ET, para tener todo el *after hours* pasado el retraso de 15 min. Son las 02:20 en
  Madrid; también se puede hacer por la mañana antes de las 04:00 ET.
- **Dónde corre:** en el PC, no en GitHub Actions, porque los datos no pueden ir al repositorio público.
- **Desglose con trades:** bajo demanda o como máximo para N eventos por día, con un tope que fijas tú.
- **Activación:** nada se activa sin tu autorización; la captura sigue desactivada (`shadow_config.json`).

## 6. Búsqueda histórica de episodios parecidos

**Objetivo:** dado un tipo de evento (por ejemplo, «C3 + I1: deriva extrema en *after hours* con volumen escaso»),
recuperar **todos** sus casos en el pasado para contarlos, mirarlos y etiquetarlos.

**Datos:** barras de 1 minuto. Hay que decidir qué periodo, porque el nivel A ya tiene 2016-2026 para los 825 valores
del universo de G2 (descarga al 92 %, parada desde el 16-nov):

| Periodo | Uso |
|---|---|
| 2016-01 a 2021-10-28 (incluye el desarrollo de G2A, 2017-2021) | Libre |
| Posterior a la prueba (desde 2026-09-15) | Libre |
| **Periodo de prueba de G2A (2021-10-29 a 2026-09-14)** | **Excluido.** Sin él se pierden 5 años, pero la prueba sigue limpia. Si un día se quiere usar, tendrá que ser una decisión explícita y anotada |

**Controles de sesgo:**
1. **Consulta registrada antes de ejecutarla:** definición, periodo, universo, versión del catálogo y hash. Se guardan
   todos los resultados, no solo los «buenos», junto con el número de casos candidatos y descartados.
2. **Sin conocimiento del futuro:**
   - líneas base estrictamente anteriores;
   - universo a la fecha (S&P histórico de `micro/universe.py`), no el actual: evita el sesgo de supervivencia;
   - identidad con `asof` por fecha;
   - precios `raw`, con splits validados contra el precio (enmienda 7);
   - resultados de empresas y noticias solo si se conocían ese día.
3. **Muestra para etiquetar, aleatoria y estratificada** (por año, liquidez y franja). Cada caso lleva **controles
   emparejados**: el mismo valor y la misma franja en días sin evento, para no etiquetar solo lo que llama la atención.
4. **Etiquetado ciego:**
   - en el laboratorio, con el cursor al final del evento;
   - `revealed_future` se deduce del registro de accesos (ya existe);
   - una etiqueta hecha después de ver lo que pasó vale para generar hipótesis, no como evidencia.
5. **Taxonomía descriptiva:** por ejemplo, «movimiento sostenido», «revertido en la sesión», «en escalón»,
   «comunicación tardía», «artefacto de datos», «indeterminado». La taxonomía v1 de la biblioteca (acumulación,
   distribución…) **no** se usa en esta fase, porque interpreta.

## 7. Fases propuestas

| Fase | Contenido | Necesita tu autorización |
|---|---|---|
| E0 | Esta propuesta + la ficha de PLTR | — (entregado) |
| E1 | Implementar §4.1-4.3 y 4.5-4.6, y probarlos con PLTR, NVDA y GOOGL | Sí |
| E2 | Retrospectivo de **conteo**: frecuencia, diversidad y simultaneidad por familia en los periodos libres; calibrar umbrales para que el registro sea manejable | Sí |
| E3 | Registro diario en sombra: `ev_scan_day.py`, lanzado a mano o programado | Sí, explícita, para activarlo |
| E4 | Búsqueda de parecidos y etiquetado ciego | Sí |
| E5 | Fase predictiva, con preregistro y tabla de resultados aparte | Más adelante |

## 8. Decisiones que te tocan

1. **La vela de PLTR** (ficha §0.6): ¿cuál viste? Decide si el *after hours* entra en el registro diario desde el
   principio. Yo propongo que sí, como tramo propio.
2. **Universo:** ≈ 650 valores (índices + proyecto) o el ampliado por liquidez.
3. **Periodo histórico:** confirmar que el periodo de prueba de G2A queda fuera.
4. **Desglose con trades:** cuántos eventos al día como máximo, o solo bajo demanda.
5. Si apruebas E1.
