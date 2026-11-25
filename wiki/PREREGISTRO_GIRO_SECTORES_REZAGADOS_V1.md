# PREREGISTRO — Giro de sectores deprimidos v1

> **BORRADOR, SIN FIRMAR (2026-11-25).** No se ha calculado ningún resultado. Los puntos marcados
> **[DECIDIR]** los fija el usuario antes de firmar. Al firmar se guarda la huella (sha256) de este
> fichero y se ejecuta una sola vez.

## 0. Origen y por qué es otra pregunta

El usuario recorre Cycle → Flujos & Rotación → Relative Flow y recuerda haber visto girar sectores
que estaban «abajo» sin actuar: Real Estate (~sep-2026), Salud (~30-sep), Staples (~8-oct). Los tres
subieron después.

La versión mecánica de ese recorrido **ya está probada y no funciona**: sector líder del régimen +
alfa de ciclo positivo + señal de compra de Flujos & Rotación + flow change (research/sector_confluence_v1,
NO SOPORTADO). Pero esos tres casos no son líderes: son sectores **deprimidos que empiezan a girar**.
Esa hipótesis no se ha probado.

Al operacionalizar «abajo» se comprobó que, por fuerza relativa a 3, 6 o 12 meses, **ninguno de los
tres era un rezagado** (Salud era el 2.º de 11 a 3 y 6 meses). Lo que los tres tenían en común es estar
muy por debajo de su máximo de 3 años frente a SPY (Salud −26,5 %, Staples −31,1 %, Real Estate −29,8 %).
La definición de §3 sale de ahí: **se eligió mirando estos tres casos** (exposición, §9).

## 1. Hipótesis

- **H1 (giro de deprimido).** Un sector deprimido (D) que empieza a girar (G) rinde más que la media de
  los sectores en las 40 sesiones siguientes.
- **H2 (lo que toca por ciclo).** Entre los eventos D∧G, los del sector de la **fase siguiente** a la
  fase dominante de Cycle rinden más que los demás.
- **Secundarias (descriptivas, no deciden):** ¿el giro añade algo a estar deprimido (D∧G frente a D
  sin G)? ¿Importa estar deprimido (D∧G frente a G sin D)?

## 2. Universo, datos y ejecución

- **Desarrollo (EE.UU.):** los 11 SPDR sectoriales frente a SPY, 1998-12 → hoy (XLRE desde oct-2015,
  XLC desde jun-2018). Yahoo, precios ajustados.
- **Confirmación (Europa):** los 19 ETFs iShares STOXX Europe 600 sectoriales (Xetra, EXV1-EXV9,
  EXH1-EXH9, EXI5) frente a EXSA.DE (STOXX 600), 2008 → hoy. Nunca se han usado en este proyecto para
  rotación sectorial.
- **Decisión semanal:** último cierre de la semana. Entrada al cierre de la sesión siguiente.
  Coste 0,1 % ida y vuelta.
- Primer evento posible: 3 años después del inicio de cada serie (hace falta el máximo de 3 años).

## 3. Definiciones (se congelan al firmar)

- **Deprimido (D):** el ratio SECTOR/índice está ≥ 20 % por debajo de su máximo de las 756 sesiones
  previas (3 años), con datos hasta la decisión. **[DECIDIR]** alternativa: percentil ≤ 20 del ratio en
  su rango de 3 años.
- **Giro (G):** el ratio cierra la semana por encima de su media de 50 sesiones, tras haber cerrado la
  semana anterior por debajo. **[DECIDIR]** alternativas: flow change de RFL cruza de ≤ 0 a > 0 en la
  semana; o pasa a Improving en RFL. (Se elige UNA como principal; las otras, solo descriptivas.)
- **Evento:** D∧G. Independiente si el mismo sector no tuvo otro evento en las 8 semanas anteriores.
  Las métricas principales usan solo eventos independientes.
- **Fase de Cycle (solo H2):** puntuación de cada fase = media del alfa (0,7 × exceso a 63 sesiones +
  0,3 × exceso a 21 sesiones frente a SPY, la fórmula de cycle.html) de sus **ETFs proxy**, no de las
  cestas de acciones (las cestas actuales se eligieron en 2026: mirarían al futuro). Fase dominante = la
  de mayor puntuación. Posiciones narrativas: P1 Early Bull · P2 Early→Mid · P3 Mid→Late · P4 Late Bull ·
  P5 Top (Oil & Gas, Uranio, Carbón) · P6 Early Bear · P7 Late Bear aprox. · P8 Late Bear. «Siguiente» =
  P+1 (P8 → P1).
