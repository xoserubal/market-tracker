# Preregistro — amplitud sectorial sobre componentes frente a la tendencia del propio ETF (v1, revisión 2)

**FIRMADO el 2026-11-11 por el usuario («dale» a las tres decisiones de §8: descarga autorizada, versión 2019-2026 aceptada, firma). Congelado desde ese momento.** Revisión 2 escrita el 2026-11-11 tras las correcciones del usuario. Ninguna
cifra de rentabilidad futura se ha calculado. El diagnóstico de datos (§2) solo mide composición, precios disponibles y
clasificación: `research/sector_breadth_v1/diag_coverage.py` → `coverage_diag.json`.
Alcance: investigación en `research/sector_breadth_v1/`. No se construye ningún motor ni se toca el Market Tracker.

Cambios respecto a la revisión 1: composición histórica reconstruida y medida (§2); muestras desplazadas a 2019-2026
por cobertura (§5); H1 con coeficientes congelados en desarrollo y prueba de exclusión de cada sector (§4); criterios
de fiabilidad por cobertura y clasificación, no por rentabilidad (§3); clasificación validado / no soportado /
inconcluyente con efecto mínimo de interés (§6); sensibilidad temporal predefinida (§6).

## 0. Pregunta y condición central
¿La evolución de la **participación interna** de un sector anticipa el rendimiento relativo futuro de su ETF **más
allá de lo que ya dice la tendencia del propio ETF**? Si no lo hace fuera de muestra, se descarta como herramienta de
detección. Ya se sabe: a nivel de ETF sectorial, Rotation Score, Relative Flow Lab y momentum no ordenan el rendimiento
futuro (2005-2026); el momentum corto de sectores se revierte en 2016-2026. La amplitud nunca se ha medido aquí.

## 1. Datos
| Pieza | Fuente | Estado |
|---|---|---|
| Componentes del S&P 500 a fecha, con sector GICS y CIK | 11 instantáneas anuales de Wikipedia (enero 2016-2026) + tabla de altas y bajas + lista actual | Descargado 2026-11-11 (`data/`) |
| Precios diarios de los miembros actuales, 11 ETFs SPDR, SPY | `research/macd_combo_filters_v1/prices_cache.parquet` | Ya descargado |
| Precios de los miembros que salieron | Yahoo | Solo se ha hecho una sonda mensual de cobertura (`data/yahoo_monthly_probe.parquet`). Falta descargar diarios para los que existen (≈ 120 símbolos, pequeño) |

## 2. Diagnóstico de viabilidad (hecho, sin rentabilidades)

**Composición histórica: recuperable.** Aplicando la tabla de cambios a la instantánea de cada enero se reproduce la del
año siguiente con un 96,5-99,4 % de coincidencia; las diferencias que quedan son cambios de símbolo (PCLN→BKNG,
HCN→WELL, KORS→CPRI…) y una errata de formato. 761 símbolos distintos pasaron por el índice entre 2016 y 2026; 258 ya no
están.

**Precios: incompletos, sobre todo al principio.** Contando los cambios de símbolo vía CIK (38 casos: FB→META, ANTM→ELV,
ABC→COR…), el % de miembros-mes con precio en Yahoo es:

| 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| 80 % | 84 % | 86 % | 88 % | 90 % | 92 % | 94 % | 96 % | 96 % | 98 % | 99 % |

Faltan ≈ 130 empresas absorbidas o deslistadas (Celgene, Anadarko, Red Hat, Twitter, Xilinx, First Republic, SVB,
Pioneer, Hess, Juniper…). Yahoo no conserva su histórico: **no se pueden recuperar con fuentes gratuitas.** Por sector,
lo peor es Energía (59 % en 2016, 74 % en 2020, 86 % en 2024) y Comunicación antes de 2023 (65-73 %).

**Clasificación GICS:** cambios importantes el 2016-08-31 (22 valores de Financieras a Inmobiliario), 2018-09-24 (15 de
Consumo discrecional y 6 de Tecnología a Comunicación) y 2023-03-17 (7 de Tecnología a Financieras, 5 a Industriales, 3
de Consumo discrecional a Básico), más unos 20 cambios sueltos. Las instantáneas dan el sector de cada año; los cambios
intraanuales tienen fecha oficial conocida.

**Clases de acciones:** 3-5 empresas con dos clases por año (GOOGL/GOOG, FOXA/FOX, NWSA/NWS, DISCA/DISCK, UAA/UA). Se
identifican por CIK.

**Consecuencia:** con un umbral de cobertura del 85 % por sector (§3), los sectores utilizables por año son:

| 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 5 | 6 | 9 | 9 | 9 | 9 | 9 | 11 | 11 | 11 |

