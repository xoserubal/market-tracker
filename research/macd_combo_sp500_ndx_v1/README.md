# Combo MACD sobre S&P 500 + Nasdaq 100 (v1)

Pregunta: la combinación `hist_cross_confirmed` + `line_near_zero_up` del Screener (la que alimenta
`MACD_COMBO_CD/SD`) ¿tiene ventaja en grandes empresas de EE.UU.?

## Preregistro (escrito 2026-11-10, antes de ejecutar el backtest)

**Universo:** componentes actuales del S&P 500 y del Nasdaq 100 (Wikipedia, 2026-11-10; 518 valores).
Sesgo de supervivencia: faltan las empresas que salieron del índice; el resultado sale optimista.

**Datos:** yfinance diario, `auto_adjust=False` (mismo precio que `/api/quote`), 2015-01-02 → 2026-11-09
(se descarta la vela del 2026-11-10, parcial). Señales desde que hay 200 sesiones de historia.

**Reglas, copiadas sin cambios de `shared/screener-lib.js` y `shared/quote-lib.js`:**
- MACD 12/26/9 con EMA sembradas por SMA; ATR14 de Wilder; SMA50/SMA200 simples.
- `hist_cross_confirmed`: histograma de hoy ≥ 0 y la racha verde empezó hace ≤ 10 sesiones.
- `line_near_zero_up`: línea MACD < 0, cierre > SMA200, SMA50 > SMA200, línea hoy − hace 5 sesiones > 0,
  |línea| / ATR14 ≤ 1,0.
- Combo = las dos a la vez en la misma barra.

**Mediciones (todas con entrada al cierre de la sesión siguiente a la señal):**
1. Plazo fijo de 5, 10 y 21 sesiones. Exceso = retorno − media equiponderada del universo en la misma ventana.
2. Regla de la cartera: salida en la primera barra posterior a la entrada con histograma ≤ 0, ejecutada al cierre
   siguiente. CD = evento solo tras ≥ 10 días naturales sin ser candidato; SD = cada día candidato, una posición
   por valor. Comparación con la media del universo en las mismas fechas; coste 0,2 % ida y vuelta.
3. Referencias: cada filtro por separado y todos los días (sin filtro).
4. Desglose por mitades (2016-2020 / 2021-2026), por año y por régimen de SPY (bajista = cierre < SMA200;
   alcista = ≥ SMA200, ≥ SMA50 y SMA50 ≥ SMA200; lateral = el resto).

**Significación:** t agrupando por semana de entrada (eventos de la misma semana no son independientes).

**Criterio fijado de antemano.** Hay evidencia a favor solo si se cumplen las tres:
- (a) Combo CD a 10 sesiones: exceso medio > 0 con t ≥ 2.
- (b) Mismo signo en las dos mitades.
- (c) Regla de cartera CD: exceso neto de 0,2 % > 0 con t ≥ 2.

Si no se cumplen las tres, no hay evidencia y no se monta vigilancia diaria del S&P 500 / Nasdaq 100.
Nada de esto cambia las carteras existentes.

## Resultados (2026-11-10) — no hay evidencia

Réplica verificada contra el Screener real: en los 28 valores que están en ambos universos, mis marcas coinciden
con las del snapshot en 829/834 filas (99,4 %) para cada filtro; las 5 diferencias son casos en el límite.

**Criterio preregistrado: (a) no, (b) no, (c) no → no se cumple.**

Exceso frente a la media del universo, eventos con cooldown de 10 días, entrada al cierre siguiente:

| | n | 5 sesiones | 10 sesiones | 21 sesiones |
|---|---:|---|---|---|
| Combo | ~11 750 | −0,04 (49 %) | −0,02 (48 %), t −0,3 | −0,07 (48 %) |
| Solo cruce del histograma | ~43 000 | −0,08 (t −2,0) | −0,03 | −0,09 |
| Solo «cerca de cruzar 0» | ~13 400 | +0,02 | +0,02 | +0,02 |
| Todos los días (referencia) | 1,37 M | 0,00 (49 %) | −0,01 (49 %) | −0,02 (48 %) |

- Mitades (combo, 10 ses.): 2016-2020 −0,14 (t −1,4); 2021-2026 +0,07 (t 0,6). Ningún año pasa de ±0,6 pp.
- Régimen SPY (combo, 10 ses.): alcista +0,07, lateral −0,12, bajista −0,28; nada significativo.
- Regla de cartera (salida al girar el histograma, mediana 13 sesiones): CD n=11 643, retorno medio +0,72 %
  pero exceso −0,16 (−0,36 tras 0,2 % de coste, t −3,6), acierto vs universo 39 %. SD casi idéntico.
  La regla de salida resta: corta las ganadoras al primer giro del histograma.
- Frecuencia: ~1 000 eventos al año sobre 518 valores (unos 2 por valor y año).

Lectura: el +3 pp a 14 días del informe del Screener (26 eventos, ~2 meses, un solo tipo de mercado) era ruido.
En 10 años de grandes empresas, comprar cuando se cumple el combo rinde lo mismo que comprar cualquier valor
cualquier día. No se monta vigilancia del S&P 500 / Nasdaq 100. Las carteras `MACD_COMBO_CD/SD` siguen como
estaban (su evaluación preregistrada no cambia), pero este resultado reduce mucho la probabilidad de que salga algo.

Ficheros: `backtest.py`, `fetch_prices.py`, `constituents.json`, `results.json`, `trades_CD.csv`, `trades_SD.csv`;
`prices_cache.parquet` fuera de git (regenerable con `fetch_prices.py`).
