# Conciliación de la tanda 1 — original frente a corregida (enmienda 1, 2026-11-20)

Enmienda: `wiki/ENMIENDA_1_FLOW_NEGATIVO_V3.md` (congelada antes de reconstruir; hash en `data/enmienda1_freeze.json`).
La enmienda nace de los rendimientos imposibles encontrados en la tanda 1 original y es **posterior a su inspección**.
Los ficheros originales (`data/etapa1_tanda1_*`, `work/etapa1_tanda1_rows.parquet`, `panel_v4.parquet`) siguen
intactos y con sus hashes. Las versiones corregidas llevan sufijo (`c1…`) y la elección corregida se guarda como
propuesta (`data/etapa1_tanda1c1_candidate.json`), **no** como congelación. No se ha tocado ningún dato de prueba.
Datos: `data/etapa1_tanda1c1_conciliacion.json`.

## 0. Reproducibilidad

- El código modificado, **sin correcciones**, reproduce exactamente el original: panel v4 idéntico (3 203 396 filas)
  y tanda 1 idéntica (72 candidatas, celda elegida, M0/M1, todas las tablas y los 720 intervalos de bootstrap).
- Por eso cambian dos hashes congelados, a sabiendas: `s1_panel.py` (lista del preregistro §13.1; `s3_freeze_v3.py
  --verify` lo marca) y `s4_etapa1.py` (hash de `etapa1_tanda1_frozen.json`). Los cambios solo añaden la lectura de
  la enmienda, activa únicamente con `FN_CORR`. Todos los demás hashes del preregistro y los originales de la tanda 1
  siguen intactos (comprobado).
- Cada familia se activa por separado; la conciliación las añade **en este orden** (el reparto entre familias depende
  del orden):

| Paso | Familia | Panel |
|---|---|---|
| c1s | contrasplits | v4c1s |
| c1si | + identidad (cortes y escisiones de identidad) | v4c1si |
| c1sic | + CIK y capitalización | v4c1sic |
| c1sicp | + valor de las escisiones | v4c1sic |
| c1sicpj | + saltos indeterminados marcados como ausentes | v4c1sic |
| c1sicpjt | + fusiones valoradas con Alpaca | v4c1sic |
| **c1** | + regla §7 (ausentes fuera del principal) = **versión corregida** | v4c1sic |

## 1. Conclusión principal

- **La candidata original (grandes, Flow < −30, 20 sesiones, todos los regímenes) sigue pasando todas las puertas** en
  las siete variantes. Ninguna otra celda pasa en ninguna variante.

| | n | Semanas | Exceso | t (NW) | IC 95 % (b60) | Mitades | Cotas | Población B |
|---|---|---|---|---|---|---|---|---|
| Original | 739 | 96 | +2,05 pp | 2,70 | +0,90 a +3,36 | +1,37 / +2,89 | +2,10 / +2,04 | +2,05 (t 2,70) |
| Corregida (c1) | 767 | 100 | +2,13 pp | 2,57 | +0,92 a +3,68 | +1,39 / +3,05 | +2,17 / +2,12 | +2,13 (t 2,57) |

- Por familia: contrasplits 0; identidad +1 episodio (t 2,71); **CIK +27 episodios** (empresas grandes que antes eran
  «sin capitalización»; t baja a 2,52); escisiones t 2,57; saltos, fusiones y §7 sin efecto apreciable.
- La t baja de 2,70 a 2,57: sigue sobre 2,5, pero con menos margen. Con 72 candidatas, una sola elegible sigue siendo
  compatible con el azar; la prueba lo decidirá.

## 2. Empresas y días afectados por familia (días utilizables 2018-2020)

| Paso | Días quitados | Días añadidos | Cambian de talla | Cambia el Flow | Cambia r20 | Empresas afectadas |
|---|---|---|---|---|---|---|
| contrasplits | 0 | 355 | 94 | 166 | 76 | 7 |
| identidad | 1 857 | 3 112 | 212 | 361 | 496 | 12 |
| CIK | 1 022 | 430 | 18 149 | 0 | 20 | 37 |
| escisiones | 0 | 0 | 0 | 0 | 266 | 13 |
| saltos | 0 | 0 | 0 | 0 | 0 (*) | 0 |
| fusiones | 0 | 0 | 0 | 0 | 38 | 2 |
| §7 | 0 | 0 | 0 | 0 | 1 826 (fuera) | 86 |

(*) los saltos solo marcan; su efecto aparece en §7. Los excesos (x20) cambian en muchos más días porque cambia la
media de la talla de esos días.

- **Contrasplits**: 355 días nuevos (CHK y otros dejan de estar excluidos por un «split incoherente» que ya no lo es);
  93 días de pequeñas pasan a micro (la capitalización de CHK/HPR ya no salta ×200/×50).
