# Preregistro — Flow Score negativo: caracterización y valor incremental (v3)

**Estado: FIRMADO** (2026-11-20). Hashes en §13.1.
- Sustituye a la v2 (`wiki/PREREGISTRO_FLOW_NEGATIVO_V2.md`), que se escribió para el universo por índices.
- Incorpora la muestra por empresa (`research/flow_negative_v1/ETAPA0_V3_INFORME.md`) y el universo v4
  (`research/flow_negative_v1/D2_VIABILIDAD_Y_V4.md`).
- Las decisiones A, B, C y D y los cuatro puntos de §12.2 están resueltos (confirmados por el usuario el 2026-11-20).
- Congelado con SHA-256 (§13.1). La etapa 1 necesita además autorización explícita antes de lanzarse.

Lo que cambia frente a la v2 está en §14.

## 0. Pregunta, objetivo y lenguaje

¿Qué pasa después de cada nivel negativo del Flow Score? ¿Cambia según el tamaño, la liquidez y el régimen? ¿Aporta
el Flow información sobre lo que viene después, más allá de la caída previa del precio?

Cada nivel y segmento acaba en una de tres lecturas:
- **reversión** (posible oportunidad);
- **continuación bajista** (peligro);
- **descripción de una caída ya producida** (nada más).

No se busca una estrategia ni un indicador nuevo, ni se toca producción.

Los componentes del Flow distintos del momentum (RSI, MACD, ATR, Koncorde, distancia al máximo) son transformaciones
del precio y, en parte, del volumen. **No son flujos de capital.** Si aportan algo, la conclusión será que contienen
información predictiva adicional a los retornos de 5 y 21 sesiones, no que exista acumulación institucional.

Principio rector: vale más una caracterización correcta que muestre que el Flow negativo no aporta nada, que una
oportunidad aparente fabricada por sesgos, costes irreales o sobreajuste.

## 1. Etapas

| Etapa | Qué hace | Datos | Decide |
|---|---|---|---|
| 0 — Construcción | Hecha: v3 + v4 | Sin resultados posteriores | La validez de los datos |
| 1 — Caracterización | Curva completa del Flow negativo | **Solo desarrollo** (§2) | Elige como mucho 4 celdas para la etapa 2 y estima los parámetros de M0/M1 |
| 2 — Validación | H1 y las celdas elegidas, **una sola vez** | **Prueba** | El veredicto |

- Las hipótesis y todos los parámetros de la etapa 2 se congelan con SHA-256 al terminar la etapa 1, antes de consultar
  ningún dato de prueba.
- La caracterización del periodo completo se publica después de la etapa 2, solo como descripción.
- **Orden dentro de la etapa 1** (por el desarrollo más largo de las pequeñas, §2.2):
  1. Se calcula y se mira solo 2018-2020, de todas las tallas.
  2. Se congela todo lo que afecta a grandes, medianas y «sin capitalización»: celdas elegidas y parámetros de M0/M1.
  3. Solo entonces se calculan los días de 2021-2022 de las pequeñas y las micro. Esos días son la prueba de las
     demás tallas. Mirarlos antes permitiría elegir celdas de grandes y medianas sabiendo cómo se comportó el mercado
     en 2021-2022.

## 2. Muestra y periodos

### 2.1 Unidad: la empresa

- Una empresa entra en la muestra el **primer día en que pertenece a cualquiera de los tres índices** (S&P 500, 400 o
  600). Sigue dentro aunque salga del índice, hasta que deja de cotizar.
- No entra su historia anterior a esa primera pertenencia: elegirla porque más tarde entró en un índice sería
  seleccionar por su éxito posterior.
- Composición (universo v4):
  - S&P 500: Wikipedia, instantáneas anuales y tabla de cambios.
  - S&P 400 de 2015-2020: carteras de los ETF IJH e IVOO publicadas en la SEC (`data/membership_etf_sp400.csv`).
    Desde 2021, Wikipedia.
  - S&P 600: solo cuenta para entrar en la muestra desde el **17-dic-2019**, primer cambio oficial registrado.
- Resultado: 2 083 empresas desde 2018.
- **Lo que no representa.** Son empresas que han pertenecido a un índice S&P. En 2018-2019 las pequeñas son solo las
  que han caído desde el S&P 500 o el 400. Faltan las pequeñas del S&P 600 de 2015-2019 que nunca estuvieron en otro
  índice (unas 260 empresas, la mayoría desaparecidas; decisión del 2026-11-19 de no buscarlas).

