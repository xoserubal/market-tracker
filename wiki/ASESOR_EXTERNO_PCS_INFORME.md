# Informe PCS (Pick Conviction Score) — para evaluación por asesor externo

**Fecha:** 2026-08-05
**Autor:** análisis interno (Claude Code) sobre el código real del sistema
**Propósito:** documento autocontenido para que un tercero pueda evaluar el
diseño del PCS — qué mide, cómo se calcula exactamente, qué supuestos hace, y
qué riesgos conocidos tiene — sin necesitar acceso al repositorio.

---

## 1. Qué es el PCS y qué problema resuelve

El **Pick Conviction Score (PCS)** es un score compuesto de 0 a 100 (en la
práctica, ~95 — ver §5) que se calcula para cada uno de los ~91-128 tickers del
universo de este sistema, una vez por corrida del pipeline (2×/día). Vive en
`scripts/pcs_calculator.py`, se calcula en Python puro sin ningún modelo de IA
de por medio, y su output (`docs/data/ai_candidates.json`) es exactamente lo
que luego se le entrega a un LLM (Grok/Mimo/Haiku, según el momento) para que
decida si selecciona, vigila o rechaza cada candidato.

**El problema que resuelve dentro de la arquitectura del sistema:** el diseño
explícito del proyecto es que el LLM **no** decide "qué comprar" desde cero —
eso se considera demasiado propenso a alucinación y a decisiones caprichosas.
En su lugar, el sistema separa el problema en capas, cada una respondiendo una
pregunta distinta:

```
MacroScore                     → ¿hay permiso de riesgo? (campo de juego)
rot_score + relative strength  → ¿hacia dónde se mueve el capital?
PCS (este documento)           → ¿qué vehículo concreto lo captura?
LLM (Grok/Mimo/Haiku)          → ¿la señal es suficientemente limpia para actuar?
```

El PCS es la capa que **traduce todas las señales cuantitativas de un ticker
en un único número comparable**, para que (a) el LLM reciba un ranking ya
depurado en vez de datos crudos, y (b) el sistema pueda definir umbrales
objetivos por cartera (ver §6) sin depender del juicio del modelo para decidir
si algo "es suficientemente fuerte".

**Lo que el PCS explícitamente NO intenta responder:** no mide "¿es buena
entrada ahora?" (eso es `extension_risk`, un campo aparte, deliberadamente no
mezclado con el PCS) ni "¿hay demasiada concentración en este tema?" (eso es
`theme_concentration_risk`, calculado fuera del PCS). El PCS es, por diseño,
una medida de **fuerza de la señal**, no de **timing de entrada** ni de
**gestión de cartera**.

---

## 2. De dónde vienen los datos que consume el PCS

El PCS no calcula casi nada de mercado por sí mismo — casi todos sus inputs
son señales ya computadas por otros módulos del pipeline, y el PCS solo las
pondera y combina. Esto es relevante para el asesor porque significa que
cualquier defecto en esos módulos upstream se propaga al PCS sin que el propio
`pcs_calculator.py` pueda detectarlo:

| Fuente | Contenido | Quién lo calcula |
|---|---|---|
| `docs/data/macro_history.json` | MacroScore actual + tendencia + flag de emergencia | módulo de régimen macro (fuera de este documento) |
| `docs/data/rotation_signals.json` | `rot_score` de ETFs/proxies sectoriales | módulo de rotación (`backtest/src/rotation`) |
| `docs/data/stock_candidates.json` | `rot_score`, `ret_4w_vs_spy`, `ret_13w_vs_spy`, `streak_weeks`, componentes CMF/OBV/MACD/RSI por ticker individual | mismo módulo de rotación, aplicado a acciones |
| `docs/data/universe.json` | metadata estática: tema, subtema, región, prioridad, si es "tradable" | mantenido a mano / `sync_universe.py` |
| Yahoo Finance (en vivo, dentro del propio `pcs_calculator.py`) | OHLCV ~2 meses, usado solo para las señales diarias (DEMS, extension_risk) | `fetch_daily_metrics()`, único cálculo de mercado que hace el propio PCS |

