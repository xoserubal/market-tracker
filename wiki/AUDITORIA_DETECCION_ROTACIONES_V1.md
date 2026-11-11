# Auditoría — detección temprana de rotaciones de capital en Market Tracker (v1)

> **Actualización 2026-11-11:** el punto H1 se ejecutó con preregistro. Early Flow ≥ 7 queda **descartado** (no supera
> al universo ni a ningún benchmark, 2016-2026). Detalle: `research/early_flow7_validation_v1/README.md`.

Fecha: 2026-11-11. Alcance: diagnóstico del sistema actual. **No se ha modificado código, fórmulas, producción
ni parámetros.** Las únicas cifras nuevas salen de scripts de solo lectura sobre datos ya guardados en el repo
(sin descargas ni coste), marcados como **exploratorios** cuando la muestra no permite más.

---

## 0. Resumen en una página

1. **Market Tracker describe bien qué está subiendo en términos relativos, pero no hay evidencia de que lo
   anticipe.** Las tres herramientas de rotación con histórico largo ya se han medido y ninguna ordena el
   rendimiento futuro mejor que el azar ni que el momentum simple:
   - Relative Flow Lab (45-50 ratios, 10 años): correlación score↔alfa futuro ≈ 0 (`wiki/RELATIVE_FLOW_LAB_HALLAZGOS.md`).
   - Rotation Score sobre 22 ETFs/materias primas, 2005-2026 semanal: rank IC −0,04 a +0,03, ningún |t| ≥ 1,1
     (cálculo de esta auditoría sobre `backtest/data/processed/signal_alphas.parquet`, tabla §8.2).
   - Early Flow ≥ 4 sobre 518 valores del S&P 500/Nasdaq 100, 2016-2026: sin exceso (`research/macd_combo_filters_v1`).
2. **Las señales "de flujo" son, sobre todo, precio.** El Flow Score se explica en un **98,5 %** por los retornos
   de 1 semana y 1 mes (R² = 0,985 sobre 6 276 lecturas reales). Early Flow tiene una correlación de 0,84 con sus
   componentes de precio. El único ingrediente que usa volumen (Koncorde, vía NVI/PVI) también se calcula sobre
   OHLCV. **No hay ninguna fuente independiente de flujos** (creaciones/reembolsos de ETF, 13F, órdenes): toda
   "acumulación" es una inferencia sobre precio y volumen.
3. **Cobertura:** el universo principal son 130 tickers elegidos a mano (59 en "Cartera", fuerte peso en petróleo,
   mineras de oro/plata, Argentina, cannabis). No sirve para afirmar rotaciones sectoriales generales: Tecnología
   tiene 12 nombres, Utilities/REITs casi ninguno, y la propia pertenencia al universo es una decisión tomada a
   posteriori (sesgo de selección).
4. **Persistencia:** la captura diaria completa existe solo desde el 2026-08-20 (Portfolio Tracker) y
   2026-09-13 (Market Tracker). Antes de eso no se puede reconstruir qué veía el sistema, salvo PCS/rot_score vía
   git (desde 2026-05-08) y lo que se recalcula desde precios (Koncorde, Early Flow, RFL, rot_score).
5. **Una pista, no un hallazgo:** en los datos en vivo (agosto-noviembre 2026, 130 tickers) las activaciones de
   **Early Flow ≥ 7 ("Fuerte")** se dan casi siempre en fase de estabilización/inicio (34 de 50 en fases B-C) y
   fueron seguidas de exceso positivo (mediana +6,8 pp a 20 sesiones, 67 % aciertos, n = 33, 21 fechas). Un solo
   régimen y dos meses y medio: no es evidencia. El estudio de 10 años probó el umbral 4, no el 7: **es el primer
   experimento que propongo, y se puede hacer en minutos con datos ya descargados.**
6. **Koncorde "pasa a acumulación"** se activa en caída libre (71 de 97 eventos en fase A, mediana −10 % el mes
   previo) y fue seguido de exceso negativo (−1 a −2 pp, aciertos 39-42 %). Hoy funciona como señal de cuchillo
   cayendo, no de acumulación.

---

## 1. Inventario de indicadores

### 1.1 Indicadores de "flujo", momentum y rotación

