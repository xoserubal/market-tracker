# PREREGISTRO — Giro de sectores deprimidos v2

> **VERSIÓN FINAL PARA FIRMA (2026-11-28). Sin firmar.**
> - Sustituye al borrador v2 del mismo día y a la v1 (2026-11-25).
> - Incorpora las decisiones del usuario sobre el §12 del borrador y sus cuatro precisiones.
> - No se ha calculado ningún resultado posterior a las señales. Solo se han contado observaciones, semanas,
>   trimestres y comparaciones identificables, y una dispersión incondicional para la potencia (§9).
> - Al firmar se guarda la huella (sha256) de este fichero y de `scripts/sector_turn/lib.js`. Cada contraste se
>   ejecuta una sola vez.

## 0. Origen y objetivo

- **Origen:**
  - El usuario recuerda haber visto girar sectores muy castigados sin llegar a actuar: Real Estate (~sep-2026), Salud
    (~30-sep) y Staples (~8-oct).
  - La versión mecánica «sector líder + señal de compra + flow change» ya está probada y no funciona
    (`research/sector_confluence_v1`, NO SOPORTADO).
- **Objetivo:**
  - Comprobar si se puede reconocer pronto el giro de sectores estadounidenses muy castigados frente al S&P 500.
  - Comprobar si el mapa de rotación de Cycle ayuda a distinguir qué giros se consolidan.
  - Cycle no es condición para reconocer un giro, y nada de esto es una señal de compra automática.

| Caso | Situación | Lectura |
|---|---|---|
| A | D∧G y el ETF encaja con la siguiente posición de Cycle | Giro con respaldo de contexto |
| B | D∧G sin encajar con Cycle | Giro identificado, sin ese respaldo |
| C | D, encaja con Cycle, sin G todavía | Vigilancia, no señal |

## 1. Hipótesis y jerarquía

- **H1-sectorial (principal):**
  - Entre los 11 sectores SPDR, un sector con deterioro relativo profundo frente al S&P 500 (D) que empieza a recuperar
    fuerza (G) rinde después más que los sectores comparables de las mismas fechas.
  - Se identifica sin mirar Cycle.
- **H1-ampliada:**
  - La misma hipótesis sobre el conjunto de sectores e industrias de EE.UU.
  - Un resultado favorable en H1-ampliada no confirma H1-sectorial.
- **H2 (valor añadido de Cycle):**
  - Entre los eventos D∧G, los que encajan con la siguiente posición de Cycle rinden más que los que no.
  - Se mide una vez descontadas la profundidad, la fuerza relativa y el momentum del propio ETF.
  - Tiene su propio veredicto y no modifica el de H1.
- **Secundarias, solo descriptivas:**
  - ¿Añade algo el giro a estar deprimido? (B0)
  - ¿Importa estar deprimido? (B3)
  - Etapas inspiradas en Pring (§8).

## 2. Mercados, bloques de evidencia y estatus

| Bloque | Contenido | Estatus |
|---|---|---|
| **A** | EE.UU., 11 sectores, del 2001-12 al 2026-08-28 | **Exploratorio.** Ya se ha mirado de muchas formas (§11). Veredictos FAVORABLE / INCONCLUYENTE / DESFAVORABLE; nunca «confirmado». |
| **A′** | EE.UU., 18 industrias no expuestas, del 2003 al 2026-08-28 | **Generalización entre niveles de agregación.** Comparte ciclo, factores y componentes con A. No es confirmación independiente de los 11 sectores. Mismas etiquetas que A. |
| **B** | Europa, 19 ETFs STOXX 600 (Xetra), desde 2008 | **Contraste secundario, solo H1, descriptivo.** Sin poder de veto sobre EE.UU. |
| **C** | Registro semanal prospectivo de EE.UU., desde la semana 2026-W48: 11 sectores y 25 industrias (36 ETFs) | **Único bloque confirmatorio**, para H1-sectorial, H1-ampliada y H2. |

- **Ventana excluida:** del 2026-08-29 al 2026-11-27, la de los casos motivadores. No entra en ningún bloque.
- **No existe un bloque histórico no examinado de los 11 sectores.** Su confirmación es necesariamente prospectiva.
- Los bloques A y A′ permiten aprender del histórico sin esperar años, con su estatus declarado.

## 3. Definiciones (congeladas; implementadas en `scripts/sector_turn/lib.js`)

