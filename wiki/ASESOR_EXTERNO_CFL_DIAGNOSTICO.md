# Diagnóstico CONFIRMED_FLOW_LEADERS — documento para asesor externo

**Fecha:** 2026-08-05
**Autor:** análisis interno (Claude Code) sobre datos reales del sistema
**Pregunta que se somete a revisión:** ¿cuál es la mejor mejora para la cartera
CONFIRMED_FLOW_LEADERS — entrar antes, entrar igual pero salir antes, o cambiar
el criterio de selección? ¿Y tenemos datos suficientes para decidirlo?

Este documento es autocontenido: incluye contexto del sistema, metodología,
datos crudos y hallazgos, para que un tercero pueda criticar el razonamiento sin
acceso al repositorio.

---

## Actualización 2026-08-05 — implementado tras revisión interna

El usuario revisó este diagnóstico y aprobó un plan acotado (P0–P3, sin activar
ningún stop real todavía). Implementado el mismo día:

- **P0 — bug de duplicados corregido en la fuente.** `_log_shadow_picks()`
  (`paper_trading.py`) ahora deduplica por `(model, ticker, portfolio, pcs)`
  dentro del mismo día antes de escribir, evitando que re-ejecuciones manuales
  (el caso real que causaba las 32 filas duplicadas de este documento) se
  registren como observaciones de mercado independientes. `compare_vs_baselines.py`
  gana el mismo dedup a nivel de análisis (`dedup_same_day_reruns()`), para
  limpiar también el histórico ya escrito antes del fix.
- **P2 — `extension_risk` reconstruido retroactivamente**, sin look-ahead
  (`scripts/reconstruct_extension_risk_historical.py`), usando exactamente la
  misma fórmula de puntuación que `pcs_calculator.compute_extension_risk()`
  (importada directamente, no reimplementada). Validado contra 4 picks que ya
  tenían el valor calculado en vivo (post-fix 2026-07-02): coincidencia exacta,
  incluidos los puntos. **Primer resultado real** (n pequeño, no concluyente):
  cruzando esto con CFL, `extreme` sale claramente peor que el resto
  (ret_1m medio -16% a -18%, 0% de aciertos, n=4-5) pero `low`/`medium`/`high`
  no muestran una escalera limpia — no hay evidencia todavía de que "entrar
  extendido" sea la explicación principal, solo de que el extremo superior es
  malo. Sigue pendiente la pregunta 3 de la sección 6 de este documento.
- **P1 — `scripts/cfl_followthrough_shadow.py`**, shadow-only: evalúa cada
  posición abierta de CFL a los ~5 días hábiles de la entrada contra 4 reglas
  (`ret_1w<0` como regla primaria — la única validada arriba —, `ret_1w<-3`,
  `ret_1w_vs_spy<-2`, ruptura ajustada por ATR de entrada), sin cerrar nada.
- **P3 — `scripts/cfl_reentry_cooldown_shadow.py`**, shadow-only: si un ticker
  falla follow-through a 1 semana, ¿qué habría pasado si CFL no pudiera
  reseleccionarlo en las siguientes 18 sesiones? Corrido retroactivo sobre las
  18 selecciones activas limpias de CFL: solo 2 habrían sido bloqueadas
  (SASK.V, URI) — muestra demasiado pequeña para concluir si el cooldown
  ayuda o no.

Los tres scripts nuevos corren en el pipeline (`market-update.yml`, Steps
10e/10f/10g, `continue-on-error: true`) tras Step 10b (update_performance).
Nada de esto activa un stop, cambia el umbral de PCS ni cierra posiciones
reales — sigue siendo observación pura, conforme a lo acordado. Documentado
en detalle en `CLAUDE.md`, sección "Diagnóstico CONFIRMED_FLOW_LEADERS...".

---

## 1. Contexto mínimo del sistema

Sistema de paper trading donde señales cuantitativas se calculan primero y un LLM
actúa como filtro final (no predice mercado, filtra señales ya calculadas):

```
MacroScore                     → permiso de riesgo (campo de juego)
rot_score + relative strength  → hacia dónde se mueve el capital
PCS (Pick Conviction Score)    → qué vehículo concreto lo captura (0-100)
IA (Grok/Mimo/Haiku)           → comité que decide si la señal es suficientemente limpia
```

