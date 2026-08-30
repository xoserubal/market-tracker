# Backtest "Cruce Rojo D" — marrón/rojo de Koncorde sobre el universo completo

Investigación previa a implementar `scripts/cruce_rojo_d_portfolio.py`
(cartera CRUCE_ROJO_D, ver CLAUDE.md). Universo Koncorde completo (198-199
tickers), OHLCV 2022-06-01→2026-08-30, `auto_adjust=False`.

## Resultado final (datos limpios, ver "Hallazgo de datos" abajo)

| Condición de entrada | señales | tickers | media | mediana | % gana | peor | mejor | días en cartera (mediana) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Sin filtro (cualquier cruce) | 14.673 | 198 | +0.63% | -1.04% | 33.7% | -54.4% | +417.9% | 6 |
| Marrón < 0 (literal) | 12 | 10 | +1.09% | -1.44% | 41.7% | -10.3% | +19.1% | 24 |
| Marrón en percentil ≤10 propio (252 ses.) | 176 | 111 | +2.42% | -1.02% | 36.9% | -11.8% | +89.5% | 16 |
| RSI < 30 | 190 | 81 | +2.88% | -0.42% | 34.2% | -20.8% | +92.3% | 12 |
| Marrón percentil ≤25 Y RSI < 30 | 134 | 73 | +3.70% | -0.65% | 38.1% | -11.9% | +92.3% | 18 |
| **Marrón percentil ≤10 Y RSI < 30 (elegida)** | **38** | **31** | **+5.39%** | -0.42% | **39.5%** | **-8.7%** | +89.5% | 22 |

Condición elegida para la cartera real: la última fila (percentil≤10 Y
RSI<30) — mejor perfil de riesgo de todas las probadas, decidida con el
usuario tras ver esta tabla.

**Todas las condiciones tienen mediana negativa pese a media positiva** —
firma clásica de seguimiento de tendencia (pocos ganadores grandes, muchas
pérdidas pequeñas), no una señal de "acierta la mayoría de las veces".

## Hallazgo de datos — dos tickers `.L` con saltos de escala 100x

`MAI.L`: glitch transitorio de 3 sesiones (2025-12-22/23/24), típico error
GBX/GBP (peniques vs libras) de Yahoo — corregido, reescalado.
`FXPO.L`: mismo tipo de salto pero **persistente desde 2026-05-18, sin
revertir** — no se corrigió a ciegas, se **excluyó** del universo. Sin esta
limpieza, el peor caso de varias condiciones salía en -99%, puro artefacto.

## Ficheros

| Fichero | Contenido | En git |
|---|---|---|
| `backtest_trades_by_condition.json` | Lista completa de operaciones (ticker, entrada, salida, retorno) por cada una de las 8 condiciones probadas | Sí |
| `ohlcv_universe.json` / `ohlcv_universe_cleaned.json` | OHLCV crudo/limpio, 198-199 tickers | No (gitignored, cache regenerable) |
| `trend_rsi_universe.json` | Series diarias de trend/trend_ma/RSI/close reconstruidas | No (gitignored, cache regenerable) |

Para regenerar las cachés: repetir la descarga yfinance (2022-06-01→hoy,
`auto_adjust=False`) para los tickers de `docs/data/koncorde_data.json`,
aplicar la corrección de escala (ver hallazgo de datos arriba) y volver a
calcular `trend`/`trend_ma` con `scripts/koncorde_calculator.py::_calc_koncorde_plus`.