El único cálculo de precios que hace el `pcs_calculator.py` directamente es
`fetch_daily_metrics()` (RSI14, ATR14, retornos a 5/10/20 días vs SPY) — y ese
cálculo **no alimenta el PCS**, solo alimenta DEMS y `extension_risk`, dos
campos informativos separados (ver §7). Todo lo que sí entra en el PCS
(componentes A-F) viene de los tres JSON de la tabla, ya precalculados antes de
que `pcs_calculator.py` se ejecute.

---

## 3. Los 6 componentes — fórmula exacta

El PCS es una suma de 6 componentes, cada uno con su propia función en el
código (`score_a` a `score_f`), evaluados de forma completamente
independiente entre sí — no hay ningún término de interacción ni
normalización conjunta. A continuación la fórmula exacta de cada uno, tal como
está en el código hoy.

### A — Macro Permission (`score_a`)

*Pregunta que responde: ¿el régimen macro permite tomar riesgo ahora?*

```
score = MacroScore actual (docs/data/macro_history.json → latest.score)

base = 13.0 si score >= 70
       10.0 si score >= 55
        6.0 si score >= 40
        2.0 en otro caso

base += 1  si trend == "Improving"
base -= 1  si trend == "Deteriorating"
base -= 3  si flag_emergency_mode está activo (última fila de macro_history)

A = clamp(base, 0, 15)
```

Es el único componente que **no depende del ticker individual** — todos los
candidatos de una misma corrida reciben exactamente el mismo valor de A (se
confirma en los datos reales de hoy, ver §5: A=14.00 en los 128 candidatos, sin
excepción).

### B — Theme Flow (`score_b`)

*Pregunta que responde: ¿está entrando capital al sector/tema de este ticker?*

Camino primario (si el ticker tiene un `theme_proxy` — normalmente un ETF
sectorial — presente en `rotation_signals.json`):

```
rot = rot_score del proxy

pts = 22.0 si rot >= 7
      18.0 si rot >= 6
      14.0 si rot >= 5
      10.0 si rot >= 4
       6.0 si rot >= 3
       3.0 en otro caso

pts += 2  si la señal del proxy es "COMPRA"   (tope 25)
pts += 1  si la señal del proxy es "ACUMULAR" (tope 25)
```

Camino de respaldo (si no hay `theme_proxy`): promedio de `ret_13w_vs_spy` de
todos los tickers del mismo `theme` en `stock_candidates.json`, mapeado a
puntos de 4.0 a 18.0 por tramos. Si tampoco hay eso: 10.0 fijo, flag
`no_theme_data`.

### C — Individual Relative Strength (`score_c`)

*Pregunta que responde: ¿este ticker concreto bate a SPY?*

```
combined = 0.6 × ret_13w_vs_spy + 0.4 × ret_4w_vs_spy

pts = 23.0 si combined >= 15   (rs_strong_leader)
      19.0 si combined >=  7   (rs_leader)
      15.0 si combined >=  2   (rs_outperform)
      11.0 si combined >= -2   (rs_neutral)
       7.0 si combined >= -7   (rs_underperform)
       3.0 en otro caso        (rs_laggard)

C = clamp(pts, 0, 25)
```

Si no hay dato de `ret_4w_vs_spy` ni `ret_13w_vs_spy`: 8.0 fijo.

### D — Individual Flow / Rotation (`score_d`)

*Pregunta que responde: ¿hay flujo técnico (CMF/OBV/volumen) confirmando?*

```
base = 17.0 si rot_score >= 8
       13.0 si rot_score >= 6
        9.0 si rot_score >= 4
        5.0 si rot_score >= 2
        2.0 en otro caso

flow_bonus   = min(3.0, (cmf_pts + obv_pts + vol_rel_pts) × 0.75)
timing_bonus = 0.5 si no_ext_pts >= 1, si no 0

D = clamp(base + flow_bonus + timing_bonus, 0, 20)
```

Si no hay `rot_score` para el ticker: 7.0 fijo.

### E — Early Acceleration (`score_e`)

*Pregunta que responde: ¿el ticker está acelerando antes de que el movimiento
sea obvio?*

```
si is_early_rotation o cluster_has_confirmed_rotation:  E = 9.0
sino si macd_pts>=1 y rsi_pts>=1:                        E = 7.0 (si streak_weeks>=3) / 6.0
sino si macd_pts>=1 o  rsi_pts>=1:                       E = 4.0
sino si no hay datos de este ticker en absoluto:         E = 3.0
sino:                                                    E = 2.0
```

