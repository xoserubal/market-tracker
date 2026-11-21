# Flow negativo v3 — informe de cierre

**Estado: CERRADO, 2026-11-21. Veredicto confirmatorio: NO SOPORTADO.** Aceptado por el usuario el mismo día.

Este documento resume la investigación. El detalle vive en los documentos enlazados; las cifras confirmatorias, en
`data/etapa2_resultados.json` (SHA-256 `d512b1b5…`). Nada de lo que sigue cambia un resultado ni un criterio posterior
a la apertura de la prueba. La única cifra nueva es la comprobación del embargo de §8.2, que aplica una regla ya
aprobada antes de la apertura.

## 1. Pregunta e hipótesis

**Pregunta** (preregistro v3 §0): ¿qué ocurre después de cada nivel negativo del Flow Score? ¿Cambia según tamaño,
liquidez y régimen? ¿Aporta el Flow información sobre el futuro más allá de la caída previa del precio?

Cada nivel y segmento debía acabar en una de tres lecturas: reversión (posible oportunidad), continuación bajista
(peligro) o descripción de una caída ya producida. No se buscaba una estrategia ni se tocaba producción.

**Hipótesis contrastadas en la prueba:**
- **H1** (preregistro §6), por talla: grandes, medianas y pequeñas. Entre empresas con caídas parecidas a 5 y 21
  sesiones, el resto del Flow (R = RSI, MACD, ATR, Koncorde, distancia al máximo) ¿distingue resultados futuros?
  Se confirma si se cumplen las dos condiciones:
  - |D| ≥ 0,5 pp con su intervalo sin el 0;
  - media de ΔIC(M1 − M0) > 0 con su intervalo sin el 0.
- **Celdas elegidas en desarrollo** (preregistro §7):
  - principal: grandes / episodio Flow < −30 / 20 sesiones / todos los regímenes;
  - anidada: la misma señal solo en régimen lateral.
  - Se confirma cada una con mismo signo que en desarrollo, |exceso| ≥ 0,5 pp e intervalo sin el 0.
- **Nivel y forma:** 5 contrastes, Bonferroni 0,05 / 5 = 0,01 por contraste, intervalos al 99 % por bootstrap de
  bloques de 60 sesiones (D: bloques de 3 meses), 2 000 réplicas.

Universo: empresas que han pertenecido al S&P 500, 400 o 600, desde su primera pertenencia hasta que dejan de cotizar
(2 083 empresas desde 2018). Talla por capitalización en la fecha de la señal. Entrada a la apertura de t+1. Exceso
frente a la media de la talla ese día.

## 2. Documentos, enmiendas y fechas

| Fecha (UTC) | Hito | Documento / congelación |
|---|---|---|
| 2026-11-18 | Diagnóstico y borradores v1-v2; etapa 0 (universo por índices, luego por empresa) | `wiki/DIAGNOSTICO_FLOW_NEGATIVO_V1.md`, `ETAPA0_INFORME.md`, `ETAPA0_V3_INFORME.md` |
| 2026-11-19 | Universo v4 (S&P 400 desde carteras de ETF de la SEC); periodos por talla | `D2_VIABILIDAD_Y_V4.md` |
| 2026-11-20 | **Preregistro v3 firmado** | `wiki/PREREGISTRO_FLOW_NEGATIVO_V3.md`, `data/preregistro_v3_freeze.json` |
| 2026-11-20 12:12 | Etapa 1, tanda 1 (desarrollo 2018-2020) congelada | `ETAPA1_TANDA1_INFORME.md`, `data/etapa1_tanda1_frozen.json` |
| 2026-11-20 13:38 | **Enmienda 1** (precios, identidad, desenlaces, embargo), aprobada con modificaciones | `wiki/ENMIENDA_1_FLOW_NEGATIVO_V3.md`, `data/enmienda1_freeze.json` |
| 2026-11-20 18:26 | **Enmienda 2** (base corregida c2, regla §7, acciones de varias clases) | `wiki/ENMIENDA_2_FLOW_NEGATIVO_V3.md`, `data/enmienda2_freeze.json` |
| 2026-11-21 00:12-00:18 | Panel c2; tandas 1 y 2 con c2 congeladas | `data/version_c2_freeze.json`, `data/etapa1_tanda{1,2}c2_frozen.json` |
| 2026-11-21 | Selección de celdas (opción a: dos celdas, la segunda anidada) | `ENMIENDA2_INFORME.md` |
| 2026-11-21 02:09 → 09:49 | Preparación de la etapa 2, complementos y correcciones técnicas | `ETAPA2_PREPARACION.md`, `data/etapa2_preparacion_freeze_v1…v4.json` y la final |
| 2026-11-21 09:49-09:54 | **Apertura única de la prueba** (cuarto intento; los tres anteriores murieron sin resultados, §8) | `ETAPA2_RESULTADOS.md`, `data/etapa2_acceso.jsonl` |

