# Enmienda 1 al preregistro Flow negativo v3 — precios, identidad, desenlaces y embargo

**Estado: APROBADA por el usuario el 2026-11-20 (con modificaciones), congelada antes de reconstruir.** Hash en
`research/flow_negative_v1/data/enmienda1_freeze.json`.

Alcance autorizado: reconstruir el panel corregido y rehacer la tanda 1 con sus reglas de selección originales.
**No** autorizado todavía: tanda 2, cualquier periodo confirmatorio, producción, commits.

## 0. Origen

Al revisar la tanda 1 (desarrollo 2018-2020) aparecieron rendimientos imposibles: +21 600 % y +7 680 % a 20 sesiones
(CHK, HPR). Eran contrasplits documentados en la SEC que la serie no recogía. La revisión del usuario (2026-11-20) pidió
corregirlos y auditar la identidad de los emisores. La auditoría (`s5_identity_audit.py`) encontró además series con
el ticker transferido a una escindida y grandes empresas sin capitalización por un CIK posterior o en conflicto.
**Esta enmienda es posterior a la inspección de la tanda 1 original**, que se conserva intacta y congelada.

## 1. Principios

- Los ficheros originales (series, panel v4, tanda 1, hashes) no se modifican. Todo lo corregido lleva sufijo `c1`.
- Cada transformación tiene una fila en un registro (`research/flow_negative_v1/data/corr1_*.csv`) con fuente, fecha,
  proporción, tratamiento y comprobación.
- Se distinguen cuatro identidades: entidad emisora, instrumento, historia de negociación e inversión económica del
  accionista. Ninguna se infiere de otra sin fuente.
- Ninguna corrección usa el rendimiento posterior a una señal para decidir.

## 2. Contrasplits (registro `corr1_splits.csv`)

- Solo los documentados en la SEC: CHK 1:200 (2020-04-15), HPR 1:50 (2020-10-30), PEI 1:15 (2022-06-16), CSR 1:10
  (2018-12-28), OVV 1:5 (2020-01-27), OPI 1:4 (2019-01-02), OPCH 1:4 (2020-02-03), VAL 1:4 (2019-04-11), LCI 1:4
  (2023-02-07), DD 1:3 (2019-06-03). Fecha = primera sesión cotizada ya ajustada.
- Precio × factor y volumen ÷ factor antes de esa fecha, en una copia (`work/series_c1/`). Se recalculan Flow,
  capitalización, talla y rendimientos.
- Controles, registrados por split: (1) la fecha no está entre los splits ya aplicados; (2) tras corregir, el cociente
  de cierre de ese día queda dentro de ×2/÷2; (3) acciones × precio coherente (la capitalización implícita no salta
  por el factor); (4) conciliación: la serie corregida dividida por la original es exactamente el factor antes de la
  fecha y 1 después.
- El split corregido deja de ser «split incoherente», pero **cualquier otra operación del mismo día se conserva como
  evento propio** (DD: la distribución de Corteva sigue siendo una escisión, §4).

## 3. Saltos de precio sin explicar (registro `corr1_jumps.csv`)

Saltos de cierre ×2 o ÷2 (y los splits rechazados como incoherentes) en series con días utilizables, clasificados en:
1. **Operación corporativa verificada** (split, escisión, fusión): se trata con §2, §4 o §6.
2. **Movimiento real de mercado**: se conserva.
3. **Error de datos confirmado**: se corrige con una fuente independiente (Yahoo, cierre del día); nunca con el último
   precio anterior.
4. **Causa indeterminada**: dato ausente (§7).

- Evidencia, siempre independiente del rendimiento posterior: segunda fuente de precios (Yahoo), movimiento del mismo
  día en el mercado y en el sector, volumen del día, 8-K presentados en ±3 días.
- Una reversión del salto en ≤ 3 sesiones es **señal de auditoría**, no prueba de error.
- Error confirmado = la segunda fuente no muestra el salto. Movimiento real = la segunda fuente lo confirma.

## 4. Escisiones (registro `corr1_spinoffs.csv`)

- Valor económico de la posición = acción matriz + acciones distribuidas × precio de la escindida + efectivo.
- Proporción de la escindida: Alpaca (2020+) o documento de la SEC (antes de 2020). Precio de la escindida: su serie
  (universo o Alpaca).
- Si no se puede reconstruir razonablemente (falta proporción o precio de la escindida), el resultado de los plazos
  que cruzan la fecha es **desconocido** (§7). Nunca se usa el retorno sin ajustar de la matriz como rendimiento total.

