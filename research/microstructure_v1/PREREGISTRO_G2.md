# Microestructura v1 — Preregistro G2 (versión para aprobación, 2026-11-15)

**Estado: borrador para tu aprobación.** No se ha calculado ninguna variable candidata ni ningún resultado. El
periodo de prueba sigue cerrado.

El preregistro se cierra en dos pasos, y cada uno necesita tu aprobación:
1. **Ahora:** apruebas el marco. Queda fijado todo lo que no depende de explorar:
   - partición;
   - ejecución y resultados;
   - familias e hipótesis con su dirección;
   - inferencia;
   - criterios de decisión;
   - sensibilidades;
   - exclusiones;
   - **la regla con la que se fijarán los parámetros abiertos**.
2. **Tras la exploración en desarrollo:** se rellenan los parámetros abiertos (§8) aplicando esa regla, se congela
   el documento con su hash y lo apruebas. Solo entonces se abre la prueba, una vez.

Si no apruebas un cambio respecto a la [propuesta de G2](G2_PROPUESTA.md), vale la propuesta. Diferencias con ella:
- las variables de agresor pasan a exploratorias;
- H-B1 se reformula sin agresor;
- se añade el tratamiento de salidas;
- se añade la política de exclusión.

## 1. Pregunta

¿Las huellas observables en lo ejecutado permiten anticipar acumulaciones silenciosas y sus rupturas **antes** de
que las detecte el momentum convencional? Las huellas son:
- dónde se negocia el volumen dentro de un rango;
- cuánto se mueve el precio por unidad de volumen;
- si esas concentraciones persisten y migran.

Se mide la **asociación** con lo que pasa después. No se concluye quién compró ni con qué intención.

## 2. Datos y partición

- **Universo:** S&P 500 a fecha (con empresas que salieron) más los valores de EE. UU. del proyecto. Identidad por
  CIK y épocas de ticker (README §4).
- **Fuentes:**
  - nivel A: barras de 1 minuto, todo el universo;
  - piloto B1: ticks, 200 bloques × 100 sesiones, plan **v2**;
  - quotes: 20 bloques × 20 sesiones;
  - barras diarias para los resultados.
- **Desarrollo:** fechas de decisión 2017-01-03 → 2021-10-29.
- **Embargo:** 40 sesiones.
- **Prueba:** 2022-01-03 → 2026-09-14.
- **Después:** la captura prospectiva (desde la aprobación final) es una confirmación independiente, no parte de
  esta prueba.
- 2016 solo aporta historia previa.

## 3. Decisión, ejecución y costes

- Las variables se conocen tras el cierre de t (más el retraso de los datos). Se entra a la apertura de t + 1 y se
  sale al cierre de t + h.
- **Costes de ida y vuelta (propuesta, pendiente de tu aprobación):** 0,2 % en general y 0,5 % en el tercil de
  liquidez más bajo. Sensibilidad con el doble.

## 4. Resultados

- **Horizontes:**
  - 20 y 40 sesiones para la familia C (principal: 40);
  - 5 y 10 para las familias A y B (principal: 10).
- **Exceso:** rentabilidad del valor menos la del SPY en la misma ventana. En C, además, frente a controles
  emparejados (§7).
- **Salidas de cotización:** se aplica la regla de `plan_exits_v2` ([G2_CAMBIOS.md](G2_CAMBIOS.md) §1). La
  observación nunca se descarta; se informa la sensibilidad excluyéndolas.

  | Tipo de salida | Resultado |
  |---|---|
  | Efectivo | Se cobra el precio de la operación y el resto del horizonte rinde 0 |
  | Acciones | Se sigue al comprador |
  | Quiebra | −30 %, con sensibilidad de 0 % y −100 % |
- **Ajustes:** splits y dividendos en la capa de variables y resultados. Los trades se guardan sin ajustar.

## 5. Referencia convencional (lo que la señal tiene que superar)

- momentum a 5 y 20 sesiones;
- fuerza relativa a 63 sesiones frente al SPY y frente a su sector;
- volumen relativo;
- extensión respecto a la SMA20 en ATR;
- azar emparejado.

Se mide la información **incremental** sobre todos ellos.

