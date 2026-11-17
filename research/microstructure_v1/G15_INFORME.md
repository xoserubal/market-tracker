# Microestructura v1 — G1.5: laboratorio visual y primer contacto con el agresor (2026-11-15)

Fase intermedia entre G1 (infraestructura) y G2 (exploración y preregistro). **Exploratoria: no valida nada.**
Dos episodios elegidos a mano y una comparación técnica de clasificadores. Ninguna variable de resultado se ha
calculado sobre el periodo de prueba.

**Resumen.**
1. El laboratorio funciona: footprint por vela y nivel, cuatro clasificadores de agresor, modo ciego y biblioteca de
   episodios con procedencia. 38 pruebas sin red pasan.
2. **El signo del delta de la primera hora no es robusto.** En los dos episodios cambia de signo según el método
   (tick / Lee-Ready / EMO frente a bid-ask estricto), según se use o no la quote con 1 s de retraso, y según se
   excluyan o no los trades fuera de mercado (TRF) de la secuencia del tick. Ninguna de esas elecciones es
   claramente la correcta. **Cualquier variable de G2 basada en el desequilibrio comprador/vendedor tiene que
   preregistrar el método y probar estas variantes como sensibilidad**.
3. Los dos episodios (NVDA, que se recupera en el día, y GOOGL, que no) tienen un delta de la primera hora muy
   parecido: negativo con los métodos habituales. Con n = 2 no se puede concluir nada, pero no hay indicio de que
   el delta separe ambos casos.
4. Error encontrado y corregido: el recorrido del día del estudio de casos (y el resumen de precios de los
   episodios del laboratorio) usaba todos los trades, incluidas comunicaciones tardías que no actualizan máximo y
   mínimo. GOOGL salía con un «máximo» de 323,94 cuando la barra diaria marca 288,33 (§4).
5. En la submuestra de quotes (380 días de 19 valores), Lee-Ready deja sin clasificar el 11 % del volumen y el
   tick y Lee-Ready coinciden en el 85 %. Retrasar la quote 1 s cambia de lado el 14 % del volumen clasificado.
   **La composición del mercado cambia mucho con los años**: TRF del 28 % (2017) al 51 % (2026) del volumen, odd
   lots del 11 % al 43 %. Desarrollo y prueba no tienen la misma microestructura (§5).
6. **Defecto del plan B1 congelado (de G1):** 4 de los 200 bloques piden un símbolo en fechas en que no tiene datos
   (PCLN y FISV por cambio de nombre, vacíos enteros; CTXS y MON, en parte, tras dejar de cotizar). Son 261 de
   20 000 sesiones. Pendiente de tu decisión (§7).

---

## 1. Qué se ha construido

| Pieza | Qué hace |
|---|---|
| `micro/episode.py` | Carga compacta de los trades y quotes de un día (NVDA, ~9,6 M de trades, sin agotar memoria) |
| `micro/aggressor.py` | Lado agresor por cuatro métodos: tick, bid-ask estricto, Lee-Ready, EMO. Lo no clasificable queda indeterminado, nunca se fuerza |
| `micro/footprint.py` | Volumen por (vela, nivel de precio) con compra, venta e indeterminado; OHLC con las reglas oficiales de barras; cursor ciego |
| `micro/library.py` | Biblioteca de episodios y anotaciones (humano / IA / regla) con procedencia y registro de accesos |
| `lab/` | Visor local (solo 127.0.0.1): servidor Python, el navegador solo dibuja |
| `g15_*.py` | Descarga acotada de un episodio, selección del contraste, estudio de casos, comparación de clasificadores |

**Exclusiones que siempre quedan como indeterminado:** subastas (O, Q, 5, 6, M; volumen real, sin agresor),
precios no estándar (B, C, G, H, N, P, R, V, W, Z, 4, 7, 9) y trades anulados.

**Quote de referencia:** la última NBBO estrictamente anterior al trade. No vale si está cruzada, bloqueada, con un
lado a 0 o es demasiado antigua; en ese caso el trade queda indeterminado (no se busca otra anterior).

**Modo ciego.** Con un cursor, el servidor solo usa trades anteriores; lo posterior no sale del servidor. Cada
petición queda en `library/access_log.jsonl`, y de ahí se deduce (no se pregunta) si una anotación es
retrospectiva (`revealed_future`). Una anotación retrospectiva sirve para generar hipótesis, nunca como evidencia.
Todo acceso a fechas del periodo de prueba (2022-01-03 a 2026-09-14, con embargo desde 2021-10-29) queda
registrado. Qué se excluye después del conjunto confirmatorio depende de lo que se vio (política proporcionada,
[G2_CAMBIOS.md](G2_CAMBIOS.md) §3): solo el valor afectado y en la ventana afectada, no la fecha entera.