- **Ratio:** cierre ajustado por dividendos (`adjclose` de Yahoo) del ETF / el de SPY, en las sesiones comunes.
- **D (deprimido):**
  - El ratio está al menos un 20 % por debajo de su máximo de las 756 sesiones que terminan en la de decisión, incluida.
  - Con menos de 756 sesiones, el ETF no es evaluable.
  - **Exposición:** la definición surgió de mirar los tres casos de 2026 (§11).
- **G (giro):**
  - El ratio cierra la semana por encima de su media de 50 sesiones (`>`), tras cerrar la semana anterior por debajo o
    en ella (`≤`).
  - Las alternativas de RFL solo se describen y no pueden sustituir a G.
- **Semana y decisión:** semana ISO; la decisión es su última sesión, normalmente el viernes.
- **Evento:** D∧G en la sesión de decisión.
- **Independencia:**
  - No hay otro D∧G del mismo ETF en las 8 semanas de decisión anteriores.
  - Es la regla de todos los bloques. Las medidas principales solo usan eventos independientes.
- **Entrada:** cierre de la sesión siguiente a la decisión.
- **Horizontes:** 40 sesiones el principal; 20 y 60 secundarios.
- **Exceso:** retorno del ETF menos la media de los ETFs de su mismo nivel disponibles en las mismas fechas, neto de
  coste.
  - Nivel: sector frente a la media de los sectores; industria frente a la media de las industrias del bloque.
  - Coste ida y vuelta: 0,10 % en sectores y 0,20 % en industrias. Sensibilidad al doble y al triple.

## 4. Universo

- **Sectores:** XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY.
  - Primer evaluable: 2001-12-28. XLRE, 2018-10; XLC, 2021-06.