Recordatorio del proyecto: a 5-20 sesiones la fuerza relativa a 3 meses tiene un efecto propio de reversión, de
−0,4 a −0,6 pp.

## 6. Variables

**Prioritarias (sin lado agresor; entran en las hipótesis):**
1. **Volumen por precio.** Concentración del volumen dentro del rango de las últimas L sesiones, medida con dos
   cosas:
   - índice de concentración del volumen por nivel;
   - anchura del área de valor (70 %) frente al rango.
2. **Desplazamiento relativo al volumen.** Variación del precio por unidad de volumen relativo, diaria e intradía.
   «Actividad sin desplazamiento» = mucho volumen frente a la historia propia con poco avance del precio, poco
   rango y cierre cerca del VWAP.
3. **Persistencia.** Fracción de sesiones anómalas en las últimas 10 y 20.
4. **Evolución de las concentraciones.** Desplazamiento del punto de máximo volumen y del área de valor dentro del
   rango (por ejemplo, si migran hacia la parte alta).

Todas se expresan **frente a la historia propia del valor** (percentil o z frente a sus sesiones previas), no en
niveles absolutos: la composición del mercado (TRF, odd lots) cambia con los años.
- En el nivel A se calculan con barras de 1 minuto. El volumen por precio es una aproximación que se declara como
  tal.
- En B1 se calculan exactas con ticks.

**Exploratorias (no entran en ninguna hipótesis principal):**
- Lado agresor: delta, desequilibrio comprador/vendedor, absorción inferida.
- En B1 el método disponible a escala es la regla del tick, con estas variantes obligatorias:
  - TRF en la secuencia o fuera;
  - solo trades que actualizan barras;
  - sin odd lots.
- Lee-Ready y EMO solo se pueden comparar en la submuestra de quotes.
- Para proponer una variable de agresor como confirmatoria en una ronda futura tiene que cumplir dos condiciones en
  desarrollo:
  - el mismo signo con todas las variantes;
  - valor incremental sobre las prioritarias.

## 7. Hipótesis principales (4, Bonferroni ×4)

**Familia C — acumulaciones silenciosas (prioridad).**

Población elegible en t, solo con datos ≤ t:
- **lateral:** rango máximo-mínimo de los últimos L cierres ≤ k × ATR;
- **sin momentum:**
  - fuerza relativa a 63 sesiones ≤ 0;
  - sin máximo de 52 semanas en las últimas 20 sesiones;
  - por debajo de los umbrales de Flow y Early Flow del sistema.

Como el momentum aún no ha disparado en t, cualquier ventaja es, por construcción, anticipación sobre él.

- **H-C1.** Dentro de esa población, el tercil superior de anomalía persistente (§6, puntos 1-4) tiene **mayor
  exceso a 40 sesiones** que controles laterales sin anomalía.
  - Los controles se emparejan por fecha, sector, tercil de liquidez, anchura del rango y duración de la
    lateralidad.
  - Secundario: 20 sesiones.
- **H-C2.** El mismo grupo tiene **mayor probabilidad de ruptura alcista** que esos controles: cierre por encima
  del máximo del rango en las 40 sesiones siguientes, sin volver dentro en las 5 posteriores.
- **Descriptivo de anticipación**, sin contraste: en las rupturas, sesiones entre t y el primer disparo del
  momentum convencional (fuerza relativa a 63 sesiones > 0 o máximo de 20 sesiones).

**Familia A — barras de 1 minuto, todo el universo.**
- **H-A1.** La actividad sin desplazamiento (§6, punto 2) aporta información incremental sobre la referencia a 10
  sesiones. Dirección prevista: positiva.

**Familia B — ticks sobre B1 (sin agresor).**
- **H-B1.** El volumen por precio y su concentración calculados con ticks añaden información a 10 sesiones sobre
  los mismos calculados con barras de 1 minuto.
- Potencia: con ~1 200 observaciones no solapadas el IC mínimo detectable es ≈ 0,10 con Bonferroni ×4. **Si el
  desarrollo no justifica un efecto de ese tamaño, H-B1 se declara exploratoria antes de abrir la prueba** y la
  corrección pasa a ×3.