- **Fase → sector SPDR:** P1 XLI (transporte) · P2 XLK · P3 XLI · P4 XLB · P5 XLE · P6 XLP y XLV ·
  P7 XLU · P8 XLF y XLY. XLRE y XLC no tienen fase: solo entran en H1.
  En Europa: equivalencia por sector (XLK→EXV3, XLV→EXV4, XLP→EXH3/EXH7, XLE→EXH1, XLU→EXH9,
  XLF→EXV1/EXH2/EXH5, XLI→EXH4/EXV8, XLB→EXV6/EXV7, XLY→EXV5/EXV9/EXH8, XLC→EXV2/EXH6, XLRE→EXI5) con la
  fase calculada en EE.UU. (supone un ciclo común). **[DECIDIR]** si H2 entra en la confirmación o se
  queda solo en EE.UU.

## 4. Medida

- **Principal:** exceso a 40 sesiones = retorno del sector − media de los sectores disponibles en las
  mismas fechas, neto de coste.
- **Secundarios:** 20 y 60 sesiones.
- **Error:** IC 95 % por bootstrap por bloques de fechas (los eventos de un mismo mes están correlacionados).

## 5. Comparaciones

- **B0:** D sin G (comprar deprimidos sin esperar al giro: reversión pura).
- **B1:** azar: el mismo número de sectores elegidos al azar en las mismas fechas (percentil de H1).
- **B2:** el tercio superior por fuerza a 63 sesiones (momentum).
- **B3:** G sin D (el giro en cualquier sector).
- **H2:** D∧G de la fase siguiente frente a D∧G del resto.

## 6. Criterios (Bonferroni para H1 y H2: α = 0,025)

H1 queda **SOPORTADA** si en la confirmación europea:
1. el exceso a 40 sesiones es ≥ +1 pp y su IC 97,5 % excluye el 0;
2. tiene el mismo signo en el desarrollo de EE.UU.;
3. supera a B0 (el giro aporta algo frente a comprar deprimidos sin más);
4. no depende de un sector: positivo en al menos 3 de cada 4 exclusiones de un sector.

**INCONCLUYENTE** si el exceso es positivo pero no cumple 1, o cumple 1 pero falla 3 o 4.
**NO SOPORTADA** en el resto. H2, igual pero frente a los D∧G del resto.

## 7. Potencia (recuento sin mirar resultados)

Con D y G tal como están en §3: **EE.UU. 271 eventos, 153 independientes** (concentrados: XLE 27,
XLU 32, XLP 21, XLF y XLV 15); **Europa 293 eventos, 179 independientes**. Con unos 150-180
independientes, un exceso de +1 pp a 40 sesiones solo se detecta si la dispersión es moderada: lo
esperable, salvo efecto grande, es INCONCLUYENTE.

## 8. Fuera de alcance

- Selección de acciones dentro del sector: solo si H1 o H2 quedan SOPORTADAS, con su propio preregistro.
- Ningún cambio en producción, carteras, PCS ni pestañas.
- No se cambian umbrales ni definiciones después de ver resultados.

## 9. Exposición declarada

- La definición de D se eligió mirando tres casos de 2026 que salieron bien (§0).
- Los SPDR de EE.UU. ya se han mirado de muchas formas: confluencia sectorial (2006-2026), RFL
  (score↔alfa 1998-2026, inversión del flow change a 1-4 semanas, registro de señales 2016-2026 con
  `to_improving` y saltos del flow change por régimen), amplitud sectorial (2019-2026). Por eso el
  desarrollo es EE.UU. y la confirmación, Europa.
- Los ETFs europeos solo se usaron sueltos (EXV5.DE como referencia de un ratio de ADS.DE), nunca en
  un estudio de rotación.
- Prospectivo, aparte: el diario sectorial (`/sector`, desde 2026-11-25) mide lo que ve el usuario. No
  es la misma regla, así que no confirma H1; se informa al lado.
