# Preregistro — Flow Score negativo: caracterización y valor incremental (v2)

**Estado: BORRADOR SIN FIRMAR.** Sustituye a la v1 (`wiki/PREREGISTRO_FLOW_NEGATIVO_V1.md`). Incorpora el encargo
de revisión del 2026-11-18 y los resultados de la etapa 0
(`research/flow_negative_v1/ETAPA0_INFORME.md`, `EMPRESAS_DESAPARECIDAS.md`).
Quedan 3 decisiones abiertas (§12). Hasta que se resuelvan, se firme y se congele con SHA-256, no se calcula ningún
rendimiento posterior a una señal.

## 0. Pregunta, objetivo y lenguaje

¿Qué pasa después de cada nivel negativo del Flow Score? ¿Cambia según el tamaño, la liquidez y el régimen? ¿Aporta
el Flow información sobre lo que viene después, más allá de la caída previa del precio?

Cada nivel y segmento acaba en una de tres lecturas: **reversión** (posible oportunidad), **continuación bajista**
(peligro) o **descripción de una caída ya producida** (nada más).

No se busca una estrategia ni un indicador nuevo, ni se toca producción. Los componentes del Flow distintos del
momentum (RSI, MACD, ATR, Koncorde, distancia al máximo) son transformaciones del precio y, en parte, del volumen.
**No son flujos de capital.** Si aportan algo, la conclusión será que contienen información predictiva adicional a
los retornos de 5 y 21 sesiones, no que exista acumulación institucional.

Principio rector: vale más una caracterización correcta que muestre que el Flow negativo no aporta nada, que una
oportunidad aparente fabricada por sesgos, costes irreales o sobreajuste.

## 1. Etapas

| Etapa | Qué hace | Datos | Decide |
|---|---|---|---|
| 0 — Construcción | Hecha (ver informe) | Sin resultados posteriores | La validez de los datos |
| 1 — Caracterización | Curva completa del Flow negativo | **Solo desarrollo** | Elige como mucho 4 celdas para la etapa 2 y estima los parámetros de M0/M1 |
| 2 — Validación | H1 y las celdas elegidas, **una sola vez** | **Prueba** | El veredicto |

Las hipótesis y todos los parámetros de la etapa 2 se congelan (con SHA-256) al terminar la etapa 1 y antes de
consultar ningún dato de prueba. La caracterización del periodo completo se publica después de la etapa 2, solo como
descripción.

## 2. Universos y periodos

| Universo | Composición en cada fecha | Desarrollo | Prueba |
|---|---|---|---|
| **L** — grandes | S&P 500 | 2018-01-02 → 2020-12-31 [DECIDIR-A] | 2021-01-04 → fin |
| **M** — medianas | S&P 400 | 2018-01-02 → 2020-12-31 [DECIDIR-A, B] | 2021-01-04 → fin |
| **S** — pequeñas | S&P 600 | 2020-01-02 → 2022-12-30 [DECIDIR-C] | 2023-01-03 → fin |
| **P** — propio | Portfolio Tracker, Flow capturado en vivo | — | — (solo descriptivo) |

- **Fin** = última fecha de señal con 40 sesiones de datos (datos congelados a 2026-11-13; fin ≈ 2026-09-17).
- Composición reconstruida con instantáneas anuales de Wikipedia + tabla de cambios (etapa 0, `data/membership.csv`).
- Un valor genera señales solo los días en que pertenece al índice. Sus precios posteriores sí se usan para medir el
  resultado de esas señales.
- El S&P 600 no representa a todas las small caps de EE. UU.: exige beneficios para entrar y excluye microcaps y
  empresas deficitarias fuera de índice. Las conclusiones de S valen para ese universo.

## 3. Datos (fuente única: Alpaca)

- Barras diarias SIP en bruto de Alpaca para todo. Splits y dividendos se aplican con la regla de coherencia con el
  precio (enmienda 7 de microestructura).
- Identidad por épocas: un ticker reutilizado, o una empresa que quiebra y reaparece, da series distintas. Enlace de
  cambios de ticker por Alpaca y, antes de 2020, por CIK de la SEC.