| Indicador | Archivo / función | Entradas | Ventana | Frecuencia | Dónde se ejecuta |
|---|---|---|---|---|---|
| **Flow Score** | `shared/flow-score.js → computeFlowScore` | w1, m1, RSI14, MACD hist>0, ATR%, Koncorde D y W, distancia al máx. 52s | 5/21 ses. | Diaria | Navegador (index, portfolio, screeners, trullas) y pipeline (`portfolio_daily_snapshot.js`, `market_daily_snapshot.js`) |
| **Early Flow** | `shared/flow-score.js → computeEarlyFlowScore` | Giro de estado Koncorde D/3D vs sesión anterior, alineación 3D/W, ratio ATR% hoy/ayer, distancia al máx., RSI, w1/m1 | 1 ses. (prev) + 5/21 | Diaria | Ídem |
| **Koncorde Plus** (blue/green/trend, 4 estados, D/3D/W) | `scripts/koncorde_calculator.py → _calc_koncorde_plus` | OHLCV: NVI y PVI (EMA15, normalizados en 90 barras), RSI14+MFI14+BB25+Stoch21 sobre ohlc4 | 90 barras | Diaria (pipeline, ~216 tickers) | Pipeline |
| **`konc_alignment`** | `koncorde_calculator.py → _konc_alignment` | Estados D/3D/W | — | Diaria | Pipeline |
| **Rotation Score (ETFs)** | `rotacion.html → calcRotScore`; réplica Python `backtest/src/rotation/score.py → rotation_score` | Bloque A: RS 13s>2 % (2), RS 4s>1 % (1), >SMA200 (1). B: CMF20>0,05, OBV>SMA50(OBV), vol20/vol60>1,10 (1 c/u). C: MACD hist>0, RSI 40-70, no extendido (1 c/u) | 4/13 semanas | Navegador diario; backtest semanal | Navegador (24 activos); backtest 2005-2026 |
| **rot_score acciones** | `backtest/src/rotation/stock_scanner.py` (`main_stocks.py`) | Igual que arriba | Semanal | Pipeline | Alimenta PCS (D) |
| **DEMS** | `scripts/pcs_calculator.py → compute_dems` | Alfa 5d/10d vs SPY, días batiendo a SPY, aceleración, vol 5d/20d, spike | 5-20 ses. | Diaria | Pipeline, solo payload de la IA |
| **PCS** (A-F) | `pcs_calculator.py → compute_pcs` | Macro, rot_score del proxy temático, RS 4s/13s, rot_score+CMF/OBV/vol, MACD/RSI/racha, calidad de datos | Semanal + diaria | Pipeline (147 tickers) | Puerta de elegibilidad (no ordena: corr. con ret_1m −0,007) |
| **Relative Flow Lab** | `shared/relative-lib.js → buildRowFromRatio`, `classify`, `coherentFlowDirection` | Ratio A/B: r1w·0,5 + r1m·0,7 + r3m·0,25 + tendencia SMA20/63 (±2) + RSI del ratio (±1,5) + flowChange·0,4 (±3) | 5-63 ses. | Diaria | Navegador; registro de eventos en pipeline (`relative_signal_log.js`) |
| **Flow state (Inflexión/Continuación/Reversión)** | `scripts/flow_state_lib.py` + espejo `shared/flow-state-lib.js` | Serie de Flow Score, ΔFlow 5 capturas, RSI, Koncorde, breadth de la cesta | 5 capturas | Diaria | Pipeline (columna "Mecánico" de Sol) y Screener |
| **Cycle Tracker** | `cycle.html → calcPhaseScores` | α = 0,7·RS3m + 0,3·RS1m por ticker; breadth (% α>0), dispersión, aceleración por fase | 21/63 ses. | Al abrir la página | Solo navegador, **sin persistencia** |
| **Matriz cross-módulos** | `relative.html` (Fase 5a) | Cycle (r3m), Flujos (rotation_history), RFL (flowChange) | — | Al abrir | Solo navegador |
| **Screeners** | `shared/screener-lib.js` | MACD, Flow state, RSI mensual | — | Diaria | Navegador + log en pipeline |

Datos calculados en `shared/quote-lib.js → buildQuoteData` y **no usados por Flow/Early**: `cmf20`,
`obvAboveSma50`, `volRatio` (solo los usa `rotacion.html`), `vol1d-3d` (solo se muestran).

### 1.2 Fórmulas exactas de las dos señales principales

**Flow Score** = 2·(0,6·w1 + 0,4·m1) + RSI(+2 si >65, +1 si >55) + MACD(±1) + ATR%(+1 si 1-3, +0,5 si 3-6, −0,5 si
>6) + Koncorde(D: up +2, acum. +1, distrib. −1, down −2; W igual × 0,5) + tendencia(+1 si a ≤10 % del máximo de 52s,
−1 si a más del 25 %). Umbrales: ≥8 Líder, ≥4 Transición.
w1/m1 son porcentajes enteros: **un mes de +10 % ya aporta 8 puntos por sí solo**. No usa fuerza relativa frente a
índice ni sector, ni volumen salvo a través de Koncorde.

**Early Flow** (suma de puntos): A) giro Koncorde D respecto a la sesión anterior (down→acum. +3, distrib.→acum. +2,
acum.→up +1, D bajista −1); A2) 3D/W alcistas +1 c/u, W bajista −1; giro 3D down→acum. +1; B) ATR% hoy/ayer <0,9 +2,
<1,0 +1, >1,2 −1; C) a −5/−15 % del máximo +2, −15/−25 % +1, < −30 % −1; D) RSI 45-58 +2, 40-45 +1, <35 −1;
E) momentum modesto (w1 0-4 y m1 −5/+5) +2, etc. Umbrales: ≥7 Fuerte, ≥4 Interesante.

