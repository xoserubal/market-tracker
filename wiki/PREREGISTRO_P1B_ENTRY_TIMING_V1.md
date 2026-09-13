# Preregistro — P1B: `ENTRY_TIMING_V1`

**Fecha de firma:** 2026-09-13
**Autor:** usuario + Claude (implementación de §4 de la Hoja de ruta consolidada)
**Fuente:** `Hoja de ruta consolidada — Auditoría de carteras IA`, v1.2, §4
+ §1.1 + §2 + §13. No commiteada en el repo (por diseño).

---

## 0. Motivación por qué se construye ahora

Mismo motivo que P1A/P1C: el contador de eventos SELECT de
`p1_readiness_monitor.py` avanza hacia el umbral de §4 (≥60 eventos)
independientemente de si hay algo capturando el predictor
(`w1_ret_5d_at_entry`). Sin captura desde ya, cuando llegue el aviso "P1B
lista" no habría datos que analizar — se empieza a capturar ahora.

---

## 1. Pregunta e hipótesis primaria (§4, literal)

Entre valores ya seleccionados por el sistema, ¿qué discrimina
follow-through de failed entry?

**Diseño — hipótesis primaria anclada, no agnóstico (enmienda del
documento original, literal):** un experimento agnóstico con n~100 y
docenas de features es una máquina de falsos positivos. Se preregistra UNA
hipótesis primaria; todo lo demás es exploratorio y sus hallazgos
requerirán preregistro independiente (patrón ya usado en Relative Flow Lab).

**Hipótesis primaria (H7, literal):** *la sobreextensión de corto plazo en
la fecha de entrada — operacionalizada como `w1_ret_5d` del ticker en la
fecha del SELECT (variable primaria) y puntos continuos de `extension_risk`
(variable secundaria de confirmación, ya en payload) — predice
negativamente el follow-through.*

---

## 2. Endpoint primario único (§4, literal — V1.2, elimina las "demasiadas
formas de ganar" de una versión anterior)

- **Predictor primario:** `w1_ret_5d` en la fecha del SELECT — retorno
  propio del ticker (NO vs SPY) en las 5 sesiones terminando en la fecha de
  entrada.
- **Outcome primario:** `ret_21d` del ticker post-SELECT.
- **Test primario:** Spearman(`w1_ret_5d`, `ret_21d`), clusterizado por
  `event_id` (§1.1) — en la práctica, dado que la unidad ya es un evento
  por fila (deduplicado), no hace falta un paso de clusterización adicional.
- **Secundarios/confirmatorios (se reportan, no deciden):** `ret_10d`, MFE,
  MAE post-SELECT; puntos continuos de `extension_risk`; cuartiles con
  monotonicidad.

**Restricción obligatoria (H9, literal):** *"medido sobre el precio del
ticker post-SELECT — nunca sobre la vida de la posición, porque la regla
de salida actual censura las tenencias (mediana ~10 días) y contaminaría
la medición."* Este preregistro cumple esta restricción reutilizando
`ret_2w`/`ret_1m` de `shadow_picks.jsonl` (calculados por
`update_performance.py` sobre precio de ticker vía yfinance, con
`entry_price` + N sesiones después — verificado leyendo su código: no
depende en ningún punto de si la posición sigue abierta).

---

## 3. Ámbito y fuente de datos — decisión de implementación, no del texto original

El texto original (§4) dice "cualquier cartera, sin restricción de
ámbito" — pero eso describe el **contador** de `p1_readiness_monitor.py`
(`count_p1b()`), que cuenta SELECTs sobre `ai_picks.json` para
`ALL_LIVE_PORTFOLIOS` (incluye `MIRROR_ESPEJO`/`CRUCE_ROJO_D*`). Esas tres
carteras **no escriben en `shadow_picks.jsonl`** (verificado por grep) y
por tanto no tienen `ret_1m`/`ret_2w` calculados por `update_performance.py`
— no hay outcome que medir ahí sin construir un fetch nuevo.

**Decisión:** el universo analizable de este script es el subconjunto de
eventos que sí aparecen en `shadow_picks.jsonl` — `HIGH_CONVICTION,
CONFIRMED_FLOW_LEADERS, EARLY_ROTATION, MACRO_THEMATIC_BENEFICIARIES,
CAVA_MACRO, MIMO_SHADOW, RANKING_SHADOW_EXPERIMENTAL`. Son exactamente las
carteras que seleccionan vehículo vía PCS/candidatos — el mecanismo de
"SELECT" al que H7 se refiere. `MIRROR_ESPEJO`/`CRUCE_ROJO_D*` quedan
fuera por el mismo motivo que P1A/P1C las excluyen (mecanismo de entrada
categóricamente distinto, sin PCS).