**Etiquetas (taxonomía v1):** posible capitulación vendedora, posible absorción compradora, posible acumulación,
posible distribución, presión compradora creciente, presión vendedora decreciente, ruptura fallida, ausencia de
patrón, indeterminado. Describen lo observado en lo ejecutado, no la intención de nadie.

## 2. Los dos episodios

**NVDA 2026-11-12** (el caso que motivó G1.5) y **GOOGL 2026-10-29** como contraste. El contraste se eligió con una
regla fijada antes de mirar candidatos (`g15_contrast_select.py`): miembro del S&P 500, ventana 2026-09-15 a
2026-11-13 (fuera del periodo de prueba), hueco de apertura ≤ −7 %, trades del día ≥ 2 × la mediana de 20 sesiones,
sin recuperación (cierre ≤ apertura y cierre a 5 sesiones < cierre del día), el de mayor volumen en dólares.
58 días tenían hueco y volumen; 15 cumplían también «sin recuperación»; ganó GOOGL (le siguen INTC, GOOG, SNDK, AMD).

| | NVDA 2026-11-12 | GOOGL 2026-10-29 |
|---|---|---|
| Cierre anterior | 173,73 | 324,89 |
| Apertura (subasta) | 151,00 (−13,1 %) | 287,22 (−11,6 %) |
| Trades del día / mediana 20 sesiones | 9,57 M / 1,96 M (×4,9) | 3,35 M / 0,56 M (×5,9) |
| Mínimo del día | 148,80 (09:31) | 280,36 (09:38) |
| Máximo del día | 167,14 (11:12) | 288,33 (11:41) |
| Cierre (barra diaria) | 166,19 (+10,1 % desde la apertura) | 283,82 (−1,2 % desde la apertura) |
| Cierre siguiente sesión | 162,85 | 279,84 |
| Volumen de la subasta de apertura | 16,1 M acciones | 2,8 M acciones |
| Volumen premercado | 90,7 M | 8,5 M |

NVDA solo tiene datos hasta 2026-11-13: no se sabe si la recuperación fue sostenida.

**Coste real de la descarga** (trades del día completo + quotes de 09:25 a 12:00):

| | Trades | Quotes | Tiempo total |
|---|---|---|---|
| NVDA | 9,57 M filas, 962 peticiones, 85 MB | 2,71 M filas, 274 peticiones, 17 MB | 37 min |
| GOOGL | 3,35 M filas, 340 peticiones, 32 MB | 0,59 M filas, 63 peticiones, 5 MB | 14 min |

La conciliación trades ↔ barras de 1 minuto cuadra en los dos días: 390 minutos, volumen y nº de trades idénticos,
una barra «inesperada» (nota B).

## 3. El delta de la primera hora (09:30-10:30) según el método

Delta = compra agresiva − venta agresiva, en millones de acciones. «Base» = quote estrictamente anterior.

| Variante | NVDA | GOOGL |
|---|---:|---:|
| Tick | −18,9 | −4,7 |
| Lee-Ready | −9,9 | −2,3 |
| EMO | −16,2 | −4,2 |
| Bid-ask estricto (solo clasifica en el bid/ask o fuera) | **+6,6** | **+1,6** |
| Lee-Ready con quote simultánea | −9,9 | −2,3 |
| Lee-Ready con la quote retrasada 1 s | **+10,0** | −1,5 |
| Lee-Ready sin TRF en la secuencia del tick | **+1,4** | **+0,6** |
| Lee-Ready excluyendo los trades TRF | −2,2 | −0,6 |
| Lee-Ready excluyendo odd lots | −10,3 | −2,1 |

Volumen de la primera hora: NVDA 285 M acciones, GOOGL 42 M.

Lectura:
- **Tick, Lee-Ready y EMO dan un delta negativo; el bid-ask estricto, positivo.** El bid-ask solo clasifica el
  44 % (NVDA) / 36 % (GOOGL) del volumen de las dos primeras horas: lo que se negocia dentro del diferencial lo
  resuelven los otros con el tick, y ahí está la diferencia de signo.
- **Usar la quote simultánea o la estrictamente anterior no cambia nada** (diferencias de miles de acciones).
- **Retrasar la quote 1 s le da la vuelta a NVDA.** Un segundo es mucho (es una prueba de sensibilidad, no una
  hipótesis de desfase), pero muestra que en una apertura violenta el emparejamiento trade-quote decide el signo.
- **Los TRF pesan casi la mitad del volumen** (48 % NVDA, 47 % GOOGL) y llevan la hora de comunicación, no la de
  ejecución. Quitarlos de la secuencia del tick convierte el delta negativo en positivo en los dos casos.
