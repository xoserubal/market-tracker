# E2 — Caracterización y calibración del registro de eventos intradía

Fecha: 2026-11-21 (LAWNMOWER). Autorización: `E2_AUTORIZACION.md`. **Solo descripción**: ningún resultado posterior a
los eventos, ninguna puntuación predictiva, nada del periodo reservado de G2A. `cat-v0` sigue intacto y reproducible.
**Me paro aquí**: nada pasa a `cat-v1` ni a E3 sin tu aprobación. Sin commits.

## 0. Resumen

- **`cat-v0` no sirve como registro.** Con la regla «percentil extremo O z robusto ≥ 4», el **63 % de los valor-días**
  de 2016-2019 tiene al menos una marca: 3,3 por día marcado. Entre el 50 % y el 87 % de las marcas de cada medida
  llegan solo por el z, en medidas de dispersión pequeña. Es el fallo que señalabas.
- **Propuesta `cat-v1`** (§6). Calibrada en 2016-2019, con umbrales fijados una sola vez:
  - normalización robusta con transformación por tipo de medida (M1);
  - umbral por medida que deja el 2 % de valor-días con marca en cada familia;
  - criterios propios para las medidas discretas o llenas de ceros.
  Marca el 9,1 % de los valor-días en calibración y el 11,7 % en 2020-2021, sin reajustar: 15 % en 2020 por el
  COVID, 7,6 % en 2021.
- **Los días de estrés siguen saliendo en bloque**:
  - el 12-mar-2020, el 99,8 % de los valores tuvo una marca de desplazamiento;
  - los vencimientos trimestrales, hasta el 48 % con marca de volumen.
- Lo que falta antes de `cat-v1`: una pasada sobre los episodios con las ventanas reales (§7) y tu revisión de la
  muestra del laboratorio.

## 1. Datos y denominadores

- **Universo:** 629 entidades con pertenencia verificada al S&P 500 en algún día de 2016-01-04 a 2021-10-28 (G1).
  - Identidades por época del nivel A.
  - Barras de 1 minuto ajustadas con los 170 splits validados en G2A (enmienda 7).
  - Nada del periodo reservado.
- **Elegibles:** miembro ese día, perfil con ≥ 30 sesiones, sin caída de datos de mercado, y ≥ 30 valores en la base
  de cada medida.
  - **Calibración 2016-2019:** 484 964 valor-días.
  - **Comprobación 2020-01-02 → 2021-10-28:** 229 112 valor-días.
  - Se calcularon también las sesiones previas a la pertenencia (759 829 valor-días en total) como calentamiento de
    la línea base.
- **Calentamiento:** el nivel A empieza el 4-ene-2016. Con 20 sesiones mínimas para el perfil y 30 para la base de cada
  medida, los primeros valor-días elegibles son de marzo-abril de 2016; 2016 tiene algo menos de denominador.
- **A fecha:**
  - cada sesión se calcula una sola vez, con el perfil de sus 60 sesiones válidas anteriores (≤ 180 días);
  - cada medida se normaliza con los valores de esa misma medida en las 60 sesiones anteriores;
  - los días que ya dieron alerta no se excluyen de la base.
- **Comprobaciones:**
  - las versiones vectorizadas (`micro/e2_fast.py`) dan exactamente lo mismo que las de `cat-v0`;
  - M0 reproduce `intraday_features.normalize` en 655 de 655 casos reales (`tests/test_e2.py`).

## 2. Métodos de normalización comparados

| Método | Qué es | Valor-días con marca: calibración → comprobación |
|---|---|---|
| **M0** (cat-v0) | percentil ≥ 99 de la base O z robusto ≥ 4 (MAD sin suelo) | 62,6 % → 68,1 % |
| **M1** robusto | cocientes en log, rachas en log(1 + x); (x − mediana) / max(MAD, suelo = percentil 10 de las MAD de calibración); umbral por medida calibrado | 9,1 % → 11,7 % |
| **M2** adaptativo | media y desviación absoluta exponenciales (semivida 20 sesiones), misma transformación; umbral calibrado | 9,0 % → 9,8 % |