**PCS** se compone de 6 bloques (macro_permission 15, theme_flow 22,
individual_rs 23, individual_flow 18.5, early_acceleration 7, data_quality 3.5).

Hay 5 carteras con distintos umbrales. La que nos ocupa:

| Cartera | PCS umbral | PCS mín entrada | Máx pos | Tamaño |
|---|---|---|---|---|
| HIGH_CONVICTION | 85 | 82 | 8 | 8–15% |
| **CONFIRMED_FLOW_LEADERS** | **78** | **75** | **12** | **5–10%** |
| EARLY_ROTATION | 70 | 68 | 15 | 4–8% |
| MACRO_THEMATIC_BENEFICIARIES | 65 | 62 | 20 | 3–6% |

CFL se rige por **métricas semanales** (confirmación), no por señales diarias.
Su tesis es "líder de flujo ya confirmado" — no entrada temprana.

**Salidas actuales (implementadas 2026-06-09):** el modelo revisa posiciones
abiertas y decide HOLD/EXIT. Criterio de EXIT: `pcs < pcs_min_entry AND
streak_weeks <= 1`, OR `rot_score <= 2`, OR `pcs < 62`, OR `left_universe`.
No hay stop por precio ni por tiempo.

El universo son ~91-128 candidatos: mucha small cap, mineras, TSX Venture,
utilities argentinas, crypto miners. ATR de varios puntos es normal.

---

## 2. Metodología y limpieza de datos (importante para juzgar la fiabilidad)

Fuente: `docs/data/shadow_picks.jsonl`, 246 filas totales, picks del 2026-05-08
al 2026-08-04. Campos de rendimiento rellenados por `update_performance.py`
contra precios reales de yfinance (`ret_1d/3d/1w/2w/1m/3m`, `vs_spy_1m`,
`max_gain_1m`, `max_drawdown_1m`).

Se aplicaron **tres filtros de limpieza**, y cada uno reduce sustancialmente la
muestra. Esto es central para valorar cuánta confianza merece lo que sigue:

**(a) Exclusión del bloque zombi del 2026-06-10 (9 posiciones).**
El cierre de posiciones no existía como funcionalidad hasta el 2026-06-09. Nueve
posiciones abiertas en mayo se quedaron sin ninguna vía de salida durante semanas
y se cerraron todas de golpe el día siguiente a implementarse la función. No
reflejan decisiones del modelo sino un hueco de infraestructura. Todas negativas
(-6.8% a -37.6% a 1 mes). Excluidas: NVDA/MSTR (08-05), COIN (09-05), KOS (15-05),
SU (16-05), ASPI (27-05), EOSE (29-05), SASK.V (30-05), RCAT (30-05).

**(b) Duplicados reales.** Se encontraron 26 filas duplicadas en CFL: mismo
modelo, mismo ticker, misma fecha, mismos valores (p.ej. SASK.V 2026-06-20 tiene
4 filas idénticas de grok-4.3). Parece un bug de logging (el pipeline corre 2×/día
y aparentemente re-loguea). **Esto es un hallazgo colateral que conviene corregir
en el propio sistema**, independientemente de este análisis.

**(c) Colapso a eventos de mercado independientes.** Cuando grok, mimo y haiku
eligen el mismo ticker el mismo día, generan 3 filas con retornos idénticos (es
el mismo evento de mercado). Promediarlas triplica el peso de ese evento. Para
las estadísticas se colapsa a pares únicos `(ticker, fecha)`.

**Resultado de la limpieza:**

```
106 filas CFL crudas
 -> 80 tras quitar duplicados exactos (modelo,ticker,fecha)
 -> 62 tras excluir el bloque zombi
 -> 52 eventos de mercado independientes (ticker+fecha únicos)
 -> 48 con ret_1w y ret_1m disponibles   <-- muestra de trabajo
    sobre 25 tickers distintos
```

**Limitaciones que el asesor debe tener presentes:**
- n=48 eventos sobre 25 tickers. Es poco.
- Periodo único: mayo–agosto 2026 (~3 meses), esencialmente un solo régimen.
- `ret_3m` está a `null` en el 100% de las filas — no hay horizonte largo todavía.
- Las reglas simuladas en §4 se ajustan sobre los mismos datos con los que se
  descubren. Riesgo de sobreajuste alto y no controlado (sin validación fuera de
  muestra, no hay datos suficientes para partirla).
