# Plan — Backtest histórico de Relative Flow Lab como señal

**Estado: plan aprobado por el usuario 2026-08-07, implementación sin empezar.**
Copiado aquí desde `~/.claude/plans/humble-jumping-moth.md` (fuera del repo,
no viaja entre máquinas) para poder retomarlo desde cualquier PC. Al empezar
a implementar, seguir el "Orden de trabajo" tal cual, paso 1 primero.

## Contexto

El usuario cree que Relative Flow Lab (`relative.html`) — 45 ratios de precios
puntuados a diario (Score, clasificación Leader/Improving/Neutral/Weakening/
Laggard, Trend Up/Down/Mixed) — podría tener utilidad real como señal de
compra/venta, y quiere comprobarlo con datos en vez de intuición: ¿el activo
A de un ratio genera alfa (retorno de A menos retorno de SPY) en las semanas/
meses siguientes cuando el ratio da Leader/Improving + Trend Up + Score alto?

No existen snapshots diarias guardadas — la página es 100% cliente, recalcula
todo en vivo en cada carga, sin persistencia (decisión explícita documentada
en CLAUDE.md al rediseñar Relative Flow Lab v2). Pero el pipeline de scoring
es una función determinista del histórico de precios — igual que
`extension_risk`, es reconstruible sin haber loggeado nada por adelantado.

El usuario ya aceptó el riesgo de overfitting de "jugar con combinaciones de
parámetros" y acordó una disciplina dev/test: buscar combinaciones solo sobre
un tramo de desarrollo, confirmar una única vez sobre un tramo de test
reservado, sin re-ajustar después de verlo. Alcance explícitamente limitado a
investigación — no se integra nada en `paper_trading.py`, `pcs_calculator.py`
ni ninguna cartera viva salvo que los hallazgos sean sólidos y el usuario lo
pida aparte, como seguimiento explícito.

## Decisiones de diseño (con motivo)