### 2.2 Periodos por talla

La talla es la de la señal: la capitalización de la empresa el día t (§4.7). Una misma empresa puede tener días de
desarrollo como pequeña y días de prueba como mediana.

| Talla en t | Desarrollo | Prueba |
|---|---|---|
| Grande (≥ 10 000 M$) | 2018-01-02 → 2020-12-31 | 2021-01-04 → fin |
| Mediana (2 000-10 000 M$) | 2018-01-02 → 2020-12-31 | 2021-01-04 → fin |
| **Pequeña (300-2 000 M$)** | **2018-01-02 → 2022-12-30** | **2023-01-03 → fin** |
| **Micro (< 300 M$)** | **2018-01-02 → 2022-12-30** | **2023-01-03 → fin** |
| Sin capitalización | 2018-01-02 → 2020-12-31 | 2021-01-04 → fin |
| P — propio (Portfolio Tracker) | — | — (solo descriptivo) |

- **Fin** = última señal con 40 sesiones de datos (datos congelados a 2026-11-13): **2026-09-17**.
- Por qué el desarrollo de las pequeñas es más largo (decisión del 2026-11-19): en 2018-2019 solo hay pequeñas caídas
  desde otros índices, y el único año con pequeñas del S&P 600 es 2020, el del COVID. Un desarrollo de un único año
  extremo no sirve para elegir nada. Con 2021 (alcista) y 2022 (bajista) hay más de un régimen.
- **Las micro siguen a las pequeñas** porque tienen el mismo problema en 2018-2019 (confirmado 2026-11-20).
- Señales disponibles, contadas sin ningún rendimiento posterior (episodios, §4.5):

  | Talla | X | Desarrollo | Prueba |
  |---|---|---|---|
  | Pequeña | −20 | ≈ 5 100 | ≈ 4 300 |
  | Pequeña | −30 | ≈ 3 000 | ≈ 2 300 |
  | Micro | −30 | ≈ 600 | ≈ 770 |

  - Desarrollo: 2018-2020 de la v4 más 2021-2022.
  - Las cifras de 2021-2026 salen del panel v3, idéntico al v4 desde 2021 salvo las capitalizaciones corregidas
    (0,1 % de los días). Son una aproximación para dimensionar.
  - Las de grandes y medianas no cambian: `data/v4_sample.json`.

## 3. Datos

- **Precios:** fuente única Alpaca, barras diarias SIP en bruto.
  - Splits y dividendos se aplican con la regla de coherencia con el precio (enmienda 7 de microestructura).
- **Identidad por épocas:**
  - Un ticker reutilizado, o una empresa que quiebra y reaparece, da series distintas.
  - Se usan todas las épocas de identidad que devuelve Alpaca, no solo la última.
  - Los cambios de ticker se enlazan por Alpaca y, antes de 2020, por el CIK de la SEC.
  - Las series duplicadas (mismos precios) se fusionan.
  - Las clases de acciones se agrupan por CIK y correlación ≥ 0,9.
- **Flow:** réplica de producción, verificada idéntica en 3 000 filas. Completo desde el 29-dic-2017 (Koncorde
  semanal de 100 semanas).
- **Capitalización, sin mirar al futuro (`mcap_pit`):**
  - Acciones de la SEC por fecha de presentación (≤ t, ≤ 400 días), corregidas por splits.
  - Cada presentación se valida contra las anteriores y con una prueba de rotación plausible (liquidez /
    capitalización entre 10⁻⁵ y 0,5 al día).
  - La versión centrada (`mcap_retro`) queda como sensibilidad: las tallas coinciden en el 99,9 % de los días.
- **Sector:**
  - GICS de Wikipedia, de la última instantánea que lista la empresa.
  - Si falta, código SIC de la SEC con la tabla SIC→GICS, solo cuando la correspondencia es inequívoca
    (`data/sic_gics_rules.csv`).
  - Sector conocido en el 99,75 % de los días.
- Los datos con licencia de Alpaca y el panel van fuera del repo. En el repo: código, composición y agregados.

## 4. Definiciones