### 1.3 Implementado vs ejecutado vs conectado

| Pieza | Estado |
|---|---|
| Flow/Early Flow, Koncorde, PCS, DEMS, RFL, screeners | Implementados y ejecutados a diario en el pipeline |
| Rotation Score de ETFs (`rotacion.html`) | Se calcula al abrir la página; histórico en `state.json` **local** (no en git, cap 70 días; perdió una semana en ago-2026 por un 413) |
| Cycle Tracker, matriz cross-módulos, breadth por fase | **Solo en el navegador, sin histórico** |
| Backtest de rotación (`backtest/src/main_*.py`, `signal_alphas.parquet`, `lead_time_analysis.parquet`) | Existe y tiene 20 años; **no está en el pipeline** (no se actualiza a diario) |
| CMF/OBV/volRatio en `buildQuoteData` | Calculados para todos, consumidos solo por `rotacion.html` |
| Koncorde `_research_fields` (blue_z, accel…) | Se registran a diario en `koncorde_signals_history.jsonl`, no alimentan nada |

---

## 2. Qué información de flujos tenemos realmente

| Tipo | Qué hay | Observación |
|---|---|---|
| **Observado** | OHLCV diario (Yahoo, 3 años por llamada; 10-20 años en cachés de investigación); FRED (liquidez, spreads, curva); CFTC COT (4 materias primas, semanal); Form 4 de insiders (solo tickers EE.UU. en acumulación Koncorde, ~7); cadenas de opciones yfinance (SPX/QQQ y 4 ETFs inversos); subastas del Tesoro; cartera propia IBKR (privado) | Ningún dato de flujo neto ni de posiciones institucionales por activo |
| **Estimado** | Koncorde (NVI/PVI + osciladores), CMF20, OBV, volRatio, vol vs media 3m, ATR%, RSI, MACD, GEX DIY (aproximación, sin desglose de quién está corto) | Todo derivado de OHLCV |
| **Inferido** | "Acumulación", "distribución", "flujo", "entrada de capital", "rotación", "Flow Score" | Son nombres de indicadores técnicos, no mediciones |

**No existe ninguna fuente independiente para contrastar las inferencias de flujo** (creaciones/reembolsos de ETF,
13F, datos de órdenes o transacciones clasificadas). El COT de 4 materias primas es lo único parecido, y no se cruza
con ninguna señal. El término "flowChange" del RFL es la aceleración del retorno del ratio (5 días contra los 5
anteriores), no un flujo.

---

## 3. Cobertura del universo

| Universo | Tamaño | Composición | Histórico persistido |
|---|---|---|---|
| Portfolio Tracker (`portfolio.json`) | **130** tickers (+FXPO.L en cuarentena) | 87 EE.UU., 12 TSX-V, 10 TSX, 7 ASX, 5 Londres, resto Europa. Secciones: Cartera 59, Argentina 13, Cannabis 9, Petróleo 8, Calidad 8, Opciones 7… | Captura diaria completa desde 2026-08-20 |
| Universo del motor (`universe.json`) | 147 | oil_gas 21, healthcare 20, mineras oro/plata 14, metales 13, tech/IA 12, Argentina 12, cíclicas EE.UU. 10, Europa 8… | PCS vía git desde 2026-05-08 |
| Koncorde | ~216 | Unión de los anteriores | Log diario desde 2026-07-21 |
| Market Tracker (`index.html`) | 64 | Índices, MAG6, bonos/materias primas, regiones, sectores EE.UU. y Europa, uranio, energía, carbón | Captura diaria desde 2026-09-13 |
| Relative Flow Lab | 50 ratios | 14 sector vs SPY, 9 rotación entre bloques, 11 anticipación interna, 10 apetito de riesgo, 6 regiones | Recalculable 10 años desde precios |
| Rotation (`rotacion.html`) | 24 activos | 12 sectores SPDR + XOP, 6 índices, TLT, oro/plata/Brent/cobre, BTC | Backtest semanal 2005-2026 |
| Investigación S&P 500 + NDX | 518 | Componentes actuales (sesgo de supervivencia) | Caché diaria 2015-2026 en `research/` (fuera de git) |

**Respuesta a la pregunta esencial:** con el universo de 130 tickers **solo podemos hablar de cambios dentro del
subconjunto que seguimos**. Motivos:
- Representatividad: Tecnología 12 nombres, Utilities ~0, REITs 3; dominan temas de materias primas y nichos.
- Sesgo de selección: los tickers entran en el portfolio cuando ya han llamado la atención; un "movimiento detectado"
  en ese universo puede ser simplemente la razón por la que se añadió.
- Clasificación: tema/subtema propios (revisados en la auditoría de universo de octubre), sin GICS de industria;
  21 temas con 1-21 nombres cada uno.

