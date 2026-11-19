# Flow negativo — viabilidad de D2 (carteras de ETF) y universo v4

Fecha: 2026-11-19. Equipo: LAWNMOWER (datos en `D:\backup market tracker\flow_negative_v1`).
**No se ha calculado ningún rendimiento posterior a una señal.** Prueba confirmatoria sin abrir. Producción sin tocar.
Sin commit.

Parte 1: la puerta de viabilidad que pediste (inventario, extracción, comparación, errores, intervalos, coste).
Parte 2: lo que se hizo tras tu decisión (opción 2: D1 + S&P 400 desde los ETF) y la validación del universo
resultante.

---

## Parte 1 — Viabilidad de D2

### 1.1 Inventario de documentos (EDGAR)

| Fondo | Gestor | Índice | Serie EDGAR | Carteras completas 2014-2019 | Desde 2019 |
|---|---|---|---|---|---|
| IJR | iShares | S&P 600 | S000004313 | 4 al año (N-Q jun/dic, N-CSRS sep, N-CSR mar) | NPORT-P |
| IJH | iShares | S&P 400 | S000004307 | 4 al año (ídem) | NPORT-P |
| VIOO | Vanguard | S&P 600 | S000030017 | 4 al año (N-Q may/nov, N-CSRS feb, N-CSR ago) | NPORT-P |
| IVOO | Vanguard | S&P 400 | S000030014 | 4 al año (ídem) | NPORT-P |
| SLY | SPDR | S&P 600 | S000006989 | 4 al año (N-CSRS dic, N-CSR jun, N-Q mar/sep) | NPORT-P |
| SPMD | SPDR | — | S000006986 | **No sirve:** hasta 2017 era el SPDR S&P 1000 y sigue el S&P 1000 (≈ 1 000 valores, 400 + 600 juntos) | — |
| MDY | SPDR | S&P 400 | UIT | No presenta N-Q/N-PORT con el mismo formato; no se usó | — |

- Combinando fondos: el S&P 600 tiene una cartera cada **31 días de mediana** (máximo 91) y el S&P 400 cada **45 días**
  (máximo 153). Detalle: `data/d2_inventory.json`; lista completa con URL y fecha exacta de cartera:
  `etf_holdings/inventory.csv` (fuera del repo).
- **Identificadores:** los N-Q, N-CSR y N-CSRS (hasta mediados de 2019) traen **solo el nombre** de la empresa, sin
  CUSIP ni ticker. Los NPORT-P traen ISIN (100 %) y CUSIP (97-100 %), pero ningún ticker.

### 1.2 Extracción de una muestra

Parser genérico para los tres gestores (`s2_etf_lib.py`). Cada cartera se valida sola: la suma de las posiciones
extraídas debe coincidir con el total de acciones que declara el propio documento.

- **Resultado:** coincidencia al dólar en todas las carteras de la muestra (p. ej. IJR 31-dic-2016: 603 posiciones,
  26 388 125 504 $ en los dos lados). Recuentos plausibles: 601-604 en el S&P 600, 399-404 en el S&P 400.
- **Trampas encontradas y resueltas:**
  - Un mismo documento contiene decenas de fondos, y el título puede venir partido por etiquetas HTML o con «®».
  - Los informes anuales de iShares traen primero un «Summary Schedule» (solo las mayores posiciones) y la cartera
    completa más adelante. Se elige la región completa.
  - Vanguard marca con «*» en una celda aparte.
  - El total a veces va dos filas más abajo.
- **Fallo de formato sin resolver (no hizo falta):** los informes semestral y anual de Vanguard (febrero y agosto)
  mezclan filas que no son posiciones o son resúmenes, y rompen los apóstrofos tipográficos. No pasan la validación del
  total y se descartan automáticamente; quedan sus N-Q (mayo y noviembre).

### 1.3 Enlace nombre → empresa

- Enlazar contra los nombres de Wikipedia **no sirve para el pasado:** Wikipedia guarda el nombre actual («Webster
  Bank», «Deckers Brands»), no el de 2016 («Webster Financial», «Deckers Outdoor»).
- Se enlaza contra la SEC: nombre actual y nombres anteriores con su vigencia, para 2 149 CIK del universo
  (`s2_sec_names.py`, `s2_link.py`). Exacto, o similitud ≥ 0,90 con margen; si no, se deja sin enlazar (nunca se
  adivina).
- **Comprobación independiente por precio:** el precio implícito de la posición (valor / acciones) frente a nuestro
  cierre de Alpaca de ese día. Coincide (±3 %) en el **98-99 %** de las empresas enlazadas
  (`data/d2_price_identity_check.json`).
  - Los pocos fallos son enlaces falsos reales: «Coherent Inc.» de 2016 enlazado a II-VI, que hoy se llama «Coherent
    Corp.»; o Regal Beloit y TCF, cuyo CIK cambió por fusión.
  - Por eso, en la parte 2 la comprobación de precio es **obligatoria** para aceptar una observación.