- **M2 es más estable fuera de calibración, porque se adapta a un régimen nuevo, pero amortigua el estrés.**

  | Familia | M1, 2020 | M2, 2020 | Calibración (ambos) |
  |---|---:|---:|---:|
  | Desplazamiento | 6,5 % | 3,1 % | 2 % |
  | Cierre/apertura | 5,1 % | 2,7 % | 2 % |

  Para un registro que debe reconocer los días anómalos, **propongo M1 como regla y M2 como lectura de contexto**:
  «raro frente a la historia» frente a «raro frente al régimen reciente».
- **Por familia (M1):** 2 % de valor-días en calibración (todas, por construcción). En 2020-2021:

  | Familia | 2020-2021 | 2020 | 2021 | Estable |
  |---|---:|---:|---:|---|
  | Desplazamiento | 4,2 % | 6,5 % | 1,3 % | |
  | Volumen/precio | 3,7 % | | | |
  | Premercado | 3,5 % | | | |
  | Cierre/apertura | 3,4 % | | | |
  | Persistente | 2,1 % | | | Sí |
  | Volumen | 1,6 % | | | Sí |

- **Por liquidez (tercil del día, M1):** los valores más líquidos marcan algo más, entre 1,2 y 4 veces más que los
  menos líquidos según la familia. En `cat-v0` la diferencia era mayor (premercado: 16 % frente a 4 %).
- **Por tramo (M1, calibración → comprobación):**

  | Tramo | Calibración | Comprobación |
  |---|---:|---:|
  | Continua | 6,3 % | 8,6 % |
  | Premercado | 2,0 % | 3,5 % |
  | After hours | 0,9 % | 1,1 % |
  | Subasta de apertura | 0,7 % | 0,7 % |
  | Subasta de cierre | 0,2 % | 0,3 % |

## 3. Falsas anomalías por dispersión pequeña

Fracción de las marcas de cada medida cuya MAD está en el 10 % más bajo de esa medida:

| Medida | M0: marca-días | M0: solo por el z | M1: con MAD pequeña |
|---|---:|---:|---:|
| C3_vol_est (volumen en after hours) | 15,9 % | 87 % | 1 % |
| C3_30 / C3_60 (deriva en after hours) | 10 % | 85 % | 20 % |
| P3 (racha de volumen alto) | 8,6 % | 79 % | **73 %** |
| PRE_vol (volumen en premercado) | 8,0 % | 80 % | 39 % |
| V3_close_est (barra mixta de cierre) | 5,1 % | 65 % | **95 %** |
| C3_ext35 (recorrido en after hours) | 4,8 % | 70 % | **93 %** |
| P1 (rachas en la misma dirección) | 1,6 % | 28 % | **100 %** |
| D3_gap (minutos sin barra) | 1,0 % | 18 % | **84 %** |

- M1 resuelve el problema en las medidas continuas: rendimientos en sigmas, cocientes de volumen, VWAP.
- Las cinco en negrita son discretas (rachas enteras), llenas de ceros (after hours poco negociado) o casi constantes
  (huecos sin barras en valores líquidos). Para ellas el suelo general no basta: necesitan un criterio propio (§6).

## 4. Redundancia, persistencia y simultaneidad (M1)

- **Redundancia** (Spearman entre puntuaciones; 150 000 valor-días de calibración). 39 pares superan 0,6. Los más
  altos:
  - V1_5–V1_15: 0,94;
  - I2_stall–V1_15: 0,93. «Volumen alto sin desplazamiento» es casi siempre «volumen alto»;
  - D1_15–I3_vwap15: 0,88;
  - V1_1–V1_5: 0,88;
  - D1_15–D1_30: 0,85.
  Las mismas parejas comparten la mitad de sus marcas (Jaccard 0,45-0,55).
- **Persistencia** (marca de la misma medida en la sesión anterior del valor):
  - C3_vol_est repite al día siguiente el 51 % de las veces, 237 veces más que su frecuencia normal. Con V3_close_est
    (20 %) y P3 (16 %), es un cambio de nivel del propio valor (un after hours que se vuelve más negociado), no
    eventos sueltos;
  - en las medidas de precio, la repetición es del 19-38 %, típica de días seguidos de mercado agitado.