- **Identidad**: entran HWM (historia de Arconic Inc.), PRG (Aaron's), APTV (Delphi Automotive), CXT, ADEA y 21st
  Century Fox como empresa propia; salen los tramos mal atribuidos de ARNC, AAN, XPER y GCI.
- **CIK**: 1 022 días quitados son **dobles conteos** del original: DowDuPont contada dos veces (DD sin CIK y DWDP,
  454 días) y Weight Watchers dos veces (WTW y WW, 568 días). Al corregir el CIK, el procedimiento original de enlaces
  las une.

## 3. Capitalización y tallas (original → corregida, días comunes)

| De «sin capitalización» a | Días |
|---|---|
| grande | 8 407 |
| mediana | 7 107 |
| pequeña | 1 810 |
| micro | 228 |

- Otros cambios: 93 pequeña → micro (CHK, HPR), 1 mediana → pequeña.
- 37 empresas cambian de talla. Ejemplos: XOM y CB pasan a grandes los 756 días; AA a mediana (507 días) o pequeña (62); DIS a grande en 722 de 756 días.
- «Sin capitalización» baja de 81 288 a 62 613 días. Lo que queda es sobre todo **empresas con varias clases de
  acciones** (GOOGL, META, LEN, TKO, Fox…), que la SEC no publica por clase, y presentaciones rechazadas por los
  filtros de calidad (sin cambios). Ninguna de las dos cosas es de identidad; quedan como límite conocido.

## 4. Episodios

| Talla | X = −10 | X = −20 | X = −30 |
|---|---|---|---|
| Grande | 4 206 → 4 330 | 1 791 → 1 844 | 739 → 767 |
| Mediana | 5 026 → 5 190 | 2 759 → 2 859 | 1 277 → 1 330 |
| Sin capitalización | 1 342 → 1 026 | 766 → 575 | 385 → 271 |

## 5. Medias de referencia (media de r20 de la talla cada día; corregida − original)

| Talla | Media de la diferencia | Máxima | Días con más de 0,25 pp |
|---|---|---|---|
| Grande | 0,06 pp | 0,30 | 14 |
| Mediana | 0,08 pp | 0,57 | 19 |
| Pequeña | 0,62 pp | 44,4 | 101 |
| Micro | 3,13 pp | 148,9 | 227 |
| Sin capitalización | 0,61 pp | 2,6 | 546 |

Las diferencias grandes de pequeñas y micro son los contrasplits de CHK y HPR, que contaminaban la media de **toda**
la talla esos días.

## 6. Las 72 candidatas

- Elegibles: la misma y única en todas las variantes.
- Con |t| ≥ 2,5 en la corregida: la candidata; grandes −20/40/bajista (t 2,65, falla por 29 semanas, igual que en el
  original); sin capitalización −30/20/alcista (t 2,97, falla por n = 61 y semanas).
- Los mayores cambios de t están en «sin capitalización», porque esa población cambia mucho (salen las grandes
  empresas mal clasificadas). Ninguno cambia la elegibilidad.

## 7. H1: M0/M1 (efecto del tercio de R, pp)

| | R bajo | R medio | R alto |
|---|---|---|---|
| Grande original | +0,29 | −0,07 | −0,14 |
| Grande corregida | +0,26 | −0,07 | −0,12 |
| Mediana original | −0,01 | −0,14 | +0,13 |
| Mediana corregida | −0,03 | −0,12 | +0,13 |

Cambios menores; los signos se mantienen.

## 8. Resultados todavía desconocidos (corregida, plazo 20)

| Tipo | Días | Detalle |
|---|---|---|
| Desenlace terminal no observado | 1 644 | quiebras y finales sin valor; grandes 349, medianas 631, micro 299, sin cap. 280, pequeñas 85 |
| Saltos indeterminados | 213 | micro 152, pequeñas 45, medianas 16 (AKRX, DO, GPOR, IVR, LPI, PVAC) |
| Escisiones no reconstruibles | 0 | FTI, LGND y Xperi caen fuera de 2018-2020 |
| Total | 1 826 | episodios afectados: 13 (X = −10), 11 (X = −20), 10 (X = −30) |

- La fusión de 21st Century Fox no se reconstruye (mixta con Disney y Fox Corp): regla del preregistro, ±5 %.
- **Chesapeake (opción a)**: sin efecto en desarrollo. Alpaca no tiene precios OTC y la cancelación (9-feb-2021) cae
  unas 155 sesiones después de la exclusión, fuera de cualquier plazo.

## 9. Riesgo de la regla §7 (señalado, no corregido)

Sacar los no observados del principal elimina sobre todo quiebras. Efecto (exceso a 20 sesiones, pp):

| Celda | §7 (principal) | Preregistro (incluidos) | Cota inferior | Ausentes |
|---|---|---|---|---|
| Micro, Flow < −30 | +2,36 | +0,74 | −3,93 | 6,2 % |
| Micro, ep −30 | +1,98 | +1,67 | −0,89 | 2,8 % |
| Micro, Z4 | −0,10 | −0,46 | −1,80 | 3,2 % |
| Grande, ep −30 | +2,13 | +2,13 | +2,12 | 0 % |

En grandes y medianas es despreciable; en micro sesga hacia arriba de forma apreciable. **Recomendación**: antes de la
tanda 2 (que elige pequeñas y micro), sustituir §7 para los desenlaces terminales por la regla del preregistro (último
cierre en el principal; cotas 0 y último cierre; la conclusión debe aguantar con ambas) y dejar §7 solo para saltos de
causa indeterminada. Requiere tu aprobación (es un cambio de una regla congelada).

## 10. Pendiente de tu decisión antes de la tanda 2

1. Aceptar la versión corregida (c1) como base de la tanda 2 (la congelación original no se toca; la c1 quedaría
   como congelación nueva, declarada como posterior a la inspección).
2. La regla §7 (punto 9).
3. Las empresas con varias clases de acciones sin capitalización (fuente nueva de acciones por clase, o aceptarlo como
   límite).
4. Pendientes ya identificados para la prueba (no tocados): canje de Uniti (0,6029, ago-2025), efectivo de WestRock →
   Smurfit Westrock (5 $, jul-2024), proporción de Xperi Inc. y de OmniAb (LGND).