### 1.4 Comparación con composiciones conocidas (`data/d2_validation_cik.json`)

**V1. ETF frente a composición conocida** (años en que nuestra reconstrucción es fiable: S&P 600 2022-2023, S&P 400
2021-2023; 23 carteras):

| | S&P 600 (IJR, VIOO, SLY) | S&P 400 (IJH, IVOO) |
|---|---|---|
| Miembros del índice presentes en el ETF | 98,8-99,3 % | 97,7-98,5 % |
| Posiciones enlazadas que son miembros | 99,0-99,8 % | 98,2-99,8 % |
| Posiciones sin enlazar por cartera | 5-8 | 6-10 |
| ETF sin estar en el índice | 1-6 | 1-7 |
| Índice sin estar en el ETF | 4-7 | 6-9 |

Revisadas a mano, casi todas las diferencias son fallos de enlace por nombre (First BanCorp de Puerto Rico frente a
First Bancorp de Carolina del Norte, «HB Fuller Co», Cadence Bank tras su fusión), no diferencias reales de cartera.
**Error de tratar cada posición del ETF como miembro del índice: del orden del 0,5-1 %.** Los ETF replican el índice
completo, no por muestreo, en la práctica.

**V2. Acuerdo entre gestores en el periodo objetivo** (empresas enlazadas):

| Par | Comunes | Solo en uno / solo en otro |
|---|---|---|
| IJR / SLY, 31-dic-2015 | 447 | 0 / 1 |
| IJR / SLY, 31-dic-2016 | 472 | 1 / 1 |
| IJR / VIOO, dic / nov 2016 | 469 | 4 / 2 |
| IJR / SLY, 31-dic-2018 | 534 | 1 / 5 |
| IJH / IVOO, dic / nov 2015 | 375 | 3 / 3 |
| IJH / IVOO, dic / nov 2016 | 378 | 6 / 4 |
| IJH / IVOO, dic / nov 2018 | 390 | 2 / 8 |

Gestores distintos dan prácticamente la misma cartera. Con un mes de diferencia, las pocas diferencias son cambios
del índice ocurridos en medio.

**V2 bis. ETF frente a nuestras reconstrucciones:**
- S&P 400 de Wikipedia frente a IJH: 30-33 diferencias por lado en 2015-2016 (≈ 8 %), 9 en 2017, 12-26 en
  2018-2020. Confirma el error ya conocido de esa reconstrucción.
- S&P 600 «congelado» frente a IJR: en dic-2016, **194 de las 600 empresas** del congelado no estaban en el ETF; en
  dic-2018, 91. Confirma con datos externos que esa composición era ficticia.

**V3. Altas y bajas frente a los cambios oficiales** (S&P 600 2020-2022, tabla de cambios oficial con fecha efectiva;
35 pares de carteras consecutivas):
- El ETF recoge en su cartera siguiente el **98 % de las altas oficiales** (480 / 490) y el **94 % de las bajas**
  (462 / 491).
- A la inversa, el 91 % de las altas del ETF (480 / 529) y el 95 % de sus bajas (462 / 488) corresponden a un cambio
  oficial. El resto es ruido de enlace o casos especiales (escisiones mantenidas un tiempo, cambios de nombre).

### 1.5 Cobertura histórica alcanzable y empresas que faltan

- **S&P 400 (2015-2020):** casi todo el índice está en nuestro universo. Faltan pocas empresas y la cobertura es
  alta (ver parte 2).
- **S&P 600 (2015-2019): falta mucho.** En las carteras de IJR no tenemos el 21 % de las empresas en 2016 y el 11 % en
  2018. Son, precisamente, las que salieron del índice antes de finales de 2019 sin haber estado nunca en el S&P 400 o
  el 500.
  - Identificarlas exige nombre → CIK → ticker de la época → precios de Alpaca, para unas 260 empresas distintas.
    EDGAR identifica sin ambigüedad unas 180; el resto queda ambiguo o sin rastro.
  - **El ticker de una empresa desaparecida no se puede sacar de forma barata:**
    - la SEC no lo conserva;
    - la lista de valores retirados de Alpaca solo reconoce 20 de 262;
    - el XBRL del 10-K lo da en 4 de 11;
    - el texto del 10-K («under the symbol …»), en 8 de 9.
  - Sería factible, pero con un coste propio (descarga de cientos de 10-K, revisión manual de ambiguos) y nuevos
    riesgos de identidad. **Por decisión tuya no se hace.**

### 1.6 Regla para los intervalos sin datos (aplicada en la parte 2)

