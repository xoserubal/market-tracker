# Diagnóstico de viabilidad — comportamiento posterior a niveles negativos del Flow Score (v1)

Fecha: 2026-11-18. Solo mide qué datos existen y cuántas observaciones habría. **No se ha calculado ningún
rendimiento posterior** ni se ha mirado ninguna relación entre el Flow y lo que pasa después. Producción sin tocar.

Pregunta del estudio: ¿qué ocurre tras cada nivel negativo del Flow Score? Las respuestas posibles son tres:
reversión (oportunidad), continuación bajista (peligro) o nada que no explique ya la caída previa (descripción).

## 1. Resumen

| Necesidad | ¿Se puede? | Cómo |
|---|---|---|
| Flow Score histórico reproducible | **Sí** | Réplica ya validada en `research/flow_cont_rev_v1/features.py` |
| Grandes empresas sin sesgo de supervivencia | **Sí, 2016-2026** | Composición del S&P 500 ya reconstruida en `sector_breadth_v1` |
| Medianas empresas | **Sí, 2016-2026** | Historial de cambios del S&P 400 en Wikipedia (desde 2012) |
| Pequeñas empresas | **Sí, pero solo 2020-2026** | Cambios del S&P 600 en Wikipedia desde dic-2019 |
| Precios de empresas desaparecidas | **Sí, con Alpaca** | 40 de 40 en la muestra; Yahoo solo 23 de 40 |
| Capitalización histórica (en cada fecha) | **Sí, con matices** | Acciones en circulación de la SEC, por fecha de presentación |
| Liquidez negociada | **Sí** | Precio × volumen, calculado con datos hasta la fecha |
| Microcaps no estadounidenses (TSX-V, ASX…) | **No** | Solo como observación con el registro propio desde ago-2026 |

**Conclusión:** el estudio es viable sin comprar datos, para empresas cotizadas en EE. UU. de los tres tamaños
del S&P (grande, mediana y pequeña). Las pequeñas solo tienen 6,5 años. Las microcaps fuera de índice y las
bolsas extranjeras quedan fuera de cualquier validación.

## 2. Flow Score histórico

- `research/flow_cont_rev_v1/features.py` replica `computeFlowScore` (`shared/flow-score.js`) barra a barra:
  - retornos de 1 semana y 1 mes, RSI, histograma MACD, ATR %, Koncorde diario y semanal, distancia al máximo
    de 365 días;
  - usa precios ajustados para Koncorde y sin ajustar por dividendos para el resto, igual que producción.
- **Contraste con el registro real:**
  - en los días en que la captura en vivo está limpia, la diferencia mediana es 0 y el percentil 90, 3 puntos;
  - con todas las capturas, la mediana es 2 y el p90 10,6. Esa diferencia viene de la propia captura en vivo
    (velas de un día antes, «sesión anterior» mal fijada antes del 10-nov), no de la réplica. Está documentado
    en el estudio Flow Continuación/Reversión.
- **Qué es el Flow, en la práctica:** el 98,5 % de su variación se explica por los retornos de 1 semana y 1 mes
  (auditoría de rotaciones). El resto (RSI, MACD, ATR, Koncorde, distancia al máximo) suma como mucho unos
  ±6 puntos. Un Flow de −30 equivale aproximadamente a caídas del 12-15 % ponderadas entre 1 semana y 1 mes.
  Por eso la etapa 2 es imprescindible.

## 3. Cuántas observaciones habría (S&P 500 + Nasdaq 100 actuales, 2016-2026)

Datos ya reconstruidos (`flow_cont_rev_v1/_work/U1_bars.pkl`, 517 valores, sesgo de supervivencia). Sirven solo
para dimensionar; el estudio usará el universo reconstruido en cada fecha.

- 1,36 millones de días-valor; el 34,5 % con Flow negativo.
- Percentiles del Flow: p1 −32,6 · p2,5 −23,5 · p5 −17,4 · p10 −11,5 · p25 −3,3 · mediana +4,6.

