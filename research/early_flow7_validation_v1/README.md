# Early Flow ≥ 7 frente a momentum, fuerza relativa y volumen — v1 (2026-11-11)

Preregistro: `wiki/PREREGISTRO_EARLY_FLOW_7_V1.md` (SHA-256 guardado en `PREREGISTRO.sha256` antes de calcular; comprobado
sin cambios al terminar). Origen: auditoría `wiki/AUDITORIA_DETECCION_ROTACIONES_V1.md`, punto H1.
Sin cambios en producción ni en ningún componente del Market Tracker. Sin descargas: precios y Early Flow ya
reconstruidos en `research/macd_combo_filters_v1` (mismo código de `shared/flow-score.js`).

## Veredicto preregistrado: **NO SOPORTADO** → Early Flow ≥ 7 se descarta como detector temprano

| Criterio (§6, prueba 2021-2026, 20 sesiones) | Resultado |
|---|---|
| 1. Exceso neto > 0 con t ≥ 2 | **No**: −0,41 pp (t −3,2), n 17 070 |
| 2. Supera a los 6 benchmarks (t ≥ 2,64) | **No**: pierde contra los 6 (−0,21 a −0,59 pp) |
| 3. Mismo signo en desarrollo | Sí (también negativo en 2016-2020: −0,39 pp, t −3,1) |
| 4. Acierto > 50 % y MAE no peor que M20 | No (acierto 46 %) |
| Otro horizonte con exceso positivo | Ninguno (5/10/20/40 negativos en ambos periodos) |

Conforme a lo acordado, no se prueban otros umbrales, ventanas ni filtros sobre estos datos.

## 1. Reproducibilidad (paso previo)

43 valores presentes en el caché y en las capturas del pipeline, 1 938 velas (2026-08-19 → 2026-11-09).
`repro.py`, `repro_results.json`.

| | Resultado |
|---|---|
| Valor de Early Flow idéntico capturado vs reconstruido | 61 % (±1: 90 %; mismo lado de 7: 97 %) |
| Estado ≥ 7 | ambos 102 · solo capturado 20 · solo reconstruido 32 |
| **Cruces del umbral 7** (31 en las capturas) | 12 el mismo día, 5 a ±2 sesiones, **14 solo en la captura**, 21 solo en la reconstrucción |
| Entradas distintas | RSI 27 %, w1 18 %, m1 18 %, distancia al máximo 17 %, ATR% 14 %, Koncorde 3D 12 %, D 5 %, W 2 % |
| Koncorde W distinto antes / después del arreglo de semanas incompletas (30-ago) | 11 % / 1 % |
| "Sesión anterior" del pipeline = sesión anterior real | 86 % |

Causas, por orden de peso:
1. **Capturas con el mercado abierto**: el 20 % de las velas capturadas tienen un precio que no es el cierre final
   (> 0,1 % de diferencia). Arrastra RSI, w1, m1, distancia al máximo, ATR y Koncorde de ese día.
2. **"Sesión anterior" del pipeline** = captura anterior, que en el 14 % no es la sesión anterior real (capturas
   repetidas o días perdidos). Afecta a los giros de Koncorde y a la compresión de ATR.
3. **Semanas Koncorde incompletas** antes del 30-ago (W recalculado a diario).
4. Diferencias de cálculo menores: el RSI en vivo se siembra con las últimas 100 sesiones (la reconstrucción usa todo
   el histórico); Koncorde en vivo sobre ~820 días, la reconstrucción sobre 2015+ ajustado.
De las 760 filas con valor distinto, 326 tienen idénticas las entradas del día: la diferencia viene solo de la sesión
anterior (giros de Koncorde y compresión de ATR). Recalcular las capturas con la sesión anterior real cambia por sí solo
el 16 % de los valores.

Consecuencia: **la señal capturada (versión original) y la reconstruida (versión corregida) son distintas en casi la
mitad de los cruces del 7.** El estudio histórico solo puede evaluar la corregida. La observación favorable de 2026
(+6,8 pp) se hizo sobre la original, en otro universo (130 tickers propios, muchos pequeños y de materias primas).

## 2. Resultados principales

