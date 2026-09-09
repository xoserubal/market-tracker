# Portar Market Tracker / Cycle / Relative Flow / Rotación al pipeline

> Copia de trabajo del plan guardado en
> `C:\Users\Usuario\.claude\plans\smooth-noodling-micali.md` (sesión Claude Code,
> 2026-09-09). Aún no aprobado para ejecución — retomar fase por fase.

## Contexto

Hoy solo dos fuentes del proyecto se capturan de verdad todos los días sin
depender de que el ordenador esté encendido: **AI Picks Lab** (pipeline
Python, `docs/data/*.json`) y **Portfolio Tracker** (`portfolio_daily_snapshot.js`,
Step 9g). Las otras cuatro pestañas — **Market Tracker** (`index.html` de la
raíz, no `docs/index.html`), **Cycle Tracker** (`cycle.html`), **Relative
Flow Lab** (`relative.html`) y **Flujos & Rotación** (`rotacion.html`) — son
100% cliente: recalculan todo en vivo en el navegador y, en el mejor de los
casos (Relative Flow/Rotación), solo persisten histórico en `state.json`
local al servidor del usuario, que ni está en git ni sobrevive si el PC está
apagado.

El usuario quiere que un modelo haga un análisis de mercado diario a partir
de la snapshot del día, para poder hacer ajustes retrospectivos de
prompt/agente/datos más adelante — eso exige que **todas** las fuentes de
datos relevantes queden capturadas de forma fiable, todos los días, sin
intervención humana. Este plan porta las 4 pestañas al pipeline de GitHub
Actions, siguiendo exactamente el patrón ya usado para Portfolio Tracker:
extraer la lógica de cálculo a un módulo compartido isomórfico (browser +
Node), y escribir un script headless que la reutilice y escriba a un archivo
nuevo commiteado a git.

**Decisiones ya confirmadas con el usuario:**
- El régimen macro de Rotación (histéresis) tendrá su **propia copia
  independiente** en el pipeline — no se toca `state.json` ni el
  comportamiento en vivo de `rotacion.html`. Se acepta que el régimen "en
  vivo" del navegador y el archivado por el pipeline puedan no coincidir
  exactamente si difiere el momento de lectura.
- Los dos precios 100% manuales de Market Tracker (U3O8 Spot, Uranium
  Long-Term) quedan `null` en el snapshot diario, documentado — sin archivo
  nuevo ni UI nueva en esta ronda.

## Arquitectura común (mismo patrón en las 4)

Para cada pestaña:
1. Extraer sus constantes de universo (tickers/registries) y sus funciones
   puras de cálculo a un módulo `shared/*.js` isomórfico (`module.exports` +
   asignación a `window`, exactamente como ya existen `shared/quote-lib.js`,
   `shared/flow-score.js` y `shared/relative-ratio-registry.js`). La página
   HTML pasa a cargarlo vía `<script src="/shared/...">` en vez de definirlo
   inline — mismo mecanismo, cero duplicación, cero riesgo de que el
   pipeline y el navegador calculen cosas distintas.
2. Escribir un script Node (o Python, para Relative Flow — ver abajo) nuevo
   que haga fetch en vivo (Yahoo/FRED, sin servidor Express corriendo — igual
   que `portfolio_daily_snapshot.js`) y escriba a un `docs/data/*.jsonl`
   nuevo, con dedup por fecha+clave, flags `--dry-run`/`--report`/`--tickers=`.
3. Wire como step nuevo en `.github/workflows/market-update.yml`,
   `continue-on-error: true`, corriendo en ambos runs del día (2x/día,
   consistente con Portfolio Tracker).
4. Verificar el output del script headless contra lo que muestra la página
   en vivo (Edge headless vía CDP, mismo método ya usado en todo el
   proyecto) antes de dar la fase por cerrada.

**Orden de implementación** (una fase a la vez, verificada antes de pasar a
la siguiente — mismo criterio que ya se usó para RFL v2/Rotación v2):

### Fase A — Cycle Tracker (la más simple: sin estado persistido, sin histéresis)
- Extraer `CYCLE_MAP` (10 fases, 80 tickers) y `OFFCYCLE_THEMES` (4 temas,
  21 tickers) de `cycle.html` a `shared/cycle-map.js`. Extraer también
  `calcPhaseScores` (alpha = 0.7×relM3+0.3×relM1, breadth, dispersion,
  acceleration, tickerRanks) a ese mismo módulo o a `shared/cycle-lib.js`.
- Nuevo `scripts/cycle_tracker_snapshot.js`: reutiliza `shared/quote-lib.js`
  (`buildQuoteData`, ya usado por `portfolio_daily_snapshot.js`) para cada
  ticker único (dedup + SPY), llama a las funciones extraídas.
- Salida: `docs/data/cycle_tracker_daily_snapshot.jsonl` — filas por ticker
  (m1/m3/alpha/rank/fase) + filas de resumen por fase (score/breadth/
  dispersion/acceleration), dedup por fecha+id.

### Fase B — Market Tracker (index.html raíz)
- Extraer `MACRO_ITEMS` (13) y `SECTIONS` (11 secciones, ~57 tickers) a
  `shared/market-tracker-universe.js`. Extraer también `computeUraniumScore`.