### 4.1 Señal y ejecución
- **Señal:** Flow_t con el cierre de t.
- **Días utilizables:** Flow completo y sin evento corporativo en [t − 259, t]. Un evento en (t, t + 40] no excluye la
  señal: se marca y se trata en el resultado (§4.2).
- **Entrada:** apertura de t+1. Sensibilidad: cierre de t+1.
- **Plazos:** 5, 10, 20 y 40 sesiones. **El principal es 20.**
- **Retorno** = cierre de t+H (rendimiento total) / entrada − 1.

### 4.2 Resultados terminales (detalle en `EMPRESAS_DESAPARECIDAS.md`, §5)
- **Valor de salida conocido:** ese valor en la fecha efectiva y después 0 % hasta el plazo.
- **Cambio de ticker:** se sigue la serie sucesora.
- **Adquisición sin valor conocido:** último cierre. Cotas: × e^−0,05 y × e^+0,05 (percentil 90 del error medido en
  2020+).
- **Quiebra, exclusión/OTC, escisión, términos incoherentes y fin desconocido:** último cierre. **Cotas: 0 y último
  cierre.**
- Cada conclusión debe mantenerse con las dos cotas.
- Toda celda con más del 1 % de episodios de valor desconocido se marca.
- Se publica además una versión que excluye esos episodios. Nada se excluye en silencio.
- Peso esperado: un final de valor desconocido en las 40 sesiones siguientes afecta al 0,31 % de los días con Flow
  negativo de 2018-2020 y al 0,08 % de los de 2021 en adelante.

### 4.3 Medidas por señal
- Retorno bruto.
- **Exceso frente a su talla:** media de todas las empresas utilizables de la misma talla ese día, de cualquier nivel
  de Flow, con la misma entrada y plazo. **Es la medida principal.**
- Exceso frente a SPY y frente a la mediana de su sector (misma muestra, misma fecha, al menos 5 pares).
- MFE y MAE: máximo y mínimo intradía entre t+1 y t+H frente a la entrada.
- **Nuevo mínimo:** el mínimo entre t+1 y t+H queda por debajo del mínimo de las 20 sesiones hasta t.
- Cola: percentiles 5 y 10; P(retorno ≤ −10 %) y P(≤ −20 %).
- Por celda: media, mediana, media recortada al 1 % y % positivo.

### 4.4 Niveles de Flow (fijados)
- **Absolutos:** Z0 [−5, 0) · Z1 [−10, −5) · Z2 [−15, −10) · Z3 [−20, −15) · Z4 [−30, −20) · Z5 < −30.
  Referencias: todos los días, Flow ≥ 0 y [0, 4).
- **Percentil entre empresas** (misma talla y día): ≤ 1 % · (1, 5] · (5, 10] · (10, 25] · (25, 50].
- **Percentil propio** (frente a las 252 sesiones anteriores de la empresa, incluida t): mismas franjas.

### 4.5 Estados y episodios
- **Estados:** todos los días en un nivel. Nunca se tratan como independientes (§9).
- **Episodios:** para X ∈ {−10, −20, −30}, primer día con Flow < X tras ≥ 10 sesiones con Flow ≥ X. Es la población
  principal para cualquier lectura de «señal». La talla del episodio es la del día t.

### 4.6 Poblaciones
- **A. Descriptiva:** todos los días utilizables, sin filtro de precio ni de liquidez. Sirve para el fenómeno.
- **B. Operable:** precio en bruto ≥ 3 $ y mediana de precio × volumen de las 20 sesiones hasta t ≥ 1 M$. Sirve para
  la utilidad práctica.
- Ambas se muestran siempre en la caracterización, con lo que elimina el filtro por talla. En micro, solo la mitad de
  los días con Flow negativo son operables.
- Los resultados de A nunca se presentan como ejecutables. Costes y oportunidades, solo en B.

### 4.7 Segmentos
- **Tamaño (clasificación principal):** capitalización `mcap_pit` el día t.
  - Grande ≥ 10 000 M$ · mediana 2 000-10 000 M$ · pequeña 300-2 000 M$ · micro < 300 M$.
  - «Sin capitalización»: el 9-10 % de los días, sin acciones de la SEC válidas. Se analiza como grupo propio y se
    marca.
- **Índice en t (secundario):** S&P 500 / 400 / 600 / ya fuera de todo índice. Solo descriptivo.
- **Liquidez:** quintiles de la mediana de precio × volumen de 20 sesiones, dentro de la talla y el día. Es una
  dimensión independiente de la capitalización.