Universo: 514 componentes actuales del S&P 500/NDX. Entrada a la apertura siguiente, coste 0,2 %. Exceso = retorno neto −
media equiponderada del universo (sin coste). Cada benchmark elige, el mismo día, el mismo número de valores que
Early Flow ≥ 7 (mismo enfriamiento de 10 sesiones). RND = selección al azar con las mismas reglas (su exceso ≈ −0,2 a
−0,3 es el coste).

### 20 sesiones (horizonte primario)
| Método | Desarrollo 2016-20: exceso (t) | Prueba 2021-26: exceso (t) | Acierto prueba | Pérdida > 10 % | MAE mediana | MFE mediana |
|---|---|---|---|---|---|---|
| **Early Flow ≥ 7** | −0,39 (−3,1) | **−0,41 (−3,2)** | 46 % | 8,1 % | −4,5 % | +5,2 % |
| M5 momentum 5 ses. | +0,03 | +0,10 | 48 % | 12,3 % | −5,4 % | +6,3 % |
| M20 momentum 20 ses. | −0,17 | +0,04 | 48 % | 11,1 % | −5,1 % | +5,9 % |
| RSM63 RS vs SPY | −0,05 | −0,03 | 47 % | 10,7 % | −5,1 % | +5,8 % |
| RSS63 RS vs sector | −0,06 | −0,02 | 47 % | 10,6 % | −5,2 % | +5,8 % |
| RSS20 RS vs sector 20 ses. | −0,13 | +0,04 | 48 % | 10,8 % | −5,1 % | +5,9 % |
| RSV RS + volumen relativo | −0,23 | −0,23 | 46 % | 9,4 % | −4,8 % | +5,4 % |
| RND azar | −0,21 | −0,27 | 47 % | 9,3 % | −4,7 % | +5,5 % |

Diferencia emparejada por fecha, Early Flow ≥ 7 − benchmark, prueba, 20 ses.: M5 −0,58 (t −1,9) · M20 −0,47 (−1,4) ·
RSM63 −0,43 (−1,5) · RSS63 −0,59 (−2,1) · RSS20 −0,45 (−1,6) · RSV −0,21 (−1,0) · RND −0,13 (−0,8).
A 40 sesiones pierde contra todos los benchmarks no aleatorios en los dos periodos (t entre −1,1 y −2,6).

### Otros horizontes (prueba)
| | 5 ses. | 10 ses. | 40 ses. |
|---|---|---|---|
| Early Flow ≥ 7 exceso (t) | −0,24 (−5,0) | −0,29 (−3,8) | −0,48 (−2,0) |
| Mejor benchmark | RSS20 −0,10 | RSS20 −0,05 | M5 +0,49 |

Antes de costes, Early Flow ≥ 7 rinde unos 0,2 pp **por debajo** del universo a 20 sesiones; los benchmarks de momentum
y fuerza relativa, unos 0,2 pp por encima. Nada de esto es grande: ningún método tiene una ventaja clara, pero Early
Flow ≥ 7 es el peor de todos los no aleatorios.

### Por año (20 ses., exceso neto)
Early Flow ≥ 7 negativo en 10 de 11 años (2017: +0,05). M20 positivo en 6 de 11.

### Por régimen (20 ses.)
| | SPY > SMA200 | SPY < SMA200 |
|---|---|---|
| Early Flow ≥ 7, desarrollo | −0,26 (n 12 259) | **−1,43** (n 1 500, acierto 41 %) |
| Early Flow ≥ 7, prueba | −0,30 (n 14 168) | **−0,97** (n 2 902, acierto 44 %) |
| M20, prueba | +0,06 | −0,09 |

Peor en mercado bajista: en ese régimen la señal compra rebotes que no siguen.

### Riesgo
Early Flow ≥ 7 tiene colas más cortas que el momentum (pérdidas > 10 %: 8 % frente a 11-12 %; MAE −4,5 % frente a
−5,1 %), pero también menos recorrido (MFE +5,2 % frente a +5,9-6,3 %), y queda por debajo del azar en exceso. Elige
situaciones de menor volatilidad, no mejores oportunidades. Es una observación, no una hipótesis preregistrada.

### Sector
Reparto parecido al azar, con algo más de financieras/utilities/inmobiliario y menos tecnología y energía que M20. No
explica la diferencia.

## 3. Anticipación (descriptivo, §5)

