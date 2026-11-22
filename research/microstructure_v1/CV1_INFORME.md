# cat-v1 — implantación y validación final

Fecha: 2026-11-21 (LAWNMOWER). Encargo: aprobación de cat-v1 tras `E2B_INFORME.md` (texto del usuario, 2026-11-21).
- Catálogo observacional, aplicación **manual**.
- Sin E3, sin tareas programadas, sin cambios en producción, sin commits.
- cat-v0 se conserva intacto y reproducible.

## 0. Resumen

1. **Implantado** en el registro y el laboratorio:
   - parámetros congelados con hash;
   - alertas y episodios históricos regenerados con ventanas reales (2016-01-04 → 2021-10-28);
   - escaneo manual en vivo con `--catalog cat-v1`;
   - consulta de cualquier valor y sesión, tenga o no alerta.
2. **Las capas 1 y 2 no han cambiado:**
   - 71 587 ficheros de datos brutos con el mismo tamaño y fecha;
   - 1 319 ficheros con el mismo sha256: manifiesto, referencia, medidas, normalización y registro y resultados de cat-v0.
3. **Reproducible:** dos ejecuciones dan salidas con el mismo sha256. Los 145 377 valores recalculados minuto a minuto
   coinciden con los guardados, y la evaluación fila a fila coincide con la vectorizada en todas las filas.
4. **Validación sobre 11 casos** (§4): las alertas, medidas e instantes son los esperados.
   - Dos limitaciones de diseño: el after hours de valores muy activos, y la subasta de cierre, que solo se mide con
     trades.
   - Apareció un error de datos que ningún control detectaba: JWN 2018-03-26, con dos series de precio mezcladas.

## 1. Qué se ha implantado

| Pieza | Fichero | Qué hace |
|---|---|---|
| Parámetros congelados | `catalog/cat_v1_params.json` (+ `.sha256`), `catalog/cat_v0_params.json` (+ `.sha256`), `cv1_freeze.py` | Copia las cifras ya fijadas en E2 y E2B. `micro/catalog_v1.py` verifica el hash al cargarlas y se niega a usar un fichero alterado. Una versión congelada no se reescribe: se crea otra. |
| Reglas | `micro/catalog_v1.py` | Normalización M1 por medida; M2 solo como contexto; criterios de las medidas discretas; V3_close_est «requiere trades»; ventanas reales; medidas de resumen como puntos con su ventana original; episodios por tramo; instantes; conocimiento del umbral. |
| Registro de incidencias de datos | `catalog/data_incidents.json` | Separado de los parámetros: crece con cada comprobación y no cambia ninguna regla (§3). |
| Reconstrucción histórica | `cv1_build.py` | Fase 1 por entidad (marcas vectorizadas, recálculo de series y ventanas reales, comprobaciones cruzadas); fase 2 agregada (sector a fecha, simultaneidad, calidad, episodios). |
| Registro del laboratorio | `micro/event_store.py` | Espacio por versión: `events/` (cat-v0, sin tocar) y `events/cat-v1/`. Las versiones no se mezclan. |
| Escaneo manual en vivo | `micro/event_scan.py`, `ev_scan.py --catalog cat-v1` (por defecto; `cat-v0` sigue disponible) | Las 44 medidas de cada valor-día con su estado y las alertas con ventanas reales. |
| Consulta de cualquier valor-día | `micro/valorday.py`, `/api/valorday` | Registro en vivo → capa 2 histórica → cálculo bajo demanda desde las barras locales, sin escribir nada. |
| Laboratorio | `lab/server.py`, `lab/app.js`, `lab/index.html` | Selector de catálogo. Puntos frente a ventanas. Tabla de alertas con rareza, magnitud, persistencia, simultaneidad, calidad, estructural, instantes y umbral conocido. Panel con todas las medidas del valor-día. |
| Integridad | `cv1_integrity.py` | Huella antes y después y comparación. |
| Validación | `cv1_validate.py`, `tests/test_lab_cat_v1_visual.js` | Los casos de §4 y capturas del laboratorio (fuera del repo: contienen datos de mercado). |
| Pruebas | `tests/test_catalog_v1.py` (11) | Hash, transformaciones idénticas a E2, regla y empate, criterios especiales, V3, D3 y liquidez, ventanas, puntos, episodios, conocimiento del umbral, versiones separadas. En total pasan 94 de la batería de microestructura (1 omitida). |

