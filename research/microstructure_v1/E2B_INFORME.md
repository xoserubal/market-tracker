# E2 — comprobaciones pendientes, propuesta final de cat-v1 y capas de información

Fecha: 2026-11-21 (LAWNMOWER). Encargo: revisión del usuario de `E2_INFORME.md` («para despues.md»), §4 y §7.
- Solo descripción: ningún resultado posterior a los eventos, ningún dato del periodo reservado de G2A.
- `cat-v0` sigue intacto. **cat-v1 queda propuesto, no aplicado.** E3 no se activa. Sin cambios en producción ni
  commits.

Principio de este informe, tal como lo fijaste: el objeto es un **registro histórico consultable** de la negociación
intradía. Las alertas son una forma de descubrir cosas en él, no lo que se conserva.

## 0. Resumen

1. **Criterios de las cinco medidas problemáticas, fijados con 2016-2019** (§1):
   - en cuatro funcionan;
   - **V3_close_est no se puede medir con barras:** en los valores de NYSE la barra de las 16:00 no recoge la subasta
     de cierre. Queda como medida guardada y la subasta de cierre se estudia con trades.
2. **Auditoría de ventanas reales en 300 valor-días** (§2):
   - la fusión de sesiones de `cat-v0` se confirma: cadenas de unas 55 alertas cortas, de 3,5 h de mediana;
   - con cat-v1 casi desaparece: 6 encadenamientos largos en 278 episodios, todos en días de COVID con unos 490
     valores marcados a la vez;
   - lo que sí alargaba los episodios era otra cosa: las medidas que resumen todo el premercado (PRE_ret, PRE_vol).
3. **Propuesta final de cat-v1** (§3), con tus cambios:
   - ninguna medida pierde su alerta por redundancia; el agrupamiento es solo visual;
   - I2 se conserva como fenómeno propio;
   - cada alerta lleva su comienzo, su instante de detección y su disponibilidad.
4. **Las cuatro capas** (§4): qué está guardado, con qué cobertura, qué es bajo demanda y qué se puede recalcular.

## 1. Criterios de las cinco medidas problemáticas

Fijados solo con la calibración (2016-2019). 2020-2021 se informa sin reajustar. Script: `e2b_criteria.py` →
`results/e2b_criteria.json`.

**Regla común**, además de la general de M1:
- **Propia historia:** el valor supera el máximo de su línea base de 60 sesiones (medidas discretas) o su percentil 99
  (continuas).
- **Magnitud absoluta:** supera el percentil 99 de esa medida en todos los valor-días elegibles de calibración.

Así una marca exige ser rara para el propio valor **y** tener un tamaño raro en el universo. Ya no basta con que la
dispersión habitual del valor sea casi nula.

| Medida | Qué mide | Umbral absoluto fijado | Marca M1 (E2) → cat-v1, calibración | cat-v1, 2020-2021 | Marcas de M1 que se conservan |
|---|---|---|---:|---:|---:|
| P1_run_up / dn | Minutos seguidos en la misma dirección | > 12 minutos | 0,32 % → 0,26 % | 0,37 % / 0,36 % | 79 % / 78 % |
| P3_highvol_run | Minutos seguidos con volumen ≥ 2 × el esperado | > 55 minutos | 0,32 % → 0,22 % | 0,18 % | 70 % |
| D3_gap | Minutos seguidos sin barra en la negociación continua | > 8 minutos | 0,39 % → 0,11 % | 0,29 % | 28 % |
| C3_ext35_up / dn | Recorrido máximo en los primeros 35 min de after hours | > 1,08 % / 1,14 % | 0,30 % → 0,26 % / 0,25 % | 0,37 % / 0,28 % | 87 % / 85 % |
| V3_close_est | Barra de las 16:00 / volumen continuo | > 1,46 (solo evaluables) | 0,21 % → 0,003 % | 0,003 % | 1 % |

**Qué cambia en la práctica:**
- **P1 y C3_ext35:** las marcas de M1 ya eran casi todas grandes. El criterio quita sobre todo las que no superaban
  la propia historia del valor.
  - Lo marcado ahora: rachas de 13-17 minutos y recorridos de after hours del 2-10 %.
- **P3:** quedan rachas de volumen alto de 67 a 330 minutos (mediana 116). Son fenómenos persistentes de verdad, no
  ruido.