**Las dos enmiendas son posteriores a ver resultados de desarrollo de la tanda 1**, y así lo declaran. Ninguna
cambió umbrales ni puertas de selección:
- **Enmienda 1:** corrigió errores de datos que esa inspección destapó:
  - 14 contrasplits no aplicados, que daban rendimientos de +21 600 %;
  - 7 tickers transferidos a escindidas;
  - 45 tramos de CIK;
  - la valoración de escisiones.
- **Enmienda 2:** volvió a los desenlaces desconocidos del preregistro y añadió una cota de capitalización para
  acciones de varias clases.

## 3. Desarrollo y prueba, por separado

### 3.1 Desarrollo (2018-2020 para grandes, medianas y sin capitalización; 2018-2022 para pequeñas y micro)

| | Episodios | Semanas | Exceso a 20 ses. | t (NW) |
|---|---:|---:|---:|---:|
| Candidata original, v4 | 739 | 96 | +2,05 pp | 2,70 |
| Candidata tras enmienda 1, c1 | 767 | 100 | +2,13 pp | 2,57 |
| **Principal, c2 (la evaluada)** | **805** | **101** | **+2,11 pp** | **2,57** |
| **Anidada lateral, c2** | **147** | **31** | **+1,97 pp** | **2,58** |

- Tanda 2 (pequeñas y micro): 48 candidatas, 0 elegibles.
  - Lo más fuerte: micro / bajista / Flow < −30, con exceso negativo (t −3,1/−3,3). No pasó por tener un 1,4-2,3 % de
    desenlaces desconocidos.
- H1 no tiene contraste en desarrollo: allí se estimaron M0 y M1, así que cualquier cifra de H1 en desarrollo está
  dentro de muestra y no significa nada.

### 3.2 Prueba (2021-01-04 → 2026-09-17 grandes y medianas; 2023-01-03 → 2026-09-17 pequeñas)

2 030 679 filas utilizables. Desenlaces desconocidos en las dos celdas: 0 %.

## 4. Los cinco contrastes confirmatorios

| # | Contraste | Estimación | IC 99 % | Veredicto |
|---|---|---|---|---|
| 1 | H1 grandes (268 974 obs., 69 meses, 1 419 días de IC) | D −0,13 pp · ΔIC −0,0027 | D −0,53 a +0,21 · ΔIC −0,011 a +0,006 | no confirmado |
| 2 | H1 medianas (318 704 obs., 69 meses) | D −0,23 pp · ΔIC +0,0021 | D −0,60 a +0,11 · ΔIC −0,002 a +0,006 | no confirmado |
| 3 | H1 pequeñas (152 481 obs., 45 meses) | D −0,28 pp · ΔIC +0,0033 | D −0,70 a +0,13 · ΔIC −0,002 a +0,009 | no confirmado |
| 4 | Principal (1 851 episodios, 542 empresas, 241 semanas) | exceso −0,11 pp (t −0,22) | −1,38 a +1,20 | no confirmado |
| 5 | Anidada lateral (354 episodios, 227 empresas, 65 semanas) | exceso −0,16 pp (t −0,29) | −1,09 a +0,69 | no confirmado |

