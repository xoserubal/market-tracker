# Infraestructura de estudio de la negociación — propuesta acotada (E3 y siguientes)

Fecha: 2026-11-21. Encargo: revisión del usuario de `CV1_INFORME.md`.
- cat-v1 queda aceptado y la calibración del catálogo, cerrada.
- El objetivo es registrar e investigar cómo se negocian las acciones, de minutos a semanas, y cruzarlo con otros datos.
  Las alertas son solo una herramienta auxiliar.
- Sin nuevas familias de alertas, sin optimizar umbrales, sin estudios predictivos.
- Sin automatizaciones permanentes, sin producción, sin commits.

En este documento:
- **Hecho y probado** (autorizado en tu §2 y §3): §1 y §2.
- **Propuesto, sin implementar:** §3 y §4.

## 1. Registro diario completo — E3 (prueba manual ejecutada)

**Qué guarda por valor y sesión** (`e3_daily.py run --day D`):

| Capa | Qué | Dónde |
|---|---|---|
| 1 | Barras originales de 1 minuto de la sesión completa (04:00-20:00 NY: premercado, continua y after hours), una unidad diaria por valor con checksum | `raw/` + manifiesto, misma clave que las descargas individuales |
| 2 | Las 44 medidas del valor-día, haya alertas o no, con su estado cat-v1 | `events/cat-v1/measures/<día>` |
| 3 | Alertas y episodios cat-v1, aparte | `events/cat-v1/alerts`, `episodes` |
| Procedencia | Cobertura, línea base, eventos corporativos, sector y si es válido a fecha, unidades de datos, versiones de código y catálogo | `events/cat-v1/symbol_days`, `results/e3/run_*.json`, `results/e3/journal.jsonl` |

**Cómo funciona:**
- **Universo:** el actual (`event_universe`: S&P 500 + Nasdaq 100 + valores y ETFs del proyecto, 620 valores), más SPY,
  QQQ y los ETFs sectoriales.
- **Descarga con la petición múltiple de Alpaca**, día a día (línea base + el día), en lotes de 100 valores.
  - Un lote que falla se reintenta; si sigue fallando, se parte en dos hasta llegar a peticiones individuales.
  - Un valor sin barras ese día queda `empty`, con su registro.
  - Los ficheros se escriben de forma atómica y en paralelo, y el lote se registra en el manifiesto en una sola
    transacción. Si el proceso se corta entre medias, la siguiente pasada rehace esas unidades.
- **Completitud:** cada valor-día del día con unidad `ok` o `empty`, y sus barras frente a su propia mediana de 20
  sesiones. Se señala si más del 20 % de los valores tiene menos de la mitad de lo habitual (posible caída del dato).
- **Escaneo cat-v1 por tandas de 50 valores.** Cada tanda se escribe al terminar, y una tanda ya escrita con la misma
  versión de código se salta.
- **Cierre del día:** simultaneidad de mercado y de sector, días de mercado, sospecha de caída de datos y episodios,
  recalculados sobre el universo entero.
- **Seguridad:** un candado impide dos pasadas a la vez, y se libera solo si el proceso que lo tenía ha muerto. Las
  fechas del periodo reservado de G2A están bloqueadas.

**Pruebas hechas:** resultados en §5.
- Interrupción simulada durante la descarga, y luego una interrupción real (proceso matado);
- reanudación, sin repetir lo hecho;
- reintento, división de lotes y caída a petición individual (con un proveedor simulado);
- idempotencia: una segunda pasada completa no descarga nada y deja el registro igual.

**Propuesta para la operación diaria** (no activada): una sola pasada `full` a partir de las 20:20 NY, lanzada a mano
o, cuando lo autorices, con la misma vía que ya usa el pipeline (el bot dispara el workflow).
- La pasada `regular` (16:20 NY) solo aporta tener las medidas de la sesión regular 4 horas antes. Propongo no
  añadirla hasta que haya un uso que lo pida.
- **Necesita este equipo encendido:** los datos y el manifiesto viven en D:, fuera del repo y de la nube.

## 2. Control de integridad: series de precio mezcladas (implementado; recorrido histórico en §5)

- **Regla** (`micro/dq_checks.py`, `dq-mixed-1`, fijada antes de recorrer el histórico):
  - en un valor-día, los cierres de 1 minuto forman dos niveles separados por ≥ 8 %;
  - el minoritario tiene ≥ 5 % de las barras y ≥ 10 barras;
  - los niveles alternan en el tiempo, con ≥ 6 cambios entre barras consecutivas.
  - Un movimiento real que se mantiene da 1-2 cambios; JWN 2018-03-26 da 181.