- **D3_gap:** antes marcaba huecos de **2 minutos** (la mediana de sus marcas) en valores que nunca tienen huecos. Ahora
  quedan huecos de 16 a 77 minutos.
  - **El 89 % cae en cinco días de mercado:**
    - 2020-03-09, 03-12 y 03-16: paradas generales del mercado por los cortacircuitos (la parada de las 09:34-09:49 se
      ve exactamente);
    - 2019-08-12 y 2019-10-09: cientos de valores con el mismo hueco y ninguna parada general que conozcamos (no
      comprobado en fuentes externas), casi seguro barras ausentes en el dato.
  - Propuesta: un hueco simultáneo en ≥ 10 % de los valores en un día sin parada documentada se trata como artefacto
    del dato (§3).
  - La regla de liquidez de E1 (≥ 5 operaciones por minuto) se mantiene, pero no filtra nada en el S&P 500: la cumple
    el ~100 % de los valor-días.
- **V3_close_est: no es una medida de la subasta de cierre.**
  - Vale 0 en el 52 % de los valor-días de 2016-2019 (19 % en 2021), y depende de la bolsa:
    - los valores de Nasdaq (AAPL, ADBE, AMD…) casi nunca dan 0;
    - casi todos los de NYSE dan 0 en el 50-95 % de sus días.
  - En esos valores, cualquier volumen en esa barra parecía raro.
  - Solo el 27 % de los valor-días es evaluable: los que tienen volumen en la barra de las 16:00 en ≥ 90 % de su base.
    Y aun ahí el umbral de M1, calibrado con la mezcla, ya no marca casi nada.
  - **Propuesta:** sin alerta con barras, estado «requiere trades». La medida se sigue guardando.

**Una aclaración sobre la tabla de E2_INFORME §3.**
- En las medidas discretas o llenas de ceros, «MAD en el 10 % más bajo» es lo normal: le pasa al 98 % de los
  valor-días en P1 y al 78-80 % en C3_ext35.
- Por eso esa columna seguirá alta con cualquier criterio. Lo que evita la falsa anomalía es la magnitud absoluta, no
  que esa columna baje.

**Efecto en las familias** (calibración; el 2 % es una referencia, y no se reajusta nada para volver a él):

| Familia | E2 (M1) | cat-v1 | cat-v1 en 2020-2021 |
|---|---:|---:|---:|
| Cierre/apertura (C) | 2,00 % | 1,95 % | 3,2 % |
| Desplazamiento (D) | 2,00 % | 1,74 % | 3,8 % |
| Persistente (P) | 2,00 % | 1,78 % | 1,8 % |
| Volumen (V) | 2,00 % | 1,80 % | 1,3 % |

## 2. Auditoría de ventanas reales y fusión de episodios

Script: `e2c_window_audit.py` → `results/e2c_window_audit.json`, `e2c_audit_alerts.parquet`.

**Muestra (semilla 20261122):**
- 240 valor-días con marca de M1, 40 por cada combinación de periodo y tercil de liquidez;
- 60 valor-días elegibles al azar;
- 228 entidades.

**Método:**
- Para cada valor-día se recalculan las series por minuto con el mismo código de cat-v0, y cada alerta toma su
  **ventana real**: cada tramo contiguo en que su serie supera el umbral, como hacía el escaneo de E1.
- Medidas de instante fijo: su ventana fija.
- Umbrales por fila con M0 (cat-v0), M1 (E2) y cat-v1.
- **Coherencia:** los 13 200 valores recalculados coinciden con los guardados.

**Episodios por tramo** (alertas a ≤ 10 min):

| | M0 (cat-v0) | M1 | cat-v1 |
|---|---:|---:|---:|
| Episodios | 784 | 349 | 335 |
| ≥ 120 min, ventanas reales | 16,7 % | 18,6 % | 19,4 % |
| Lo mismo con la ventana del pico (la medición de E2_INFORME) | 0,7 % | 0,3 % | 0,3 % |
| **Sin PRE_ret / PRE_vol:** ≥ 120 min | 7,2 % (51) | 2,7 % (8) | 2,9 % (8) |
| **Sin PRE:** ≥ 80 % de la sesión continua | 14 | 1 | 1 |
| **Sin PRE:** encadenamientos largos de alertas cortas | 38 (mediana 55 alertas, 3,4 h) | 6 | 6 |

**Lo que dice la auditoría:**
1. **La ventana del pico subestimaba mucho la longitud.** Con ventanas reales, el comienzo del fenómeno precede en
   14 minutos de mediana al momento en que puede detectarse. Es la longitud de la ventana de la medida, que hay que
   tener completa.
2. **Lo que más alarga los episodios no es la fusión, sino PRE_ret y PRE_vol.** Resumen todo el premercado
   (04:00-09:30), y su ventana fija son esos 330 minutos. Son 57 de los 65 episodios largos de cat-v1.
   - Propuesta: las medidas de resumen se tratan como puntos en su instante de detección, con la ventana resumida como
     atributo. Así no encadenan nada.