- Las dos celdas cambian de signo frente al desarrollo y quedan lejos del umbral de 0,5 pp.
- Lectura de §8 para ambas: «descripción de la caída».
- Las cotas terminales (−0,10/−0,11 y −0,15/−0,16 pp) y los saltos de precio tal cual o anulados dan lo mismo.

## 5. Rentabilidad absoluta, exceso frente a la talla y costes

Celda principal, 20 sesiones, coste del 0,2 % ida y vuelta (grandes). Análisis complementario, congelado antes de abrir
la prueba; no decide.

| Medida | Bruta | Neta de costes |
|---|---:|---:|
| Rentabilidad absoluta, media por episodio | +3,09 % | +2,89 % |
| Rentabilidad absoluta, media diaria (IC 99 % −0,61 a +2,69) | +1,03 % | +0,83 % |
| Episodios con rentabilidad absoluta positiva | 59,8 % | 59,2 % |
| Exceso frente a la talla, media diaria (la medida que decide) | −0,11 pp | −0,31 pp |
| Episodios con exceso positivo | 52,2 % | 51,3 % |
| Frente al SPY, media | +0,51 pp | — |

- **La rentabilidad absoluta positiva no es una ventaja de la señal.** Es la subida de las grandes en 2021-2026: frente
  a su talla, el exceso es nulo, y negativo tras costes.
- Un exceso relativo positivo tampoco habría demostrado por sí solo una reversión rentable. Aquí ni siquiera lo hay.
- La media por episodio es mayor que la diaria porque da más peso a los días con muchos episodios a la vez; la decisión
  preregistrada usa la diaria.
- Celda lateral: absoluta bruta +1,35 % por episodio (+1,02 % diaria); exceso diario −0,16 pp bruto y −0,36 pp neto;
  52,8 % de episodios positivos en absoluto.

## 6. Resultados adversos y limitaciones

**Recorrido adverso** (celda principal; la lateral es casi igual):
- Excursión adversa máxima antes de las 20 sesiones: mediana −6,4 %, media −8,6 %, percentil 10 −19,3 %.
- El 33 % de los episodios llega a ir un 10 % en contra y el 9 %, un 20 %.
- Tras la señal, el 83 % marca un nuevo mínimo de 20 sesiones, frente al 44 % de días comparables sin ella.
  Su percentil 10 a 20 sesiones es −12,6 %, frente a −9,4 %.
- **Atribución** frente a días comparables sin la señal: principal −0,59 pp (IC −1,59 a +0,38); lateral −0,90 pp
  (IC −1,74 a +0,01). La versión estricta de la lateral, con comparadores también laterales, da −0,74 pp (IC −2,06 a
  +0,60). Todo apunta a algo peor que los días comparables, sin ser significativo en las versiones principales.

**Limitaciones:**
- **Universo:** empresas que han estado en un índice S&P. Faltan unas 260 pequeñas del S&P 600 de 2015-2019 que nunca
  estuvieron en otro índice, en su mayoría desaparecidas. La lista de Wikipedia del S&P 600 no se usa antes del
  17-dic-2019.
- **Precios:** los de Alpaca (SIP desde 2016), sin precios OTC. Los términos de fusión anteriores a 2020 se toman del
  último cierre.
- **Capitalización:** acciones en circulación de la SEC por fecha de presentación. Las de varias clases solo tienen una
  cota inferior, que solo permite asignar «grande».
- **Un solo periodo de prueba,** con un mercado mayoritariamente alcista para las grandes. No se ha comprobado en otro
  régimen largo.
- **Estadística:** las celdas anidadas no son independientes (147 de los 805 episodios de desarrollo de la principal
  son la lateral). Con 126 días de señal en la lateral y bloques de 60, el bootstrap tiene poca resolución.
