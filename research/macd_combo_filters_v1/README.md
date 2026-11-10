# Combo MACD + filtros (Koncorde, Early Flow, sector, extensión, fuerza relativa, mercado) — v1

Continuación de `research/macd_combo_sp500_ndx_v1/` (el combo MACD solo no tiene ventaja en S&P 500 + Nasdaq 100).
Pregunta: ¿algún filtro, solo o sumado al combo MACD, da retorno por encima del universo a 7/14/21/28 días?

## Preregistro (escrito 2026-11-10, antes de calcular ningún filtro)

**Universo y datos:** los 518 valores de `macd_combo_sp500_ndx_v1` (componentes actuales; sesgo de supervivencia).
yfinance diario 2015-01-02 → 2026-11-09, con apertura y volumen; ETF sectoriales SPDR para el filtro C.

**Señal MACD:** la misma del estudio anterior (copia de `shared/screener-lib.js`): `hist_cross_confirmed` y
`line_near_zero_up` a la vez.

**Filtros** (evaluados con datos hasta el cierre del día de la señal; un filtro sin datos cuenta como no cumplido):
- **A — Koncorde no en distribución:** ni el estado 3D ni el semanal son `distribution`. Cálculo con
  `scripts/koncorde_calculator.py` (`_calc_koncorde_plus`, `_state`) sobre precios ajustados. El 3D se reconstruye
  con bloques de 3 sesiones que terminan en el día de la señal, como hace el pipeline. El semanal usa la última semana
  cerrada.
- **B — Early Flow activo:** `computeEarlyFlowScore` de `shared/flow-score.js` (el mismo código de la pestaña, vía
  Node) ≥ 4 («Interesante» o «Fuerte»). Las entradas se reconstruyen como en `shared/quote-lib.js`: RSI14,
  ATR% (redondeado a 0,1), distancia al máximo de 365 días, retornos de 5 y 21 sesiones redondeados, estados de
  Koncorde. La sesión anterior aporta las entradas «prev».
- **C — Sector favorable:** el ETF de su sector GICS (XLK, XLF, XLV, XLY, XLP, XLE, XLI, XLB, XLRE, XLC, XLU) frente
  a SPY está en Leader o Improving, con `buildRowFromRatio` + `classify` de `shared/relative-lib.js`. Sector actual
  aplicado a todo el periodo (anacronismo de la reclasificación GICS de 2018). XLC solo existe desde jun-2018.
- **D — No extendido:** (cierre − SMA20) / ATR14 < 1,5.
- **E — Fuerza relativa:** retorno de 63 sesiones del valor menos el de SPY > 0.
- **F — Mercado favorable:** SPY cierra por encima de su SMA200 (el motor de Cava no está instalado en este equipo).
- **ABC:** A, B y C a la vez (la combinación propuesta por el usuario).

**Hipótesis medidas (14):** cada filtro solo (A, B, C, D, E, F, ABC) y MACD + cada uno.
Evento = primer día en que se cumple tras ≥ 10 días naturales sin cumplirse (en las de MACD + X: evento del combo
MACD en el que X se cumple ese día). Referencia: el combo MACD solo.

**Medición:** entrada al cierre de la sesión siguiente; plazos de 5, 10, 15 y 20 sesiones (≈ 7/14/21/28 días).
Exceso = retorno − media equiponderada del universo en la misma ventana, menos 0,2 % de coste. Significación con t
agrupado por semana de entrada.

**Selección y confirmación (la parte que decide):**
1. Desarrollo = señales de 2016-2020. De las 56 combinaciones (14 hipótesis × 4 plazos) se eligen como máximo 3 con
   exceso neto > 0, t ≥ 2 y n ≥ 100, las de mayor t.
2. Prueba = señales de 2021-01-01 a 2026-11-09, una sola vez, solo para las elegidas. Se confirma si el exceso neto
   > 0 con t ≥ 2,4 (corrección por hasta 3 pruebas).
3. Se informa también si una combinación MACD + X confirmada supera a X solo. Si no lo supera, el MACD no aporta.

Si nada se confirma: no hay evidencia y no se monta nada. Si algo se confirma: se propone vigilarlo en sombra con su
propio preregistro, sin tocar las carteras existentes. Las 56 cifras de ambos periodos se publican igualmente.

## Resultados (2026-11-10) — no hay evidencia

**Validación de la reconstrucción:** Koncorde coincide con `koncorde_data.json` del 2026-11-09 en 42/42 valores
comunes en diario, 3D y semanal. Early Flow frente al `earlyFlow` del snapshot diario (1 341 filas): 63 % idéntico,
92 % a ±1 punto, 93 % en el mismo lado del umbral 4 (en vivo la «sesión anterior» es la captura anterior del pipeline,
que a veces se repite o salta días).

**Selección en desarrollo (2016-2020): ninguna de las 56 combinaciones cumple exceso neto > 0 con t ≥ 2.** No hay nada
que confirmar en 2021-2026. Todas las cifras (exceso neto de 0,2 % frente a la media del universo; sumar 0,2 para el
bruto) están en `results.json`. Resumen a 10 sesiones (≈ 14 días):

| | Desarrollo 2016-2020 | Prueba 2021-2026 |
|---|---|---|
| MACD (referencia) | −0,36 (t −3,6, n 4 991) | −0,14 (t −1,2, n 6 627) |
| A Koncorde 3D/W no en distribución | −0,17 / MACD+A −0,35 | −0,31 / MACD+A −0,14 |
| B Early Flow ≥ 4 | −0,19 / MACD+B −0,37 | −0,15 / MACD+B −0,22 |
| C sector Leader/Improving | −0,34 / MACD+C −0,29 | −0,20 / MACD+C −0,16 |
| D no extendido | −0,25 / MACD+D −0,36 | +0,01 / MACD+D −0,15 |
| E fuerza relativa 63 ses. > 0 | **−0,60 (t −5,6)** / MACD+E −0,29 | **−0,35 (t −3,2)** / MACD+E −0,10 |
| F SPY > SMA200 | −0,17 / MACD+F −0,31 | −0,18 / MACD+F −0,10 |
| ABC | −0,30 / MACD+ABC −0,13 (n 542) | −0,25 / MACD+ABC −0,35 (n 776) |

Lectura:
- En bruto, casi todo queda en 0 ± 0,2 pp: ningún filtro ni combinación hace que una acción del S&P 500 / Nasdaq 100
  rinda más que la media en las 1-4 semanas siguientes. Aciertos del 44-49 %.
- MACD+ABC (lo propuesto) llega a +0,28 a 15 sesiones en desarrollo, con t 0,8 y n 542, y en prueba es negativo a
  todos los plazos (−0,52 a 15 sesiones).
- Único efecto robusto y **en contra**: la fuerza relativa positiva a 3 meses (E) rinde por debajo del universo a
  1-4 semanas en los dos periodos (reversión de corto plazo, conocida en la literatura). No sirve como filtro de compra.
- Limitación: F (mercado) afecta a todos los valores a la vez, así que medido contra la media del universo no puede
  dar exceso. Solo podría ayudar en retorno absoluto, que este estudio no mide.

Conclusión: no se monta vigilancia ni cartera de estas combinaciones en grandes empresas de EE.UU.

Ficheros: `fetch_data.py`, `build_features.py`, `early_flow.js`, `sector_regime.js`, `analyze.py`, `sectors.json`,
`results.json`. Fuera de git: `prices_cache.parquet` y `_work/` (regenerables).