- **No modifica las barras.** Registra cada caso con su evidencia (niveles, salto, cambios, reparto) y su impacto:
  alertas cat-v1 de ese valor-día y medidas de la capa 2 por encima de su propia historia.
  - Los casi marcados (salto ≥ 8 % y ≥ 3 cambios) se guardan aparte, para ver qué deja fuera la regla.
- Las alertas de un valor-día marcado pasan a «sospecha de datos», con la etiqueta `suspected_mixed_price_series`.
- En el registro diario se aplica a cada valor-día de la pasada.
- **Sectores:** un sector tomado de una instantánea posterior a la fecha ya no se usa como sector a fecha. Se guarda
  aparte como `sector_retrospective`, con `sector_point_in_time = false`, y no entra en la simultaneidad por sector.
  Afecta a 18 575 de 714 076 valor-días del histórico (2,6 %).

## 3. Volume Profile entre sesiones — primera versión (propuesta)

**Pregunta que permite estudiar:** cómo se reparte el volumen negociado por nivel de precio, sesión a sesión, y cómo
evoluciona ese reparto en ventanas de 5 a 60 sesiones, junto al precio y al volumen. Es descriptivo:
- una concentración de volumen es una concentración de volumen;
- no se etiqueta como acumulación ni como intención de nadie.

**Datos y dos calidades separadas**, siempre a la vista, nunca mezcladas:
- `source = bars_estimated`: perfil desde las barras de 1 minuto. El volumen de cada barra se reparte uniformemente
  entre su mínimo y su máximo. Es una estimación: no se sabe a qué precio dentro de la barra se negoció cada acción.
  Cubre todo: el histórico 2016-2021 del S&P 500 y el registro diario.
- `source = trades_observed`: perfil exacto desde los trades, solo donde se hayan descargado (bajo demanda, §4).
- Para comparar ambas, en los valor-días que tengan las dos se guarda la diferencia: posición del POC y solape del
  área de valor.

**Tabla nueva en la capa 2** (`features/vp_session/<entidad>.parquet`; no toca nada existente):
- **Por valor-día y tramo** (sesión regular, y aparte la extendida):
  - rejilla de precio relativa al valor (paso = 0,1 % del precio de cierre anterior, para comparar valores y fechas);
  - volumen por nivel, POC y área de valor del 70 % (VAL/VAH);
  - nodos de volumen alto y bajo (los niveles por encima del percentil 80 y por debajo del 20 del propio perfil);
  - volumen total, rango y `source`.
- Una fila por valor-día con el resumen, más el perfil completo en formato largo comprimido.
- **Coste estimado:** recorrer las barras del histórico es como la fase 1 de cat-v1 (unos 45-50 min). Del orden de
  1-2 GB.

**Comparaciones** (`vp_compare.py`, calculado a demanda sobre esa tabla; no se congela nada):
- **Sesiones consecutivas:**
  - desplazamiento del POC, en % y en rangos medios (ATR);
  - solape de las áreas de valor;
  - parecido entre perfiles (distancia sobre la rejilla común);
  - si el cierre queda dentro, encima o debajo del área de valor anterior.
- **Ventanas de 5, 10, 20, 40 y 60 sesiones:**
  - perfil compuesto (suma de volúmenes por nivel);
  - concentraciones persistentes: niveles que están entre los nodos altos en ≥ X % de las sesiones de la ventana, con X
    y la ventana como parámetros de consulta, no fijados;
  - migración del POC (pendiente, número de cambios de sentido);
  - y, al lado, retorno, volumen relativo y rango del mismo periodo.
- Todo a fecha: un perfil de ventana para el día t solo usa sesiones ≤ t.

**En el laboratorio:**
- un mapa sesión × nivel de precio (color = volumen), con el precio de cierre y el POC superpuestos;
- selector de ventana (5-60 sesiones) y del tramo (regular o extendida);
- marca visible de la fuente (estimado con barras u observado en trades).

**Entrega de la primera versión:**
- tabla de perfiles del histórico y del registro diario;
- comparaciones a demanda;
- vista del laboratorio;
- y un cuaderno descriptivo con 4-6 casos elegidos por regla fija (por ejemplo: un valor con POC estable 20 sesiones,
  uno con migración sostenida, el estrés de 2020, un valor con opa pendiente), mostrando lo que se ve, sin conclusiones
  predictivas.

## 4. Acceso libre a la información y desglose bajo demanda (propuesta)

**Ya existe** (§4 de CV1_INFORME): cualquier valor y día se abre en el laboratorio con sus barras y sus 44 medidas,
tenga o no alerta. Si no está en el registro ni en la capa 2, se calcula desde las barras locales sin escribir nada.

