# Hallazgos — Backtest histórico de Relative Flow Lab

**Fecha: 2026-08-08.** Ejecutado según `wiki/PLAN_RELATIVE_FLOW_LAB_BACKTEST.md`
y `wiki/PREREGISTRO_RELATIVE_FLOW_LAB_V0.md` (grid y regla de selección
congelados antes de correr el grid search; test evaluado una sola vez).

## Veredicto en una línea

**El score de Relative Flow Lab, tal como está definido hoy, no predice
alfa futuro de forma útil.** La correlación pooled score↔alfa es
indistinguible de cero en los 3 horizontes, y de las 7 combinaciones
distintas seleccionadas en dev (top-3 por horizonte) solo 1 sobrevive el
criterio modesto de "plausible" en test — proporción compatible con azar
dado que se probaron ~200 combinaciones en dev. Mismo patrón que el
hallazgo de PCS↔ret_1m (-0.007) documentado en
`wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md`: el score funciona como filtro
narrativo/interpretativo, no como ranking predictivo.

## Metodología

- **Reconstrucción**: `scripts/relative_flow_lib.py` porta literalmente
  `alignRatio`/`ret`/`retWindow`/`sma`/`calcRSI`/`buildRow`/`classify` de
  `relative.html`, vectorizado para producir una fila por (par, día) sin
  mirar al futuro — verificado con 47 tests unitarios
  (`scripts/test_relative_flow_lib.py`), incluyendo un chequeo dorado
  contra las funciones JS reales ejecutadas en Node sobre datos servidos
  por `server.js` en vivo.
- **Universo**: 45 ratios del registry (`shared/relative-ratio-registry.js`,
  cargado vía Node, nunca copiado a mano), histórico completo por yfinance
  (`period="max"`, `auto_adjust=True`) — entre 1998 y 2021 según el ETF.
  228.893 filas diarias reconstruidas
  (`docs/data/relative_flow_history_reconstructed.jsonl`, no commiteado —
  163MB, por encima del límite de GitHub; regenerable en ~2-3 min con la
  cache de precios).
- **Etiqueta objetivo**: `fwd_alpha_{1w,1m,3m}` = retorno de A menos retorno
  de SPY en las 5/21/63 sesiones siguientes, cada uno sobre su propio
  calendario de cotización.
- **Resampleo semanal** (activado por defecto): una fila por (par, semana
  ISO) para mitigar la autocorrelación de ventanas de retorno solapadas.
  42.348 filas en dev tras resamplear y excluir burn-in.
- **Corte dev/test**: fecha única, hoy − 365 días naturales (2025-08-08),
  igual para los 45 pares. Dev = 42.348 filas, test = 2.385 filas.

## Desviaciones declaradas (ver plan, decisiones #1-#8)

- **Ajuste por dividendo**: la reconstrucción usa `auto_adjust=True`;
  `relative.html`/`server.js` sirven close sin ajustar. Esto genera una
  divergencia pequeña pero real en `r3m`/`r6m`/`score` para pares con yield
  no trivial — verificado en el chequeo dorado: `xlk_spy` (XLK con yield
  ~0.6%) diverge ~0.15-0.35pp en r3m/r6m y 0.1 en score final (3.9 vs 4.0
  en vivo, misma clasificación "Improving"); `ura_urnm`/`gdxj_gdx` (sin
  evento de dividendo relevante en la ventana) coinciden hasta la 4ª-5ª
  cifra decimal.
- **RSI de Wilder**: un único pase expandible desde el origen de cada serie
  (no una ventana de 3 años re-sembrada cada día como hace la página en
  vivo) — matemáticamente converge al mismo valor pasadas ~300 barras
  (memoria exponencial de Wilder), confirmado en el mismo chequeo dorado
  (diferencias de RSI <0.05 puntos en los 3 pares comparados).
- **`burn_in`** (primeras 300 barras de cada serie alineada) marcado pero
  excluido del análisis por `analyze_relative_flow_signal.py` — no afecta
  a los pares con historial largo (>1998), sí recorta una porción no
  trivial de los pares de historial corto.
- **Pares de historial corto** (AMR, HCC, CCJ/URNM, XLC, XLRE, URA,
  BTC-USD, arrancan 2017-2021): incluidos en el pooled, pero con mucha
  menos n por definición — no se desglosan aparte en este informe porque
  ninguno de los 7 aparece entre las combinaciones congeladas evaluadas.

## Baseline incondicional (dev, pooled, 42.348 filas)

| Horizonte | n | mean α | median α | win rate |
|---|---|---|---|---|
| 1w | 42.348 | +0.019 | -0.026 | 49.3% |
| 1m | 42.348 | +0.035 | -0.146 | 48.2% |
| 3m | 42.348 | +0.113 | -0.371 | 47.6% |

Nota: media positiva pero mediana negativa y win rate <50% en los 3
horizontes — la distribución de alfa está sesgada por unos pocos episodios
de fuerte outperformance (crypto/miners, uranio) que arrastran la media
sin que la mayoría de observaciones le ganen a SPY. Cualquier señal debe
compararse contra ESTE baseline, no contra cero.

## Correlación score ↔ alfa futuro (dev)

**Pooled — indistinguible de cero en los 3 horizontes:**