- **Rotación:** tercios de liquidez / capitalización; «no evaluable» sin capitalización.
- **Régimen** (SPY en t):
  - alcista = cierre ≥ SMA200, cierre ≥ SMA50 y SMA50 ≥ SMA200;
  - bajista = cierre < SMA200;
  - lateral = el resto.
- **Tipo de caída — regla jerárquica y excluyente**, con retornos de 21 sesiones hasta t, evaluada en este orden:
  1. **General:** SPY ≤ −5 % o mediana de su sector ≤ −8 %.
  2. **Idiosincrática:** empresa − mediana de su sector ≤ −10 pp y SPY > −3 %.
  3. **Mixta:** el resto.
  - Si el sector tiene menos de 5 pares ese día, se usa SPY en lugar del sector y la observación queda marcada.
- **Sector:** §3. Se publica qué parte de cada celda usa SIC.

## 5. Etapa 1 — caracterización (solo desarrollo)

- **Contenido:**
  - Tablas por talla × nivel (absoluto y percentiles) × plazo, para estados y episodios, poblaciones A y B, con todas
    las medidas de §4.3.
  - Cruces con liquidez, rotación, régimen, tipo de caída e índice en t.
  - Curvas de exceso, MAE, nuevo mínimo y cola izquierda frente al nivel.
- Celda con menos de 100 episodios o menos de 30 semanas distintas: «insuficiente», no se interpreta.
- **Parámetros que se estiman aquí y se congelan:** las medias de exceso a 20 sesiones de las 25 celdas de retornos
  (M0) y los tres efectos de tercio de R (M1), con la población A del desarrollo de cada talla (§6.2).
- **Elección para la etapa 2.** Como mucho 4 celdas en total (talla × umbral de episodio × plazo de 20 o 40 ×
  régimen o «todos»): las de mayor |t| que cumplan a la vez:
  - |t| ≥ 2,5 con el error de §9;
  - al menos 100 episodios;
  - mismo signo en las dos mitades del desarrollo:
    - grandes, medianas y sin capitalización: 2018-01 → 2019-06 y 2019-07 → 2020-12;
    - pequeñas y micro: 2018-2020 y 2021-2022;
  - mismo signo con las dos cotas de §4.2;
  - menos del 1 % de episodios de valor desconocido.
- La elección se hace en dos tandas (§1): primero grandes, medianas y sin capitalización (congeladas con su hash);
  después pequeñas y micro, con las plazas que queden.
- Si ninguna celda cumple, la etapa 2 se limita a H1.
- La etapa 1 no produce ninguna regla operativa, aunque algo parezca claro.

## 6. H1 — ¿el resto del Flow añade algo a la caída previa?

**Pregunta:** entre empresas con caídas parecidas a 5 y 21 sesiones, ¿los demás componentes del Flow permiten
distinguir resultados futuros?

### 6.1 Variables y celdas (congeladas sin resultados: `research/flow_negative_v1/data/v4_h1_frozen_cuts.json`)
- **w1 y m1:** retornos de 5 y 21 sesiones, redondeados como en el Flow.
- **R = Flow − 2·(0,6·w1 + 0,4·m1):** el resto, que contiene RSI, MACD, ATR, Koncorde y distancia al máximo. Los
  retornos explican el 26,6 % de la varianza de R: R tiene variación propia.
- **Población:** días utilizables con Flow < 0 (población A; la B como sensibilidad).
- **Cortes 5 × 5:** quintiles de 2018-2020 con todas las tallas juntas: w1 −7 / −4 / −2 / 0 y m1 −15 / −9 / −5 / −2.
  Se usan los mismos en todas las tallas y en todos los periodos.
  - Los cortes de la v2 (`h1_frozen_cuts.json`) y de la v3 (`v3_h1_frozen_cuts.json`) quedan **obsoletos**.
- **Tercios de R dentro de cada una de las 25 celdas** (c1 y c2, del mismo fichero). R bajo = R ≤ c1; R alto = R ≥
  c2. Si c1 = c2, R bajo = R < c1 y R alto = R > c1.
- **Celda de cálculo:** (talla, mes natural, quintil de w1, quintil de m1). Es válida si R bajo y R alto tienen cada
  uno al menos 10 observaciones ese mes.