- Server.js ya calcula los deltas v1w/v1m/v3m/v6m/v1y dentro de
  `/api/fred/:series`/`/api/fred3` y el fetch de `/api/oilprice/:code` — esa
  lógica hay que extraerla a módulos isomórficos propios (`shared/fred-lib.js`,
  y el fetch de oilprice) para que el script headless no dependa de un
  servidor Express corriendo, igual que se hizo con `quote-lib.js`. **Nota
  para la implementación:** leer primero `server.js` (rutas `/api/fred`,
  `/api/fred3`, `/api/oilprice`) para confirmar la lógica exacta antes de
  extraer — no se ha auditado línea a línea en este plan.
- Nuevo `scripts/market_tracker_snapshot.js`: reutiliza
  `shared/quote-lib.js` + `shared/flow-score.js` (ya isomórfico, ya usado
  por Portfolio) + los módulos extraídos arriba.
- U3O8/Uranium LT quedan `null` explícito (decisión ya tomada).
- Salida: `docs/data/market_tracker_daily_snapshot.jsonl`.

### Fase C — Relative Flow Lab
- **Reutilizar `scripts/relative_flow_lib.py`** (ya existe, ya validado
  formula-a-fórmula contra `relative.html` con 47 tests + golden-check
  Node-vs-Python, ver sección "Backtest histórico de Relative Flow Lab" en
  CLAUDE.md) — no reescribir la lógica de ratios, solo envolverla en un
  script de captura diaria (no del backtest histórico completo).
- Nuevo `scripts/relative_flow_daily_snapshot.py`: para los 50 ratios del
  registry (`shared/relative-ratio-registry.js`, ya cargable desde Python
  vía el mecanismo que ya usa `relative_flow_lib.py`), computa
  score/signal/flowChange de hoy y los añade a
  `docs/data/relative_flow_daily_history.jsonl` (nuevo, dedup por
  fecha+id) — el equivalente commiteado y propio del pipeline de lo que
  hoy es `relative_flow_history` en `state.json` (que se deja intacto,
  sin tocar).
- Fuera de alcance de esta fase: la matriz de coherencia cross-módulos (que
  cruza con `rotation_history` de Rotación) — depende también de la Fase D,
  se retoma como fast-follow una vez existan ambos históricos propios del
  pipeline.

### Fase D — Flujos & Rotación (la más compleja)
- Extraer `UNIVERSE`, `REGIMES`, `CLUSTERS`, y las 3 funciones puras ya
  aisladas explícitamente para este propósito —
  `computeEffectiveRegime`, `buildEarlyRotQualifyMap`, `computeTickerRow`
  (`rotacion.html`, ya preparadas para poder llamarse fuera del render) —
  más la lógica de histéresis de `updateStateFromData` a
  `shared/rotation-lib.js`.
- Nuevo `scripts/rotation_pipeline_snapshot.js`: usa `shared/quote-lib.js`
  para las cotizaciones y las funciones extraídas para el scoring/régimen.
  **Nota para la implementación:** confirmar de dónde saca `rotacion.html`
  el MacroScore semanal (¿se recalcula client-side o se lee de algo que ya
  produce `backtest/src/main_macro.py`?) antes de escribir el fetch — no
  verificado en esta ronda de exploración.
- Mantiene su **propio** `docs/data/rotation_pipeline_state.json` (régimen
  actual/pendiente, contador de histéresis, fecha de entrada) — la
  histéresis solo avanza **una vez por día natural** aunque el script corra
  2x/día (mismo patrón dedup-por-día que el resto del proyecto), para no
  confirmar un cambio de régimen dentro del mismo día por las dos corridas.
- Escribe `docs/data/rotation_pipeline_history.jsonl` (score/signal/
  blockA-B-C/fit/macro_regime/rs_1w-4w-13w por ticker/día) — equivalente
  propio y commiteado de `rotation_history`.
- `DIVERGENCE_REGISTRY`/`computeFitLevel`/`computeSubscoreProfile`: opcional
  para esta fase, se pueden portar en un fast-follow una vez el MVP
  (universo + régimen + histéresis + histórico) esté verificado.

## Verificación (cada fase)

- Comparar numéricamente el output del script headless contra lo que
  muestra la página en vivo el mismo día (Edge headless vía CDP, mismo
  método usado en todo el proyecto) para una muestra de tickers.
- `--dry-run`/`--report` antes de escribir a disco real.
- Confirmar dedup (correr el script dos veces el mismo día → 0 filas
  nuevas la segunda vez).
- Para Fase D en particular: verificar que un cambio de régimen synthetic
  (datos fabricados) solo se confirma tras 2 días naturales distintos, no
  tras 2 corridas del mismo día.

## Fuera de alcance (explícito, en todas las fases)

No se toca el comportamiento en vivo de ninguna de las 4 páginas más allá
de cambiar un `<script>` inline por un `<script src="...">` (mismo
contenido, sin cambio funcional). No se migra `state.json` a git. No se
crea archivo de precios manuales para Market Tracker. La matriz de
coherencia cross-módulos de Relative Flow queda pendiente hasta que exista
el histórico propio de Rotación (Fase D).