2016-2018 no permite una comparación entre sectores con sentido. Por eso las muestras pasan a 2019-2026 (§5).

## 3. Reglas de datos y fiabilidad (fijadas antes de ver rentabilidades)

**Pertenencia:** un valor cuenta para su sector en la fecha t si es miembro del S&P 500 en t según la reconstrucción
(instantánea de enero del año + cambios con fecha ≤ t; para 2026, lista actual con *Date added*).

**Cambios de símbolo:** se enlazan por CIK con el símbolo que tiene precio. Si hay más de un candidato con precio en la
fecha, el valor se trata como sin precio (ambiguo).

**Verificación de identidad (antes del análisis):** para cada símbolo que ya no está en el índice y del que Yahoo
devuelve precios, se compara el nombre de Yahoo con el de Wikipedia y se exige que la serie cubra su periodo de
pertenencia. Si no coincide (símbolo reutilizado por otra empresa), se trata como sin precio.

**Clases de acciones:** una por empresa (CIK): la de mayor volumen monetario mediano en las 63 sesiones anteriores a t.

**Sector a fecha:** el de la instantánea de ese año; los valores afectados por las reclasificaciones oficiales
(2016-08-31, 2018-09-24, 2023-03-17) cambian de sector en esa fecha. Altas a mitad de año: sector de la siguiente
instantánea o de la lista actual. Comunicación (XLC) solo desde 2018-10-01.

**Sector fiable en la fecha t** si se cumplen todas:
1. ≥ 85 % de sus miembros efectivos (tras deduplicar clases) tienen precio en t y ≥ 63 sesiones de historia;
2. ≥ 10 miembros con precio;
3. sector conocido para ≥ 95 % de los miembros;
4. casos ambiguos o no verificados ≤ 5 % de los miembros.

Los sectores no fiables en t no entran ese día (ni como señal ni como objetivo). **Una fecha entra en el análisis si
tiene ≥ 8 sectores fiables.** Sensibilidad predefinida: umbral del 80 % (se informa siempre, no decide).
Estas reglas no usan rentabilidades futuras y quedan fijas con la firma.

## 4. Variables y pruebas

Fechas de decisión: último día bursátil de cada semana. Todo con datos hasta el cierre de t.

- **Amplitud:** P21(s, t) = % de miembros fiables del sector con retorno de 21 sesiones > el de SPY.
  **Señal: ΔP = P21(t) − P21(t−20).**
- **Tendencia del ETF (controles):** RS21 = retorno 21 ses. ETF − SPY; RS63 ídem 63; ΔRS21 = RS21(t) − RS21(t−20).
- **Objetivo:** exceso del ETF sobre SPY de la apertura de t+1 al cierre de t+H. **H = 20** (primario); 10, 40, 60
  secundarios.
- **Transformación robusta:** en cada fecha, cada variable se convierte en su rango entre los sectores fiables,
  centrado en 0 y escalado a [−0,5, 0,5]. Evita que uno o dos sectores extremos dominen con solo 8-11 observaciones.
- **Secundarias (descriptivas):** % de miembros sobre su SMA50 y su cambio; diferencial equiponderado − ETF a 21 ses.

**H1 — residualización congelada (primaria).** En desarrollo, mínimos cuadrados agrupados (todas las fechas y sectores,
sin constante porque las variables están centradas) del rango de ΔP sobre los rangos de RS21, RS63 y ΔRS21. Los tres
coeficientes se congelan. En todas las fechas: residuo = rango(ΔP) − coeficientes × rangos de los controles.
Estadístico: Spearman entre el residuo y el exceso futuro, por fecha; media de fechas; t de Newey-West con retardo 4.
Ya no se usa la regresión transversal semana a semana: con 8-11 sectores y 4 parámetros era demasiado sensible.

**H2 — modelo anidado (primaria).** En desarrollo, mínimos cuadrados agrupados del rango del exceso futuro sobre los
rangos de los controles (modelo base) y sobre los controles + ΔP (completo). Coeficientes congelados. En prueba: IC por
fecha de cada modelo; diferencia completo − base; t de Newey-West con retardo 4.

**Exclusión de cada sector (obligatoria):** H1 y H2 se repiten 11 veces quitando un sector cada vez (coeficientes
reestimados en desarrollo sin él). Se informan las 11.

**Referencias:** IC de RS21, RS63 y ΔRS21 solos; IC de ΔP sin controlar; azar.

**Lectura económica (descriptiva):** exceso a 20 ses. de los 3 sectores con mayor residuo menos los 3 con menor, por año
y por régimen (SPY sobre/bajo su SMA200), con 0,1 % de coste por cambio.