### 6.2 Estadísticos (fuera de muestra, en la prueba de cada talla)
1. **Diferencia controlada D.** En cada celda válida:
   - d_c = exceso medio a 20 sesiones de R alto − exceso medio de R bajo;
   - D_mes = media de d_c ponderada por el número de observaciones de la celda;
   - D = media de D_mes en los meses de prueba.
2. **Comparación de modelos.**
   - M0 = media de exceso de desarrollo de la celda 5 × 5 de la empresa (solo retornos previos).
   - M1 = M0 + efecto de su tercio de R (bajo, medio, alto), estimado en desarrollo con todas las celdas de la talla
     juntas.
   - En cada día de prueba con al menos 30 observaciones de la talla: IC_t = correlación de Spearman entre la
     predicción y el exceso realizado.
   - ΔIC_t = IC_t(M1) − IC_t(M0). Se usa la media de ΔIC.

### 6.3 Contrastes y criterio
- **Tres contrastes:** grandes, medianas y pequeñas.
- Micro y «sin capitalización» solo se describen, sin veredicto: en 2018-2020 solo el 63 % y el 79 % de sus
  observaciones caen en celdas mensuales de 30 o más.
- **Confirmado (en cada talla por separado) si se cumplen las dos:**
  - |D| ≥ 0,5 pp con su intervalo sin el 0;
  - media de ΔIC > 0 con su intervalo sin el 0.
- Intervalos al nivel corregido de §9.
- Si se cumple una y no la otra: «evidencia parcial», no confirmado.
- **Signo:** D > 0 significa que, con la misma caída, mejor estado técnico precede a mejor resultado; D < 0, lo
  contrario.
- Si no se confirma en ninguna talla, lo que muestre la etapa 1 describe la caída ya producida.
- Sensibilidades publicadas (no deciden):
  - población B;
  - plazos de 5, 10 y 40;
  - cotas terminales;
  - tallas con `mcap_retro`;
  - pequeñas con desarrollo solo 2018-2020 y prueba desde 2021;
  - celdas por día de 5 × 5 con mínimo de 10.

## 7. Celdas elegidas en la etapa 1 (H2-H5)

- **Se confirma** si en la prueba de su talla: mismo signo, |exceso| ≥ 0,5 pp × (H/20)^0,5 e intervalo sin el 0.
- **Atribución al Flow** (necesaria para llamarla oportunidad o peligro): frente a días sin esa señal de la misma
  celda (talla, mes, quintil w1, quintil m1), la diferencia mantiene el signo con el intervalo sin el 0. Si no, se
  clasifica como «describe la caída previa».

## 8. Clasificación final de cada nivel y segmento

| Lectura | Requisitos |
|---|---|
| **Reversión (posible oportunidad)** | Exceso positivo confirmado + atribución + exceso neto de costes > 0 en la población B con los costes base |
| **Continuación bajista (peligro)** | Exceso negativo confirmado, o más nuevos mínimos o peor percentil 10 que los días de su misma celda de retornos, con intervalo sin el 0 |
| **Descripción de la caída** | Todo lo demás, incluido lo que explican w1 y m1 |

- Cualquier lectura exige mantenerse con las dos cotas terminales.
- Significación y relevancia se informan por separado: un efecto significativo por debajo de 0,5 pp se publica como
  «estadísticamente distinto de cero, sin relevancia económica».
- **Costes (supuestos, no observados), ida y vuelta:** grande 0,2 % · mediana 0,4 % · pequeña 0,8 % · **micro
  1,5 %** · sin capitalización 0,8 % (confirmado 2026-11-20).
  - Sensibilidades ×2 y ×3.
  - El spread estimado (Abdi-Ranaldo) solo sirve de contraste: micro ~0,7-1,2 %, pequeñas ~0,2-0,6 %; en grandes se
    trunca en 0 y no informa.
  - Se advierte que en los segmentos menos líquidos el coste real puede superar cualquiera de estos.
- Se distinguen siempre: retorno bruto (descriptivo), exceso frente a talla y sector, y neto de costes (solo
  población B).

## 9. Inferencia

- Para cada celda se forma la serie diaria de su exceso medio (una cifra por día). Así la correlación transversal de
  una crisis cuenta una vez por día, no una por empresa.