La rotación sectorial **general** solo se puede observar con los ETFs sectoriales (12 SPDR en EE.UU., sectores
europeos en Market Tracker) y con el caché de 518 valores del S&P 500/NDX, que hoy solo vive en `research/`.

---

## 4. Capacidad de análisis transversal

| Comparación | Disponible | Dónde | Limitación |
|---|---|---|---|
| Acción vs su propio histórico | Sí | RSI, distancia a máximos, Koncorde blue_z, percentil del trend Koncorde | — |
| Acción vs su industria | **No** | — | PCS-B usa el rot_score del proxy temático o la media del tema, no fuerza relativa del valor dentro del tema |
| Industria vs industrias | Parcial | Cycle Tracker (fases), cestas de `flow_state_lib` | Cestas = secciones del portfolio; sin histórico en Cycle |
| Sector vs mercado | Sí | RFL `*_spy`, `rotacion.html`, Cycle | Solo ETFs; sin breadth de componentes |
| Sectores y clases de activo entre sí | Sí | RFL (rotación entre bloques, apetito de riesgo), matriz cross-módulos | Solo precio |

| Herramienta pedida | Estado |
|---|---|
| Fuerza relativa | Sí (vs SPY; nunca vs sector a nivel de acción) |
| Cambios de momentum | Sí (ΔFlow, flowChange, MACD) |
| Breadth / participación de componentes | **Parcial y efímera**: breadth por fase en Cycle (sin histórico); breadth de cesta en `flow_state_lib` (solo veto, cestas de 2-13 nombres) |
| Volumen / valor negociado vs su referencia | Parcial: vol/media 3m, volRatio 20/60, DEMS vol 5d/20d. Nunca en valor monetario ni agregado por sector |
| Persistencia de acumulación | Parcial: `konc_d_blue_positive_days_6`, rachas semanales de rot_score |
| Concentración del liderazgo | **No** (solo el ratio QQQ/RSP como proxy de mercado) |
| Cambios de ranking en el tiempo | Parcial: Δ1W de RFL y rotación (local); `relative_signal_log` (eventos) |

**Lo que falta para "sectores que empiezan a mejorar de forma amplia sin destacar todavía por rentabilidad":** un
indicador de breadth por sector calculado sobre sus componentes (no sobre el ETF), con histórico. No existe. Sin él,
el sistema no puede distinguir un sector que sube por un valor estrella de uno que mejora en amplitud.

---

## 5. Capacidad de detección temprana (fases A-E)

### 5.1 Lectura teórica de las fórmulas
- **Flow Score**: por construcción es momentum de 1-4 semanas → se activa en fases C-D. No puede ver una mejora con
  el precio lateral.
- **Early Flow**: diseñado para B-C (premia RSI 45-58, momentum modesto, estar a 5-15 % del máximo y giros de
  Koncorde). Su componente de "compresión de volatilidad" está mal planteado: compara el ATR de hoy con el de ayer, y
  un ATR de 14 sesiones casi nunca cae un 10 % en un día (ocurre en el **0,3 %** de las lecturas); el +1 por "<1,0" se
  activa en el **44 %**, es decir, ruido.
- **Koncorde acumulación** (blue ≥ 0 con green < 0): diseñado para B, pero blue es un oscilador normalizado en 90
  barras que gira en cuanto la caída frena.
- **Rotation Score / RFL**: ponderan el retorno de 1-13 semanas → C-D.

### 5.2 Contraste con datos reales (exploratorio)
Fuente: `portfolio_daily_snapshot.jsonl`, 130 tickers, 64 velas (2026-08-19 → 2026-11-10). Fase asignada con una regla
fijada antes de mirar resultados: A = m1 < −5 %; E = m3 ≥ 40 %; D = m3 ≥ 15 %; B = m1 < 5 % y m3 < 0; C = resto.
Evento = primera activación tras ≥10 velas sin activarse. Exceso = retorno del valor − mediana del universo ese día.

| Señal | n | Fase A/B/C/D/E | m1 mediano previo | Exceso mediano 5 / 10 / 20 ses. | Aciertos 20 ses. |
|---|---|---|---|---|---|
| Early Flow ≥ 7 | 50 | 3/14/20/10/3 | 0 % | +0,6 / +1,8 / **+6,8** | 67 % (n 33) |
| Flow Score ≥ 8 | 123 | 9/40/53/18/2 | +3 % | +0,1 / +1,3 / +2,4 | 62 % (n 61) |
| Koncorde D → acumulación | 97 | **71**/9/12/3/1 | **−10 %** | −1,4 / −1,1 / −2,0 | 42 % (n 43) |
| `konc_alignment` = accumulation_setup | 25 | 19/5/1/0/0 | −12 % | −1,0 / −0,2 / −3,3 | 44 % (n 9) |
| Momentum simple m1 ≥ 10 % | 97 | 0/0/68/24/5 | +12 % | −0,2 / −1,4 / +3,0 | 55 % (n 55) |

