# U1 — Actualización y conciliación del universo (2026-11-21)

Autorización: aprobación del usuario del 2026-11-21 («Actualización del universo»). Código: `u1_universe_registry.py`,
`micro/event_universe.py`. Pruebas: `tests/test_universe_registry.py` (5). Datos: `MICRO_DATA_DIR/reference/`
(`universe_sources/` con las fuentes tal cual; `universe_registry/` con las tablas y su `manifest.json`).

## 1. Qué se ha hecho

Un registro nuevo con cuatro capas separadas, como pediste:

| Capa | Tabla | Clave | Fuente |
|---|---|---|---|
| Identidad del emisor | `issuers` (623) | CIK (S&P 500); ticker (Nasdaq 100) | Wikipedia + SEC (nombres y nombres anteriores con fechas) |
| Instrumento y ticker | `instruments` (630) | emisor + ticker, con desde/hasta | Wikipedia + Alpaca |
| Composición a cada fecha | `membership` (630 tramos) | índice + emisor + ticker | 96 revisiones de la lista del S&P 500 y 17 de la del Nasdaq 100 |
| Disponibilidad en Alpaca | `provider_availability` (642) | símbolo | `/v2/assets` + barras |

Además: `events` (47 cambios fechados, con el método de cada fecha) y `successions` (4 cambios de ticker del mismo
emisor).

**No se ha modificado** `reference/universe_intervals.parquet`, el de G1, porque lo usan los planes congelados de
G2A. Hasta la instantánea de G1 (2026-01-14) manda ese fichero; desde ahí, el registro nuevo.

## 2. EQR, AvalonBay y VMRK

Verificado con tres fuentes independientes, sin reemplazar nada hacia atrás:

- **SEC:** el CIK 906107 se llamó «Equity Residential» hasta el 2026-08-12 y hoy es «Vivmark Residential», con el
  ticker VMRK en NYSE. AvalonBay (CIK 915912) presentó el 2026-08-17 un 8-K con la culminación de la operación
  (punto 2.01) y su exclusión de cotización (3.01), y un formulario 25-NSE.
- **Alpaca:** el activo EQR ya no existe (404); VMRK está activo en NYSE.
  - Con el símbolo EQR, la serie termina el 2026-08-17.
  - Con VMRK y `asof` anterior a la fusión, la primera barra es del 2026-08-18.
  - El precio es continuo (63,66 → 64,03): es el mismo instrumento con otro ticker.
  - AVB está inactivo y su última barra es del 2026-08-14.
- **Wikipedia:** RDDT entra en el S&P 500 el 2026-08-18, en la plaza de AVB.

Cómo queda en el registro:
- **Emisor 906107:** EQR del inicio al 2026-08-17 y VMRK desde el 2026-08-18. Es miembro sin interrupción.
- **AVB:** sale el 2026-08-14, fecha **aproximada** (es su última barra; ver §4).
- **Fecha por fecha:** al 2026-08-14 el universo contiene EQR y AVB; al 2026-08-18, VMRK y RDDT.
- **Matiz sobre «la compañía resultante»:** el registrante superviviente es el de EQR (mismo CIK y precio continuo).
  AvalonBay desaparece como emisor.

## 3. Otros cambios corporativos con el mismo procedimiento (desde el 2026-01-14)

**Cambios de ticker del mismo emisor:**
- **BK → BNY:** 2026-05-21; continuidad de precio verificada.
- **PSKY → SKYD:** 2026-10-06; continuidad de precio verificada. La SEC confirma el nombre anterior «Paramount Skydance»
  hasta el 2026-10-06.
- **SATS → ECHO (EchoStar):** 2026-06-24. **SATS se reutiliza desde el 2026-10-20 para otra empresa**: Alpaca le da
  un historial nuevo. Queda marcado en `old_ticker_reused_from`, para que nadie una las dos series por el ticker.

**Corrección de identidad:** a XOM se le corrigió el CIK en Wikipedia el 2026-08-07. Se registra como corrección, sin
interrumpir su pertenencia.

**Entradas y salidas:** 19 en el S&P 500 y 4 en el Nasdaq 100. Por ejemplo:
- DAY sale el 2026-02-03 y entra CIEN el 2026-02-09;
- MTCH, MOH, PAYC y LW salen el 2026-03-20; entran VRT, LITE, COHR y SATS el 2026-03-23;
- KVUE sale el 2026-11-03 y entra OKTA el 2026-11-04.