**Lo que falta, acotado:**
1. **Intervalos de varias sesiones:** elegir valor y un rango de fechas (no solo un día) y ver barras agregadas (1, 5,
   15, 60 min y diarias), las medidas por sesión y, cuando exista, el perfil de §3.
   - Si faltan barras, se ofrece descargarlas (con estimación de coste y confirmación), igual que hoy los trades.
2. **Medidas nuevas desde las barras originales sin tocar nada congelado:** un espacio de trabajo
   (`MICRO_DATA_DIR/scratch/`) donde una medida definida a mano (función sobre la matriz de barras de `micro/`) se
   calcula para un valor y un intervalo.
   - Se guarda con su definición y su hash, y nunca escribe en las capas 1-3.
   - Si una medida resulta útil, pasarla a la capa 2 sería una decisión aparte.
3. **Desglose con trades y quotes integrado con cat-v1:**
   - `ev_drilldown.py` y la API del laboratorio aceptan `--catalog cat-v1` (episodios y alertas del registro cat-v1);
   - los cambios de estado tras el desglose se escriben en el registro de cat-v1, no en el de cat-v0;
   - **desglose de cualquier ventana elegida a mano en el laboratorio:** selección de la franja → estimación de
     peticiones y MB → confirmación → descarga → ficha;
   - topes de peticiones, tiempo y almacenamiento, y control de memoria (los mismos de hoy);
   - el periodo reservado de G2A sigue bloqueado salvo autorización explícita, y queda anotado.
4. **Búsqueda de estructuras semejantes, sin implementarla:** se conserva lo que la hará posible.
   - el vector de 44 medidas normalizadas por valor-día (capa 2);
   - los resúmenes de perfil de §3;
   - ambos indexados por emisor y fecha.
   - Solo hace falta añadir un índice de vecinos cuando decidas usarlo.

## 5. Resultados de la prueba de E3 y del control

### 5.1 Pasada `full` del viernes 2026-11-20 (prueba manual)

**Universo:** 620 valores (S&P 500 + Nasdaq 100 + valores y ETFs del proyecto) y el contexto: 621 símbolos en la
descarga.
- **Línea base:** 48 sesiones, del 2026-09-15 (el día siguiente al periodo reservado de G2A) al 2026-11-19.
- **Días descargados:** 49 (base + el día).

**Coste real de la primera captura** (no se había bajado ninguno de esos 49 días para estos valores):

| | |
|---|---|
| Unidades valor-día descargadas | 29 477 con barras + 204 vacías (+ 754 ya existentes) |
| Peticiones a Alpaca | 1 461 (≈ 30 por día de mercado, con lotes de 100 valores) |
| Transferencia | 1,24 GB de respuestas |
| Barras guardadas | 12,8 millones; 506 MB en disco (≈ 10 MB por día) |
| Tiempo de descarga | ≈ 83 s por día; 49 días en ≈ 90 min. Manda la escritura de ficheros en este disco, no la API |
| Fallos | 0 lotes fallidos, 0 divisiones, 0 caídas a petición individual |
| Escaneo cat-v1 | 620 valores en 13 tandas, ≈ 16 min (≈ 75 s por tanda de 50) |
| Comprobación de cobertura | ≈ 2 min |
| Registro del día (capa 2-3) | ≈ 1,05 MB: medidas 0,88 MB, valor-días 0,09 MB, alertas 0,05 MB, episodios 0,02 MB |

**Coste diario en régimen** (solo el día nuevo):
- ≈ 31 peticiones, ≈ 1,5 min de descarga y ≈ 10 MB;
- más ≈ 2 min de cobertura y ≈ 16 min de escaneo;
- **unos 20 minutos por pasada**, en este equipo.

**Lo que dejó el día:**
- **616 de 620 valores con datos:**
  - 3 sin datos son de OTC (GTBIF, MAPS, PLNH), que Alpaca no cubre;
  - **EQR no existe para Alpaca** («asset not found», 0 barras en los 49 días). La lista del S&P 500 actual está
    desfasada o el valor ha cambiado de símbolo. Queda como incidencia de cobertura del universo.
- **615 valores con sus 44 medidas** (27 060 filas). El que falta, AWX, tiene barras en el 2 % de los minutos: sin
  sesiones válidas no hay línea base. Queda registrado con línea base 0.
- **Estados de las medidas:**
  - 25 420 por debajo;
  - 916 no evaluables (sobre todo, after hours sin negociación);
  - 615 «requiere trades» (V3_close_est);
  - 109 marcas.
- **162 alertas en 63 valores, 80 episodios.** Ningún día de mercado, ninguna sospecha de caída de datos y ningún
  valor con cobertura baja.
  - Por familia: D 50, I 38, V 26, PM 22, P 13, C 13.
  - Por representación: 131 ventanas y 31 puntos.

