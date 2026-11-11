# Preregistro — Early Flow ≥ 7 frente a momentum, fuerza relativa y volumen (v1)

Escrito el 2026-11-11, **antes de calcular ninguna de las cifras que define**. Autorizado por el usuario tras la
auditoría `wiki/AUDITORIA_DETECCION_ROTACIONES_V1.md` (punto H1). Código y resultados:
`research/early_flow7_validation_v1/`. No se modifica producción ni ningún componente del Market Tracker.

## 0. Qué se sabía antes de escribir esto (declaración)
- **El umbral 7 se elige por una observación favorable en datos en vivo de 2026** (portfolio, 130 tickers, ago-nov
  2026: 50 activaciones, exceso mediano +6,8 pp a 20 sesiones, n = 33). Esa muestra **no es validación**: se usa solo
  para formular la hipótesis y no entra en el contraste. El 7 es además el umbral "Fuerte" que ya tenía el código
  (`shared/flow-score.js → classifyEarlyFlow`), no un valor buscado.
- El mismo universo y periodo se usó en `research/macd_combo_filters_v1` con **Early Flow ≥ 4** (sin exceso en
  desarrollo ni en prueba). Ese estudio no miró el umbral 7, pero el periodo de prueba 2021-2026 ya no es virgen
  para la familia Early Flow. Se declara como limitación.
- Ningún resultado de Early Flow ≥ 7 en el S&P 500/NDX se ha calculado antes de este documento.

## 1. Datos
- Universo: 518 componentes **actuales** del S&P 500 y Nasdaq 100 (`research/macd_combo_sp500_ndx_v1/constituents.json`),
  sector GICS actual (`research/macd_combo_filters_v1/sectors.json`), precios diarios yfinance 2015-01-02 → 2026-11-09
  (`prices_cache.parquet`, ya descargado). Valores con < 250 sesiones de historia excluidos (como en el estudio previo).
- **Sesgo de supervivencia:** solo están las empresas que hoy siguen en los índices. Faltan las que salieron
  (quiebras, absorciones, caídas de capitalización). Esto sesga al alza cualquier estrategia que compre valores
  débiles en recuperación, y en general hace que los retornos absolutos no sean extrapolables. Medir exceso frente
  a la media del mismo universo atenúa, pero no elimina, el sesgo. El sector actual se aplica a todo el periodo
  (reclasificación GICS de 2018). No hay histórico de componentes en el repo: no se corrige, se documenta.
- Early Flow reconstruido con el código exacto de producción (`computeEarlyFlowScore`), entradas como en
  `research/macd_combo_filters_v1/build_features.py`: Koncorde D/3D/W sobre precios ajustados, 3D = bloque de 3
  sesiones que termina el día de la señal, W = última semana cerrada; RSI14, ATR% (0,1), distancia al máximo de 365
  días, w1/m1 redondeados como JS; "sesión anterior" = sesión bursátil real anterior.

## 2. Paso 1 — reproducibilidad (antes de cualquier cifra de alfa)
Solapamiento: valores presentes a la vez en el caché y en `docs/data/portfolio_daily_snapshot.jsonl` o
`market_equities_daily_snapshot.jsonl`, velas 2026-08-19 → 2026-11-09, indexadas por `asOf` (última captura por vela).
Se informa:
1. Coincidencia del valor de Early Flow capturado vs reconstruido (idéntico, ±1, mismo lado de 7).
2. Tabla de confusión del estado ≥ 7 y **cruces del umbral 7** (primera vela ≥ 7 tras ≥ 10 velas por debajo):
   cuántos coinciden el mismo día, a ±2 sesiones, y cuántos solo existen en una versión.
3. Origen de cada discrepancia, por entrada: estado Koncorde D, 3D, W; RSI; w1; m1; distancia al máximo; ATR%; y
   la "sesión anterior" (captura anterior ≠ sesión anterior real).
4. Efecto de las semanas Koncorde incompletas (capturas anteriores al 2026-08-30).
Versiones: **original** = valor capturado por el pipeline (solo existe desde 2026-08-20); **corregida** = reconstrucción
con sesión anterior real. El estudio histórico solo puede usar la corregida; se informa cuánto difiere de la original.
Este paso no condiciona la ejecución del resto, solo su interpretación.

