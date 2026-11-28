# PREREGISTRO — Giro de sectores deprimidos v2

> **FIRMADO por el usuario el 2026-11-28.** Huellas (sha256) en `research/sector_turnaround_v2/freeze.json`.
> - Sustituye al borrador v2 del mismo día y a la v1 (2026-11-25).
> - Incorpora las decisiones del usuario sobre el §12 del borrador, sus cuatro precisiones y las siete precisiones
>   finales del asesor (ponderación 50/50 por nivel, solo resultados completos, lectura de los umbrales, robustez
>   separada del veredicto, dependencia temporal).
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

Los eventos de una misma semana están correlacionados: un sector y sus industrias, o varias industrias de una misma
posición. Por eso los estimandos promedian semanas, no eventos.

- **Media semanal de un nivel:**
  - el exceso de cada semana es la media de los excesos a 40 sesiones de sus eventos independientes de ese nivel con
    resultado completo (§6.2);
  - la media del nivel es la media de esos valores semanales, con el mismo peso para cada semana.
- **H1-sectorial y bloque A:** E_sect = media semanal del nivel sector.
- **Bloque A′:** media semanal del nivel industria, con las 18 industrias no expuestas.
- **H1-ampliada (principal):** **E_amp = 0,5 · E_sect + 0,5 · E_ind**, donde E_ind es la media semanal del nivel
  industria (en C, las 25 industrias).
  - Las dos medias se recalculan sobre la misma remuestra del bootstrap (§6.3), así que su dependencia temporal se
    trata de forma conjunta.
  - **Motivo:** la regla anterior (cada semana igual y 50/50 dentro de la semana) no reparte el peso al 50/50
    global. Con los recuentos históricos (134 semanas con eventos de sector, 289 de industria y 57 con ambos), los
    sectores pesaban un 28,8 % y las industrias un 71,2 %.
  - **Sensibilidades:**
    - la regla anterior;
    - el mismo peso para cada evento.
  - **Para que E_amp esté definido, cada nivel necesita al menos 10 eventos con resultado completo.** Si no se
    llega, H1-ampliada no es evaluable en ese momento. Es el único elemento nuevo de esta revisión, añadido por
    coherencia: con un nivel vacío el estimando no existe.
- **Solape entre niveles:** se informa de qué parte de los eventos de industria coincide en semana con un evento de su
  sector.
- **Siempre se informa de:**
  - eventos registrados y eventos con resultado completo;
  - semanas distintas y trimestres distintos;
  - rentabilidad absoluta, coste y sensibilidad al coste;
  - desviación y % de eventos positivos;
  - peor caída intermedia en las 40 sesiones (MAE);
  - las pruebas de robustez de §6.7.

### 6.2 Eventos registrados y eventos con resultado observado

- Un evento está **registrado** desde su semana de decisión.
- Tiene **resultado completo** para un horizonte cuando, en la fecha del análisis, ya existen la sesión de entrada
  (la siguiente a la decisión) y las 40 sesiones posteriores. Para los horizontes de 20 y 60 sesiones se aplica lo
  mismo con su número de sesiones.
- **Solo los eventos con resultado completo a 40 sesiones cuentan** para la evaluabilidad y para los contrastes
  confirmatorios.
- Los informes muestran siempre las dos cifras.

### 6.3 Inferencia y dependencia temporal

- **Principal:** bootstrap por bloques de trimestre natural, con 10 000 remuestras. Se remuestrean trimestres enteros
  con todos sus eventos, así que se conserva la dependencia entre ETFs de un mismo trimestre.
- **Lo que no garantiza:** remuestrear trimestres **no conserva toda la dependencia entre trimestres contiguos**. Las
  ventanas de 40 sesiones de los eventos de las últimas semanas de un trimestre se solapan con las del trimestre
  siguiente. Por eso:
  - se informa de qué parte de los eventos tiene una ventana que entra en el trimestre siguiente y se solapa con la
    de otro evento de ese bloque;
  - se repite el bootstrap con bloques de semestre y de año;
  - se informa de cómo cambian los límites del intervalo entre esas longitudes de bloque, sobre todo si hay menos de
    20 trimestres.
  - **Si el veredicto estadístico cambia con otra longitud de bloque,** se indica junto al veredicto como «sensible a
    la dependencia temporal». El veredicto principal sigue siendo el de bloques trimestrales.

### 6.4 Comparadores (todos con eventos independientes con resultado completo y las mismas fechas)

