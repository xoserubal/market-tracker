# Preregistro — Screener como sistema de picks en sombra

Estado: **FIRMADO 2026-10-09** (decisiones del usuario en la sección 2). Implementado en `scripts/screener_shadow_portfolio.py`
(Step 9g1b del pipeline).

## 0. Declaración de sesgo (importante)
Esta regla se redacta **después** de haber visto el informe `docs/data/screener_signal_report.json` (7 semanas, mercado
a la baja, ningún filtro separado del ruido). Para no elegir a posteriori la combinación que mejor salió, la
**selección de filtros y la definición de éxito se fijan aquí, no a partir de esos números**. Los datos acumulados
hasta la firma **no cuentan** para la evaluación: solo cuentan eventos con fecha de entrada posterior a la firma.

## 1. Qué se mide
Los 5 filtros del Screener, **cada uno por separado** (no combinaciones — evita buscar entre combinaciones):
`flow_inflexion`, `flow_continuacion`, `flow_reversion`, `line_near_zero_up`, `hist_cross_confirmed`.
Sin añadir filtros nuevos durante la evaluación.

## 2. Ejecución (cartera sombra mecánica, sin IA) — FIJADA 2026-10-09
- **Una sola cartera `SCREENER_SHADOW`** (decisión del usuario): cada posición lleva el filtro de origen (`filter`) y el
  dashboard la muestra con una pestaña por filtro. Una posición por (filtro, ticker, evento); un mismo ticker puede estar
  abierto por dos filtros a la vez.
- **Eventos:** solo capturas con fecha >= **2026-10-10** (`START_CAPTURE_DATE`). Un evento = primera aparición de un
  ticker en un filtro tras >=10 días naturales sin ser candidato de ese filtro.
- **Entrada:** cierre de la sesión **siguiente** a la barra de la señal (la apertura no está en el snapshot). Todo se
  indexa por fecha de barra (`asOf`), no por fecha de captura.
- **Tamaño:** 5% fijo y provisional ("ya veremos los pesos si esto llega a ser algo más"); sin límite de posiciones.
- **Salida (en múltiplos del ATR% de entrada, congelado; evaluada sobre cierres, una vez por barra):**
  - hard stop: cierre <= entrada − **1,5 × ATR**
  - trailing: se activa cuando el máximo cierre >= entrada × (1 + máx(**5%**, **1,5 × ATR%**)); después sale con
    cierre <= máximo − **2 × ATR**
  - time stop: primer cierre con >= **14 días naturales** desde la barra de entrada.
  Justificación de usar ATR y no % fijos: la mediana de ATR% del universo es 4%; un stop fijo del 2% habría sido tocado
  por el 70% de los eventos del Screener antes de 14 días (medido sobre 190 eventos, solo cierres).
- **Sin Telegram:** la cartera está en `SILENT_PORTFOLIOS` de `notify_telegram.py` (muchos eventos/día; solo recogida de datos).

## 3. Referencia y baselines
- Exceso = retorno de la posición − **mediana del universo ese día** al mismo horizonte (ya implementado).
- Baseline aleatorio: mismo número de eventos por semana, tickers al azar del universo, mismas fechas de entrada/salida.

## 4. Criterios (fijados antes de mirar eventos nuevos)
- **No concluyente** por debajo de **40 eventos independientes madurados a 14 días por filtro** (el informe actual usa 30;
  se sube a 40 por ser el mínimo que este proyecto ya se exige — ver `PREREGISTRO_PCS_FLOOR_FACTORIAL_V1.md`).
- **Candidato a piloto** (no a capital real) solo si, con ≥40 eventos y ≥2 regímenes de mercado distintos (p. ej. una fase
  alcista y otra bajista, medido por el signo del universo a 30 días): exceso medio a 14d **> 0**, IC95% del exceso medio
  que **no incluya 0**, y la mediana del exceso también > 0.
- **Descarte** de un filtro si, con ≥40 eventos, su exceso medio a 14d es **< 0** o su IC95% incluye claramente 0 con
  media ≤ 0.
- **Corrección por comparaciones múltiples:** con 5 filtros × 3 horizontes, el único contraste que decide es **14 días**
  (fijado aquí); 7 y 30 días son descriptivos. Umbral de significación con Bonferroni ×5 (α = 0,01).
- Nada se promueve a capital real por esta vía; solo a piloto sombra ampliado.

## 5. Registro obligatorio al implementarla (lección de CAVA_MACRO / MIRROR_ESPEJO)
Dashboard (`PTF_LABELS` en `docs/index.html`), Telegram (`_PORTFOLIO_LABELS` en `paper_trading.py` y
`notify_telegram.py`), `"event":"close"` en cada cierre, y paso del pipeline con `continue-on-error: true`.

## 6. Qué mide qué
- **Contraste estadístico (el que decide, sección 4):** retorno a 14 días naturales **sin stops** desde la entrada ejecutable,
  por filtro, vs la mediana del universo — `horizons_executable` de `scripts/screener_signal_report.js`. Los stops de la
  cartera NO entran en ese contraste: mezclan la calidad de la señal con la regla de salida.
- **La cartera** muestra qué haría esa regla de salida concreta. Los precios por barra del snapshot permiten recalcular
  después cualquier otra regla de salida sobre las mismas entradas, sin relanzar nada.