- **Simultaneidad** (fracción de valores elegibles con marca de la familia ese día):
  - mediana del 1 %;
  - en días de mercado, hasta el 99,8 % (desplazamiento, 12-mar-2020). Toda la semana del 9 al 19 de marzo de 2020
    supera el 80 %;
  - el volumen simultáneo cae siempre en **vencimientos trimestrales y reequilibrios de índices**: 20-sep-2019 (48 %),
    21-sep-2018, 15-jun-2018, 17-mar-2017… Es un fenómeno de mercado, no de un valor;
  - entre el 30 % y el 51 % de las marcas de desplazamiento, volumen/precio, cierre y volumen caen en días con ≥ 10 %
    de valores marcados.

## 5. Episodios y calidad del dato

- **Episodios** (M1, agrupando alertas a ≤ 10 minutos):
  - 92 273 episodios, mediana de 5 minutos;
  - percentil 90: 33 min; percentil 99: 116 min;
  - el 0,96 % pasa de 2 horas y el 0,23 % de 5 horas;
  - agrupando por tramo: mediana de 1 minuto, 0,9 % por encima de 2 h.
  - **Limitación importante:** aquí la ventana de cada alerta es la del pico de su medida, no el tramo completo en que
    supera el umbral (§7). Con los tramos completos, `cat-v0` llegaba a fusionar sesiones enteras; esta medición no
    lo reproduce y subestima la longitud.
- **Calidad:**
  - días con evento corporativo no reconstruido (0,01 % de los valor-días): 72 % con marca, frente al 10 %;
  - tamaño por operación (V2) en las 60 sesiones tras un split: 2,6 % frente a 0,3 % en V2_size_dn. Es el cambio
    de microestructura que provoca el split (más operaciones, no más grandes);
  - cierres anticipados y baja cobertura de minutos marcan menos, no más.

## 6. Propuesta de catálogo `cat-v1` (no aplicada)

1. **Normalización M1**:
   - base de 60 sesiones a fecha;
   - transformación por tipo de medida;
   - suelo de dispersión = percentil 10 de las MAD de calibración de cada medida.
   M2 se guarda como contexto.
2. **Umbral por medida, en unidades de su propia dispersión**, fijado con 2016-2019 (cuantil común por familia para
   el 2 % de valor-días). Valores congelados en `results/e2_report.json → calibration.M1`. Sin cuota diaria: en días
   de estrés se marcan los que haga falta.
3. **Criterios propios para las cinco medidas problemáticas**:
   - P1 y P3: racha mínima absoluta;
   - D3_gap: solo valores con liquidez suficiente, como ya hacía E1, con un umbral de minutos absoluto;
   - C3_ext35 y V3_close_est: exigir además percentil ≥ 99 de la base.
   Cifras concretas a fijar con la misma calibración: **pendiente, no calculado**.
4. **Redundancias:**
   - V1_5 e I2 se conservan como medidas, pero no generan alerta propia (se cuentan con V1_15);
   - D1_15/D1_30/I3_vwap15 en la misma ventana dan una sola alerta, con las demás como detalle.
   Todas las medidas brutas y normalizadas se siguen guardando.
5. **Contexto obligatorio en cada alerta**, en campos separados:
   - rareza (puntuación M1 y percentil);
   - magnitud (valor bruto);
   - simultaneidad (fracción de valores con marca de la familia ese día, y en su sector);
   - persistencia (sesiones seguidas con la misma marca);
   - calidad (evento corporativo, ventana tras un split, cobertura, cierre anticipado, medida estimada).
   «Día de mercado» = ≥ 10 % de valores marcados en la familia.
6. **Artefactos:**
   - día con evento corporativo no reconstruido → `artifact`;
   - V2 en las 60 sesiones tras un split → `artifact`.
7. **Episodios:** agrupar por tramo (premercado, apertura, continua, cierre, after hours) y no fusionar a través de
   tramos.

## 7. Limitaciones