- **El 23-26 % del volumen se negocia exactamente en el punto medio** (30-36 % de los TRF): ese tramo lo clasifica
  solo el tick, el método más expuesto al problema anterior.
- Las tasas de acuerdo entre métodos son altas cuando ambos clasifican (tick~Lee-Ready 89 %, tick~EMO 95 %), pero
  eso no es exactitud: no hay lado agresor verdadero con el que comparar, y el desacuerdo se concentra en el
  volumen que decide el signo.

**Consecuencia para G2.** La hipótesis H-B1 de la propuesta usa el «desequilibrio por la regla del tick ponderado
por volumen». Con lo visto aquí, el preregistro tiene que fijar si los TRF entran en la secuencia de referencia y
llevar las variantes de esta tabla como sensibilidad. Si el resultado depende de esa elección, no es un hallazgo.

## 4. Error encontrado y corregido: precios fuera de las reglas de barras

`g15_case_study.py` calculaba el recorrido del día (apertura, mínimo, máximo, cierre) con **todos** los trades de la
sesión regular, incluidos los que según las reglas oficiales no actualizan máximo ni mínimo. En los dos días el
precio erróneo era un odd lot comunicado por TRF (condiciones `@ I`, mercado `D`) por la tarde:

| | Antes (todos los trades) | Ahora (reglas de barras) |
|---|---|---|
| GOOGL máximo / mínimo | 323,94 (15:43, casi el cierre del día anterior) / 279,73 | 288,33 / 280,36, igual que la barra diaria |
| NVDA máximo / mínimo | 177,41 (14:41, por encima del cierre anterior) / 147,04 | 167,14 / 148,80 |

Los recorridos corregidos están en `g15_case_study.json` (con los valores anteriores guardados aparte).

El mismo fallo estaba en el resumen de precios que el laboratorio guarda con cada episodio de la biblioteca
(`price_min`/`price_max`). Ahora los dos usan la misma regla que el footprint (máximo/mínimo con `upd_hl`,
apertura/cierre con `upd_oc ≠ N`), con una prueba de regresión (`test_episode_prices_follow_bar_rules`). La
biblioteca estaba vacía, así que ningún episodio guardado quedó afectado. Las velas de 5 minutos y el footprint ya
aplicaban la regla bien.

## 5. Comparación de clasificadores en la submuestra de quotes

`g15_classifier_comparison.py` sobre los 20 bloques × 20 sesiones de quotes (sesión regular): **380 días de 19
valores**. Faltan los 20 días de FISV (2024-01), sin datos por el defecto del §7. Solo estadísticas de
clasificación, sin rentabilidades. El periodo de prueba se usó solo para esto y quedó anotado en
`library/test_period_usage.jsonl` (240 sesiones de 12 valores; corregido el 2026-11-15, antes decía 260). Mediana por día; trades por día: 14 000 / 28 000 / 40 000 según el
tercil de liquidez.

| Medida (mediana por día) | Valor |
|---|---:|
| Volumen sin clasificar: tick / Lee-Ready / bid-ask estricto | 4,5 % / 10,7 % / 56,5 % |
| Acuerdo tick~Lee-Ready (cuando ambos clasifican) | 85,2 % |
| Acuerdo tick~Lee-Ready en TRF / en bolsas | 87,3 % / 84,7 % |
| Volumen con quote válida | 95,2 % |
| Antigüedad de la quote usada | 1,6 ms |
| Lee-Ready con quote simultánea en vez de anterior: volumen que mantiene el lado | 100 % |
| Lee-Ready con la quote retrasada 1 s: volumen que mantiene el lado | 85,7 % |
| Volumen TRF / odd lots / en el punto medio | 37 % / 25 % / 21 % |
| Volumen en subastas (excluido) | 1,8 % |

**Por año** (mediana por día):

| Año | Acuerdo tick~LR | LR sin clasificar | TRF | Odd lots | En el punto medio |
|---|---:|---:|---:|---:|---:|
| 2017 | 85 % | 6 % | 28 % | 11 % | 13 % |
| 2018 | 83 % | 10 % | 39 % | 8 % | 17 % |
| 2019 | 86 % | 8 % | 24 % | 26 % | 20 % |
| 2021 | 90 % | 8 % | 31 % | 20 % | 24 % |
| 2022 | 87 % | 5 % | 35 % | 26 % | 22 % |
| 2023 | 82 % | 11 % | 36 % | 20 % | 22 % |
| 2024 | 83 % | 14 % | 41 % | 33 % | 20 % |
| 2025 | 87 % | 14 % | 46 % | 36 % | 24 % |
| 2026 | 84 % | 16 % | 51 % | 43 % | 24 % |

(Cada año es la muestra de 1-3 valores de la submuestra, no el mercado entero; 2020 no tiene ningún bloque.)