- Error de Newey-West con retardo igual al plazo.
- **Bootstrap por bloques de 60 sesiones (principal, 2 000 réplicas)**; sensibilidades de 20 y 120 sesiones.
- Para D (serie mensual): bloques de 3 meses; sensibilidades de 1 y 6.
- Se decide con el principal. Si alguna sensibilidad mete el 0 en el intervalo, la celda se marca como «frágil» (no
  cambia el veredicto).
- **Comparaciones múltiples:** Bonferroni sobre H1 (3 tallas) + las celdas elegidas (como mucho 7 contrastes). Nivel
  por contraste = 0,05 / número de contrastes.

## 10. Trayectoria previa del Flow (sin hipótesis)

Las series guardan el Flow diario completo de cada empresa. Más adelante se puede estudiar si llega a −20
deteriorándose deprisa o tras semanas estable. **En v3 no es hipótesis ni filtro.**

## 11. Universo propio (P) y salidas

- **P:** mismas tablas de la etapa 1 con el Flow tal como se capturó (desde el 20-ago-2026). Van en un apartado aparte,
  sin intervalos que se lean como prueba. Nunca fija nada.
- **Salidas:** código y agregados en `research/flow_negative_v1/`. Precios, Flow por empresa y día y
  capitalizaciones, fuera del repo.

## 12. Decisiones

### 12.1 Resueltas
| | Problema | Decisión |
|---|---|---|
| A | Flow completo solo desde el 29-dic-2017 | Señales desde 2018-01-02 |
| B | S&P 400 2016-2020 de Wikipedia con un 3-8 % de error | Carteras de IJH e IVOO en la SEC (v4) |
| C / D | S&P 600 anterior a dic-2019 ficticio; las pequeñas solo tienen 2020 de desarrollo | El S&P 600 cuenta solo desde el 17-dic-2019 (D1) y el desarrollo de las pequeñas se alarga a 2022 (§2.2; decisión del 2026-11-19) |
| — | Unidad de análisis | Empresa, con talla por capitalización en t (2026-11-18) |
| — | Empresas desaparecidas del S&P 600 de 2015-2019 | No se buscan (2026-11-19) |

### 12.2 Puntos nuevos de la v3 (confirmados por el usuario el 2026-11-20)
1. **Las micro siguen el periodo de las pequeñas** (desarrollo hasta 2022). Alternativa: dejarlas con 2018-2020.
2. **H1 con tres veredictos** (grandes, medianas, pequeñas). Micro y «sin capitalización», solo descriptivas.
3. **Coste supuesto de las micro: 1,5 %** ida y vuelta (antes no tenían uno propio). «Sin capitalización»: 0,8 %.
4. **Etapa 1 en dos tandas** (§1), para que los días de 2021-2022 de las pequeñas no influyan en la elección de celdas
   de grandes y medianas.

## 13. Congelación

Al firmar, se guardará el SHA-256 de:
1. Este documento (versión final).
2. El código de las etapas 0, v3 y v4, en `research/flow_negative_v1/`:
   - `fn_config.py`, `s0_*.py`;
   - `s1_extend.py`, `s1_sic.py`, `s1_panel.py`, `s1_stats.py`;
   - `s2_*.py`, `s3_validate_v4.py`.
3. Los datos congelados del repo:
   - `data/membership.csv`, `data/changes.csv`, `data/membership_etf_sp400.csv`;
   - `data/terminal_events_v4.csv`, `data/sic_gics_rules.csv`, `data/sic_sector_by_cik.csv`;
   - `data/v4_h1_frozen_cuts.json`.
4. Los datos de fuera del repo, con su hash publicado en el repo: `work/panel_v4.parquet`, `work/companies_v4.csv` y
   `work/company_links_v4.csv`. Viven en el disco externo (`D:\backup market tracker\flow_negative_v1` en LAWNMOWER;
   firmado el 2026-11-20 desde DESPACHOB con el mismo disco montado en E:).

Al terminar cada tanda de la etapa 1, y antes de tocar la prueba, se congela un archivo con las celdas elegidas y los
parámetros de M0/M1 de esa tanda.

Código adaptado a periodos por talla antes de firmar (entra en el hash). `fn_config.py` define `DEV_END_BY_SIZE`,
`TEST_START_BY_SIZE`, `period_for()`, los costes por talla y `dev_mask(df, tanda)`. Esta última nunca incluye días de
prueba, limita la tanda 1 a 2018-2020 y bloquea la tanda 2 hasta que exista `data/etapa1_tanda1_frozen.json`.
`DEV_END` (por índice) queda solo para reproducir la etapa 0 v3.