Lectura:
- Early Flow ≥ 7 sí se activa antes que el momentum (m1 mediano 0 frente a +12 %) y en este periodo fue seguido de
  exceso positivo; los eventos están repartidos en 21 fechas distintas (no es un solo día bueno). Pero es un solo
  régimen, 2,5 meses, 130 tickers correlacionados y sin corrección por comparaciones múltiples.
- Koncorde "acumulación" no detecta acumulación: detecta que la caída se frena, y mayoritariamente sigue cayendo
  respecto al universo.
- **No se puede responder con datos si distinguen recuperación sostenible de rebote**: haría falta una definición de
  "tendencia consolidada" y más historia (ver §7-8).

---

## 6. Persistencia histórica

| Información | ¿Reconstruible a fecha? | Desde | Notas |
|---|---|---|---|
| Valores de Flow/Early/Koncorde/MACD/RSI por ticker (portfolio) | Sí, tal como se vieron | 2026-08-20 | `portfolio_daily_snapshot.jsonl` (37 MB, ~0,5 MB/día; habrá que partirlo hacia mar-2027) |
| Ídem universo Market Tracker | Sí | 2026-09-13 | `market_equities_daily_snapshot.jsonl` |
| Koncorde + ingredientes de investigación, ~216 tickers | Sí, con retornos futuros ya rellenos | 2026-07-21 | **W anterior al 2026-08-30 contaminado** (se recalculaba a diario sobre semanas incompletas) |
| PCS, rot_score, temas (motor) | Sí, vía `git show` de `ai_candidates.json` | 2026-05-08 | 364 commits |
| Eventos de los screeners | Sí | 2026-08-26 | Sin capturas en días perdidos del pipeline |
| Eventos RFL (to_improving, saltos de flowChange…) | Sí (recalculado desde precios) | 10 años | Backfill no es fuera de muestra; live desde 2026-10-16 |
| Rankings diarios de rotación ETF, Δ1W, coherencia | Solo en `state.json` local, cap 70 días | — | No en git; dependen de abrir la página; hueco 20-28 ago |
| Cycle Tracker, matriz cross-módulos, breadth por fase | **No** | — | Se calculan al abrir y no se guardan |
| Qué se mostró en pantalla / qué se descartó | **No** | — | No hay registro de la vista |

Problemas de calidad encontrados (sin corregir, solo documentados):
1. `date` (fecha de captura) ≠ fecha de la vela; `asOf` va 1-2 sesiones por detrás y a veces se repite. Cualquier
   estudio debe indexar por `asOf`.
2. La "sesión anterior" de Early Flow es la captura anterior del pipeline, que se repite o salta días: solo el 63 % de
   los valores coinciden exactamente con una reconstrucción limpia (93 % del mismo lado del umbral 4).
3. w1/m1/fromHigh se redondean a enteros; el máximo de 52 semanas usa cierres de los últimos 365 días contados desde
   "ahora", no desde la fecha de la vela (afecta a reconstrucciones con `cutoffDate`).
4. Precios en GBp/GBP: FXPO.L lleva un error ×100 persistente; otros `.L` lo han tenido de forma transitoria.
5. Precios de Yahoo ajustados en investigación vs sin ajustar en vivo (diferencias pequeñas, ya medidas en RFL).
6. Hora de cierre: el pipeline corre a las 23:10 Madrid (después del cierre de EE.UU.); antes del 10-nov algunas
   capturas eran intradía.
7. Copias en conflicto de Dropbox en `shared/` (`flow-score (Copia en conflicto…).js`) y en
   `backtest/data/processed/`: no se cargan, pero son un riesgo de confusión.

**Conclusión:** antes del 20-ago-2026 no se puede saber qué veía el sistema día a día salvo PCS/rot_score; lo demás
hay que recalcularlo desde precios, con las salvedades de arriba. Para validar anticipación a varios años hay que
reconstruir, no consultar logs.

---

## 7. Evidencia histórica de rotaciones

Estudios ya hechos que incluyen **todas** las señales (no solo las que salieron bien):

