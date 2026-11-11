# Preregistro — ¿rinden peor las acciones extendidas sobre su SMA20? (v1, borrador)

**FIRMADO el 2026-11-11 por el usuario («dale»: descarga autorizada y firma). Congelado desde ese momento.** No se ha calculado ninguna rentabilidad. Alcance: investigación en
`research/extension_sma20_atr_v1/`. No se toca el Market Tracker, el pipeline, el PCS ni ninguna cartera.

## 0. Pregunta
¿Comprar una acción muy extendida sobre su SMA20 (en unidades de ATR) da peor resultado a 1-4 semanas que comprar la
media del universo? Y si es así, ¿aporta algo más que la reversión ya conocida de la fuerza relativa a 3 meses?

Si la respuesta es sí en las dos cosas, «no comprar lo extendido» sería un filtro útil para cualquier cartera.

Lo que ya se sabe:
- **Fase 1 del Ranking Score:** `dist_sma20_atr` correlaciona −0,27 con el retorno a un mes (p = 0,008, 98 picks, un
  solo régimen de tres meses). No supera la corrección por los 14 componentes que se probaron.
- **`research/macd_combo_filters_v1`** (S&P 500 + Nasdaq 100, 2016-2026): la fuerza relativa positiva a 63 sesiones
  rinde 0,35-0,60 puntos por debajo del universo a 1-4 semanas, en desarrollo y en prueba. En ese estudio el filtro
  «no extendido < 1,5 ATR» no se distinguió de cero, pero medía otra cosa: el día en que un valor deja de estar
  extendido.

## 1. Datos
- **Universo:** los 518 componentes actuales del S&P 500 y el Nasdaq 100
  (`research/macd_combo_sp500_ndx_v1/constituents.json`), más SPY.
  - Sesgo de supervivencia declarado: solo están los que siguen hoy en los índices. Afecta al nivel de los retornos,
    no necesariamente a la comparación entre valores.
- **Precios:** yfinance diario de 2015-01-01 a 2026-11-10, con OHLC y Adj Close, descargados con el mismo código de
  `research/macd_combo_filters_v1/fetch_data.py`. **Hay que volver a descargarlos:** la caché no está en este entorno
  (unos 520 símbolos).

## 2. Variable (fijada antes de ver rentabilidades)
**X = (cierre − SMA20) / ATR14**, con la fórmula exacta de `pcs_calculator.py`:
- SMA20 del cierre;
- ATR14 = media simple de 14 sesiones del rango verdadero, sobre OHLC ajustados (High, Low y Open escalados por
  Adj Close / Close);
- se calcula con datos hasta el cierre de t;
- hacen falta al menos 20 sesiones de historia.

## 3. Medición
- **Fecha de decisión:** último día bursátil de cada semana.
- **Entrada y salida:** compra a la apertura ajustada de t+1 y venta al cierre ajustado de t+H.
  - **H = 20 sesiones** (primario); 5 y 10 son secundarios.
- **Objetivo:** retorno del valor menos la media equiponderada de los valores disponibles en esa misma ventana.
  - Bruto, sin coste: el filtro consiste en no comprar, así que no genera operaciones.
- **Deciles:** en cada fecha, los valores con X disponible se reparten en deciles de X. D10 es el más extendido.
- **Estadístico por fecha:** exceso medio de D10. Resumen: media de las fechas, con t de Newey-West de retardo 4
  (ventanas de 20 sesiones solapadas cuatro semanas).

## 4. Hipótesis
- **H1 (primaria):** el exceso medio de D10 a 20 sesiones es negativo.
- **H2 (incremental, primaria):** X aporta información sobre la fuerza relativa a 63 sesiones.
  - En desarrollo se estima, agrupando todas las fechas, la regresión del rango de X (centrado en [−0,5, 0,5]) sobre
    el rango de RS63, y el coeficiente se congela.
  - Residuo = rango(X) − b × rango(RS63).
  - Estadístico: Spearman por fecha entre el residuo y el objetivo; media de fechas con t de Newey-West de retardo 4.
- **Descriptivo:**
  - exceso de cada decil (D1 a D10);
  - exceso de los umbrales que usa `extension_risk`: X > 2 (+2 puntos) y X > 3 (+3 puntos);
  - Spearman de X sin controlar.

## 5. Muestras y potencia
- **Desarrollo:** 2016-01-01 → 2020-12-31. Solo se usa para estimar b y comprobar el signo.
- **Prueba:** 2021-01-01 → última fecha con 20 sesiones de futuro. Se ejecuta una sola vez.
- **Ojo:** los datos de prueba ya se usaron en `macd_combo_filters_v1` para la fuerza relativa, aunque no para X.
- **Potencia:** unas 300 fechas de prueba con unos 50 valores en D10 cada una.
  - El error de la media de D10 ronda 0,15-0,25 puntos a 20 sesiones (hay que corregirlo por la correlación entre
    valores el mismo día).
  - Se detectarían con fiabilidad efectos de 0,4-0,5 puntos o más.

## 6. Clasificación
**Efecto mínimo de interés (EMI):** D10 rinde −0,5 puntos o menos frente al universo a 20 sesiones. Es una pérdida
evitable que justifica tener un filtro.

**VALIDADO**, si se cumple todo en la prueba a 20 sesiones:
1. media de D10 ≤ −0,5 y el límite superior del IC 95 % < 0;
2. H2: IC del residuo < 0 con t ≤ −2;
3. el mismo signo en desarrollo, tanto en D10 como en el residuo;
4. D10 por debajo de la media de D1-D9;
5. D10 negativo en al menos 3 de 4 subperiodos (2021-2022, 2023, 2024, 2025-2026);
6. D10 negativo sin el 1 % de peores eventos (los más negativos);
7. datos no solapados (una semana de cada cuatro, las 4 rejillas): media de D10 < 0 en las 4.

**NO SOPORTADO:** el límite inferior del IC 95 % de D10 es > −0,5 (no hay pérdida evitable útil).

**INCONCLUYENTE:** el resto.

Caso concreto: si se cumplen 1, 3-7 pero no 2, la conclusión es «el efecto existe, pero es la misma reversión que ya
mide la fuerza relativa a 3 meses».

**Sensibilidades (se informan todas, ninguna decide):**
- H = 5 y 10;
- solo SPY por encima de su SMA200, y solo por debajo;
- exceso neutral por sector (frente a la media de su sector GICS, con `sectors.json`).

No se probarán otras definiciones de la extensión ni otros umbrales sobre estos datos.

**Alcance de un VALIDADO:** se propondría como filtro en sombra (por ejemplo, marcar los SELECT con X en D10 y medir
en vivo), con un preregistro propio. No se cambia el PCS ni ninguna regla de entrada directamente.

## 7. Pendiente antes de firmar
1. Autorizar la descarga de precios (unos 520 símbolos de Yahoo, de 2015 a 2026).
2. Firmar. La huella SHA-256 se guarda en `research/extension_sma20_atr_v1/PREREGISTRO.sha256` antes de calcular nada.

## 8. Firma
- Firmado el 2026-11-11. La huella SHA-256 del documento, calculada sin esta sección 8, está en `research/extension_sma20_atr_v1/PREREGISTRO.sha256`. Se guardó antes de calcular nada.