- Flow: réplica de producción, verificada idéntica en 3 000 filas y equivalente a Yahoo (mediana y p90 de la
  diferencia, 0).
- Capitalización: acciones de la SEC por fecha de presentación (≤ t, ≤ 400 días), corregidas por splits y limpias de
  errores de escala.
- Datos con licencia de Alpaca fuera del repo. En el repo solo hay código, composición y agregados por franja.

## 4. Definiciones

### 4.1 Señal y ejecución
- Flow_t con el cierre de t; solo días con Flow completo y sin evento corporativo en [t − 259, t + 40] sesiones.
- Entrada: **apertura de t+1**. Sensibilidad: cierre de t+1.
- Plazos: 5, 10, 20 y 40 sesiones. **El principal es 20.** Retorno = cierre de t+H (rendimiento total) / entrada − 1.

### 4.2 Resultados terminales (detalle en `EMPRESAS_DESAPARECIDAS.md`, §5)
- Valor de salida conocido: ese valor en la fecha efectiva y después 0 % hasta el plazo.
- Cambio de ticker: se sigue la serie sucesora.
- Adquisición sin valor conocido: último cierre. Cotas: × e^−0,05 y × e^+0,05 (percentil 90 del error medido en
  2020+).
- Quiebra, exclusión/OTC, escisión, términos incoherentes y fin desconocido: último cierre. **Cotas: 0 y último
  cierre.**
- Cada conclusión debe mantenerse con las dos cotas. Toda celda con más del 1 % de episodios de valor desconocido se
  marca. Se publica además una versión que excluye esos episodios. Nada se excluye en silencio.

### 4.3 Medidas por señal
- Retorno bruto.
- Exceso frente al universo: media de todos los miembros del mismo universo, de cualquier nivel de Flow, con la
  misma entrada y plazo.
- Exceso frente a SPY y frente a la mediana de su sector (mismo índice, misma fecha, al menos 5 pares).
- MFE y MAE (máximo y mínimo intradía entre t+1 y t+H frente a la entrada).
- **Nuevo mínimo:** el mínimo entre t+1 y t+H queda por debajo del mínimo de las 20 sesiones hasta t.
- Cola: percentiles 5 y 10; P(retorno ≤ −10 %) y P(≤ −20 %).
- Por celda: media, mediana, media recortada al 1 % y % positivo.

### 4.4 Niveles de Flow (fijados)
- **Absolutos:** Z0 [−5, 0) · Z1 [−10, −5) · Z2 [−15, −10) · Z3 [−20, −15) · Z4 [−30, −20) · Z5 < −30.
  Referencias: todos los días, Flow ≥ 0 y [0, 4).
- **Percentil entre valores** (mismo universo y día): ≤ 1 % · (1, 5] · (5, 10] · (10, 25] · (25, 50].
- **Percentil propio** (frente a las 252 sesiones anteriores del valor, incluida t): mismas franjas.

### 4.5 Estados y episodios
- **Estados:** todos los días en un nivel. Nunca se tratan como independientes (§9).
- **Episodios:** para X ∈ {−10, −20, −30}, primer día con Flow < X tras ≥ 10 sesiones con Flow ≥ X. Es la población
  principal para cualquier lectura de «señal».

### 4.6 Poblaciones
- **A. Descriptiva:** todos los miembros con datos válidos, sin filtro de precio ni de liquidez. Sirve para el
  fenómeno.
- **B. Operable:** precio en bruto ≥ 3 $ y mediana de precio × volumen de las 20 sesiones hasta t ≥ 1 M$. Sirve para
  la utilidad práctica.
- Ambas se muestran siempre en la caracterización, con lo que elimina el filtro por índice y franja (etapa 0: hasta
  el 7,6 % en Z5 del S&P 600). Los resultados de A nunca se presentan como ejecutables. Costes y oportunidades, solo
  en B.

### 4.7 Segmentos
- **Tamaño:** universo (L, M, S) como clasificación principal. Dentro de cada uno, tercios de capitalización en la
  fecha (solo en universos-año con cobertura SEC ≥ 80 %, como en todos los de la etapa 0). Las series con saltos
  residuales de acciones (2,2 %) quedan marcadas.
