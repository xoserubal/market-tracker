# Ficha de episodio — PLTR, 17 de noviembre de 2026 (cierre y after hours)

Primera ficha de la línea de **eventos intradía** (ver [EVENTOS_PROPUESTA.md](EVENTOS_PROPUESTA.md)).
**Exploratoria y descriptiva:** un solo episodio, elegido a mano después de verlo. No valida nada ni interpreta la
intención de nadie.

> **Corrección 2026-11-18 (E1).** La cuota de la subasta de cierre que daba esta ficha (18,0 %) no era la cuota de
> la subasta: era la barra mixta de las 16:00 (subasta + primer minuto de *after hours*, 2,53 M acciones) dividida por
> el volumen de las barras regulares. Con trades de toda la sesión, la subasta (2 009 394 acciones) es el **15,2 % del
> volumen continuo** (13 236 507) y el **13,0 % de la sesión regular con subastas** (15 415 533). El volumen continuo
> tampoco era 13,87 M: esa cifra incluía comunicaciones tardías y condiciones no estándar de horario regular. El
> percentil 49 se calculó con la misma estimación por barras en la historia; la cuota exacta no tiene historia con la
> que compararse (harían falta los trades de las sesiones anteriores). Las cifras corregidas salen de
> `micro/sessions.py`; la ficha automática de E1 está en `fichas/`.

Reproducible con `py -3 ev_case_sheet.py PLTR 2026-11-17`. Los datos crudos y el JSON (`results/ev_case_PLTR_2026-11-17.json`)
se quedan en `MICRO_DATA_DIR` (licencia personal de Alpaca): no van al repositorio.

## 0. Resumen

1. **En la sesión regular, el cierre de PLTR fue normal frente a su propia historia.** Retorno de los últimos 5, 10 y
   30 minutos, rebote desde el mínimo de los últimos 10 minutos, volumen del último minuto y la estimación por barras
   de la subasta: todo entre los percentiles 38 y 80 de sus 45 sesiones previas.
2. **El cierre oficial fue 156,56**, en la subasta de Nasdaq (2,01 M acciones). La última operación continua fue a
   156,53. La subasta no movió el precio.
3. **La barra de 1 minuto de las 16:00 mezcla dos cosas:** la subasta de cierre y el primer minuto de *after hours*.
   Su cierre (157,00) y su máximo salen de operaciones de *after hours*, no de la subasta.
4. **Lo extraordinario está en el *after hours*:**
   - +1,6 % a las 16:30 sobre el cierre (máximo previo +0,4 %, en 27 sesiones con dato);
   - +1,9 % de recorrido máximo hasta las 16:35 (percentil 96; solo el 2-nov, con 27 veces más volumen, y el 16-oct
     fueron mayores).
   - El tramo más rápido (16:27-16:31, de 157,80 a 159,22) se negoció con **32 540 acciones**. El 85 % de las
     operaciones fueron *odd lots* y la mediana del *after hours* fue de 6 acciones.
5. **Tras el cierre se comunicaron 679 093 acciones a precio de referencia:** operaciones fuera de mercado (TRF) con
   condición P o W, la mayoría exactamente a 156,56. Esas operaciones no se hicieron a esas horas ni movieron el precio.
6. **La vela que motivó la ficha (resuelto con la captura del usuario, Investing.com, 5 minutos, hora de Madrid):**
   - es la **barra de volumen verde de las 22:00 de Madrid (16:00 ET)**, no una vela de precio;
   - corresponde a la **subasta de cierre** (2,01 M acciones);
   - sale verde porque esa barra cierra por encima de su apertura, empujada por el primer minuto de *after hours*;
   - frente a la historia de PLTR parece **normal**: la estimación por barras (barra mixta / barras regulares) da
     18,0 %, percentil 49 de esa misma estimación en sus sesiones previas. La cuota exacta de la subasta es 15,2 % del
     volumen continuo (ver la corrección del principio). Un pico así aparece casi todos los días;
   - la subida de la línea de precio a la derecha (hasta 158,79) es el *after hours*, y eso sí es extremo (§4-§5).

   **Consecuencia para el detector:** el volumen de las subastas debe ir en su propio tramo y normalizarse contra
   las subastas anteriores del valor. Medido junto al volumen continuo, marcaría «volumen extraordinario al cierre»
   prácticamente todos los días en todos los valores.

## 1. Datos usados

| Dato | Ventana (hora de Nueva York) | Filas | Peticiones |
|---|---|---:|---:|
| Barras de 1 minuto | julio a 17-nov 17:20 (5 meses) | 75 817 | 10 |
| Trades | 09:25-17:15 | 270 675 | 28 |
| Quotes (NBBO) | 15:30-16:05 | 31 727 | 4 |

- Feed SIP, `asof` = 2026-11-17, ajuste `raw`. Unidades con calidad A en el manifiesto.
- Los trades **no cubren el premercado** antes de las 09:25 ni el *after hours* después de las 17:15. A las 17:36 ET
  aún no había pasado el retraso de 15 minutos del plan gratuito para el resto del *after hours*.