**Precisión de los timestamps:** milisegundos en 2017, microsegundos en 2018, nanosegundos desde 2019. En 2017 el
emparejamiento trade-quote es más ambiguo.

Lectura:
- **El acuerdo entre métodos es estable (82-90 %) y la quote anterior o simultánea da igual.** Lo que sí mueve el
  resultado es el desfase entre trade y quote (1 s cambia el 14 %) y la secuencia de referencia del tick.
- **Lo que más cambia es la composición:** cada vez más volumen fuera de mercado, en odd lots y en el punto medio, y
  más volumen sin clasificar por Lee-Ready. Desarrollo (mediana TRF 28 %, odd lots 16 %) y prueba (42 %, 30 %)
  no son el mismo mercado. Una variable de agresor calibrada en desarrollo puede cambiar en prueba por la
  estructura del mercado, no por la señal. **G2 debe medir estas variables relativas a la propia historia del
  valor (por ejemplo, frente a sus 60 sesiones previas) y no en niveles absolutos**, y llevar el año o la cuota de
  TRF como control.
- En el tercil menos líquido, el bid-ask estricto deja sin clasificar el 78 % y los odd lots son el 41 % del
  volumen: ahí el bid-ask estricto no sirve.

## 6. Limitaciones

- Dos episodios, elegidos a mano, con el resultado conocido: sirven para entender la herramienta, no para extraer
  ninguna regla.
- No hay lado agresor verdadero. Concordancia entre métodos ≠ exactitud.
- La absorción pasiva (órdenes límite que reciben las agresivas) no se ve sin libro de órdenes; solo se infiere de
  forma indirecta (mucho volumen agresor en un nivel sin que el precio avance), y esa inferencia hereda toda la
  fragilidad del §3.
- Antes de ~2018 los timestamps de Alpaca son de milisegundos (§5): el emparejamiento trade-quote es más ambiguo.
- Las quotes solo cubren 09:25-12:00 en los episodios y la sesión regular en la submuestra.
- Los odd lots por TRF entran en la secuencia de referencia del tick aunque su precio no actualice las barras (el
  de 323,94 del §4 era uno de ellos). Cada uno genera un tick falso y su vuelta. Pesan poco en volumen (el 1,8 %
  se negocia fuera del diferencial), pero G2 debería probar la variante «solo trades que actualizan barras» en la
  secuencia del tick.

## 7. Qué queda pendiente

- Nada de lo anterior autoriza G2: siguen pendientes la partición desarrollo/prueba, los costes y el preregistro.
- **Defecto del plan B1 congelado.** Comprobado cada bloque contra las barras diarias de su (símbolo, asof):

  | Bloque | Símbolo | Sesiones sin datos | Causa |
  |---|---|---:|---|
  | dev-036 | PCLN | 100 de 100 | Priceline pasó a BKNG el 27-feb-2018; el bloque es de jun-oct de 2018 |
  | test-024 | FISV | 100 de 100 | Fiserv cotizó como FI de jun-2023 a nov-2025; la lista del S&P lo llamaba FISV hasta ene-2024 |
  | test-086 | CTXS | 54 de 100 | Dejó de cotizar en sep-2022, dentro del bloque |
  | dev-018 | MON | 7 de 100 | Ídem en jun-2018 |

  Total: 261 de 20 000 sesiones (1,3 %). El plan de quotes tiene el mismo problema en el bloque de FISV. Opciones:
  (a) mantener el plan y declarar esos bloques como faltantes; (b) corregir PCLN→BKNG y FISV→FI en esas fechas
  (misma empresa) y dejar CTXS/MON con lo que hay; (c) sustituir los dos bloques vacíos por otros con la misma
  regla de muestreo. Recomiendo (b): no cambia la muestra, solo el símbolo con el que se pide. La descarga de B1
  todavía no ha llegado a esos bloques (va después del nivel A).
  **Resuelto el 2026-11-15 con la opción (b)**, aprobada: planes v2, ver [G2_CAMBIOS.md](G2_CAMBIOS.md) §1.
- ~~El nivel A probablemente tiene el mismo hueco para Fiserv~~ Comprobado: **no lo tiene**. El nivel A ya asignaba
  a cada fecha el ticker de su época (PCLN hasta el 26-feb-2018 y BKNG después; FISV, FI y FISV), sin ningún día
  sin datos en esas dos empresas. El defecto era solo de los planes B1 y de quotes.
- Descargas en curso: nivel A (barras de 1 minuto, ~24 h) y después el piloto B1 completo (~15 h).
- El laboratorio se usa con `py -3 lab/server.py` → http://127.0.0.1:8765. Mientras dure la descarga, mejor no
  cargar días muy grandes (el 2026-11-15 un análisis en paralelo agotó la memoria y colgó la descarga).