- **Liquidez:** quintiles de la mediana de precio × volumen de 20 sesiones, dentro del universo y el día. Es una
  dimensión independiente de la capitalización.
- **Rotación:** tercios de liquidez / capitalización donde hay capitalización; si no, «no evaluable».
- **Régimen** (SPY en t): alcista = cierre ≥ SMA200, cierre ≥ SMA50 y SMA50 ≥ SMA200; bajista = cierre < SMA200;
  lateral = el resto.
- **Tipo de caída — regla jerárquica y excluyente**, con retornos de 21 sesiones hasta t, evaluada en este orden:
  1. **General:** SPY ≤ −5 % o mediana de su sector ≤ −8 %.
  2. **Idiosincrática:** valor − mediana de su sector ≤ −10 pp y SPY > −3 %.
  3. **Mixta:** el resto.
  - Si el sector tiene menos de 5 pares ese día, se usa SPY en lugar del sector y la observación queda marcada.
- **Sector:**
  - GICS de las instantáneas de Wikipedia (la última que lista el valor; no es en cada fecha). «Telecommunication
    Services» se normaliza a «Communication Services».
  - Faltan en el 0,2-0,4 % de los días-miembro de L y M y en el 3,6 % de S (empresas que solo aparecen en la tabla de
    cambios). Para ellas se usará el código SIC de la SEC con una tabla SIC→GICS fijada antes de la etapa 1.
  - Se publica qué parte de cada celda usa SIC. La referencia sectorial de las empresas desaparecidas es menos fiable
    y así se dirá.

## 5. Etapa 1 — caracterización (solo desarrollo)

- **Contenido:** tablas por universo × nivel (absoluto y percentiles) × plazo, para estados y episodios, poblaciones A
  y B, con todas las medidas de §4.3. Cruces con capitalización, liquidez, rotación, régimen y tipo de caída. Curvas
  de exceso, MAE, nuevo mínimo y cola izquierda frente al nivel.
- Celda con menos de 100 episodios o menos de 30 semanas distintas: «insuficiente», no se interpreta.
- **Parámetros que se estiman aquí y se congelan:** las medias de exceso a 20 sesiones de las 25 celdas de retornos
  (M0) y los tres efectos de tercio de R (M1), con la población A de desarrollo de cada universo (§6.2).
- **Elección para la etapa 2.** Como mucho 4 celdas en total (universo × umbral de episodio × plazo de 20 o 40 × régimen
  o «todos»), las de mayor |t|, que cumplan a la vez:
  - |t| ≥ 2,5 con el error de §9;
  - al menos 100 episodios;
  - mismo signo en las dos mitades del desarrollo;
  - mismo signo con las dos cotas de §4.2;
  - menos del 1 % de episodios de valor desconocido;
  - [si B] en M, el mismo signo en L o en S en desarrollo.
  Si ninguna cumple, la etapa 2 se limita a H1.
- La etapa 1 no produce ninguna regla operativa, aunque algo parezca claro.

## 6. H1 — ¿el resto del Flow añade algo a la caída previa?

**Pregunta:** entre valores con caídas parecidas a 5 y 21 sesiones, ¿los demás componentes del Flow permiten
distinguir resultados futuros?

### 6.1 Variables y celdas (congeladas en la etapa 0, sin resultados: `research/flow_negative_v1/data/h1_frozen_cuts.json`)
- w1 y m1: retornos de 5 y 21 sesiones, redondeados como en el Flow.
- **R = Flow − 2·(0,6·w1 + 0,4·m1):** el resto, que contiene RSI, MACD, ATR, Koncorde y distancia al máximo.
- **Población:** días con Flow < 0, completo y sin evento (población A; la B como sensibilidad).
- **Cortes 5 × 5** de w1 y m1: quintiles de la población de desarrollo de cada universo, fijados. Por ejemplo, en L:
  w1 −6/−4/−2/0 y m1 −12/−7/−5/−2.
