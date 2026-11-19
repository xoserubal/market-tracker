# Flow negativo — informe de la etapa 0, versión 3 (muestra por empresa)

Fecha: 2026-11-18. Cálculos hechos en DESPACHOB (`s1_extend.py`, `s1_sic.py`, `s1_panel.py`, `s1_stats.py`).
Informe escrito y comprobado en LAWNMOWER con los mismos datos (`D:\backup market tracker\flow_negative_v1`, copia
verificada por SHA-256). **No se ha calculado ningún rendimiento posterior a una señal.** Producción sin tocar.

Complementa a `ETAPA0_INFORME.md` (v2), que sigue valiendo para composición, precios, paridad y ajustes. Este
documento solo cubre lo que cambia con la v3 y lo que se ha encontrado al revisarla.

## Resumen

1. **Cambio de enfoque:** la unidad pasa a ser la empresa, no la pertenencia a un índice. Una empresa entra en la
   muestra el primer día en que pertenece a cualquiera de los tres índices y sigue dentro aunque salga de él, hasta
   que deja de cotizar. 2 088 empresas y 3,47 M de días-empresa desde 2018.
2. **Problema grave encontrado al revisar (§3):** la composición del S&P 600 anterior al 17-dic-2019 no existe; es la
   lista de esa fecha copiada hacia atrás. Con el marco por empresa, eso mete en 2018-2019 a 542 empresas por una
   pertenencia ficticia: el 36 % de los días de esos años y el 25 % de los días con Flow negativo del periodo de
   desarrollo. Son supervivientes: faltan las pequeñas que salieron del índice antes de finales de 2019. **Hay que
   decidir cómo corregirlo antes de usar los cortes de H1 o de firmar nada.**
3. Problema menor (§4): el filtro de capitalización «sin mirar al futuro» deja pasar errores de escala de la SEC en
   unas 20 empresas (0,04 % de los días). Afecta sobre todo a la franja «micro».
4. El resto de puertas se cumple: precio, sector, desenlaces y diseño de H1 (§5-§7).

## 1. Qué cambia respecto a la v2

| Pieza | v2 | v3 |
|---|---|---|
| Unidad | Días en que el valor pertenece a un índice | Días de la empresa desde su entrada en el marco |
| Tamaño | Universo L / M / S (el índice) | Capitalización en la fecha: micro < 300 M$, pequeña < 2 000 M$, mediana < 10 000 M$, grande |
| Después de salir del índice | Solo se usa el precio para medir resultados | La empresa sigue generando señales |
| Series cortadas | Cada petición terminaba 75 días después de la baja del índice | 265 series prolongadas hasta el final de los datos (`s1_extend.py`) |
| Duplicados | — | 115 pares de series idénticas fusionados (mismos precios en ≥ 95 % de ≥ 20 días comunes); 9 sucesiones por cambio de ticker; 7 pares de clases de acciones |
| Capitalización | Filtro de errores centrado (miraba presentaciones posteriores) | Filtro que en cada presentación solo mira las anteriores (`mcap_pit`); el centrado queda como sensibilidad (`mcap_retro`) |
| Sector sin Wikipedia | Pendiente | Código SIC de la SEC con tabla SIC→GICS solo cuando es inequívoca (`s1_sic.py`) |
| Eventos | Excluían la señal en [t − 259, t + 40] | Excluyen solo los de [t − 259, t] (impiden calcular bien el Flow); los de (t, t + 40] se marcan y se tratan en el resultado |
| Coste | Supuestos | Además, spread estimado (Abdi-Ranaldo, 21 sesiones) para contrastar los supuestos |

La entrada en el marco usa solo información disponible en cada fecha: la historia de una empresa anterior a su
primera pertenencia a un índice no entra. Elegirla porque más tarde entró en un índice sería seleccionar por su éxito
posterior. **Esa regla es correcta, pero solo funciona si la fecha de pertenencia es real** (ver §3).

## 2. La muestra