- El modelo activo cambió durante el periodo (haiku → grok), así que la muestra
  mezcla selecciones de modelos distintos.
- `extension_risk`, `konc_*` y `theme_concentration_risk` están rellenos solo en
  4/106 filas (un bug documentado los dejó a null hasta 2026-07-02), así que **no
  se puede analizar si la extensión en la entrada explica el mal rendimiento** —
  que es justamente la variable más relevante para la hipótesis "entrar antes".

---

## 3. Hallazgos

### 3.1 El rendimiento es malo y es alpha negativo real, no beta de mercado

Muestra independiente (n=48):

| Métrica | Media | Mediana | % positivos |
|---|---|---|---|
| ret_1d | -1.20% | -0.92% | 39.6% |
| ret_1w | -2.56% | -2.65% | 37.5% |
| ret_1m | -4.85% | -5.08% | 35.4% |
| **vs_spy_1m** | **-5.08%** | -5.29% | 35.4% |
| max_gain_1m | +13.52% | +6.58% | — |
| max_drawdown_1m | -16.19% | -11.34% | — |

`ret_1m` (-4.85%) y `vs_spy_1m` (-5.08%) son casi idénticos: **el mercado no
explica el resultado**. Es underperformance genuina.

### 3.2 Las posiciones nacen mal, no se estropean con el tiempo

El retorno medio ya es negativo el **primer día** (-1.20%) y solo empeora.
No existe una fase inicial positiva que luego se devuelva.

Comparación con HIGH_CONVICTION (misma metodología), que sí recupera:

| | ret_1d | ret_1w | ret_2w | ret_1m |
|---|---|---|---|---|
| CFL | -1.20% | -2.56% | -0.40% | -4.85% |
| HIGH_CONVICTION | -0.94% | +0.03% | +2.08% | +1.15% |

### 3.3 La asimetría recorrido/caída es estructuralmente peor en CFL

Medianas por cartera (datos deduplicados):

| Cartera | max_gain | max_drawdown | ratio |
|---|---|---|---|
| **CONFIRMED_FLOW_LEADERS** | **+5.50%** | **-10.51%** | **0.52** |
| HIGH_CONVICTION | +14.54% | -14.03% | 1.04 |
| EARLY_ROTATION | +8.24% | -14.46% | 0.57 |
| MIMO_SHADOW | +4.50% | -4.50% | 1.00 |

CFL compra activos que, en el mes siguiente, ofrecen la mitad de recorrido al
alza que de caída. HIGH_CONVICTION compra activos con recorrido simétrico.
Además, **el 42.6% de los picks de CFL nunca suben más de un 5%** en todo el mes.

Esto apunta a un problema de **calidad de entrada**: no es que se gestionen mal
posiciones buenas, es que se entra en activos sin recorrido disponible.

### 3.4 El retorno a 1 semana predice fuertemente el de 1 mes

Es el hallazgo más robusto y el único consistente en **todas** las carteras:

| Cartera | corr(ret_1w, ret_1m) | negativos@1w que recuperan a 1m |
|---|---|---|
| CONFIRMED_FLOW_LEADERS | **+0.735** | 3/36 |
| HIGH_CONVICTION | +0.666 | 3/16 |
| EARLY_ROTATION | +0.545 | 5/22 |
| MIMO_SHADOW | +0.802 | 4/9 |

En la muestra independiente de CFL: corr **+0.723**; de 30 picks negativos a 1
semana, solo **2 acaban positivos al mes (6.7%)**; los 18 positivos a 1 semana
promedian **+10.47%** a un mes frente a **-14.04%** los negativos.

### 3.5 El PCS no ordena resultados (hallazgo incómodo)

Correlación PCS ↔ ret_1m por cartera:

| Cartera | n | corr(PCS, ret_1m) |
|---|---|---|
| CONFIRMED_FLOW_LEADERS | 53 | **-0.199** |
| HIGH_CONVICTION | 26 | -0.310 |
| EARLY_ROTATION | 30 | +0.314 |
| MACRO_THEMATIC_BENEFICIARIES | 11 | -0.177 |
| MIMO_SHADOW | 16 | -0.411 |
| **GLOBAL (todas)** | **136** | **-0.007** |