- **Ventanas de los episodios.** Se guardan el valor y el minuto del pico de cada medida, no su serie completa (sería
  ~35 veces más espacio). La fusión excesiva de episodios de `cat-v0` no se puede reproducir con esto; para
  comprobarla hace falta recalcular las series de una muestra de valor-días. Propuesto como primer paso tras tu
  revisión.
- **Contexto de mercado.** La simultaneidad es transversal, sobre los propios valores: no se usaron barras intradía de
  SPY ni de ETF sectoriales. El sector de cada entidad es el de su última fecha.
- **Sin escisiones ni fusiones de Alpaca antes de 2020** (enmienda 7): los días con evento no reconstruido solo se
  marcan.
- **Universo:** solo miembros del S&P 500 (la única pertenencia histórica verificada); nada de Nasdaq 100 ni de las
  listas del proyecto.
- **Calibración:** el objetivo del 2 % por familia es una orientación elegida para fijar umbrales, no una propiedad de
  los datos. Otro objetivo daría otro catálogo; las tasas por medida para cualquier umbral se pueden recalcular desde
  las medidas guardadas sin repetir el cálculo pesado.
- **2020-2021 es la única comprobación fuera de calibración y está dominada por el COVID.** El periodo reservado de
  G2A sigue cerrado: no hay más datos libres.

## 8. Muestra para el laboratorio

`results/e2_lab_sample.csv` (semilla 20261121): 144 filas.
- **108 eventos M1:** hasta 3 por familia × periodo (calibración / comprobación) × liquidez.
- **36 ventanas de control** de 30 minutos, en valor-días elegibles sin ninguna marca.

Cada fila trae su enlace al laboratorio en modo ciego (`py -3 lab/server.py`).

## 9. Costes reestimados

| Concepto | Valor |
|---|---|
| Cálculo de medidas | 25,8 ms por valor-día; 19 570 s de CPU para 759 829 valor-días (≈ 1 h 20 min con 4 procesos) |
| Normalización | 3 min (4 procesos) |
| Análisis | 5 min |
| Almacenamiento | 1,1 GB entre medidas y normalización (1 450 bytes por valor-día) |
| Registro diario de ~650 valores | ≈ 17 s de CPU y ≈ 1 MB al día (~250 MB al año) |

La descarga diaria del registro bajaría unas 16 veces con la petición múltiple de barras, ya verificada pero sin
conectar (§10).

## 10. Otros puntos de la autorización

- **Petición múltiple de barras** (`AlpacaProvider.fetch_bars_multi`, `e2_multibars_check.py`):
  - equivalencia exacta con las peticiones individuales en 3 días (incluido un cierre anticipado);
  - paginación forzada correcta, sin pérdidas ni duplicados entre símbolos;
  - un símbolo inexistente devuelve una lista vacía;
  - un fallo en la 2.ª página lanza un error y no devuelve nada a medias.
  Mismo limitador y reintentos. **No conectada todavía al escaneo.**
- **`micro/shadow.py`:** declarado obsoleto; `run` solo admite `dry_run`. Solo lo usan dos pruebas; ningún script ni
  workflow lo lanza. No se borra.
- **Fallo de la unidad sin tope:** `download._window` ya exigía tope en una sesión sin cerrar; ahora también en un mes
  sin terminar. Comprobado que ninguna unidad mensual guardada estaba incompleta.
- **Descargas:** ninguna en E2. El nivel A no se ha reanudado.
- **Pruebas:** 84 de 84 (`py -3 -m pytest -q tests`).

## 11. Ficheros

| Qué | Dónde |
|---|---|
| Código (sin commit) | `e2_compute.py`, `e2_normalize.py`, `e2_analyze.py`, `micro/e2_fast.py`, `e2_multibars_check.py`, `tests/test_e2.py` |
| Cambios | `micro/providers/alpaca.py` (petición múltiple), `micro/download.py` (mes sin tope), `micro/shadow.py` (obsoleto) |
| Datos (fuera del repo) | `MICRO_DATA_DIR/features/e2_measures/`, `e2_norm/`, `results/e2_report.json`, `results/e2_alerts_M{0,1,2}.parquet`, `results/e2_lab_sample.csv` |