- **Observación:** la empresa está en una cartera fiable (total cuadrado, ≥ 90 % de nombres enlazados y precio
  verificado) en la fecha d.
- **Tramo de pertenencia:** desde la primera observación de una racha hasta la última. **No se atribuye pertenencia
  antes de la fecha observada** (la entrada real pudo ser hasta 1-5 meses antes; se pierde ese tramo, a propósito).
  Tras la última observación con ella, la fecha de baja es desconocida y el tramo se cierra en esa observación.
- **Estado:** confirmado (≥ 2 observaciones), inferido (una sola) y desconocido (fuera de cualquier observación).
- En la muestra por empresa solo importa la **fecha de entrada**: una empresa sigue en la muestra aunque salga del
  índice. Por eso la incertidumbre sobre la fecha de baja apenas afecta.

### 1.7 Coste y recursos (estimado y real)

| Pieza | Coste |
|---|---|
| Inventario de presentaciones (≈ 250 páginas índice) | ≈ 5 min |
| Carteras: ≈ 90 documentos, 1,5 GB en D: | ≈ 20 min de descarga |
| Nombres de la SEC del universo (2 149 CIK) + listado completo de EDGAR (40 MB) | ≈ 30 min |
| Pertenencia S&P 400 + panel v4 + validación + estadísticas | ≈ 1 h de máquina |
| **No hecho:** identificar ~260 empresas desaparecidas del S&P 600 | días de trabajo, con revisión manual |

Todo con fuentes públicas gratuitas (EDGAR, con el User-Agent autorizado) y precios de Alpaca ya descargados.

---

## Parte 2 — Opción 2 aplicada y universo v4

Decisión del 2026-11-19: **D1 + S&P 400 desde los ETF.** No se busca ninguna empresa desaparecida.

### 2.1 Qué cambia respecto a la v3

| Pieza | v3 | v4 |
|---|---|---|
| S&P 600 | Composición de dic-2019 copiada a 2015-2019 | Solo cuenta para entrar en la muestra desde el **17-dic-2019** (primer cambio oficial) |
| S&P 400, 2015-2020 | Reconstrucción de Wikipedia (error del 3-8 %) | **Carteras de IJH e IVOO** (38 fechas fiables), enlazadas por CIK y verificadas por precio |
| S&P 400, 2021 en adelante | Wikipedia | Igual (fiable) |
| Capitalización | Prueba de rotación plausible solo en la primera presentación | En **todas**, y una primera presentación que no se puede comprobar (empresa que aún no cotiza) no sirve de ancla |
| Sector | Del último tramo de Wikipedia | Igual, buscado también en la pertenencia sin recortar (es un dato fijo de la empresa) |

**Pertenencia al S&P 400 desde los ETF** (`s2_etf_membership.py` → `data/membership_etf_sp400.csv`):
- 38 carteras: 23 de IJH (trimestrales) y 15 de IVOO (mayo y noviembre). Se descartaron 8 de Vanguard (feb/ago) por no
  cuadrar el total.