| Año | Días-empresa | Empresas | Utilizables | Ya fuera de todo índice | Con capitalización | Con sector |
|---|---|---|---|---|---|---|
| 2018 | 369 680 | 1 520 | 96,2 % | 1,3 % | 89,4 % | 99,3 % |
| 2019 | 375 983 | 1 535 | 97,2 % | 1,4 % | 89,8 % | 99,3 % |
| 2020 | 382 300 | 1 561 | 97,6 % | 2,2 % | 90,6 % | 99,4 % |
| 2021 | 384 635 | 1 584 | 97,9 % | 2,0 % | 90,7 % | 99,6 % |
| 2022 | 385 850 | 1 598 | 96,9 % | 2,6 % | 91,4 % | 99,8 % |
| 2023 | 393 545 | 1 647 | 97,4 % | 4,8 % | 91,5 % | 99,8 % |
| 2024 | 407 899 | 1 679 | 97,8 % | 7,4 % | 90,7 % | 99,8 % |
| 2025 | 411 429 | 1 704 | 98,2 % | 8,9 % | 90,1 % | 99,8 % |
| 2026 | 363 294 | 1 733 | 98,1 % | 10,1 % | 89,2 % | 99,7 % |

- «Utilizable» = Flow completo y sin evento corporativo en las 259 sesiones previas.
- La parte de empresas que ya no están en ningún índice crece con los años (1 % → 10 %): es lo esperado al seguirlas
  después de salir.
- Sector: 97,7 % de Wikipedia, 2,0 % por SIC, 0,4 % sin sector. De 139 CIK clasificados por SIC, 12 quedan
  «ambiguos» (el código encaja en varios sectores GICS) y se tratan sin sector.

**Tamaño en desarrollo (días utilizables, 2018-2020):** grande 291 k, mediana 350 k, pequeña 322 k, micro 23 k y sin
capitalización 108 k (10 %). Las micro son, en su mayoría, empresas que han caído: en prueba, el 89 % de sus días son
de empresas que ya salieron de los índices. Solo la mitad de los días micro con Flow negativo pasan el filtro operable
(precio ≥ 3 $ y ≥ 1 M$/día): 52 % en desarrollo, 47 % en prueba.

## 3. Problema grave: el S&P 600 anterior a diciembre de 2019 es ficticio

- La tabla de cambios del S&P 600 de Wikipedia empieza el **17-dic-2019**. Antes no hay ningún cambio registrado.
- `s0_universe.py` reconstruye hacia atrás desde la primera lista fiable deshaciendo cambios. Sin cambios que
  deshacer, la composición de 2015 a 2019 queda **congelada en 602 valores**: la lista de diciembre de 2019 copiada a
  todas las fechas anteriores. Comprobado: 0 entradas y 1 salida en cinco años, cuando el índice real cambia unas
  50-100 empresas al año.
- En la v2 no importaba, porque el universo S empezaba en 2020. **En la v3 sí:** el marco por empresa toma la primera
  pertenencia a cualquier índice, así que esas empresas entran en la muestra el 2-ene-2018.

Peso:

| | Empresas | Días afectados |
|---|---|---|
| 2018 | 538 de 1 520 | 36,2 % del año |
| 2019 | 542 de 1 535 | 36,2 % del año |
| Desarrollo, días con Flow negativo | — | **25,1 %** |

Qué sesgo introduce:

- **Supervivencia:** las 542 son las pequeñas que seguían en el S&P 600 a finales de 2019. Faltan las que estaban en
  el índice en 2018-2019 y salieron antes por quiebra, compra, caída o ascenso al S&P 400 (salvo que estuvieran
  también en otro índice). Precisamente las que más Flow negativo extremo habrían generado.
- **Información futura:** la pertenencia al S&P 600 exige beneficios positivos. Saber que una empresa estaba en el
  índice en diciembre de 2019 dice algo de cómo le fue en 2018-2019.