| Horizonte | n | Pearson r | p | IC95% | Spearman ρ |
|---|---|---|---|---|---|
| 1w | 42.348 | -0.0086 | 0.078 | [-0.018, 0.001] | -0.0122 |
| 1m | 42.348 | +0.0034 | 0.484 | [-0.006, 0.013] | -0.0092 |
| 3m | 42.348 | +0.0118 | 0.015 | [0.002, 0.021] | -0.0200 |

r² del orden de 0.0001-0.0002 en los 3 casos — aunque a 3m el intervalo de
confianza excluye el cero (gracias al tamaño de muestra, no a la magnitud
del efecto), el propio r=0.0118 no tiene ninguna utilidad práctica como
ranking. Pearson y Spearman divergen en signo a 1m/3m — indicio de que la
relación (si existe) no es monótona y probablemente está dominada por unos
pocos valores extremos, no por una tendencia consistente.

**Por tipo (`type` del registry) — mismo patrón, con matices:**

| type | n | r (1w/1m/3m) | mean α 3m |
|---|---|---|---|
| anticipation | 7.204 | -0.018 / +0.045 / **+0.068** | +0.91 |
| risk_appetite | 7.717 | -0.004 / -0.006 / -0.065 | +0.07 |
| rotation | 6.969 | -0.035 / -0.043 / -0.008 | +0.49 |
| regions | 3.540 | -0.015 / -0.016 / -0.083 | -0.60 |
| sector_snapshot | 16.918 | -0.038 / -0.035 / -0.024 | -0.21 |

`anticipation` es el único bucket con correlación positiva y creciente con
el horizonte — pero r=0.068 a 3m (p<0.0001 solo por el tamaño de muestra)
sigue siendo demasiado pequeño para ordenar nada (r²<0.5% de varianza
explicada). No se investiga más a fondo aquí — queda anotado como el único
matiz que distingue un bucket de otro, no como un hallazgo accionable.

## Grid search en dev y confirmación en test

Metodología y regla de selección completas en
`wiki/PREREGISTRO_RELATIVE_FLOW_LAB_V0.md`. Resumen: 198 combinaciones
evaluadas en dev (168 con n≥20), top-3 por horizonte congeladas (9
entradas, 7 conjuntos distintos por duplicación esperada
`label=Leader`≡`score≥8`), evaluadas una sola vez en test:

| Horizonte | Combinación | dev mean α | test mean α | test win rate | test n | Veredicto |
|---|---|---|---|---|---|---|
| 1w | Laggard/Mixed | +0.271 | -0.183 | 45.3% | 75 | No soportado (signo invertido) |
| 1w | score≥1/Down | +0.180 | +0.149 | 42.9% | 7 | No soportado (n<20) |
| 1w | Laggard/Down | +0.147 | +0.281 | 49.7% | 358 | No soportado (win rate<0.55) |
| 1m | Leader/Mixed (≡score≥8) | +0.931 | -0.780 | 41.5% | 82 | No soportado (signo invertido) |
| 1m | score≥7/Mixed | +0.792 | -0.846 | 41.8% | 103 | No soportado (signo invertido) |
| 3m | Laggard/Mixed | +1.622 | -0.288 | 39.7% | 58 | No soportado (signo invertido) |
| 3m | **Leader/Mixed (≡score≥8)** | +1.020 | **+1.276** | **57.1%** | 63 | **Plausible** |

**1 de 7 combinaciones distintas ("Leader, trend Mixed, horizonte 3 meses")
cumple el criterio modesto de plausibilidad** (mismo signo, win rate≥55%,
n≥20). Con ~200 combinaciones probadas en dev sin corrección por
comparaciones múltiples, encontrar 1 superviviente de 7 no es una
confirmación fuerte — es aproximadamente lo que cabría esperar por azar.
Las otras 6 combinaciones invierten el signo entre dev y test (el patrón
más común) o no alcanzan el win rate mínimo — es decir, lo que "funcionaba"
en dev mayoritariamente **no** se sostuvo en el año más reciente.

## Conclusión

- El score de Relative Flow Lab **no sirve como ranking predictivo de alfa**
  en ninguno de los 3 horizontes evaluados — la correlación pooled es
  ruido, y el único superviviente del grid search (Leader/Mixed a 3 meses)
  es consistente con una single-comparación con suerte, no con una señal
  robusta.
- El bucket `anticipation` merece una nota, no una promoción: es el único
  con correlación positiva y creciente con el horizonte, pero la magnitud
  (r≈0.07 a 3m) es demasiado pequeña para operar.
- **No se recomienda ninguna acción sobre `paper_trading.py`,
  `pcs_calculator.py` ni ninguna cartera viva.** Esto confirma, con un
  método distinto (backtest histórico en vez de correlación PCS↔ret_1m),
  el mismo patrón ya documentado para PCS: el score funciona como filtro
  de elegibilidad/narrativa, no como ranking.

## Fuera de alcance (explícito)

Corrección Newey-West/HAC para la autocorrelación residual; recalibrar los
pesos del score (0.5/0.7/0.25 + ajustes) contra estos datos — el hallazgo
es que la fórmula ACTUAL no predice, no que una fórmula distinta no
pudiera; desglose por par individual (45 series, no solo por type);
extender el backtest a Early Flow Detector (`shared/flow-score.js`,
métrica separada de este módulo); cualquier integración con
`paper_trading.py`/carteras vivas salvo petición explícita del usuario.