- **Tercios de R dentro de cada una de las 25 celdas** (c1 y c2, fijados en desarrollo). R bajo = R ≤ c1; R alto = R ≥
  c2. Si c1 = c2, R bajo = R < c1 y R alto = R > c1 (no ocurre con los cortes actuales).
- **Celda de cálculo:** (mes natural, quintil de w1, quintil de m1). Es válida si R bajo y R alto tienen cada uno al
  menos 10 observaciones ese mes. En desarrollo, el 98-99,6 % de las observaciones cae en celdas de 30 o más.

Por qué así: con 10 × 10 por día la celda mediana tiene 1 observación, y con 5 × 5 por día la mitad de las
observaciones queda en celdas de menos de 10. Agrupar un mes con cortes fijos permite comparar valores con caídas
parecidas sin que una o dos empresas dominen.

### 6.2 Estadísticos (fuera de muestra, periodo de prueba)
1. **Diferencia controlada D.** En cada celda válida:
   - d_c = exceso medio a 20 sesiones de R alto − exceso medio de R bajo;
   - D_mes = media de d_c ponderada por el número de observaciones de la celda;
   - D = media de D_mes en los meses de prueba.
2. **Comparación de modelos.**
   - M0 = media de exceso de desarrollo de la celda 5 × 5 del valor (solo retornos previos).
   - M1 = M0 + efecto de su tercio de R (bajo, medio, alto), estimado en desarrollo con todas las celdas juntas.
   - En cada día de prueba con al menos 30 observaciones: IC_t = correlación de Spearman entre la predicción y el
     exceso realizado. ΔIC_t = IC_t(M1) − IC_t(M0). Se usa la media de ΔIC.

### 6.3 Criterio (en cada universo por separado)
- **Confirmado si se cumplen las dos:**
  - |D| ≥ 0,5 pp con su intervalo sin el 0;
  - media de ΔIC > 0 con su intervalo sin el 0.
- Intervalos al nivel corregido de §9.
- Si se cumple una y no la otra: «evidencia parcial», no confirmado.
- **Signo:** D > 0 significa que, con la misma caída, mejor estado técnico precede a mejor resultado; D < 0, lo
  contrario.
- Si no se confirma en ningún universo, lo que muestre la etapa 1 describe la caída ya producida.
- Sensibilidades publicadas (no deciden): población B, plazos de 5, 10 y 40, cotas terminales, sin saltos
  inexplicados, S sin 2020, celdas por día de 5 × 5 con mínimo de 10.

## 7. Celdas elegidas en la etapa 1 (H2-H5)

- **Se confirma** si en prueba: mismo signo, |exceso| ≥ 0,5 pp × (H/20)^0,5 e intervalo sin el 0.
- **Atribución al Flow** (necesaria para llamarla oportunidad o peligro): frente a días sin esa señal de la misma
  celda (mes, quintil w1, quintil m1), la diferencia mantiene el signo con el intervalo sin el 0. Si no, se clasifica
  como «describe la caída previa».

## 8. Clasificación final de cada nivel y segmento

| Lectura | Requisitos |
|---|---|
| **Reversión (posible oportunidad)** | Exceso positivo confirmado + atribución + exceso neto de costes > 0 en la población B con los costes base |
| **Continuación bajista (peligro)** | Exceso negativo confirmado, o más nuevos mínimos o peor percentil 10 que los días de su misma celda de retornos, con intervalo sin el 0 |
| **Descripción de la caída** | Todo lo demás, incluido lo que explican w1 y m1 |

- Cualquier lectura exige mantenerse con las dos cotas terminales.
- Significación y relevancia se informan por separado: un efecto significativo por debajo de 0,5 pp se publica como
  «estadísticamente distinto de cero, sin relevancia económica».
- **Costes (supuestos, no observados), ida y vuelta:** L 0,2 %, M 0,4 %, S 0,8 %. Sensibilidades ×2 y ×3. Se advierte
  que en los segmentos menos líquidos el coste real puede ser mayor que cualquiera de estos.
- Se distinguen siempre: retorno bruto (descriptivo), exceso frente a universo y sector, y neto de costes (solo
  población B).