**Nota:** a diferencia de A-D y F, `score_e` **no aplica ningún `clamp()`** —
devuelve directamente uno de estos 5 valores fijos. El máximo posible es 9.0,
no 10.0 (no existe ninguna combinación de inputs que produzca más de 9.0).

### F — Data Quality / Tradability (`score_f`)

*Pregunta que responde: ¿hay suficiente dato como para fiarse del resto del
score?*

```
si meta.tradable == False:  F = 0.0  (y el ticker queda "no eligible", ver §4)

F = 3.0  si el ticker tiene entrada en stock_candidates.json
F += 1.5 si el ticker tiene entrada en rotation_signals.json
F += 0.5 si priority == "high"
F -= 1.0 si priority == "low"

F = clamp(F, 0, 5)
```

---

## 4. Agregación final y regla de elegibilidad

```
PCS = A + B + C + D + E + F        (redondeado a 1 decimal)
eligible = meta.tradable AND F > 0
```

**Observación sobre `eligible`:** es una barrera muy baja — solo excluye
tickers explícitamente marcados `tradable: false` en `universe.json`, o
tickers sin absolutamente ningún dato de `stock_candidates.json` ni
`rotation_signals.json` combinado con prioridad "low" (el único camino para
que F llegue a 0 con datos parciales). El filtrado real no ocurre aquí — ocurre
después, comparando el PCS contra el umbral de cada cartera (§6). `eligible`
esencialmente solo dice "esto no es basura sin datos", no "esto es una buena
señal".

---

## 5. Verificación: el techo real del PCS no es 100, y no coincide con lo documentado

Esto no estaba señalado en ningún sitio del proyecto — se descubrió al
verificar la fórmula línea por línea para este informe, trazando el máximo
alcanzable de cada componente contra sus propias ramas de código (no contra
los comentarios de cabecera del código, que dicen "0–15", "0–25", etc. de forma
aspiracional pero no siempre alcanzable).

| Componente | Comentario en el código | `CLAUDE.md` (documentado) | **Techo real (trazado por rama)** | Máximo observado hoy (128 tickers reales) |
|---|---|---|---|---|
| A | 0–15 | 15 | **14.0** | 14.0 |
| B | 0–25 | 22 | **24.0** | 24.0 |
| C | 0–25 | 23 | **23.0** | 23.0 |
| D | 0–20 | 18.5 | **20.0** | 19.8 |
| E | 0–10 | 7 | **9.0** | 7.0 *(ningún ticker de hoy tiene `is_early`)* |
| F | 0–5 | 3.5 | **5.0** | 5.0 |
| **Suma** | **100** | **89.0** | **95.0** | — |

Tres números distintos para lo que debería ser un solo hecho objetivo. Ninguno
de los tres coincide con los otros dos. La columna "techo real" se verificó
dos veces: analíticamente (trazando cada rama del código) y empíricamente
(máximo realmente observado hoy sobre los 128 candidatos vigentes — coincide
exactamente salvo en E, donde hoy no hay ningún ticker en rotación temprana
activa para alcanzar el 9.0 teórico).

**Por qué importa esto más allá de ser un detalle cosmético:** los umbrales de
cartera (§6) están definidos como números absolutos (82, 75, 68, 62) asumiendo
implícitamente una escala de referencia de "sobre 100". Si el techo real es
95, esos umbrales son ligeramente más exigentes de lo que su propio diseño
pretendía (82/95 = 86% de conviction real, no 82% como sugiere la cifra). Es
un efecto pequeño, pero es exactamente el tipo de discrepancia silenciosa que
un asesor externo debería poder detectar y que el equipo interno no había
verificado hasta ahora.

---

## 6. Cómo se usa el PCS: umbrales por cartera

El PCS no decide nada por sí mismo — define el **campo de candidatos elegibles
por cartera**, dentro del cual el LLM elige. Cuatro carteras activas (más una
de control, ver limitación en §7):

| Cartera | PCS umbral (para aparecer) | PCS mín. entrada | Máx. posiciones | Tamaño posición |
|---|---|---|---|---|
| HIGH_CONVICTION | 85 | 82 | 8 | 8–15% |
| CONFIRMED_FLOW_LEADERS | 78 | 75 | 12 | 5–10% |
| EARLY_ROTATION | 70 | 68 | 15 | 4–8% |
| MACRO_THEMATIC_BENEFICIARIES | 65 | 62 | 20 | 3–6% |
| REJECTED_HIGH_SCORE *(control)* | 75 | 75 | 20 | 5% |

