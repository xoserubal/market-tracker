# Incidencia: el riesgo de concentración temática que recibe la IA no corresponde a la cartera que evalúa

**Estado:** abierta. Auditoría prioritaria **posterior** a la línea B. No se ha modificado ninguna lógica.
**Fecha de apertura:** 2026-10-25.
**Prioridad:** alta (afecta a lo que la IA ve en cada decisión de selección).

## Hipótesis a comprobar

`compute_theme_concentration()` (`scripts/paper_trading.py`) suma las posiciones abiertas de **todas** las carteras, incluidas las sombra y las experimentales, y devuelve un único `theme_risk` / `subtheme_risk` por ticker. Ese valor llega a la IA como `theme_concentration_risk` y `theme_exposure`, y el prompt lo presenta como «cuán concentrada está ya la cartera abierta». Si la IA decide por cartera (HIGH_CONVICTION, CFL, ER, MTB), el dato podría no describir la cartera que está evaluando.

## Evidencia ya medida (estado congelado del 2026-10-24)

- **181 posiciones abiertas en 11 carteras, 74 tickers distintos.** SCREENER_SHADOW tiene 108; MACD_COMBO_SD, 19; MACD_COMBO_CD, 15; MIMO_SHADOW, 13; CAVA_MACRO, 10. Las cuatro carteras clásicas no tienen posiciones abiertas ese día.
- `oil_gas`: **48 posiciones = 16 tickers únicos, peso sumado 268 %.** `healthcare_largecap`: 48 posiciones = 14 tickers únicos, 252 %. Un mismo ticker se cuenta una vez por cartera.
- Umbrales actuales del riesgo: tema «alto» con ≥ 3 posiciones o ≥ 30 % de peso. Con estos volúmenes, casi todo candidato sale «alto» o «medio». La señal pierde capacidad de discriminar.

## Preguntas que debe responder la auditoría

1. ¿Qué carteras deben contar para la concentración que ve la IA al evaluar cada cartera? (solo la propia, solo las que operan con capital real o simulado principal, todas sin duplicar tickers…).
2. ¿Se cuenta un ticker una vez por cartera o una vez en total? ¿Cómo se suma el peso cuando varias carteras tienen la misma posición?
3. ¿Qué carteras no deberían influir nunca (sombra, experimentales, mecánicas sin IA)?
4. ¿Cambia la distribución de `theme_risk` que recibió la IA en los runs históricos? Medirlo con los payloads guardados en `docs/data/ai_model_payloads/`.
5. ¿Hay evidencia en `model_tests` de que la IA haya usado ese campo en su razonamiento o en su rechazo de candidatos?
6. ¿La regla `theme_concentration_risk` es observacional (fase de observación desde 2026-05-16) o ya condiciona decisiones?

## Alcance

Solo diagnóstico y simulación con datos congelados. No cambiar umbrales ni la forma de calcular el riesgo hasta tener las respuestas. **No mezclar con la línea B ni con la línea A.**
