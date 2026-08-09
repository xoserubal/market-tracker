# Preregistro — Backtest de Relative Flow Lab v0

**Fecha de escritura de esta sección: 2026-08-08, antes de correr el grid
search real sobre `dev`.** Ver `wiki/PLAN_RELATIVE_FLOW_LAB_BACKTEST.md` para
el contexto completo. Mismo papel que `PREREGISTRO_RANKING_SCORE_V0.md`:
congelar la regla de juego antes de ver los resultados que decidirían si
cambiarla.

## Pregunta

¿El `score` de Relative Flow Lab (o su clasificación Leader/Improving/
Neutral/Weakening/Laggard × Trend Up/Down/Mixed) predice alfa real
(retorno de A − retorno de SPY) en las 1/4/13 semanas siguientes, por
encima de lo que predeciría no tener ninguna señal?

## Datos

`docs/data/relative_flow_history_reconstructed.jsonl` — 45 ratios ×
histórico diario completo (algunos desde 1998, otros desde 2019-2021 según
el ETF), generado por `scripts/reconstruct_relative_flow_historical.py`.
Filas con `burn_in=true` (primeras 300 barras de cada serie alineada,
RSI todavía convergiendo) se excluyen en `analyze_relative_flow_signal.py`.
Resampleo semanal activado por defecto (decisión #5 del plan) — una fila
por (par, semana ISO), mitiga pero no elimina la autocorrelación por
solapamiento de las ventanas de retorno futuro.

**Pares de historial corto** (interpretar con cautela, n bajo incluso tras
años de datos): AMR, HCC, CCJ/URNM, XLC, XLRE, URA, BTC-USD — arrancan entre
2017 y 2021, no desde 1998 como la mayoría.

## Corte dev/test

**Fecha de calendario única, no un % por par:** `hoy − 365 días naturales`
(2025-08-08 en esta ejecución), calculada en tiempo de ejecución. `dev` =
todo lo anterior, `test` = el último año, igual para los 45 pares — evita
que el tramo de test de cada par caiga en un régimen de mercado distinto
según cuándo empezó su historial (decisión #6 del plan).

## GRID congelado (código: `analyze_relative_flow_signal.py::build_grid()`)

~200 combinaciones, dos familias × 3 horizontes (1w/1m/3m):

1. **label × trend**: 5 labels (Leader/Improving/Neutral/Weakening/Laggard)
   × 3 trends (Up/Down/Mixed) = 15 combinaciones.
2. **score_min × trend**: `score >= score_min` para `score_min` en
   `range(-8, 9)` (17 valores, de -8 a 8 en pasos de 1) × 3 trends = 51
   combinaciones.

Total: 66 combinaciones × 3 horizontes = **198 evaluaciones**. Cualquier
combinación con `n < 20` en el tramo correspondiente (dev o test) se
descarta — umbral fijado aquí, antes de ver ningún resultado.

## Regla de selección

Sobre `dev` únicamente: para cada uno de los 3 horizontes, se ordenan las
combinaciones con `n >= 20` por alfa medio descendente y se seleccionan las
**top 3** (una lista por horizonte, máx. 9 combinaciones en total). Esa
selección se congela — se copia literalmente, sin retocar, en el bloque
`json-frozen-combos` de este documento (añadido en una edición posterior a
esta, tras correr `--grid`, pero antes de `--confirm-test`) y es
EXACTAMENTE lo que se evalúa sobre `test` — nunca una búsqueda nueva sobre
test, nunca un ajuste tras verlo.

## Criterios de veredicto (modestos, definidos antes de ver test)

Por cada una de las combinaciones congeladas, evaluada en `test`:

- **Plausible**: `test_n >= 20`, alfa medio en test tiene el MISMO signo que
  en dev, y `win_rate >= 0.55`.
- **No soportado**: cualquier otro caso — incluyendo `test_n < 20`
  (muestra insuficiente, no es evidencia en ningún sentido), signo opuesto
  a dev, o `win_rate < 0.55`.

No hay categoría "confirmado" — con ~200 combinaciones probadas en dev y
sin corrección de familywise error, incluso una confirmación limpia en test
para 1-3 combinaciones de 9 es evidencia débil, no una señal lista para
`paper_trading.py`. El techo de este backtest es "plausible, vale la pena
seguir mirando con más rigor" — no "operar esto".

## Advertencias explícitas (repetidas en el informe final)

- La significancia sigue siendo optimista pese al resampleo semanal —
  autocorrelación residual no eliminada (Newey-West/HAC queda fuera de
  alcance a propósito, mismo principio de "no añadir complejidad antes de
  que los datos la justifiquen").
- ~200 combinaciones en el grid de dev significa que los "ganadores" en dev
  son optimistas por diseño (multiple comparisons) — lo único que importa
  de verdad es la confirmación en test, hecha una sola vez.
- El ajuste por dividendo (`auto_adjust=True`) hace que el score
  reconstruido diverja ligeramente del que muestra la página en vivo en
  pares con yield no trivial (ver chequeo dorado en
  `scripts/test_relative_flow_lib.py`) — pequeño, pero real.

## Alcance

Esto es investigación. No se toca `paper_trading.py`, `pcs_calculator.py`
ni ninguna cartera viva salvo que los hallazgos sean sólidos y el usuario
lo pida aparte, como seguimiento explícito — igual que
`PREREGISTRO_RANKING_SCORE_V0.md`.

---

## Combinaciones congeladas (top-3 por horizonte, seleccionadas en dev)

Ejecutado `py -3 scripts/analyze_relative_flow_signal.py --grid` sobre dev
(42.348 filas resampleadas a semana, 168/198 combinaciones con n≥20).
Nota: `label=Leader` y `score_min=8` son, por construcción de `classify()`
(`score>=8 -> Leader`), el MISMO subconjunto — la duplicación en la tabla es
esperada, no un error de la búsqueda.

| Horizonte | Combinación | n (dev) | mean α | median α | win_rate |
|---|---|---|---|---|---|
| 1w | label=Laggard, trend=Mixed | 614 | 0.2714 | 0.0088 | 0.5049 |
| 1w | score≥1, trend=Down | 69 | 0.1796 | -0.1258 | 0.4783 |
| 1w | label=Laggard, trend=Down | 5416 | 0.1471 | 0.0614 | 0.5109 |
| 1m | label=Leader, trend=Mixed | 801 | 0.9309 | 0.5485 | 0.5331 |
| 1m | score≥8, trend=Mixed | 801 | 0.9309 | 0.5485 | 0.5331 |
| 1m | score≥7, trend=Mixed | 1074 | 0.7923 | 0.4313 | 0.5251 |
| 3m | label=Laggard, trend=Mixed | 614 | 1.6223 | 0.2336 | 0.5065 |
| 3m | label=Leader, trend=Mixed | 801 | 1.0197 | -0.7596 | 0.4769 |
| 3m | score≥8, trend=Mixed | 801 | 1.0197 | -0.7596 | 0.4769 |

**Lectura honesta antes de tocar test:** ningún `win_rate` supera 0.5331 —
muy lejos del 0.55 fijado arriba como umbral de "plausible". El baseline
incondicional pooled ya tenía win_rate≈0.48-0.49 y mean α positivo en los 3
horizontes (0.019/0.035/0.113) simplemente porque el mercado en su
conjunto subió durante casi todo el periodo dev — varias de estas
combinaciones "top" no le ganan claramente a ESE baseline, solo tienen
mean α positivo en términos absolutos. La correlación pooled score↔alfa ya
adelantaba esto: r=-0.009/0.003/0.012 en 1w/1m/3m — indistinguible de cero,
mismo patrón que el hallazgo de PCS↔ret_1m (-0.007) en
`wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md`.

Se congelan estas 9 combinaciones igualmente, tal como dicta la regla ya
fijada arriba — **el criterio de éxito no cambia porque los números de dev
ya se vean flojos**.

```json-frozen-combos
[
  {"kind": "label_trend", "label": "Laggard", "trend": "Mixed", "horizon": "1w"},
  {"kind": "score_min_trend", "score_min": 1, "trend": "Down", "horizon": "1w"},
  {"kind": "label_trend", "label": "Laggard", "trend": "Down", "horizon": "1w"},
  {"kind": "label_trend", "label": "Leader", "trend": "Mixed", "horizon": "1m"},
  {"kind": "score_min_trend", "score_min": 8, "trend": "Mixed", "horizon": "1m"},
  {"kind": "score_min_trend", "score_min": 7, "trend": "Mixed", "horizon": "1m"},
  {"kind": "label_trend", "label": "Laggard", "trend": "Mixed", "horizon": "3m"},
  {"kind": "label_trend", "label": "Leader", "trend": "Mixed", "horizon": "3m"},
  {"kind": "score_min_trend", "score_min": 8, "trend": "Mixed", "horizon": "3m"}
]
```
