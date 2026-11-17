# Microestructura v1 — Cambios aprobados tras G1.5 (2026-11-15)

Respuesta del usuario al informe G1.5: G1.5 aprobado con correcciones. Este documento recoge qué se ha hecho en cada
punto. El preregistro para aprobación está en [PREREGISTRO_G2.md](PREREGISTRO_G2.md).

**Resumen.**
1. Planes B1 y de quotes corregidos (**v2**) sin tocar v1 y sin cambiar ninguna empresa ni ningún bloque. Solo
   cambian el símbolo y el `asof` de 2 bloques. Tras la corrección, todas las sesiones de B1 sin datos se explican
   por las dos salidas de cotización (CTXS y MON). El nivel A no necesitaba corrección.
2. CTXS y MON siguen en la muestra. Sus salidas (fusiones en efectivo a 104 $ y 128 $) están verificadas con el
   8-K de cierre en la SEC y tienen una regla de tratamiento económico fijada.
3. El laboratorio muestra el volumen indeterminado por vela y método, compara los cuatro clasificadores vela a vela
   y permite las variantes de sensibilidad (retraso de la quote, TRF y trades que no actualizan barras).
4. Registro exacto de lo que se ha mirado del periodo de prueba y política de exclusión proporcionada. Con lo
   ocurrido hasta hoy, excluye 628 valor-sesiones únicas del periodo de prueba (~0,1 %) y ninguna fecha completa
   (corregido el 2026-11-16: la primera cifra, 689, contaba dos veces los valores con varias exposiciones).
5. Descargas reanudadas con los planes v2 y controles de memoria en la descarga y en el laboratorio. 44 pruebas en
   Python y 7 en JavaScript pasan.

---

## 1. Corrección de los planes B1 y de quotes (v1 → v2)

**Regla (general, no un parche para dos casos).** El símbolo y el `asof` de cada bloque en cada fecha son los que el
nivel A asigna a esa entidad (CIK) en esa fecha. El nivel A ya recorta cada ticker a su época de identidad, así
que ahí los cambios de nombre estaban bien resueltos. El script no elige si un bloque abarca dos tickers: falla.
Tampoco aplica ningún cambio de símbolo que no tenga su evidencia registrada. Script: `g2_plan_corrections.py`.

**Cambios de símbolo y su evidencia:**