En CFL por tramos (muestra independiente, corr -0.261):

| Tramo PCS | n | ret_1m medio | % gana |
|---|---|---|---|
| <75 | 6 | +4.49% | 83.3% |
| 75–78 | 7 | -3.21% | 28.6% |
| 78–81 | 24 | -6.45% | 33.3% |
| 81+ | 17 | -8.39% | 17.6% |

El signo es inconsistente entre carteras y **globalmente nulo (-0.007)**. La
lectura prudente no es "PCS alto es malo" sino: **por encima del umbral, el PCS
no tiene poder de ordenación sobre el resultado**. Funciona como puerta
(elegibilidad), no como ranking. Los tramos extremos tienen n muy pequeño (6 y 17)
y el sesgo temporal (los PCS bajos se concentran en junio, mes distinto) podría
explicar parte del patrón — no se ha controlado por fecha.

Dato adicional: el campo `confidence` que emite el propio modelo tampoco
discrimina (high: -4.70%, medium: -3.83%; n=62/18) — la autoevaluación del LLM no
aporta información sobre el resultado.

### 3.6 Concentración y rotación excesiva

25 tickers distintos en 52 eventos. Los más repetidos: ASPI (11 entradas,
-30.57% medio), SASK.V (11, -6.00%), CORZ (7, +15.03%), OSCR (6, +20.88%).
Ritmo: 23 picks en mayo, 32 en junio, 6 en julio. Se reentra repetidamente en los
mismos nombres, incluidos los que van mal.

---

## 4. Simulación de reglas de salida

Sobre la muestra independiente (n=48). "Cortar a 1w" = si `ret_1w < umbral`, se
realiza esa pérdida; si no, se mantiene a 1 mes.

| Regla | Media | Mediana | % gana |
|---|---|---|---|
| **BASE — mantener a 1 mes (actual)** | **-4.85%** | -5.08% | 35.4% |
| Cortar a 1w si negativo | **-1.68%** | -4.03% | 31.2% |
| Cortar a 1w si < -3% | -1.95% | -5.08% | 33.3% |
| Vender todo a 1w (sin criterio) | -2.56% | -2.65% | 37.5% |

Sobre el conjunto deduplicado más amplio (n=58) la mejora es mayor: -3.60% → -0.64%.

**Matiz que conviene no pasar por alto:** la regla mejora la **media** (+3.17pp)
pero **empeora el % de aciertos** (35.4% → 31.2%). No hace ganar más veces: evita
la cola catastrófica. El beneficio es de gestión de riesgo, no de acierto. Y sigue
siendo negativo (-1.68%) — la regla no convierte la cartera en rentable.

---

## 5. Lectura interna (a criticar)

**Sobre "¿entrar antes?"** — No hay datos para responderlo directamente. No existe
ningún campo que mida "cuán tarde se entró", y `extension_risk` —la variable
diseñada exactamente para eso— está vacía en el 96% de las filas por un bug ya
corregido pero que no rellena histórico. La evidencia *indirecta* (§3.3: mediana
de recorrido al alza de solo 5.5%, 42.6% de picks que nunca suben un 5%) es
compatible con "se entra tarde, cuando el movimiento ya se agotó", pero también
lo es con "se eligen activos malos". **No se puede distinguir con estos datos.**

**Sobre "¿entrar igual pero salir antes?"** — Sí hay datos, y es lo mejor
soportado: corr +0.723, consistente en las 4 carteras, solo 2/30 recuperan. Es el
único hallazgo que sobrevive a las tres limpiezas y aparece en todas las carteras.

**Sobre el criterio de selección** — Subir el umbral de PCS **no** está soportado:
el tramo 81+ es el peor (-8.39%, 17.6% aciertos). Si el PCS no ordena, endurecerlo
solo reduce el número de picks sin mejorar su calidad.

**Propuesta interna (borrador, sujeta a esta revisión):** implementar una revisión
obligatoria a ~1 semana de la entrada, en fase de **observación** primero
(registrar qué habría hecho la regla sin ejecutarla, igual que se hizo con
`koncorde_shadow_exits.py`), no como stop automático. Motivos para no ejecutarla
directamente: (a) la regla está ajustada sobre los mismos datos que la revelan,
sin validación fuera de muestra; (b) mejora la media pero empeora el win rate, y
convendría entender ese trade-off antes de operarlo; (c) con ATR de varios puntos
en este universo, un corte a una semana puede estar cortando ruido normal.

