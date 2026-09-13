# Preregistro — PCS_FLOOR_FACTORIAL_V1 (P2)

**Fecha de firma:** 2026-09-13
**Autor:** usuario + Claude (implementación de §6 de la Hoja de ruta consolidada)
**Fuente:** `Hoja de ruta consolidada — Auditoría de carteras IA`, v1.2 (FINAL —
arquitectura congelada), firmada 2026-08-30, §6 + §1.1 + §2 + §6.1 + §13.
Documento externo, no commiteado en el repo (por diseño, ver CLAUDE.md § "Hoja
de ruta consolidada"). Este preregistro reproduce literalmente los apartados
relevantes para no depender de que el texto externo siga disponible.

> Cláusula de congelación de arquitectura (§14 de la hoja de ruta): con la
> firma de la v1.2 se cerró la fase de diseño del programa completo. Este
> preregistro no reabre esa discusión — solo instancia P2 tal como quedó
> fijado. Cualquier cambio posterior requiere adenda motivada por error
> material, nunca por opinión nueva ni por resultados parciales.

---

## 0. Punto de partida (verificado 2026-09-13, no asumido)

- **P0 ya está desplegado** (`scripts/ai_picks_decision_state.py`, arrancó
  2026-08-30, Step 10i del pipeline) y ya captura los campos que P2
  necesita: `PCS`, `rot_score`, `streak_weeks`, `trigger_threshold`,
  `trigger_threshold_source`, `event_id`, `mechanical_exit_trigger`,
  `exit_rule_id` — **`T_active` (§6) ya se calculó dentro de P0 desde el
  primer día**, no hubo que añadirlo aquí.
- **Gate de calendario cumplido:** hoy son 14 días desde la firma
  (2026-08-30 → 2026-09-13), el umbral de "≥2 semanas de captura P0" de §6.
  Confirmado por `scripts/p1_readiness_monitor.py` (`fired.p2_ready =
  "2026-09-13"`).
- **Backfill retroactivo ejecutado sobre las 15 sesiones ya capturadas por
  P0** (2026-08-30 → 2026-09-13, 197 filas, 24 posiciones) — no se esperó a
  que P2 empezara a acumular desde cero, porque el historial de P0 ya
  existía y no reevaluarlo habría tirado 2 semanas de muestra.
- **Nota de honestidad sobre la muestra:** con 24 posiciones abiertas y ~2
  semanas de historial, la cláusula de potencia calendario de §3/§6 (90 días
  → informe intermedio si no hay suficiente n) se espera que aplique. No se
  fuerza ninguna lectura con esta muestra.

---

## 1. Definición formal del suelo — T_active (§6, literal)

```
T_active = max( 62,                                  ← suelo absoluto, siempre
                pcs_min_entry  si streak_weeks ≤ 1 ) ← suelo de cartera, condicionado
```

Toda referencia a "suelo" en los brazos B/C/D y en el breach severity
significa **T_active de esa posición ese día**. Ya calculado por P0
(`trigger_threshold`) para las carteras PCS-gated (`compute_t_active()` en
`ai_picks_decision_state.py`).

### 1.1 Extensión de T_active a CAVA_MACRO (decisión de implementación, no del texto original)

El esquema de P0 marca `trigger_threshold=None` para `CAVA_MACRO`
(`trigger_threshold_source="not_pcs_gated"`) porque Cava no tiene tiering
por `pcs_min_entry`/`streak_weeks` — su única condición de salida por PCS es
el suelo absoluto fijo (`pcs<62`, ver `compute_mechanical_exit()` rama
`CAVA_MACRO`). La hoja de ruta no dice explícitamente si P2 cubre Cava.
Decisión tomada aquí, análoga a como T_active se define para el resto: para
`CAVA_MACRO`, `T_active = ABSOLUTE_FLOOR = 62` siempre (caso particular de
la fórmula general con `pcs_min_entry` inexistente). Implementado en
`pcs_floor_factorial_v1_shadow.py → t_active_for_row()`, sin tocar
`ai_picks_decision_state.py` (P0 sigue devolviendo `None` para Cava; P2 lo
reinterpreta solo dentro de su propio script).

---

## 2. Ámbito (decisión de implementación, no del texto original)

La hoja de ruta no fija explícitamente el ámbito de P2. Se adopta **el mismo
ámbito que P1A/P1C (§3)**: `HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS,
EARLY_ROTATION, MACRO_THEMATIC_BENEFICIARIES, CAVA_MACRO`. `MIMO_SHADOW`
queda excluida (no sufre consecuencias reales de sus posiciones, mismo
motivo por el que P1A no la incluye); `MIRROR_ESPEJO`/`CRUCE_ROJO_D*` quedan
excluidas porque no usan un suelo de PCS en absoluto (Espejo sale por
trailing 5%, Cruce Rojo D por cruce Koncorde).

Importado directamente de `p1_readiness_monitor.P1A_P1C_SCOPE` en
`pcs_floor_factorial_v1_shadow.py` — mismo ámbito, una sola fuente, sin
riesgo de que ambos scripts diverjan silenciosamente.

---

## 3. Los cuatro brazos shadow (§6, literal)

| Brazo | Regla |
|---|---|
| A (control) | Actual — regla 13 real (`mechanical_exit_trigger` de P0, sin cambios) |
| B (histéresis) | Cerrar si `PCS < T_active − 1.5` — una sola lectura basta |
| C (confirmación) | Cerrar si `PCS < T_active` en 2 lecturas consecutivas |
| D (ambos) | Cerrar si `PCS < T_active − 1.5` en 2 lecturas consecutivas |

**Ninguno de los 4 brazos toca `ai_picks.json` ni cierra nada real.**

### 3.1 "2 lecturas consecutivas" (decisión de implementación, no del texto original)

P0 dedupea a **una fila por posición por día natural** (el pipeline corre
2×/día, pero P0 solo guarda la primera captura de cada día — ver docstring
de `ai_picks_decision_state.py`). La hoja de ruta no precisa si "lectura"
significa "corrida del pipeline" o "día". Dado que P0 ya opera a granularidad
diaria, "2 lecturas consecutivas" se interpreta aquí como **2 días naturales
consecutivos con fila capturada** (no necesariamente calendario sin huecos —
si falta una captura un día, se compara contra la lectura anterior
disponible, mismo principio que `findHistEntryAtOrBefore` ya usado en
`rotacion.html`/`relative.html`). Implementado en
`evaluate_position_history()` guardando el estado de la lectura previa.

---

## 4. Breach severity — dos niveles fijos (§6, literal)

```
MARGINAL: T_active − 3.0 ≤ PCS < T_active                → aplica histéresis/confirmación del brazo
SEVERE:   PCS < T_active − 3.0  O  rot_score ≤ 2         → EXIT inmediato en todos los brazos
```

El nivel SEVERE salta cualquier histéresis/confirmación en B/C/D. No se
aplica como override explícito sobre A porque la regla 13 real (control) ya
incluye `rot_score≤2` y el suelo absoluto en su propia lógica — el control
no necesita el override para llegar al mismo resultado en los casos donde
ambos deberían coincidir.

---

## 5. Precedencia entre sombras (§6.1) — fuera de alcance de este preregistro individual

La hoja de ruta fija la precedencia `SEVERE > P1C > P1A > P2` para el libro
sombra **combinado** y para producción, pero aclara explícitamente: *"los
shadows individuales de P1A, P1C y P2 se computan en paralelo y sin
interferencia mutua... si la precedencia se aplicara dentro de cada shadow
individual, [el experimento] quedaría censurado."* Este preregistro cubre
únicamente el shadow individual de P2 (`pcs_floor_factorial_v1_shadow.py`),
que evalúa sus 4 brazos contra la realidad como si fuera el único
mecanismo — sin interferencia de P1A/P1C, que no están implementados
todavía. La combinación con precedencia queda pendiente de que P1A/P1C
existan.

---

## 6. Métricas (§6, literal + operacionalización)

- **Whipsaws** → clasificación ya existente en `pcs_floor_whipsaw_shadow.py`
  (holding_days≤2 AND |price_change_pct|<3.0) — objetivo declarado: ~0 en
  los brazos B/C/D frente al control.
- **Coste en los deterioros reales** (pérdida media adicional por el
  retraso de histéresis/confirmación vs el control) → tolerancia ≤0.5pp.
- **`excess_CAGR_calendar` a nivel cartera** (libro shadow) — decisiva para
  promoción, mismo principio ya establecido en el proyecto para estrategias
  de exposición intermitente (ver CLAUDE.md, sección "Principio: métrica
  primaria para estrategias con exposición intermitente").

**Diferido explícitamente en esta v1:** el cálculo de whipsaw/pérdida-evitada
a nivel de cada brazo B/C/D requiere precio del ticker **después** de la
fecha en que ese brazo habría cerrado (que puede ser antes del cierre real)
— eso es un análisis aparte sobre el log ya acumulado (`--report` actual
solo cuenta disparos, no reconstruye el contrafactual de precio). Se
construirá cuando haya suficientes divergencias brazo-vs-control que valga
la pena analizar; no bloquea el arranque del shadow logging.

---

## 7. Criterios de promoción (§6/§3, doble n literal de §1.1)

Sobre **≥40 episodios cerrados nuevos post-firma Y ≥30 eventos independientes
(`event_id = ticker+entry_date`, §1.1)** en el ámbito de §2, por brazo:

- Reduce whipsaws (según clasificación de `pcs_floor_whipsaw_shadow.py`) sin
  aumentar el coste en deterioros reales por encima de la tolerancia (0.5pp).
- `excess_CAGR_calendar` del libro shadow del brazo ≥ libro control.

**Cláusula de resultado no concluyente (§6, literal):** con ~25-40
cierres/trimestre repartidos en 4 brazos, es probable que ningún brazo
alcance significación en el primer ciclo. Resultado no concluyente → seguir
acumulando sin tocar parámetros. **No se promociona ni descarta nada con
celdas de n<20.**

**Cláusula de potencia calendario (§3, aplicada a P2 por remisión explícita
del propio §6: "Aplica la misma cláusula de potencia calendario de P1A"):**
si a 90 días de la firma (2026-11-28) no se han acumulado suficientes
episodios, se publica un informe intermedio y se alarga el plazo — **nunca**
se tocan parámetros ni se mira el resultado por brazo durante la extensión.

---

## 8. Reapertura — fuera de alcance de P2 (§6 V1.1, literal)

*"La condición de reapertura (`PCS > T_active + 1.5`) es una hipótesis de
**entrada** (reentry), no de salida, y queda fuera del criterio de promoción
de los brazos B/D. Se registra como regla operativa anti-whipsaw del paper
trading, evaluada aparte con su propio registro. P2 promociona
exclusivamente por calidad de cierre."* No implementada en este cambio — no
hay ninguna regla de reapertura en `paper_trading.py` hoy que evaluar.

---

## 9. Parámetros congelados (§13, tabla literal aplicable a P2)

| Parámetro | Valor | Estado de validación |
|---|---|---|
| Histéresis (buffer) | −1.5 sobre T_active | Propuesto por el auditor, sin objeción |
| Breach severity (SEVERE) | T_active − 3.0 | Fijado por el auditor, formalizado sobre T_active en ronda 4 |
| Confirmación | 2 lecturas consecutivas | Fijado por el auditor, sin objeción |
| Suelo absoluto | 62.0 | Ya productivo (regla 13 real) |

Ninguno se ajusta con datos de este experimento — están congelados en la
hoja de ruta v1.2, ronda 4.

---

## 10. Implementación

- `scripts/pcs_floor_factorial_v1_shadow.py` — evalúa los 4 brazos cada día
  sobre las filas de P0 en ámbito, append-only, dedup por
  `(position_id, date)` mismo patrón que P0. `--report` resume disparos por
  brazo y distribución de severidad.
- Salida: `docs/data/pcs_floor_factorial_v1_shadow.jsonl`.
- Pipeline: Step 10i2, justo después de Step 10i (P0) — necesita las filas
  del día ya escritas por P0. `continue-on-error: true`.
- **No se modifica** `ai_picks_decision_state.py`, `paper_trading.py`,
  `cava_portfolio.py` ni ninguna cartera real.

---

## 11. Explícitamente fuera de alcance de esta v1

- Combinación con precedencia P1A/P1C/P2 (§6.1) — P1A/P1C no están
  implementados todavía.
- Análisis de whipsaw/pérdida-evitada por brazo (contrafactual de precio
  post-disparo) — diferido hasta tener suficiente divergencia acumulada.
- Cualquier cambio de parámetro — todos están congelados por la cláusula de
  congelación de arquitectura (§14 de la hoja de ruta).
- Extender el ámbito más allá de HC/CFL/ER/MTB/Cava.
