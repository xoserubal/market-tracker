# Flow negativo — preparación de la etapa 2 (última puerta antes de la prueba)

2026-11-21, LAWNMOWER. **La prueba no se ha abierto**: no existe `data/etapa2_resultados.json` ni `data/etapa2_acceso.jsonl`.
Selección aprobada por el usuario el 2026-11-21: opción (a), dos celdas, la segunda anidada en la primera.

## 1. Congelaciones finales

| Congelación | Fecha (UTC) | SHA-256 del fichero |
|---|---|---|
| `data/preregistro_v3_freeze.json` | 2026-11-20 | `2839be99…ff2b71` |
| `data/enmienda1_freeze.json` | 2026-11-20 | `ee831122…6741b44` |
| `data/enmienda2_freeze.json` | 2026-11-20 | `013e4be1…8e36f2` |
| `data/version_c2_freeze.json` (panel c2 y su código) | 2026-11-21 | `2554cd9d…73058b0c` |
| `data/etapa1_tanda1c2_frozen.json` (tanda 1) | 00:15:27 | `7fbb528d…d55e3e` |
| `data/etapa1_tanda2c2_frozen.json` (tanda 2) | 00:18:53 | `8bd41efc…aa78a5f` |
| `data/etapa2_preparacion_freeze_v1.json` (primera congelación de la etapa 2) | 02:09:28 | `1acf1ab8cac7d6189d236036f5f8ea7f1025c4391bedbb35d53009f5bf664705` |
| `data/etapa2_preparacion_freeze_v2.json` (añade los complementos de §8 bis y este documento) | 2026-11-21 | `9e1472a8799e4d886330ed051a86471a01fd018967985c4d8a63d236f04b1102` |
| `data/etapa2_preparacion_freeze_v3.json` (primera corrección de memoria, §8 quater) | 2026-11-21 | `6956600f13bb4874da5cca3a3ae2e075c4146a242dad7f1ad01f83f9bcfec823` |
| `data/etapa2_preparacion_freeze_v4.json` (desenlaces por tandas, §8 quater) | 2026-11-21 | `a40dfafec1bbf8d3479f8d05414571aaf1a030625401e711f57e26f5e7b16c13` |
| **`data/etapa2_preparacion_freeze.json`** (v5: lectura de las columnas usadas, §8 quater) | 2026-11-21 | se registra en `data/etapa2_acceso.jsonl` al abrir (no puede ir aquí: el documento está dentro de la congelación) |

- La última congela el código y los datos de la ejecución:
  - código: `s9_etapa2.py` (`a3f4743f…`), `s4_etapa1.py` (`02cc9873…`, el mismo de las dos tandas) y `fn_config.py`
    (`ab8ab082…`, el del preregistro);
  - parámetros: las dos tandas, sus selecciones, los cortes de H1 y las congelaciones anteriores;
  - registros de corrección (`terminal_events_v4`, `corr1_*`);
  - datos: `work/panel_v4c2.parquet` (`7a8ba161…`) y las filas de las dos tandas.
- `s9_etapa2.py --open-test` comprueba todos esos hashes antes de leer nada, y se niega si alguno no coincide.

## 2. Contrastes confirmatorios (exactamente 5)

| | Contraste | Confirmado si |
|---|---|---|
| 1 | H1 grandes (prueba 2021-01-04 → 2026-09-17) | Se cumplen las dos (§6.3): <br>• \|D\| ≥ 0,5 pp con su intervalo sin el 0 <br>• media de ΔIC > 0 con su intervalo sin el 0 <br>Si solo se cumple una: «evidencia parcial» |
| 2 | H1 medianas (prueba 2021-01-04 → 2026-09-17) | Igual que el 1 |
| 3 | H1 pequeñas (prueba 2023-01-03 → 2026-09-17) | Igual que el 1 |
| 4 | **Principal:** grandes / episodio Flow < −30 / 20 sesiones / todos los regímenes | Las tres a la vez (§7): <br>• mismo signo que en desarrollo (+) <br>• exceso ≥ 0,5 pp <br>• intervalo sin el 0 |
| 5 | **Secundaria anidada:** la misma señal, solo régimen lateral | Igual que el 4 |

- **Reversión (posible oportunidad)** (§8) exige, además de confirmar:
  - atribución al Flow frente a días sin la señal de la misma talla, mes y quintiles de w1/m1, con el intervalo sin
    el 0;
  - exceso neto de costes > 0 en la población B, con coste del 0,2 % ida y vuelta en grandes;
  - que se mantenga con las dos cotas terminales.
  Si no: «descripción de la caída».
