# Enmienda 2 al preregistro Flow negativo v3 — base corregida, regla §7 y acciones de varias clases

**Estado: decisiones APROBADAS por el usuario el 2026-11-20.** Este documento las fija antes de reconstruir; su hash
se guarda en `research/flow_negative_v1/data/enmienda2_freeze.json`.

Alcance autorizado: panel corregido definitivo, tanda 1 con sus reglas originales y tanda 2 **solo sobre desarrollo**.
**No** autorizado: abrir la prueba o la validación, producción, commits de Flow negativo, pushes.

## 0. Declaración de orden

**Esta enmienda, igual que la 1, es posterior a la inspección de los resultados de desarrollo de la tanda 1** (la
original y la corregida c1, `CONCILIACION_TANDA1_ENMIENDA1.md`). Las decisiones no se toman para mejorar ningún
resultado: corrigen datos y vuelven a la regla original del preregistro. La tanda 1 original
(`data/etapa1_tanda1_frozen.json`) y sus hashes se conservan intactos.

## 1. Versión corregida como base

- La base es la versión c1 de la enmienda 1 (contrasplits, identidad, CIK, escisiones, saltos, fusiones con Alpaca),
  con los cambios de §2 y §3 de esta enmienda. Se llama **c2**.
- La tanda 1 se rehace sobre c2 con las reglas originales, sin tocar umbrales, puertas, plazos ni plazas, y se congela
  como `data/etapa1_tanda1c2_frozen.json` (no sustituye a la original).
- La tanda 2 toma sus plazas de esa congelación (4 − elegidas en la tanda 1 c2).

## 2. Regla §7 para desenlaces terminales (vuelta al preregistro §4.2)

- **Desenlace terminal de valor desconocido** (quiebra, exclusión/OTC, fin desconocido, adquisición sin valor
  conocido…): en el principal, **último cierre disponible**, como fija el preregistro §4.2. Cotas: 0 y último cierre
  (adquisiciones: × e^−0,05 y × e^+0,05). La conclusión debe mantenerse con las dos cotas.
- **Igual en señales y en las referencias:** esas observaciones cuentan también en la media de su talla de ese día
  (y en la del sector y la de SPY), con el mismo valor central y las mismas cotas.
- **Saltos de precio de causa indeterminada** (registro `corr1_jumps.csv`, clase `indeterminate`) y escisiones no
  reconstruibles: tratamiento independiente, como la enmienda 1 §7. Fuera del principal (también de la media de su
  talla), con dos sensibilidades: retorno tal cual y retorno con el salto anulado (salto del día e = c_e / c_{e−1};
  si cae en la sesión de entrada, la entrada pasa al cierre de t).
- La frecuencia de desconocidos (terminales, saltos, escisiones) sigue contando para la puerta «menos del 1 %».
- Implementación: familia `missing_j` en `s4_etapa1.py` (la antigua `missing` sigue reproduciendo la c1).

## 3. Empresas con varias clases de acciones

**Problema.** La API `companyconcept` de la SEC solo publica hechos sin dimensión. Las empresas que declaran sus
acciones en circulación por clase (eje `us-gaap:StatementClassOfStockAxis`) aparecen sin acciones y sin
capitalización (GOOGL, META, PLTR, V, MA…).

**Piloto** (`s7_xbrl_classes.py`): leer el XBRL original de cada 10-K/10-Q desde 2016-06 y extraer
`dei:EntityCommonStockSharesOutstanding` por clase, con su fecha, y `dei:TradingSymbol` por clase. Emisores:
GOOGL, META, V, MA, BRK, CMCSA, NKE, EL, LEN, MSTR, F, UPS, PLTR, EXPE, STZ.

**Regla de valoración, sin imputar nada.**
- La clase de la serie se identifica por su símbolo en la portada (`dei:TradingSymbol`, obligatorio desde 2019).
  Para presentaciones anteriores se usa el mismo miembro XBRL de la clase (p. ej. `CommonClassAMember`) cuya relación
  con el símbolo consta en presentaciones posteriores: es la identidad de la clase, no un valor.
- **Cota inferior** = acciones de la propia clase × precio de la serie (las demás clases valen ≥ 0). Las acciones de
  la clase pasan los mismos filtros sin mirar al futuro que las demás (≤ t, ≤ 400 días, coherencia con las anteriores,
  rotación plausible con la liquidez de esa clase).
- **Solo se asigna talla si la cota inferior la decide sin ambigüedad**: cota ≥ 10 000 M$ ⇒ grande. Por debajo, la
  capitalización real puede estar en una talla superior según el valor de las clases sin cotización (con canjes que
  no son siempre 1:1: Visa, Berkshire), así que el día sigue «sin capitalización».
- No se rellena ningún día que ya tenga capitalización con las fuentes anteriores.
- Viabilidad: el piloto es viable si en la mayoría de los emisores se extraen las acciones por clase de casi todas las
  presentaciones y la clase de la serie se identifica. Si lo es, la regla se aplica a todos los emisores «sin
  capitalización» con CIK (familia `multiclass` de `s1_panel.py`). Si no, se declara la limitación y se sigue.

## 4. Orden de ejecución

1. Congelar esta enmienda (hash).
2. Piloto (§3) y, si es viable, extracción general.
3. Panel c2 = c1 + `multiclass`; tanda 1 c2 con `missing_j`; congelación de la tanda 1 c2 (nuevo hash).
4. Comparación de las 72 candidatas con la original y la c1; comprobar si grandes / Flow < −30 / 20 sigue pasando.
5. Si no hay cambios materiales inesperados: tanda 2 (pequeñas y micro, 2021-2022) con las plazas restantes y los
   criterios fijados. Congelación de la tanda 2.
6. Alto. Informe y selección definitiva al usuario. La prueba sigue cerrada.