**Pruebas de funcionamiento:**

| Prueba | Resultado |
|---|---|
| Interrupción simulada a los 3 lotes de descarga | El candado huérfano se detecta y se retira. La pasada siguiente salta las 300 unidades hechas y sigue |
| Interrupción real (proceso matado) durante la descarga | Reanuda sin repetir nada: el día a medias se completa con las unidades que faltaban |
| Interrupción real durante el escaneo (tras 2 tandas) | Reanuda con «520 pendientes, 100 ya hechos», sin volver a descargar (0 peticiones en los 49 días) |
| Segunda pasada completa (idempotencia) | 0 peticiones y 0 unidades nuevas. Huella del registro del día (medidas, valor-días, alertas y episodios) idéntica antes y después |
| Reintento de lote, división en mitades, caída a petición individual, valores vacíos | Probado con un proveedor simulado (`tests/test_e3_download.py`) |
| Coincidencia de la petición múltiple con las individuales | Ya verificada en E2 (`e2_multibars_check.py`) |

**Corregido durante la prueba**:
- **Coste del manifiesto:** cada operación en SQLite cuesta ~75 ms en este disco. Ahora se registra cada lote en una
  sola transacción, y los ficheros se escriben en paralelo: de 0,5 a 0,13 s por unidad.
- **Persistencia:** se leía todo el registro histórico de cat-v1 en cada tanda; ahora solo los días previos necesarios.
- **Alertas en vivo sin la columna `pass`:** el registro no podía sustituir bien un reescaneo. Se añadió la columna y se
  completó en las alertas ya escritas (sin duplicados).
- **Valores sin datos:** se reescaneaban en cada pasada, porque su fila no guardaba la versión del código.

**Integridad:**
- de los 71 587 ficheros de barras anteriores, ninguno ha cambiado ni se ha borrado; hay 30 073 nuevos;
- medidas, normalización y registro y resultados de cat-v0: sha256 idéntico;
- cambia el manifiesto, porque gana las filas nuevas, y se añaden 28 cachés de eventos corporativos.

### 5.2 Series de precio mezcladas en el histórico (S&P 500, 2016-01-04 → 2021-10-28)

- **759 827 valor-días** recorridos sobre las barras originales, sin errores, en ≈ 43 min.
- **Un solo caso marcado: JWN 2018-03-26**:
  - 181 cambios de nivel entre 47,07 $ y 63,73 $, con un 42 % de las barras en el nivel minoritario;
  - impacto: sus 1 034 alertas cat-v1 quedan «sospecha de datos»;
  - las medidas de la capa 2 de ese día se conservan y quedan identificadas como afectadas.
- **3 casi marcados**, con 3 cambios, por debajo de los 6 que exige la regla:
  - POM 2016-03-23 (salto del 17 %; es el día en que se cerró su compra por Exelon);
  - ZBH 2018-09-20 (9 %, el 0,5 % de las barras);
  - HSY 2016-08-29 (8 %).
  - Ninguno muestra niveles alternando: son saltos que se mantienen.
- **Lectura:** el problema de JWN es raro en este universo (1 de cada ~760 000 valor-días). El control queda en la
  pasada diaria por si aparece en otros datos.
- **Salidas:** `results/dq_mixed_series.parquet` (marcados, con su evidencia e impacto), `dq_mixed_series_candidates`
  (también los casi marcados) y `dq_mixed_series_summary.json`.

### 5.3 Sectores a fecha

- 18 575 valor-días elegibles del histórico tenían el sector sacado de una instantánea posterior (altas a mitad de año).
  Afectan a 3 182 alertas.
- Esos valor-días ya no tienen sector a fecha (`sector` vacío, `sector_point_in_time = false`). El sector posterior se
  conserva en `sector_retrospective`, marcado como aproximación retrospectiva.
- No entran en la simultaneidad por sector.
- El registro diario guarda el mismo indicador en cada valor-día.

## 6. Lo que necesito que decidas

1. **Operación diaria:** si autorizas lanzar la pasada `full` cada día a mano, o programarla, y por qué vía. Necesita
   este equipo encendido y unos 20 minutos.
2. **Universo:** EQR no existe para Alpaca. ¿Actualizo la lista del S&P 500 actual desde su fuente antes de seguir?
3. **Volume Profile (§3):** si la propuesta te vale tal cual, empiezo por la tabla de perfiles de la capa 2 y la vista
   del laboratorio.
4. **Acceso libre (§4):** el orden propuesto es desglose integrado con cat-v1 y ventanas manuales, luego intervalos de
   varias sesiones, luego el espacio de medidas nuevas.