**Dos decisiones de implementación que no estaban escritas en la propuesta:**
- **Tolerancia de empate.** En las medidas discretas el umbral es un cuantil que coincide con un valor alcanzable. La
  capa 2 guarda float32 y la evaluación usa float64. Sin tolerancia, 5 valor-días de prueba caían a uno u otro lado
  según el redondeo. «≥ umbral» incluye el empate, con un margen relativo de 1e-6, en las dos rutas. Tras el cambio,
  0 discrepancias en todo el histórico.
- **Cada tramo continuo por encima del umbral es una alerta propia.** Una medida puede dar varias en un día (en CHTR
  2020-12-17, cuatro ventanas de I2_stall en 15 minutos). Todas van al mismo episodio.

## 2. Resultados del histórico (S&P 500, 2016-01-04 → 2021-10-28)

- 714 076 valor-días elegibles, de los que 65 686 tienen alguna alerta.
  - 235 634 alertas: 190 560 de ventana y 45 074 puntos.
  - 97 089 episodios: mediana de 1 alerta y de 15 minutos; el 2,1 % dura más de 120 minutos.
- **Las tasas por familia en calibración reproducen exactamente las de E2B** (C 1,95 %, D 1,74 %, P 1,78 %, V 1,80 %,
  I y PM 2,00 %). En 2020-2021 suben C, D, I y PM (3,2-3,8 %), por el estrés de 2020.
  - El 86 % de las alertas de 2020 cae en días en que ≥ 10 % de los valores marcan la misma familia; en 2021, el 7 %.
- **Episodios largos** (> 120 min): 2 054, todos en negociación continua; la mitad en días de mercado (marzo de 2020).
  - De la otra mitad, la mayoría son valores con una opa en efectivo pendiente y el precio clavado (SPLS 2017, TE y
    CPGX 2016, TIF 2020). Su dispersión es casi nula y cualquier movimiento de céntimos es raro para ellos.
  - Es un efecto estructural real que el catálogo describe bien. No hay ninguna etiqueta que lo identifique (§6).
- **Instantes:**
  - 108 574 alertas son de 2016-2019, el periodo con el que se fijaron los umbrales: `threshold_knowledge =
    in_sample_calibration`;
  - 127 060 son de 2020 a 2021-10-28: `retrospective_out_of_sample`;
  - nada es «prospectivo» hasta los escaneos posteriores al 2026-11-21.
  - Ningún umbral se presenta como conocido en su fecha.
- **Sector a fecha** (el sector que tenía el valor ese día, no el actual):
  - 695 430 valor-días con la instantánea vigente;
  - 18 575 con la siguiente (alta a mitad de año: el sector es casi constante, pero es información posterior);
  - 71 con la anterior.
- **Estados:**
  - 233 963 candidatas;
  - 496 artefactos: incidencia de datos corroborada y huecos de apertura en días con evento corporativo no
    reconstruido;
  - 1 175 sospechas de datos: 141 del 2019-10-09 y 1 034 de JWN 2018-03-26.

**En vivo** (GOOGL, NVDA y PLTR del 29-oct al 17-nov, solo barras locales):

| | Alertas | Episodios |
|---|---:|---:|
| cat-v0 | 223 | 29 |
| cat-v1 | 18 | 10 |

El 12-nov, NVDA tenía 36 alertas en un solo episodio de cat-v0; con cat-v1 son 10, en tres episodios (premercado,
I2_stall en la continua y primeros minutos). La línea base en vivo arranca el 2026-09-15 (después del periodo
reservado): el 22-oct no llega a 30 sesiones y no se evalúa.

## 3. Calidad de datos

**Dos ejes, separados en cada alerta y episodio:**
- `data_quality` (errores o sospechas del dato):
  - `corroborated_data_incident_day`, `suspected_data_outage_day`, `suspected_mixed_price_series`;
  - `corp_event_unreconstructed`, `unadjusted_split_in_baseline` (en vivo), `low_minute_coverage`.
- `structural` (el mercado o el valor):
  - `documented_market_halt_day`, `market_wide_family_day`, `early_close`;
  - `post_split_V2_window`: efecto estructural de un split, separado de los errores de datos.

**Las observaciones originales no se tocan.** Solo cambian el estado y la etiqueta de las alertas; la capa 2 sigue
igual (§0).

