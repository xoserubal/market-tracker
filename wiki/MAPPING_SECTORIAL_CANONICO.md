# Mapping Sectorial Canónico — Fase 5a RFL v2

> Precondición para la matriz de coherencia cross-módulos (Cycle Tracker ×
> Flujos & Rotación v2 × Relative Flow Lab). Sin este mapping, las tres
> columnas de la matriz cruzan cosas distintas bajo el mismo nombre de
> sector y producen falso consenso o falsa divergencia. Firmado 2026-08-11.

## Principio

Un "sector" en esta matriz es una fila que cruza exactamente:
- **Cycle Tracker** (`cycle.html`): una fase de `CYCLE_MAP` (10 fases
  clásicas — off-cycle themes excluidos, ver "Fuera de alcance").
- **Flujos & Rotación v2** (`rotacion.html`): un ticker de `UNIVERSE`.
- **Relative Flow Lab** (`relative.html`): un ratio `*_spy`/`*_urth` del
  registry (`shared/relative-ratio-registry.js`), cluster `sector_snapshot`
  o `rotation` (`xlk_spy`, promovido a `rotation` en la Fase 1 de RFL v2).

Los tres NO comparten universo de tickers — cada mapping se verificó
individualmente contra el código real de los tres módulos (no se asumió
nada), 2026-08-11.

## Tabla de mapping

| Sector | Cycle Tracker (fase, proxy) | Flujos & Rotación (ticker) | RFL (ratio) | Cobertura |
|---|---|---|---|---|
| Transportation | Early Bull (IYT) | — no está en `UNIVERSE` | — no está en el registry | Solo Cycle (1/3) |
| Technology | Early → Mid Bull (XLK) | XLK | `xlk_spy` | Completa (3/3) |
| Capital Goods | Mid → Late Bull (XLI) | XLI | `xli_spy` | Completa (3/3) |
| Materials | Late Bull (XLB) | XLB | `xlb_spy` | Completa (3/3) |
| Oil & Gas | Late Bull → Top (XLE) | XLE (también XOP) | `xle_spy` (también `xop_xle`) | Completa (3/3) |
| Uranium | Late Bull → Top (URNM) | — no está en `UNIVERSE` | `urnm_urth` (vs URTH, no vs SPY) | Cycle + RFL (2/3) |
| Coal & Steel Inputs | Late Bull → Top (TECK, sin ETF) | — no está en `UNIVERSE` | — solo ratios stock-vs-stock (`hcc_btu`, `amr_btu`, `hcc_xme`, `amr_xme`), ninguno vs SPY/URTH | Solo Cycle (1/3) |
| Staples | Early Bear (XLP) | XLP | `xlp_spy` | Completa (3/3) |
| Healthcare | Early Bear (XLV) | XLV | `xlv_spy` | Completa (3/3) |
| Utilities | Late Bear — Approx. (XLU) | XLU | `xlu_spy` | Completa (3/3) |
| Financials & Cyclicals | Late Bear (XLF, también XHB) | XLF | `xlf_spy` | Completa (3/3) |

**8 de 11 filas con cobertura completa (3/3)** — Technology, Capital Goods,
Materials, Oil & Gas, Staples, Healthcare, Utilities, Financials. Las 3
restantes (Transportation, Uranium, Coal & Steel Inputs) no tienen los tres
módulos representados con el mismo ticker — se muestran igualmente en la
matriz pero como `NO EVALUABLE` (nunca se inventa una lectura con datos
ausentes), documentado así a propósito en vez de forzar un ticker sustituto
que no es el mismo instrumento.

## Fuente de cada columna (decisión de implementación, Fase 5a)

- **Cycle (3M):** NO es el score compuesto de la fase completa de
  `cycle.html` (media del cesto de 4-8 tickers de esa fase, con breadth y
  dispersión) — reimplementar ese cálculo dentro de `relative.html`
  exigiría duplicar `calcPhaseScores` y descargar el histórico de ~90
  tickers adicionales que RFL no toca hoy. En su lugar, se usa el **retorno
  a 3 meses (r3m) del mismo ratio `*_spy` de RFL** que ya usa como su
  proxy el propio ticker que Cycle Tracker marca `role:"proxy"` para esa
  fase — mismo instrumento, mismo concepto (alfa vs mercado a 3 meses), sin
  fetch ni cálculo nuevo. Es una aproximación declarada, no el dato
  original de Cycle Tracker — documentado explícitamente en la UI y en el
  export a LLM para que no se lea como si fuera literalmente Cycle Tracker.
- **Flujos (semanal):** última entrada de `rotation_history[ticker]` en
  `state.json` (ya sembrado por `rotacion.html` desde su propia Fase 1) —
  lectura directa, sin recalcular el RotScore.
- **RFL (5-10d):** `flowChange` del mismo ratio `*_spy` (retorno de los
  últimos 5 días vs los 5 días previos) — el campo de RFL con el horizonte
  más corto, ya usado por el Early Flow Detector y por el filtro de
  coherencia de la Fase 4 (Top 3 Flow In/Out).

## Lenguaje interpretativo obligatorio

Igual que el registry de divergencias de `rotacion.html` (Fase 4 de
Flujos & Rotación v2): nunca "confirma"/"contradice" en sentido conclusivo.
"Coincidencia entre los 3 módulos SUGIERE consenso multi-horizonte."
"Divergencia entre los módulos PLANTEA lectura ambigua." "Confirmación con
horizontes distintos NO garantiza continuación de tendencia."

## Fuera de alcance

- **Off-cycle themes** de `cycle.html` (Crypto & Mining, AI Cloud &
  Infrastructure, Defense & Space, Latam Emerging) — excluidos de esta
  matriz por la misma razón que `cycle.html` los mantiene fuera de
  `PhaseTimeline`/resumen global: no responden a "¿dónde estamos en el
  ciclo?", que es la pregunta que esta matriz cruza.
- Real Estate (XLRE), Comm. Services (XLC), Consumer Disc. (XLY) — están en
  `rotacion.html`/RFL pero no tienen fase propia en `CYCLE_MAP` — sin
  ancla de Cycle Tracker, no hay fila posible.
- Histéresis o suavizado de la matriz — se recalcula en vivo en cada carga,
  igual que el resto de RFL.
