# VP1 — Piloto de fidelidad del Volume Profile: perfil estimado con barras frente a perfil observado con trades

Fecha: 2026-11-22. Autorización: aprobación del usuario del 2026-11-21 (§4: piloto, no generación masiva).
Código: `micro/volume_profile.py`, `vp1_pilot.py`. Pruebas: `tests/test_volume_profile.py` (6).
Resultados: `MICRO_DATA_DIR/results/vp1/` (`sample.json`, `comparisons.parquet`, `summary.json`).

**Descriptivo.** Mide cuánto se parece un perfil calculado con barras de 1 minuto al que sale de las operaciones
reales. No interpreta ninguna concentración de volumen como acumulación o distribución.

## 1. Diseño (fijado antes de mirar resultados)

**Muestra:** 192 sesiones regulares; 191 comparadas.
- **Parte A (156):** todas las sesiones con trades de la sesión regular completa ya descargados fuera del periodo
  reservado de G2A.
  - Casi todas son de 2017-2019 y de liquidez media.
  - Se añaden AAPL ×4, GOOGL, HIMS y PLTR de noviembre de 2026.
  - NVDA (12-nov) se omitió por memoria: 9,6 M de trades.
- **Parte B (36):** sesiones regulares del 18, 19 y 20 de noviembre de 2026 de 12 valores del universo E3.
  - Elegidos al azar (semilla 20261121), 4 por tercil de liquidez:
    - baja: OGI, GL, WRB y SWK;
    - media: OTIS, VYLR, ADM e IVZ;
    - alta: P, MDT, CVS y BE.
  - Abarcan de 2 200 a 315 000 operaciones por sesión.
  - Coste: 287 peticiones (se estimaron 323).

**Qué se compara:** los minutos [apertura, cierre) de la sesión regular.
- **A (estimado):** las barras de esos minutos.
- **B (observado):** los trades de esos minutos con la misma regla de volumen que las barras (`upd_vol`, sin
  canceladas; las impresiones oficiales M/Q no suman).
- **Variantes de B:** sin comunicaciones tardías, sin subastas y con la subasta de cierre, que se imprime a las 16:00 y
  no entra en las barras de la sesión regular.

**Rejilla:** niveles de 0,05 %, 0,10 % y 0,25 % del precio de referencia (la mediana de los trades continuos del día).

**Reparto del volumen dentro de cada barra:**
- todo al cierre;
- todo al VWAP de la barra;
- uniforme entre mínimo y máximo;
- triangular centrado en el VWAP dentro de [mínimo, máximo].

**Medidas:**
- **POC:** el mismo nivel, o la distancia en puntos básicos;
- **volumen observado en el POC estimado:** como fracción del volumen del POC observado. Cerca de 1 es un casi empate;
  cerca de 0, un POC estimado donde apenas hubo negociación;
- **área de valor del 70 %:** solapamiento de Jaccard y desplazamiento del punto medio;
- **distancia de variación total** entre los perfiles normalizados (0 = idénticos, 1 = sin solape);
- **concentración:** cuota del nivel máximo;
- **nodos de volumen alto:** niveles con ≥ 50 % del máximo; se mide su coincidencia.

## 2. Resultados

Rejilla del 0,10 % y todas las sesiones (n = 191):

| Reparto | POC igual | Vol. observado en el POC estimado: mediana / p10 | POC estimado con < 50 % | Dif. POC p90 (pb) | Área de valor (Jaccard, mediana) | Variación total (mediana) | Nodos altos (Jaccard) |
|---|---:|---|---:|---:|---:|---:|---:|
| Cierre | 68 % | 1,00 / 0,75 | 2,1 % | 21 | 1,00 | 0,091 | 0,75 |
| VWAP de la barra | 73 % | 1,00 / 0,78 | 3,7 % | 41 | 1,00 | 0,070 | 0,80 |
| Uniforme [mín, máx] | 71 % | 1,00 / 0,84 | 0 % | 19 | 1,00 | 0,064 | 0,82 |
| **Triangular en el VWAP** | **81 %** | **1,00 / 0,92** | **0 %** | **11** | **1,00** | **0,045** | **0,88** |