| Código | Pregunta | Método y población que lo identifica | Identificables en A / A′ |
|---|---|---|---|
| B0 | ¿Aporta el giro sobre estar deprimido? (D∧G frente a D sin G) | Regresión con efectos fijos por semana, controles de profundidad y fuerza relativa a 63 sesiones. Solo semanas con ambos | 118 / 277 semanas |
| B0′ | Emparejamiento descriptivo | D sin G de otro ETF a ±4 semanas y a ±5 pp de profundidad. Reutiliza parejas y mezcla semanas | 108 de 148 / 365 de 409 eventos |
| B1 | Azar | Mismo número de ETFs al azar en las mismas fechas; se da el percentil | todas |
| B2 | Momentum | Tercio superior por fuerza relativa a 63 sesiones | todas |
| B3 | ¿Importa estar deprimido? (G sin D) | Semanas con ambos | — |

- Los comparadores **no son condición** de ningún veredicto.
- **El informe distingue expresamente dos afirmaciones:**
  1. «los eventos D∧G tienen exceso positivo», que es el estimando de H1;
  2. «esperar al giro G aporta valor frente a estar solo deprimido», que es B0.
- **Solo se puede atribuir la ventaja al giro** si B0 es evaluable y su intervalo queda por encima de 0. Si B0 no es
  positivo o no es evaluable, el informe dice expresamente que la eventual ventaja **no puede atribuirse
  específicamente al giro**.
- Si en algún comparador los efectos fijos no tienen suficiente variación, se declara **no evaluable**. Los efectos
  fijos no suplen la falta de comparadores.

### 6.5 Multiplicidad

- **Familia confirmatoria (bloque C):** {H1-sectorial, H1-ampliada, H2}, con Bonferroni: α = 0,05/3 por contraste e
  intervalos de confianza al **98,33 %**.
- **Bloques A y A′ (exploratorios):** IC 95 %, sin pretensión confirmatoria.
- Horizontes secundarios, comparadores, sensibilidades, Europa y Pring: IC 95 %, solo descriptivos.

### 6.6 Efecto mínimo relevante y cómo leerlo

- **H1: +1,0 pp** de exceso neto a 40 sesiones. Es un umbral inicial.
- **Estimación ≥ +1,0 pp con el límite inferior del intervalo por encima de 0** indica un efecto positivo con una
  estimación económicamente relevante. **No demuestra que el efecto verdadero supere +1,0 pp.** Para eso el límite
  inferior tendría que ser ≥ +1,0 pp; se informa aparte de si lo es.
- **NO SOPORTADA o DESFAVORABLE** (límite superior < +1,0 pp) significa que no hay evidencia suficiente de un efecto
  de la magnitud económicamente exigida. **No significa que no exista ningún efecto positivo.**

### 6.7 Veredicto estadístico y robustez operativa, por separado

**Veredicto estadístico** (solo estimación e intervalo):

| Bloque | Positivo | Negativo | Resto |
|---|---|---|---|
| A, A′ (exploratorio, IC 95 %) | **FAVORABLE:** estimación ≥ +1,0 pp y límite inferior > 0 | **DESFAVORABLE:** límite superior < +1,0 pp | **INCONCLUYENTE** |
| C (confirmatorio, IC 98,33 %) | **SOPORTADA:** estimación ≥ +1,0 pp y límite inferior > 0 | **NO SOPORTADA:** límite superior < +1,0 pp | **INCONCLUYENTE** |

**Robustez operativa** (no es un veto científico):
- Siempre se informa de tres pruebas:
  1. estimación > 0 con el **coste triple**;
  2. estimación > 0 **sin los 5 mejores eventos**;
  3. estimación > 0 en **al menos el 75 % de las exclusiones individuales de un ETF evaluables**. Una exclusión es
     evaluable si, después de quitar ese ETF, se siguen cumpliendo los mínimos de §6.1 y §6.8.
- **ROBUSTA** si se cumplen las tres; **NO ROBUSTA** en otro caso.
- **Lectura:** SOPORTADA y NO ROBUSTA indica un efecto estadístico que no basta para uso operativo sin más
  evidencia.

### 6.8 Evaluabilidad y punto de decisión (C)

| Hipótesis | Eventos independientes **con resultado completo** | Trimestres distintos | Plazo |
|---|---|---|---|
| H1-ampliada | ≥ 60 (y ≥ 10 por nivel, §6.1) | ≥ 12 | 3 años desde 2026-W48 |
| H1-sectorial | ≥ 30 | ≥ 10 | 5 años |

- **Punto de decisión:** cuando se cumple la evaluabilidad o vence el plazo, lo que ocurra primero. El contraste se
  ejecuta una sola vez.
- **Si vence el plazo sin evaluabilidad: INCONCLUYENTE.** No se fuerza ninguna conclusión.
- **Antes del punto de decisión:** solo informes descriptivos, con eventos registrados y con resultado completo, que
  no cambian nada.

## 7. H2 — valor añadido de Cycle

### 7.1 Estimando