Y por debajo de todo esto, la duda de fondo: si el problema real es la asimetría
de entrada (§3.3), una regla de salida es un parche que limita el daño sin
arreglar la causa.

---

## 6. Preguntas concretas al asesor

1. Con n=48 eventos sobre 25 tickers y un solo régimen de 3 meses, ¿es
   defendible actuar sobre el hallazgo de la regla a 1 semana, o la muestra
   obliga a esperar? ¿Qué tamaño mínimo pedirías?
2. La regla mejora media pero empeora win rate. ¿Cómo lo interpretas? ¿Es
   aceptable para una cartera con este perfil de universo (small caps, ATR alto)?
3. ¿Cómo separarías "entrar tarde" de "elegir mal", dado que `extension_risk` no
   tiene histórico? ¿Merece la pena reconstruirlo retroactivamente desde precios?
4. El PCS no ordena resultados por encima del umbral (corr global -0.007). ¿Es
   esto esperable por diseño (una puerta no tiene por qué ordenar), o señala un
   problema real en la composición del PCS?
5. La asimetría max_gain/max_dd de 0.52 frente al 1.04 de HIGH_CONVICTION, ¿es la
   métrica correcta para diagnosticar calidad de entrada? ¿Usarías otra?
6. Dado que CFL se define como "líder de flujo confirmado", ¿tiene sentido
   conceptualmente que su recorrido restante sea la mitad que el de una cartera
   de convicción alta, o eso invalida la tesis misma de la cartera?

---

## 7. Datos crudos — picks CFL limpios

Muestra tras deduplicar por (modelo, ticker, fecha) y excluir el bloque zombi.
Nota: filas con mismo ticker+fecha y distinto modelo comparten retornos (mismo
evento de mercado); para las estadísticas de §3 se colapsan a un solo evento.
`Shadow=NO` significa que era el modelo activo (la cartera real) en ese momento.

