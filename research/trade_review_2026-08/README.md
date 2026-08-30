# Trade Review 2026-08 — datos día a día por ticker

Generado para `wiki/ASESOR_EXTERNO_AUDITORIA_CARTERAS_IA.md` (§5.5). Reconstrucción de un
solo uso, fuera del repo de producción — no forma parte del pipeline.

## El documento con los datos

**`trade_review_signals.csv`** — 3.697 filas, una por (ticker, día), para los 68 tickers
que han tenido alguna operación real en el sistema (114 cerradas + 33 abiertas a
2026-08-30). Ábrelo directamente en Excel/Sheets/lo que sea — es el dato completo
"Koncorde/Flow Score/MACD por ticker y día" que pedía la auditoría, sin resumir ni agregar.

Cada fila cubre desde 25 días naturales antes de la fecha de entrada de esa operación hasta
40 días después del cierre (o de hoy, si sigue abierta) — así se puede ver tanto el
contexto previo a la entrada como lo que pasó después de la salida, no solo el tramo exacto
de la tenencia.

### Columnas

| Columna | Qué es |
|---|---|
| `ticker`, `date` | Identificador de la fila |
| `portfolios_en_ventana` | Cartera(s) que tuvieron una posición abierta en ese ticker ese día concreto (separadas por `\|` si coinciden varias, p. ej. CFL y MIMO_SHADOW el mismo día). **Vacío** = el día cae en el margen de contexto (antes de entrar o después de cerrar), no dentro de la tenencia real — no es un hueco de datos. |
| `price` | Cierre ajustado por dividendos (yfinance, `auto_adjust=False` en la descarga, ver nota abajo) |
| `rsi` | RSI(14), Wilder |
| `macdHist`, `macdBull` | Histograma MACD(12,26,9) y su signo — mismo cálculo que `shared/quote-lib.js → calcMACD` |
| `atrPct` | ATR(14) / precio × 100 |
| `w1_ret_5d`, `m1_ret_21d` | Retorno propio del ticker a 5/21 sesiones (no relativo a SPY — ver §5.5 del documento principal) |
| `fromHigh52w` | Distancia al máximo de las últimas ~252 sesiones, en % |
| `konc_d_blue`, `konc_d_trend_ma`, `konc_d_state` | Koncorde diario — azul (oscilador NVI), **línea roja** (`trend_ma` = EMA(15) de la tendencia RSI+MFI+BB+Stoch — la "señal" de la línea ocre, sin área propia en el mini-gráfico de `portfolio.html`) y estado (`up`/`accumulation`/`distribution`/`down`) |
| `konc_3d_blue`, `konc_3d_trend_ma`, `konc_3d_state` | Koncorde 3D (bloques de 3 sesiones no solapadas), mismas 3 series |
| `konc_w_blue`, `konc_w_trend_ma`, `konc_w_state` | Koncorde semanal (con el fix del 2026-08-30 — solo semanas ya cerradas), mismas 3 series |
| `flowScore`, `earlyFlow` | Flow Score y Early Flow Score — mismas fórmulas que el "Ranking de Setups" de `portfolio.html` |

## Cómo se generó (reproducible)

1. `ohlcv_long_history.json` — OHLCV real (yfinance, `auto_adjust=False`), 2022-06-01 →
   2026-08-30, para los 68 tickers con al menos una operación real (`EQR`, con 2 operaciones
   en MIMO_SHADOW, se descartó — Yahoo solo devuelve 15 sesiones recientes para ese ticker en
   este momento, no hay histórico suficiente).
2. `koncorde_reconstructed_raw.json` — Koncorde D/3D/W para el histórico completo de cada
   ticker, calculado con las funciones reales de `scripts/koncorde_calculator.py`
   (`_calc_koncorde_plus`, `_resample_3d`, `_resample_weekly`, `_state`) importadas
   directamente, no reimplementadas. Válido sin look-ahead porque la normalización interna
   de Koncorde es una ventana móvil estrictamente hacia atrás (`pandas.rolling`, sin
   `center=True`) — el valor en cualquier fecha pasada es idéntico al que habría mostrado el
   pipeline en vivo ese día. Verificado exacto contra producción: PLTR 2026-08-28 da
   `konc_d_blue=-14.80`, igual que el snapshot real de `koncorde_data.json`.