**Consecuencia declarada, no oculta:** el n que cuenta hacia el umbral de
60 en `p1_readiness_monitor.py` puede ir por delante del n realmente
analizable aquí (el contador incluye Mirror/Cruce Rojo D, este script no).
El `--report` de este script muestra su propio n, no el del monitor —
nunca se declara "listo" con la cifra del monitor si el n propio es menor.

---

## 4. Unidad estadística y deduplicación (§4/§1.1, literal)

`event_id = ticker + fecha SELECT`, **deduplicado entre carteras y
modelos** — si el mismo ticker se selecciona el mismo día para varias
carteras (p. ej. PLTR en CFL y CAVA_MACRO el mismo día), es un solo evento
de mercado, no dos. Implementado en `dedup_events()`: prefiere la fila
`shadow=False` (activa) si existe para ese `event_id`.

---

## 5. Criterio de éxito (§4, literal)

Sobre ≥60 SELECTs-evento independientes post-firma (en el universo
analizable de §3, no el del contador): Spearman primario negativo con
`|ρ|≥0.15` y **estabilidad de signo mensual, donde un mes solo computa si
tiene ≥10 eventos independientes** (signo consistente en ≥3 de los meses
computables, mínimo 3 meses computables). Si se cumple, la implementación
candidata es un **delay de entrada** (no un veto, no una inversión) — regla
concreta a preregistrar en `ENTRY_TIMING_V2` con estos datos como
justificación.

**Freno a V2 (literal):** un Spearman de -0.16 en un solo régimen cumple
el listón de V1 (deliberadamente bajo, diagnóstico) pero **no se convierte
en delay automático** — V2 requiere su propio preregistro con sus propios
umbrales. El listón bajo de V1 compra derecho a diseñar V2, no a
implementarla.

---

## 6. Implementación

- `scripts/p1_entry_snapshot.py` — helper compartido (`w1_ret_5d_at_entry`,
  calculado con fetch dedicado a la fecha de entrada, no aproximado desde
  P0).
- `scripts/p1b_entry_timing_v1_shadow.py` — construye el dataset de
  eventos desde `shadow_picks.jsonl`, reutiliza `ret_2w`/`ret_1m` ya
  calculados. **Reconstruye el fichero de salida entero cada vez** (no
  append-only) — mismo motivo que `cfl_reentry_cooldown_shadow.py`:
  `ret_21d` llega asincrónicamente días después vía
  `update_performance.py`, y un log append-only congelaría el valor con
  información parcial del día en que se capturó por primera vez.
  `--report` corre el test primario (Spearman, vía `spearman()` reutilizado
  de `ranking_score_readiness_monitor.py`, sin duplicar la implementación)
  solo cuando hay ≥60 eventos con predictor y outcome maduros — si no,
  imprime cuántos faltan y no calcula nada.
- Salida: `docs/data/p1b_entry_timing_v1_shadow.jsonl`.
- Pipeline: Step 10i5, justo después de Step 10i4 (P1C). `continue-on-error: true`.

---

## 7. Exploratorio secundario (§4, literal, etiquetado, sin autoridad)

`konc_w_state` condicional a MacroScore (H6); distancia a máximos 52w;
racha de sesiones verdes. Cualquier hallazgo aquí → preregistro propio
antes de uso. No implementado en este cambio.

---

## 8. Verificado (2026-09-13)

Primera captura real: 21 eventos SELECT únicos post-firma en el universo
analizable (`shadow_picks.jsonl`, 2026-08-30→2026-09-13). Predictor
(`w1_ret_5d_at_entry`) disponible en 21/21 (100% — el fetch dedicado
funciona de forma fiable). Outcome (`ret_21d`) maduro en 0/21 — esperado,
hacen falta ~21 sesiones de mercado desde la entrada más temprana
(2026-08-30), que todavía no han transcurrido. `--report` confirma
correctamente "faltan 60 eventos... sin test primario todavía" en vez de
forzar un cálculo con muestra insuficiente.