| Ticker | Fecha | Modelo | Shadow | PCS | ret_1d | ret_1w | ret_1m | vs_spy_1m | max_gain | max_dd |
|---|---|---|---|---|---|---|---|---|---|---|
| CORZ | 2026-05-08 | grok-4.3 | sí | None | 0.13 | 5.63 | 17.84 | 17.92 | 32.9 | -5.37 |
| NBIS | 2026-05-08 | grok-4.3 | sí | None | 5.11 | 24.22 | 24.33 | 24.4 | 57.49 | -2.71 |
| CORZ | 2026-05-08 | claude-sonnet-4.6 | sí | None | 0.13 | 5.63 | 17.84 | 17.92 | 32.9 | -5.37 |
| NBIS | 2026-05-08 | claude-sonnet-4.6 | sí | None | 5.11 | 24.22 | 24.33 | 24.4 | 57.49 | -2.71 |
| NVDA | 2026-05-15 | claude-haiku-4.5 | sí | 77.0 | -1.33 | -4.43 | -7.84 | -9.35 | 3.09 | -11.43 |
| WCP.TO | 2026-05-15 | grok-4.3 | NO | 80.5 | 2.61 | -2.77 | -5.04 | -5.28 | 3.96 | -7.61 |
| UCO | 2026-05-15 | claude-haiku-4.5 | sí | 82.0 | 0.84 | -5.9 | -25.52 | -27.03 | 5.46 | -27.29 |
| WCP.TO | 2026-05-15 | claude-haiku-4.5 | sí | 80.5 | 2.61 | -2.77 | -5.04 | -5.28 | 3.96 | -7.61 |
| ASPI | 2026-05-15 | claude-haiku-4.5 | sí | 79.0 | -9.05 | -4.31 | 11.03 | 9.52 | 47.24 | -17.16 |
| CORZ | 2026-05-16 | claude-haiku-4.5 | sí | 80.2 | -2.76 | 11.88 | 20.41 | 20.09 | 29.23 | -7.45 |
| GLNG | 2026-05-16 | claude-haiku-4.5 | sí | 80.0 | -1.99 | -8.74 | -12.47 | -12.78 | 1.34 | -14.6 |
| OXY | 2026-05-16 | claude-haiku-4.5 | sí | 79.5 | 1.68 | -3.75 | -10.75 | -11.06 | 2.58 | -11.1 |
| VLE.TO | 2026-05-16 | claude-haiku-4.5 | sí | 80.0 | -2.27 | -18.32 | -17.56 | -19.6 | 1.14 | -20.29 |
| VAL | 2026-05-21 | claude-haiku-4.5 | sí | 85.5 | -0.31 | -8.72 | -22.61 | -21.63 | 0.59 | -24.72 |
| CORZ | 2026-05-22 | claude-haiku-4.5 | sí | 78.2 | 4.39 | 13.02 | 10.02 | 11.43 | 20.59 | -0.32 |
| OSCR | 2026-05-22 | claude-haiku-4.5 | sí | 80.8 | -3.31 | 1.46 | 28.8 | 30.21 | 34.19 | -11.26 |
| CORZ | 2026-05-26 | claude-haiku-4.5 | sí | 69.8 | 3.15 | 10.16 | 3.41 | 5.33 | 15.51 | -4.51 |
| OSCR | 2026-05-28 | grok-4.3 | NO | 81.8 | -0.45 | 5.69 | 31.89 | 33.43 | 37.32 | -10.03 |
| OSCR | 2026-05-28 | claude-haiku-4.5 | sí | 81.8 | -0.45 | 5.69 | 31.89 | 33.43 | 37.32 | -10.03 |
| ASTS | 2026-05-28 | claude-haiku-4.5 | sí | 81.8 | -14.79 | -19.39 | -34.8 | -33.25 | -10.78 | -52.12 |
| TSLA | 2026-05-28 | claude-haiku-4.5 | sí | 78.5 | -1.43 | -5.35 | -6.84 | -5.3 | -0.23 | -16.63 |
| ASPI | 2026-05-29 | claude-haiku-4.5 | sí | 82.5 | 2.96 | -13.75 | -20.05 | -19.02 | 9.77 | -27.06 |
| ASTS | 2026-05-29 | claude-haiku-4.5 | sí | 81.8 | -6.84 | -17.47 | -21.65 | -20.62 | 4.7 | -43.81 |
| BBAR | 2026-06-03 | grok-4.3 | NO | 79.0 | 0.23 | -0.28 | 17.77 | 17.9 | 26.96 | -2.94 |
| SASK.V | 2026-06-03 | claude-haiku-4.5 | sí | 82.5 | -5.93 | -23.73 | -16.95 | -16.34 | 4.24 | -26.27 |
| EOSE | 2026-06-03 | claude-haiku-4.5 | sí | 78.5 | -1.46 | -25.98 | -38.29 | -38.16 | 0.37 | -38.6 |
| BBAR | 2026-06-03 | claude-haiku-4.5 | sí | 79.0 | 0.23 | -0.28 | 17.77 | 17.9 | 26.96 | -2.94 |
| YPF | 2026-06-03 | claude-haiku-4.5 | sí | 72.0 | 0.4 | -1.15 | -15.99 | -15.86 | 4.72 | -19.82 |
| EOSE | 2026-06-04 | grok-4.3 | NO | 83.0 | -12.38 | -23.27 | -41.34 | -40.35 | 1.86 | -45.67 |
| SASK.V | 2026-06-04 | grok-4.3 | NO | 82.5 | -16.22 | -9.01 | -2.7 | -1.41 | 10.81 | -21.62 |
| WCP.TO | 2026-06-09 | claude-haiku-4.5 | sí | 77.0 | 0.97 | -3.04 | -4.6 | -6.5 | 3.22 | -12.35 |
| YPF | 2026-06-09 | claude-haiku-4.5 | sí | 77.0 | 1.23 | -4.42 | -11.25 | -13.94 | 7.24 | -17.89 |
| OSCR | 2026-06-09 | claude-haiku-4.5 | sí | 77.2 | 2.31 | 4.92 | 12.2 | 9.5 | 21.6 | -0.29 |
| ASPI | 2026-06-09 | claude-haiku-4.5 | sí | 77.8 | -8.59 | 0.62 | -21.72 | -24.41 | 18.75 | -24.45 |
| HIMS | 2026-06-09 | claude-haiku-4.5 | sí | 76.5 | -4.14 | 8.59 | 18.63 | 15.94 | 34.75 | -8.49 |
| GGAL | 2026-06-09 | claude-haiku-4.5 | sí | 74.2 | -0.74 | 8.9 | 7.48 | 4.79 | 16.3 | -4.3 |
| BBAR | 2026-06-09 | claude-haiku-4.5 | sí | 73.5 | -2.65 | 13.52 | 17.19 | 14.5 | 23.95 | -2.7 |
| NBIS | 2026-06-12 | claude-haiku-4.5 | sí | 78.2 | 11.93 | 22.06 | -14.14 | -16.16 | 29.05 | -19.42 |
| OSCR | 2026-06-12 | claude-haiku-4.5 | sí | 70.5 | 3.11 | 0.99 | 8.32 | 6.29 | 17.13 | -3.96 |
| LOMA | 2026-06-13 | grok-4.3 | NO | 83.5 | -1.63 | -0.49 | -7.5 | -7.22 | 1.71 | -11.74 |
| GGAL | 2026-06-13 | claude-haiku-4.5 | sí | 81.8 | -2.72 | -8.24 | -10.33 | -10.04 | 3.9 | -14.51 |
| LOMA | 2026-06-13 | claude-haiku-4.5 | sí | 83.5 | -1.63 | -0.49 | -7.5 | -7.22 | 1.71 | -11.74 |
| YPF | 2026-06-13 | claude-haiku-4.5 | sí | 77.0 | -2.57 | -8.65 | -7.87 | -7.58 | 0.02 | -16.3 |
| GGAL | 2026-06-13 | grok-4.3 | NO | 81.8 | -2.72 | -8.24 | -10.33 | -10.04 | 3.9 | -14.51 |
| BBAR | 2026-06-13 | claude-haiku-4.5 | sí | 84.8 | -0.53 | -1.45 | -5.13 | -4.84 | 8.6 | -10.15 |
| QQQ | 2026-06-16 | grok-4.3 | NO | 83.0 | -1.01 | -2.53 | -4.63 | -3.94 | 2.25 | -5.8 |
| TDOC | 2026-06-16 | grok-4.3 | NO | 81.0 | 0.26 | 3.17 | 24.57 | 25.25 | 30.61 | -1.85 |
| HIMS | 2026-06-17 | grok-4.3 | NO | 80.0 | 11.23 | 2.57 | 2.54 | 2.13 | 22.45 | -5.02 |
| HIMS | 2026-06-17 | claude-haiku-4.5 | sí | 80.0 | 11.23 | 2.57 | 2.54 | 2.13 | 22.45 | -5.02 |
| SASK.V | 2026-06-19 | claude-haiku-4.5 | sí | 80.5 | -0.92 | -6.42 | -3.67 | -2.84 | 5.5 | -10.09 |
| ASPI | 2026-06-19 | claude-haiku-4.5 | sí | 79.8 | -2.75 | -14.56 | -43.96 | -44.36 | 4.4 | -50.41 |
| SASK.V | 2026-06-20 | grok-4.3 | NO | 80.5 | -0.92 | -6.42 | -3.67 | -2.84 | 5.5 | -10.09 |
| ASPI | 2026-06-20 | mimo-v2.5-pro | sí | 79.8 | -2.75 | -14.56 | -43.96 | -44.36 | 4.4 | -50.41 |
| ASPI | 2026-06-20 | grok-4.3 | NO | 79.8 | -2.75 | -14.56 | -43.96 | -44.36 | 4.4 | -50.41 |
| SASK.V | 2026-06-20 | mimo-v2.5-pro | sí | 80.5 | -0.92 | -6.42 | -3.67 | -2.84 | 5.5 | -10.09 |
| URI | 2026-07-01 | grok-4.3 | NO | 80.5 | -1.18 | -2.08 | -2.92 | -3.09 | 5.93 | -10.51 |
| ROOT | 2026-07-01 | grok-4.3 | NO | 79.0 | 2.87 | 7.32 | -9.77 | -9.94 | 12.46 | -10.6 |

---

## 8. Nota sobre reproducibilidad

Todos los números salen de `docs/data/shadow_picks.jsonl` con los tres filtros de
§2. No se ha modificado ningún dato del sistema para este análisis. El bug de
filas duplicadas (§2b) sigue presente en el pipeline en el momento de escribir
esto y no se ha corregido todavía.