| Estudio | Universo / periodo | Resultado |
|---|---|---|
| RFL backtest (`wiki/RELATIVE_FLOW_LAB_HALLAZGOS.md`) | 45 ratios, 1998-2026 | Score↔alfa 1s/1m/3m: r = −0,009 / +0,003 / +0,012. 6 de 7 reglas no replican fuera de muestra |
| RFL family test (`wiki/PREREGISTRO_RELATIVE_FLOW_FAMILY_TEST_V1.md`) | 37 activos | Refugio vs industrial: refutada |
| Registro de eventos RFL (`relative_signal_report.json`) | 19 ratios vs mercado, 10 años, por régimen | Nada a 1-5 sesiones; saltos de flowChange al alza +0,6-0,9 pp a 21 ses. con aciertos < 50 %; saltos a la baja → rebote (señal invertida) |
| Fase 4/5a RFL (`CLAUDE.md`, 2026-09-17) | 215 393 filas | "Entrando" rinde **menos** que "saliendo" a 1-4 semanas (t −6): reversión |
| Combo MACD + filtros (`research/macd_combo_filters_v1`) | 518 valores, 2016-2026 | Early Flow ≥4, Koncorde, sector Leader/Improving: sin exceso. RS 63 ses. > 0 rinde **por debajo** (t −5,6 / −3,2) |
| Capitulación (`wiki/HALLAZGOS_CAPITULACION_PRECURSORES_V1.md`) | 590 eventos, 112 tickers, 5 años | Volumen no discrimina rebotes (p = 0,61) |
| Ranking Score Fase 1 (`docs/analysis/ranking_score_fase1_informe.md`) | 98 picks | Solo `dist_sma20_atr` plausible; Koncorde inconcluyente |
| Lead time early rotation → COMPRA (`backtest/data/processed/lead_time_analysis.parquet`) | ETFs 2005-2026, modo A | 28 episodios con convergencia: anticipación mediana 22 semanas (IQR 10-39). α 13 semanas desde la señal temprana: media +2,4 pp, 63 % positivos (n 46); desde la confirmación +1,3 pp |

Lo que **no existe** es el estudio por episodios que pide el encargo (primera señal, cuánto había subido ya,
confirmación, anticipación, recorrido restante, falsas señales, posición en el ranking). Para hacerlo faltan:
- Una definición mecánica de "inicio de tendencia" y "liderazgo consolidado", fijada antes (propuesta en §8.3).
- Histórico diario de los rankings: reconstruible para RFL, rot_score, Early Flow y Koncorde desde precios; **no**
  para Cycle Tracker ni la matriz (hay que portarlos a un script).
- Un universo no seleccionado a posteriori: el caché del S&P 500/NDX (con sesgo de supervivencia, documentable) y los
  ETFs sectoriales.

---

## 8. Evaluación cuantitativa

### 8.1 Qué se puede hacer hoy sin modificar nada
- **ETFs/sectores, 20 años semanales**: `signal_alphas.parquet` ya tiene rot_score, sus bloques y α futuro a 4/13/26
  semanas. Medido en esta auditoría (abajo).
- **Acciones S&P 500/NDX, 10 años diarios**: `research/macd_combo_filters_v1/_work/` ya tiene Early Flow,
  Koncorde, RS y sector por día. Falta Flow Score y los benchmarks, que son cálculos sobre los mismos precios.
- **Portfolio en vivo**: 64 velas; solo exploratorio.

### 8.2 Rotation Score frente a momentum en sectores/ETFs (2005-2026, cálculo de esta auditoría)
22 activos, fechas no solapadas, rank IC transversal medio (t entre paréntesis):

| Señal | 2005-15, 4 sem. | 2005-15, 13 sem. | 2016-26, 4 sem. | 2016-26, 13 sem. |
|---|---|---|---|---|
| rot_score completo | +0,03 (1,0) | −0,04 (−0,7) | −0,03 (−1,1) | −0,04 (−0,8) |
| Bloque A (precio/RS) | +0,04 (1,1) | −0,04 (−0,8) | −0,03 (−1,0) | −0,03 (−0,5) |
| Bloque B (volumen: CMF, OBV, vol rel.) | −0,02 (−0,7) | 0,00 (0,0) | +0,03 (1,1) | −0,07 (−1,4) |
| Momentum 2 sem. | +0,04 (1,3) | −0,08 (−1,4) | −0,05 (−1,8) | −0,12 (−2,2) |
| Momentum 4 sem. | +0,01 (0,4) | −0,02 (−0,3) | 0,00 (0,0) | −0,12 (−2,6) |
| Momentum 13 sem. | +0,02 (0,7) | −0,01 (−0,1) | −0,02 (−0,8) | +0,01 (0,2) |

Ni el score ni el bloque de volumen ordenan los sectores; el momentum corto incluso muestra reversión en 2016-2026.

### 8.3 Exploratorio en vivo (no es evidencia)
130 tickers, rank IC medio en fechas no solapadas (5 ses.: 9 fechas; 10 ses.: 5; 20 ses.: 2):

| Señal | 5 ses. | 10 ses. | 20 ses. |
|---|---|---|---|
| w1 (momentum 1 sem.) | +0,04 | +0,14 | +0,31 |
| m1 (momentum 1 mes) = RS vs índice en ranking | +0,04 | +0,02 | +0,06 |
| m1 + volRatio | +0,01 | −0,06 | −0,05 |
| Flow Score | +0,05 | +0,10 | +0,21 |
| Early Flow | +0,09 | +0,20 (t 3,1) | +0,34 (2 fechas) |
| Koncorde blue_z | +0,01 | +0,03 | +0,14 |

Con una sola referencia (SPY), la fuerza relativa frente al índice ordena igual que el retorno bruto: el benchmark 2
solo se diferencia del 1 si se mide frente al sector.

