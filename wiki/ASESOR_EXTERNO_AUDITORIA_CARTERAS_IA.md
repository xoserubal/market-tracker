# Auditoría externa — AI Picks Lab: selección, entrada y salida por cartera y por modelo

**Fecha:** 2026-08-30
**Autor:** análisis interno (Claude Code) sobre datos reales del sistema
**Pregunta que se somete a revisión:** con ~4 meses de operación real (paper trading) en
7 carteras gestionadas por 4 modelos distintos, ¿qué mejoras concretas — en selección de
valores, en criterio de entrada, en criterio de salida — están soportadas por los datos, y
cuáles son solo intuición? ¿Qué se debería cambiar primero?

Este documento es autocontenido: incluye contexto del sistema, metodología, datos reales
extraídos hoy mismo del repositorio, y hallazgos ya establecidos en auditorías anteriores
(citados, no repetidos), para que un tercero sin acceso al repo pueda evaluar el sistema y
criticar el razonamiento.

---

## 0. Cómo leer este documento

- **Sección 1**: qué es el sistema, en el mínimo necesario para juzgar lo demás.
- **Sección 2**: las 7 carteras + 1 modelo shadow, mandatos y estado actual real.
- **Sección 3**: reglas exactas que rigen al comité IA (HARD_RULES, texto literal).
- **Sección 4**: cómo entra el sistema — evidencia sobre calidad de entrada.
- **Sección 5**: cómo sale el sistema — el hallazgo más nítido de este documento, cerrando
  en **5.4** con la pregunta central de esta auditoría (¿selección o ejecución?) respondida
  con precio real, operación por operación, y en **5.5** con el mismo cruce pero usando
  Koncorde/MACD/Flow Score reconstruidos (semanal sí separa resultado, MACD/Flow Score no —
  y en sentido contrario al esperado).
- **Sección 6**: comparativa entre los 4 modelos (Grok/Mimo/Haiku/Sonnet) — rendimiento
  real y calidad de la respuesta que emiten.
- **Sección 7**: lo que ya se investigó y se descartó — para no repetir trabajo.
- **Sección 8**: trabajo en curso relacionado (Ranking Score) — para no solapar.
- **Sección 9**: limitaciones metodológicas explícitas.
- **Sección 10**: preguntas concretas al asesor.
- **Sección 11**: apéndice A — ficheros fuente y cómo reproducir cada tabla.
- **Sección 12**: apéndice B — las **147 operaciones reales** del sistema (114 cerradas +
  33 abiertas), una fila por operación: modelo, fecha y precio de entrada, PCS, fecha y
  precio de salida (o "abierta" y precio actual), motivo, retorno, máximo/mínimo alcanzado
  mientras estuvo abierta, y qué hizo el precio 1 semana / 1 mes / máximo tras la salida.
  Es la base de datos detrás de §5.4 — si algo de §5.4 no convence, está aquí para
  verificarlo fila por fila.
- **Sección 13**: apéndice C — Koncorde D/W, MACD y Flow Score en el momento exacto de
  entrada y de salida de cada una de las mismas 147 operaciones (mismo orden que el
  Apéndice B, para cruzar retorno con contexto técnico fila a fila). La evolución día a día
  completa (no solo entrada/salida) está en `research/trade_review_2026-08/` — ver §5.5.

---

## 1. Qué es el sistema (mínimo necesario)

Paper trading donde señales cuantitativas se calculan primero y un LLM actúa como **filtro
final**, no como predictor de mercado:

```
MacroScore                      → permiso de riesgo (campo de juego, igual para todos)
rot_score + relative strength   → hacia dónde se mueve el capital
PCS (Pick Conviction Score)     → qué vehículo concreto lo captura (techo real 95, no 100)
IA (comité de modelos)          → decide si la señal es lo bastante limpia para operar
```

El universo actual (2026-08-29) son **132 candidatos** (126 elegibles), PCS elegible entre
27.0 y 89.5, mediana 59.2. Small caps, mineras, TSX Venture, utilities argentinas, crypto
miners — ATR de varios puntos es la norma, no la excepción.

**PCS** — 6 componentes con techo real distinto del nominal "0-100" (verificado, ver
`wiki/ASESOR_EXTERNO_PCS_INFORME.md`):

| Componente | Techo real | Qué mide |
|---|---|---|
| A — macro_permission | 14.0 | Régimen macro, idéntico para todos los tickers de una corrida |
| B — theme_flow | 24.0 | Flujo del tema sectorial |
| C — individual_rs | 23.0 | Relative strength individual |
| D — individual_flow | 20.0 | Flujo técnico (MACD, RSI, OBV) |
| E — early_acceleration | 9.0 | DEMS y señales diarias |
| F — data_quality | 5.0 | Calidad/completitud de datos |
| **Suma (techo real)** | **95.0** | no 100 |

---

## 2. Las carteras — mandatos y estado real hoy

| Cartera | PCS umbral | PCS mín. entrada | Máx pos | Tamaño | Motor de decisión |
|---|---|---|---|---|---|
| HIGH_CONVICTION | 85 | 82 | 8 | 8–15% | Comité IA (modelo activo) |
| CONFIRMED_FLOW_LEADERS | 78 | 75 | 12 | 5–10% | Comité IA (modelo activo) |
| EARLY_ROTATION | 70 | 68 | 15 | 4–8% | Comité IA (modelo activo) |
| MACRO_THEMATIC_BENEFICIARIES | 65 | 62 | 20 | 3–6% | Comité IA (modelo activo) |
| REJECTED_HIGH_SCORE *(control)* | 75 | 75 | 20 | 5% | Comité IA — cartera de control, nunca se opera |
| MIMO_SHADOW | igual que la cartera de origen | — | — | — | `xiaomi/mimo-v2.5-pro`, corre en paralelo sobre el mismo universo que ve el modelo activo, sin gastar capital real — sirve de comparación directa |
| CAVA_MACRO | 62 (puerta binaria) | 62 | 3/theme, 4/categoría Cava | 10% fijo | Cava (árbol de decisión determinista) decide postura/categorías elegibles; PCS decide el ticker dentro de eso |
| MIRROR_ESPEJO | — (no usa PCS) | — | sin límite | 5% fijo | Solo entra en señal Koncorde "espejo" (reversión), decide `x-ai/grok-4.3` con un prompt propio sin HARD_RULES ni PCS |

**Estado real de posiciones abiertas hoy** (`docs/data/ai_picks.json`):

| Cartera | Posiciones abiertas |
|---|---|
| HIGH_CONVICTION | 1 |
| CONFIRMED_FLOW_LEADERS | 2 |
| EARLY_ROTATION | 0 |
| MACRO_THEMATIC_BENEFICIARIES | 0 |
| REJECTED_HIGH_SCORE | 0 |
| MIMO_SHADOW | 18 |
| MIRROR_ESPEJO | 2 |
| CAVA_MACRO | 10 |

Modelo activo actual: `x-ai/grok-4.3` (desde 2026-06-20; antes `anthropic/claude-haiku-4.5`
desde el arranque del sistema el 2026-05-08). `xiaomi/mimo-v2.5-pro` corre como shadow desde
2026-06-20. `anthropic/claude-sonnet-4.6` aparece solo de forma ocasional/manual (n muy
pequeño en todo lo que sigue — tratarlo como anecdótico, no como muestra).

---

## 3. Reglas exactas del comité IA (HARD_RULES, texto literal)

Fuente: `scripts/ai_shared.py`, compartido por `paper_trading.py` y `build_eval_bundle.py`
(centralizado precisamente para que no puedan desincronizarse — hubo un incidente real de
esto antes de centralizarlo).

1. Solo puede seleccionar tickers presentes en la lista de candidatos.
2. Solo tickers con `eligible=true`.
3. No seleccionar futuros, commodities ni índices macro directamente — si la señal viene de
   un tema commodity/macro, seleccionar la acción/ETF relacionado.
4. No rellenar carteras con picks mediocres — una lista `selected` vacía es una respuesta
   válida.
5. Solo JSON válido, sin markdown ni texto extra.
6. No inventar datos ausentes del payload. Si `prev_snapshot_available=false`, no especular
   sobre cambios de PCS/score entre semanas.
7. Ante contradicciones fuertes, usar WATCH o REJECT, no SELECT.
8. Cada `selected` debe traer portfolio, signal_type, confidence, reason_short (≥20
   caracteres), reason_full (≥100), comparative_edge (≥30, debe nombrar al menos un peer y
   explicar por qué quedó por debajo).
9. Cada `rejected` debe traer reason + una `rejection_category` válida.
10. Cada candidato con pcs≥62 no seleccionado debe aparecer en **exactamente una** de
    watch/rejected, nunca en ambas.
11. No hacer SELECT de un ticker ya presente en `active_picks_relevant` — ya es posición
    abierta.
12. En HIGH_CONVICTION y CONFIRMED_FLOW_LEADERS, no usar DEMS/spike_flag como razón
    **primaria** de REJECT cuando las métricas semanales (ret_4w/13w_vs_spy, streak_weeks)
    son fuertes — usar WATCH.
13. Revisar **todas** las posiciones abiertas en `open_picks_review`. EXIT si: (a)
    `current_pcs < pcs_min_entry AND current_streak_weeks <= 1`, O (b) `current_rot_score
    <= 2`, O (c) `current_pcs < 62` (suelo absoluto, independiente del streak), O (d)
    `left_universe=true`. Si no, HOLD. No se puede omitir ninguna posición activa.

**Nota importante para el asesor:** la regla 13 es, en la práctica, la totalidad de lo que
gobierna las salidas — ver Sección 5, es el hallazgo más nítido de este documento.

Categorías de rechazo válidas: `insufficient_conviction`, `macro_conflict`, `weak_flow`,
`weak_relative_strength`, `technical_overextension`, `data_quality`, `not_tradable`,
`better_alternative_available`.

---

## 4. Entrada — qué mira el modelo, evidencia de calidad

El payload que recibe el modelo por candidato incluye (además de PCS y sus 6 componentes):
`rot_score`, `ret_4w/13w_vs_spy`, `streak_weeks`, `dist_52w_high`, DEMS/`spike_flag`,
`extension_risk` (nivel + puntos + flags, observacional), `theme_concentration_risk` /
`subtheme_concentration_risk` (observacional), `konc_d/3d/w_state` + `konc_alignment`
(observacional). Ninguno de los campos observacionales es hard rule — son guidance "soft"
en el prompt.

### 4.1 Extension risk (¿se entra tarde?) — actualizado con más datos que la última vez

Reconstruido retroactivamente vía `scripts/reconstruct_extension_risk_historical.py`
(232 ticker-fecha, sin look-ahead — usa solo barras ≤ fecha de entrada), cruzado contra
`ret_1m` real (167 con ambos datos disponibles):

| extension_risk | n | ret_1m medio | mediana | % gana |
|---|---:|---:|---:|---:|
| low | 49 | -2.26% | -4.60% | 40.8% |
| medium | 78 | -3.88% | -3.67% | 38.5% |
| high | 32 | -3.54% | -0.72% | 46.9% |
| **extreme** | **8** | **-20.91%** | **-18.04%** | **12.5%** |

Mismo patrón que la primera pasada de este análisis (2026-08-05, entonces n mucho más
pequeño): **extreme es claramente malo, pero low/medium/high no forman una escalera
limpia** — medium (n=78) es peor que high (n=32) en media. Con n=167 ya no es una muestra
diminuta, pero la ausencia de escalera sigue sin explicarse. n=8 en "extreme" sigue siendo
poco para actuar.

### 4.2 PCS como ranking por encima del umbral — recordatorio, no repetido aquí

Ya establecido con rigor en `wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md` §3.5: correlación
global PCS↔ret_1m sobre 136 picks de 5 carteras = **-0.007**, signo inconsistente cartera
por cartera. **No se ha vuelto a recalcular en este documento** — sigue siendo el hallazgo
vigente. Ver también Sección 8 (Ranking Score) para el intento en curso de abordarlo.

### 4.3 Confidence del modelo vs. quality_score del validador — dos señales distintas

Ya establecido: el campo `confidence` que emite el propio modelo **no discrimina**
resultado (CFL: high -4.70%, medium -3.83%, CFL diagnóstico §3.5). Este documento añade una
señal distinta que **nunca se había cruzado con retorno**: `quality_score` y
`hard_rule_violations`, calculados automáticamente por `validate_model_response()` sobre
cada llamada — ver Sección 6.2, es uno de los hallazgos más interesantes de esta auditoría.

---

## 5. Salida — el hallazgo más nítido de este documento

### 5.1 El 100% de los cierres reales del sistema son mecánicos, verbatim

Se auditaron **los 114 eventos de cierre** (`event: "close"`) de las 8 carteras en
`docs/data/ai_picks.json`, leyendo el texto exacto de `close_reason` — que en el código
(`paper_trading.py`, `update_portfolio()`) es literalmente `review.get("reason", "")`: el
texto que el propio modelo escribió al decidir EXIT, no una descripción generada por el
sistema a posteriori.

```
Cierres por umbral de PCS ("pcs X below Y" / "pcs X < Y floor"):  100 / 114  (88%)
Cierres por rot_score bajo:                                         9 / 114  ( 8%)
Cierres por trailing stop (solo MIRROR_ESPEJO, mecanismo propio):   5 / 114  ( 4%)
Cierres sin ninguna de las tres palabras clave arriba:               0 / 114  ( 0%)
```

**Cero de 114.** Aunque la HARD_RULE 13 permite —de hecho exige— que el modelo revise cada
posición abierta y decida EXIT con su propio juicio, **nunca**, en ningún cierre registrado
desde que la función existe (2026-06-09), el modelo ha articulado una razón de salida que no
sea, textualmente, restar el número de PCS o rot_score contra su umbral. No hay un solo caso
observado de "la tesis se rompió por una razón cualitativa" (competencia, guidance, ruptura
técnica, cambio de narrativa) como motivo de cierre — a pesar de que sí existen esos
argumentos en los `reason_full` de las **entradas** (SELECT).

Desglose por cartera:

| Cartera | Cierres | PCS floor | rot_score | trailing stop |
|---|---:|---:|---:|---:|
| HIGH_CONVICTION | 8 | 8 | 0 | 0 |
| CONFIRMED_FLOW_LEADERS | 26 | 24 | 2 | 0 |
| EARLY_ROTATION | 6 | 6 | 0 | 0 |
| MACRO_THEMATIC_BENEFICIARIES | 2 | 2 | 0 | 0 |
| MIMO_SHADOW | 52 | 45 | 7 | 0 |
| MIRROR_ESPEJO | 5 | 0 | 0 | 5 |
| CAVA_MACRO | 15 | 15 | 0 | 0 |

CAVA_MACRO y MIRROR_ESPEJO no pasan por el modelo en absoluto para decidir salidas — son
100% mecánicas por diseño desde el principio (ver CLAUDE.md). Lo que este hallazgo añade es
que **las 4 carteras que sí tienen un LLM con autoridad para decidir EXIT por juicio propio
(HC/CFL/ER/MTB) tampoco lo usan nunca en la práctica** — convergen exactamente al mismo
comportamiento que Cava/Espejo tienen por construcción.

### 5.2 ¿Es esto un problema? — evidencia de que la propia regla mecánica es ruidosa