- 629 empresas, 671 tramos: **627 confirmados** (≥ 2 observaciones) y **44 inferidos** (una sola).
- Precio: 13 913 enlaces verificados y 131 rechazados por no coincidir (enlaces falsos).
- Segundo enlace por ticker para empresas sin CIK o con CIK erróneo en nuestro mapa: recupera 33 empresas, todas
  verificadas por precio. Son sobre todo absorbidas en 2016-2018 (Panera, Kate Spade, Cabela's, FEI…), justo las que
  importan para el sesgo de supervivencia.

### 2.2 Validación del universo v4 (`s3_validate_v4.py` → `data/v4_validation.json`)

| Comprobación | Resultado |
|---|---|
| Días con pertenencia al S&P 600 antes del 17-dic-2019 | **0** |
| Panel desde 2021 | **Mismas empresas y mismos días que la v3.** Solo cambia la capitalización donde se corrigió |
| Miembros del S&P 400 por fin de mes en el panel, 2016-2020 | 377-393, mediana 386. Los que faltan hasta ~400 no tienen serie de precios, no se pudieron enlazar o no pasaron la verificación de precio |
| Empresas que salen del todo | 20. Casi todas absorbidas en 2016-2017, con solo 1 408 días desde 2018 (despreciable); Vitamin Shoppe sale con razón (era del S&P 600 congelado) |
| Capitalizaciones absurdas (≥ 1 000 billones $) | 136 días → **0**. Por encima de 5 billones solo quedan Apple y Nvidia (reales) |
| Discrepancias > ×10 con la versión retrospectiva | 20 → **8 empresas**; en las de más peso (CPK, CCRN, PNM) la errónea es la retrospectiva |
| Cobertura de capitalización | 90,4 % (sin pérdida) |
| Sector conocido | 99,75 % de los días; 100 % en 2018-2019 |

El contador de presentaciones rechazadas sube a 33 038: son presentaciones anteriores a 2015, sin precio con el que
comprobarlas. No cambian ninguna capitalización del periodo del panel.

### 2.3 La muestra v4

| Año | Días-empresa | Empresas | Ya fuera de todo índice | Con capitalización |
|---|---|---|---|---|
| 2018 | 232 518 | 972 | 4,7 % | 89,1 % |
| 2019 | 242 978 | 1 531 | 5,7 % | 89,7 % |
| 2020 | 381 233 | 1 555 | 1,3 % | 90,8 % |
| 2021-2026 | sin cambios respecto a la v3 | | | |

- 2018 pierde ~550 empresas frente a la v3: las pequeñas que solo eran del S&P 600, que ahora entran el 17-dic-2019.
- **Desarrollo (2018-2020), días con Flow negativo:** 311 135 (en la v3, 419 550). Episodios bajo −10 / −20 / −30:
  13 797 / 7 786 / 4 086.
- **Episodios bajo −30 en desarrollo por tamaño:** grande 746, mediana 1 381, pequeña 1 652, micro 386, sin
  capitalización 387.
- Desenlaces: 598 series terminan dentro del marco. Un final de valor desconocido en las 40 sesiones siguientes
  afecta al 0,31 % de los días con Flow negativo de desarrollo y al 0,08 % de los de prueba.

### 2.4 Cortes de H1 recalculados (`data/v4_h1_frozen_cuts.json`)

Calculados solo tras validar el universo, sobre los días con Flow negativo del desarrollo (311 135 días, 1 589
empresas). Sin rendimientos.

- Quintiles: w1 −7 / −4 / −2 / 0 (igual que en la v3) y m1 −15 / −9 / −5 / −2 (en la v3, −14).
- Las 25 celdas tienen entre 4 197 y 27 765 días y al menos 1 189 empresas cada una. Ninguna empresa pesa más del
  0,6 % de una celda.
- Agrupando por mes: el 99,8 % de los días cae en celdas de 30 o más. Por tamaño: grandes 96 %, medianas 98 %,
  pequeñas 90 % y **micro solo 63 %** (H1 no es fiable en micro).
- Los retornos de 5 y 21 sesiones explican el 26,6 % de la varianza de R: R sigue teniendo variación propia.
- Los cortes de la v3 (`data/v3_h1_frozen_cuts.json`) quedan **obsoletos**: no usarlos.

### 2.5 Lo que esto implica para el preregistro (decisiones tuyas)

1. **Las pequeñas solo tienen un año de desarrollo, 2020,** y es el año del desplome del COVID. En 2018-2019 apenas
   hay pequeñas: solo las que han caído desde el S&P 400 o el 500. Cualquier conclusión de desarrollo sobre pequeñas
   dependería de un único régimen extremo.
   - Opción a: alargar el desarrollo de las pequeñas hasta 2021 o 2022 (como ya proponía DECIDIR-C) y empezar su
     prueba después.
   - Opción b: un único corte para todos y tratar las pequeñas de desarrollo como «insuficiente» si no llegan al
     mínimo de episodios y semanas del preregistro (§5).
2. **Lo que queda fuera:** las pequeñas del S&P 600 de 2015-2019 que nunca estuvieron en otro índice. El sesgo que
   introducía la v3 desaparece, a cambio de no tener esas empresas en desarrollo.
3. Con esto, DECIDIR-A (desarrollo desde 2018) y DECIDIR-B (S&P 400 2016-2020) quedan resueltas; DECIDIR-C se
   convierte en el punto 1.

### 2.6 Ficheros

- Código nuevo o cambiado:
  - `s2_etf_lib.py`, `s2_etf_inventory.py`, `s2_etf_sample.py`, `s2_etf_validate.py`, `s2_etf_validate_cik.py`,
    `s2_etf_gap.py`, `s2_sec_names.py`, `s2_link.py`, `s2_etf_membership.py`, `s3_validate_v4.py`;
  - `s1_panel.py` y `s1_stats.py`, ahora con `FN_TAG=v4`; sin la etiqueta reproducen la v3.
- En el repo (agregados y pertenencia pública):
  - `data/d2_*.json`, `data/membership_etf_sp400.csv`;
  - `data/v4_*.json`, `data/terminal_events_v4.csv`.
- Fuera del repo, en D:: `etf_holdings/` (documentos en bruto y carteras extraídas), `sec/names_universe.csv`,
  `sec/cik-lookup-data.txt` y `work/panel_v4.parquet`, `companies_v4.csv` y los registros `*_v4.log`.
