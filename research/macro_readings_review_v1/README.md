# Revisión de las lecturas macro de Market Tracker (2026-11-18)

**Solo revisión: no se ha cambiado nada.** Las lecturas de la pestaña principal (`shared/market-macro.js → STATUS`)
también van a la captura diaria (`market_macro_daily_snapshot.jsonl`) y de ahí a Sol, así que cualquier cambio es un
cambio en producción y espera tu aprobación.

Método (`fetch.py` + `evaluate.js`, datos en `_work/`, sin publicar):
- historia larga de cada serie desde 2000, de la misma fuente que la página (FRED o Yahoo);
- evaluada con **las funciones reales** de `shared/market-macro.js` y los mismos desfases que el servidor (5/21/65/252
  observaciones diarias, 1/4/13/52 semanales, 1/3/12 mensuales);
- para cada lectura: etiqueta de hoy, percentil del valor actual, con qué frecuencia sale cada etiqueta y cuántas veces
  cambia al año.

El HY y el IG solo tienen 3 años en FRED (licencia ICE).

## 1. Resumen

| Prioridad | Lectura | Problema | Propuesta |
|---|---|---|---|
| **1 · error** | Liquidez neta (también MacroScore y su backtest) | **Unidades:** RRPONTSYD está en miles de millones y se resta como si fueran millones | Multiplicar por 1000 en los 4 sitios (§2) y revisar el MacroScore |
| **1 · concepto** | Producción industrial (INDPRO) | Se clasifica el **nivel** del índice (2017 = 100), no su crecimiento | Variación anual (y 3 meses anualizada) |
| 2 | HY spread | La dirección a 1 mes es ruidosa (38 cambios al año) y hoy no ve la subida de +64 pb en 3 meses | Dirección a 3 meses con media de 5 días (7 cambios al año) |
| 2 | Curvas 10Y-3M y 10Y-2Y | «Aplanada» se aplica a curvas **invertidas** (−0,5 a 0) | Reordenar las etiquetas y añadir la «desinversión» |
| 2 | Liquidez neta | Cortes de nivel fijos: con las unidades corregidas, «normal» el 100 % de los últimos 3 años | Usar la variación a 13 semanas, como el MacroScore |
| 3 | IG spread | Sin dirección; dos etiquetas en 3 años | Misma dirección que el HY |
| 3 | Breakeven 5Y | «Riesgo deflación» por debajo del 2 %: 37 % del tiempo | «Expectativas bajas»; deflación solo < 1,25 % |
| 3 | DXY, T-Bill 3M | Dirección asimétrica o ausente | Añadir «bajando» / sesgo de bajadas o subidas |
| 3 | VIX | Cortes distintos en cada módulo; 59 cambios al año | Alinear con Cava (14/20/30) y, si quieres, histéresis |
| — | 10Y, TIPS 10Y, M2, balance de la Fed | Correctas para lo que pretenden | Sin cambios |

## 2. Error de unidades en la liquidez neta (prioridad 1)

FRED publica **WALCL y WTREGEN en millones** y **RRPONTSYD en miles de millones**. Todas las combinaciones del
proyecto hacen `WALCL − RRPONTSYD − WTREGEN` sin convertir, así que el repo inverso se resta 1000 veces más pequeño de
lo que es. `backtest/config/series.yaml` lo declara en millones, y no lo está.

Dónde está:
1. `server.js → /api/fred3`: lectura de la pestaña principal y componente de liquidez neta del MacroScore en
   `rotacion.html`.
2. `scripts/market_daily_snapshot.js`: captura diaria que recibe Sol.
3. `backtest/src/processors/alignment.py` (+ `series.yaml`): `macro_weekly.parquet`, el MacroScore histórico y los
   backtests. Ejemplo, junio de 2022: liquidez neta 8,12 billones en el parquet, cuando la correcta es ~6,1.

Efecto:

| | Repo inverso medio | Semanas en que el tramo del MacroScore (25 puntos) es distinto |
|---|---:|---:|
| 2018-2020 | 5-14 mil millones | 0-15 % |
| 2021 | 729 mil millones | 56 % |
| 2022 | 2,0 billones | 52 % |
| 2023 | 1,76 billones | 62 % |
| 2024 | 403 mil millones | 52 % |
| 2025 | 112 mil millones | 36 % |
| 2026 | ~0 | 2 % |
| **2013-2026** | | **27 %** |

- **Hoy apenas cambia nada:** el repo inverso está casi a cero (diferencia de 1-3 mil millones). Ni la lectura ni el
  MacroScore actuales cambian.
- **En 2021-2024 el MacroScore no vio el drenaje del repo inverso**, que fue la principal fuente de liquidez de esos
  años, y su backtest se calibró con esa serie. Los cortes «probados en backtest» de los regímenes deberían revisarse
  después de corregirlo.

Propuesta:
- corregir las unidades en los 4 sitios (`server.js`, `market_daily_snapshot.js`, `alignment.py`, `series.yaml`);
- regenerar `macro_weekly.parquet` y el histórico del MacroScore;
- comparar regímenes antes y después antes de dar por buenos los cortes actuales.

Es un cambio en producción y en el backtest: necesita tu aprobación.

## 3. Lectura por lectura

Hoy = último dato disponible el 2026-11-17. Percentil sobre 10 años (sobre 3 en HY e IG).