- **Línea base:**
  - 45 sesiones, del 15-sep al 16-nov, todas anteriores al episodio;
  - excluye el periodo de prueba de G2A (con su embargo) y cualquier sesión de hace más de 180 días;
  - las medidas del *after hours* a las 16:30 tienen solo 27 sesiones con dato: en el resto no hubo barra a las 16:30.

## 2. Contexto del día

| | |
|---|---|
| Subasta de apertura | 159,98 (169 632 acciones) |
| Máximo de la sesión regular | 162,59 a las 09:31:41 |
| Mínimo de la sesión regular | 153,91 a las 12:04:07 |
| Última operación continua | 156,53 a las 15:59:59,99 |
| Cierre oficial (subasta de cierre) | 156,56 a las 16:00:00,06 |
| Retorno de la apertura a la última continua | −2,2 % (percentil 20 de su historia) |
| Volumen continuo regular | 13,24 M acciones (exacto, sin subastas, comunicaciones tardías ni condiciones no estándar; antes se dio 13,87 M) |

## 3. La sesión dividida en tramos

Separar estos tramos es requisito del detector: en las barras de 1 minuto se mezclan.

| Tramo | Acciones | Precio | Nota |
|---|---:|---|---|
| Negociación continua 15:50-16:00 | 1 340 648 | de 156,63 a 156,53, mínimo 155,83 a las 15:54 | |
| Subasta de cierre (Nasdaq, condición 6) | 2 009 394 | 156,56 | 15,2 % del volumen continuo; 13,0 % de la sesión regular con subastas |
| Impresiones de cierre oficial (M) en Q y P | (2 × 2 009 394) | 156,56 | Informativas: no suman volumen |
| Comunicaciones tardías a precio de referencia (TRF, P/W) | 679 093 en 56 operaciones | sobre todo 156,56; algunas W a 147,75-149,61 | La mayor, 207 152 acciones, se comunicó a las 16:57:46 |
| *After hours* (sin subastas ni precios no estándar), 16:00-17:15 | 289 274 en 5 042 operaciones | 156,37 → 159,48 → 156,90 | 90 % de las operaciones son *odd lots*; mediana de 6 acciones |

## 4. Frente a su propia historia (45 sesiones previas)

| Medida | Hoy | Percentil | Mediana | p10 / p90 | Máximo previo |
|---|---:|---:|---:|---|---:|
| Retorno de los últimos 5 min (15:54→15:59) | +0,11 % | 71 | 0,00 % | −0,36 / +0,28 % | +0,88 % |
| Retorno de los últimos 10 min | −0,08 % | 38 | 0,00 % | −0,45 / +0,53 % | +1,39 % |
| Retorno de los últimos 30 min | −0,01 % | 51 | −0,01 % | −0,61 / +0,79 % | +1,58 % |
| Ídem 10 min en desviaciones típicas de 1 minuto | −0,16 | 38 | 0,00 | −1,23 / +1,32 | +2,93 |
| Rebote desde el mínimo de los últimos 10 min | +0,45 % | 73 | +0,23 % | +0,06 / +0,67 % | +1,36 % |
| Cuota de volumen de los últimos 10 min | 9,6 % | 71 | 8,3 % | 5,9 / 11,3 % | 12,8 % |
| Volumen del minuto 15:59 / mediana por minuto del día | ×17,1 | 80 | ×13,7 | ×7,8 / ×19,6 | ×28,1 |
| Barra mixta de las 16:00 / barras regulares (estimación, no cuota de subasta) | 18,0 % | 49 | 18,1 % | 11,1 / 28,6 % | 61,2 % |
| **After hours: retorno a las 16:30 sobre las 15:59** | **+1,60 %** | **100** (n = 27) | −0,08 % | −0,91 / +0,09 % | +0,40 % |
| **After hours: máximo 16:01-16:35** | **+1,88 %** | **96** | +0,20 % | +0,01 / +0,58 % | +5,20 % (2-nov) |
| Volumen de las barras 16:01-16:35 | 151 214 | 31 | 308 450 | 65 754 / 1,69 M | 5,74 M |

Lectura:
- Nada de la sesión regular sale de lo habitual en PLTR.
- El *after hours* tiene un desplazamiento extremo para su historia con un volumen por debajo de la mediana. Por eso
  encaja en la anomalía de **desplazamiento con volumen escaso**, no en la de volumen anómalo.
- Las dos sesiones previas con un recorrido mayor fueron:
  - el 2-nov, con 4,06 M acciones de *after hours*;
  - el 16-oct (+2,0 %), con 143 000 acciones, también escaso.
- **El volumen de las barras de *after hours* incluye las comunicaciones tardías** (condición P). Para medir el
  volumen de verdad hacen falta los trades.