- **Dependencia:** los 147 episodios de la 5 están dentro de los 805 de la 4. Si pasan las dos, se informa como un solo
  hallazgo; la 5 no prueba una ventaja propia del mercado lateral.
- Micro y «sin capitalización»: solo descriptivas, sin veredicto. Todo lo demás (sensibilidades, otros plazos,
  subperiodos) se publica sin decidir nada.

## 3. Comparaciones múltiples

- **Bonferroni sobre los 5 contrastes** (§9: H1 de 3 tallas + celdas elegidas). Nivel por contraste: 0,05 / 5 = **0,01**.
  Intervalos al **99 %**.
- No se relaja nada: no se corrige por la dependencia entre las celdas 4 y 5, lo que hace la corrección más
  conservadora, no menos.
- **Decisión con el método principal:**
  - bootstrap por bloques de 60 sesiones, 2 000 réplicas;
  - para D, bloques de 3 meses;
  - error de Newey-West con retardo igual al plazo, como información.
- Si los bloques de 20/120 sesiones (D: 1 y 6 meses) meten el 0, la celda se marca «frágil» sin cambiar el veredicto.

## 4. Desenlaces desconocidos (preregistro §4.2 + enmienda 2 §2)

| Caso | Principal | Cotas |
|---|---|---|
| Valor de salida conocido | Ese valor, y 0 % hasta el plazo | — |
| Adquisición sin valor conocido | Último cierre | ×e^−0,05 y ×e^+0,05 |
| Quiebra, exclusión/OTC, fin desconocido, términos incoherentes | Último cierre | 0 y último cierre |
| Saltos de precio indeterminados y escisiones no reconstruibles | Fuera del principal y de la media de su talla | Sensibilidades: saltos tal cual y saltos anulados |

- Toda conclusión debe mantenerse con las dos cotas.
- La fracción de desconocidos se informa por contraste. En desarrollo era 0 % en las dos celdas elegidas.

## 5. Fechas de prueba, solapes y periodo común

| Talla | Desarrollo | Prueba (decide) | Último precio visto por su desarrollo* |
|---|---|---|---|
| Grandes, medianas, sin cap. | 2018-01-02 → 2020-12-31 | **2021-01-04 → 2026-09-17** | 2021-03-02 |
| Pequeñas, micro | 2018-01-02 → 2022-12-30 | **2023-01-03 → 2026-09-17** | 2023-03-01 |

\* La última señal de desarrollo usa precios hasta 40 sesiones después.

- **El preregistro no define embargo**, y añadirlo ahora sería cambiar la regla después de ver el desarrollo. La
  decisión usa los periodos de prueba completos de la tabla.
- Para separar lo que pides, cada contraste de grandes y medianas se publica también en tres subperiodos, **sin decidir
  nada**:
  - sin el solape con su propio desarrollo: señales posteriores al 2-mar-2021;
  - **antes del periodo común limpio:** señales del 4-ene-2021 al 1-mar-2023. Ese mercado ya se vio, a través de las
    pequeñas y micro de la tanda 2, aunque la selección de grandes se congeló antes de mirarlo;
  - **periodo común limpio: señales desde el 2-mar-2023**, que ningún desarrollo de ninguna talla vio. Es la única
    validación común a todas las tallas.
- Si un veredicto cambia de un subperiodo a otro, se dirá expresamente.

## 6. Integridad tras la reparación del disco

| Comprobación | Resultado |
|---|---|
| `s3_freeze_v3.py --verify` (preregistro) | Todo coincide, incluidos `panel_v4.parquet`, `companies_v4.csv` y `company_links_v4.csv` (externos). Única diferencia: `s1_panel.py`, ampliado por las enmiendas 1 y 2. Sin variables de corrección reproduce el v4; su versión actual la congela c2 |
| `s8_freeze_c2.py --verify` (versión c2: código, panel y acciones por clase) | OK |
| Hashes de las dos tandas c2 (filas, tablas, selección, código) | 10 de 10 OK |
| Documento de la enmienda 2 frente a su congelación | OK |
| Lectura de todo el directorio de datos | 10 165 ficheros legibles; todos los parquet/JSON se abren |
| `s9_etapa2.py --verify` | OK |

## 7. Reproducción sin datos de prueba

- **Selecciones:** las tandas 1 y 2 se repitieron desde cero con el código congelado (sufijo `c2r`), y coinciden
  exactamente con las congeladas:
  - celdas elegidas, modelos M0/M1, las 72 y 48 candidatas, tablas y filas;
  - el parquet de filas es idéntico byte a byte (mismo SHA-256).
  - La fecha máxima por talla es el fin de su desarrollo (2020-12-31; 2022-12-30 para pequeñas y micro).
  - Resultado: `data/etapa2_repro_check.json`. Los ficheros `*c2r*` son la repetición; no sustituyen a nada.