## 9. Inferencia

- Para cada celda se forma la serie diaria de su exceso medio (una cifra por día). Así la correlación transversal de
  una crisis cuenta una vez por día, no una por empresa.
- Error de Newey-West con retardo igual al plazo.
- **Bootstrap por bloques de 60 sesiones (principal, 2 000 réplicas)**; sensibilidades de 20 y 120 sesiones. Para D
  (serie mensual): bloques de 3 meses, sensibilidades de 1 y 6.
- Se decide con el principal. Si alguna sensibilidad mete el 0 en el intervalo, la celda se marca como «frágil» (no
  cambia el veredicto).
- **Comparaciones múltiples:** Bonferroni sobre H1 (3 universos) + las celdas elegidas (como mucho 7 contrastes).
  Nivel por contraste = 0,05 / número de contrastes.

## 10. Trayectoria previa del Flow (sin hipótesis)

Las series guardan el Flow diario completo de cada valor, de modo que más adelante se puede estudiar si llega a −20
deteriorándose deprisa o tras semanas estable. **En v1 no es hipótesis ni filtro.**

## 11. Universo propio (P) y salidas

- **P:** mismas tablas de la etapa 1 con el Flow tal como se capturó (desde el 20-ago-2026), en un apartado aparte,
  sin intervalos que se lean como prueba. Nunca fija nada.
- **Salidas:** código y agregados en `research/flow_negative_v1/`. Precios, Flow por valor y día y capitalizaciones,
  fuera del repo.

## 12. Decisiones abiertas (bloquean la firma)

| | Problema (etapa 0) | Recomendación | Alternativa |
|---|---|---|---|
| **DECIDIR-A** | Alpaca empieza en 2016; el Flow completo (Koncorde semanal de 100 semanas) existe desde el 29-dic-2017 | Señales de L y M desde 2018-01-02 | 2016-2017 como sensibilidad con Flow sin la parte semanal |
| **DECIDIR-B** | Composición del S&P 400 2016-2020 con coherencia 86,7-94,0 % (< 95 %); las anclas mensuales no la arreglan | Mantener M en desarrollo con la advertencia; sus celdas solo pasan a la etapa 2 si el signo coincide en L o S | Sacar M de la etapa 1 y evaluarlo solo en H1 en prueba |
| **DECIDIR-C** | S&P 600 en 2020 reconstruido hacia atrás sin ancla (84-96 % de coincidencia con las listas de Wikipedia) | Desarrollo 2020-2022 + sensibilidad sin 2020 | Desarrollo 2021-2022 |

Tus seis decisiones de la v1 están incorporadas: etapa 1 solo en desarrollo; Alpaca como fuente única (ya
validada); umbrales de caída con regla jerárquica; filtros solo para la población operable; costes como supuestos con
sensibilidad; mínimo de 0,5 pp distinto de la significación.

## 13. Propuesta de congelación

Al firmar, se guardará el SHA-256 de:
1. Este documento (versión final).
2. El código de la etapa 0: `fn_config.py`, `s0_universe.py`, `s0_prices.py`, `s0_prices_retry_empty.py`,
   `s0_series.py`, `s0_terminal.py`, `s0_terminal_impact.py`, `s0_sec.py`, `s0_parity.py`, `s0_coverage.py`,
   `s0_h1_design.py`, `s0_h1_cuts.py`.
3. Los datos congelados: `data/membership.csv`, `data/changes.csv`, `data/terminal_events.csv`,
   `data/h1_frozen_cuts.json` y, fuera del repo, `work/panel.parquet`, `work/series_summary.csv`,
   `sec/cik_map.csv`. Los dos últimos, con su hash publicado en el repo.

Al terminar la etapa 1 y antes de tocar la prueba, se congelará un segundo archivo con las celdas elegidas y los
parámetros de M0/M1.

Pendiente antes de firmar, además de A-C: la tabla SIC→GICS para el 0,2-3,6 % de días sin sector. Opcional y sin
efecto previsto en las conclusiones: las 19 adquisiciones en acciones o mixtas cuyo comprador no está en el universo.