### 13.1 Hashes (firmado 2026-11-20)

Generados con `research/flow_negative_v1/s3_freeze_v3.py` (repo: saltos de línea normalizados a LF; externos: bytes).
El hash de este documento está en `research/flow_negative_v1/data/preregistro_v3_freeze.json`. Comprobación:
`py -3 s3_freeze_v3.py --verify`.

| Tipo | Fichero | SHA-256 |
|---|---|---|
| código | `research/flow_negative_v1/fn_config.py` | `ab8ab08272a20b246727a12ba6ee9730d0be04839ffc4730c3ad4586ff8cc006` |
| código | `research/flow_negative_v1/s3_freeze_v3.py` | `8e714503e321be1d26edef559a1bbd3bd15095ac18cf3ef4f0d2cda0ae042351` |
| código | `research/flow_negative_v1/s0_coverage.py` | `831f5c4379738811b44334c7c429b51c9c537d085d89831f57351419540c27b0` |
| código | `research/flow_negative_v1/s0_h1_cuts.py` | `70b1fb059e83a762192436ba9bd09fdbe594d113225375ae131466d16e4183cb` |
| código | `research/flow_negative_v1/s0_h1_design.py` | `89a8e39a15c0257553fce631f38f040f7f5e513ba198625d07501928d2470281` |
| código | `research/flow_negative_v1/s0_parity.py` | `597480d5308d2c84f94dc18d5c8a7bdbc307b734701dd81f97faa2b393a5d302` |
| código | `research/flow_negative_v1/s0_prices.py` | `8725c750dd43c2cc74c55f2dd0ba90738956500e7451fc5d2d226802b7abe0ad` |
| código | `research/flow_negative_v1/s0_prices_retry_empty.py` | `ae5e8fcc9d06e6931a7b7417fdb13c34c724f780dc04675962d07ecffb35f0f1` |
| código | `research/flow_negative_v1/s0_sec.py` | `c020dcb6653c32427c0b80ad37e0f0c9cae4d316ec7b3d0ff1cb17d48176e2b4` |
| código | `research/flow_negative_v1/s0_series.py` | `92acfa0c0b96d7018823a9a2091d4f0d82567a3dd448520a491e6771a2b85935` |
| código | `research/flow_negative_v1/s0_terminal.py` | `1a7063d1061534354d8332e1776d06430cfde4eb6e09bd5c490764003130dcc7` |
| código | `research/flow_negative_v1/s0_terminal_impact.py` | `4ce976b49fa2c48de3aed6284cad66af28ec8415359efd91dcb25645f2fb9eed` |
| código | `research/flow_negative_v1/s0_universe.py` | `d276809e8aae192d9582ea5bd71ae8abe62087d96df8761423e1db4bb04a8a9a` |
| código | `research/flow_negative_v1/s0_wiki_monthly.py` | `50c14ce33d74f25a26b80e31f97499b8ec14141b5dd43e40b16a1eb9ad8103ee` |
| código | `research/flow_negative_v1/s1_extend.py` | `1396f975723e013846787ac3a2c243fdee80ff65e18b960fe2ef7bdbf0d39e0f` |
| código | `research/flow_negative_v1/s1_sic.py` | `9edf6be3b0939c46b5d64d967a655e8933623a57d32abe381e227e1d021293fd` |
| código | `research/flow_negative_v1/s1_panel.py` | `6db8772b0adfc7682b7088fb27b425f8e800affa676c77be24dab43b3c4f54fd` |
| código | `research/flow_negative_v1/s1_stats.py` | `53b386bff14330732cd2d253e089c5a7eadd5bd3e1a725887775d56efa3db95c` |
| código | `research/flow_negative_v1/s2_etf_gap.py` | `bfb903b85a93d8cf55368fd3325a6d8bfef051c3c80aefde799e47e49a0bfa08` |
| código | `research/flow_negative_v1/s2_etf_inventory.py` | `dfe90381f2c0120a38272bfc8c9fc271ac1116f7bbd28462d8aeb2d75694884b` |
| código | `research/flow_negative_v1/s2_etf_lib.py` | `bf5b0369c8e599b69449e16d90f89770c320b2284236a5afb9676ca57a9657ff` |
| código | `research/flow_negative_v1/s2_etf_membership.py` | `f8a95143cb897b473914a2ac1fb6eae77647b178ed5ecf9dd68272ad6dfdca72` |
| código | `research/flow_negative_v1/s2_etf_sample.py` | `db316d6ff35d4795743ec6f731307e1dfc276b3da2d90b87abf12384e862540e` |
| código | `research/flow_negative_v1/s2_etf_validate.py` | `3d1196aafbc040611546ee161f14a6f588280d5472936fc6d947f45ebbb4bcfd` |
| código | `research/flow_negative_v1/s2_etf_validate_cik.py` | `713394e7ca24ce8b5e0465104c5e3edb88eea939f7a82c88ab503989cb0d93e8` |
| código | `research/flow_negative_v1/s2_link.py` | `8f2357f03926131b11c3a22d19dbc60dc9e5138f29a47bcd4f6698ac87a745c0` |
| código | `research/flow_negative_v1/s2_sec_names.py` | `d686bac0c0285f18495fb062fe654d5ceb4b5987091b77194d7603f045e636dc` |
| código | `research/flow_negative_v1/s3_validate_v4.py` | `c81daa2adb24bbc91207f3d5519e1fc597f63da655f58b251259349668626a28` |
| datos repo | `research/flow_negative_v1/data/membership.csv` | `ec67600d7b451625d5b6afdca12b05e8fde64b94d61db339f477880cc27e0f69` |
| datos repo | `research/flow_negative_v1/data/changes.csv` | `3449827ca59f348ac6170940d60f9fa334906fde8a880fae5422178832efd274` |
| datos repo | `research/flow_negative_v1/data/membership_etf_sp400.csv` | `ad65e63aed75f4c70569e06b349b0729d85c23fc66fd7ca558e8961204cd677e` |
| datos repo | `research/flow_negative_v1/data/terminal_events_v4.csv` | `1d5622ac73d6f8acf46e2ff7bd4675c2a50010a75a475d25f35835881d04f39e` |
| datos repo | `research/flow_negative_v1/data/sic_gics_rules.csv` | `0837268492a8d1407237c84b365086364cfcbc5b6307a13a2daba5ecd18710b4` |
| datos repo | `research/flow_negative_v1/data/sic_sector_by_cik.csv` | `0fa81a8a86df06c312bd3b8cf50d100ace284e412339f7df124b781c81537283` |
| datos repo | `research/flow_negative_v1/data/v4_h1_frozen_cuts.json` | `6027f7e4be9502ee56fe79686d3386b979369b986db1bf473d6d58be0589bf9e` |
| datos externos | `work/panel_v4.parquet` | `8c1888326e66d4bc1962c0893c3e7436446694eb8fa0af4cba86e1c4e8ee46c7` |
| datos externos | `work/companies_v4.csv` | `367b39a30d85292e384cab1c87c7a6fbfe554384103a52004193716d45e289aa` |
| datos externos | `work/company_links_v4.csv` | `0e43ebae2951f769a7463d3c87ddb04228aa6b94410130b21e0379fd407dca40` |

## 14. Cambios frente a la v2

| Pieza | v2 | v3 |
|---|---|---|
| Unidad | Días de pertenencia a un índice (L / M / S) | Empresa, desde su primera pertenencia a cualquier índice |
| Tamaño | El índice | Capitalización en t (grande / mediana / pequeña / micro / sin capitalización) |
| S&P 400 2015-2020 | Wikipedia | Carteras de ETF |
| S&P 600 | Desde 2020 como universo | Solo como entrada en la muestra, desde el 17-dic-2019 |
| Desarrollo de pequeñas | 2020-2022 (S&P 600) | 2018-2022 (talla pequeña) |
| Eventos futuros | Excluían la señal en (t, t + 40] | Se marcan y se tratan en el resultado |
| Exceso de referencia | Media del universo-índice | Media de la talla |
| Cortes de H1 | Por universo, v2 | Únicos, v4 (2018-2020, todas las tallas) |
| H1 | 3 universos | 3 tallas (grande, mediana, pequeña) |
| Regla «M necesita el signo de L o S» | Sí | Eliminada (la composición del S&P 400 ya es fiable) |
| Coste de micro | — | 1,5 % |