## 3. Señales y comparación equilibrada
Todas con datos hasta el cierre del día t. **Entrada ejecutable = apertura de t+1. Coste 0,2 % ida y vuelta.**
- **EF7 (evento):** Early Flow ≥ 7 en t y < 7 en t−1, sin otro evento EF7 del mismo valor en las 10 sesiones previas.
- **Benchmarks** (puntuación continua en t):
  - M5: retorno 5 sesiones. M20: retorno 20 sesiones.
  - RSM63: retorno 63 sesiones − retorno de SPY 63 sesiones.
  - RSS63: retorno 63 sesiones − retorno del ETF de su sector 63 sesiones. RSS20: ídem a 20 sesiones.
  - RSV: media de los percentiles transversales de RSM63 y de RVOL (volumen medio 20 / volumen medio 60).
  - RND: selección aleatoria (semilla fija 7).
- **Emparejamiento:** cada día t con k_t eventos EF7, cada benchmark elige los k_t valores con mayor puntuación entre
  los que no eligió en las 10 sesiones previas (mismo enfriamiento). Mismas fechas, mismo número de señales, misma
  exposición. RND elige k_t al azar con la misma regla.
- Contexto sectorial: se informa el reparto por sector de cada método y el exceso frente al ETF de su sector.

## 4. Métricas
- Horizontes 5, 10, 20, 40 sesiones. **Horizonte primario: 20.** Retorno = cierre de t+h / apertura de t+1 − 1 − 0,2 %.
- Exceso = retorno − media equiponderada del universo para la misma entrada y horizonte (sin coste en la media).
  Secundario: exceso frente al ETF del sector.
- Diferencia emparejada por fecha: d_t = media de exceso EF7 − media de exceso del benchmark ese día. Error estándar
  Newey-West sobre la serie diaria de d_t con retardo = horizonte. Igual para el exceso de EF7 solo.
- Riesgo: MAE y MFE desde la entrada (mínimo/máximo intradía hasta t+h), percentiles 5/25/50/75/95 del retorno,
  % de pérdidas > 10 %, acierto (exceso > 0). Por año y por régimen (SPY sobre/bajo su SMA200 en t).

## 5. Anticipación
- **Inicio de tendencia (fijado aquí):** día T en que el valor entra en el quintil superior transversal de RSM63
  (percentil ≥ 0,80) habiendo estado por debajo del percentil 0,60 en las 20 sesiones previas.
  **Sostenida** si está en el quintil superior al menos 16 de las sesiones T..T+19. **Falso arranque** si no.
- Por método: cobertura = % de inicios sostenidos con al menos un evento del método en [T−40, T−1]; anticipación =
  T − primer evento en esa ventana; precisión = % de eventos seguidos de un inicio sostenido del mismo valor en
  [t+1, t+40]; "ya había subido" = retorno de t−20 a t y desde el mínimo de 60 sesiones; "recorrido restante" =
  máximo de cierre en [t+1, t+40] / apertura t+1 − 1 y retorno a 40 sesiones.
- RSM63 y RSV están ligados por construcción a la definición de tendencia: su anticipación se informa, pero no se
  interpreta como ventaja.

## 6. Muestras y criterio de éxito
- **Desarrollo:** señales 2016-01-01 → 2020-12-31. **Prueba:** señales 2021-01-01 → 2026-11-09 menos el horizonte.
  Ambas se calculan en una sola ejecución; no se cambia nada después.
- **EF7 aporta valor incremental (capacidad demostrada)** solo si en **prueba**, a 20 sesiones:
  1. exceso neto medio de EF7 > 0 con t ≥ 2;
  2. supera a **cada uno** de los 6 benchmarks no aleatorios con diferencia emparejada > 0 y t ≥ 2,64
     (Bonferroni 0,05 / 6, bilateral);
  3. el signo de 1 y de 2 es el mismo en desarrollo;
  4. acierto > 50 % y mediana de MAE no peor que la de M20 en más de 1 pp.
- **Indicio exploratorio:** se cumple 1 en prueba (y su signo en desarrollo) pero falla 2, 3 o 4; o solo se cumple a
  otro horizonte.
- **No soportado:** exceso de EF7 en prueba ≤ 0 o t < 2 a 20 sesiones.
- **Inconcluso:** menos de 100 eventos EF7 en prueba.
- Si no hay capacidad demostrada, EF7 se descarta como detector temprano. **No se probarán otros umbrales, ventanas ni
  filtros sobre estos datos.**
- La anticipación (§5) es descriptiva: no cambia la clasificación anterior, se informa al lado.

## 7. Lo que no se hace
Ningún cambio en `shared/flow-score.js`, en el pipeline ni en otras páginas. No se descarga nada nuevo. No se prueba
breadth sectorial (siguiente prioridad, preregistro aparte).