3. **La fusión de cat-v0 se confirma:**
   - cadenas de 50-55 alertas cortas de desplazamiento y VWAP (D1, D2, I3), que cubren 3-4 horas;
   - 14 episodios de sesión casi entera en 300 valor-días.
   - Venía de los umbrales de cat-v0: con M0, cualquier minuto agitado supera su propia base.
4. **Con cat-v1 la fusión casi desaparece.** Los 6 encadenamientos que quedan caen en 2020-03-12, 03-16, 03-18 y
   03-20, días en que unos 490 de los ~500 valores marcaban a la vez. No es un fallo de la agrupación: el valor estuvo
   agitado toda la sesión, como todo el mercado.
   - Propuesta: se conservan, con la marca de día de mercado.
   - El único episodio largo de una sola ventana fuera de esos días (2020-02-20) es un fenómeno persistente real.
5. **Agrupar por tramo o por día da casi lo mismo** una vez quitado el premercado. Agrupar por tramo evita unir el
   premercado con la sesión, así que se mantiene.

## 3. Propuesta final de cat-v1

Para aprobar; nada de esto está aplicado. Ninguna regla borra información de las capas 1 y 2 (§4).

1. **Normalización M1** como regla y **M2 como contexto**, guardados los dos.
   - M1: base de 60 sesiones a fecha (≤ 180 días), transformación por tipo de medida y suelo de dispersión = percentil
     10 de las MAD de calibración.
2. **Umbral por medida**, en unidades de su propia dispersión, fijado una vez con 2016-2019 (`e2_report.json →
   calibration.M1`).
   - El 2 % por familia fue solo la referencia para fijarlo: no es una cuota ni una definición de relevancia.
   - Sin cuota diaria: en un día de estrés se marcan los que haga falta.
3. **Las cinco medidas problemáticas:** los criterios de §1, congelados en `results/e2b_criteria.json`.
   V3_close_est, sin alerta con barras («requiere trades»).
4. **Redundancias: ninguna medida pierde su alerta. Esto cambia la propuesta de E2_INFORME §6.**
   - Se agrupan solo para mostrarlas:
     - volumen: V1_1, V1_5, V1_15 e I2;
     - desplazamiento: D1_15, D1_30 e I3.
   - Cada alerta sigue siendo consultable por separado.
   - **I2** (volumen alto sin desplazamiento) se conserva como fenómeno propio. Que se parezca a V1 en la puntuación no
     lo hace equivalente: comparten aproximadamente la mitad de sus marcas, y las marcas de V1 que no son I2 son
     precisamente las de volumen alto que sí desplaza el precio.
   - Se conservan las escalas de 1, 5 y 15 minutos.
5. **Campos separados en cada alerta:**
   - rareza: puntuación M1, percentil propio y puntuación M2;
   - magnitud: el valor bruto;
   - persistencia: sesiones seguidas con la misma marca;
   - simultaneidad: fracción de valores con marca de la familia ese día, y en su sector. «Día de mercado» = ≥ 10 %;
   - calidad: evento corporativo, ventana de 60 sesiones tras un split, cobertura de minutos, cierre anticipado, medida
     estimada, medida no evaluable por la bolsa.
6. **Artefactos**, que se marcan sin borrar nada:
   - día con evento corporativo no reconstruido;
   - V2 en las 60 sesiones posteriores a un split;
   - **nuevo:** D3_gap simultáneo en ≥ 10 % de los valores en un día sin parada general documentada. Hasta ahora,
     2019-08-12 y 2019-10-09. Las paradas de marzo de 2020 son un evento de mercado, no un artefacto.
7. **Episodios:**
   - por tramo (premercado, apertura, continua, cierre, after hours), con alertas a ≤ 10 min y **ventanas reales**;
   - las medidas de resumen (PRE_*, C1_*, C3_30/60, C3_vol_est, C5_*, V3_*) entran como puntos en su instante de
     detección;
   - cada alerta se conserva individualmente y lleva `episode_id`;
   - el episodio guarda su comienzo, detección, fin, nº de alertas y la marca de día de mercado.
8. **Instantes de cada alerta:**
   - `t_start`: comienzo del fenómeno;
   - `t_detect`: primer instante en que pudo detectarse;
   - `t_peak`, `t_end`;
   - `t_available`: cuándo habría estado disponible el dato. Con el plan gratuito de Alpaca, detección + 15 minutos,
     también en el histórico. La fecha real de descarga se guarda aparte, en el manifiesto.

## 4. Las cuatro capas de información