- **Datos excluidos:** no se reconstruyeron las empresas sin precio de salida; sus valores-día quedan fuera del
  principal según el preregistro §4.2 y la enmienda 2.

## 7. Sensibilidades exploratorias (no confirmatorias)

**Ninguna de estas cifras decide nada ni puede usarse como hallazgo.** Se eligieron sin corrección por comparaciones
múltiples entre unas 50 variantes.
- **H1:** población B, celdas diarias, talla retrospectiva, cotas terminales, plazos de 5/10/40 sesiones y subperiodos.
  Todas «no confirmado», salvo H1 pequeñas a 40 sesiones: ΔIC +0,0061 (IC +0,0009 a +0,011) con D ≈ 0, «evidencia
  parcial».
- **Celdas:**
  - principal a 5/10/40 sesiones: −0,19 / +0,07 / +0,05 pp;
  - lateral a 5/10/40 sesiones: +0,16 / **+0,96** (IC +0,21 a +1,63) / +0,70 pp;
  - entrada al cierre de t+1: −0,07 / −0,15 pp;
  - costes ×2 y ×3 (neto): principal −0,51 / −0,71 pp, lateral −0,56 / −0,76 pp.
- **Periodo común limpio** (señales desde el 2-mar-2023, que ningún desarrollo vio):
  - H1 grandes: D −0,08 pp, ΔIC −0,0048;
  - H1 medianas: D −0,11 pp, ΔIC +0,0019;
  - celda principal +0,06 pp (IC −1,87 a +1,91); lateral −0,07 pp (IC −1,45 a +1,29);
  - absoluta bruta diaria +1,15 % y +1,45 %, con intervalos que incluyen el 0.
- **Expresamente no se rescatan** la lateral a 10 sesiones ni H1 pequeñas a 40 como señales nuevas.

## 8. Incidentes técnicos, accesos y reproducibilidad

### 8.1 Accesos al conjunto de prueba (`data/etapa2_acceso.jsonl`)

| Hora (UTC) | Congelación | Qué pasó |
|---|---|---|
| 09:13 | v2 `9e1472a8…` | Construyó las filas en memoria; murió por memoria al empezar H1. Sin cifras |
| 09:26 | v3 `6956600f…` | Murió por memoria al construir los desenlaces. Sin cifras ni filas guardadas |
| 09:35 | v4 `a40dfafe…` | Guardó las filas (`c07cef34…`); murió por memoria en H1. Sin cifras |
| 09:49-09:54 | v5 `093cb385…` | Reutilizó esas filas tras comprobar su hash; resultados `d512b1b5…` |

- **Causa:** las demás aplicaciones del equipo ocupaban unos 15 GB de memoria comprometida y dejaban menos de 5 GB.
- **Arreglos, ninguno cambia cálculos:**
  - sin copias completas de la tabla;
  - desenlaces por tandas de empresas;
  - lectura solo de las columnas usadas.
- **Comprobación de cada arreglo:** el ensayo de desarrollo, byte a byte, y la reconstrucción de las 833 902 filas de
  desarrollo, columna a columna.
- **Detalle:** `ETAPA2_PREPARACION.md` §8 quater.

### 8.2 Error de ejecución encontrado al cerrar: el embargo de la enmienda 1

- La enmienda 1 §9 fija un embargo de 40 sesiones tras el último cierre de desarrollo:
  - prueba propia de grandes y medianas desde el 2021-03-03;
  - prueba propia de pequeñas desde el 2023-03-02.
- `ETAPA2_PREPARACION.md` §5 decía, por error, que el preregistro no definía embargo, y la decisión usó los periodos
  completos.
