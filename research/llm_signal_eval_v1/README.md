# Evaluación retroactiva de las señales de Sol (v1, 2026-10-27)

`py -3.12 eval.py` (el `py -3` no tiene pandas). Cruza `docs/data/market_analysis_llm.jsonl`
(31 informes, 2026-09-13 a 2026-10-27, 360 señales) con cierres de yfinance.

**Método (fijado antes de mirar retornos):** `subject` es texto libre → `resolve.py` lo traduce a
tickers (cesta de hasta 6, media simple; en «A vs B» solo la pata A; 354/360 resueltos). Entrada =
cierre de la sesión siguiente a la fecha del informe; horizontes 1/3/5/10 sesiones; resultado =
retorno de la cesta menos SPY. Evento independiente = mismo (ticker primario, convicción) sin
repetirse en 5 sesiones (207 independientes). No evalúa la narrativa, ni trigger/invalidation,
ni subjects sin ticker.

## Resultado (alfa medio vs SPY, eventos independientes)

| Convicción | h1 | h3 | h5 | h10 |
|---|---|---|---|---|
| EARLY | -0.22 (n35) | -0.47 | -0.62 | -0.67 (n26) |
| CONFIRMED | +0.32 | -0.17 | -0.88 | -2.32 (n17) |
| EARLY+CONFIRMED | -0.02 | -0.34 | -0.71 | -1.32 (n43) |
| MATURE | -0.31 | -1.80 | -3.25 | -3.39 (n7) |
| EXTENDED | -0.21 | -3.44 | n2 | -7.14 (n3) |
| bajistas (DIST/INVAL/EXT) | -0.35 | -1.93 (t-3.0) | -0.35 | -3.87 (n26, t-2.9) |

- Las etiquetas alcistas (EARLY/CONFIRMED) **no baten a SPY** en ningún horizonte (t entre -0.1 y -1.5).
- Las etiquetas **bajistas/de madurez sí apuntan en la dirección correcta** (MATURE, EXTENDED,
  INVALIDATED, DISTRIBUTION rinden por debajo de SPY a 3-10 sesiones). Es la parte con algo de señal,
  pero n pequeño (3-26), 7 etiquetas × 4 horizontes sin corrección por comparaciones múltiples,
  y los eventos del mismo día comparten régimen de mercado (el t real es menor).
- Confianza declarada (`confidence_pct`) **no discrimina**: ≥70 % no rinde mejor que 55-70 %
  (a 10 sesiones es peor: -2.91 vs +0.34).
- EARLY→CONFIRMED: de 54 tickers con EARLY, 12 llegaron a CONFIRMED. Alfa a 5 sesiones desde el
  EARLY: +0.52 (n=6, los que luego confirmaron) vs -1.91 (n=22, los que no); entrar tarde, en el
  CONFIRMED: -5.23 (n=3). **n demasiado pequeño para concluir nada.**

## Limitaciones que condicionan todo
- Solo ~6 semanas y un mercado en caída (mediana del universo -0.9 % a 7 días): el alfa vs SPY
  de una señal «alcista» en bajada es difícil. Una sola racha, un solo régimen.
- Horizontes de 10 sesiones solo existen para eventos hasta ~13-oct.
- Retorno absoluto de EARLY no mirado; costes no incluidos; 4 símbolos sin precio (YAL, WHC, WCP, R9U2).
- Descriptivo, no preregistrado.