- **Efecto previsible:** en desarrollo, las pequeñas con Flow negativo parecerán más propensas a recuperarse de lo que
  son. Justo la dirección que más fácilmente se confundiría con una oportunidad.
- También contamina los cortes de H1 ya congelados en `data/v3_h1_frozen_cuts.json` (calculados sobre esa muestra).
  No usan resultados, así que se pueden recalcular sin romper nada.

Opciones (decisión tuya, **DECIDIR-D**):

| | Qué se hace | Efecto |
|---|---|---|
| **D1 (recomendada para no esperar)** | El S&P 600 solo cuenta como entrada en el marco desde el 17-dic-2019. Las pequeñas que solo eran del S&P 600 entran entonces. | Desarrollo 2018-2019 = solo empresas del S&P 500 y 400 (y las caídas desde ellos). Las pequeñas tienen un solo año de desarrollo (2020), que además es el más dudoso del S&P 600 (84-96 % de coincidencia). Probablemente obliga a alargar el desarrollo de las pequeñas hasta 2021 o 2022. |
| **D2 (recomendada si se acepta un día de trabajo)** | Reconstruir el S&P 600 de 2015-2019 con las carteras trimestrales del ETF iShares IJR (o SPDR SLY) publicadas en la SEC (formularios N-Q y N-CSR antes de 2019, N-PORT después). Cada fecha de cartera es un ancla. | Resuelve el problema de raíz y sirve igual para el S&P 400 de 2016-2020 (IJH o MDY), que tiene el error de composición del 6-12 % ya conocido (DECIDIR-B). No está comprobado que esas carteras estén completas y bien en EDGAR; sería lo primero que se mediría. |
| D3 | Sacar 2018-2019 del desarrollo para todas las empresas | Desarrollo de un solo año (2020): insuficiente. No la recomiendo. |

## 4. Problema menor: errores de escala que pasan el filtro de capitalización

- El filtro nuevo (`clean_pit`) valida cada presentación de la SEC contra las anteriores. Si la primera presentación
  aceptada es errónea, o dos erróneas seguidas coinciden, el error entra y se queda.
- Comparando con el filtro centrado: 1 352 días-empresa (0,04 %) de 20 empresas difieren más de ×10, y 136 días de 2
  empresas tienen capitalizaciones absurdas de más de 1 000 billones de dólares (HXL en 2024-2025 y AJG en 2020, ×10⁶).
  Hay errores en las dos direcciones: en unos casos falla el filtro nuevo (GRMN ×1 000, CCRN y CPK ÷1 000) y en otros
  falla el centrado en el primer dato de empresas recién creadas (CTVA, VTRS, AMCR, LIN).
- Efecto en el tamaño: 2 999 días cambian de franja (0,09 %), 1 230 de ellos con Flow negativo. Casi todo cae en
  «micro», que es la franja más pequeña, así que ahí pesa más.
- **Arreglo propuesto, sin decidir nada sobre resultados:** aplicar a todas las presentaciones la misma prueba de
  rotación plausible que ya se usa con la primera (liquidez / capitalización entre 10⁻⁵ y 0,5 al día). Lo haría al
  rehacer el panel por la decisión D.

## 5. Flow negativo en la muestra v3

| | Desarrollo 2018-2020 | Prueba 2021 → 17-sep-2026 |
|---|---|---|
| Días utilizables con Flow < 0 | 419 550 (38,3 %) | 918 488 (41,2 %) |
| [−5, 0) | 136 857 | 298 465 |
| [−10, −5) | 96 305 | 227 642 |
| [−15, −10) | 63 762 | 154 161 |
| [−20, −15) | 41 558 | 95 281 |
| [−30, −20) | 43 525 | 89 990 |
| < −30 | 37 543 | 52 949 |
| Operables en < −30 | 89,9 % | 87,4 % |
| Episodios bajo −10 / −20 / −30 | 18 299 / 10 438 / 5 390 | 39 950 / 22 615 / 10 571 |