Ya establecido en el diagnóstico de CFL (§3.4): el retorno a 1 semana predice fuertemente
el de 1 mes (corr +0.723 a +0.802 según cartera, solo 2-4/30 negativos a 1w recuperan a 1m)
— la propia regla de salida mecánica, aunque simplista, tiene una base real. Pero:

**`pcs_floor_whipsaw_shadow.jsonl` (38 cierres por suelo de PCS clasificados
retroactivamente, todas las carteras):**

| Clasificación | n | Interpretación |
|---|---:|---|
| likely_real_deterioration | 35 | precio cayó de verdad (media -5.85%, mediana holding 10 días) |
| **flat_price_whipsaw** | **3** | cerrado en 1 día, precio prácticamente plano, el componente PCS que se movió fue `B_theme_flow` en 2/3 casos — ruido de un día en el flujo del tema, no del propio ticker |

Los 3 casos de ruido puro: SE (CFL, 2026-07-07→08, precio -0.73%, B_theme_flow 22→6),
SE (MTB, 2026-07-15→16, +1.89%), NVDA (MTB, 2026-07-15→16, +0.33%).

**Caso adicional encontrado en este análisis, no capturado todavía por el shadow monitor**
(muy reciente): `FCX` en CAVA_MACRO — entrada 2026-08-03, cerrada 2026-08-26 **con +25.57%
de ganancia** por `pcs 61.5 < 62.0` (a 0.5 puntos del suelo), y **reabierta al día
siguiente**, 2026-08-27. Un caso de manual, no verificado aún por el script automático —
merece revisión.

**Lectura combinada:** la regla mecánica de salida es la única que existe en la práctica
(§5.1), tiene una base estadística real (ret_1w predice ret_1m), pero produce al menos un
~8% de cierres identificables como ruido de un solo día en un componente concreto del PCS
(B_theme_flow, el más volátil de los 6), sin ningún mecanismo de segunda lectura antes de
ejecutar el cierre.

### 5.3 Reentrada tras fallo — evidencia todavía escasa

`cfl_reentry_cooldown_shadow.jsonl` (23 filas, shadow-only, nunca aplicado de verdad):
`ret_1w<0` en la entrada ("is_failure") en 13/23 = 56.5% de los casos. Si existiera un
cooldown de 18 sesiones tras un fallo a 1 semana, **3 reentradas habrían quedado
bloqueadas**: SASK.V (2026-06-20), URI (2026-07-25), WCP.TO (2026-08-11) — n demasiado
pequeño para saber si el cooldown habría ayudado o simplemente habría evitado operaciones
que igualmente habrían salido bien.

`cfl_followthrough_shadow.jsonl` — solo **3 filas** en 25 días desde que existe el script
(2026-08-05). Esto es en sí mismo informativo: **CFL rara vez mantiene una posición abierta
más de ~1 semana antes de que el suelo mecánico de PCS la cierre primero** — el propio
diseño de la regla de salida no deja mucho margen para que una regla de seguimiento a 1
semana tenga datos que evaluar.

### 5.4 ¿Selección o ejecución? — evidencia operación por operación, con precios reales

Todo lo anterior son agregados. Para responder directamente "¿el pick era bueno y solo
falló cuándo entrar/salir, o el pick en sí era malo?" hace falta el dato que faltaba en la
primera versión de este documento: **fecha y precio exactos de entrada y salida de cada
operación real, cruzados con lo que hizo el precio antes, durante y después** — no solo el
retorno del punto de entrada al punto de salida.

Se reconstruyeron las **147 operaciones reales** de las 8 carteras (114 cerradas + 33
abiertas hoy) con precios reales de Yahoo Finance (`auto_adjust=True`, cierre a cierre, sin
intradía) para calcular, por cada una: el **máximo y el mínimo alcanzado mientras la
posición estuvo abierta** (¿hubo recorrido real, aunque no se capturara?), y — la pieza
nueva — **qué hizo el precio en el mes siguiente al cierre** (¿la salida evitó más caída, o
cortó justo antes de un rebote?). Tabla completa operación por operación en el
**Apéndice B** (Sección 12).

**Hallazgo 1 — se deja mucho recorrido sobre la mesa antes de que el suelo mecánico actúe.**
Sobre 112 cierres con ambos datos disponibles: diferencia entre el máximo alcanzado durante
la tenencia y el retorno realmente materializado al cerrar:

```
media   = 9.64 puntos porcentuales dejados sobre la mesa
mediana = 6.55 pp
38/112 (34%) dieron atrás más de 10pp de una ganancia intermedia antes de cerrar
```

Casos concretos representativos (no elegidos por ser los más extremos, sino por ilustrar
dos patrones distintos):

- **TDOC** (CFL, entrada 2026-06-16 a $7.46): llegó a **+30.29%** mientras estuvo abierta,
  y se cerró 45 días después, el 2026-07-31, a **-11.80%** — dio la vuelta entera de +30%
  a -12% sin ningún mecanismo que capturara nada del recorrido intermedio, porque el suelo
  de PCS no reacciona al precio, reacciona al propio PCS.
- **NBIS** (HIGH_CONVICTION, entrada 2026-05-08 a $177.05): llegó a **+61.93%**, se cerró el
  2026-07-02 a **+29.44%** — en este caso el cierre sí capturó ganancia real, pero dejó
  32.5pp de un recorrido que sí existió y que el sistema vio y no protegió.

**Hallazgo 2 — casi 4 de cada 10 cierres van seguidos de un rebote apreciable en el mes
siguiente.** Sobre 111 cierres: el precio alcanza un máximo medio de **+8.23%** (mediana
+6.56%) sobre el precio de cierre, dentro del mes posterior a la salida. **43/111 (39%)**
superan el +8% en ese mes. Frente a esto, solo **17/57 (30%, de los que ya tienen 1m
maduro)** siguen cayendo más de un 5% tras la salida — es decir, hay más casos de "salimos y
subió" que de "salimos y siguió cayendo" entre los que ya se pueden medir a un mes.

Casos concretos:

- **NBIS** (CONFIRMED_FLOW_LEADERS y MIMO_SHADOW simultáneamente — mismo evento de mercado
  contado dos veces, ver limitación en §9): cerrada el 2026-08-07 a $189.88 por
  `PCS 57.0<75`/`PCS 57.0<62` — el precio llegó a **+46.24%** sobre ese cierre dentro del
  mes siguiente.
- **NBIS** (MIMO_SHADOW, otro ciclo distinto, cerrada 2026-07-28 a -14.97% realizado): a la
  semana +13.87%, al mes **+47.80%** de máximo sobre el precio de cierre.
- **SASK.V** (CFL, cerrada 2026-06-10 a -22.22% realizado): al mes, máximo de **+35.16%**
  sobre el precio de cierre.
- **EOSE** (CFL, cerrada 2026-06-10 a -30.37% realizado): esta sí siguió cayendo
  (post-cierre 1m = -30.51%) — un caso donde la salida mecánica sí estaba justificada,
  incluido a propósito para no dar una imagen sesgada solo de rebotes.

**Hallazgo 3 — el caso FCX (CAVA_MACRO) es el ejemplo más limpio de fricción sin propósito
del suelo mecánico.** Entrada 2026-08-03 a $63.64. Cerrada 2026-08-26 a $79.91 —
**+25.57% de ganancia real, capturada** — por `PCS 61.5 < 62.0` (medio punto por debajo del
umbral). Reabierta al **día siguiente**, 2026-08-27, a $78.42 — prácticamente el mismo
precio. El suelo hizo exactamente lo que está diseñado para hacer (cerrar cuando el PCS cae
del umbral) sobre una posición que, mirada con precio real, no tenía ningún problema — y el
propio sistema volvió a comprar casi de inmediato. No estaba en el conjunto de 3 casos que
`pcs_floor_whipsaw_shadow.jsonl` había detectado hasta ahora (Sección 5.2) — es reciente y
el script automático aún no lo ha evaluado.

**Lectura combinada de 5.1-5.4, para no perder el hilo:** el sistema tiene un único
mecanismo de salida real (el suelo de PCS/rot_score, §5.1), que no mira el precio en
absoluto — solo el propio PCS. Eso significa que puede cerrar una posición que va ganando
mucho (FCX, NBIS) exactamente igual que una que va perdiendo mucho (EOSE), y que entre el
punto de entrada y el disparo del suelo puede pasar bastante tiempo (mediana 10 días en
`pcs_floor_whipsaw_shadow.jsonl`, hasta 45 días en TDOC) durante el cual no hay ninguna
protección de ganancias ni ningún corte de pérdidas más ceñido. **Esto no demuestra que los
picks sean malos** — varios de los casos con peor retorno realizado (TDOC, NBIS) tuvieron
recorrido a favor real y sustancial en algún momento de la tenencia. Apunta más bien a que
**la mecánica de salida —no la de selección— es donde más margen de mejora hay,
evidenciado con precios reales, no solo con la correlación ya conocida (§5.2, ret_1w→ret_1m)**.

### 5.5 Contexto técnico en el momento de entrada — Koncorde D/3D/W, MACD y Flow Score reconstruidos

El sistema en producción no persistía Koncorde/Flow Score/MACD para ninguno de estos picks
en el momento de la entrada o la salida (esa captura completa solo existe desde 2026-08-20,
ver CLAUDE.md "Captura diaria completa de Portfolio Tracker") — así que, para poder cruzar
selección de valores con contexto técnico real en retrospectiva, se **reconstruyó** todo
esto desde cero para las 147 operaciones, reutilizando el código de producción real, no una
reimplementación:

- **Koncorde D/3D/W**: importadas directamente las funciones de
  `scripts/koncorde_calculator.py` (`_calc_koncorde_plus`, `_resample_3d`,
  `_resample_weekly` — esta última ya con el fix del 2026-08-30, ver hilo anterior de esta
  misma conversación — `_state`), computadas una sola vez sobre el histórico completo de
  cada ticker (2022-06→hoy) y leídas en cualquier fecha histórica — válido porque la
  normalización interna es una ventana móvil estrictamente hacia atrás (`pandas.rolling`,
  sin `center=True`), así que no hay look-ahead: el valor en una fecha pasada es idéntico al
  que habría mostrado el pipeline en vivo ese día. **Verificado exacto** contra el snapshot
  real de producción: PLTR 2026-08-28 reconstruido da `konc_d_blue=-14.80` — coincide al
  céntimo con el valor real que ya se citó en el hilo anterior sobre PLTR de esta misma
  conversación.
- **RSI/MACD/ATR%/Flow Score/Early Flow Score**: reutilizadas literalmente
  `shared/quote-lib.js` (`calcRSI`, `calcMACD`, `calcATR`) y `shared/flow-score.js`
  (`computeFlowScore`, `computeEarlyFlowScore`) — el mismo código que sirve `portfolio.html`
  — recorriendo cada fecha del histórico con la serie de precios recortada hasta ese día
  (misma disciplina sin look-ahead). `w1`/`m1` en Flow Score son el retorno propio del
  ticker a 5/21 sesiones, **no** relativo a SPY (confirmado leyendo `buildQuoteData()` — una
  aclaración necesaria porque en otra parte del proyecto, al intentar portar Early Flow a
  Python, se había asumido lo contrario).

**Primer cruce — contexto técnico en la entrada vs. retorno realizado** (112 cierres con
señal reconstruida disponible):

| Corte | n | ret. realizado medio | mediana |
|---|---:|---:|---:|
| `konc_w_state` = up (semanal alcista) | 72 | **-2.31%** | -3.44% |
| `konc_w_state` = distribution (semanal bajista) | 34 | **-6.11%** | -5.16% |
| `konc_d_state` = up | 73 | -3.66% | -3.48% |
| `konc_d_state` = distribution | 38 | -4.48% | -5.09% |
| MACD **alcista** en la entrada | 85 | **-5.10%** | -4.53% |
| MACD **bajista** en la entrada | 27 | **-0.10%** | -1.97% |
| Flow Score "Líder" (≥8) en la entrada | 94 | **-4.10%** | -4.28% |
| Flow Score "Débil" (<4) en la entrada | 11 | **-1.10%** | -2.10% |

Dos lecturas, en direcciones opuestas:

- **`konc_w_state` en la entrada sí separa** (-2.31% vs -6.11%, 3.8pp, en la dirección
  esperada) — coherente con lo que el propio proyecto ya documenta sobre Koncorde semanal
  como la lectura menos ruidosa (`konc_d_state` separa en la misma dirección pero mucho más
  débil, coherente también con "el diario es ruido").
- **MACD alcista y Flow Score "Líder" en la entrada correlacionan con *peor* resultado, no
  mejor** — contraintuitivo, y en la dirección opuesta a lo que se esperaría de dos señales
  de momentum. Mirando la tabla del Apéndice C se ve un patrón recurrente: muchas entradas
  llevan MACD ▲ (alcista) el día de entrar y ▼ (bajista) el día en que el suelo de PCS
  finalmente las cierra — el MACD parece girar bajista *antes* de que el PCS se rompa, sin
  que el sistema use esa señal para nada. Compatible con una lectura de "el sistema compra
  momentum ya maduro" (persigue fuerza que está a punto de agotarse) más que con "compra
  demasiado pronto".
- **Caso de validación cruzada, no buscado a propósito:** las 7 entradas de MIRROR_ESPEJO
  (Apéndice C) tienen **Flow Score negativo en el 100% de los casos** (-7.7 a -35.8) — encaja
  exactamente con el diseño documentado de esa cartera (entra en reversiones tipo V tras una
  caída fuerte, cuando el momentum convencional todavía se lee como débil/negativo) y sirve
  de verificación de que la reconstrucción está calculando lo que dice calcular.

**El documento con el dato completo, día a día, ticker a ticker — no solo el cruce de
arriba:**

> **`research/trade_review_2026-08/trade_review_signals.csv`** — 3.697 filas, una por
> (ticker, fecha), con precio, RSI, MACD, ATR%, Koncorde D/3D/W — azul y **línea roja**
> (`trend_ma`) de cada timeframe, más el estado — y Flow Score/Early Flow Score, para cada
> uno de los 68 tickers, cubriendo desde 25 días antes de cada entrada hasta 40 días después
> de cada cierre (o de hoy, si sigue abierta). CSV, no JSONL — pensado para abrirse
> directamente en Excel/Sheets y ordenar/filtrar/graficar sin herramientas adicionales. Es
> el dato en bruto: **el análisis de esta sección es una primera lectura, no la única
> posible** — con esta tabla se puede repetir el cruce de arriba con otros cortes, mirar la
> evolución completa alrededor de una operación concreta (no solo su punto de entrada/salida,
> que es todo lo que muestra el Apéndice C), o proponer reglas de entrada/salida nuevas y
> probarlas contra estos mismos datos. **No** incluye verde ni la línea ocre (`trend` sin
> suavizar) — ver `README.md` de esa carpeta para el detalle exacto de qué queda dentro y
> qué no.

Ficheros de soporte, todos en `research/trade_review_2026-08/` (fuera del repo de
producción a propósito — reconstrucción de un solo uso para esta auditoría, no un artefacto
del pipeline), documentados en el `README.md` de esa carpeta:

| Fichero | Contenido |
|---|---|
| `trade_review_signals.csv` | **El documento** — ver arriba |
| `trade_review_signals.jsonl` | Mismo dato, formato JSONL (una fila = un objeto JSON), para quien prefiera procesarlo por script |
| `koncorde_reconstructed_raw.json` | Series diarias/3D/semanales completas de Koncorde por ticker, histórico completo (no solo la ventana de la operación) |
| `ohlcv_long_history.json` | OHLCV crudo, 2022-06→2026-08-30, fuente única para ambos scripts de reconstrucción |
| `reconstruct_flow_macd.js` | Script Node que genera el JSONL/CSV — reproducible, documentado, reusa el código de producción sin reimplementarlo |
| `README.md` | Esquema de columnas, metodología y huecos conocidos, en detalle |

**Huecos conocidos:** `EQR` (2 operaciones en MIMO_SHADOW) sin datos — Yahoo Finance solo
devuelve 15 sesiones recientes para este ticker en el momento de escribir esto, un problema
de la fuente, no de la reconstrucción (mismo patrón que otros gaps de datos ya documentados
en el proyecto — TIPS/nominal en subastas, renombrado de WTI). `NBIS` (IPO ~2024-10) tiene
menos de 2 años de histórico — su Koncorde semanal puede faltar en las primeras operaciones
(ver "—" en Apéndice C) por warmup insuficiente, no por error.

---

## 6. Comparativa entre modelos — Grok / Mimo / Haiku / Sonnet

### 6.1 Rendimiento real por cartera × modelo (ret_1m, muestra limpia)