**Por periodo**, con el reparto triangular y la rejilla del 0,10 %:

| Periodo | n | POC igual | Vol. en el POC estimado (p10) | Dif. POC p90 (pb) | Variación total |
|---|---:|---:|---:|---:|---:|
| 2016-2021 (liquidez media) | 147 | 86 % | 0,99 | 10 | 0,042 |
| Noviembre de 2026 | 44 | 66 % | 0,83 | 30 | 0,057 |

**Por liquidez** (parte B, n = 12 por tercil, triangular):
- POC igual: 75 % en la baja, 58 % en la media y 50 % en la alta.
- Volumen observado en el POC estimado (p10): 0,79, 0,87 y 0,74.
- Variación total: 0,062, 0,046 y 0,076.

En los valores muy líquidos el perfil es plano: la cuota mediana del nivel máximo es el 7 %, frente al 17 % del
conjunto. Por eso el POC cambia de nivel con diferencias pequeñas.

**Tamaño de los niveles:**

| Nivel | POC igual (triangular) | Variación total |
|---|---:|---:|
| 0,05 % | 71 % | 0,067 |
| 0,10 % | 81 % | 0,045 |
| 0,25 % | 93 % | 0,026 |

- Con el reparto al cierre, el nivel del 0,05 % baja al 52 % de POC igual y al 9 % de POC estimados con menos de la
  mitad del volumen real.
- Con los trades solos, el POC observado se mueve una mediana de 13 pb entre las tres rejillas (p75: 22 pb; máximo:
  819 pb). El POC depende del tamaño del nivel tanto como de la fuente de datos.

**Variantes de lo observado** (frente al reparto por VWAP, rejilla del 0,10 %):
- Quitar las comunicaciones tardías (≈ 1,5 % del volumen en la mediana; hasta el 18 %) o las subastas apenas cambia la
  comparación.
- **Añadir la subasta de cierre sí la cambia:**
  - POC igual: del 73 % al 57 %;
  - POC estimados con menos de la mitad del volumen real: del 3,7 % al 14 %;
  - Jaccard del área de valor: de 1,0 a 0,9.
- **Un perfil «del día» con barras no recoge la subasta de cierre.** Hay que decidir si el perfil la incluye, y con
  barras solo puede añadirse aparte, con trades o con su impresión.

## 3. Hallazgos de datos

> **Corrección del 2026-11-22: la diferencia de 2016-2017 NO era de Alpaca; era un fallo de nuestro cargador.**
> - **Qué fallaba:** `episode.load_trades` quitaba siempre, aunque hubiera una sola unidad, las filas iguales en
>   (hora, mercado, precio, tamaño, condiciones). En 2016-2017 hay muchas operaciones legítimas idénticas salvo el
>   identificador. Por ejemplo, en KSS 2017-05-10 se quitaban 7 580 de 47 382.
> - **Qué se ha cambiado:** solo se quitan repeticiones entre unidades que se solapan, y con el identificador en la
>   clave. `legacy_overlap_dedupe=True` reproduce el comportamiento anterior.
> - **Comprobación:** con el cargador corregido, el volumen de trades con la regla de las barras coincide
>   **exactamente** con el de las barras: KSS 6 547 164 = 6 547 164; JNPR al 0,02 %; AIG 2019 igual.
> - **Repetición de VP1** (resultados anteriores guardados como `*_v1_cargador_antiguo`):
>   - relación barras/trades: mediana 0,9997, máximo 1,000;
>   - triangular, rejilla del 0,10 %: POC igual 82 % (antes 81 %), variación total 0,044, nodos altos 0,875;
>   - 2016-2021: POC igual 86 %.
>   - Las conclusiones no cambian.
> - **Alcance:** G2A no usaba este cargador. En los días recientes (marcas de tiempo en nanosegundos: AAPL, PLTR,
>   GOOGL) no cambia nada, así que las fichas de E1 y los casos de G1.5 se mantienen.
> - **La excepción que queda es real:** GL 2026-11-20, con las barras un 5 % por debajo. Alpaca no genera barra en los
>   minutos que solo tienen lotes impares (no mueven el precio): 2 360 operaciones y 19 827 acciones sin barra. Donde
>   hay barra, el volumen coincide exactamente.
>
> Lo que sigue es el texto original, que atribuía la diferencia a Alpaca.