| Franja de Flow | Días-valor | Episodios aprox. (primera entrada tras ≥10 sesiones fuera) |
|---|---|---|
| [−5, 0) | 185 333 | — |
| [−10, −5) | 121 097 | 25 609 por debajo de −5 |
| [−15, −10) | 71 644 | 20 286 por debajo de −10 |
| [−20, −15) | 39 617 | 13 942 por debajo de −15 |
| [−30, −20) | 32 550 | 9 041 por debajo de −20 |
| < −30 | 17 169 | 3 599 por debajo de −30 |

- **Concentración en el tiempo:** el % de días-valor con Flow < −10 va del 4,5 % (2017) al 21,9 % (2022).
  Las zonas extremas se concentran en pocos episodios de mercado (2018, 2020, 2022, 2025). El número efectivo
  de observaciones independientes es mucho menor que el nominal. La inferencia tiene que agrupar por fecha.
- No se ha medido todavía la distribución en medianas y pequeñas. Es de esperar que allí los extremos sean más
  frecuentes (más volatilidad): las franjas absolutas pueden significar cosas distintas según el tamaño. Por eso
  se miden también percentiles.

## 4. Universos sin sesgo de supervivencia

### 4.1 Composición en cada fecha

| Índice | Fuente | Desde | Estado |
|---|---|---|---|
| S&P 500 | Instantáneas anuales de Wikipedia + cambios | 2016 | Ya reconstruido; coincidencia anual 96,5-99,4 % (`sector_breadth_v1`) |
| S&P 400 | Tabla de cambios (627 filas desde 2012) + instantáneas de la página (desde 2010) | 2016 | Por construir; ~50 cambios/año |
| S&P 600 | Tabla de cambios (491 filas desde dic-2019) + instantáneas (página creada en ago-2018) | 2020 | Por construir; 51-94 cambios/año |

- Las tablas de cambios de Wikipedia pueden estar incompletas. Hay que contrastarlas con las instantáneas, como
  se hizo con el S&P 500, y publicar la coincidencia antes de mirar ningún resultado.
- Los motivos de salida en el S&P 600 desde 2016: 182 adquisiciones, 7 quiebras o exclusiones de bolsa,
  17 por capitalización (el resto, movimientos entre índices sin motivo explícito).
- **Ventaja del enfoque:** pertenecer a un índice en una fecha es en sí una medida de tamaño en esa fecha, sin
  usar la capitalización actual. Grande = S&P 500, mediana = S&P 400, pequeña = S&P 600.

### 4.2 Precios de empresas que dejaron de cotizar

Muestra aleatoria de 40 salidas del S&P 600 (2020-2026) y de 60 de cada índice para Yahoo:

| Fuente | S&P 600 | S&P 400 |
|---|---|---|
| Yahoo (yfinance) | 27/60 y 23/40 (45-57 %) | 34/60 |
| **Alpaca (SIP diario)** | **40/40** | (no probado; se espera igual) |

- En Alpaca, las series de empresas absorbidas o quebradas terminan justo en su último día de cotización (p. ej.
  FBC 30-nov-2022, AKRX 29-may-2020, HMSY 31-mar-2021).
- Lo que falta en Yahoo son, sobre todo, adquisiciones y quiebras: justo lo que más sesga un estudio de caídas
  (las quiebras empeoran el resultado; las adquisiciones con prima lo mejoran).
- **Riesgos ya conocidos de Alpaca** (`research/microstructure_v1`):
  - un símbolo reutilizado mezcla empresas (ADT, «B»): hay que pedir cada serie con `asof` = último día en que
    se observó la empresa de interés y cortar por épocas (`micro/identity.py` ya lo hace);
  - antes de 2020 no registra escisiones ni fusiones y a veces aplica splits a otra empresa: los splits se validan
    contra el precio antes de aceptarlos (enmienda 7 de microestructura).
- **Licencia:** los datos de Alpaca no se pueden redistribuir. Se guardan fuera del repo (`MICRO_DATA_DIR`), igual
  que en microestructura. Si se pueden publicar agregados derivados sigue sin verificar: el informe solo
  publicaría estadísticos agregados por franja, nunca series por valor.

### 4.3 Coherencia de la fuente de precios

El Flow se ha validado con Yahoo. Mezclar Yahoo y Alpaca en el mismo estudio meterá diferencias de ajuste.
Propuesta: usar **una sola fuente (Alpaca) para todo**. Antes de calcular ningún resultado, comparar el Flow
reconstruido con Alpaca y con Yahoo en los valores que estén en ambas. Si la diferencia es grande, la puerta de
calidad no se supera.