| Empresa | Cambio | Primera sesión con el símbolo nuevo | Evidencia |
|---|---|---|---|
| Booking Holdings | PCLN → BKNG | 2018-02-27 | Alpaca: PCLN termina el 26-feb (cierre 1905,64); BKNG sigue sin salto (apertura del 27-feb, 1884,00). Alpaca no publica este cambio en sus acciones corporativas. |
| Fiserv | FISV → FI | 2023-06-07 | Alpaca `name_changes` (mismo CUSIP 337738108). FISV termina el 6-jun (114,23) y FI empieza el 7-jun (115,50). Antes de esa fecha «FI» era otro valor (Frank's International, que pasó a XPRO en 2021); la época de identidad lo separa. |
| Fiserv | FI → FISV | 2025-11-11 | Alpaca `name_changes`. Ningún bloque B1 cae ahí; el nivel A ya lo tenía bien. |

**Bloques que cambian** (las 100 sesiones de cada uno; ni la empresa, ni las fechas, ni el estrato cambian):

| Bloque | Periodo | v1 | v2 |
|---|---|---|---|
| dev-036 (2018-06-12 → 2018-10-31) | desarrollo | PCLN, asof 2019-01-11 | BKNG, sin asof (vigente) |
| test-024 (2023-11-15 → 2024-04-10) | prueba | FISV, asof 2024-01-11 | FI, asof 2026-01-13 |

El bloque test-024 está también en el plan de quotes (sus 20 primeras sesiones): mismo cambio.

**Versiones congeladas** (`MICRO_DATA_DIR/samples/`). Cada `.meta.json` guarda la versión anterior, su hash, los
cambios y su justificación:

| Plan | SHA-256 del plan | Filas |
|---|---|---:|
| `b1_plan_v1` (sin tocar; comprobado antes y después) | `72da1f76…` | 200 |
| `b1_plan_v2` | `e5031604…` | 200 |
| `quotes_plan_v1` (sin tocar) | `87d03f56…` | 20 |
| `quotes_plan_v2` | `7223e6c8…` | 20 |
| `plan_exits_v2` (salidas y tratamiento) | `0437be0c…` | 2 |

Las columnas `symbol_v1`, `asof_v1` y `correction` de v2 dejan el cambio visible fila a fila.

**Revalidación de cobertura** (barras diarias con volumen para el símbolo y `asof` que pide cada plan):

| | Valor-sesiones | Con datos | Sin datos | Explicadas por una salida |
|---|---:|---:|---:|---:|
| B1 v1 | 20 000 | 19 739 | 261 | 61 |
| **B1 v2** | 20 000 | **19 939** | **61** | **61** |
| Quotes v2 | 400 | 400 | 0 | — |

Ya descargado con v2: las 20 sesiones de quotes de FI (2,77 M de quotes, calidad A). Los trades de test-024 y de
dev-036 llegan con la etapa B1. Las 20 unidades vacías que pidió v1 (trades y quotes de FISV) siguen en el
manifiesto, pero ya no las usa ningún plan.

**Nivel A: no necesita corrección.** Comprobado entidad por entidad para las dos empresas:
- Booking: PCLN del 2016-01-04 al 2018-02-26 y BKNG desde el 2018-02-27.
- Fiserv: FISV hasta el 2023-06-06, FI del 2023-06-07 al 2025-01-13 y FISV (vigente) después.
- Ningún día sin negociación en ninguna de las dos.

En todo el universo hay 295 entidad-días sin negociación de 1,68 millones. Casi todos son valores del proyecto
antes de salir a bolsa (AWX, QXO, HIMS…), no tickers mal asignados.

**Hallazgo nuevo, sin relación con los nombres.** El bloque test-097 (CZR) necesita 7 sesiones más de barras
diarias para medir su resultado a 40 sesiones (2025-12-19 → 2025-12-30): la referencia diaria de G1 se corta 60
sesiones después de que el valor sale del índice. CZR sigue cotizando: no es una salida. Hay que descargar esas
barras antes de medir resultados.

### Salidas de cotización: CTXS y MON

Siguen en la muestra. Sus sesiones posteriores a la salida no se inventan ni se sustituyen: no generan
observaciones porque ya no hay mercado.

| Bloque | Empresa | Última sesión | Fecha efectiva | Contraprestación | Fuente | Sesiones elegibles con mercado |
|---|---|---|---|---|---|---:|
| dev-018 | Monsanto (MON) | 2018-06-06 (cierre 127,95) | 2018-06-07 | 128,00 $ en efectivo (Bayer) | 8-K 0001193125-18-188226, Item 2.01 | 53 de 60 |
| test-086 | Citrix (CTXS) | 2022-09-29 (cierre 103,90) | 2022-09-30 | 104,00 $ en efectivo (Cloud Software Group) | 8-K 0001193125-22-256805, Item 2.01; Alpaca `cash_mergers` | 6 de 60 |

**Tratamiento económico** (fijado en `plan_exits_v2` y en el preregistro). Se aplica a toda observación cuyo
horizonte cruce una salida:

| Tipo de salida | Resultado de la observación |
|---|---|
| Fusión en efectivo | Se cobra el precio de la operación en la fecha efectiva; el resto del horizonte rinde 0 (efectivo). |
| Fusión en acciones | Se convierte a acciones del comprador con la relación de canje y se sigue su serie. |
| Fusión mixta | Combinación de las dos anteriores. |
| Quiebra o exclusión sin precio | Último precio con −30 % de rentabilidad de deslistado, y sensibilidad con 0 % y −100 %. |

- La referencia de mercado se mide con la misma regla.
- La observación nunca se descarta (sería sesgo de supervivencia).
- Como sensibilidad se informa también el resultado excluyéndolas.

Las dos salidas de B1 son fusiones en efectivo. Las verifiqué yo con EDGAR, no son un supuesto.

## 2. Delta y agresividad

**En el laboratorio** (`lab/`, uso local):
- **Volumen indeterminado** visible:
  - en el resumen de la ventana;
  - en cada nivel de precio;
  - nuevo: por vela y método.
- **Comparación de métodos por vela (nueva).** Para cada vela da el delta y el % indeterminado con los cuatro
  clasificadores, y marca las velas en que el signo cambia según el método. Un delta menor que el 5 % del volumen
  clasificado cuenta como ≈0.
- **Variantes de sensibilidad** (desplegable «Sensibilidad del agresor»):
  - retraso de la quote en ms;
  - quote estrictamente anterior o simultánea;
  - TRF fuera de la secuencia del tick;
  - secuencia del tick solo con trades que actualizan barras (nuevo).

  Además, un filtro nuevo, «solo trades que actualizan barras», quita los que según las reglas oficiales no mueven
  máximo y mínimo: odd lots, comunicaciones tardías y precios no estándar. Las opciones usadas se guardan con cada
  episodio.

**Para G2** (detalle en el preregistro):
- Las hipótesis principales usan variables **sin lado agresor**: volumen ejecutado por precio, desplazamiento del
  precio relativo al volumen, y persistencia y evolución de las concentraciones de negociación.
- Las variables de agresor quedan como **exploratorias**. Para pasar a confirmatorias tendrían que tener el mismo
  signo con todas las variantes y aportar valor incremental sobre las estables, comprobado solo en desarrollo.
- Restricción práctica: en B1 solo hay quotes en 20 de los 200 bloques. A escala, el único método disponible es la
  regla del tick. Lee-Ready y EMO solo se pueden comparar en la submuestra de quotes.

## 3. Protección del conjunto confirmatorio

### Qué se ha mirado del periodo de prueba (2022-01-03 → 2026-09-14, embargo desde 2021-10-29)

Registro completo: [test_exposure_registry.csv](test_exposure_registry.csv). Lo genera `g2_test_exposure.py` a
partir de los registros que dejan los propios scripts. Contiene solo identificadores y fechas, sin datos de mercado.

| Nivel | Qué | Dónde |
|---|---|---|
| E1 | Comparación técnica de clasificadores: **240 sesiones regulares de 12 valores** (un bloque de 20 sesiones cada uno). Solo se calcularon % sin clasificar, concordancia entre métodos, cuota de TRF y de odd lots, punto medio y antigüedad de la quote. **Sin rentabilidades ni variables candidatas.** | CTLT 2022-04/05 · POOL 2023-01/02 · BK 2023-02/03 · NKE 2023-10 · FSLR 2024-01/02 · SNA 2024-11/12 · VTRS 2024-12/2025-01 · PAYX 2025-04/05 · TYL 2025-07/08 · AMZN 2025-11/12 · AMP 2026-01/02 · AKAM 2026-03/04 |
| E0 | Conciliación trades↔barras de URI 2025-11-28 y OSCR 2026-03-09 (G1); descarga de FI test-024 (sin análisis) | — |
| E0 | Barras diarias de todo el universo (cobertura, identidad, liquidez previa para muestrear y comprobación de los planes) y descargas del nivel A y de B1 con su calificación de calidad | todo el periodo |
| — | Laboratorio: **ningún acceso** a fechas de prueba (no existe registro de accesos); biblioteca de episodios vacía | — |

Fuera del periodo de prueba, con el resultado visto (E3):
- el estudio de NVDA (2026-11-12);
- el contraste GOOGL (2026-10-29);
- los 58 candidatos cribados para elegirlo (52 valores, 2026-09-15 → 2026-11-13).

Al elegir el contraste se calculó su resultado: recuperación en el día y a 5 sesiones.

### Elecciones de método: solo con desarrollo

Las cifras de G1.5 mezclaban desarrollo y prueba. Se han recalculado **solo con los 140 días de desarrollo** (7
valores, 2017-2021). Las elecciones del preregistro se justifican con esta tabla, no con la del informe G1.5:

| Mediana por día, solo desarrollo | Valor |
|---|---:|
| Volumen sin clasificar: tick / Lee-Ready / bid-ask estricto | 2,7 % / 7,3 % / 46,0 % |
| Acuerdo tick~Lee-Ready (si ambos clasifican) | 85,3 % |
| Lee-Ready con la quote retrasada 1 s: volumen que mantiene el lado | 87,0 % |
| Volumen TRF / odd lots / en el punto medio | 28 % / 16 % / 19 % |

Las tres conclusiones de G1.5 se sostienen con desarrollo solo:
- **El bid-ask estricto no sirve como método principal:** deja sin clasificar el 46 % (el 55 % en el tercil menos
  líquido).
- **El emparejamiento con la quote importa:** retrasarla 1 s cambia de lado el 13 % del volumen.
- **La composición cambia dentro del propio desarrollo:** odd lots del 11 % (2017) al 20-26 % (2019-2021). Por eso
  las variables se normalizan frente a la historia del propio valor.

Hay pocos valores por año, así que ninguna cifra por año es representativa del mercado.

### Política de exclusión (proporcionada; `micro/exposure.py`)

Se excluye lo que pudo influir en una decisión, y nada más:

| Nivel | Qué se vio | Exclusión del contraste confirmatorio |
|---|---|---|
| E0 técnica | descarga, calidad, identidad, cobertura, liquidez previa | ninguna |
| E1 estadística sin resultados | estadísticas de microestructura sin rentabilidades | ninguna; esas cifras no pueden elegir métodos ni parámetros, y el contraste se repite sin esas ventanas como sensibilidad |
| E2 variable vista | un episodio con las variables candidatas, sin ver el después | ese valor, fechas de decisión en [día − H, día + L] |
| E3 resultado visto | el precio posterior, o una criba por resultado | igual que E2, para cada valor visto o cribado |
| M de mercado | un dato agregado de todo el mercado en una fecha | esa fecha para todos los valores, en [día − H, día + L] |

- H = horizonte más largo; L = ventana más larga de las variables. Una observación decidida en t usa variables de
  [t − L, t] y resultado de (t, t + H], así que un día visto d la afecta si t cae en [d − H, d + L].
- Cualquier método o parámetro elegido con información del periodo de prueba **degrada a exploratoria** la
  hipótesis que lo usa. Eso no se arregla excluyendo observaciones.

**Efecto hoy** (ventana de variables de 140 sesiones y H = 40, fijadas en G2A_PROTOCOLO; actualizado 2026-11-16):
- Las ventanas E3 posteriores a la prueba entran 40 sesiones hacia atrás en ella, desde el 2026-07-21.
- Excluyen **628 valor-sesiones únicas de 51 valores**, en torno al 0,1 % de la prueba. La primera versión decía 689
  porque sumaba ventana por ventana y contaba dos veces los valores con más de una exposición (GOOGL, AMD, FICO…).
- Auditoría fila a fila, con la ventana exacta y su justificación: [test_exclusion_audit.csv](test_exclusion_audit.csv).
  Las 57 exposiciones que tocan la prueba son E3 (resultado posterior visto): la criba de G1.5 (hueco ≤ −7 % con
  volumen alto, con su cierre a 5 sesiones visto) y GOOGL como contraste. La ventana va de d − 40 sesiones al final
  de la prueba; hacia delante (d + 139) cae fuera de la prueba. NVDA (12-nov-2026) no toca la prueba.
- Las exposiciones técnicas (E0) y las de estadísticos de clasificadores (E1) siguen en el registro con su
  trazabilidad, sin excluir nada.
- **Sensibilidad de mercado (nueva):** la criba descargó las barras diarias de todos los miembros del S&P 500 y
  comprobó en cada valor-día de 15-sep a 5-nov-2026 si hubo ese hueco. De los no elegidos solo se sabe «no hubo hueco
  ≤ −7 % con volumen alto», un conocimiento negativo y débil. No se excluye en el contraste principal; como
  sensibilidad se excluyen todas las fechas de decisión desde el 2026-07-20 (40 sesiones, ~20 700 valor-sesiones).
- Las 240 sesiones E1 no se excluyen, pero se informa la sensibilidad sin ellas.
- **Ninguna fecha se excluye entera.**

## 4. Descargas y memoria

- La descarga se paró y se relanzó a las 22:40 UTC con el código nuevo. Es reanudable: el nivel A siguió donde iba,
  en la unidad 39 817 de 76 340. Orden de las etapas: quotes (las 20 de FI, ya hechas) → nivel A → piloto B1 con v2.
- **Control de memoria en la descarga** (`g2_downloads.py`):
  - no encola una unidad nueva si quedan menos de 1,5 GB libres (`MICRO_DL_MIN_FREE_MB`) y registra la espera;
  - un `MemoryError` deja la unidad como fallida reintentable, en vez de matar el hilo;
  - se mantiene la salida por bloqueo con reinicio automático.
- **Control de memoria en el laboratorio** (`lab/server.py`):
  - estima el pico de cada día antes de cargarlo (≈260 B por trade y 120 B por quote, medido);
  - exige dejar libres 2,5 GB para el resto del equipo (`MICRO_LAB_RESERVE_MB`);
  - carga un solo día a la vez;
  - si no cabe, vacía la caché y, si aun así no cabe, rechaza la carga con un mensaje.

  Un día como NVDA del 12-nov (9,6 M de trades) necesita unos 2,5 GB.
- El límite de disco no cambia: la descarga se detiene si quedarían menos de 40 GB libres en D:. Ahora quedan 135 GB.

## 5. Pruebas

`py -3 -m pytest research/microstructure_v1/tests -q`: **44 pasan** (38 de antes + 6 nuevas):
- comparación de métodos por vela;
- filtro y referencia del tick sin trades que no actualizan barras;
- rechazo del laboratorio por memoria;
- espera de la descarga por memoria;
- corrección de planes con evidencia obligatoria, fallo si el bloque abarca dos tickers y salidas sin relleno;
- ventanas de exclusión proporcionadas.

`node tests/test_lab_layout.js`: 7 pasan.

## 6. Correcciones al informe G1.5

- Las sesiones de prueba usadas eran **240**, no 260 (12 valores × 20).
- El bloque de PCLN es de **2018** (junio-octubre), no de 2019. El cambio a BKNG fue el 27-feb-2018.
- La sospecha de un hueco de Fiserv en el nivel A era errónea: no lo hay.