## 8. Parámetros abiertos y cómo se fijan (solo con desarrollo)

| Parámetro | Valores candidatos |
|---|---|
| L (duración de la lateralidad) | {40, 120} |
| k (anchura máxima del rango) | 3 valores, fijados en desarrollo como los percentiles 20, 35 y 50 de su distribución (antes de mirar resultados) |
| Umbral de «sesión anómala» | percentil 80 o 90 de la historia propia |

Fijos, sin elegir: normalización frente a las 120 sesiones previas e índice de anomalía con igual peso de los
cuatro componentes.

Reglas:
- **Rejilla congelada aquí: 2 × 3 × 2 = 12 combinaciones por familia.** Elegir de una rejilla cerrada evita
  ajustar a mano.
- **Criterio de elección:** mediana del IC (o de la diferencia frente a controles) por año de desarrollo. Se exige
  el mismo signo en al menos 4 de los 5 años y en las dos mitades (2017-2019 y 2020-2021).
- Se informan todas las combinaciones, no solo la elegida.
- **Si ninguna cumple, la hipótesis no se lleva a la prueba:** queda como resultado negativo en desarrollo.
- Lo fijado se escribe en este documento y se congela con hash antes de abrir la prueba.

## 9. Inferencia y criterio de decisión

- **Familias A y B:**
  - IC transversal por fecha (Fama-MacBeth);
  - errores Newey-West con retardo igual al horizonte;
  - prueba principal con observaciones no solapadas;
  - el n efectivo se declara aparte del nominal.
- **Familia C:** diferencia frente a controles emparejados, con errores agrupados por fecha. El n se cuenta por
  episodio lateral, no por valor-día.
- **SOPORTADA** si se cumplen las cuatro condiciones:
  - p < 0,05/4 en la prueba;
  - el efecto supera el mínimo de interés: +0,5 pp de exceso neto de costes por operación en C, e IC ≥ 0,03 en A
    y B;
  - el mismo signo en las dos mitades de la prueba;
  - sobrevive a las sensibilidades del §10 sin cambiar de signo.
- **NO SOPORTADA** si el intervalo excluye el mínimo de interés o el signo es contrario.
- En cualquier otro caso, **INCONCLUYENTE**.
- Un resultado negativo bien contrastado se publica y cierra la hipótesis.

## 10. Sensibilidades obligatorias

- TRF dentro o fuera;
- odd lots dentro o fuera;
- trades que no actualizan barras dentro o fuera;
- las variantes del agresor (solo en las exploratorias);
- tratamiento de las salidas: con la regla, excluidas, y −30/0/−100 %;
- sin las ventanas E1;
- costes ×2;
- por tercil de liquidez;
- control por año o cuota de TRF;
- régimen del SPY: por encima o por debajo de la SMA200.

## 11. Protección del conjunto confirmatorio

Se aplica la política proporcionada de [G2_CAMBIOS.md](G2_CAMBIOS.md) §3 (`micro/exposure.py`):
- **Ventanas:** se excluyen las de los valores con exposición E2/E3, con la L y la H finales; por ahora, 628
  valor-sesiones únicas de 51 valores (corregido el 2026-11-16, ver G2_CAMBIOS §3 y `test_exclusion_audit.csv`).
- **E1:** se mantienen las 240 sesiones E1 y se informa la sensibilidad sin ellas.
- **Exploración:** se hace solo con fechas de decisión de desarrollo, y cualquier acceso a la prueba queda
  registrado.
- **Método elegido con la prueba:** cualquier método o parámetro elegido con información de la prueba hace
  exploratoria la hipótesis.

## 12. Qué no permite concluir

- No demuestra compras institucionales ni ningún mecanismo: es una asociación.
- No convierte ningún patrón visual en señal de inversión.
- Una hipótesis SOPORTADA pasaría a la captura prospectiva en sombra, nunca directamente a una cartera.

## 13. Pendiente de tu aprobación

1. El marco de este documento (§1-§12).
2. Los costes del §3.
3. La rejilla y la regla de selección del §8.
4. La descarga de las barras diarias de los horizontes que faltan (CZR, 7 sesiones; y las que salgan al calcular
   resultados).