- **Los trades de Alpaca de 2016-2017 están incompletos frente a las barras:**
  - en las 47 sesiones de esos años, el volumen de los trades con la misma regla es un 3-13 % menor (mediana 7 %);
  - la diferencia es uniforme en todas las horas de la sesión regular y no aparece en el after hours;
  - desde 2018 cuadran (mediana 1,000; casi siempre ±1 %), con alguna excepción suelta en sentido contrario (ATO,
    2019-06-20: las barras, un 3,6 % por debajo).
  - No se ha investigado la causa.
  - En esas sesiones el perfil «observado» es una muestra de las operaciones, no todas. El acuerdo de forma no
    empeora (POC igual en el 92 % de las sesiones con hueco), pero el volumen absoluto por nivel no es exacto.
- **GL, noviembre de 2026:** sus barras suman un 4-5 % menos que sus trades.

## 4. Qué precisión aporta cada fuente

- **Barras de 1 minuto con reparto triangular en el VWAP.** Reproducen:
  - el volumen total (relación mediana 1,002);
  - la forma del perfil (variación total del 4-6 %);
  - el área de valor (Jaccard mediano 1,0) y los nodos de volumen alto (0,88).
  - El POC sale idéntico en el 66-86 % de las sesiones. Cuando no coincide, el nivel estimado tiene casi el mismo
    volumen real que el verdadero (p10 entre 0,83 y 0,99, nunca menos de la mitad): son casi empates, no errores
    groseros.
- **Trades.** Hacen falta para:
  - **el POC exacto en valores muy líquidos** (perfil plano);
  - **la subasta de cierre** y cualquier separación por tramo (subastas, comunicaciones tardías, after hours);
  - **niveles finos** (0,05 % o menos).
- **Repartos al cierre y al VWAP:** son los peores; no deberían usarse.

## 5. Propuesta para el nivel de cálculo histórico (pendiente de tu decisión)

1. **Perfiles históricos con barras:** reparto triangular en el VWAP, niveles del 0,10 % del precio de referencia,
   etiquetados `estimated_bars_1m`. Coste: solo cálculo; las barras ya están.
2. **Subasta de cierre:** no puede estimarse con barras. O se deja fuera explícitamente, o se añade desde los trades
   cuando estén descargados (`observed_trades`, marcado como tal).
3. **Trades bajo demanda:** solo para los casos que se investiguen en el laboratorio, no de forma masiva.
4. **POC:** por la sensibilidad al nivel, mostrar siempre junto al POC los niveles con al menos el 90 % de su volumen
   (la «zona del POC») y no un único precio.
5. **Escala común entre días:** `volume_profile.split_factor` lleva los precios a la escala de un día de referencia
   con los splits de Alpaca; está probado con datos sintéticos.
   - Es imprescindible antes de comparar sesiones.
   - Los eventos corporativos que Alpaca no registra antes de 2020 (enmienda 7 de G2A) siguen siendo un límite.

## 6. Límites

- **Parte A:** no es aleatoria (es lo que ya estaba descargado) y la dominan cinco valores de liquidez media.
- **Parte B:** la de 2026 es aleatoria, pero pequeña (12 valores × 3 días): los porcentajes por tercil tienen mucho
  margen de error.
- **Valores muy grandes:** quedan fuera; NVDA no se procesó por memoria.
- **Solo sesión regular:** el perfil con pre y after hours no se ha comparado.