## 5. Capitalización y liquidez en cada fecha

- **Acciones en circulación — SEC (`dei:EntityCommonStockSharesOutstanding`):**
  - dato trimestral de la portada de cada 10-Q/10-K, con fecha de cierre y de **presentación**;
  - se usa el último dato presentado con fecha ≤ t (sin mirar al futuro);
  - comprobado con AAPL (2009-2026) y con HMS Holdings (absorbida en 2021: datos 2010-2021);
  - el número no está ajustado por splits: capitalización = precio sin ajustar × acciones de esa fecha.
  - yfinance `get_shares_full` da exactamente los mismos números (copia la SEC), pero solo para tickers vigentes.
- **Enlace empresa → CIK de la SEC:**
  - para tickers vigentes, `company_tickers.json` (10 400 entradas);
  - para empresas desaparecidas, búsqueda por nombre en EDGAR (funcionó con HMS Holdings). Es un enlace por
    nombre: requiere comprobación y su cobertura hay que medirla y publicarla.
- **Problemas conocidos:** empresas con varias clases de acción (la portada puede dar solo una clase), emisores
  extranjeros que presentan 20-F/40-F (sin este dato), y retrasos de hasta un trimestre.
- **Liquidez negociada:** mediana de precio × volumen de las 20 sesiones previas (incluida t). Es inmediata.
- **Rotación (turnover):** liquidez negociada / capitalización, solo donde haya capitalización.

**Propuesta:** el tamaño principal es el índice al que pertenece el valor en esa fecha (no depende de la SEC).
Los tramos de capitalización dentro de cada índice y la rotación se informan solo si la cobertura de la SEC en ese
tramo llega al 80 %; si no, quedan como descriptivos.

## 6. Universo propio (Portfolio Tracker)

- Registro diario con el Flow tal como se capturó: 134 valores, del 20-ago al 17-nov-2026 (~3 meses).
- Muchas microcaps hundidas: un 38 % de las filas con Flow < −10 y un 9 % < −30. Es otro universo, no comparable.
- Solo un régimen de mercado y capturas en vivo con desfases conocidos.
- **Uso:** solo descriptivo, en un apartado propio. Nunca como validación ni para fijar umbrales.

## 7. Contexto de mercado y sector

- **Régimen:** SPY frente a su SMA200 y SMA50 (la misma definición que el registro de señales de RFL).
- **Caída del valor frente a caída general:** retorno de 21 sesiones del valor frente al de SPY y frente a la
  mediana de su sector dentro del mismo índice.
- **Sector:** GICS de las tablas de Wikipedia para los miembros actuales. Para las empresas desaparecidas no
  viene: se usará el código SIC de la SEC (`submissions`), con una tabla de correspondencia fijada de antemano.
- La comparación con el sector se hace contra los demás valores del mismo sector e índice en la misma fecha.
  Los ETF sectoriales SPDR son de grandes empresas: no sirven de referencia para las pequeñas.

## 8. Costes y tiempos

- Descarga de Alpaca: ~2 900 símbolos (S&P 500 + 400 + 600 de todo el periodo) de barras diarias 2015-2026.
  Con el límite de 200 peticiones por minuto, menos de una hora.
- SEC: ~2 900 consultas con pausas (límite de 10 por segundo); 1-2 horas con reintentos.
- Reconstrucción de Koncorde y Flow: unas horas de cálculo (ya se hizo para 517 valores).
- Sin coste monetario.

## 9. Lo que queda fuera (y por qué)

- **Microcaps y bolsas no estadounidenses:** sin composición histórica ni precios de empresas desaparecidas.
- **Pequeñas empresas antes de 2020:** no hay historial de cambios del S&P 600 anterior a dic-2019.
- **Empresas fuera de cualquier índice:** sin forma gratuita de reconstruir el universo en cada fecha.
- **Sesgo restante:** los índices S&P exigen beneficios para entrar. Las pequeñas empresas del S&P 600 son de
  más calidad que las small caps en general (Russell 2000). La conclusión vale para ese universo, no para todas.