### 8.4 Diseño propuesto (pendiente de autorización)
Preregistro antes de calcular, en `wiki/PREREGISTRO_DETECCION_ROTACIONES_V1.md`:
- **Universos**: (a) 518 valores S&P 500/NDX 2015-2026 (caché existente; sesgo de supervivencia declarado);
  (b) 11 ETFs sectoriales + 6 índices + 4 materias primas, 2005-2026; (c) portfolio solo como descriptivo.
- **Señales**: B1 momentum 5 y 20 ses.; B2 RS vs índice y vs ETF de su sector (21/63 ses.); B3 B2 + volumen relativo
  20/60; B4 Flow Score, Early Flow (umbrales del código: 4 y 7), Koncorde acumulación/alineación, rot_score, RFL del
  sector.
- **Entrada ejecutable**: apertura de la sesión siguiente. Horizontes 5/10/20/40 sesiones. Coste 0,2 %.
- **Métricas**: rank IC diario (t con fechas no solapadas o Newey-West); exceso del top 5/10/20 vs universo y vs su
  sector; acierto; MFE/MAE desde la entrada; estabilidad del ranking (solape del top 20 entre semanas).
- **Liderazgo (definición fija)**: entrar en el quintil superior de RS de 63 sesiones vs SPY y permanecer ≥ 20
  sesiones. Falso arranque: entrar y salir antes de 10 sesiones. Anticipación = sesiones entre la primera señal y la
  entrada en el quintil; "recorrido restante" = retorno desde la entrada ejecutable hasta el máximo de los 40
  siguientes, y cuánto había subido ya en las 20 anteriores.
- **Validación**: desarrollo 2016-2020, prueba 2021-2026 una sola vez; resultados por régimen (SPY sobre/bajo SMA200);
  agrupación por fecha.
- **Criterio de éxito**: una señal B4 solo cuenta si en prueba supera a B1-B3 en IC y en exceso del top 10, con t ≥ 2,
  y deja MFE/MAE ≥ 1,5 desde la entrada.
- **Coste**: sin descargas para (a) y (b); unas horas de desarrollo; ningún cambio en producción.

---

## 9. Lagunas, por nivel

### Nivel 1 — datos que ya existen y no se aprovechan
| Mejora | Problema que resuelve | Detecta antes o confirma | Validación |
|---|---|---|---|
| Ejecutar §8.4 sobre los cachés ya descargados | No sabemos si algo supera al momentum | — | Es la validación |
| Persistir Cycle Tracker y matriz en un script del pipeline | Hoy no se puede reconstruir qué mostraban | — | Permite medirlos |
| Medir Koncorde blue_z/accel con los retornos ya rellenos (16 000 filas) | Koncorde lleva 4 meses registrando sin evaluarse | Antes | IC por fecha, preregistrado |
| Corregir el componente de compresión de ATR de Early Flow (comparar con la media de 20-60 sesiones, no con ayer) | Hoy es ruido | Antes | Solo tras §8.4, con preregistro |

### Nivel 2 — obtenibles con las fuentes actuales (Yahoo, gratis)
| Mejora | Aporta | Detecta antes o confirma | Histórico | Validación |
|---|---|---|---|---|
| **Breadth por sector sobre componentes** (S&P 500 por GICS: % por encima de SMA50, % con RS 21 > RS 63, nuevos máximos/mínimos, dispersión) | Distinguir mejora amplia de un valor estrella | Antes (hipótesis) | 10 años con el caché | ¿El breadth del sector anticipa el RS del ETF sectorial? |
| RS de cada acción **vs su ETF sectorial** | Liderazgo dentro de la industria | Antes | 10 años | Comparar con RS vs índice |
| Concentración del liderazgo (peso de los 5 mayores en el retorno del sector) | Rotaciones estrechas vs amplias | Confirma | 10 años | Descriptivo + IC |
| Valor negociado (precio × volumen) relativo agregado por sector | Volumen comparable entre valores | Confirma | 10 años | IC vs B3 |
| Ampliar el universo a S&P 1500 o Russell 1000 + ETFs de industria (SMH, KRE, XOP, ITB, IGV…) | Representatividad | — | Yahoo, 10-20 años | — |

### Nivel 3 — fuentes externas nuevas
| Mejora | Aporta | Coste estimado | Dificultad | Validación |
|---|---|---|---|---|
| **Flujos de ETF** (shares outstanding diarios × NAV: creaciones/reembolsos) | La única medida observada de entrada de capital por sector | Gratis parcial (webs de emisores SPDR/iShares publican shares outstanding diarios, sin histórico largo); de pago con histórico (ETF.com, Bloomberg, FactSet) | Media | ¿Los flujos netos del ETF sectorial preceden a su RS? |
| 13F institucional | Posiciones trimestrales con 45 días de retraso | Gratis (SEC) | Alta | Solo confirmación |
| Volumen de opciones por lado / OCC (desglose de clientes) | Posicionamiento | De pago (Cboe DataShop) | Alta | Ya se intentó con GEX sin benchmark |
| Microestructura (operaciones clasificadas, bloques) | Presión compradora real | De pago | Muy alta | — |