1. **Cierres ajustados por dividendo (yfinance `auto_adjust=True`) para todo
   — score y retorno futuro.** `/api/history/:symbol` en `server.js` sirve el
   `close` de Yahoo ajustado solo por splits, sin dividendos — reconstruir con
   `auto_adjust=True` no va a coincidir barra a barra con lo que muestra la
   página en vivo. Para la pregunta real ("¿esto genera alfa económico de
   verdad?") el ajuste por dividendo es la base correcta, sobre todo en pares
   con yield no trivial (HYG, TLT, BIL, GLD, SPY). Desviación declarada
   explícitamente en el código y en el informe final, con un chequeo puntual
   contra la página en vivo para documentar la magnitud de la divergencia
   esperada (pequeña, por el ajuste de dividendo).

2. **RSI — puerto literal del bucle de Wilder de `calcRSI`, no reutilizar
   `_rsi14` de `reconstruct_extension_risk_historical.py`.** Ese helper ya
   existente usa `rolling().mean()` (RSI de Cutler) — matemática distinta,
   no va a coincidir numéricamente. Hay que transliterar el bucle recursivo
   exacto de `calcRSI` (semilla = media simple de los primeros 14 deltas,
   luego suavizado recursivo `(prev*(period-1)+actual)/period`), calculado
   una sola vez por serie completa (pase único hacia adelante, O(n)) en vez
   de re-sembrar cada día sobre una ventana de 3 años (lo que hace la página
   en vivo en cada carga) — justificado porque el suavizado de Wilder tiene
   memoria exponencialmente decreciente (vida media ~14 barras): pasadas
   ~300 barras desde cualquier punto de arranque, un cálculo acumulado desde
   el inicio y uno re-sembrado cada 3 años convergen al mismo valor. Por eso
   se descartan (marcadas, no borradas) las primeras 300 sesiones de cada
   serie alineada como "burn-in".

3. **El registry de ratios se carga desde el JS real vía Node, nunca se
   copia a mano a Python.** `shared/relative-ratio-registry.js` es un IIFE
   que expone `window.RATIO_REGISTRY` — verificado que carga sin problema
   con un shim mínimo:
   ```
   node -e "global.window=global; require('./shared/relative-ratio-registry.js'); console.log(JSON.stringify(RATIO_REGISTRY))"
   ```
   (confirmado: devuelve las 45 entradas). Copiar el registry a mano
   reproduciría exactamente el tipo de deriva que este proyecto ya tuvo que
   arreglar dos veces (`ai_shared.py`, `calcCMF` duplicado). El script de
   reconstrucción llama a Node en cada ejecución y además vuelca el export a
   `docs/data/relative_ratio_registry_export.json` — efecto colateral útil:
   si el registry JS cambia, se ve en el diff de ese archivo.

4. **Reconstrucción completa en cada ejecución, no append-only.** A
   diferencia de `shadow_picks.jsonl` (donde interesa congelar lo que se
   sabía en el momento de decidir), aquí no hay "decisión" que proteger de
   contaminación — cada fila mejora con el tiempo según madura el retorno
   futuro. Mismo patrón que `cfl_reentry_cooldown_shadow.py` (reconstruye
   entero cada vez, documentado explícitamente en su docstring).

5. **Autocorrelación por solapamiento — mitigado, no ignorado.** Con una
   fila por día, las ventanas de retorno futuro a 21/63 sesiones se solapan
   casi por completo entre días consecutivos — tratar cada fila como
   observación independiente infla la significancia aparente. El script de
   análisis re-muestrea por defecto a **una fila por par y semana ISO**
   (`--no-resample` para desactivarlo) y tanto el código como el informe
   final dejan dicho por escrito que los p-valores siguen siendo optimistas
   pese al resampleo — una corrección Newey-West/HAC completa queda fuera de
   alcance a propósito (mismo principio ya citado en CLAUDE.md: no añadir
   complejidad antes de que los datos la justifiquen).

6. **Corte dev/test: fecha de calendario única, no porcentaje por par.** Los
   pares tienen historiales de duración muy distinta (SPY/GLD llevan décadas;
   AMR, HCC, CCJ/URNM, XLC, XLRE, URA solo 5-9 años). Un "últimos 20% por
   par" pondría el tramo de test de cada par en un régimen de mercado
   distinto. En su lugar: **corte único, `hoy - 365 días naturales`**
   (calculado en tiempo de ejecución, no como fecha fija en el código) — dev
   = todo lo anterior, test = ese último año, igual para los 45 pares. Los
   horizontes de 1m/3m cerca del final del tramo de test no van a tener
   retorno futuro válido todavía (no hay datos de "mañana") — se documenta
   esa asimetría en vez de ocultarla, no se aproxima.

7. **Burn-in marcado (`burn_in: true/false`), no descartado en la
   reconstrucción** — así el script de análisis (o cualquier chequeo de
   sensibilidad futuro) puede decidir incluirlo o no sin recalcular nada.

8. **Freno de código contra "espiar" el test.** El script de análisis solo
   toca el tramo de test si se pasa `--confirm-test` explícito (con aviso
   impreso bien visible) — el modo normal de iteración solo ve dev. Convierte
   el acuerdo de "no re-ajustar tras ver el test" en una barrera de código,
   no solo una promesa.

9. **Dependencias: no hace falta tocar `requirements.txt`.** Verificado que
   `backtest/requirements.txt` (el que instala realmente el workflow, no el
   `requirements.txt` de la raíz) ya trae `pandas`, `yfinance` y `scipy`.

## Fórmulas exactas a portar (de `relative.html`, líneas ~143-219)

```js
alignRatio(aSeries, bSeries)   // inner join por fecha exacta (string), value = a.close/b.close
ret(arr, bars)                 // (last/prev - 1) * 100, null si no hay suficiente historia
retWindow(arr, endOffset, bars)
sma(values, len)                // media simple de los últimos `len` valores
calcRSI(values, period=14)      // Wilder EXACTO: semilla = media simple de los primeros 14 deltas,
                                 // luego (prev*(period-1)+actual)/period recursivo. loss===0 -> 100.
buildRow(pair, history)          // r1w=ret(5) r1m=ret(21) r3m=ret(63) r6m=ret(126, NO se usa en score)
                                  // flowChange = retWindow(0,5) - retWindow(5,5), clip ±3 tras *0.4
                                  // trend: last>s20>s63 -> Up; last<s20<s63 -> Down; si no, Mixed
                                  // trendAdj: Up=+2 Down=-2 Mixed=0
                                  // rsiAdj: >65=+1.5 >55=+0.8 <35=-1.5 <45=-0.8 si no 0
                                  // score = round(((r1w??0)*0.5 + (r1m??0)*0.7 + (r3m??0)*0.25
                                  //         + trendAdj + rsiAdj + flowChangeAdj) * 10) / 10
                                  // <70 puntos alineados -> sin score (error:true), igual que la página
classify(row)                    // >=8 Leader, >=3 Improving, <=-8 Laggard, <=-3 Weakening, si no Neutral
```

## Registry — 45 pares, ~47 tickers únicos (incl. SPY)

risk_appetite(7) · anticipation(11) · rotation(7) · regions(4) ·
sector_snapshot(16). Lista completa vía `load_ratio_registry()` (Node), no
se copia a mano — ver decisión #3.

## Ficheros nuevos

### 1. `scripts/relative_flow_lib.py`
Funciones puras, sin I/O de red, importadas tanto por el script de
reconstrucción como por los tests (evita que la lógica se desincronice):
`load_ratio_registry()`, `align_ratio()`, `vectorized_ret()`,
`vectorized_ret_window()`, `rolling_sma()`, `wilder_rsi_expanding()`
(puerto literal de `calcRSI`, pase único), `trend_label()`,
`score_from_components()`, `classify_label()`, `compute_pair_series()`
(orquesta todo lo anterior fila a fila, "a fecha de ese día", sin mirar al
futuro — propiedad estructural distinta de las etiquetas de retorno futuro,
que sí usan datos posteriores a propósito, como objetivo).

### 2. `scripts/test_relative_flow_lib.py`
Mismo patrón que `scripts/test_cava_mapping.py`/
`scripts/test_numeric_claims_validation.py` (sin pytest). **Se escribe y se
deja en verde antes de tocar el script de reconstrucción** — es la pieza de
mayor riesgo de estar mal (el puerto de Wilder). Casos:
- RSI: serie monótona creciente → 100 exacto (replica el quirk de la JS, no
  se "corrige"); serie monótona decreciente → cerca de 0; ejemplo de Wilder
  calculado a mano.
- Cross-check independiente: recalcular RSI con
  `pandas.Series(deltas).ewm(alpha=1/period, adjust=False)` (matemáticamente
  equivalente si se siembra bien) y comprobar que ambas implementaciones
  coinciden — dos caminos independientes de acuerdo es más fuerte que uno.
- `align_ratio`: fechas descuadradas, nulls en una sola pata, valores no
  finitos.
- `trend_label`: empates exactos (`last==s20==s63` → Mixed).
- `classify_label`: valores frontera exactos (7.9 vs 8.0, etc.).
- Score end-to-end sobre una serie sintética calculada a mano.
- **Chequeo de valor real contra la página en vivo**: cargar `relative.html`
  (servidor local, mismo patrón que el resto de páginas de este proyecto —
  reiniciar `node server.js` tras cambios en rutas `/api/*`) para 3-5 pares
  (uno de historial largo tipo `xlk_spy`, uno corto tipo `ura_urnm`),
  anotar score/RSI/trend/label reales, hardcodear como test con tolerancia
  documentada (no igualdad exacta — la desviación de dividendo garantiza
  pequeña divergencia), mismo trend/clasificación exigidos, score dentro de
  una banda a afinar con el primer chequeo real.

### 3. `scripts/reconstruct_relative_flow_historical.py`
- Flags: `--dry-run`, `--pairs xlk_spy,ura_urnm` (iteración rápida),
  `--no-fetch`/`--save-cache` (caché de precios, patrón de
  `compare_vs_baselines.py`), `--report`.
- Descarga única: `yf.download(all_syms, period="max", auto_adjust=True, threads=True, progress=False)`
  — `period="max"` porque la disponibilidad varía muchísimo por ticker.
- Mismo manejo de columnas single/multi-ticker y `skipped_no_data` que
  `reconstruct_extension_risk_historical.py`.
- Por par: `align_ratio` → `compute_pair_series` → fila diaria de
  score/trend/label.
- Retorno futuro de A y de SPY calculados cada uno sobre **su propio
  calendario de cotización** (no el del ratio alineado — BTC-USD cotiza
  todos los días naturales, los futuros tienen su propio calendario),
  mismo idioma de "fecha más cercana ≤ objetivo" que ya usa
  `reconstruct_extension_risk_historical.py` para `ret_5d_vs_spy`. Horizontes
  5/21/63 sesiones. `fwd_alpha_{1w,1m,3m} = fwd_ret_a - fwd_ret_spy`, `null`
  si no hay suficientes sesiones futuras todavía (nunca aproximado).
- Marca `burn_in` (primeras 300 sesiones alineadas) y `split` (`dev`/`test`,
  corte = hoy − 365 días naturales, calculado en tiempo de ejecución).
- Salida: `docs/data/relative_flow_history_reconstructed.jsonl` — una fila
  por (par, día): `pair_id, type, cluster, a, b, date, ratio_value, r1w, r1m,
  r3m, r6m, flow_change, rsi, trend, score, label, fwd_ret_a_{1w,1m,3m},
  fwd_ret_spy_{1w,1m,3m}, fwd_alpha_{1w,1m,3m}, burn_in, split,
  bars_in_aligned_series, reconstructed_at`.
- `--report`: recuento de filas/rango de fechas/burn-in/dev-test por par,
  aviso explícito de los pares de historial corto (AMR, HCC, CCJ/URNM, XLC,
  XLRE, URA, BTC-USD) para que no se descubran solos más tarde.

### 4. `scripts/analyze_relative_flow_signal.py`
La parte barata y re-ejecutable — esto es lo que permite "jugar con
combinaciones" sin volver a descargar ni recalcular nada:
- `load_history()`, `resample_weekly()` (activado por defecto),
  `split_dev_test()`.
- `compute_baseline()` — alfa medio/mediana/win-rate incondicional, agrupado
  y por `type` — el punto de comparación obligatorio (mismo principio que
  `baselines.jsonl`: nunca reportar una señal sin su baseline mecánica al
  lado).
- `compute_correlation()` — Pearson r + Spearman ρ, p-valor, IC95% vía
  Fisher z (mismo patrón que `ranking_score_fase1_analysis.py`).
- `compute_group_stats()` — por `(label, trend)`, n/media/mediana/win-rate/
  t-test de Welch vs. baseline, agrupado y por `type`.
- `GRID` (constante congelada, ver preregistro): combinaciones de
  label×trend y de score_min×trend, × 3 horizontes (~200 combinaciones,
  barato porque es puro pandas sobre un fichero ya materializado).
- `run_grid_search()` — solo sobre dev, descarta combinaciones con n<20
  (fijado de antemano), ordena por alfa medio (reporta también win-rate y
  t-stat, no solo el ranking).
- `evaluate_test()` — **solo alcanzable con `--confirm-test`** (aviso
  impreso), aplica exactamente las combinaciones ya congeladas del
  preregistro sobre el tramo de test.
- Salida: `docs/data/relative_flow_signal_results.json`.

### 5. `wiki/PREREGISTRO_RELATIVE_FLOW_LAB_V0.md`
Se escribe **después** de validar la reconstrucción pero **antes** de correr
el grid search — mismo papel que `PREREGISTRO_RANKING_SCORE_V0.md`, del
mismo tamaño reducido que el usuario ya prefirió ahí (~1 página, no 10-15).
Contenido: el `GRID` congelado, la fecha de corte y por qué es única y no
por par, la regla de selección (máx. top-3 combinaciones por horizonte desde
dev, congeladas, evaluadas una sola vez en test), criterios modestos de
"plausible"/"no soportado", y el aviso de los pares de historial corto.

### 6. `wiki/RELATIVE_FLOW_LAB_HALLAZGOS.md`
Se escribe una sola vez, después de la confirmación en test. Metodología +
desviaciones declaradas + baseline + correlación + stats por grupo (pooled y
por type) + resultado del grid en dev + confirmación en test + veredicto
explícito + línea de "fuera de alcance": esto es investigación, no se toca
`paper_trading.py`/`pcs_calculator.py`/ninguna cartera salvo petición
explícita aparte.

### 7. `CLAUDE.md`
Sección nueva al final del proceso (no antes), resumiendo qué se construyó,
dónde vive todo, y el veredicto en una línea.

## Orden de trabajo

1. `relative_flow_lib.py`
2. `test_relative_flow_lib.py` — verde antes de seguir
3. `reconstruct_relative_flow_historical.py` (`--dry-run --pairs xlk_spy`
   primero, luego `--report` completo)
4. Chequeo puntual contra la página en vivo (retroalimenta la tolerancia del
   test dorado del paso 2)
5. `analyze_relative_flow_signal.py` (baseline/correlación/stats primero,
   sanity-check en dev antes de montar el grid search)
6. `PREREGISTRO_RELATIVE_FLOW_LAB_V0.md` — grid y reglas congeladas
7. `run_grid_search` solo en dev, seleccionar y anotar combinaciones top
8. `--confirm-test` una única vez
9. `RELATIVE_FLOW_LAB_HALLAZGOS.md`
10. `CLAUDE.md`

## Verificación

- Los tests unitarios del paso 2 (RSI sintético + cross-check independiente
  + casos frontera + score end-to-end + chequeo dorado contra la página real).
- Aserción de "no look-ahead": cada fila del score solo indexa
  `values[0:t+1]`; los campos `fwd_*` solo indexan `values[t+1:]` —
  estructuralmente imposible que el score vea su propia etiqueta.
- Pase de cordura sobre la reconstrucción completa: recuentos de filas por
  par razonables según la fecha de IPO/lanzamiento conocida de cada ticker,
  recuento de burn-in y dev/test coherente, los pares de historial corto
  visiblemente cortos (no llenos por error).
- Advertencias explícitas, en código y en el informe final: la significancia
  sigue siendo optimista pese al resampleo semanal (autocorrelación
  residual); ~200 combinaciones en el grid de dev significa que los
  "ganadores" en dev son optimistas por diseño — lo que importa de verdad es
  la confirmación en test, hecha una sola vez.