La lista completa, con el método de cada fecha, está en `events.parquet`.

**Cambios anteriores al 14 de enero:** MMC → MRSH y FI → FISV ya figuraban en la instantánea de G1. En el fichero de
G1 aparecen como entradas del 2026-01-15, un artefacto de esa reconstrucción. El registro nuevo los corrige para las
fechas posteriores; las anteriores siguen en G1, sin tocar.

## 4. Cómo se fechan los cambios (y cuánta confianza dan)

| Método | Cambios | Fiabilidad |
|---|---:|---|
| Columna «Date added» de Wikipedia (entradas) | 16 | alta: es la fecha efectiva publicada |
| Salida emparejada con una entrada de la misma edición | 13 | alta: la salida es el día anterior |
| Fecha en el comentario de la edición («effective 9-Feb-2026») | 7 | alta |
| Cambio de ticker fechado con Alpaca (primera barra del ticker nuevo) | 4 | alta: viene de los datos |
| Hora de la edición de Wikipedia (`edit_timestamp_approx`) | 7 | **aproximada** |

Las 7 aproximadas son las salidas por adquisición (DAY, HOLX, EA, AVB), dos salidas del Nasdaq 100 y la corrección de
XOM. Para cada salida se guarda también la última barra en Alpaca (`alpaca_last_bar`) como evidencia: en las
adquisiciones coincide con la fecha registrada o queda a un día.

## 5. Universo actual de E3 tras la conciliación

- **Composición:** S&P 500 (503) y Nasdaq 100 (101) idénticos a los que ya se usaban; la revisión más reciente de
  Wikipedia es del 2026-11-08.
- **Valores:** 619 en lugar de 620. EQR deja de pedirse; consta en `superseded` como sustituido por VMRK desde el
  2026-08-18, que ya estaba en el universo por el S&P 500.
- **No cubiertos por el proveedor (3):** GTBIF, MAPS y PLNH, todos de OTC, que proceden de las listas del proyecto.
  - Alpaca no da barras de minuto de ninguno; MAPS tiene barras diarias, pero con volumen cero.
  - E3 ya no los pide, y el escaneo los registra con estado `provider_not_covered`, no como día sin negociación.
- **Inactivos o desaparecidos (10):** AVB, BK, CTRA, DAY, EA, EQR, HOLX, KVUE, PSKY y WBD. Solo cuentan para fechas
  pasadas; ninguno está en el universo actual.

## 6. Aceptado (2026-11-22) y pendiente

**Aceptado:** el usuario aceptó la conciliación el 2026-11-22. Se conservan el historial de cambios corporativos
(`events`, `successions`) y la separación entre emisor, ticker, pertenencia y cobertura del proveedor.

**Pendiente: identidad histórica estable para los emisores identificados solo por ticker.** Hoy son:
- los miembros del Nasdaq 100 (Wikipedia no da CIK; el ISIN solo aparece desde 2026-10-24);
- los valores de las listas del proyecto que no están en ningún índice;
- en VP2, las entidades `T:SÍMBOLO`.

Un cambio de ticker o la reutilización de un ticker (como SATS) no se detecta en ellos de forma fiable. Propuesta, sin
implementar: resolver el CIK por la SEC (`company_tickers.json` y el historial de nombres) o, si no lo hay, el
identificador del activo en Alpaca, y fechar sus tramos con el primer y último día de barras.

## 7. Límites

- **Nasdaq 100:** su historial propio en Wikipedia empieza el 2026-07-09 (antes estaba dentro del artículo del
  índice). La pertenencia anterior no está verificada en este registro.
- **Fechas aproximadas:** las 7 de §4.
- **La lista actual depende de Wikipedia:** su última revisión es del 2026-11-08. Un cambio anunciado después no
  estaría.
- **Actualización:** no es automática. Se repite con `py -3 u1_universe_registry.py fetch` y `build`, que guardan las
  revisiones y la fecha de consulta.
- **Tickers del proyecto sin CIK:** se resuelven por la tabla de cambios de ticker del índice. Un cambio de ticker de un
  valor que no esté en ningún índice no se detectaría; Alpaca daría 404 y quedaría como «no encontrado», visible en
  el informe de conciliación.