- **Constructor de filas de la prueba:** con el periodo «dev», `s9_etapa2.py` reconstruye las 833 902 filas de la
  tanda 1 idénticas a las congeladas, columna a columna (`data/etapa2_rebuild_dev_check.json`). La prueba usa la misma
  función, con el periodo «test».
- **Ensayo de punta a punta** sobre las filas de desarrollo (`data/etapa2_ensayo_desarrollo.json`):
  - reproduce las cifras de desarrollo de las dos celdas (805 y 147 episodios, mismos excesos y t);
  - las cifras de H1 están dentro de muestra (M0/M1 se estimaron con ellas) y no significan nada.
  - **Dato de desarrollo que conviene conocer antes de abrir:** con los criterios de §8, la celda principal ya saldría
    en desarrollo como «descripción de la caída», porque su atribución frente a días con caídas parecidas no excluye
    el 0 al 99 % (+0,68 pp). La lateral saldría como «reversión».

## 8. Interpretaciones de implementación (no fijadas literalmente en el preregistro)

Revísalas antes de autorizar: una vez abierta la prueba ya no se pueden cambiar.

1. **D:** peso de cada celda mensual = todas sus observaciones (tercios bajo, medio y alto).
2. **ΔIC:** solo días con ≥ 30 observaciones con Flow < 0 y resultado de la talla. Predicción M0 = media de desarrollo
   de su celda 5 × 5; M1 = M0 + efecto congelado de su tercio de R. Spearman por día.
3. **Atribución:** la referencia son todos los días utilizables sin esa señal de la misma talla, mes y quintiles de w1 y
   m1, sea cual sea su Flow. Para la celda lateral, la señal se restringe a días laterales y la referencia no.
4. **«Se mantiene con las dos cotas»:** las medias con cota inferior y superior tienen el mismo signo que la principal.
5. **Lectura «continuación bajista»:** solo por exceso negativo confirmado. Lo de nuevos mínimos y percentil 10 frente a
   la referencia se informa sin intervalo. No afecta a estas dos celdas, de signo positivo.
6. **Neto de costes:** media diaria del exceso frente a la talla en la población B, menos el coste de ida y vuelta.
   Sensibilidades ×2 y ×3.

## 8 bis. Complementos añadidos el 2026-11-21, antes de abrir la prueba (no deciden nada)

Pedidos por el usuario tras revisar este documento. Los cinco contrastes, sus umbrales, Bonferroni, los intervalos al
99 %, los periodos, los desenlaces desconocidos, las sensibilidades y el bootstrap principal **no cambian**.
- Se calculan después de todo lo confirmatorio y con su propio generador aleatorio (semilla 20261122). Las cifras
  confirmatorias del ensayo son idénticas con y sin ellos (§8 ter).
- No se usaron resultados de desarrollo para fijar ninguna definición ni elegir variantes.

**1. Atribución estricta de la celda lateral.**
- Referencia: días de grandes sin la señal (ep −30), del **mismo régimen lateral**, mismo mes y misma celda de
  quintiles w1 × m1.
- Comparadores insuficientes:
  - cada grupo de referencia necesita **≥ 10** observaciones, y los episodios sin grupo suficiente quedan fuera
    (se informa cuántos);
  - si se empareja menos del 50 % de los episodios, o salen menos de 10 días, el resultado es «no evaluable», sin cifra.
- Sensibilidad: el mismo cálculo sin mínimo de comparadores.
- Inferencia: media diaria, Newey-West y bootstrap por bloques de 60 al 99 %.
- Se publica **junto a la atribución original** (§2 y §8.3), que es la que sigue contando para la clasificación de
  §8. No se sustituye una por otra según cuál salga mejor. Si discrepan, se dirá expresamente.

**2. Rentabilidad absoluta y operabilidad**, para las dos celdas: población A, población B y periodo común limpio.
- Rentabilidad absoluta bruta y neta de costes (0,2 % ida y vuelta en grandes): media por episodio, mediana y media
  diaria con su intervalo al 99 %. También sus cotas terminales y el exceso frente al SPY.
- Exceso relativo frente a la talla, bruto y neto.
- Proporción de episodios positivos, en cada una de las cuatro medidas.
- Máxima excursión adversa: media, mediana, percentil 10 y proporción ≤ −10 % y ≤ −20 %. Y la favorable: media y
  mediana.