---

## 10. Respuestas al encargo

| | Pregunta | Clasificación | Respuesta |
|---|---|---|---|
| **A** | ¿Identifica qué activos e industrias mejoran su comportamiento relativo? | **Parcialmente disponible** | Lo describe bien a nivel de ETF sectorial y dentro de los 130 tickers (RFL, rotación, Cycle). No a nivel de industria con componentes ni para el mercado general. Describir no es anticipar. |
| **B** | ¿Identifica de forma consistente cambios de liderazgo entre sectores? | **Demostrado con datos — en sentido negativo** | RFL (10 años) y rot_score (20 años) no ordenan el rendimiento futuro de sectores; hay reversión a 1-4 semanas. |
| **C** | ¿Distingue acumulación incipiente de momentum desarrollado? | **Capacidad implementada, no validada** | Early Flow se activa antes que el momentum (m1 mediano 0 % vs +12 %); Flow Score es momentum. Koncorde "acumulación" se activa en caída libre. Early Flow ≥ 4 no tiene ventaja en grandes valores; ≥ 7 sin probar fuera de los datos en vivo. |
| **D** | ¿Cuánto depende del precio? | **Demostrado con datos** | Flow Score: 98,5 % explicado por w1/m1. Early Flow: correlación 0,84 con sus partes de precio; el resto es Koncorde, también derivado de OHLCV. RFL: 100 % precio. Bloque de volumen de rot_score: IC ≈ 0. Ninguna fuente independiente. |
| **E** | ¿Con cuánta anticipación detecta movimientos que se consolidan? | **No evaluable con los datos actuales** | Solo el estudio de ETFs: señal temprana ~22 semanas antes de la confirmación, α modesto (+2,4 pp a 13 sem., n 46). Falta la definición de liderazgo y el estudio por episodios (§8.4). |
| **F** | ¿Tasa de falsas señales y por régimen? | **Parcialmente disponible** | RFL: aciertos 46-52 % en todos los regímenes. En vivo: Koncorde acumulación 58 % de fallos a 20 ses.; Early Flow ≥ 7 33 %. Sin desglose por régimen para acciones. |
| **G** | ¿Supera a un screener de momentum, RS y volumen? | **Demostrado con datos — no, donde se ha medido** (ETFs 20 años, RFL 10 años, Early Flow ≥ 4 en S&P 500) · **No evaluable** para el universo propio y Early Flow ≥ 7 | §8.2 y §8.3. |
| **H** | Tres mejoras prioritarias | — | Ver abajo. |

### H — Tres mejoras priorizadas

1. **Validación §8.4 con los datos ya descargados (Nivel 1, horas, sin coste).** Primero Early Flow ≥ 7 frente a
   momentum/RS/RS+volumen en el S&P 500/NDX 2016-2026. Es la única pista viva y se puede confirmar o descartar sin
   tocar nada. Hipótesis: el decil superior de Early Flow ≥ 7 bate al decil superior de momentum 20 ses. en exceso a
   20 sesiones fuera de muestra.
2. **Breadth sectorial sobre componentes, con histórico (Nivel 2, gratis).** Es lo que falta para responder la
   pregunta de fondo ("sector que mejora en amplitud antes de destacar en rentabilidad"). Hipótesis: un aumento del %
   de componentes con RS 21 > RS 63 anticipa la entrada del ETF sectorial en el quintil superior de RS 63 en ≥ 10
   sesiones, mejor que el propio RS del ETF.
3. **Una medida observada de flujo: creaciones/reembolsos de ETFs sectoriales (Nivel 2/3).** Sin ella, "flujo de
   capital" seguirá siendo un nombre para indicadores de precio. Empezar por capturar a diario los shares outstanding
   de los 11 SPDR (gratis, desde hoy) y valorar un proveedor con histórico solo si la captura muestra algo. Hipótesis:
   flujos netos de 20 días en el quintil superior preceden a una mejora del RS del sector.

Lo que **no** recomiendo: añadir indicadores técnicos nuevos derivados de OHLCV sobre el universo de 130 tickers. Ya
hay muchos y los medidos no superan al momentum.

---

## Anexo — reproducibilidad
Scripts de solo lectura usados en esta auditoría (fuera del repo, en el directorio temporal de la sesión):
- `audit_live.py`: fases, eventos, R² y IC sobre `docs/data/portfolio_daily_snapshot.jsonl` (indexado por `asOf`,
  última captura por vela, FXPO.L excluido; retornos futuros contados en velas capturadas, que pueden saltar días).
- `rot_ic.py`: IC de rot_score, bloques y momentum sobre `backtest/data/processed/signal_alphas.parquet` (modo A,
  SPY excluido, α futuro verificado contra `prices_weekly.parquet`).
Ninguno escribe en el repo. Pueden incorporarse a `research/` si se aprueba §8.4.