"Umbral" y "mínimo de entrada" son distintos a propósito: un ticker necesita
cruzar el umbral más alto para *entrar en el radar* de una cartera, pero una
posición ya abierta solo se cierra si cae por debajo del **mínimo de entrada**
(más bajo) — evita que ruido de un día alrededor del umbral fuerce entradas y
salidas constantes. La lógica de salida completa vive en `paper_trading.py`,
fuera de este componente.

**Dato real de hoy** (macro: Bull Maduro, MacroScore 85.4, Improving) — el PCS
más alto de los 128 candidatos es **NBIS con 79.5**, por debajo incluso del
umbral de HIGH_CONVICTION (85) y de CONFIRMED_FLOW_LEADERS (78). Con el techo
real siendo 95 (§5), un PCS de 79.5 representa el 83.7% del máximo posible —
alto en términos relativos, pero insuficiente para la cartera más exigente
bajo los umbrales absolutos actuales.

---

## 7. Riesgos y limitaciones ya conocidos (documentados en el proyecto antes de este informe)

- **Doble conteo entre componentes**, señalado en `CLAUDE.md` desde el
  diseño original: `ret_4w_vs_spy` entra en C directamente, y también
  correlaciona con `rot_score` (que entra en B y D) y con `streak_weeks` (que
  entra en E). No hay ningún término de ortogonalización — si el mercado
  favorece "momentum reciente" de forma generalizada, ese mismo hecho se
  premia 3 o 4 veces en componentes distintos, inflando el PCS de esos
  tickers más de lo que su fuerza real de señal justificaría. Pendiente de
  análisis formal desde el diseño original (roadmap "semana 7": "Análisis de
  correlación entre componentes PCS (A-F) y rendimiento posterior").
- **`extension_risk` y `theme_concentration_risk` deliberadamente fuera del
  PCS** — decisión de diseño explícita, no un descuido: el PCS mide fuerza de
  señal, no timing de entrada ni concentración de cartera. Correcto por
  diseño, pero significa que un PCS alto no protege en absoluto contra entrar
  tarde en un movimiento ya agotado.

## 8. Evidencia empírica reciente — el PCS no ordena resultados por encima del umbral

Esto **no** estaba documentado antes de esta semana. Al diagnosticar el
underperformance de CONFIRMED_FLOW_LEADERS (`wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md`,
2026-08-05) se cruzó el PCS de entrada contra el retorno real a 1 mes de cada
pick, para las 5 carteras con datos suficientes:

| Cartera | n | corr(PCS, ret_1m) |
|---|---|---|
| CONFIRMED_FLOW_LEADERS | 53 | -0.199 |
| HIGH_CONVICTION | 26 | -0.310 |
| EARLY_ROTATION | 30 | +0.314 |
| MACRO_THEMATIC_BENEFICIARIES | 11 | -0.177 |
| MIMO_SHADOW | 16 | -0.411 |
| **GLOBAL (las 5 combinadas)** | **136** | **-0.007** |

El signo cambia de cartera a cartera y la correlación global es
esencialmente nula. En CFL específicamente, por tramos, el tramo de PCS más
alto (81+) es el que peor resultado obtuvo (-8.39% de retorno medio, 17.6% de
aciertos), peor que el tramo justo por debajo del umbral de entrada (n=6,
+4.49%, aunque con muestra muy pequeña).

**Lectura prudente (no la única posible, de ahí la pregunta al asesor en §9):**
por encima del umbral de cada cartera, el PCS parece funcionar como **puerta**
(sí discrimina lo suficientemente fuerte para calificar) pero no como
**ranking** (no predice cuál de los que califican rendirá mejor). Esto no
estaba puesto a prueba hasta este análisis — la correlación entre PCS y
rendimiento posterior siempre fue un supuesto implícito del diseño, nunca
verificado con datos reales hasta ahora.

Limitaciones de esta evidencia: n=136 sobre ~3 meses, un solo régimen de
mercado (Bull Maduro/Bull Pleno mayormente), sin controlar por fecha ni por
tema. No es una prueba definitiva de que el PCS no ordene — es la primera
medición real de que la pregunta importa.

---

## 9. Preguntas concretas para el asesor

1. **Sobre el techo real (§5):** ¿recalibrar los umbrales de cartera contra el
   techo real (95) en vez del nominal (100), o es un efecto demasiado pequeño
   para justificar el cambio? ¿Hay algún riesgo en que "PCS sobre 100" sea una
   ficción de framing que nadie cuestiona?
2. **Sobre la falta de poder de ranking (§8):** con corr global -0.007 por
   encima del umbral, ¿qué evidencia adicional pedirías antes de aceptar la
   lectura "es una puerta, no un ranking"? ¿Hay una forma de testear
   directamente si el PCS *debería* ordenar por diseño, o si eso nunca fue una
   promesa razonable de un score de este tipo?
3. **Sobre el doble conteo (ret_4w_vs_spy / rot_score / streak_weeks):** ¿cómo
   priorizarías atacar esto — ortogonalizar los componentes (p.ej. regresión
   para extraer la parte no explicada por los demás), reducir pesos a mano, o
   dejarlo en fase de observación hasta tener más datos con `ret_3m` (que
   empieza a estar disponible esta misma semana)?
4. **Sobre el diseño de los componentes en sí:** A es idéntico para todos los
   tickers de una misma corrida (§3) — ¿tiene sentido que "permiso macro" sea
   un componente del PCS individual, o debería vivir fuera del PCS (como
   `extension_risk`) ya que no aporta ninguna capacidad de diferenciar entre
   tickers en un momento dado?
5. **Sobre E (Early Acceleration):** el salto de 9.0 (is_early) a 7.0/6.0
   (macd+rsi positivos) es un salto discreto grande sin gradiente intermedio.
   ¿Es preferible una función continua, o el diseño discreto es deliberadamente
   más robusto a ruido en un componente que ya es el más pequeño (máx 9 de
   ~95)?
6. **Meta-pregunta:** dado que este es un sistema de paper trading en fase de
   observación explícita (principio del proyecto: "no añadir complejidad antes
   de tener datos que la justifiquen"), ¿el PCS necesita cambios ahora, o el
   siguiente paso correcto es simplemente esperar a tener `ret_3m` real (~3
   meses, disponible desde esta semana para los primeros picks) antes de tocar
   la fórmula?

---

## 10. Apéndice — snapshot real de hoy (2026-08-05)

Contexto macro: MacroScore 85.4, régimen "Bull Maduro", tendencia "Improving".
128 candidatos totales.

**Top 5 por PCS:**

| Ticker | PCS | A | B | C | D | E | F |
|---|---|---|---|---|---|---|---|
| NBIS | 79.5 | 14.0 | 14.0 | 23.0 | 19.0 | 6.0 | 3.5 |
| WCP.TO | 77.5 | 14.0 | 24.0 | 15.0 | 14.5 | 7.0 | 3.0 |
| YPF | 76.5 | 14.0 | 14.0 | 19.0 | 19.0 | 7.0 | 3.5 |
| SYK | 75.0 | 14.0 | 14.0 | 19.0 | 19.0 | 6.0 | 3.0 |
| MLX.AX | 73.5 | 14.0 | 8.0 | 23.0 | 18.5 | 7.0 | 3.0 |

**Distribución por componente (128 candidatos):**

| Componente | Máximo hoy | Mínimo hoy | Media |
|---|---|---|---|
| A | 14.00 | 14.00 | 14.00 |
| B | 24.00 | 4.00 | 11.84 |
| C | 23.00 | 3.00 | 9.11 |
| D | 19.80 | 2.00 | 8.90 |
| E | 7.00 | 2.00 | 5.03 |
| F | 5.00 | 0.00 | 3.04 |

---

## 11. Nota sobre reproducibilidad

Todas las fórmulas de §3-4 son transcripción literal de `scripts/pcs_calculator.py`
(671 líneas, leído íntegro para este informe, sin resumir ni interpretar
ninguna rama). Los techos de §5 se verificaron dos veces — trazado analítico
de cada rama y verificación empírica contra `docs/data/ai_candidates.json`
real del día. Los datos de §8 y §10 son reales, no simulados. No se modificó
ningún archivo del sistema para producir este informe.