- **Un exceso relativo positivo no demuestra por sí solo una reversión alcista rentable.** Puede ser positivo con
  rentabilidad absoluta negativa (si la talla entera cae más), o desaparecer tras costes.

## 8 ter. Verificación de los complementos

- Ensayo con las filas de desarrollo antes y después de añadir los complementos: todo lo confirmatorio (H1, celdas,
  atribución original, clasificación, sensibilidades) sale **idéntico**, comparando el JSON completo sin el bloque
  `complementary`.
- La atribución estricta se calcula sin error y es evaluable en desarrollo: se emparejan 133 de 147 episodios.
  No se miró su valor.
- Único cambio adicional en el código: la salida de consola pasa a UTF-8. El ensayo falló al imprimir «→» en cp1252,
  después de escribir el JSON.
- La congelación anterior se conserva como `data/etapa2_preparacion_freeze_v1.json`; la nueva incluye ese fichero y
  este documento.

## 8 quater. Incidente: primera apertura sin resultados por falta de memoria (2026-11-21 09:13 UTC)

- `--open-test` (congelación v2, `9e1472a8…`) quedó registrado en `etapa2_acceso.jsonl`, construyó las filas de prueba
  en memoria y murió por falta de memoria (`ArrayMemoryError`) al empezar H1.
- **No se escribió ni se mostró ninguna cifra de prueba**: no existe `etapa2_resultados.json`, y la salida solo
  contiene la traza del error.
- Causa: las sensibilidades de cotas y de entrada al cierre copiaban la tabla entera de prueba (~2,3 GB por copia),
  sobre lo que retenía la propia construcción.
- Arreglo, sin cambiar ningún cálculo:
  - las cotas sustituyen la columna solo en el subconjunto de la talla;
  - la columna de entrada al cierre se añade una vez;
  - las filas de prueba se escriben en `work/etapa2_test_rows.parquet` y se releen en limpio. El paso por parquet no
    altera nada (§7). Si la ejecución vuelve a morir sin resultados, se reutilizan solo si su hash coincide con el
    registrado en el acceso.
- Comprobación: el ensayo de desarrollo con el código corregido es **idéntico byte a byte** al anterior, complementos
  incluidos.
- La congelación v2 se conserva como `data/etapa2_preparacion_freeze_v2.json`.
- **Segundo intento (09:26 UTC, congelación v3 `6956600f…`):** murió otra vez por memoria, esta vez antes, al construir
  los desenlaces (el cálculo guarda listas de Python por columna para ~2 M de filas). Tampoco escribió ni mostró ninguna
  cifra, y no llegó a guardar filas.
- Arreglo: los desenlaces se calculan por tandas de empresas (10) y se juntan. Cada fila depende solo de la ruta de su
  empresa, así que el resultado es el mismo.
  - Comprobado con `--rebuild-dev-check`: las 833 902 filas de desarrollo salen idénticas a las congeladas, columna a
    columna.
- La congelación v3 se conserva como `data/etapa2_preparacion_freeze_v3.json`.
- **Tercer intento (09:35 UTC, v4 `a40dfafe…`):** construyó y guardó las filas de prueba (`rows_built`, hash
  `c07cef34…` en el acceso) y murió por memoria al empezar H1. Las demás aplicaciones abiertas en el equipo ocupaban
  unos 15 GB de memoria comprometida, y quedaban menos de 5 GB. Tampoco escribió ni mostró ninguna cifra.
- Arreglo: el análisis lee solo las columnas que usa (`analysis_columns`). Si falta alguna, se para con error.
  - Comprobado: el ensayo de desarrollo con la lectura reducida es **idéntico byte a byte**.
- La congelación v4 se conserva como `data/etapa2_preparacion_freeze_v4.json`. El siguiente intento reutiliza las filas
  ya construidas, solo si su hash coincide con el registrado.

## 9. Comando

Desde `research/flow_negative_v1/`, en LAWNMOWER, con el disco externo en D::

```
py -3 s9_etapa2.py --verify
py -3 s9_etapa2.py --open-test --confirm "ABRO LA PRUEBA"
```

- Comprueba los hashes de §1 y se niega si no coinciden o si ya existe una ejecución.
- Registra el acceso y construye las filas de prueba con el código congelado.
- Calcula los 5 contrastes y las sensibilidades, y escribe `data/etapa2_resultados.json` (agregados).
- Es de una sola oportunidad: no se puede repetir sobre el mismo fichero de resultados.
- Duración estimada: 30-60 minutos, unos 2,2 M de filas de prueba.