- Coeficiente β de concordancia en una regresión, sobre los eventos D∧G independientes con posición asignada y con
  resultado completo:
  - variable explicada: exceso a 40 sesiones;
  - variable de interés: concordante (0/1);
  - controles: profundidad (`dist_max756`), fuerza relativa a 63 sesiones, momentum a 21 sesiones y nivel;
  - en el histórico, además, efectos de año.
- **Pesos**, con el mismo principio que E_amp:
  - cada nivel suma el 50 % del peso;
  - dentro de un nivel, cada semana pesa lo mismo;
  - dentro de una semana, cada evento pesa lo mismo.
  - **Sensibilidad:** el mismo peso para cada evento.
- **Inferencia:** bootstrap de trimestres, con las comprobaciones de §6.3.
- Se informa de la correlación de la concordancia con cada control. Si la concordancia solo replica la fuerza
  relativa, el coeficiente controlado lo mostrará. Dos medidas derivadas de precios que coinciden no cuentan como
  evidencia independiente.

### 7.2 Muestra confirmatoria (C)

- Sectores con la tabla «Cycle + XLRE» e industrias con la tabla del libro, usando la Cycle real de la serie
  `cycle-copy-1`.
- **Se informa además, solo de forma descriptiva:** sectores solos, sin XLRE, sin IBB/IHI/XHS, y con el Cycle
  simplificado.

### 7.3 Efecto mínimo relevante y cómo leerlo

- **H2: +2,0 pp** de exceso a 40 sesiones. Es un umbral inicial.
- Se lee igual que en §6.6:
  - β ≥ +2,0 pp con el límite inferior por encima de 0 no demuestra que el efecto verdadero supere +2,0 pp;
  - NO SOPORTADA significa falta de evidencia de un efecto de esa magnitud, no ausencia de cualquier efecto.

### 7.4 Evaluabilidad y punto de revisión

- **Evaluabilidad:** ≥ 30 eventos concordantes **y** ≥ 30 no concordantes, todos con resultado completo y cada
  grupo repartido en ≥ 10 trimestres distintos.
- **Punto de revisión:** 30 concordantes con resultado completo, o 5 años, lo que ocurra antes.
- **Llegar al punto de revisión no garantiza potencia.** Por eso:
  - se informa del efecto mínimo detectable alcanzado, calculado con la dispersión incondicional (§9);
  - el veredicto lo deciden los intervalos de confianza.

### 7.5 Veredicto estadístico y robustez (por separado, como en §6.7)

- **Veredicto estadístico** (con la evaluabilidad cumplida):
  - **SOPORTADA:** β ≥ +2,0 pp y límite inferior del IC 98,33 % > 0.
  - **NO SOPORTADA:** límite superior del IC 98,33 % < +2,0 pp.
  - **INCONCLUYENTE:** en el resto, o si no se cumple la evaluabilidad en el punto de revisión.
- **Robustez operativa:** las tres pruebas de §6.7 aplicadas a β, con la etiqueta ROBUSTA o NO ROBUSTA.

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
  Por eso H1-ampliada combina al 50/50 las medias semanales de cada nivel (§6.1).

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
- **Exceso:** siempre frente al mismo nivel. H1-ampliada = 0,5·E_sect + 0,5·E_ind (§6.1). H2 usa el mismo principio
  de pesos (§7.1).
- **Comparadores:** informan sin decidir, en los bloques exploratorios y en el confirmatorio. Así ningún veredicto
  depende de un comparador que puede no ser identificable.
- **Puntos de decisión** (§6.8, §7.4): fijados en eventos **con resultado completo** (§6.2), trimestres y plazo. Al
  vencer el plazo sin evaluabilidad, el resultado es INCONCLUYENTE.
- **Umbrales:** el efecto mínimo relevante (+1,0 pp en H1, +2,0 pp en H2) se usa igual en el veredicto positivo y en
  el negativo, con la lectura de §6.6 y §7.3.
- **Veredicto y robustez:** el veredicto estadístico solo depende de la estimación y el intervalo. Las tres pruebas de
  robustez dan una etiqueta aparte (§6.7). Exploratorio y confirmatorio siguen la misma lógica.
- **Dependencia temporal:** bloques trimestrales como principal, con comprobación de solapes y sensibilidad de
  semestre y año (§6.3).
- **Multiplicidad:** solo afecta al bloque C (98,33 %). A y A′ usan el 95 % y nunca se llaman confirmación.
- **Cycle:** el H2 confirmatorio usa solo la serie `cycle-copy-1` con la Cycle real. El simplificado nunca sustituye a
  la real.
- **B0:** no es condición de ningún veredicto, porque en el prospectivo puede no ser identificable. Sin B0 positivo y
  evaluable, el informe no atribuye la ventaja al giro (§6.4).