**Transiciones de liderazgo (descriptivo):** el ETF entra en los 3 primeros por RS63 tras 20 sesiones en la mitad
inferior y sigue entre los 3 primeros ≥ 15 de las 20 siguientes. Por método (residuo, ΔRS21, RS21, azar): % de
transiciones señaladas en las 40 sesiones previas, anticipación, precisión, exceso ya acumulado y exceso posterior.

## 5. Muestras y potencia
- **Desarrollo:** 2019-01-01 → 2022-12-31 (estimación de coeficientes). **Prueba:** 2023-01-01 → 2026-11-09 menos el
  horizonte, una sola vez. 2016-2018 no se usa (cobertura).
- Prueba ≈ 200 fechas semanales, ≈ 48 ventanas de 20 sesiones no solapadas, 9-11 sectores.
- **Potencia:** con ~10 sectores, el IC de una fecha tiene una desviación típica de ~0,33 bajo la hipótesis nula, de modo
  que el error de la media es ~0,05. Para detectar con un 80 % de probabilidad hace falta un IC real de **≈ 0,13 o
  más**. Los efectos medidos hasta ahora a nivel de sector rondan |IC| ≤ 0,12. **Un efecto real pero menor que ≈ 0,13
  probablemente saldrá inconcluyente.**

## 6. Clasificación
**Efecto mínimo de interés (EMI): IC = 0,05** a 20 sesiones. Por debajo no tendría valor práctico.

**VALIDADO** (en prueba, a 20 sesiones), si se cumplen todas:
1. H1: IC medio del residuo > 0 con t ≥ 2 (Newey-West, retardo 4);
2. H2: diferencia completo − base > 0 con t ≥ 2;
3. 1 y 2 con el mismo signo en desarrollo;
4. exclusión de sectores: IC de H1 positivo en las 11 repeticiones y t ≥ 1,5 en todas;
5. sensibilidad temporal: Newey-West con retardo 8 con t ≥ 2 en H1 y H2; y en datos no solapados (una fecha de cada
   cuatro, las 4 posibles rejillas) IC medio > 0 en las 4;
6. diferencial 3 primeros − 3 últimos positivo en la prueba completa y en al menos 3 de los 4 años de prueba.

**NO SOPORTADO:** el intervalo de confianza del 95 % del IC de H1 en prueba queda entero por debajo del EMI (límite
superior < 0,05). Se puede afirmar que no hay un efecto útil.

**INCONCLUYENTE:** ni validado ni no soportado. Incluye un IC positivo pero impreciso, o que solo cumple algunos
criterios. **No se presenta como refutación**: significa que con estos datos no se puede saber. Tampoco se promueve a
producción.

Además: si en más de 2 sectores la verificación de identidad deja casos sin resolver por encima del 5 %, o si la prueba
tiene menos de 150 fechas con ≥ 8 sectores fiables, el resultado es INCONCLUYENTE por datos.

Reglas comunes: la especificación primaria es la que decide; las sensibilidades (umbral 80 %, retardos, rejillas no
solapadas, horizontes 10/40/60) se informan todas y no se puede escoger a posteriori la más favorable. No se probarán otras
definiciones de amplitud, ventanas ni umbrales sobre estos datos.

**Alcance de cualquier resultado:** sin el histórico de las empresas que salieron del índice, un VALIDADO solo vale
para 2023-2026 y los sectores con cobertura ≥ 85 %. No se presentará como ventaja predictiva general hasta replicarlo con
datos completos (incluidos los deslistados) o en un periodo nuevo.

## 7. Fuera de alcance de v1
Industrias (las instantáneas traen subindustria GICS, pero no hay ETFs de industria para el control), otros mercados, el
universo propio de 130 tickers y cualquier cambio en Market Tracker, pipeline o carteras.

## 8. Pendiente antes de firmar
1. Autorizar la descarga diaria de Yahoo de los ≈ 120 símbolos que ya no están en el índice pero tienen precio (pequeña)
   y la verificación de nombres (≈ 120 consultas).
2. Decidir si se acepta la versión 2019-2026 con la potencia de §5, o si antes se valora un proveedor con histórico de
   deslistados para recuperar 2016-2018 y ampliar el periodo (sería la única forma de ganar potencia de verdad).
3. Firmar: desde entonces quedan congelados reglas, horizontes, umbrales y criterios.

## 9. Firma y datos descargados
- Firmado el 2026-11-11. La huella SHA-256 de este documento se guarda en
  `research/sector_breadth_v1/PREREGISTRO.sha256` antes de calcular ninguna variable del estudio.
- Descarga autorizada hecha antes de la firma: precios diarios de 113 de los 120 símbolos que ya no están en el índice
  y tienen datos en Yahoo (7 recientes, deslistados en 2026, no devuelven diarios) y nombres de Yahoo de 118.