| Capa | Qué es | Dónde | Cobertura | Se recalcula desde |
|---|---|---|---|---|
| **1. Datos de mercado originales** | Barras de 1 minuto (o, h, l, c, v, nº de operaciones, VWAP), sin ajustar | `MICRO_DATA_DIR/raw` (16,8 GB) + manifiesto con checksums | ~600 valores por año, 2016-01 → 2026-11 (70 751 unidades) | Alpaca (descarga) |
| | Trades y quotes | `raw` | **Solo muestras:** 419 valor-días de trades (31 valores) y 417 de quotes (25 valores); fichas, G1.5, plan B1 | Bajo demanda, desde Alpaca (2016 en adelante; nada de los últimos 15 min) |
| | Referencia: identidad por época, pertenencia al S&P 500, splits validados, eventos corporativos, caídas de datos | `reference/`, `features/` | Toda la muestra | Registros propios versionados |
| **2. Medidas** | Valor de cada una de las 44 medidas de cada valor-día **elegible, marcado o no**, con su signo y su minuto de pico, más metadatos de calidad | `features/e2_measures` (629 entidades, 759 829 valor-días) | S&P 500, 2016-01 → 2021-10-28 | Capa 1 (≈ 26 ms por valor-día; coincidencia exacta comprobada) |
| | Normalización: tamaño de base, percentil, z, MAD, desviación M1, puntuación M2 | `features/e2_norm` (1,4 GB entre las dos) | Igual | Capa 2 (3 min) |
| | **No guardado:** las series por minuto de cada medida | — | — | Capa 1, bajo demanda (como en §2) |
| **3. Catálogo versionado** | Definición de cada código (`micro/event_catalog.py`), umbrales congelados por versión y alertas individuales con ventana e instantes, agrupadas en episodios | `results/e2_alerts_M{0,1,2}.parquet`, `e2b_criteria.json`, `e2c_audit_*`; `events/` (registro de E1) | cat-v0 (E1), cat-v1 propuesto | Capas 1-2 + parámetros de la versión. Una versión nueva no borra la anterior |
| **4. Estudios e hipótesis** | G2A, E2, preregistros y fichas | `research/microstructure_v1/*.md`, `results/` | — | Leen las capas 1-3; nunca las modifican |

**Qué garantiza este diseño:**
- **Nada se pierde al cambiar el catálogo.** La capa 2 tiene todas las medidas de todos los valor-días elegibles, con o
  sin marca. Cualquier umbral nuevo, o cualquier búsqueda de un patrón que no dio alerta (por ejemplo, I2 por debajo
  del umbral), se resuelve desde ahí sin repetir el cálculo pesado.
- **Cruce con cualquier otro dato:**
  - todo está indexado por **entidad histórica** (identidad del emisor por épocas, no por ticker) y **fecha de la
    sesión**;
  - cada instante intradía se puede convertir a hora UTC;
  - se distingue siempre el **momento del fenómeno** (`t_start`, `t_detect`) del momento en que el dato estuvo
    **disponible** (`t_available`).
- **Ampliable sin rediseñar.** Lo que pediste en tu §5 encaja así:
  - **Concentración de volumen por precio, POC y área de valor:**
    - una tabla nueva de la capa 2 por valor-día, con su perfil de volumen por nivel;
    - con barras es aproximada; exacta con trades, bajo demanda;
    - la migración entre sesiones se calcula sobre esa tabla.
  - **Persistencia a 5-60 sesiones:** se deriva de la capa 2 a lo largo de las fechas, sin datos nuevos.
  - **Volumen alto sin desplazamiento (I2) y movimientos rápidos con poco volumen (I1):** ya son medidas de la capa 2.
  - **Continua frente a subastas:** las medidas por tramo ya existen.
    - Las subastas exactas necesitan trades.
    - V3_close_est muestra que con barras no basta, sobre todo en NYSE.
  - **Acciones frente a sectores:** la simultaneidad por sector ya está en la capa 3.
    - **Limitación:** hoy se usa el sector de la última fecha de cada entidad. Hay que pasar a sector a fecha.
  - **Episodios semejantes:** cada valor-día tiene un vector de 44 medidas normalizadas en la capa 2; buscar parecidos
    es una consulta sobre esa tabla.
- **Límites de cobertura que conviene recordar:**
  - la capa 2 solo cubre el S&P 500 de 2016 a 2021-10-28;
  - de 2021-10-29 a 2026-09-14 está el periodo reservado de G2A, cuyas barras están guardadas pero bloqueadas;
  - trades y quotes son solo muestras: el registro diario y el histórico se basan en barras.

## 5. Lo que queda

- Tu aprobación de cat-v1 (§3), o los cambios que quieras.
- Pendientes para cuando se aplique, que ya pertenecen a cat-v1 y no a E2:
  - recalcular las alertas con las ventanas reales y las medidas de resumen como puntos;
  - el artefacto de huecos simultáneos;
  - el sector a fecha.
- Sin E3, sin tareas programadas, sin producción y sin commits.