| Lectura | Hoy | Etiqueta | Pctl. | Cortes actuales | Frecuencia de las etiquetas (10 años) | Observaciones | Propuesta |
|---|---|---|---:|---|---|---|---|
| VIX | 25,5 | Estrés | 86 | 15 / 20 / 25 / 35 | Calma 36 %, Complacencia 33 %, Cautela 17 %, Estrés 12 %, Pánico 2 % | Bien repartida, pero cambia 59 veces al año (ronda los cortes). Cortes distintos en cada módulo: MacroScore 14/18/23/30, Cava 14/20/30, Duration 20, panel de compra de Rotación 23, modo emergencia 35 | Alinear con Cava (14 / 20 / 30, y 35 = pánico); opcional: histéresis de 1 punto |
| DXY | 103,6 | Dólar fuerte y subiendo | 81 | 95 / 100 / 106; «subiendo» si Δ1M > 1 (≥ 100) o > 0 (≥ 106) | neutral 38 %, débil 24 %, fuerte 18 %… | Asimétrico: hay «subiendo» pero nunca «bajando»; con < 95 no mira la dirección | Dirección simétrica (±1 punto en 1 mes) en todos los niveles |
| 10Y | 5,10 % | Estrés por tipos largos | 99 | 3,0 / 4,0 / 4,75 | bajos 54 %, restrictivos 28 % | Coherente con Duration (4,55-4,60 como disparador) | Sin cambios; quizá añadir dirección a 3 meses (+45 pb) |
| TIPS 10Y | 2,92 % | Tipos reales muy restrictivos | 99,9 | 0 / 1 / 2 | 3 años: restrictivos 53 %, muy restrictivos 47 % | Correcta (el oro en Rotación usa < 1 %: coherente) | Sin cambios |
| T-Bill 3M | 4,14 % | Política restrictiva | 73 | 2,5 / 3,5 / 4,75 | 10 años: acomodaticia 58 %, neutral 2 % | Sin dirección: no distingue un ciclo de subidas de uno de bajadas | Añadir sesgo con Δ3M (±25 pb: «bajadas en curso» / «subidas en curso») |
| Curva 10Y-3M | +77 pb | Normal | 60 | 1 / 0 / −0,5 / −1 | Normal 39 %, Empinada 31 %, Invertida 20 %, Aplanada 10 % | **«Aplanada» = de −0,5 a 0, es decir, invertida** (10 % de los días); de 0 a +0,25, casi plana, sale «Normal» (12 %). No ve la desinversión, que el MacroScore sí penaliza | Empinada > 1 · Normal 0,25-1 · Aplanada 0-0,25 · Invertida −0,5-0 · Invertida profunda < −0,5; y «desinvirtiendo» si estaba invertida y sube > 50 pb en 3 meses |
| Curva 10Y-2Y | +30 pb | Normal | 45 | ídem | Normal 65 % | Lo mismo: «Aplanada» invertida el 14 % de los días | Ídem |
| HY spread | 334 pb | Normal | 84 (3 años) | nivel 300/375/475/600; dirección ±20 pb a 1 mes, +75 ruptura | Comprimido 49 %, Normal 47 %, Elevado 4 % (con y sin dirección) | **Lo que viste:** a 1 mes son +3 pb (el 16-oct fue un máximo local) y la lectura no avisa de la subida de 270 a 334 pb en 3 meses. Además la dirección cambia 38 veces al año | Dirección a **3 meses con media de 5 días**, ±40 pb (ruptura +120): 7 cambios al año; hoy diría «Normal · ampliándose (+64 pb 3M)». Alternativa más cercana a la actual: 1 mes con media de 5 días (20 cambios al año), que hoy seguiría sin dirección |
| IG spread | 90 pb | Normal | 64 (3 años) | 80 / 130 / 200 | Normal 76 %, Muy comprimido 24 % | Sin dirección; poco informativa | Misma regla de dirección que el HY (escalada: ±10 pb en 3 meses) |
| Breakeven 5Y | 2,26 % | Inflación controlada | 55 | 2 / 2,5 / 3 | controlada 43 %, **riesgo deflación 37 %**, elevada 17 % | Un 1,8 % no es riesgo de deflación (2016-2020 entero salía así). La señal de Rotación usa 2,8 % | < 1,25 riesgo deflación · 1,25-2 expectativas bajas · 2-2,5 controlada · 2,5-2,8 elevada · ≥ 2,8 elevada persistente (= INFLATION_OVERLAY) · ≥ 3 stagflación |
| Producción industrial | índice 103,4 | **Expansión fuerte** | 94 | **nivel** 98 / 100 / 103 | Expansión 64 % | Error de concepto: un índice 2017 = 100 sube con los años; 103 no significa expansión fuerte. Hoy: variación anual +2,15 % (percentil 76 de 10 años; mediana +0,8 %), 3 meses anualizados +0,9 %, y el último mes −0,45 | Variación anual: < −1 % contracción · −1 a +0,5 estancamiento · +0,5 a +2,5 expansión · > +2,5 expansión fuerte; con nota si los 3 meses anualizados van en sentido contrario. Renombrar el tipo interno `pmi` → `indpro` |
| M2 | 23,5 billones | Expansión M2 moderada | — | variación anual 2 / 6 | moderada 50 %, fuerte 31 % | Correcta | Sin cambios |
| Balance de la Fed | 6,76 billones | Balance estable | — | variación anual ±3 / −8 | repartida | Correcta | Sin cambios |
| Liquidez neta | 5,84 billones | Liquidez normal | 53 | **nivel** 4 / 5,5 / 7 billones | 3 años: normal 100 % (corregida) | Error de unidades (§2) y cortes de nivel que no informan | Variación a 13 semanas con los tramos del MacroScore (±100 / ±500 mil millones), igual que Rotación |

**Lecturas derivadas, revisión rápida:**
- **Uranio:** el régimen usa la rentabilidad del año en curso (YTD > 0). A principios de enero todos los YTD rondan 0
  y la puntuación salta por calendario, no por mercado. Propuesta: rentabilidad a 6 o 12 meses.
- **Diferencial Brent-WTI:** no revisado a fondo.

## 4. Siguiente paso

Si te parece bien, lo haría por bloques, cada uno con su verificación y tu visto bueno:
1. **Unidades de la liquidez neta.** Servidor, captura diaria y backtest, con la comparación del MacroScore antes y
   después.
2. **Lecturas de la pestaña principal:**
   - producción industrial, curvas, HY e IG, breakeven, DXY y T-Bill, y la liquidez neta por variación;
   - en `shared/market-macro.js`, un solo sitio que comparten la página y la captura diaria;
   - aviso a Sol en su addendum de que han cambiado.
3. **Alineación del VIX** entre módulos (opcional).