**Huecos simultáneos**, comprobados con dos fuentes:
- trades y barras de Alpaca (otro endpoint del mismo proveedor), leídos en memoria:
  `results/cat_v1/gap_coverage_check.json`;
- búsqueda de incidencias generales de mercado.

| Día | Qué falta | Proveedor | Fuente externa | Clasificación |
|---|---|---|---|---|
| 2019-08-12 | ≈15:20-16:00, 71 % de los valores | En los valores de NYSE los trades también desaparecen desde ≈15:25 (PFE, WFC, T); los de Nasdaq (AAPL, MSFT) están completos | CNBC: problema de procesado del sistema consolidado (CTA) desde ≈15:15 ET; se negoció con normalidad, pero se retrasó la publicación de operaciones y cierres | **Corroborada**: incidencia de difusión del dato. Las alertas que se solapan con la ventana en valores con hueco propio pasan a artefacto (460) |
| 2019-10-09 | ≈13:01-14:18, 19-23 % de los valores | Faltan los trades de 13:05 a 14:15 en PFE, ORCL, MS y MO; JPM y AAPL completos | Ninguna incidencia general encontrada | **Sospecha sin confirmar** (141 alertas) |
| Marzo de 2020 (9, 12, 16, 18) | Paradas de 14-15 min | — | Cortacircuitos de nivel 1 documentados | Evento de mercado, no artefacto: etiqueta estructural |

**JWN 2018-03-26, error que ningún control detectaba:**
- Toda la sesión, las barras alternan cada minuto entre ≈47 $ (cierre anterior: 46,7 $) y ≈63,7 $.
- En los trades de Alpaca, de 10:30 a 10:50 ET, hay 642 operaciones a 63,58-63,78 $ y 371 a 46,91-47,13 $, en todas las
  bolsas.
- Casi con seguridad son operaciones de otro instrumento asignadas a JWN.
- Apareció como un episodio de 1 030 alertas fuera de día de mercado.
- No hay otra fuente de minuto para confirmarlo: queda como sospecha, en `valor_day_incidents`.
- Es probable que haya más casos así (§6).

## 4. Validación de casos

Elegidos por regla fija, no por su resultado (`cv1_validate.py`). En todos:
- las medidas marcadas en el panel del valor-día son exactamente las de las alertas registradas;
- el laboratorio carga barras, alertas y medidas;
- las 11 capturas salen sin errores de página.

Horas de Nueva York; «disponible» = detección + 15 min (plan gratuito).

| Caso | Valor y día | Alertas | Lo que muestra |
|---|---|---|---|
| Día ordinario, histórico | AAPL 2019-12-30 (el día de 2019 con menos alertas: 1,2 % de los valor-días) | 0 | Las 44 medidas visibles sin alerta; la más alta, D1_30_up, al 45 % de su umbral. |
| Día ordinario, actual | GOOGL 2026-11-17 | 0 | Desde el registro en vivo; la más alta al 23 % del umbral. |
| Estrés generalizado | AAPL 2020-03-16 (cortacircuito) | 4 | PRE_ret (punto 09:30, ventana original 04:00-09:30); D3_jump 09:45-09:46 (reapertura tras la parada; disponible 10:01); C1_5 y C1_10 al cierre. Simultaneidad 77-95 % del mercado, etiquetas de parada y de día de mercado. D3_gap no se marca: las paradas del 9 y el 12 ya estaban en su línea base. |
| Volumen alto sin desplazamiento, histórico | CHTR 2020-12-17 | 8 | V1_1 = 6 046 veces el volumen esperado a las 14:02, V2_size, cuatro ventanas de I2_stall (13:52-14:17) y ninguna de desplazamiento. Un episodio. 2 % del mercado: fenómeno propio del valor. |
| Volumen alto sin desplazamiento, actual | NVDA 2026-11-10 | 2 | I2_stall 10:46-11:01 y P3 (volumen alto de 09:31 a 16:00, 389 minutos seguidos). |
| Subasta de cierre, con trades | PLTR 2026-11-17 | 0 | V3_close_est = «requiere trades». El desglose con trades da una subasta de cierre del 15,2 % del volumen continuo; la estimación con barras, 0,186. |
| Subasta de cierre, histórico | A (NYSE) 2019-06-03 | 0 | La barra de las 16:00 vale 0, como en 280 de los 500 miembros ese día. Estado «requiere trades». |
| After hours, actual | PLTR 2026-11-17 | 0 | Recorrido del 1,9 %, el máximo de sus 45 sesiones de base, pero M1 = 6,9 frente a un umbral de 318 (§5). |
| After hours, histórico | VRTX 2021-06-10 | 3 | Caída del 18,7 % en los primeros 35 min (16:01-16:36), C3_30 y C3_60 como puntos; 1 % del mercado. |
| Datos incompletos, corroborados | PFE 2019-08-12 | 5 | D3_gap 15:32-16:00, y los saltos y retornos alrededor del hueco: los cinco son artefacto, con la fuente citada. |
| Datos incompletos, sospecha | PFE 2019-10-09 | 1 | D3_gap 13:04-14:09 = sospecha sin confirmar. |