- **Efecto: ninguno sobre el veredicto.**
  - Grandes, medianas y las dos celdas ya estaban calculadas con ese periodo, como sensibilidad «sin el solape del
    propio desarrollo»: todo «no confirmado».
  - Faltaba H1 pequeñas desde el 2023-03-02. Se calculó después de cerrar con el mismo código congelado
    (`s9b_embargo_check.py` → `data/etapa2_embargo_check.json`): D −0,31 pp (IC −0,72 a +0,06), ΔIC +0,0035
    (IC −0,002 a +0,009), no confirmado.
- **Tampoco se hizo** la comparación secundaria de la enmienda 1 §10 (la candidata frente a reglas simples de
  reversión). Al no confirmarse la candidata ya no puede cambiar nada, y hacerla ahora ya no cumpliría su condición de
  congelar los umbrales sin haber visto la prueba. Queda sin hacer, declarada.

### 8.3 Otros incidentes

- **Disco externo dañado** al traerlo de otro equipo (desconexión sin expulsar). Reparado con `chkdsk /scan` y
  `/spotfix`, solo dentro de la carpeta del estudio; dos JSON de la SEC se descargaron de nuevo.
  - Permisos heredados de otro usuario, arreglados con `takeown` + `icacls /reset`.
  - Después: 10 165 ficheros legibles y todas las congelaciones verificadas.
- **pandas 3** no admite NaN en una columna booleana (`nl{H}`). Se convierte a `object`, como hacía pandas 2, sin
  cambio de resultados.

### 8.4 Garantías de reproducibilidad

- El preregistro, las dos enmiendas, la versión c2, las tandas y la preparación de la etapa 2 están congelados con
  SHA-256, y todas las verificaciones pasan.
  - Única diferencia frente al preregistro: `s1_panel.py`, ampliado por las enmiendas, cuya versión actual congela c2.
- Las selecciones de las dos tandas se reprodujeron desde cero, idénticas byte a byte (`data/etapa2_repro_check.json`).
- Para repetir el cálculo confirmatorio, con el disco de datos en `D:\backup market tracker\flow_negative_v1`:
  - `s9_etapa2.py --verify`;
  - cargar `work/etapa2_test_rows.parquet` (hash registrado) y `run()`.
  - El script se niega a escribir sobre los resultados existentes.

## 9. Implicaciones para Market Tracker

- **No se usa Flow < −30 como señal autónoma de compra o de reversión.**
- **El indicador Flow no se retira de producción:** este estudio solo evaluó la hipótesis de reversión por Flow
  negativo, no todos sus usos.
- **Exposición consumida:** 2021-01-04 → 2026-09-17 en grandes, medianas y sin capitalización; 2023-01-03 →
  2026-09-17 en pequeñas y micro. Quedan inspeccionados para esta familia de hipótesis (Flow negativo como predictor de
  reversión o continuación, por niveles, episodios, tallas, regímenes y plazos), y el desarrollo 2018-2022 también.
  Registro: `data/exposicion_flow_negativo.json`.

## 10. Estudios futuros

- Sin nuevas optimizaciones de umbrales, plazos ni regímenes sobre los periodos ya inspeccionados.
- Sin rescatar como señal la lateral a 10 sesiones ni H1 pequeñas a 40.
- Toda investigación posterior tiene que cumplir tres condiciones:
  - responder a una pregunta sustancialmente nueva;
  - declarar esta exposición previa;
  - disponer de una validación independiente: datos posteriores al 2026-09-17 en tiempo real, otro mercado u otro
    universo no inspeccionado.

## 11. Qué se conserva

- **En el repositorio:** código, congelaciones, enmiendas, informes, tablas agregadas y este cierre.
- **En el disco de datos (`D:\backup market tracker\flow_negative_v1`):**
  - panel, series y filas de desarrollo y de prueba;
  - acciones por clase de la SEC.
- **Fuera del repositorio**, por llevar cierres de Alpaca (licencia personal, no redistribuible):
  - `data/corr1_jumps_evidence.csv`;
  - `data/corr1_overlay_checks.json`;
  - todas las filas y series, que están en el disco de datos.