## 5. Identidad (registro `corr1_identity.csv`)

Series con el ticker transferido a otra entidad: ARNC, AAN, DLPH, FOXA/FOX, XPER, COHR, CR.
- Se cortan en la fecha documentada. El tramo posterior es la nueva entidad, sin historia previa.
- El tramo anterior se une a otra serie **solo si hay continuidad legal y económica documentada** (misma entidad
  renombrada: se une y la operación se registra como escisión §4). Si la operación fue una fusión mixta o en efectivo
  (21st Century Fox, Coherent Inc.: 220 $ + 0,91 acciones de II-VI), el tramo anterior termina ese día con su
  desenlace económico (§6), y no se empalma con el comprador.

## 6. Desenlaces terminales (registro `corr1_terminals.csv`)

- Se distinguen: última sesión en bolsa, periodo OTC y fecha efectiva (cancelación o pago).
- **Chesapeake (acciones antiguas):** exclusión de la NYSE tras el 26-jun-2020, OTC (CHKAQ) hasta el 9-feb-2021,
  cancelación sin distribución (plan, 8-K 19-ene-2021, clase 10). Valor 0 desde el 9-feb-2021. Para plazos que
  terminan antes, se busca el precio OTC de esa fecha; si no hay, el desenlace es **no observado** (§7).
- El mismo criterio se aplica a otras quiebras **solo** cuando la documentación fija los derechos del accionista.
- Fusiones: valor = efectivo + acciones recibidas × precio del comprador en la fecha efectiva (Alpaca o SEC). Si falta
  algo, la regla del preregistro (§4.2) sin cambios.

## 7. Datos ausentes (desconocidos, no observados, indeterminados)

- En el principal, la observación queda fuera (también de la media de su talla ese día), con cotas: el preregistro
  §4.2 cuando aplica; para saltos indeterminados, el retorno tal cual y el retorno con el salto anulado.
- Se publica su frecuencia por talla, población, nivel de Flow y tipo de señal, y una sensibilidad incluyéndolas.

## 8. CIK y capitalización (registro `corr1_cik.csv`)

- CIK correcto para cada serie (se corrigen los mal asignados y los ausentes) y, cuando el CIK actual es de un holding
  posterior, tabla de CIK predecesor con su vigencia y factor de canje.
- Solo se usa el CIK predecesor con continuidad legal y económica documentada (reorganización de holding, canje fijo);
  si no se puede justificar, la empresa sigue «sin capitalización» en esas fechas.
- Las tallas se recalculan con presentaciones publicadas ≤ t, igual que antes.
- Se informa cuántos días y empresas cambian de talla y cómo varían poblaciones y medias de referencia.

## 9. Embargo y particiones

- **Embargo mínimo de 40 sesiones** tras el último cierre usado en desarrollo:
  - grandes, medianas, sin capitalización: último cierre usado 2021-03-02 → prueba propia desde **2021-03-03**;
  - pequeñas y micro: último cierre usado 2023-03-01 → prueba propia desde **2023-03-02**.
- **Validación común**, posterior al desarrollo de todas las tallas: desde **2023-03-02** (referencia: marzo de 2023).
- Se declara que el desarrollo de pequeñas y micro (2021-2022) comparte régimen de mercado con la primera parte de la
  prueba de grandes y medianas.
- Antes de abrir cualquier periodo confirmatorio se presentará la partición definitiva y el número efectivo de
  observaciones.

## 10. Comparación secundaria de la candidata

La candidata (grandes, Flow < −30, 20 sesiones) sigue siendo la hipótesis procedente de la tanda 1 original. En la
evaluación, además del criterio principal (sin cambios), se comparará con reglas simples de reversión en grandes:
caída previa a 5 y a 21 sesiones, volatilidad elevada, momentum 12-1 bajo y combinaciones caída + volatilidad. Umbrales
congelados solo con desarrollo, igualando el número de episodios.

## 11. Reconstrucción y conciliación

1. Congelar esta enmienda (hash).
2. Registros `corr1_*` verificados.
3. Panel v4c1 con el mismo `s1_panel.py` + registros.
4. Tanda 1 completa con sus reglas originales (`etapa1_tanda1c1_*`), sin tocar los umbrales ni las puertas.
5. Conciliación con la original, incluido el efecto de cada familia de correcciones por separado. Si la candidata deja
   de pasar las puertas se declara; si aparecen otras, se identifican como resultados de desarrollo de la versión
   corregida, posteriores a la inspección original.
6. Alto.