3. `koncorde_windowed.jsonl` — el paso 2 recortado a las ventanas de cada operación
   (intermedio, regenerable).
4. `reconstruct_flow_macd.js` — Node, reutiliza literalmente `shared/quote-lib.js`
   (`calcRSI`, `calcMACD`, `calcATR`) y `shared/flow-score.js` (`computeFlowScore`,
   `computeEarlyFlowScore`) — el mismo código que sirve `portfolio.html` — recorriendo cada
   fecha con la serie de precios recortada hasta ese día (mismo principio sin look-ahead).
   Produce `trade_review_signals.jsonl`.
5. `trade_review_signals.csv` — el JSONL anterior convertido a CSV y anotado con
   `portfolios_en_ventana` (script ad-hoc, no guardado — trivial de rehacer con
   `csv.writer` sobre el JSONL).

Para regenerar desde cero: `trades_windows.json` sale de `docs/data/ai_picks.json` (las 147
operaciones reales del sistema a la fecha en que se generó esto); a partir de ahí, los pasos
2-4 son deterministas sobre `ohlcv_long_history.json`.

## Huecos y limitaciones conocidos

- **Solo 2 de las 4 series de Koncorde Plus.** El mini-gráfico de `portfolio.html` pinta 4
  series (azul, verde, ocre/`trend` crudo, roja/`trend_ma`) — este CSV solo trae azul y roja
  (las dos que ya se usan en el resto del proyecto para clasificar estado y para el research
  log, `konc_d_blue_z`/`konc_d_blue_accel`, etc.). Verde y ocre (`green`/`trend` sin
  suavizar) no están volcadas — sí se calculan en la reconstrucción interna
  (`koncorde_reconstructed_raw.json` las tiene, `block_series()` en el paso 2 devuelve la
  tupla completa) pero no se propagaron al CSV final. Añadirlas es solo tocar
  `reconstruct_flow_macd.js` y regenerar, no hace falta volver a descargar ni recalcular
  nada.
- **Precio con ajuste de dividendos distinto entre documentos.** Este CSV se descargó con
  `auto_adjust=False`; el precio de entrada/salida del Apéndice B del documento principal usa
  `auto_adjust=True` (otra descarga, hecha en otro momento de la misma auditoría). Para la
  inmensa mayoría de tickers de este universo (small caps sin dividendo, o con dividendo
  pequeño) la diferencia es despreciable, pero los dos documentos no están garantizados a
  coincidir al céntimo en `price` para tickers con dividendo significativo — no verificado
  caso por caso.
- `EQR` — sin datos (ver arriba).
- `NBIS` — IPO ~2024-10, menos de 2 años de histórico; su Koncorde semanal puede faltar
  (`null`) en sus primeras operaciones por warmup insuficiente (`MIN_BARS=100` semanas), no
  por error.
- Precio de cierre a cierre, sin intradía. `w1`/`m1` son el retorno propio del ticker, no
  relativo a SPY.
- Esto es una reconstrucción retroactiva, no una captura en vivo — el sistema real no
  guardaba estos datos para estas operaciones en su momento (esa captura diaria completa
  solo existe desde 2026-08-20, ver CLAUDE.md). No se ha verificado punto a punto contra
  producción para los 68 tickers, solo el caso PLTR citado arriba y la coherencia interna
  (Mirror Espejo con Flow Score negativo en el 100% de sus entradas, consistente con su
  diseño documentado).

Ver `wiki/ASESOR_EXTERNO_AUDITORIA_CARTERAS_IA.md` §5.5 para el análisis agregado sobre este
mismo dato — este README documenta solo los datos crudos, no las conclusiones.