- Episodio = primer día bajo el umbral tras ≥ 10 sesiones por encima.
- Episodios bajo −30 en desarrollo por tamaño: grande 747, mediana 1 514, pequeña 2 607, micro 525, sin
  capitalización 509. **Ojo:** las cifras de pequeñas de desarrollo incluyen el sesgo de §3.
- Señales con un evento corporativo en las 40 sesiones siguientes: 0,13 %. Se tratan en el resultado, no se excluyen.

## 6. Desenlaces de empresas que dejan de cotizar

618 series terminan dentro del marco.

| Categoría | Valor de salida conocido | Desconocido |
|---|---|---|
| Compra en efectivo | 172 | 0 (4 con términos incoherentes) |
| Compra en acciones | 58 | 12 (1 incoherente) |
| Compra mixta | 22 | 17 |
| Compra de tipo desconocido | — | 125 |
| Cambio de ticker | (se sigue la serie sucesora: 133) | — |
| Quiebra o liquidación | — | 7 |
| Fin sin causa identificada | — | 62 |
| Otros (fusión, escisión, exclusión) | — | 5 |

- Igual que en la v2: **todos los finales de 2016-2019 tienen valor desconocido** (Alpaca no da términos antes de
  2020). Desde 2020, la mayoría es conocido.
- Peso en las señales: un final de valor desconocido en las 40 sesiones siguientes afecta al **0,24 %** de los días
  con Flow negativo de desarrollo y al **0,08 %** de prueba. Se concentra en < −30 y en [−5, 0). Las cotas del
  preregistro (§4.2) lo cubren.

## 7. Diseño de H1 con la muestra v3

- Población: días utilizables con Flow < 0 de desarrollo, todas las tallas juntas: 419 550 días, 1 597 empresas.
- Cortes de quintil: w1 −7 / −4 / −2 / 0 y m1 −14 / −9 / −5 / −2 (más anchos que los del S&P 500 en la v2, porque
  ahora entran pequeñas y micro).
- Las 25 celdas tienen entre 5 477 y 35 903 días y al menos 1 333 empresas. Ninguna empresa pesa más del 0,4 % de
  una celda.
- Agrupando por mes: el 99,99 % de los días cae en celdas de 30 o más. Por tamaño también, salvo micro (56 %).
- Los retornos de 5 y 21 sesiones explican el 25,5 % de la varianza de R, como en la v2: R tiene variación propia.
- **Estos cortes se tendrán que recalcular** cuando se corrija §3 (no usan resultados, así que no hay problema en
  hacerlo).

## 8. Costes: el spread estimado no sirve para las grandes

- El estimador de Abdi-Ranaldo da una mediana de 0 en grandes varios años (2018, 2019, 2023): la fórmula se trunca en
  0 cuando el spread real es menor que su ruido. En empresas líquidas no informa.
- Donde sí informa: micro ~0,7-1,2 %, pequeñas ~0,2-0,6 %, liquidez < 1 M$/día ~1,1 %. Es coherente con el orden
  de los costes supuestos del preregistro (0,2 / 0,4 / 0,8 % ida y vuelta) y apunta a que en micro el 0,8 % puede
  quedarse corto. Se usa solo para contrastar, no para fijar costes.

## 9. Qué necesito para seguir

1. **DECIDIR-D** (§3): D1 (rápida) o D2 (comprobar las carteras del ETF en la SEC y, si están bien, rehacer S&P 600
   2015-2019 y S&P 400 2016-2020).
2. Las decisiones A, B y C del preregistro v2 cambian con la v3:
   - **A** (desarrollo desde 2018): la v3 ya lo aplica.
   - **B** (S&P 400 2016-2020) y **C** (S&P 600 2020): con el marco por empresa ya no se analiza por índice, pero la
     calidad de la composición sigue decidiendo qué empresas entran y cuándo. Con D2 se resolverían las dos.
3. Con eso, rehago el panel (incluido el arreglo de §4), recalculo los cortes de H1 y escribo el preregistro v3 para
   firmarlo. Hasta entonces, nada de rendimientos posteriores.