**Cualquier valor y sesión, con o sin alerta:**
- JNJ 2019-12-30 sale de la capa 2;
- PLTR 2020-11-27, que no está en la capa 2 (no era del S&P 500), se calcula bajo demanda desde las barras locales sin
  escribir nada;
- GOOGL 2026-11-12 sale del registro en vivo.
- En modo ciego, el panel del valor-día no se muestra hasta el fin del after hours: sus medidas resumen la sesión
  entera.

## 5. Limitaciones

- **After hours de valores muy activos.** Los umbrales de C3 en unidades de dispersión son muy altos (118 en C3_30, 318
  en C3_ext35). La familia C se calibró con un cuantil común, y lo dominan los valores cuyo after hours casi no se
  mueve. Con un 1-2 % ya se marca un valor tranquilo; uno activo (PLTR) necesita mucho más. Así lo dejó la calibración
  aprobada; no lo he cambiado.
- **Subastas.** Con barras no se miden bien, sobre todo en NYSE. Necesitan trades, y hoy los trades solo existen como
  muestras.
- **En vivo:**
  - las barras no se ajustan por splits, así que la alerta lleva `unadjusted_split_in_baseline` si hubo uno en su base;
  - la simultaneidad solo se calcula sobre los valores escaneados, y sin al menos 50 valores no se declara día de
    mercado.
- **Cobertura:**
  - histórico: S&P 500 de 2016 a 2021-10-28;
  - periodo reservado de G2A: bloqueado;
  - desde el 2026-09-15: solo lo escaneado a mano.
- **El desglose con trades** (`ev_drilldown.py`) sigue enlazado a los episodios de cat-v0. Con cat-v1 se usa su ventana
  manual.
- **El dibujo de precio del laboratorio es estrecho** cuando la tabla de alertas es ancha, y las horas del eje se
  solapan. Es estético; no se ha tocado.

## 6. Lo que queda para tu decisión

1. **Registro diario:** la pasada `regular` o `full` diaria del universo, y su tamaño.
2. **Control de series de precio mezcladas:** un control genérico, por ejemplo «precio que alterna entre dos niveles
   separados en más de X % durante N minutos». Necesita recorrer las barras: unos 50 minutos para todo el histórico.
3. **Etiqueta estructural de «opa pendiente con precio clavado»:** útil para leer los episodios largos fuera de días
   de mercado.
4. **Las capacidades que anunciaste:** evolución del Volume Profile entre sesiones, búsqueda de estructuras
   semejantes y acceso selectivo a trades y quotes (incluido enlazar el desglose con los episodios de cat-v1).

## 7. Dónde está cada cosa

- **Repo (sin datos de mercado):**
  - `catalog/`, `micro/catalog_v1.py`, `micro/valorday.py`;
  - `cv1_freeze.py`, `cv1_build.py`, `cv1_integrity.py`, `cv1_validate.py`;
  - pruebas y laboratorio.
- **`MICRO_DATA_DIR/results/cat_v1/`:**
  - `alerts.parquet`, `episodes.parquet`, `day_family.parquet`, `day_sector_family.parquet`;
  - `build_manifest.json`, con hashes, versión de código y cifras;
  - `validation_cases.json`, `gap_coverage_check.json`;
  - `screens/`, con las capturas.
- **`MICRO_DATA_DIR/events/cat-v1/`:** registro del laboratorio, retrospectivo (`pass = retro`) y en vivo.
- **Integridad:** `results/cv1_integrity_before.json`, `cv1_integrity_after2.json`.