Metodología: mismo criterio que `wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md` §2 — deduplicado
por (modelo, ticker, portfolio, fecha, pcs), excluido el bloque zombi de mayo (9 posiciones
sin vía de salida antes de que existiera `update_portfolio` EXIT, ver CLAUDE.md "Cierre de
posiciones"). n=249 tras limpieza, sobre `docs/data/shadow_picks.jsonl` (298 filas crudas).

| Cartera | Modelo | n | ret_1m medio | mediana | % gana |
|---|---|---:|---:|---:|---:|
| CONFIRMED_FLOW_LEADERS | haiku-4.5 | 39 | **-5.02%** | -6.84% | 35.9% |
| CONFIRMED_FLOW_LEADERS | grok-4.3 | 20 | **+0.33%** | -2.81% | 45.0% |
| CONFIRMED_FLOW_LEADERS | sonnet-4.6 | 2 | +21.09% | — | — *(n irrelevante)* |
| CONFIRMED_FLOW_LEADERS | mimo-v2.5-pro | 2 | -23.82% | — | — *(n irrelevante)* |
| EARLY_ROTATION | haiku-4.5 | 28 | -1.36% | -6.08% | 46.4% |
| EARLY_ROTATION | grok-4.3 | 6 | -11.98% | -9.23% | 33.3% |
| HIGH_CONVICTION | haiku-4.5 | 21 | +3.65% | -0.21% | 47.6% |
| HIGH_CONVICTION | grok-4.3 | 6 | -6.80% | -14.29% | 33.3% |
| MACRO_THEMATIC_BENEFICIARIES | haiku-4.5 | 10 | -14.94% | -12.23% | 10.0% |
| MACRO_THEMATIC_BENEFICIARIES | grok-4.3 | 2 | +8.38% | — | — *(n irrelevante)* |
| **MIMO_SHADOW** *(mimo, en paralelo, sin capital real)* | mimo-v2.5-pro | **37** | **+0.34%** | +0.75% | **56.8%** |

**Overall por modelo, todas las carteras (ret_1m):**

| Modelo | n | media | mediana | % gana |
|---|---:|---:|---:|---:|
| haiku-4.5 | 98 | -3.13% | -6.70% | 38.8% |
| grok-4.3 | 34 | -2.63% | -3.29% | 44.1% |
| mimo-v2.5-pro (shadow) | 42 | -2.05% | -0.30% | 50.0% |
| sonnet-4.6 | 5 | +5.73% | +8.71% | 60.0% *(n irrelevante, anecdótico)* |

**Hallazgo a subrayar y a la vez matizar con cuidado:** el modelo shadow (mimo, que nunca
ha gestionado capital real) tiene el mejor % de aciertos y una media casi neutra, mejor que
los dos modelos que sí han operado la cartera real (haiku primero, grok después). **Pero
haiku operó mayoritariamente mayo-junio y grok mayoritariamente julio-agosto, mientras que
mimo (shadow desde 2026-06-20) solapa sobre todo con el periodo de grok** — es decir, esta
comparación mezcla modelo y régimen de mercado, exactamente el mismo problema de confusión
que ya señalaba el diagnóstico de CFL para el cambio haiku→grok. **No se puede concluir
"mimo es mejor modelo" de esta tabla sola** — hace falta un cruce fecha a fecha (ver
Sección 10, pregunta 4).

### 6.2 Calidad de la respuesta — quality_score y hard_rule_violations, nunca cruzados con retorno hasta ahora

`docs/data/ai_model_test_summary.jsonl` (441 llamadas registradas), calculado
automáticamente por `validate_model_response()` en cada llamada — independiente del
resultado de mercado, mide solo si la respuesta del modelo cumplió el formato/reglas:

| Modelo | Llamadas | quality_score medio | hard_rule_violations medio | % respuesta con schema inválido |
|---|---:|---:|---:|---:|
| grok-4.3 | 203 | **89.6** | **0.08** | 3.0% (6/203) |
| mimo-v2.5-pro | 134 | 76.5 | 0.22 | 17.9% (24/134) |
| haiku-4.5 | 68 | **59.0** | **4.15** | 26.5% (18/68) |
| sonnet-4.6 | 4 | 69.75 | 0.00 | 25% (1/4, n irrelevante) |

haiku-4.5 viola en promedio **más de 4 hard rules por llamada** — muy por encima de grok
(0.08) y mimo (0.22). Esto no se había cuantificado nunca en un documento de auditoría.

**Cruce nuevo, hecho para este documento: ¿el quality_score de la llamada predice el
retorno de los picks de esa llamada?** Se unió cada pick con ret_1m (n=249, arriba) contra
el quality_score/hard_rule_violations promedio de las llamadas de ese modelo ese día
(n=179 con ambos datos disponibles):

```
corr(quality_score, ret_1m)          = -0.069   (prácticamente nula, signo contraintuitivo)
corr(hard_rule_violations, ret_1m)   = -0.099   (débil)

split por mediana de quality_score (mediana=80):
  quality_score >= 80:  n=90   ret_1m medio = -3.62%
  quality_score <  80:  n=89   ret_1m medio = -1.44%   <- ¡peor score, mejor retorno!

split por hard_rule_violations:
  hard_rule_violations == 0:  n=67   ret_1m medio = +1.66%
  hard_rule_violations >  0:  n=112  ret_1m medio = -5.05%   <- diferencia de 6.7 puntos
```

**Dos lecturas en tensión, deliberadamente no resueltas aquí:**
- La correlación lineal (Pearson) es casi nula en ambos casos — no hay una relación continua
  limpia.
- Pero el corte binario `hard_rule_violations==0` vs `>0` muestra una diferencia de 6.7
  puntos porcentuales en ret_1m medio — grande si es real.
- **El riesgo de confusión es alto**: haiku concentra casi todas las violaciones (4.15/call)
  y operó sobre todo mayo-junio; grok casi no viola reglas (0.08/call) y operó sobre todo
  julio-agosto. La diferencia observada puede ser "las violaciones de hard rules predicen
  mal resultado" o puede ser enteramente "julio-agosto fue mejor mercado que mayo-junio,
  y da la casualidad de que ahí es cuando corría el modelo que menos viola reglas". Con los
  datos actuales **no se puede separar una hipótesis de la otra** (mismo problema exacto que
  §6.1). Es la pregunta más interesante de esta auditoría y la que menos se puede responder
  sin un cruce controlado por fecha.

### 6.3 vs_spy_1m por cartera (alpha real, todas las carteras/modelos combinados)

| Cartera | n | vs_spy_1m medio | mediana | % gana |
|---|---:|---:|---:|---:|
| CONFIRMED_FLOW_LEADERS | 63 | -3.46% | -4.84% | 39.7% |
| EARLY_ROTATION | 37 | -3.37% | -7.63% | 43.2% |
| HIGH_CONVICTION | 28 | **+0.34%** | -2.77% | 42.9% |
| MACRO_THEMATIC_BENEFICIARIES | 14 | **-11.13%** | -9.61% | 21.4% |
| MIMO_SHADOW | 37 | -1.34% | -0.28% | 48.6% |

MACRO_THEMATIC_BENEFICIARIES es la peor con diferencia — el umbral de entrada más bajo del
sistema (PCS≥62) coincide con el peor alpha, coherente con (aunque no prueba causalidad de)
la hipótesis "umbral más bajo = selección más ruidosa".

### 6.4 Las dos carteras "fuera del comité" — datos reales, muestra pequeña

**CAVA_MACRO** (15 cierres, todos por suelo de PCS): media -1.21%, mediana -1.98%, 33.3% de
aciertos. Incluye el caso FCX de §5.2 (+25.57% cerrado por 0.5 puntos de PCS).

**MIRROR_ESPEJO** (5 cierres, todos por trailing stop del 5%, sin PCS): media **+3.73%**,
mediana +0.97%, **80% de aciertos**. n=5 es anecdótico — no se puede sacar ninguna
conclusión estadística — pero es la única cartera del sistema sin ningún cierre negativo
por debajo de -3.5% y con la mayor tasa de acierto observada. Merece seguimiento explícito
dado lo pequeño que es todavía.

---

## 7. Ya investigado y descartado — para no repetir trabajo

El proyecto tiene un historial de hipótesis probadas con preregistro y rechazadas. Listadas
aquí para que el asesor no proponga repetir exactamente lo mismo sin saberlo:

| Hipótesis | Resultado | Documento |
|---|---|---|
| PCS ordena resultado por encima del umbral | Rechazada — corr global -0.007 | `ASESOR_EXTERNO_CFL_DIAGNOSTICO.md` |
| Relative Flow Lab (45 ratios macro/sector) predice alfa futuro | Rechazada — r≈0 en 1w/1m/3m pooled | `RELATIVE_FLOW_LAB_HALLAZGOS.md` |
| Familia refugio vs. industrial (oro/plata/cobre/platino) responde distinto a la señal de Relative Flow | Rechazada tras corrección metodológica (Δ TAE → excess_CAGR_calendar) | `PREREGISTRO_RELATIVE_FLOW_FAMILY_TEST_V1.md` |
| Precursores técnicos (RSI/volumen/vela) anticipan rebote tras capitulación | Rechazada, n=590, con grupo de control | `HALLAZGOS_CAPITULACION_PRECURSORES_V1.md` |
| Confidence emitido por el modelo discrimina resultado | Rechazada | `ASESOR_EXTERNO_CFL_DIAGNOSTICO.md` §3.5 |

Principio operativo del proyecto, explícito: **una estrategia con exposición intermitente
(<50% del calendario) debe evaluarse con `excess_CAGR_calendar`, nunca con una métrica
anualizada solo sobre días expuestos** — derivado de un caso real donde una métrica mal
elegida mostró +50pp de "alfa" que en realidad eran -25pp frente a comprar y mantener. Si el
asesor propone métricas nuevas de evaluación de reglas de entrada/salida, aplicar este
principio.

---

## 8. Trabajo en curso relacionado — para no solapar

**Iniciativa Ranking Score / PCS reframing** (`wiki/PREREGISTRO_RANKING_SCORE_V0.md`,
firmado 2026-08-06): ataca directamente el mismo hallazgo de §4.2 (PCS no ordena). Fase 0
(campos `pcs_raw`/`pcs_ex_macro`/`pcs_normalized`/componentes A-F como campos de primer
nivel + persistencia + retropoblación histórica vía git-history de
`rot_score_delta_4w`/`theme_breadth`) **completa desde 2026-08-07**. Fase 1 (informe
descriptivo de 3-5 páginas sobre estos campos + Koncorde en subsección propia) **agendada
para 2026-09-03** — deliberadamente pospuesta para dar tiempo a que madure más muestra, no
por dependencia técnica. Koncorde Research Log (`docs/data/koncorde_signals_history.jsonl`)
fusionado dentro de esta misma Fase 1.

**El asesor puede opinar sobre el diseño de esta iniciativa** (el preregistro está abierto a
crítica) pero no debería proponer repetirla desde cero — el trabajo de reconstrucción
histórica (git-history, sin look-ahead) ya está hecho y verificado.

---

## 9. Limitaciones metodológicas — explícitas, no ocultas

1. **Un solo régimen de mercado real.** ~4 meses (mayo-agosto 2026), predominantemente
   alcista o lateral según el activo. Ningún hallazgo de este documento se ha probado contra
   un régimen bajista sostenido.
2. **Confusión modelo × tiempo, sistemática.** El modelo activo cambió una vez
   (haiku→grok, 2026-06-20) y mimo-shadow arrancó el mismo día — toda comparación
   "modelo A vs modelo B" en este documento (§6.1, §6.2) está parcialmente explicada por
   "cuándo operó cada uno", no solo por la calidad del modelo. Señalado explícitamente en
   cada tabla donde aplica, no una sola vez al final.
3. **n pequeño en casi todos los cortes finos.** Los splits interesantes (extreme
   extension_risk n=8, sonnet n=2-5, MIRROR_ESPEJO n=5, cooldown blocked n=3) son
   sugerentes, no concluyentes.
4. **`ret_3m` insuficiente.** Solo picks de mayo-principios de junio tienen ret_3m maduro.
   Ninguna tabla de este documento usa horizonte a 3 meses por esa razón.
5. **Las reglas shadow (whipsaw, cooldown, followthrough) se leen sobre los mismos datos que
   las generan** — mismo riesgo de sobreajuste que el resto del proyecto ya reconoce
   explícitamente en su criterio de promoción (~100-150 eventos independientes, 2+
   regímenes, validación fuera de muestra — ninguna regla shadow de este documento lo
   cumple todavía).
6. **El hallazgo de §5.1 (100% de cierres mecánicos) es descriptivo, no dice si es bueno o
   malo** — solo que la arquitectura permite juicio cualitativo y en la práctica nunca se ha
   usado. No implica que debiera usarse más; podría ser evidencia de que la disciplina
   mecánica es exactamente lo que evita el sesgo de "aguantar una posición perdedora por
   apego a la tesis".
7. **§5.4 — mismo riesgo de eventos correlacionados que en el resto del documento.** Muchas
   filas del Apéndice B son el mismo evento de mercado contado varias veces (mismo ticker,
   misma fecha de entrada, distinta cartera/modelo — ej. NBIS, SE, CVE aparecen en 2-3
   carteras simultáneamente para el mismo movimiento de precio real). Los agregados de §5.4
   (media de 9.64pp, 34%, 39%, 30%) **no están deduplicados por evento único** — a diferencia
   de la metodología de §6.1, que sí colapsa duplicados. Se decidió así a propósito porque
   aquí el objeto de estudio es "qué le pasó a cada operación real del sistema", no "cuántos
   eventos de mercado independientes hay" — pero el asesor debe saber que el n real de
   eventos *independientes* detrás de §5.4 es menor que el n de filas.
8. **Precio de cierre a cierre, sin intradía, con dividendos ajustados (`auto_adjust=True`
   de yfinance).** `entry_price`/`close_price` del propio sistema son el precio de cierre
   real de la sesión de entrada/salida (no ajustado por dividendos, tal como los registra
   `paper_trading.py`); las columnas nuevas de §5.4/Apéndice B (máx./mín. durante la
   tenencia, retornos post-cierre) se calcularon sobre una serie descargada aparte con
   ajuste por dividendos activado — para la inmensa mayoría de tickers de este universo
   (small caps sin dividendo, o con dividendo pequeño) la diferencia es despreciable, pero
   no se ha verificado caso por caso. No se usó ningún dato intradía — el "máximo durante la
   tenencia" es el máximo de los cierres diarios, no el máximo intradía real, así que es una
   cota inferior del recorrido real disponible.
9. **§5.5/Apéndice C — reconstrucción, no captura en vivo.** Koncorde/RSI/MACD/ATR/Flow
   Score/Early Flow Score de §5.5 no se guardaron en el momento real de cada operación (esa
   captura solo existe desde 2026-08-20) — se recalcularon hoy con datos históricos, mismo
   principio "sin look-ahead" ya usado y verificado en otras reconstrucciones del proyecto
   (`extension_risk_reconstructed.jsonl`), y verificado puntualmente contra un valor real de
   producción (PLTR 2026-08-28). No se ha verificado punto a punto para los 68 tickers — solo
   ese caso y la coherencia interna (Mirror Espejo con Flow Score negativo en el 100% de sus
   entradas, consistente con su diseño documentado). `EQR` (2 operaciones) queda sin datos —
   Yahoo Finance solo devuelve 15 sesiones recientes para ese ticker en el momento de escribir
   esto.

---

## 10. Preguntas concretas al asesor

1. **§5.1** — el sistema permite a la IA decidir EXIT por juicio propio, y en 114 cierres
   observados nunca lo ha hecho por una razón distinta al suelo numérico de PCS/rot_score.
   ¿Es esto evidencia de que la capa de "juicio cualitativo" no aporta nada y se podría
   simplificar a una regla puramente mecánica sin pérdida real? ¿O el valor de esa capa está
   en decisiones que no vemos aquí (los HOLD correctos, no los EXIT)?
2. **§5.2** — con solo 3/38 casos identificados como "whipsaw de precio plano" pero un caso
   adicional real y reciente (FCX, +25.57% cerrado por 0.5 puntos de PCS y reabierto al día
   siguiente) que el script automático todavía no ha capturado, ¿qué diseño de "segunda
   lectura antes de cerrar" recomendarías que no penalice los 35 casos de deterioro real?
   (ej. exigir 2 lecturas consecutivas por debajo del suelo, excluir el componente
   `B_theme_flow` del cálculo del suelo, ventana de gracia de N días)
3. **§5.4 — la más importante de este documento.** Con precios reales operación por
   operación: 34% de los cierres dieron atrás más de 10pp de una ganancia intermedia real, y
   39% de los cierres (con 1m ya maduro contable) vieron un rebote >8% en el mes siguiente a
   la salida, frente a solo 30% que siguió cayendo. ¿Esta evidencia apunta más a "cambiar
   *cuándo* se sale" (ej. trailing stop desde el máximo, como ya usa MIRROR_ESPEJO con un 5%)
   que a "cambiar *qué* se selecciona"? Dado que el sistema ya tiene dos ejemplos funcionando
   de salida por trailing stop (MIRROR_ESPEJO 5%, CAVA_MACRO 25% como cortacircuito, ninguno
   disparado nunca), ¿trasladarías esa mecánica —en vez del suelo de PCS— a HIGH_CONVICTION/
   CFL/EARLY_ROTATION/MACRO_THEMATIC, o conviven mal con el propio objeto de esas carteras
   (que es "acompañar mientras dure la confirmación de flujo", no "maximizar cada trade")?
4. **§5.5** — MACD alcista y Flow Score "Líder" en el momento de la entrada correlacionan
   con *peor* resultado (-5.10% y -4.10%) que MACD bajista/Flow Score "Débil" (-0.10% y
   -1.10%), mientras que `konc_w_state` alcista sí correlaciona con mejor resultado en la
   dirección esperada. ¿Es plausible que el sistema esté sistemáticamente comprando momentum
   ya maduro (dos señales de "fuerza ya confirmada" que resultan malas, frente a una señal de
   "estructura de fondo" que sí funciona)? Si la lectura es correcta, ¿usarías `konc_w_state`
   como filtro de entrada adicional (no solo el PCS) y evitarías activamente entrar cuando
   Flow Score ya está en "Líder"? Ten en cuenta el mismo problema de n pequeño y de
   correlación sin causalidad que el resto del documento — no se ha corregido por múltiples
   comparaciones (van 4 cruces en §4.1/§5.5 solos).
5. **§6.1/§6.2** — la comparación entre modelos está sistemáticamente confundida con el
   periodo en que cada uno operó. ¿Cómo diseñarías un cruce fecha-a-fecha usando
   MIMO_SHADOW (que corre en paralelo al modelo activo sobre el mismo universo, mismo día)
   para aislar el efecto del modelo del efecto del régimen? Concretamente: para cada fecha
   en que ambos seleccionaron algo, ¿comparar directamente sus retornos del mismo día
   controla lo suficiente, o el universo de candidatos que ve cada uno ya difiere lo
   bastante como para invalidar la comparación?
6. **§6.2** — la diferencia de 6.7pp en ret_1m entre picks de llamadas con
   `hard_rule_violations=0` vs `>0` es grande pero con el mismo problema de confusión
   temporal que la pregunta 5. Si se pudiera aislar el efecto, ¿tendría sentido conceptual
   que la limpieza formal de una respuesta (seguir las reglas de estilo/formato) correlacione
   con la calidad de la selección subyacente? ¿O es más probable que sea una coincidencia de
   qué modelo estaba activo cuándo?
7. **§4.1** — extension_risk "extreme" (n=8) sigue siendo claramente peor, pero
   low/medium/high no forman una escalera limpia incluso con n=167 (más del doble que la
   primera vez que se miró esto). ¿Qué tamaño de muestra pedirías antes de considerar esto
   resuelto (¿"solo extreme importa"?) en vez de seguir abierto?
8. **§6.4** — MIRROR_ESPEJO (n=5, 80% de aciertos, cartera sin PCS, solo entra en un patrón
   Koncorde muy específico) es la muestra más pequeña de todas pero la de mejor pinta. ¿Qué
   harías con una cartera experimental así — dejarla correr más tiempo sin tocarla, ampliar
   su universo de entrada (hoy solo mira ~194 tickers de Koncorde, no los 91-128 candidatos
   PCS), o es demasiado pronto para cualquier decisión?
9. **General** — dado el historial de hipótesis descartadas (Sección 7) y el hallazgo
   recurrente de que casi ninguna señal individual predice retorno de forma limpia, ¿el
   problema de fondo es de *señales* (ninguna variable individual es suficiente) o de
   *composición* (las señales sí aportan algo pero el PCS las combina mal)? ¿Cómo
   distinguirías una cosa de la otra con los datos que ya existen, sin construir nada nuevo?

---

## 11. Apéndice A — ficheros fuente y reproducibilidad

Todos los números de este documento salen de datos reales del repositorio a fecha
2026-08-30, sin modificar ni recalcular nada retroactivamente salvo donde se indica
explícitamente (extension_risk reconstruido, sin look-ahead).

| Fichero | Contenido | Usado en |
|---|---|---|
| `docs/data/shadow_picks.jsonl` | 298 filas crudas, todos los picks de todos los modelos/carteras (salvo CAVA/Mirror, que no pasan por aquí) | §4, §5, §6.1 |
| `docs/data/ai_picks.json` | Posiciones abiertas + historial de cierres, las 8 carteras | §2, §5.1, §5.2, §6.4 |
| `docs/data/ai_model_test_summary.jsonl` | 441 llamadas, quality_score/hard_rule_violations/coste por llamada | §6.2 |
| `docs/data/extension_risk_reconstructed.jsonl` | 232 filas, reconstruido sin look-ahead | §4.1 |
| `docs/data/pcs_floor_whipsaw_shadow.jsonl` | 38 clasificaciones de cierres por suelo de PCS | §5.2 |
| `docs/data/cfl_reentry_cooldown_shadow.jsonl` | 23 filas, shadow-only | §5.3 |
| `docs/data/cfl_followthrough_shadow.jsonl` | 3 filas, shadow-only | §5.3 |
| `docs/data/baseline_comparison.json` | Comparativa vs. baselines mecánicas (top-PCS/rot/ret_4w), regenerado hoy con `py -3 scripts/compare_vs_baselines.py --save-cache` | contexto adicional no citado en detalle arriba |
| `docs/data/ai_candidates.json` | Snapshot del universo actual (132 candidatos, 126 elegibles) | §1 |
| `scripts/ai_shared.py` | HARD_RULES, texto literal | §3 |
| Precio real vía `yfinance` (69 tickers, 2026-04-15→2026-08-30, `auto_adjust=True`) — descargado hoy para este documento, no persistido en el repo | Máx./mín. durante tenencia + retorno post-cierre a 1sem/1m/máx. | §5.4, Apéndice B |
| `research/trade_review_2026-08/trade_review_signals.csv` — **el documento con Koncorde (azul + línea roja)/RSI/MACD/Flow Score por ticker y día**, 3.697 filas, ábrelo en Excel/Sheets. Soporte: `ohlcv_long_history.json` (68 tickers, 2022-06→hoy), `koncorde_reconstructed_raw.json`, `reconstruct_flow_macd.js`, `README.md` (esquema de columnas, incluye qué falta: verde y la línea ocre sin suavizar) | Koncorde D/3D/W, RSI, MACD, ATR%, Flow Score, Early Flow Score — reconstruidos con el código real de producción (`scripts/koncorde_calculator.py`, `shared/quote-lib.js`, `shared/flow-score.js`) | §5.5, Apéndice C |

**Metodología de limpieza aplicada** (idéntica a `ASESOR_EXTERNO_CFL_DIAGNOSTICO.md` §2,
extendida a todas las carteras): dedup por (modelo, ticker, portfolio, fecha, pcs);
exclusión del bloque zombi de 9 posiciones de mayo cerradas de golpe el 2026-06-10 (sin vía
de salida disponible en su momento, no reflejan decisión del modelo).

Nada de este análisis ha modificado ningún dato del sistema. `pcs_floor_whipsaw_shadow.jsonl`,
`cfl_reentry_cooldown_shadow.jsonl` y `cfl_followthrough_shadow.jsonl` son shadow-only por
diseño — no han cerrado ni bloqueado ninguna posición real.

---

## 12. Apéndice B — las 147 operaciones reales, con precios de mercado

Una fila por operación real (posición cerrada o abierta) en cada una de las 8 carteras, tal
como está registrada en `docs/data/ai_picks.json` a fecha 2026-08-30, cruzada con precio
real de Yahoo Finance. `REJECTED_HIGH_SCORE` no aparece — es cartera de control y nunca ha
tenido una posición real.

**Cómo leer las columnas:** *Máx./Mín. tenencia* = el mayor/menor precio que alcanzó el
ticker entre la fecha de entrada y la de salida (o hasta hoy si sigue abierta), expresado
como % sobre el precio de entrada — es el recorrido que hubo disponible, se haya capturado o
no. *+1sem/+1m post-salida* = retorno del precio exactamente 5 y 21 sesiones después del
cierre, sobre el precio de cierre — negativo confirma que la salida evitó más caída,
positivo indica que el precio se recuperó después de vender. *Máx. 1m post-salida* = el
mayor precio alcanzado en cualquier momento de esas 21 sesiones, no solo el valor puntual al
final — la cifra que mejor captura "cuánto rebote hubo, aunque no llegara a durar todo el
mes". Filas con `*` junto al retorno son posiciones **todavía abiertas** — ese retorno es
no-realizado (marca a precio de hoy), y las tres últimas columnas no aplican.

#### HIGH_CONVICTION (9 operaciones — 8 cerradas, 1 abierta)

| Ticker | Modelo | Entrada | Entry $ | PCS | Salida | Close $ | Motivo | Ret. | Máx. tenencia | Mín. tenencia | +1sem post-salida | +1m post-salida | Máx. 1m post-salida |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| CORZ | haiku | 2026-05-08 | 22.92 | — | 2026-06-10 | 27.01 | PCS 66.5<82 | +17.84% | +26.75% | -0.57% | +5.07% | -15.92% | +7.96% |
| NBIS | haiku | 2026-05-08 | 177.05 | — | 2026-07-02 | 229.18 | PCS 72.2<82 | +29.44% | +61.93% | +0.00% | -4.16% | -7.24% | -3.58% |
| CVE | grok | 2026-05-15 | 30.15 | 85.0 | 2026-06-10 | 27.65 | PCS 60.2<82 | -8.29% | +4.89% | -9.07% | -7.41% | -0.14% | +2.43% |
| OXY | grok | 2026-05-19 | 59.70 | 89.5 | 2026-06-10 | 56.55 | PCS 52.2<82 | -5.28% | +1.21% | -5.71% | -6.21% | -3.08% | +0.97% |
| QQQ | grok | 2026-05-19 | 705.88 | 85.5 | 2026-06-11 | 693.69 | PCS 61.8<82 | -1.73% | +5.59% | -1.83% | +6.65% | +3.75% | +7.13% |
| VAL | grok | 2026-05-20 | 111.05 | 89.5 | 2026-06-10 | 87.49 | PCS 34.0<82 | -21.22% | -1.31% | -21.22% | -5.07% | -9.05% | +2.81% |
| VLE.TO | grok | 2026-05-20 | 12.91 | 86.0 | 2026-06-10 | 11.05 | PCS 34.0<82 | -14.41% | -0.00% | -16.42% | +1.27% | -2.62% | +6.52% |
| LLY | grok | 2026-08-11 | 1231.94 | 86.8 | 2026-08-28 | 1176.10 | PCS 59.5<62 | -4.53% | +3.93% | -4.65% | — | — | -0.13% |
| HIMS | grok | 2026-08-26 | 31.75 | 86.8 | **abierta** | 28.84 | (4d) | -9.17%* | -0.28% | -9.17% | — | — | — |

#### CONFIRMED_FLOW_LEADERS (28 operaciones — 26 cerradas, 2 abiertas)

| Ticker | Modelo | Entrada | Entry $ | PCS | Salida | Close $ | Motivo | Ret. | Máx. tenencia | Mín. tenencia | +1sem post-salida | +1m post-salida | Máx. 1m post-salida |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| NVDA | haiku | 2026-05-08 | 214.95 | — | 2026-06-10 | 208.19 | PCS 65.5<75 | -3.14% | +9.54% | -6.76% | -1.70% | -2.24% | +2.05% |
| MSTR | haiku | 2026-05-08 | 187.59 | — | 2026-06-10 | 117.02 | PCS 27.5<75 | -37.62% | +4.45% | -38.51% | -0.39% | -21.30% | +12.07% |
| COIN | grok | 2026-05-09 | 216.60 | 83.5 | 2026-06-10 | 155.50 | PCS 27.5<75 | -28.21% | +0.00% | -29.64% | +6.06% | +1.20% | +9.08% |
| KOS | grok | 2026-05-15 | 2.93 | 82.0 | 2026-06-10 | 2.79 | PCS 59.8<75 | -4.78% | +10.24% | -8.87% | -10.39% | -12.54% | +6.81% |
| WCP.TO | grok | 2026-05-15 | 16.68 | 80.5 | 2026-06-16 | 16.18 | PCS 40.8<75 | -3.00% | +2.08% | -5.77% | -3.72% | -3.57% | -2.18% |
| SU | grok | 2026-05-16 | 68.29 | 80.5 | 2026-06-10 | 61.20 | PCS 42.2<75 | -10.38% | +1.44% | -10.38% | -8.04% | +0.11% | +1.45% |
| ASPI | grok | 2026-05-27 | 6.93 | 78.5 | 2026-06-10 | 6.40 | PCS 51.2<75 | -7.65% | +20.20% | -15.58% | +4.37% | -28.28% | +13.75% |
| OSCR | grok | 2026-05-28 | 21.99 | 81.8 | 2026-07-17 | 28.86 | PCS 74.8<75 | +31.24% | +46.34% | -6.78% | -2.32% | +9.32% | +13.51% |
| EOSE | grok | 2026-05-29 | 8.99 | 83.0 | 2026-06-10 | 6.26 | PCS 32.5<75 | -30.37% | +4.78% | -32.48% | +21.41% | -30.51% | +22.20% |
| SASK.V | grok | 2026-05-30 | 1.17 | 83.5 | 2026-06-10 | 0.91 | PCS 33.8<75 | -22.22% | +2.56% | -23.08% | +19.78% | +21.98% | +35.16% |
| RCAT | grok | 2026-05-30 | 14.50 | 83.0 | 2026-06-10 | 11.49 | rot_score≤2 | -20.76% | +3.10% | -24.86% | -2.52% | -27.07% | +4.53% |
| BBAR | grok | 2026-06-03 | 18.87 | 79.0 | 2026-06-26 | 19.06 | PCS 58.0<75 | +1.01% | +15.13% | -9.43% | +8.48% | -1.55% | +10.57% |
| LOMA | grok | 2026-06-13 | 12.55 | 83.5 | 2026-06-25 | 11.44 | PCS 41.8<75 | -8.84% | -2.31% | -8.84% | +2.80% | +1.57% | +6.56% |
| GGAL | grok | 2026-06-13 | 55.16 | 81.8 | 2026-06-26 | 49.42 | PCS 49<75 | -10.41% | +1.97% | -11.18% | +7.05% | -0.68% | +8.49% |
| QQQ | grok | 2026-06-16 | 744.00 | 83.0 | 2026-06-24 | 713.65 | PCS 57<75 | -4.08% | -0.56% | -4.49% | +1.61% | -4.12% | +3.19% |
| TDOC | grok | 2026-06-16 | 7.46 | 81.0 | 2026-07-31 | 6.58 | PCS 58.5<62 | -11.80% | +30.29% | -11.80% | +8.36% | — | +8.36% |
| HIMS | grok | 2026-06-17 | 31.47 | 80.0 | 2026-07-22 | 32.73 | PCS 56.2<62 | +4.00% | +21.64% | +0.67% | -23.62% | -2.66% | +0.03% |
| ASPI | grok | 2026-06-20 | 7.18 | 79.8 | 2026-06-26 | 6.35 | PCS 62.5<75 | -11.56% | +1.39% | -14.07% | -12.91% | -40.55% | -2.05% |
| SASK.V | grok | 2026-06-20 | 1.11 | 80.5 | 2026-06-26 | 1.00 | rot_score≤2 | -9.91% | -1.80% | -9.91% | +6.00% | -2.00% | +12.00% |
| URI | grok | 2026-07-01 | 1132.89 | 80.5 | 2026-07-08 | 1056.02 | PCS 72.8<75 | -6.79% | -2.03% | -6.95% | -1.00% | +9.91% | +9.91% |
| ROOT | grok | 2026-07-01 | 55.92 | 79.0 | 2026-07-16 | 55.69 | PCS 60.5<62 | -0.41% | +18.40% | -0.41% | +3.32% | -7.61% | +10.25% |
| AFM.V | grok | 2026-07-04 | 1.52 | 80.8 | 2026-07-07 | 1.44 | PCS 61.2<62 | -5.26% | -4.61% | -5.26% | +0.00% | +9.72% | +9.72% |
| SE | grok | 2026-07-07 | 105.00 | 78.5 | 2026-07-08 | 104.23 | PCS 62.5<62 | -0.73% | +0.30% | -0.73% | +6.84% | +6.50% | +10.25% |
| URI | grok | 2026-07-25 | 1139.71 | 82.2 | 2026-07-26 | 1141.59 | PCS 70.2<75 | +0.16% | — | — | -2.42% | -7.75% | +2.03% |
| TMO | grok | 2026-07-25 | 568.26 | 80.5 | **abierta** | 622.18 | (36d) | +9.49%* | +11.52% | -1.54% | — | — | — |
| NBIS | grok | 2026-08-05 | 225.74 | 83.5 | 2026-08-07 | 189.88 | PCS 57<75 | -15.89% | -2.99% | -16.73% | +46.24% | — | +46.24% |
| PLTR | grok | 2026-08-07 | 155.92 | 80.5 | 2026-08-21 | 173.96 | PCS 70.5<75 | +11.57% | +15.41% | +9.70% | +7.09% | — | +7.09% |
| SEDANA.ST | grok | 2026-08-12 | 11.14 | 85.2 | **abierta** | 13.62 | (18d) | +22.26%* | +22.26% | -7.54% | — | — | — |

#### EARLY_ROTATION (6 operaciones — 6 cerradas, 0 abiertas)

| Ticker | Modelo | Entrada | Entry $ | PCS | Salida | Close $ | Motivo | Ret. | Máx. tenencia | Mín. tenencia | +1sem post-salida | +1m post-salida | Máx. 1m post-salida |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| TSLA | grok | 2026-05-09 | 445.00 | 75.0 | 2026-06-10 | 396.68 | PCS 54.2<68 | -10.86% | +0.06% | -14.25% | -0.08% | -0.48% | +7.21% |
| ASTS | grok | 2026-05-23 | 105.86 | 69.8 | 2026-06-10 | 88.71 | PCS 55.8<68 | -16.20% | +25.72% | -17.51% | -3.70% | -23.82% | +9.98% |
| MLX.AX | grok | 2026-05-23 | 1.74 | 69.5 | 2026-06-10 | 1.51 | PCS 49.8<68 | -13.22% | -0.29% | -14.94% | -1.32% | -13.91% | -0.33% |
| CVE | grok | 2026-07-22 | 28.79 | 75.2 | 2026-07-29 | 27.66 | PCS 67<68 | -3.92% | +3.23% | -3.92% | +0.25% | +14.64% | +19.05% |
| TOU.TO | grok | 2026-07-23 | 64.78 | 76.0 | 2026-07-31 | 62.30 | PCS 60.5<68 | -3.83% | +0.59% | -4.43% | -3.45% | — | +0.42% |
| CVE | grok | 2026-07-30 | 29.07 | 71.5 | 2026-07-31 | 30.32 | PCS 66.5<68 | +4.30% | +4.30% | +3.85% | -6.83% | — | +8.61% |

#### MACRO_THEMATIC_BENEFICIARIES (2 operaciones — 2 cerradas, 0 abiertas)

| Ticker | Modelo | Entrada | Entry $ | PCS | Salida | Close $ | Motivo | Ret. | Máx. tenencia | Mín. tenencia | +1sem post-salida | +1m post-salida | Máx. 1m post-salida |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| SE | grok | 2026-07-15 | 109.29 | 66.8 | 2026-07-16 | 111.36 | PCS 59.8<62 | +1.89% | +1.89% | -2.81% | -10.65% | +9.50% | +18.09% |
| NVDA | grok | 2026-07-15 | 211.80 | 66.8 | 2026-07-16 | 212.50 | PCS 58.8<62 | +0.33% | +0.33% | -2.08% | -1.76% | +5.96% | +6.02% |

#### MIMO_SHADOW (70 operaciones — 52 cerradas, 18 abiertas)

| Ticker | Modelo | Entrada | Entry $ | PCS | Salida | Close $ | Motivo | Ret. | Máx. tenencia | Mín. tenencia | +1sem post-salida | +1m post-salida | Máx. 1m post-salida |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| SASK.V | mimo | 2026-06-20 | 1.11 | 80.5 | 2026-07-02 | 0.99 | PCS 60.5<62 | -10.81% | -1.80% | -10.81% | +8.08% | -1.01% | +13.13% |
| GS | mimo | 2026-06-20 | 1096.56 | 74.0 | 2026-07-06 | 1021.00 | PCS 61.5<62 | -6.89% | +0.89% | -7.77% | +2.44% | +3.13% | +12.84% |
| NBIS | mimo | 2026-06-20 | 286.69 | 86.0 | 2026-07-08 | 195.19 | rot_score≤2 | -31.92% | -1.07% | -31.92% | +2.21% | -2.72% | +15.65% |
| CAT | mimo | 2026-06-20 | 985.82 | 74.2 | 2026-07-14 | 931.47 | PCS 60.5<62 | -5.51% | +7.82% | -5.69% | -4.46% | -8.15% | +0.02% |
| AMD | mimo | 2026-06-20 | 537.37 | 83.0 | 2026-07-18 | 495.76 | PCS 62.8<68 | -7.74% | +8.10% | -7.74% | -0.16% | -2.29% | +11.41% |
| AFM.V | mimo | 2026-06-22 | 1.50 | 69.8 | 2026-07-03 | 1.49 | PCS 61.8<62 | -0.67% | +1.33% | -5.33% | -7.38% | +0.00% | +2.01% |
| NUE | mimo | 2026-06-23 | 244.93 | 78.2 | 2026-06-27 | 239.78 | PCS 63.8<68 | -2.10% | +1.37% | -2.40% | -5.15% | +6.77% | +10.78% |
| HUM | mimo | 2026-06-23 | 360.72 | 71.0 | 2026-07-15 | 406.77 | PCS 65.8<68 | +12.77% | +13.50% | -0.68% | -2.25% | -5.36% | +0.25% |
| SLS | mimo | 2026-06-23 | 8.53 | 73.8 | 2026-08-04 | 11.22 | PCS 67.8<75 | +31.54% | +81.13% | +6.33% | -1.52% | — | +37.79% |
| SE | mimo | 2026-06-25 | 92.75 | 69.5 | 2026-06-25 | 92.75 | PCS 67.5<75 | +0.00% | -4.03% | -4.03% | +11.37% | +12.55% | +20.06% |
| UNH | mimo | 2026-06-26 | 415.53 | 74.5 | 2026-07-28 | 417.64 | PCS 66.8<75 | +0.51% | +5.01% | +0.02% | -2.42% | -3.98% | +2.67% |
| CVS | mimo | 2026-06-26 | 104.66 | 71.5 | 2026-08-04 | 105.37 | PCS 63.8<75 | +0.68% | +5.03% | -3.07% | -11.27% | — | -0.90% |
| EQR | mimo | 2026-06-27 | 68.38 | 70.0 | 2026-07-09 | 68.31 | PCS 50.2<62 | -0.10% | — | — | -2.36% | — | +1.01% |
| ABBV | mimo | 2026-06-27 | 253.35 | 68.2 | 2026-08-04 | 245.10 | PCS 59.8<62 | -3.26% | +3.93% | -4.07% | +2.04% | — | +8.51% |
| TTI | mimo | 2026-06-29 | 10.87 | 76.8 | 2026-07-03 | 9.30 | rot_score≤2 | -14.44% | +4.69% | -14.44% | -1.29% | -6.77% | +1.94% |
| TDOC | mimo | 2026-06-29 | 8.39 | 79.5 | 2026-07-31 | 6.58 | PCS 58.5<62 | -21.57% | +15.85% | -21.57% | +8.36% | — | +8.36% |
| SE | mimo | 2026-07-01 | 95.83 | 74.2 | 2026-07-03 | 103.30 | PCS 65.8<75 | +7.80% | +7.80% | +6.78% | +7.12% | +7.88% | +7.88% |
| HIMS | mimo | 2026-07-01 | 34.67 | 84.5 | 2026-07-22 | 32.73 | rot_score≤2 | -5.60% | +10.41% | -8.62% | -23.62% | -2.66% | +0.03% |
| ROOT | mimo | 2026-07-03 | 61.73 | 74.5 | 2026-07-16 | 55.69 | rot_score≤2 | -9.78% | +7.26% | -9.78% | +3.32% | -7.61% | +10.25% |
| SE | mimo | 2026-07-07 | 105.00 | 78.5 | 2026-07-14 | 110.66 | PCS 59.8<62 | +5.39% | +5.85% | -0.73% | -3.98% | +15.77% | +18.84% |
| LLY | mimo | 2026-07-08 | 1235.56 | 78.2 | 2026-07-15 | 1152.54 | PCS 64.2<68 | -6.72% | -1.65% | -6.85% | +0.76% | +4.75% | +6.74% |
| OSCR | mimo | 2026-07-09 | 30.81 | 79.2 | 2026-08-04 | 30.74 | PCS 67.5<75 | -0.23% | +2.56% | -8.50% | -9.01% | — | +6.57% |
| URI | mimo | 2026-07-11 | 1095.55 | 72.2 | 2026-07-14 | 1085.34 | PCS 63.8<68 | -0.93% | -1.10% | -2.88% | -6.78% | +4.05% | +6.96% |
| SASK.V | mimo | 2026-07-11 | 1.11 | 83.0 | 2026-07-16 | 1.05 | PCS 53.5<75 | -5.41% | +0.90% | -11.71% | -0.00% | +7.62% | +8.57% |
| EQR | mimo | 2026-07-17 | 70.00 | 73.8 | 2026-07-22 | 68.29 | PCS 63.0<75 | -2.44% | -1.43% | -2.44% | -3.40% | — | +0.00% |
| LLY | mimo | 2026-07-18 | 1179.11 | 80.5 | 2026-08-04 | 1121.36 | PCS 60.2<62 | -4.90% | +3.38% | -5.51% | +8.20% | — | +14.18% |
| HUM | mimo | 2026-07-20 | 400.00 | 80.2 | 2026-08-04 | 374.50 | PCS 67.8<75 | -6.37% | +1.08% | -9.46% | -0.45% | — | +4.84% |
| CVE | mimo | 2026-07-23 | 28.99 | 75.2 | 2026-07-29 | 27.66 | PCS 67.0<75 | -4.59% | +2.52% | -4.59% | +0.25% | +14.64% | +19.05% |
| JNJ | mimo | 2026-07-24 | 259.27 | 81.0 | 2026-08-01 | 256.35 | PCS 67.8<75 | -1.13% | +2.37% | -1.81% | +1.63% | — | +6.55% |
| NUE | mimo | 2026-07-24 | 241.15 | 75.8 | 2026-08-21 | 240.48 | PCS 53.8<62 | -0.28% | +13.93% | -0.28% | +4.17% | — | +5.12% |
| MRK | mimo | 2026-07-24 | 130.48 | 83.2 | **abierta** | 148.35 | (37d) | +13.70%* | +19.90% | -2.08% | — | — | — |
| TOU.TO | mimo | 2026-07-25 | 65.16 | 72.0 | 2026-07-31 | 62.30 | PCS 60.5<62 | -4.39% | -1.07% | -4.99% | -3.45% | — | +0.42% |
| NBIS | mimo | 2026-07-26 | 220.97 | 70.8 | 2026-07-28 | 187.88 | PCS 55.2<62 | -14.97% | -14.97% | -23.21% | +20.15% | +13.87% | +47.80% |
| WCP.TO | mimo | 2026-07-26 | 16.70 | 75.5 | 2026-07-29 | 15.60 | PCS 62.5<75 | -6.59% | -4.43% | -6.93% | +4.10% | +14.42% | +16.47% |
| YPF | mimo | 2026-07-28 | 50.90 | 73.5 | 2026-08-06 | 48.67 | PCS 59.0<62 | -4.38% | +3.22% | -4.38% | +1.60% | — | +8.28% |
| SYK | mimo | 2026-07-29 | 346.60 | 74.5 | 2026-08-01 | 325.70 | PCS 66.5<75 | -6.03% | +1.63% | -6.03% | +6.17% | — | +6.89% |
| TECK | mimo | 2026-07-31 | 62.49 | 69.8 | 2026-08-01 | 60.24 | PCS 59.0<62 | -3.60% | -3.60% | -3.60% | +11.01% | — | +18.89% |
| III.L | mimo | 2026-07-31 | 2847.00 | 77.8 | 2026-08-05 | 2886.00 | PCS 61.8<75 | +1.37% | +2.63% | +0.60% | -2.53% | — | +1.66% |
| SEDANA.ST | mimo | 2026-08-01 | 9.80 | 70.5 | 2026-08-04 | 10.06 | PCS 60.5<62 | +2.65% | +2.65% | +2.45% | +10.74% | — | +35.39% |
| PAM | mimo | 2026-08-02 | 88.32 | 70.2 | 2026-08-05 | 84.79 | PCS 54.8<62 | -4.00% | -1.81% | -5.08% | -6.35% | — | -1.13% |
| WCP.TO | mimo | 2026-08-03 | 16.54 | 68.5 | 2026-08-06 | 15.85 | PCS 55.5<62 | -4.17% | -1.63% | -4.17% | +6.56% | — | +14.64% |
| SE | mimo | 2026-08-04 | 111.15 | 72.2 | **abierta** | 119.36 | (26d) | +7.39%* | +18.32% | -0.13% | — | — | — |
| TMO | mimo | 2026-08-04 | 574.03 | 70.8 | **abierta** | 622.18 | (26d) | +8.39%* | +10.40% | -1.62% | — | — | — |
| NBIS | mimo | 2026-08-05 | 225.74 | 83.5 | 2026-08-07 | 189.88 | PCS 57.0<62 | -15.89% | -2.99% | -16.73% | +46.24% | — | +46.24% |
| NVDA | mimo | 2026-08-05 | 211.94 | 71.5 | 2026-08-11 | 217.55 | PCS 55.5<75 | +2.65% | +5.67% | +2.62% | +1.01% | — | +4.79% |
| TECK | mimo | 2026-08-06 | 66.05 | 71.5 | 2026-08-14 | 63.76 | rot_score≤2 | -3.47% | +1.24% | -3.82% | +8.53% | — | +12.33% |
| DPM.TO | mimo | 2026-08-06 | 56.59 | 70.0 | **abierta** | 64.73 | (24d) | +14.38%* | +23.96% | +2.47% | — | — | — |
| FCX | mimo | 2026-08-07 | 68.18 | 72.8 | 2026-08-26 | 79.91 | PCS 61.5<62 | +17.20% | +17.20% | -2.73% | — | — | -1.14% |
| PLTR | mimo | 2026-08-07 | 155.92 | 80.5 | **abierta** | 186.29 | (23d) | +19.48%* | +19.48% | +9.70% | — | — | — |
| OXY | mimo | 2026-08-11 | 58.65 | 79.5 | 2026-08-15 | 58.36 | rot_score≤2 | -0.49% | +0.70% | -1.62% | +3.00% | — | +5.41% |
| KTOS | mimo | 2026-08-11 | 62.42 | 74.5 | 2026-08-21 | 56.18 | PCS 58.0<62 | -10.00% | +3.46% | -10.00% | -7.44% | — | +1.76% |
| AFM.V | mimo | 2026-08-11 | 1.66 | 74.5 | 2026-08-21 | 1.49 | PCS 55.5<62 | -10.24% | -7.23% | -12.65% | +2.01% | — | +4.03% |
| WCP.TO | mimo | 2026-08-11 | 16.79 | 82.0 | **abierta** | 17.85 | (19d) | +6.31%* | +8.22% | +0.60% | — | — | — |
| SYK | mimo | 2026-08-12 | 348.15 | 83.0 | 2026-08-19 | 331.37 | rot_score≤2 | -4.82% | -0.27% | -4.82% | -0.51% | — | +2.60% |
| SEDANA.ST | mimo | 2026-08-12 | 11.14 | 85.2 | **abierta** | 13.62 | (18d) | +22.26%* | +22.26% | -7.54% | — | — | — |
| NBIS | mimo | 2026-08-14 | 255.04 | 83.0 | 2026-08-21 | 220.11 | PCS 57.8<62 | -13.70% | +8.88% | -14.08% | -4.97% | — | +0.85% |
| SLS | mimo | 2026-08-14 | 12.36 | 87.0 | **abierta** | 13.21 | (16d) | +6.88%* | +25.08% | +3.40% | — | — | — |
| III.L | mimo | 2026-08-15 | 2785.00 | 80.2 | 2026-08-21 | 2793.00 | PCS 62.8<68 | +0.29% | +3.81% | +0.11% | — | — | +5.05% |
| OSCR | mimo | 2026-08-21 | 31.57 | 81.2 | 2026-08-29 | 30.47 | PCS 75.5<75 | -3.48% | +1.49% | -4.81% | — | — | — |
| TECK | mimo | 2026-08-21 | 66.16 | 74.2 | **abierta** | 69.34 | (9d) | +4.81%* | +8.25% | +4.59% | — | — | — |
| CRON | mimo | 2026-08-22 | 3.31 | 75.2 | **abierta** | 3.38 | (8d) | +2.11%* | +7.25% | +2.11% | — | — | — |
| EXK | mimo | 2026-08-23 | 10.62 | 74.0 | **abierta** | 10.76 | (7d) | +1.32%* | +6.40% | +1.32% | — | — | — |
| VRTX | mimo | 2026-08-24 | 548.05 | 78.2 | **abierta** | 541.69 | (6d) | -1.16%* | +0.88% | -1.16% | — | — | — |
| III.L | mimo | 2026-08-25 | 2934.00 | 80.2 | 2026-08-28 | 2834.00 | PCS 67.8<75 | -3.41% | -1.02% | -3.41% | — | — | — |
| CVE | mimo | 2026-08-26 | 30.76 | 80.8 | **abierta** | 31.58 | (4d) | +2.67%* | +3.09% | +2.34% | — | — | — |
| DHR | mimo | 2026-08-27 | 215.36 | 87.5 | **abierta** | 216.07 | (3d) | +0.33%* | +0.33% | +0.15% | — | — | — |
| VLE.TO | mimo | 2026-08-28 | 13.14 | 85.5 | **abierta** | 13.26 | (2d) | +0.91%* | +0.91% | +0.91% | — | — | — |
| TNZ.TO | mimo | 2026-08-28 | 63.29 | 88.5 | **abierta** | 64.64 | (2d) | +2.13%* | +2.13% | +2.13% | — | — | — |
| FCX | mimo | 2026-08-28 | 78.42 | 68.5 | **abierta** | 76.45 | (2d) | -2.51%* | -2.51% | -2.51% | — | — | — |
| HUM | mimo | 2026-08-29 | 392.63 | 88.0 | **abierta** | 385.54 | (1d) | -1.81%* | — | — | — | — | — |

#### CAVA_MACRO (25 operaciones — 15 cerradas, 10 abiertas)

| Ticker | Modelo | Entrada | Entry $ | PCS | Salida | Close $ | Motivo | Ret. | Máx. tenencia | Mín. tenencia | +1sem post-salida | +1m post-salida | Máx. 1m post-salida |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| III.L | cava | 2026-08-03 | 2867.00 | 69.8 | 2026-08-07 | 2886.00 | PCS 60.2<62 | +0.66% | +1.92% | +0.00% | -3.50% | — | +1.66% |
| OSCR | cava | 2026-08-03 | 30.74 | 80.2 | 2026-08-07 | 26.94 | PCS 59.0<62 | -12.36% | -0.00% | -13.66% | +21.60% | — | +21.60% |
| YPF | cava | 2026-08-03 | 51.06 | 76.0 | 2026-08-07 | 49.28 | PCS 53.0<62 | -3.48% | +0.00% | -4.68% | +1.55% | — | +6.93% |
| PAM | cava | 2026-08-03 | 86.72 | 70.2 | 2026-08-07 | 82.48 | PCS 32.0<62 | -4.89% | +0.00% | -5.03% | -4.30% | — | +0.28% |
| KOS | cava | 2026-08-03 | 2.53 | 69.2 | 2026-08-07 | 2.48 | PCS 59.8<62 | -1.98% | -0.00% | -7.11% | +2.42% | — | +21.77% |
| NUE | cava | 2026-08-03 | 261.28 | 62.8 | 2026-08-21 | 240.48 | PCS 53.8<62 | -7.96% | +5.15% | -7.96% | +4.17% | — | +5.12% |
| FCX | cava | 2026-08-03 | 63.64 | 62.2 | 2026-08-26 | 79.91 | PCS 61.5<62 | +25.57% | +25.57% | -0.00% | — | — | -1.14% |
| TMO | cava | 2026-08-03 | 574.03 | 83.5 | **abierta** | 622.18 | (27d) | +8.39%* | +10.40% | -1.62% | — | — | — |
| MRK | cava | 2026-08-03 | 127.77 | 83.2 | **abierta** | 148.35 | (27d) | +16.11%* | +22.45% | -0.00% | — | — | — |
| SLS | cava | 2026-08-03 | 11.22 | 75.8 | **abierta** | 13.21 | (27d) | +17.74%* | +37.79% | -1.60% | — | — | — |
| GS | cava | 2026-08-07 | 1039.61 | 62.0 | 2026-08-11 | 1034.51 | PCS 60.0<62 | -0.49% | +0.00% | -0.50% | +0.58% | — | +2.36% |
| URI | cava | 2026-08-07 | 1162.84 | 73.8 | 2026-08-22 | 1098.51 | PCS 55.8<62 | -5.53% | +0.17% | -5.81% | — | — | -1.36% |
| PLTR | cava | 2026-08-07 | 172.01 | 80.5 | **abierta** | 186.29 | (23d) | +8.30%* | +8.30% | -0.56% | — | — | — |
| SE | cava | 2026-08-07 | 113.43 | 76.2 | **abierta** | 119.36 | (23d) | +5.23%* | +15.94% | +0.00% | — | — | — |
| DHR | cava | 2026-08-07 | 204.76 | 73.0 | **abierta** | 216.07 | (23d) | +5.52%* | +6.88% | -2.53% | — | — | — |
| AWX | cava | 2026-08-11 | 2.86 | 74.2 | 2026-08-22 | 2.67 | PCS 57.8<62 | -6.64% | +0.00% | -6.64% | — | — | +3.75% |
| III.L | cava | 2026-08-21 | 2891.00 | 62.8 | 2026-08-29 | 2834.00 | PCS 59.8<62 | -1.97% | +1.49% | -1.97% | — | — | — |
| TK | cava | 2026-08-22 | 13.24 | 64.5 | 2026-08-25 | 13.36 | PCS 60.5<62 | +0.91% | +0.91% | +0.83% | — | — | +0.00% |
| RIO | cava | 2026-08-22 | 105.30 | 62.5 | 2026-08-25 | 106.81 | PCS 58.5<62 | +1.43% | +1.43% | -0.47% | — | — | +0.00% |
| VIT-B.ST | cava | 2026-08-25 | 257.00 | 69.8 | 2026-08-27 | 276.40 | PCS 58.2<62 | +7.55% | +7.55% | -0.93% | — | — | +0.00% |
| OSCR | cava | 2026-08-25 | 30.93 | 87.2 | **abierta** | 30.47 | (5d) | -1.49%* | +1.00% | -2.85% | — | — | — |
| EOS.AX | cava | 2026-08-26 | 11.24 | 68.5 | 2026-08-28 | 10.23 | PCS 58.5<62 | -8.99% | +0.00% | -10.59% | — | — | -1.76% |
| FCX | cava | 2026-08-27 | 78.42 | 64.5 | **abierta** | 76.45 | (3d) | -2.51%* | +0.00% | -2.51% | — | — | — |
| TK | cava | 2026-08-28 | 13.04 | 65.0 | **abierta** | 13.05 | (2d) | +0.08%* | +0.08% | +0.08% | — | — | — |
| VIT-B.ST | cava | 2026-08-29 | — | 64.5 | **abierta** | 276.40 | (1d) | —* | — | — | — | — | — |

#### MIRROR_ESPEJO (7 operaciones — 5 cerradas, 2 abiertas)

| Ticker | Modelo | Entrada | Entry $ | PCS | Salida | Close $ | Motivo | Ret. | Máx. tenencia | Mín. tenencia | +1sem post-salida | +1m post-salida | Máx. 1m post-salida |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| CORZ | grok(espejo) | 2026-07-31 | 21.81 | — | 2026-08-07 | 21.05 | trailing_stop_5% | -3.48% | +4.68% | -5.00% | -4.13% | — | -0.19% |
| ACMR | grok(espejo) | 2026-07-31 | 78.65 | — | 2026-08-11 | 79.41 | trailing_stop_5% | +0.97% | +6.55% | -0.23% | +6.25% | — | +7.85% |
| CAT | grok(espejo) | 2026-07-31 | 809.14 | — | 2026-08-20 | 816.15 | trailing_stop_5% | +0.87% | +8.96% | +0.70% | +0.10% | — | +1.44% |
| ASM.AS | grok(espejo) | 2026-08-02 | 788.60 | — | 2026-08-18 | 863.20 | trailing_stop_5% | +9.46% | +15.12% | +0.84% | -4.05% | — | -2.41% |
| OSCR | grok(espejo) | 2026-08-08 | 27.90 | — | 2026-08-26 | 30.93 | trailing_stop_5% | +10.86% | +17.42% | -0.82% | — | — | +1.00% |
| MAI.L | grok(espejo) | 2026-08-13 | 67.50 | — | **abierta** | 68.50 | (17d) | +1.48%* | +1.48% | +1.48% | — | — | — |
| UNH | grok(espejo) | 2026-08-15 | 401.73 | — | **abierta** | 392.95 | (15d) | -2.19%* | -0.18% | -4.20% | — | — | — |

**Nota sobre "Motivo":** extraído del texto literal de `close_reason` (el propio modelo lo
escribió, ver §5.1), abreviado a `PCS X<Y` (X = PCS en el momento del cierre, Y = umbral que
se incumplió) o `rot_score≤2`. Cuando el umbral exacto no queda claro en el texto original
del modelo se usa el `pcs_min_entry` de la cartera como referencia. `trailing_stop_5%` es el
único mecanismo no basado en PCS del sistema (MIRROR_ESPEJO). Modelo abreviado: `haiku` =
`anthropic/claude-haiku-4.5`, `grok` = `x-ai/grok-4.3`, `mimo` = `xiaomi/mimo-v2.5-pro`,
`cava` = `cava-engine-1.1.0`, `grok(espejo)` = `x-ai/grok-4.3` con el prompt separado de
Mirror Espejo (§2) — nunca pasa por `shadow_picks.jsonl`, se infiere del diseño documentado
de esa cartera.

---

## 13. Apéndice C — Koncorde D/W, MACD y Flow Score en el momento de entrada y de salida

Mismas 147 operaciones que el Apéndice B (mismo orden — cruzar por ticker+fecha de entrada
para ver retorno y contexto técnico lado a lado), con el contexto técnico reconstruido
descrito en §5.5. `Konc D`/`Konc W` = estado (`Alza`/`Acum.`=acumulación/`Distrib.`=
distribución/`Baja`) + valor del blue entre paréntesis, redondeado. `Flow` = Flow Score
(`computeFlowScore`, mismo cálculo que "Ranking de Setups" en `portfolio.html`). `MACD` = ▲
alcista / ▼ bajista (histograma MACD(12,26,9) ≥ 0 o < 0). REJECTED_HIGH_SCORE no aparece
(cartera de control, sin operaciones reales). "—" = sin dato reconstruido (huecos
documentados en §5.5: EQR sin histórico suficiente, NBIS sin warmup semanal en sus primeras
operaciones).

#### HIGH_CONVICTION

| Ticker | Entrada | Konc D@entr. | Konc W@entr. | Flow@entr. | MACD@entr. | Salida | Konc D@sal. | Konc W@sal. | Flow@sal. | MACD@sal. |
|---|---|---|---|---:|:---:|---|---|---|---:|:---:|
| CORZ | 2026-05-08 | Distrib.(-23) | Alza(+7) | 39.7 | ▲ | 2026-06-10 | Distrib.(-22) | Alza(+17) | -5.1 | ▼ |
| NBIS | 2026-05-08 | Distrib.(-24) | — | 43.5 | ▲ | 2026-07-02 | Distrib.(-23) | — | -35.3 | ▼ |
| CVE | 2026-05-15 | Alza(+14) | Alza(+54) | 33.5 | ▲ | 2026-06-10 | Alza(+4) | Alza(+7) | -4.7 | ▼ |
| OXY | 2026-05-19 | Distrib.(-3) | Alza(+156) | 21.9 | ▲ | 2026-06-10 | Distrib.(-3) | Alza(+50) | -2.1 | ▼ |
| QQQ | 2026-05-19 | Alza(+4) | Alza(+18) | 11.2 | ▼ | 2026-06-11 | Alza(+2) | Alza(+21) | 1.2 | ▼ |
| VAL | 2026-05-20 | Alza(+57) | Alza(+59) | 36.5 | ▲ | 2026-06-10 | Alza(+6) | Distrib.(-15) | -9.8 | ▼ |
| VLE.TO | 2026-05-20 | Distrib.(-35) | Alza(+3) | 5.5 | ▲ | 2026-06-10 | Alza(+39) | Distrib.(-8) | -5.0 | ▲ |
| LLY | 2026-08-11 | Distrib.(-13) | Alza(+0) | 16.7 | ▲ | 2026-08-28 | Distrib.(-20) | Distrib.(-16) | -6.6 | ▼ |
| HIMS | 2026-08-26 | Distrib.(-8) | Alza(+17) | -3.7 | ▲ | abierta | — | — | — | — |

#### CONFIRMED_FLOW_LEADERS

| Ticker | Entrada | Konc D@entr. | Konc W@entr. | Flow@entr. | MACD@entr. | Salida | Konc D@sal. | Konc W@sal. | Flow@sal. | MACD@sal. |
|---|---|---|---|---:|:---:|---|---|---|---:|:---:|
| NVDA | 2026-05-08 | Alza(+45) | Alza(+45) | 30.7 | ▲ | 2026-06-10 | Baja(-41) | Alza(+19) | -17.1 | ▼ |
| MSTR | 2026-05-08 | Alza(+17) | Alza(+0) | 49.5 | ▲ | 2026-06-10 | Baja(-11) | Distrib.(-40) | -48.6 | ▼ |
| COIN | 2026-05-09 | Alza(+8) | Distrib.(-2) | 34.6 | ▲ | 2026-06-10 | Acum.(+2) | Distrib.(-2) | -32.4 | ▼ |
| KOS | 2026-05-15 | Distrib.(-18) | Alza(+72) | 39.3 | ▼ | 2026-06-10 | Alza(+36) | Alza(+30) | 4.9 | ▼ |
| WCP.TO | 2026-05-15 | Alza(+22) | Alza(+16) | 28.4 | ▲ | 2026-06-16 | Distrib.(-18) | Alza(+17) | -7.1 | ▼ |
| SU | 2026-05-16 | Alza(+26) | Alza(+31) | 26.6 | ▲ | 2026-06-10 | Acum.(+20) | Alza(+3) | -8.5 | ▼ |
| ASPI | 2026-05-27 | Distrib.(-2) | Distrib.(-4) | 59.0 | ▲ | 2026-06-10 | Distrib.(-13) | Distrib.(-7) | -36.4 | ▼ |
| OSCR | 2026-05-28 | Alza(+20) | Alza(+11) | 16.7 | ▼ | 2026-07-17 | Alza(+2) | Alza(+0) | -1.9 | ▼ |
| EOSE | 2026-05-29 | Distrib.(-8) | Distrib.(-5) | 29.0 | ▲ | 2026-06-10 | Distrib.(-10) | Distrib.(-4) | -58.4 | ▼ |
| SASK.V | 2026-05-30 | Distrib.(-15) | Distrib.(-5) | 25.0 | ▲ | 2026-06-10 | Distrib.(-14) | Distrib.(-5) | -47.0 | ▼ |
| RCAT | 2026-05-30 | Alza(+6) | Distrib.(-6) | 95.2 | ▲ | 2026-06-10 | Distrib.(-19) | Distrib.(-12) | -31.6 | ▼ |
| BBAR | 2026-06-03 | Distrib.(-4) | Distrib.(-5) | 24.6 | ▲ | 2026-06-26 | Distrib.(-11) | Distrib.(-0) | -8.4 | ▼ |
| LOMA | 2026-06-13 | Distrib.(-32) | Alza(+62) | 29.1 | ▲ | 2026-06-25 | Distrib.(-10) | Alza(+41) | -2.1 | ▼ |
| GGAL | 2026-06-13 | Alza(+0) | Distrib.(-3) | 52.4 | ▲ | 2026-06-26 | Distrib.(-20) | Distrib.(-48) | -12.0 | ▼ |
| QQQ | 2026-06-16 | Alza(+9) | Alza(+18) | 11.0 | ▼ | 2026-06-24 | Alza(+10) | Alza(+23) | -0.4 | ▼ |
| TDOC | 2026-06-16 | Alza(+9) | Distrib.(-6) | 28.0 | ▼ | 2026-07-31 | Acum.(+33) | Alza(+2) | -48.9 | ▼ |
| HIMS | 2026-06-17 | Alza(+4) | Distrib.(-2) | 54.4 | ▲ | 2026-07-22 | Distrib.(-14) | Distrib.(-6) | -26.8 | ▼ |
| ASPI | 2026-06-20 | Distrib.(-7) | Distrib.(-4) | 40.6 | ▼ | 2026-06-26 | Distrib.(-7) | Distrib.(-3) | -26.4 | ▼ |
| SASK.V | 2026-06-20 | Distrib.(-33) | Distrib.(-1) | 9.0 | ▲ | 2026-06-26 | Distrib.(-18) | Distrib.(-3) | -19.8 | ▼ |
| URI | 2026-07-01 | Distrib.(-10) | Alza(+22) | 14.4 | ▼ | 2026-07-08 | Alza(+9) | Alza(+2) | -2.0 | ▼ |
| ROOT | 2026-07-01 | Distrib.(-0) | Distrib.(-3) | 19.6 | ▲ | 2026-07-16 | Distrib.(-1) | Alza(+4) | -5.7 | ▼ |
| AFM.V | 2026-07-04 | Alza(+4) | Alza(+50) | 1.5 | ▲ | 2026-07-07 | Alza(+7) | Alza(+50) | 7.9 | ▼ |
| SE | 2026-07-07 | Alza(+25) | Alza(+12) | 30.3 | ▲ | 2026-07-08 | Alza(+22) | Alza(+12) | 35.1 | ▲ |
| URI | 2026-07-25 | Alza(+2) | Alza(+2) | 18.9 | ▲ | 2026-07-26 | Alza(+2) | Alza(+2) | 18.9 | ▲ |
| TMO | 2026-07-25 | Distrib.(-8) | Alza(+5) | 19.5 | ▲ | abierta | — | — | — | — |
| NBIS | 2026-08-05 | Alza(+10) | — | 69.7 | ▲ | 2026-08-07 | Alza(+5) | — | -10.1 | ▲ |
| PLTR | 2026-08-07 | Distrib.(-19) | Alza(+4) | 77.9 | ▲ | 2026-08-21 | Distrib.(-15) | Alza(+11) | 43.9 | ▲ |
| SEDANA.ST | 2026-08-12 | Alza(+16) | Alza(+3) | 37.1 | ▲ | abierta | — | — | — | — |

#### EARLY_ROTATION

| Ticker | Entrada | Konc D@entr. | Konc W@entr. | Flow@entr. | MACD@entr. | Salida | Konc D@sal. | Konc W@sal. | Flow@sal. | MACD@sal. |
|---|---|---|---|---:|:---:|---|---|---|---:|:---:|
| TSLA | 2026-05-09 | Distrib.(-15) | Alza(+17) | 42.5 | ▲ | 2026-06-10 | Baja(-17) | Alza(+19) | -24.7 | ▼ |
| ASTS | 2026-05-23 | Distrib.(-1) | Alza(+27) | 94.7 | ▲ | 2026-06-10 | Distrib.(-5) | Distrib.(-2) | -22.0 | ▼ |
| MLX.AX | 2026-05-23 | Alza(+0) | Distrib.(-1) | 40.6 | ▲ | 2026-06-10 | Distrib.(-13) | Distrib.(-23) | -20.4 | ▼ |
| CVE | 2026-07-22 | Alza(+13) | Distrib.(-2) | 24.1 | ▲ | 2026-07-29 | Alza(+28) | Distrib.(-2) | 17.8 | ▲ |
| TOU.TO | 2026-07-23 | Alza(+25) | Distrib.(-2) | 15.9 | ▲ | 2026-07-31 | Distrib.(-1) | Alza(+15) | -0.8 | ▲ |
| CVE | 2026-07-30 | Alza(+46) | Distrib.(-2) | 25.0 | ▲ | 2026-07-31 | Alza(+37) | Distrib.(-2) | 27.0 | ▲ |

#### MACRO_THEMATIC_BENEFICIARIES

| Ticker | Entrada | Konc D@entr. | Konc W@entr. | Flow@entr. | MACD@entr. | Salida | Konc D@sal. | Konc W@sal. | Flow@sal. | MACD@sal. |
|---|---|---|---|---:|:---:|---|---|---|---:|:---:|
| SE | 2026-07-15 | Alza(+26) | Alza(+10) | 39.9 | ▲ | 2026-07-16 | Alza(+23) | Alza(+10) | 19.3 | ▲ |
| NVDA | 2026-07-15 | Distrib.(-48) | Alza(+15) | 11.5 | ▲ | 2026-07-16 | Distrib.(-62) | Alza(+15) | 2.3 | ▲ |

#### MIMO_SHADOW

| Ticker | Entrada | Konc D@entr. | Konc W@entr. | Flow@entr. | MACD@entr. | Salida | Konc D@sal. | Konc W@sal. | Flow@sal. | MACD@sal. |
|---|---|---|---|---:|:---:|---|---|---|---:|:---:|
| SASK.V | 2026-06-20 | Distrib.(-33) | Distrib.(-1) | 9.0 | ▲ | 2026-07-02 | Distrib.(-12) | Distrib.(-3) | -4.2 | ▼ |
| GS | 2026-06-20 | Alza(+11) | Alza(+35) | 23.2 | ▲ | 2026-07-06 | Alza(+4) | Alza(+26) | 8.4 | ▼ |
| NBIS | 2026-06-20 | Alza(+14) | — | 70.3 | ▲ | 2026-07-08 | Distrib.(-17) | — | -32.9 | ▼ |
| CAT | 2026-06-20 | Alza(+50) | Alza(+37) | 35.5 | ▲ | 2026-07-14 | Alza(+19) | Alza(+13) | 4.5 | ▼ |
| AMD | 2026-06-20 | Distrib.(-18) | Alza(+123) | 29.5 | ▼ | 2026-07-18 | Distrib.(-23) | Alza(+7) | -10.3 | ▼ |
| AFM.V | 2026-06-22 | Distrib.(-5) | Alza(+52) | 14.3 | ▲ | 2026-07-03 | Alza(+5) | Alza(+50) | 22.1 | ▲ |
| NUE | 2026-06-23 | Alza(+10) | Alza(+26) | -1.3 | ▼ | 2026-06-27 | Acum.(+19) | Alza(+17) | -13.3 | ▼ |
| HUM | 2026-06-23 | Distrib.(-30) | Alza(+59) | 9.7 | ▼ | 2026-07-15 | Alza(+34) | Alza(+54) | 15.5 | ▼ |
| SLS | 2026-06-23 | Alza(+21) | Alza(+14) | 39.9 | ▼ | 2026-08-04 | Alza(+9) | Distrib.(-24) | 8.4 | ▼ |
| SE | 2026-06-25 | Distrib.(-23) | Alza(+14) | -1.9 | ▲ | 2026-06-25 | Distrib.(-23) | Alza(+14) | -1.9 | ▲ |
| UNH | 2026-06-26 | Alza(+29) | Alza(+10) | 25.2 | ▲ | 2026-07-28 | Distrib.(-13) | Distrib.(-1) | -1.9 | ▼ |
| CVS | 2026-06-26 | Alza(+29) | Distrib.(-16) | 24.1 | ▲ | 2026-08-04 | Alza(+9) | Distrib.(-20) | -0.7 | ▼ |
| EQR | 2026-06-27 | — | — | — | — | 2026-07-09 | — | — | — | — |
| ABBV | 2026-06-27 | Alza(+23) | Alza(+4) | 34.0 | ▲ | 2026-08-04 | Alza(+10) | Alza(+37) | -7.6 | ▼ |
| TTI | 2026-06-29 | Alza(+27) | Alza(+25) | 26.7 | ▲ | 2026-07-03 | Distrib.(-36) | Distrib.(-6) | -22.2 | ▼ |
| TDOC | 2026-06-29 | Alza(+13) | Alza(+5) | 38.3 | ▲ | 2026-07-31 | Acum.(+33) | Alza(+2) | -48.9 | ▼ |
| SE | 2026-07-01 | Alza(+31) | Alza(+13) | 23.1 | ▲ | 2026-07-03 | Alza(+33) | Alza(+12) | 37.1 | ▲ |
| HIMS | 2026-07-01 | Distrib.(-0) | Distrib.(-5) | 46.0 | ▲ | 2026-07-22 | Distrib.(-14) | Distrib.(-6) | -26.8 | ▼ |
| ROOT | 2026-07-03 | Alza(+9) | Alza(+2) | 40.1 | ▲ | 2026-07-16 | Distrib.(-1) | Alza(+4) | -5.7 | ▼ |
| SE | 2026-07-07 | Alza(+25) | Alza(+12) | 30.3 | ▲ | 2026-07-14 | Alza(+17) | Alza(+10) | 33.9 | ▲ |
| LLY | 2026-07-08 | Distrib.(-20) | Alza(+1) | 10.3 | ▲ | 2026-07-15 | Distrib.(-26) | Distrib.(-4) | -5.4 | ▼ |
| OSCR | 2026-07-09 | Distrib.(-16) | Alza(+12) | 10.3 | ▼ | 2026-08-04 | Distrib.(-17) | Distrib.(-3) | -7.0 | ▼ |
| URI | 2026-07-11 | Alza(+15) | Alza(+2) | 5.2 | ▼ | 2026-07-14 | Alza(+13) | Alza(+2) | 5.2 | ▼ |
| SASK.V | 2026-07-11 | Distrib.(-8) | Distrib.(-1) | 9.0 | ▲ | 2026-07-16 | Distrib.(-12) | Distrib.(-1) | -19.0 | ▼ |
| EQR | 2026-07-17 | — | — | — | — | 2026-07-22 | — | — | — | — |
| LLY | 2026-07-18 | Distrib.(-41) | Distrib.(-4) | -2.2 | ▼ | 2026-08-04 | Distrib.(-15) | Alza(+0) | -15.9 | ▼ |
| HUM | 2026-07-20 | Alza(+50) | Alza(+44) | 10.1 | ▼ | 2026-08-04 | Acum.(+23) | Alza(+24) | -13.3 | ▼ |
| CVE | 2026-07-23 | Alza(+11) | Distrib.(-2) | 29.3 | ▲ | 2026-07-29 | Alza(+28) | Distrib.(-2) | 17.8 | ▲ |
| JNJ | 2026-07-24 | Alza(+34) | Alza(+20) | 17.0 | ▼ | 2026-08-01 | Alza(+13) | Alza(+18) | -3.2 | ▼ |
| NUE | 2026-07-24 | Alza(+15) | Alza(+10) | 15.4 | ▲ | 2026-08-21 | Distrib.(-13) | Alza(+14) | -10.5 | ▼ |
| MRK | 2026-07-24 | Alza(+8) | Alza(+41) | 17.8 | ▲ | abierta | — | — | — | — |
| TOU.TO | 2026-07-25 | Alza(+22) | Alza(+16) | 14.2 | ▲ | 2026-07-31 | Distrib.(-1) | Alza(+15) | -0.8 | ▲ |
| NBIS | 2026-07-26 | Alza(+6) | — | -18.5 | ▼ | 2026-07-28 | Acum.(+5) | — | -51.1 | ▼ |
| WCP.TO | 2026-07-26 | Distrib.(-23) | Distrib.(-2) | 5.5 | ▲ | 2026-07-29 | Alza(+1) | Distrib.(-2) | 6.9 | ▲ |
| YPF | 2026-07-28 | Distrib.(-16) | Alza(+6) | 5.9 | ▲ | 2026-08-06 | Alza(+5) | Alza(+11) | -0.3 | ▼ |
| SYK | 2026-07-29 | Alza(+37) | Alza(+15) | 28.4 | ▲ | 2026-08-01 | Alza(+58) | Alza(+13) | 9.9 | ▲ |
| TECK | 2026-07-31 | Distrib.(-11) | Alza(+13) | 2.3 | ▲ | 2026-08-01 | Distrib.(-11) | Alza(+13) | 2.7 | ▲ |
| III.L | 2026-07-31 | Alza(+11) | Alza(+54) | 19.1 | ▲ | 2026-08-05 | Alza(+14) | Alza(+54) | 15.5 | ▲ |
| SEDANA.ST | 2026-08-01 | Alza(+3) | Alza(+4) | 35.1 | ▲ | 2026-08-04 | Alza(+2) | Alza(+4) | 30.3 | ▲ |
| PAM | 2026-08-02 | Alza(+20) | Alza(+4) | 13.1 | ▲ | 2026-08-05 | Alza(+7) | Alza(+4) | 3.9 | ▼ |
| WCP.TO | 2026-08-03 | Distrib.(-17) | Distrib.(-2) | 13.9 | ▲ | 2026-08-06 | Alza(+22) | Distrib.(-2) | 12.9 | ▲ |
| SE | 2026-08-04 | Alza(+26) | Distrib.(-2) | 12.6 | ▲ | abierta | — | — | — | — |
| TMO | 2026-08-04 | Distrib.(-5) | Alza(+9) | 7.3 | ▲ | abierta | — | — | — | — |
| NBIS | 2026-08-05 | Alza(+10) | — | 69.7 | ▲ | 2026-08-07 | Alza(+5) | — | -10.1 | ▲ |
| NVDA | 2026-08-05 | Alza(+16) | Alza(+7) | 33.3 | ▲ | 2026-08-11 | Alza(+21) | Alza(+32) | 15.7 | ▲ |
| TECK | 2026-08-06 | Alza(+8) | Alza(+13) | 28.1 | ▲ | 2026-08-14 | Distrib.(-9) | Alza(+19) | 8.9 | ▲ |
| DPM.TO | 2026-08-06 | Alza(+68) | Distrib.(-8) | 42.8 | ▲ | abierta | — | — | — | — |
| FCX | 2026-08-07 | Alza(+24) | Alza(+30) | 31.7 | ▲ | 2026-08-26 | Alza(+22) | Alza(+14) | 46.7 | ▲ |
| PLTR | 2026-08-07 | Distrib.(-19) | Alza(+4) | 77.9 | ▲ | abierta | — | — | — | — |
| OXY | 2026-08-11 | Distrib.(-11) | Alza(+19) | 17.3 | ▲ | 2026-08-15 | Alza(+5) | Alza(+43) | 13.6 | ▲ |
| KTOS | 2026-08-11 | Alza(+30) | Distrib.(-21) | 60.4 | ▲ | 2026-08-21 | Alza(+6) | Distrib.(-58) | -1.4 | ▼ |
| AFM.V | 2026-08-11 | Distrib.(-8) | Alza(+49) | 10.9 | ▲ | 2026-08-21 | Distrib.(-1) | Alza(+5) | -8.1 | ▼ |
| WCP.TO | 2026-08-11 | Alza(+34) | Distrib.(-9) | 21.1 | ▲ | abierta | — | — | — | — |
| SYK | 2026-08-12 | Alza(+33) | Alza(+35) | 18.7 | ▲ | 2026-08-19 | Alza(+14) | Alza(+30) | 7.0 | ▼ |
| SEDANA.ST | 2026-08-12 | Alza(+16) | Alza(+3) | 37.1 | ▲ | abierta | — | — | — | — |
| NBIS | 2026-08-14 | Alza(+18) | — | 111.7 | ▲ | 2026-08-21 | Distrib.(-1) | — | -26.5 | ▲ |
| SLS | 2026-08-14 | Alza(+21) | Alza(+3) | 18.9 | ▲ | abierta | — | — | — | — |
| III.L | 2026-08-15 | Alza(+5) | Alza(+28) | 7.2 | ▼ | 2026-08-21 | Alza(+22) | Alza(+24) | 14.2 | ▼ |
| OSCR | 2026-08-21 | Alza(+24) | Alza(+10) | 12.9 | ▲ | 2026-08-29 | — | — | — | — |
| TECK | 2026-08-21 | Alza(+33) | Alza(+17) | 31.1 | ▲ | abierta | — | — | — | — |
| CRON | 2026-08-22 | Distrib.(-9) | Alza(+11) | 30.9 | ▲ | abierta | — | — | — | — |
| EXK | 2026-08-23 | Alza(+5) | Alza(+35) | 43.1 | ▲ | abierta | — | — | — | — |
| VRTX | 2026-08-24 | Alza(+21) | Alza(+35) | 27.2 | ▲ | abierta | — | — | — | — |
| III.L | 2026-08-25 | Alza(+12) | Alza(+24) | 11.0 | ▼ | 2026-08-28 | — | — | — | — |
| CVE | 2026-08-26 | Alza(+26) | Alza(+27) | 12.1 | ▼ | abierta | — | — | — | — |
| DHR | 2026-08-27 | Distrib.(-4) | Alza(+37) | 11.0 | ▲ | abierta | — | — | — | — |
| VLE.TO | 2026-08-28 | Alza(+10) | Alza(+5) | 16.3 | ▲ | abierta | — | — | — | — |
| TNZ.TO | 2026-08-28 | Alza(+21) | Alza(+5) | 30.7 | ▲ | abierta | — | — | — | — |
| FCX | 2026-08-28 | Alza(+13) | Alza(+12) | 23.3 | ▲ | abierta | — | — | — | — |
| HUM | 2026-08-29 | — | — | — | — | abierta | — | — | — | — |

#### CAVA_MACRO

| Ticker | Entrada | Konc D@entr. | Konc W@entr. | Flow@entr. | MACD@entr. | Salida | Konc D@sal. | Konc W@sal. | Flow@sal. | MACD@sal. |
|---|---|---|---|---:|:---:|---|---|---|---:|:---:|
| III.L | 2026-08-03 | Alza(+10) | Alza(+54) | 15.9 | ▲ | 2026-08-07 | Alza(+10) | Alza(+45) | 10.9 | ▲ |
| OSCR | 2026-08-03 | Distrib.(-13) | Distrib.(-3) | 5.4 | ▼ | 2026-08-07 | Acum.(+15) | Distrib.(-2) | -23.0 | ▼ |
| YPF | 2026-08-03 | Distrib.(-30) | Alza(+11) | 14.5 | ▲ | 2026-08-07 | Alza(+4) | Alza(+10) | -0.7 | ▼ |
| PAM | 2026-08-03 | Alza(+20) | Alza(+4) | 13.1 | ▲ | 2026-08-07 | Distrib.(-3) | Alza(+3) | -8.1 | ▼ |
| KOS | 2026-08-03 | Distrib.(-46) | Alza(+36) | 22.9 | ▲ | 2026-08-07 | Distrib.(-10) | Alza(+30) | 2.1 | ▲ |
| NUE | 2026-08-03 | Alza(+4) | Alza(+9) | 26.9 | ▲ | 2026-08-21 | Distrib.(-13) | Alza(+14) | -10.5 | ▼ |
| FCX | 2026-08-03 | Alza(+33) | Alza(+11) | 8.9 | ▲ | 2026-08-26 | Alza(+22) | Alza(+14) | 46.7 | ▲ |
| TMO | 2026-08-03 | Distrib.(-6) | Alza(+9) | 16.6 | ▲ | abierta | — | — | — | — |
| MRK | 2026-08-03 | Distrib.(-1) | Alza(+36) | -2.2 | ▼ | abierta | — | — | — | — |
| SLS | 2026-08-03 | Distrib.(-4) | Distrib.(-24) | -19.2 | ▼ | abierta | — | — | — | — |
| GS | 2026-08-07 | Alza(+8) | Alza(+22) | 4.3 | ▼ | 2026-08-11 | Alza(+7) | Alza(+22) | 0.3 | ▼ |
| URI | 2026-08-07 | Alza(+1) | Alza(+21) | 22.2 | ▲ | 2026-08-22 | Distrib.(-4) | Alza(+11) | -11.4 | ▼ |
| PLTR | 2026-08-07 | Distrib.(-19) | Alza(+4) | 77.9 | ▲ | abierta | — | — | — | — |
| SE | 2026-08-07 | Alza(+28) | Distrib.(-2) | 13.4 | ▲ | abierta | — | — | — | — |
| DHR | 2026-08-07 | Alza(+16) | Alza(+58) | 14.7 | ▲ | abierta | — | — | — | — |
| AWX | 2026-08-11 | Alza(+74) | Distrib.(-3) | 28.4 | ▲ | 2026-08-22 | Distrib.(-9) | Alza(+2) | 5.1 | ▼ |
| III.L | 2026-08-21 | Alza(+22) | Alza(+24) | 14.2 | ▼ | 2026-08-29 | — | — | — | — |
| TK | 2026-08-22 | Alza(+14) | Alza(+53) | 27.5 | ▲ | 2026-08-25 | Alza(+12) | Alza(+53) | 26.3 | ▲ |
| RIO | 2026-08-22 | Alza(+10) | Distrib.(-1) | 27.1 | ▲ | 2026-08-25 | Alza(+40) | Distrib.(-1) | 31.3 | ▲ |
| VIT-B.ST | 2026-08-25 | Alza(+5) | Distrib.(-7) | 22.4 | ▲ | 2026-08-27 | Distrib.(-8) | Distrib.(-7) | 23.8 | ▲ |
| OSCR | 2026-08-25 | Distrib.(-4) | Alza(+10) | 8.5 | ▲ | abierta | — | — | — | — |
| EOS.AX | 2026-08-26 | Alza(+12) | Alza(+12) | 91.7 | ▲ | 2026-08-28 | Distrib.(-19) | Alza(+11) | 69.1 | ▲ |
| FCX | 2026-08-27 | Alza(+15) | Alza(+14) | 44.3 | ▲ | abierta | — | — | — | — |
| TK | 2026-08-28 | Alza(+35) | Alza(+41) | 17.3 | ▲ | abierta | — | — | — | — |
| VIT-B.ST | 2026-08-29 | — | — | — | — | abierta | — | — | — | — |

#### MIRROR_ESPEJO

| Ticker | Entrada | Konc D@entr. | Konc W@entr. | Flow@entr. | MACD@entr. | Salida | Konc D@sal. | Konc W@sal. | Flow@sal. | MACD@sal. |
|---|---|---|---|---:|:---:|---|---|---|---:|:---:|
| CORZ | 2026-07-31 | Alza(+68) | Distrib.(-14) | -22.2 | ▼ | 2026-08-07 | Distrib.(-20) | Distrib.(-10) | -9.6 | ▲ |
| ACMR | 2026-07-31 | Alza(+24) | Distrib.(-4) | -35.8 | ▼ | 2026-08-11 | Distrib.(-3) | Alza(+10) | -16.1 | ▲ |
| CAT | 2026-07-31 | Acum.(+22) | Distrib.(-7) | -24.0 | ▼ | 2026-08-20 | Distrib.(-5) | Alza(+8) | -10.9 | ▲ |
| ASM.AS | 2026-08-02 | Alza(+54) | Distrib.(-22) | -15.4 | ▼ | 2026-08-18 | Alza(+23) | Alza(+18) | -1.9 | ▲ |
| OSCR | 2026-08-08 | Alza(+9) | Distrib.(-2) | -19.2 | ▼ | 2026-08-26 | Distrib.(-3) | Alza(+10) | -1.9 | ▲ |
| MAI.L | 2026-08-13 | Alza(+50) | Baja(-1) | -10.5 | ▲ | abierta | — | — | — | — |
| UNH | 2026-08-15 | Acum.(+4) | Distrib.(-15) | -7.7 | ▼ | abierta | — | — | — | — |