- **Industrias, según la tabla 14-2** de Navarro (*If It's Raining in Brazil, Buy Starbucks*), basada en el modelo de
  rotación de Stovall/S&P.
  - **Auditoría de exposición** (`research/sector_turnaround_v2/exposure_audit.py`): busca cada ticker como palabra en
    los ficheros de texto y como valor real dentro de los de datos.
  - **Expuestas, solo en C:** IYT, XHB (proxies de Cycle); SMH, XME, SLX, XOP, KRE (RFL y test de familias).
  - **No expuestas (A′ y C):** ITB solo aparece citado en una lista de propuestas, nunca usado.
  - **IBB, IHI y XHS amplían la lista literal del libro** (biotecnología, equipos médicos y servicios de salud; el
    libro dice «health care» y «pharmaceuticals»). Se incluyen en la muestra principal y se informa además sin ellos.
  - La posición 4 (materiales) no tiene ninguna industria sin exponer.

| Posición | Categoría del libro | A′ (primer evaluable) | Solo C |
|---|---|---|---|
| 1 Early bull | Transporte | XTN (2014-01) | IYT |
| 2 Early→mid bull | Tecnología | XSD (2009-02) | SMH |
| 3 Mid→late bull | Bienes de equipo | PAVE (2020-03) | — |
| 4 Late bull | Materiales básicos | — | XME, SLX |
| 5 Late bull→top | Energía | OIH (2004-03), XES (2009-06), FCG (2010-05) | XOP |
| 6 Early bear | Staples y salud | IHE, IHI (2009-05), XHS (2014-10), IBB (2004-02), PBJ (2008-06) | — |
| 7 Approaching late bear | Utilities (incluye telecos de cable y poste) | IYZ (2003-06) | — |
| 8 Late bear | Finanzas y consumo cíclico | KBE (2008-11), IAT (2009-05), ITB (2009-05), XRT (2009-06), CARZ (2014-05), IYR (2003-06) | KRE, XHB |

## 5. Cycle: cuatro objetos separados y versiones inmutables

### 5.1 Los cuatro objetos

1. **Tabla y algoritmo reales de Cycle** (`cycle.html` tal cual, sin modificar).
   - **Algoritmo:**
     - α de cada valor = 0,7·(m3 − m3 de SPY) + 0,3·(m1 − m1 de SPY), con los retornos enteros de `/api/quote`. Si
       falta m1, se usa m3.
     - Puntuación de la fase = media de α de todos sus valores.
     - Fase dominante = la de mayor puntuación. En empate, la primera de la tabla.
   - **Copia congelada:** `cycle_copy.js`, serie `cycle-copy-1`, huella de los fragmentos originales `57bf3c57…`.
   - **Equivalencia** (`test_cycle_equivalence.js`): el original se extrae de `cycle.html` y se ejecuta.
     - 503 casos sintéticos sin ninguna diferencia.
     - Las 3 mutaciones introducidas en el original se detectan.
     - Datos reales del 2026-11-27: 81 valores idénticos entre original y copia, y con lo que `/api/quote` sirve a la
       pestaña.
   - **Cada captura semanal** vuelve a ejecutar el original y la copia, y exige que coincidan.
2. **Tabla del libro** (§4). Es la tabla secundaria. A nivel de sector solo difiere de la de Cycle en XLRE.
3. **Cycle simplificado histórico**, solo con los valores de papel *proxy*: IYT; SMH, XLK; XLI; FCX, XLB; XLE; URNM,
   URA; TECK; XLP, XLV; XLU; XLF, XHB.
   - Misma fórmula que la real, pero sin las acciones de la tabla real, que se eligieron en 2026.
   - **Cobertura:**

     | Desde | Fases con puntuación |
     |---|---|
     | 2001-12 | 7 |
     | 2002-10 | 8 (+ TECK) |
     | 2004-04 | 9 (+ IYT) |
     | 2011-02-11 | 10 (+ URA) |

   - FCX y TECK son acciones sueltas que hacen de proxy.
   - No se inventan datos: la fase dominante se calcula con las fases disponibles y la cobertura queda registrada.
   - **No equivale a la ejecución real de Cycle.**
4. **Registro prospectivo de la pestaña Cycle real** (§10). Es la única fuente de H2 confirmatoria.

### 5.2 Versiones inmutables

- Cada registro guarda su serie (`cycle_series`) y las huellas de `cycle.html`, de sus fragmentos y de la copia.
- Si `cycle.html` cambia, la captura se detiene y avisa. No se actualiza sola.
- Para una nueva definición hacen falta tres cosas:
  1. autorización expresa;
  2. una copia nueva con otro `COPY_VERSION`, que vuelve a pasar la prueba de equivalencia;
  3. **una serie prospectiva nueva**. Los eventos de series distintas nunca se juntan en el mismo contraste.

### 5.3 Posiciones, siguiente posición y concordancia (congelado)

- **De fases a posiciones:**

  | Fase de Cycle | Posición |
  |---|---|
  | 1 | 1 |
  | 2 | 2 |
  | 3 | 3 |
  | 4 | 4 |
  | 5, 6, 7 | 5 |
  | 8 | 6 |
  | 9 | 7 |
  | 10 | 8 |

  - Petróleo y gas, uranio y carbón comparten la posición 5: no son siguientes unas de otras.
- **Posición actual** = la de la fase dominante, aunque otras fases de su posición puntúen distinto.
- **Siguiente** = posición + 1; de la 8 se vuelve a la 1.
- **Sectores por posición:**

  | Posición | Sector |
  |---|---|
  | 2 | XLK |
  | 3 | XLI (proxy industrial amplio, que incluye transporte: limitación declarada) |
  | 4 | XLB |
  | 5 | XLE |
  | 6 | XLP, XLV |
  | 7 | XLU |
  | 8 | XLF, XLY |

  - La posición 1 no tiene sector SPDR.
  - XLC sin fase.
  - **XLRE en la posición 8** en la tabla prospectiva («Cycle + XLRE»), con su exposición declarada. Todo el H2
    histórico se presenta con y sin XLRE.
- **Industrias:** posición del libro (§4).
- **Concordancia:** el ETF con D∧G está asignado a la siguiente posición. Si no tiene posición, queda fuera de H2.
- No se puede declarar a posteriori que la siguiente era otra.

## 6. H1 — estimando, ponderación, comparadores y criterios

### 6.1 Estimando y tratamiento de las señales contemporáneas

Los eventos de una misma semana están correlacionados (un sector y sus industrias, varias industrias de una misma
posición). Por eso el estimando pondera por semana, no por evento.

- **H1-sectorial y bloque A:**
  - Exceso de cada semana = media de los excesos a 40 sesiones de sus eventos independientes.
  - Estimando = media de esos valores semanales, con el mismo peso para cada semana.
- **H1-ampliada:**
  - Cada semana con eventos pesa lo mismo.
  - Dentro de la semana, sectores e industrias pesan **50 % y 50 %** cuando hay eventos de ambos niveles, y 100 % el
    nivel presente si solo hay uno.
  - Dentro de cada nivel, todos los eventos pesan igual.
  - Se fija así para que las 25 industrias no anulen a los 11 sectores.
  - **Sensibilidad:** el mismo cálculo con el mismo peso para cada evento.
- **Bloque A′:** como H1-sectorial, solo con industrias.
- **Solape:** se informa de qué parte de los eventos de industria coincide en semana con un evento de su sector.
- **Siempre se informa de:**
  - número de eventos, **semanas distintas** y **trimestres distintos**;
  - rentabilidad absoluta, coste y sensibilidad al coste;
  - desviación y % de eventos positivos;
  - peor caída intermedia en las 40 sesiones (MAE);
  - resultado sin los 5 mejores eventos;
  - exclusión de un ETF cada vez.

### 6.2 Inferencia

- **Bootstrap por bloques de trimestre natural:** se remuestrean trimestres enteros con todos sus eventos, así que se
  conservan la dependencia entre ETFs de una misma fecha y el solape de ventanas.
- 10 000 remuestras.
- Sensibilidad con bloques de semestre y de año.

### 6.3 Comparadores (todos con eventos independientes y las mismas fechas)

| Código | Pregunta | Método y población que lo identifica | Identificables en A / A′ |
|---|---|---|---|
| B0 | ¿Aporta el giro sobre estar deprimido? (D∧G frente a D sin G) | Regresión con efectos fijos por semana, controles de profundidad y fuerza relativa a 63 sesiones. Solo semanas con ambos | 118 / 277 semanas |
| B0′ | Emparejamiento descriptivo | D sin G de otro ETF a ±4 semanas y a ±5 pp de profundidad. Reutiliza parejas y mezcla semanas | 108 de 148 / 365 de 409 eventos |
| B1 | Azar | Mismo número de ETFs al azar en las mismas fechas; se da el percentil | todas |
| B2 | Momentum | Tercio superior por fuerza relativa a 63 sesiones | todas |
| B3 | ¿Importa estar deprimido? (G sin D) | Semanas con ambos | — |

- Los comparadores **informan, no deciden**. El veredicto de H1 depende del estimando de §6.1.
- Si en algún comparador los efectos fijos no tienen suficiente variación, se declara **no evaluable**. Los efectos
  fijos no suplen la falta de comparadores.

### 6.4 Multiplicidad

- **Familia confirmatoria (bloque C):** {H1-sectorial, H1-ampliada, H2}, con Bonferroni.
  - α = 0,05/3 por contraste.
  - Intervalos de confianza al **98,33 %**.
- **Bloques A y A′ (exploratorios):** IC 95 %, sin pretensión confirmatoria.
- Horizontes secundarios, comparadores, sensibilidades, Europa y Pring: IC 95 %, solo descriptivos.

### 6.5 Efecto mínimo relevante

- **H1: +1,0 pp** de exceso neto a 40 sesiones.

### 6.6 Criterios exploratorios (A, A′)

- **FAVORABLE** si se cumplen las cuatro condiciones:
  1. estimando ≥ +1,0 pp con IC 95 % por encima de 0;
  2. positivo en al menos 3 de cada 4 exclusiones de un ETF;
  3. positivo sin los 5 mejores eventos;
  4. positivo con el coste triple.
- **DESFAVORABLE** si el límite superior del IC 95 % es menor que +1,0 pp.
- **INCONCLUYENTE** en el resto.

### 6.7 Criterios confirmatorios (C)

**Evaluabilidad mínima:**

| Hipótesis | Eventos independientes | Trimestres distintos | Plazo |
|---|---|---|---|
| H1-ampliada | ≥ 60 | ≥ 12 | 3 años desde 2026-W48 |
| H1-sectorial | ≥ 30 | ≥ 10 | 5 años |

- **Punto de decisión:** cuando se cumple la evaluabilidad o vence el plazo, lo que ocurra primero. El contraste se
  ejecuta una sola vez.
- **Si vence el plazo sin evaluabilidad: INCONCLUYENTE.** No se fuerza ninguna conclusión.
- **Antes del punto de decisión:** solo informes descriptivos, que no cambian nada.

**Veredictos** (con la evaluabilidad cumplida):
- **SOPORTADA** si se cumplen las cuatro condiciones:
  1. estimando ≥ +1,0 pp y límite inferior del IC 98,33 % > 0;
  2. positivo en al menos 3 de cada 4 exclusiones de un ETF;
  3. positivo sin los 5 mejores eventos;
  4. positivo con el coste triple.
- **NO SOPORTADA** si el límite superior del IC 98,33 % es menor que +1,0 pp, es decir, si se descarta un efecto
  relevante.
- **INCONCLUYENTE** en el resto.

## 7. H2 — valor añadido de Cycle

### 7.1 Estimando

- Coeficiente β de concordancia en una regresión, sobre los eventos D∧G independientes con posición asignada:
  - variable explicada: exceso a 40 sesiones;
  - variable de interés: concordante (0/1);
  - controles: profundidad (`dist_max756`), fuerza relativa a 63 sesiones, momentum a 21 sesiones y nivel (sector o
    industria);
  - en el histórico, además, efectos de año;
  - pesos de §6.1 (los de H1-ampliada);
  - inferencia por bootstrap de trimestres (§6.2).
- Se informa de la correlación de la concordancia con cada control. Si la concordancia solo replica la fuerza
  relativa, el coeficiente controlado lo mostrará. Dos medidas derivadas de precios que coinciden no cuentan como
  evidencia independiente.

### 7.2 Muestra confirmatoria (C)

- Sectores con la tabla «Cycle + XLRE» e industrias con la tabla del libro, usando la Cycle real de la serie
  `cycle-copy-1`.
- **Se informa además, solo de forma descriptiva:** sectores solos, sin XLRE, sin IBB/IHI/XHS, y con el Cycle
  simplificado.

### 7.3 Efecto mínimo relevante

- **H2: +2,0 pp** de exceso a 40 sesiones.

### 7.4 Evaluabilidad y punto de revisión

- **Evaluabilidad:** ≥ 30 eventos concordantes **y** ≥ 30 no concordantes, cada grupo repartido en ≥ 10 trimestres
  distintos.
- **Punto de revisión:** 30 concordantes o 5 años, lo que ocurra antes.
- Llegar al punto de revisión no garantiza potencia. Por eso se informa del efecto mínimo detectable alcanzado,
  calculado con la dispersión incondicional (§9), y el veredicto lo deciden los intervalos de confianza.

### 7.5 Veredictos (con la evaluabilidad cumplida)

- **SOPORTADA:** β ≥ +2,0 pp y límite inferior del IC 98,33 % > 0.
- **NO SOPORTADA:** límite superior del IC 98,33 % < +2,0 pp.
- **INCONCLUYENTE:** en el resto, o si no se cumple la evaluabilidad en el punto de revisión.

### 7.6 Histórico (A, A′): solo descriptivo

- Usa el Cycle simplificado.
- No hay variación suficiente dentro de una misma semana:

| Muestra | Concordantes / no concordantes | Sin posición | Semanas con ambos | Trimestres con concordantes (con ambos) |
|---|---|---|---|---|
| Sectores, tabla Cycle | 28 / 103 | 17 | 3 | 24 (13) |
| Sectores, Cycle + XLRE | 29 / 114 | 5 | 4 | 25 (13) |
| Industrias A′, tabla del libro | 88 / 321 | 0 | 23 | 53 (49) |

## 8. Etapas inspiradas en Pring (descriptivo, secundario)

**Simplificación inspirada en Pring**, no su método (que usa KST y medias de 12 meses).

- Cada mercado es alcista si su serie está por encima de su media de 252 sesiones:
  - **Bonos:** ^TNX invertido (Yahoo, desde 1970).
  - **Acciones:** SPY.
  - **Materias primas:** ^SPGSCI (desde 1984).
- **Etapas:**

  | Etapa | Bonos | Acciones | Materias primas |
  |---|---|---|---|
  | I | alcista | bajista | bajista |
  | II | alcista | alcista | bajista |
  | III | alcista | alcista | alcista |
  | IV | bajista | alcista | alcista |
  | V | bajista | bajista | alcista |
  | VI | bajista | bajista | bajista |

- Las combinaciones restantes se registran como «sin etapa».
- Solo se describe el reparto de los eventos por etapa. No es una condición de entrada ni cambia H1 ni H2.

## 9. Potencia y efecto mínimo detectable

- **Dispersión incondicional** del exceso a 40 sesiones de todos los ETF-semana, sin distinguir señales. Es la única
  cifra calculada con datos posteriores, y no está condicionada a ninguna señal.
  - Sectores: 4,98 %.
  - Industrias A′: 7,49 %.
- **Efecto mínimo detectable** (potencia 80 %, α = 0,05):

| Muestra | Eventos indep. | Semanas distintas | Trimestres distintos | MDE (n = eventos) | MDE (n = trimestres, conservador) |
|---|---|---|---|---|---|
| A, sectores | 148 | 134 | 74 | 1,2 pp | 1,6 pp |
| A′, industrias | 409 | 289 | 86 | 1,0 pp | 2,3 pp |
| A + A′ juntos (referencia para H1-ampliada) | 557 | 366 | 96 | — | — |
| H2 sectores (concordantes) | 28 | — | 24 | — | ~4 pp |

- **Solape entre niveles:** 103 de los 409 eventos de industria (25 %) caen en una semana con algún evento de sector.
  Por eso H1-ampliada pondera por semana y por nivel (§6.1).

- **Ritmo prospectivo** (media 2015-2025): unos 7 eventos al año en los sectores y unos 26 en las 18 industrias A′;
  el registro sigue además las 7 expuestas.
  - **H1-ampliada:** previsiblemente evaluable en unos 2 años.
  - **H1-sectorial:** previsiblemente entre 4 y 5 años.
  - **H2:** puede llegar al plazo sin evaluabilidad suficiente.
- Recuento completo: `research/sector_turnaround_v2/counts.json` (`counts.js`).

## 10. Registro semanal prospectivo

- **Código:** `scripts/sector_turn/` (`registry.js`, `lib.js`, `cycle_copy.js`, `cycle_original.js`,
  `cycle_check.js`).
- **Pruebas:**
  - `test_registry.js`: 41;
  - `test_cycle_equivalence.js`: sintéticas, mutaciones y `--live` contra `/api/quote`.
- **Contenido por semana, haya o no señales:**
  - fecha de corte, hora real de captura y puntualidad;
  - por ETF: ratio, máximo de 3 años, distancia, SMA50, posición actual y de la semana anterior, D, G y D∧G;
  - Cycle real: 10 fases, dominante, siguiente posición y candidatos, y comprobación de que original y copia
    coinciden;
  - Cycle simplificado;
  - eventos con sus concordancias;
  - listas D, G, D∧G, D sin G, G sin D y caso C;
  - versiones y huellas del código, de Cycle y de las tablas.
- **Reconstrucción exacta:**
  - cada semana guarda `inputs/<semana>.json.gz`: 900 sesiones de cada ETF y los cierres base de m1/m3 de cada valor
    de Cycle, con un control de coherencia con `/api/quote`;
  - el registro lleva el sha256 de ese fichero, y la lectura se calcula **siempre a partir de él**;
  - `verify --deep` la recalcula y tiene que salir idéntica.
  - **Por qué es necesario:** al rehacer la semana 2026-W48 horas después de capturarla, Yahoo devolvió precios
    ajustados con diferencias relativas de hasta 2,4·10⁻⁶. Ninguna señal cambió, pero sin las entradas guardadas la
    lectura no sería reproducible.
- **Semana 2026-W48:**
  - Capturada a tiempo, en local, antes de existir el fichero de entradas (esquema 1, huella `e41ab595…`).
  - Tiene un **suplemento aproximado** (`inputs/2026-W48.supplement.json.gz`): reproduce señales, listas y Cycle de
    forma idéntica; los decimales difieren como máximo 2,4·10⁻⁶ (tolerancia 10⁻⁴).
  - El suplemento quedará encadenado en el registro de la semana siguiente.
  - **Se anclará como `anchored_late`.**
- **Puntualidad:**
  - a tiempo, si se captura antes de la apertura de la sesión siguiente;
  - recuperada con retraso (marcada), hasta 14 días;
  - después, **hueco explícito** en la cadena.
  - Si la última sesión no es el viernes, se espera al sábado a mediodía (UTC) para distinguir un festivo de un dato
    que aún no ha llegado.
  - Si faltan dos o más sectores, la captura se aborta sin escribir nada.
- **Integridad:**
  - el fichero solo se amplía, con cadena de huellas;
  - `verify` detecta:
    - registros alterados;
    - cadena rota;
    - duplicados;
    - semanas omitidas;
    - cola cortada;
    - entradas ausentes o alteradas;
    - anclajes que no casan;
    - anclajes sin registro;
  - además avisa de los cambios de serie de Cycle.
- **Almacenamiento:**
  - **Principal:** repositorio privado `market-tracker-registry`. Lo crea el usuario, con un token de grano fino
    restringido a él (`PRIVATE_REGISTRY_TOKEN`).
  - **Segunda copia:** un clon espejo en LAWNMOWER, actualizado y verificado (`verify --deep`) cada semana por una
    tarea programada, con aviso si diverge.
  - Las capturas locales actuales se trasladan al repositorio privado sin reescribirlas.
- **Publicación:**
  - Solo después de guardar en el repositorio privado: huella, fecha y anterior en
    `docs/data/sector_turn_anchors.jsonl` (repositorio público) y por Telegram.
  - `anchored_late` = anclado después de la apertura de la sesión siguiente; los registros de esquema 1, siempre.
  - Si el push privado falla, no se publica ninguna huella y se avisa.
  - El contenido nunca se publica.
- **Separación:** las reconstrucciones retrospectivas (`research/sector_turnaround_v2`) nunca escriben en el
  registro, y el registro no contiene resultados. Los rendimientos se calculan solo en el análisis, una vez vencido
  cada horizonte.
- **Integración en el pipeline:** un único paso (`registry.js run-weekly --private-git --alert`, con
  `continue-on-error` y aviso por Telegram ante cualquier fallo). Antes de activarlo se comprueban con el repositorio
  real:
  1. permisos (el token solo escribe en ese repositorio);
  2. persistencia y recuperación (relanzar tras un fallo no duplica ni pierde nada);
  3. integridad (`verify --deep` en el runner y en el espejo);
  4. publicación de huellas.

## 11. Exposición previa y garantías

- **D** se eligió mirando los tres casos de 2026, que quedan fuera de todos los bloques.
- **XLRE en la posición 8:** el inmobiliario fue uno de esos casos. Su asignación va con exposición declarada, el H2
  histórico se presenta con y sin ella, y ese caso no cuenta como confirmación.
- **Sectores de EE.UU. ya analizados:**
  - confluencia sectorial;
  - RFL (puntuación frente a alfa, inversión del flow change, registro de señales 2016-2026);
  - amplitud sectorial;
  - recuentos de la v1 y de esta versión, sin resultados.
- **Industrias:** auditadas (§4). Las expuestas solo entran en C.
- **Europa:** solo se usó EXV5.DE suelto, como referencia de un ratio.
- **Precios ajustados de Yahoo:** varían ligeramente entre consultas. El histórico usa los de la fecha de descarga y el
  prospectivo los guarda (§10).
- **No se cambian umbrales, periodos, tablas, ponderaciones ni correspondencias después de ver resultados.**

## 12. Revisión de coherencia (hecha antes de firmar)

- **Mismas definiciones en todo el código:** D, G, evento e independencia (§3) son las de `lib.js`, que usan tanto el
  recuento histórico como el registro.
- **Exceso:** siempre frente al mismo nivel. Cada estimando especifica su ponderación (§6.1).
- **Comparadores:** informan sin decidir, en los bloques exploratorios y en el confirmatorio. Así ningún veredicto
  depende de un comparador que puede no ser identificable.
- **Puntos de decisión** (§6.7, §7.4): fijados en eventos, trimestres y plazo. Al vencer el plazo sin evaluabilidad, el
  resultado es INCONCLUYENTE.
- **Umbrales:** el efecto mínimo relevante (+1,0 pp en H1, +2,0 pp en H2) se usa igual en SOPORTADA y en NO SOPORTADA.
- **Multiplicidad:** solo afecta al bloque C (98,33 %). A y A′ usan el 95 % y nunca se llaman confirmación.
- **Cycle:** el H2 confirmatorio usa solo la serie `cycle-copy-1` con la Cycle real. El simplificado nunca sustituye a
  la real.
- **Cambio respecto al borrador:** B0 deja de ser condición para FAVORABLE o SOPORTADA. Pasa a informar, porque en el
  prospectivo puede no ser identificable y bloquearía el veredicto. Responde a la pregunta secundaria de si el giro
  aporta algo sobre estar deprimido.
