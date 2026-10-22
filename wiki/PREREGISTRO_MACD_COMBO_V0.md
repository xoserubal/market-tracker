# Preregistro — Carteras MACD_COMBO (Cruce confirmado + Cerca de 0)

Estado: **FIRMADO 2026-10-22** (decisiones del usuario). Implementado en `scripts/macd_combo_portfolio.py`
(Step 9g1d del pipeline, `continue-on-error`, sin Telegram).

## 0. Declaración de sesgo
La idea nace de mirar el historial del informe del Screener, donde la combinación de los dos filtros (26 eventos,
exceso medio ejecutable +1,9 a 7d y +3,1 a 14d) salía mejor que el cruce confirmado solo. Con n < 30 eso es una pista,
no evidencia. Los eventos con fecha de captura **anterior al 2026-10-23** se reconstruyen con los datos disponibles
(`phase = backfill_exploratory`) y **no cuentan** para evaluar; la prueba preregistrada son los eventos con captura
>= **2026-10-23** (`phase = preregistered`).

## 1. Reglas (fijadas antes de ver resultados de la fase preregistrada)
- **Señal de entrada:** el valor es candidato a la vez de `hist_cross_confirmed` y `line_near_zero_up` (log
  `screener_signal_log.jsonl`, mismo motor que el Screener).
- **Entrada:** cierre de la sesión siguiente a la barra de la señal (indexado por `asOf`, como `SCREENER_SHADOW`).
- **Salida (única):** primera barra posterior a la de entrada con `macdHist <= 0`; se ejecuta al cierre de la barra
  siguiente. **Sin stops y sin límite de días**: mientras el histograma siga positivo, la posición continúa.
- **Tamaño:** 5 % fijo, sin límite de posiciones. Un ticker no puede tener dos posiciones abiertas en la misma cartera.
- **Dos carteras** (misma entrada y salida; solo cambia la re-entrada):
  - `MACD_COMBO_CD` (con cooldown): evento = primera aparición como candidato combinado tras >= 10 días naturales sin serlo.
  - `MACD_COMBO_SD` (sin cooldown): cada día candidato es señal válida; se re-entra en cuanto exista una barra de
    entrada posterior a la de salida.

## 2. Datos que se conservan para estudiar salidas alternativas
- `docs/data/macd_combo_tracking.jsonl`: por posición y barra, desde la barra de la señal hasta la salida, todos los
  campos escalares del snapshot (volumen, RSI, Koncorde D/3D/W, OBV, SMA, MACD, ATR...) + PCS del día + rol de la
  fila (`signal`, `entry`, `hold`, `exit_signal`, `exit`). Se reescribe entero en cada ejecución.
- `docs/data/pcs_daily_log.jsonl`: PCS y componentes de todos los candidatos de `ai_candidates.json`, una vez por día
  (alimentado por el pipeline; reconstruido desde git para 2026-08-20 en adelante).
- Cualquier salida alternativa se evalúa **a posteriori sobre estas entradas**, nunca cambia la regla de la cartera.

## 3. Criterios
- **No concluyente** por debajo de **40 eventos independientes cerrados** por cartera en la fase preregistrada.
- La comparación decisiva es el retorno de la cartera frente al de comprar al azar el mismo número de valores del
  universo en las mismas fechas, con la misma duración. Una cartera por sí sola no prueba nada: una salida sin límite
  mezcla la calidad de la señal con la duración de la posición.
- Las salidas alternativas que salgan del estudio de tracking son **hipótesis** y requieren su propio preregistro.
- Nada se promueve a capital real por esta vía.

## 4. Limitaciones conocidas
- El snapshot solo cubre ~130 valores desde 2026-08-20; el histograma MACD guardado depende de lo capturado cada día.
- El PCS reconstruido desde git corresponde al último commit de cada día; los días sin commit válido quedan vacíos.
- Mercado de la ventana disponible: una sola fase; sin regímenes distintos no se puede generalizar.