## 5. El *after hours* minuto a minuto (trades, reglas oficiales de barras)

| Tramo | Acciones | Operaciones | Primera → última | Mínimo / máximo | % operaciones *odd lot* | % volumen TRF |
|---|---:|---:|---|---|---:|---:|
| 16:00-16:20 | 138 551 | 1 541 | 156,56 → 157,42 | 156,37 / 157,82 | 89 % | 78 % |
| 16:20-16:27 | 17 733 | 681 | 157,43 → 157,74 | 157,00 / 158,00 | 94 % | 28 % |
| **16:27-16:31** | **32 540** | 363 | **157,80 → 159,22** | 157,80 / 159,10 | 85 % | 72 % |
| 16:31-16:40 | 28 605 | 825 | 159,00 → 158,33 | 158,01 / 159,48 | 90 % | 44 % |
| 16:40-17:00 | 33 943 | 924 | 158,05 → 157,21 | 156,90 / 158,17 | 90 % | 51 % |

- El máximo y el mínimo de la tabla siguen las reglas de barras. Con todas las operaciones salían un máximo de
  169,72 y un mínimo de 150,61: eran *odd lots* comunicados fuera de mercado, que no actualizan las barras. Es el
  mismo error que se corrigió en G1.5.
- El 16:00-16:20 incluye 95 804 acciones con condición T a 156,56 y otras comunicaciones al precio de cierre.
- A las 17:20 PLTR estaba en 157,68, por debajo del máximo del *after hours*.
- No he comprobado si hubo noticias a esa hora: la ficha describe lo ejecutado, no la causa.

## 6. Desequilibrio comprador/vendedor en el cierre (con reservas)

| Tramo | Acciones | Tick | Lee-Ready | EMO | Bid-ask estricto | Diferencial mediano |
|---|---:|---:|---:|---:|---:|---:|
| 15:30-15:50 | 666 161 | +6,6 % | +8,7 % | +6,9 % | +11,3 % (63 % sin clasificar) | 3,2 pb |
| 15:50-16:00 | 1 340 648 | −5,5 % | −6,1 % | −5,4 % | −5,8 % (50 % sin clasificar) | 1,9 pb |

(Delta = compra − venta agresiva, en % del volumen.)

- Aquí los cuatro métodos coinciden en el signo; en G1.5 no coincidían.
- **No hay línea base:** no tenemos quotes de las sesiones anteriores, así que no se puede decir si −6 % es
  habitual en el cierre de PLTR.
- Tampoco se ha probado la sensibilidad (TRF fuera de la secuencia del tick, quote retrasada).
- **No se interpreta.**

## 7. Anomalías del catálogo que encajan

Detalle del catálogo en [EVENTOS_PROPUESTA.md](EVENTOS_PROPUESTA.md) §3.

| Código | Anomalía | ¿Encaja? |
|---|---|---|
| C3 | Desplazamiento extraordinario en el *after hours* | **Sí** (percentil 100 a las 16:30, n = 27) |
| I1 | Desplazamiento alto con volumen escaso | **Sí** (16:27-16:31) |
| C4 | Comunicaciones tardías a precio de referencia | Presente (679 093 acciones); sin línea base todavía |
| C1 | Cambio brusco en los últimos minutos de la sesión regular | No (percentiles 38-71) |
| C2 | Subasta de cierre anómala (cuota o salto de precio) | No con la estimación por barras (percentil 49; +1,9 pb sobre la última continua). La cuota exacta (15,2 %) no tiene historia comparable |
| V1 | Volumen anómalo al cierre | No (percentil 71-80) |

**Conclusión de la ficha:** el episodio no es una vela alcista en la sesión regular. Es un movimiento de *after hours*
de +1,6 % a +1,9 %, extremo para la historia de PLTR y hecho con poco volumen y operaciones muy pequeñas. Que el
precio volviera a 157,7 a las 17:20 se anota como observación; no es una conclusión ni una predicción.

## 8. Abrirlo en el laboratorio

1. `py -3 lab/server.py` → http://127.0.0.1:8765
2. Ticker PLTR, fecha 2026-11-17, desde 15:30 hasta 16:40, vela de 1 minuto, sesión **extendida**.

El laboratorio todavía no abre episodios desde un enlace con parámetros: está en la propuesta (§4, pieza 6).

## 9. Limitaciones

- Episodio elegido después de conocerlo: sirve para diseñar el detector, no como ejemplo de nada.
- Sin quotes de sesiones anteriores: el desequilibrio por agresor no está normalizado.
- Sin trades fuera de 09:25-17:15.
- **Acceso al periodo de prueba:** una primera versión de la línea base usó sesiones del 24-ago al 14-sep y la
  primera ejecución calculó en memoria, sin mostrarlas, medidas de todas las sesiones de PLTR desde 2020. Queda
  anotado en `library/test_period_usage.jsonl` (52 sesiones, sin variables de G2A). La versión final de la ficha
  excluye el periodo de prueba.