Inicio de tendencia sostenida (entrar en el quintil superior de RS 63 vs SPY tras 20 sesiones por debajo del percentil
60, y quedarse ≥ 16 de 20 sesiones): 396 inicios, **183 sostenidos** (103 en desarrollo, 80 en prueba). La definición es
estricta y deja pocos casos.

| Prueba 2021-26 | Cobertura (evento en las 40 ses. previas) | Anticipación mediana | Precisión | Subida previa 20 ses. | Sobre mínimo 60 ses. | Recorrido máx. 40 ses. desde la entrada | Retorno 40 ses. |
|---|---|---|---|---|---|---|---|
| **Early Flow ≥ 7** | 46 % | 31 ses. | 0,4 % | **0 %** | +9 % | +6,8 % | +1,5 % |
| M5 | 88 % | 26 | 0,8 % | +5 % | +17 % | +8,3 % | +1,8 % |
| M20 | 78 % | 21 | 0,7 % | +11 % | +21 % | +7,8 % | +1,7 % |
| RSS20 | 76 % | 24 | 0,7 % | +9 % | +20 % | +7,9 % | +1,9 % |
| RND | 65 % | 21 | 0,4 % | +1 % | +11 % | +7,2 % | +1,6 % |
(RSM63, RSS63 y RSV tienen cobertura de 6-13 % por construcción: eligen valores que ya están arriba, y la definición de
inicio exige venir de abajo. No se interpretan.)

Lectura: Early Flow ≥ 7 **sí detecta antes** (el valor no había subido nada en las 20 sesiones previas, frente a +5/+11 %
del momentum), pero **no detecta mejor**: cubre menos inicios de tendencia que el azar (46 % frente a 65 %), su precisión
es la del azar (0,4 %) y el recorrido que queda desde la entrada es menor que con cualquier otro método. Desarrollo da lo
mismo (cobertura 47 % vs azar 71 %, precisión 0,6 % vs 0,7 %).

## 4. Clasificación de los resultados

| Tipo | Contenido |
|---|---|
| **Capacidad predictiva demostrada** | Ninguna. |
| **Resultado demostrado (negativo)** | Early Flow ≥ 7 rinde por debajo del universo y de todos los benchmarks a 5-40 sesiones, en desarrollo y en prueba, en 10 de 11 años y en los dos regímenes. No anticipa inicios de tendencia mejor que el azar. |
| **Indicios exploratorios** | Perfil de riesgo más bajo (colas y MAE menores), sin ventaja de retorno. No preregistrado como hipótesis. |
| **Inconcluyente / no evaluable** | El universo propio (130 tickers, pequeñas y materias primas) y la versión capturada de la señal: no hay histórico. La observación de 2026 queda sin confirmar y sin validez independiente. |

## 5. Limitaciones
- **Sesgo de supervivencia**: componentes actuales de los índices; faltan los que salieron. Favorece a las estrategias
  que compran valores débiles en recuperación, es decir, debería **ayudar** a Early Flow; aun así sale negativo.
- **Sector actual** aplicado a todo el periodo (GICS cambió en 2018).
- El periodo 2021-2026 ya se había mirado con Early Flow ≥ 4 (estudio previo): la prueba no es virgen para la familia.
- Reconstrucción ≠ señal en vivo (§1): se evalúa la versión corregida. Koncorde W no existe hasta tener 100 semanas
  (≈ 2017) en la reconstrucción; en 2016 Early Flow pierde ese componente.
- El exceso frente al sector usa el ETF de cierre a cierre (el valor, de apertura a cierre): diferencia menor.
- Las señales de un mismo día están correlacionadas; los t usan Newey-West sobre la serie de fechas con retardo igual
  al horizonte.

## Ficheros
`repro.py` → `repro_results.json` (paso 1) · `study.py` → `results.json` (todas las cifras), `_events_ef7.csv`
(eventos con su exceso a 20 sesiones). Ejecución: `py -3 -W ignore repro.py` y `py -3 -W ignore study.py` (~30 s, solo lee
`research/macd_combo_filters_v1/prices_cache.parquet` y `_work/earlyflow_out.csv`, que están fuera de git y se regeneran
con `fetch_data.py` + `build_features.py` + `early_flow.js` de ese directorio).
