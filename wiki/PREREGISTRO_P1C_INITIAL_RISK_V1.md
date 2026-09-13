# Preregistro — P1C: `INITIAL_RISK_V1`

**Fecha de firma:** 2026-09-13
**Autor:** usuario + Claude (implementación de §5 de la Hoja de ruta consolidada)
**Fuente:** `Hoja de ruta consolidada — Auditoría de carteras IA`, v1.2, §5
+ §1.1 + §2 + §13. No commiteada en el repo (por diseño).

> Cláusula de congelación de arquitectura (§14): este preregistro instancia
> P1C tal como quedó fijado en la v1.2, sin reabrir el diseño.

---

## 0. Motivación por qué se construye ahora

Mismo motivo que P1A (ver `PREREGISTRO_P1A_PROFIT_PROTECTION_V1.md` §0):
el contador de `p1_readiness_monitor.py` avisará cuando haya suficiente
muestra de cierres reales, independientemente de si P1C existe como
código. Se construye ahora, con backfill retroactivo sobre las 2 semanas
de P0 ya capturadas, para no perder esa muestra.

---

## 1. Pregunta (§5, literal)

¿Cuándo puede reconocerse que una entrada no está funcionando **antes** de
que el suelo de PCS la cierre? El subconjunto MFE bajo → pérdida grande que
P1A no puede tocar por construcción (H4: *"el overlay armado no toca por
construcción ninguna operación que nunca alcanzó el umbral de armado"*).

---

## 2. Ámbito

Mismo que P1A (§3/§5): `HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS,
EARLY_ROTATION, MACRO_THEMATIC_BENEFICIARIES, CAVA_MACRO`. Importado de
`p1_readiness_monitor.P1A_P1C_SCOPE`.

---

## 3. Los cuatro brazos (§5, literal, con la corrección V1.1 al brazo C)

| Brazo | Regla |
|---|---|
| A (control) | Suelo de PCS actual, tal cual — `mechanical_exit_trigger` de P0 |
| B (ATR stop) | Cierre < entrada − 2.0·ATR(14)_entry — ATR congelado el día de entrada |
| C (time stop) | A las 7 sesiones, si MFE en precio < 0.5·ATR(14)_entry (congelado) Y retorno < 0 → fallo |
| D (structure) | Cierre < mínimo de Low en las 5 sesiones ANTERIORES a la entrada |

**Nota V1.1 sobre el brazo C (literal):** sustituye al `MFE < +1.5%` de la
V1 original, calibrado a un universo que no es este — con ATR de varios
puntos como norma en este universo (crypto miners, small caps), +1.5% en 7
sesiones es respiración, no fallo. La versión ATR-normalizada mide lo mismo
("no ha habido impulso a favor") en las unidades propias del ticker. No se
mantiene el 1.5% ni como brazo informativo.

Ninguno de los 4 brazos toca `ai_picks.json` ni cierra nada real.

---

## 4. Decisiones de implementación no fijadas en el texto original

### 4.1 ATR de entrada y "5 sesiones previas a la entrada"

Mismo fetch dedicado compartido con P1A (`scripts/p1_entry_snapshot.py`):
`atr_entry` (ATR14 congelado al cierre de `entry_date`) y
`pre_entry_low_5d` (mínimo de `Low` en las 5 sesiones **anteriores** a
`entry_date`, excluyendo el propio día de entrada). Ambos calculados vía un
fetch específico a yfinance por posición, cacheado — no derivados del
primer día capturado por P0, que para posiciones abiertas antes del
2026-08-30 no coincide con la entrada real (mismo razonamiento que P1A §4).

### 4.2 "7 sesiones" del brazo C — aproximación honesta, documentada

"Sesión" para el brazo C se implementa como el **índice de fila** dentro
del historial que P0 lleva capturando para esa posición (1-indexed), no un
conteo real de sesiones NYSE. Para posiciones **abiertas en o después de la
firma de P0** (2026-08-30 — que es justamente lo que cuenta para el
criterio de promoción de §1.1), el índice coincide con las sesiones reales,
porque P0 captura desde el mismo día de entrada. Para posiciones
preexistentes (p. ej. TMO, abierta 2026-07-25), el índice subestima las
sesiones reales — su "sesión 7" según este script en realidad cae más
tarde en la vida real de la posición. Aceptado como limitación conocida
porque no afecta a los eventos que importan para la promoción (los
posteriores a la firma).

**Evaluación puntual, no persistente:** el brazo C se evalúa UNA sola vez,
en la primera fila cuyo índice sea ≥7 — dispare o no, no se re-evalúa en
días posteriores (es un chequeo de fuse, no una condición continua).

---

## 5. Métricas (§5, literal)

Para cada brazo, sobre las operaciones donde dispara antes que el suelo de
PCS: pérdida evitada (retorno en el disparo vs. retorno realizado real),
falsos positivos (operaciones que tras el disparo recuperaron a >+5% en 21
sesiones sobre precio), y el mismo doble nivel trade/portfolio de P1A con
`excess_CAGR_calendar` como decisiva (libro shadow, diferido — ver §8).

---

## 6. Criterio de éxito (§5, literal — doble n de §1.1)

≥40 episodios nuevos post-firma **y** ≥30 eventos independientes; un brazo
promociona si reduce la pérdida media de cola (p10) en ≥3pp con ≤20% de
falsos positivos y sin degradar `excess_CAGR_calendar` respecto al control.

**Interacción declarada con P2 (literal):** la histéresis del suelo de PCS
(P2) puede retrasar salidas justificadas; P1C es el contrapeso que
reconoce el deterioro por precio. Ambos experimentos comparten captura P0
y se evaluarán también en combinación (solo la combinación
ganador-de-P1C + ganador-de-P2, no el producto cartesiano) — pendiente de
que ambos tengan muestra suficiente por separado primero.

Cláusulas de resultado no concluyente y de potencia calendario a 90 días:
idénticas a P1A (ver `PREREGISTRO_P1A_PROFIT_PROTECTION_V1.md` §6).

---

## 7. Implementación

- `scripts/p1c_initial_risk_v1_shadow.py` — evalúa los 4 brazos cada día,
  append-only, dedup por `(position_id, date)`. `--report` resume disparos.
- `scripts/p1_entry_snapshot.py` — helper compartido (ATR_entry,
  pre_entry_low_5d).
- Salida: `docs/data/p1c_initial_risk_v1_shadow.jsonl`.
- Pipeline: Step 10i4, justo después de Step 10i3 (P1A). `continue-on-error: true`.

---

## 8. Explícitamente diferido en esta v1

- Libros shadow prospectivos a nivel cartera (mismo motivo que P1A §8).
- Análisis de pérdida evitada/falsos positivos por brazo (necesita precio
  real después de cada disparo, incluido cuando el disparo es anterior al
  cierre real) — mismo criterio de "esperar a tener divergencia real
  acumulada" que P2.
- Combinación P1C+P2 con precedencia (§6.1 de la hoja de ruta).

---

## 9. Verificado (2026-09-13)

Backfill retroactivo sobre las 15 sesiones de P0: 197 filas, 24 posiciones.
Los 4 brazos disparan en casos **distintos**, coherentes con sus reglas
(verificado manualmente, no solo por conteo):

- `SEDANA.ST` (CFL): brazo A (control, suelo absoluto de PCS).
- `OSCR` (CAVA_MACRO): brazo D desde la sesión 1 — entró ya por debajo de
  su propio mínimo de 5 sesiones previas (`entry_price=30.93` vs
  `pre_entry_low_5d=30.50`).
- `FCX` (CFL): brazo B en sesión 4 — cierre 72.47 vs. umbral
  `entrada(78.42) − 2·ATR_entry(2.77) = 72.88`. FCX es uno de los casos de
  giveback ya documentados en el doc base de la auditoría (H2).
- `VLE.TO` (CFL): brazo C, disparado exactamente en la sesión 7 según diseño.
