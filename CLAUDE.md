# AI Picks Lab — Documentación del proyecto

> **Convención:** Actualizar este archivo cada vez que se implemente una funcionalidad nueva, se cambie una decisión de diseño, o se añada una regla al sistema. Es la fuente de verdad para futuras sesiones con Claude.

---

## Arquitectura del pipeline

```
backtest/src/main.py          → fetch datos (Yahoo, FRED)
backtest/src/main_macro.py    → MacroScore semanal
backtest/src/main_rotation.py → rot_score por ticker
backtest/src/main_backtest.py → backtest histórico
backtest/src/main_confluence.py → confluence score
backtest/src/main_portfolio.py  → equity curves
backtest/src/main_stocks.py     → stock scanner

scripts/export_to_json.py     → parquets → docs/data/*.json
scripts/pcs_calculator.py     → Pick Conviction Score (91 tickers)
scripts/event_detector.py     → detecta eventos de señal
scripts/update_performance.py → rellena ret_* en shadow_picks.jsonl (yfinance)
scripts/paper_trading.py      → llama a los modelos IA → picks
scripts/force_analyze.py      → análisis forzado de cualquier ticker por los modelos (manual)
scripts/notify_telegram.py         → notificaciones de picks + recordatorios
scripts/telegram_portfolio_bot.py  → comandos Telegram para Portfolio Tracker
scripts/build_eval_bundle.py       → bundle para evaluador externo
scripts/chat_picks.py              → chat interactivo con el modelo
```

**GitHub Actions** (`market-update.yml`): ejecuta todo el pipeline dos veces al día (08:00 y 20:00 UTC).

---

## Filosofía de diseño

El sistema NO pide a la IA que "prediga el mercado". La IA actúa como **filtro final** sobre señales cuantitativas ya calculadas:

```
MacroScore  →  campo de juego (permiso de riesgo)
rot_score + relative strength  →  hacia dónde se mueve el capital
PCS (Pick Conviction Score)    →  qué vehículo concreto lo captura
IA (Grok/Haiku/Sonnet)         →  comité que decide si la señal es suficientemente limpia
```

Esto reduce drásticamente el riesgo de alucinación y decisiones caprichosas.

---

## PCS — Pick Conviction Score

Calculado en `scripts/pcs_calculator.py`. Componentes (máx 100 pts):

| Componente | Máx | Descripción |
|------------|-----|-------------|
| A — macro_permission | 15 | MacroScore y régimen |
| B — theme_flow | 22 | Flujo del tema sectorial |
| C — individual_rs | 23 | Relative strength individual |
| D — individual_flow | 18.5 | Flujo técnico (MACD, RSI, OBV) |
| E — early_acceleration | 7 | DEMS y señales diarias |
| F — data_quality | 3.5 | Calidad y completitud de datos |

**Riesgo conocido:** algunos componentes (ret_4w, rot_score, streak_weeks) están correlacionados. Pendiente análisis de doble conteo (ver roadmap semana 7).

---

## Portfolios — mandatos y umbrales

| Portfolio | PCS threshold | PCS min entry | Max pos | Size |
|-----------|--------------|---------------|---------|------|
| HIGH_CONVICTION | 85 | 82 | 8 | 8–15% |
| CONFIRMED_FLOW_LEADERS | 78 | 75 | 12 | 5–10% |
| EARLY_ROTATION | 70 | 68 | 15 | 4–8% |
| MACRO_THEMATIC_BENEFICIARIES | 65 | 62 | 20 | 3–6% |
| REJECTED_HIGH_SCORE *(control)* | 75 | 75 | 20 | 5% |

---

## HARD_RULES del modelo IA

Definidas en `paper_trading.py → HARD_RULES`. El modelo las recibe en el payload bajo `system_context.hard_rules`. Las violaciones se detectan automáticamente en `validate_model_response()` y reducen el `quality_score`.

Reglas clave (añadidas 2026-05-13):
- **No SELECT sobre posición ya abierta.** Si el ticker está en `active_picks_relevant`, debe ser HOLD, no SELECT. Violación detectada en validador.
- **No usar DEMS/spike_flag como razón primaria de REJECT en HIGH_CONVICTION o CONFIRMED_FLOW_LEADERS.** Esas carteras se rigen por métricas semanales. Usar WATCH en su lugar.
- **No especular sobre cambios entre semanas si `prev_snapshot_available=false`.** El payload indica explícitamente si hay snapshot previo disponible.

---

## Señales diarias (DEMS) — reglas de uso

```
Daily signals = radar temprano        → solo para EARLY_ROTATION
Weekly signals = confirmación         → HIGH_CONVICTION, CONFIRMED_FLOW
Macro = permiso de riesgo             → todas las carteras
```

| DEMS | spike_flag | Acción recomendada |
|------|-----------|-------------------|
| ≥14 | false | Puede SELECT si PCS ≥ 68 (solo EARLY_ROTATION) |
| 10–13 | cualquiera | WATCH, no SELECT |
| <10 | — | No usar DEMS como razón primaria |
| cualquiera | true | WATCH, salvo outperform_d10 ≥ 6 |

---

## Archivos de datos clave

| Archivo | Descripción |
|---------|-------------|
| `docs/data/ai_candidates.json` | 91 tickers con PCS, métricas, flags — input del modelo |
| `docs/data/ai_candidates_prev.json` | Snapshot de la semana anterior |
| `docs/data/ai_model_reasoning.json` | Razonamiento estructurado del modelo activo (último run) |
| `docs/data/ai_picks.json` | Posiciones abiertas en paper portfolio |
| `docs/data/shadow_picks.jsonl` | Todos los picks (activo + shadow) para tracking de rendimiento |
| `docs/data/baselines.jsonl` | Baselines mecánicas por run: top-3 PCS, rot_score, ret_4w, ret_13w |
| `docs/data/ai_model_test_summary.jsonl` | Métricas por llamada al modelo (coste, latencia, quality score) |
| `docs/data/model_tests/` | Respuesta completa de cada modelo por fecha |
| `docs/data/ai_model_payloads/` | Payload exacto enviado al modelo por fecha |
| `docs/data/reminders.json` | Recordatorios programados → Telegram |
| `docs/data/eval_bundle_latest.json` | Bundle para evaluador externo (generado con build_eval_bundle.py) |

---

## Force Analyze — análisis ad-hoc de cualquier ticker (implementado 2026-06-25)

Script: `scripts/force_analyze.py`. Documentación completa: `wiki/FORCE_ANALYZE_AUDIT.md`.

Dos modos principales:

### Modo análisis (force_analyze normal)

Pide a uno o varios modelos que analicen un ticker con los datos actuales de `ai_candidates.json`.

```bash
py -3 scripts/force_analyze.py NVDA                                    # modelo activo
py -3 scripts/force_analyze.py SMCI --compare-portfolio all            # contrasta vs cartera
py -3 scripts/force_analyze.py CORZ --compare-portfolio HIGH_CONVICTION
py -3 scripts/force_analyze.py MSTR --all-models --save
py -3 scripts/force_analyze.py TSLA --models grok mimo
```

Aliases de modelo: `grok`, `mimo`, `haiku`, `sonnet` (o IDs completos de OpenRouter).
Portfolios: `HIGH_CONVICTION`, `CONFIRMED_FLOW_LEADERS`, `EARLY_ROTATION`, `MACRO_THEMATIC_BENEFICIARIES`, `MIMO_SHADOW`, `all`.

### Modo auditoría (--audit)

Cuando grok y mimo discrepan sobre un ticker, genera un prompt árbitro con los datos exactos del pipeline (lo que ambos modelos vieron) para obtener una tercera opinión.

**Exportar para copiar-pegar** (sin coste de API — pegar en Claude.ai, ChatGPT, etc.):
```bash
py -3 scripts/force_analyze.py SE --audit                  # run de hoy
py -3 scripts/force_analyze.py SE --audit --date 2026-06-25 --save  # guarda .txt
```

**Llamar a un árbitro por API** (gasta créditos):
```bash
py -3 scripts/force_analyze.py SE --audit --models sonnet --save
py -3 scripts/force_analyze.py SE --audit --models haiku
```

**Fuentes de datos del modo auditoría:**
- `docs/data/ai_model_payloads/YYYY-MM-DD.json` — payload exacto enviado a los modelos
- `docs/data/model_tests/YYYY-MM-DD_*.json` — respuestas completas de cada modelo

**Salidas con `--save`:**
- Sin `--models`: `docs/data/force_analysis/TICKER_YYYYMMDD_HHMM_audit_prompt.txt`
- Con `--models`: `docs/data/force_analysis/TICKER_YYYYMMDD_HHMM.json`
- Siempre actualiza: `docs/data/force_analyses.json` (log del visor del dashboard)

**Dashboard:** AI Picks Lab → pestaña "Force Analysis". Las auditorías se muestran con badge morado "AUDITORÍA" y las decisiones originales de cada modelo antes del veredicto del árbitro.

---

## Sistema de evaluación externa

Para evaluar la calidad del razonamiento del modelo:

```bash
py -3 scripts/build_eval_bundle.py
```

Genera `docs/data/eval_bundle_latest.json` con:
- `system_rules`: HARD_RULES, mandatos de portfolios, reglas de estilo
- `input_context`: los 15 candidatos que recibió el modelo + macro_context + posiciones abiertas
- `model_decisions`: razonamiento completo estructurado
- `evaluation_rubric`: 4 categorías con peso y preguntas concretas

**Rúbrica de evaluación:**

| Categoría | Peso | Qué mide |
|-----------|------|---------|
| Hard rule compliance | 30% | ¿Siguió todas las reglas? |
| Reasoning quality | 35% | ¿Citó números reales? ¿Comparó peers? ¿No inventó datos? |
| Decision consistency | 25% | ¿Las decisiones son coherentes con los umbrales? |
| Coverage and balance | 10% | ¿Cubrió todos los candidatos PCS≥62? ¿Selección apropiada? |

**Errores típicos detectados en Grok 4.3 (2026-05-12):**
- Confundió dist_52w_high de CORZ (-8.24%) con la de MSTR (-57%) → error numérico grave
- Seleccionó NBIS que ya estaba en open_positions (ahora bloqueado por validador)
- Especuló "PCS climbed from 83 to 88" sin tener prev_snapshot (ahora HARD_RULE)
- Rechazó SASK.V (PCS 84, rot_score 9, 6 semanas streak) principalmente por DEMS 4 (ahora HARD_RULE)

---

## Baselines mecánicas

Con cada run de `paper_trading.py` se registra en `baselines.jsonl`:
- `top_pcs`: top-3 tickers elegibles por PCS
- `top_rot_score`: top-3 por rot_score
- `top_ret_4w`: top-3 por ret_4w_vs_spy
- `top_ret_13w`: top-3 por ret_13w_vs_spy

**Propósito:** comparar rendimiento posterior del modelo vs estas baselines mecánicas. Si el modelo no bate consistentemente a top-3-PCS, el filtro IA no añade valor.

---

<!-- BOT_DOCS_START -->

## Telegram Portfolio Bot

> Sección auto-generada desde `scripts/telegram_portfolio_bot.py` — no editar manualmente.
> Se regenera en cada run del pipeline. Para añadir comandos: editar `COMMANDS` en el script.

Bot que procesa comandos de Telegram para gestionar el Portfolio Tracker
(`portfolio.json` / `localhost:3000/portfolio.html`).
Se ejecuta como Step 12 en el pipeline de GitHub Actions (2×/día, modo `--once`).
También se puede lanzar en modo continuo localmente: `py -3 scripts/telegram_portfolio_bot.py`

**Estado persistido en:** `docs/data/telegram_bot_state.json` (commiteado en cada run).

**IMPORTANTE:** Gestiona `portfolio.json` (Portfolio Tracker), independiente de `ai_picks.json` (AI Picks Lab).

### Comandos

| Comando | Uso | Descripción |
|---------|-----|-------------|
| `/portfolio` | `/portfolio` | Lista todas las secciones y tickers del Portfolio Tracker, agrupados por sección (máx 12 por sección). |
| `/check` | `/check TICKER` | Precio actual Yahoo Finance (15 min delay) + sección, shares, avgCost y P&L si la posición tiene datos de coste. |
| `/add` | `/add TICKER [notas opcionales]` | Añade el ticker a la sección 'Watchlist' de portfolio.json. Crea la sección si no existe. Rechaza duplicados. |
| `/remove` | `/remove TICKER` | Elimina el ticker de cualquier sección del portfolio. |

### Flujo de datos (write commands)

```
Usuario → Telegram → getUpdates (pipeline 2×/día o local continuo)
        → modifica portfolio.json en disco
        → git commit + push  (paso "Commit updated data" del workflow)
        → server.js git pull (al arrancar o botón Sincronizar)
        → portfolio.html ve los cambios
```

<!-- BOT_DOCS_END -->

---

## Recordatorios programados

Gestionados en `docs/data/reminders.json`. El workflow los comprueba cada día y envía el mensaje por Telegram en la fecha programada.

| Fecha | ID | Contenido |
|-------|----|-----------|
| 2026-05-28 | semana3_metricas_horizonte | Prompt para implementar métricas por horizonte + comparativa vs baselines + análisis spike_flag |
| 2026-07-01 | semana7_motor_avanzado | Prompt para Open Pick Review Engine + validación numérica + rejection_primary_reason + análisis doble conteo PCS |

Para añadir un recordatorio: editar `docs/data/reminders.json` directamente (sin tocar código).

---

## Extension Risk y Theme Concentration Risk (implementado 2026-05-16)

### Principio: fase OBSERVACIÓN, no bloqueo
Ambos campos son **informativos**. El sistema está en paper trading. El objetivo es recoger datos para determinar si correlacionan con peor rendimiento antes de hacerlos bloqueantes.

### Extension Risk

Calculado en `scripts/pcs_calculator.py → compute_extension_risk()`. Responde: "¿estoy entrando tarde?"

**No se mezcla con PCS.** PCS = ¿es fuerte esta señal? Extension risk = ¿llego tarde?

| Campo | Fuente | Notas |
|-------|--------|-------|
| `dist_sma20_atr` | (close − SMA20) / ATR14 | Requiere High/Low diarios — extraídos del mismo `yf.download()` de DEMS |
| `rsi_14` | RSI Wilder 14 períodos sobre close | Calculado en `fetch_daily_metrics()` |
| `momentum_decay` | `ret_5d_vs_spy < −1%` AND `ret_20d_vs_spy > 20%` | Move fuerte pero impulso frenándose |
| `spike_flag` | Ya existía en DEMS | Doble efecto: reduce DEMS Y aumenta extension_points |

**Fórmula de puntos → nivel:**
- dist_sma20_atr > 3.0 → +3 pts (`dist_sma20_atr_extreme`); > 2.0 → +2 pts
- ret_4w_vs_spy > 40% → +3 pts; > 25% → +2 pts
- momentum_decay = true → +2 pts
- spike_flag = true → +2 pts
- RSI > 85 → +2 pts; > 78 → +1 pt
- **≥6 pts = extreme · ≥4 = high · ≥2 = medium · <2 = low**

**Campos en ai_candidates.json:** `extension_risk`, `extension_points`, `extension_flags`
**Campos en payload del modelo:** `extension_risk`, `extension_points`, `extension_flags` (por candidato)
**Campos en shadow_picks.jsonl:** `extension_risk`, `extension_points`, `extension_flags` (al seleccionar)

**Soft guidance al modelo:** si extension_risk es "high" o "extreme", el modelo debe reconocerlo en `reason_full` o `key_risks`. Si no lo hace, se registra `extension_risk_not_acknowledged` en `validation.soft_warnings` del test result — sin penalización en quality_score.

**Importante:** ret_4w_vs_spy > 25% será frecuente en este universo (crypto miners, energy small caps). Esto es esperado — serán etiquetados como "extended" habitualmente. El análisis de semana 3 dirá si eso importa.

### Theme Concentration Risk

Calculado en `scripts/paper_trading.py → compute_theme_concentration()`. Responde: "¿estoy comprando el mismo trade varias veces?"

**Campos en payload por candidato:** `theme_concentration_risk`, `subtheme_concentration_risk`
**Sección nueva en payload:** `theme_exposure` (nivel raíz, junto a `macro_context`)

```
theme_exposure = {
  "oil_gas": {open_positions, open_tickers, open_weight_pct, new_candidates_today, risk}
}
```

**Reglas de clasificación tema padre:** `high` si ≥3 posiciones o ≥30% weight; `medium` si ≥2 o ≥20%; `low` resto.
**Reglas subtema:** `high` si ≥2 posiciones o ≥20% weight; `medium` si ≥1 o ≥10%; `low` resto.

**Soft guidance al modelo:** cuando theme_concentration_risk es "high", reconocerlo en el razonamiento. Puede seleccionar igualmente. Preferir diversificación solo si candidatos son equivalentes.

### Cuándo convertir en filtro duro
1. Cuando haya ≥30–50 picks con datos de rendimiento real (ret_1w, ret_1m).
2. Análisis: `rendimiento(extension_risk=low)` vs `rendimiento(extension_risk=high/extreme)`.
3. Si diferencia es estadísticamente significativa y consistente → se justifica añadir como HARD_RULE.
4. Mismo criterio para theme_concentration_risk.

---

## Roadmap de mejoras pendientes

### Semana 3 (≈2026-05-28)
- ✅ `scripts/update_performance.py`: implementado (2026-05-27). Rellena ret_1d/3d/1w/2w/1m/3m + vs_spy_1m + max_gain_1m + max_drawdown_1m en shadow_picks.jsonl. Se ejecuta automáticamente en cada run del pipeline (Step 10b). Ver detalles abajo.
- ✅ Comparativa picks vs baselines + análisis spike_flag + simulación EXIT: implementado (2026-06-22). Script: `scripts/compare_vs_baselines.py`. Resultados: `docs/data/baseline_comparison.json`. Ver hallazgos abajo.

### Comparativa vs baselines — compare_vs_baselines.py (implementado 2026-06-22)

Compara picks activos del modelo vs baselines mecánicas y simula señales de EXIT.

**Uso:**
```bash
py -3 scripts/compare_vs_baselines.py              # descarga precios frescos + análisis completo
py -3 scripts/compare_vs_baselines.py --no-fetch   # usa cache de precios (_baseline_price_cache.json)
py -3 scripts/compare_vs_baselines.py --save-cache # guarda precios para --no-fetch futuro
```

**Hallazgos 2026-06-22** (13 picks activos con ret_1m, periodo 2026-05-08 al 2026-05-19):
- AI avg ret_1m = -8.8% vs baseline top-PCS = -5.0% → AI underperformed en overall (-3.8%)
- Win rate por run: 5/8 = 62% vs top-PCS (gana la mayoría de runs, pero las pérdidas son más grandes)
- HIGH_CONVICTION: avg +7.2% (mejor portfolio), CONFIRMED_FLOW_LEADERS: avg -19.4%
- **spike_flag**: 1 pick con spike=True → -28.9%; 12 sin spike → -4.9%. Evitar spikes habría mejorado +24.1%
- **EXIT simulation**: 4/13 picks habrían tenido señal de EXIT. Exiting early habría mejorado avg +7.2% en esos picks
- **Limitación**: EXIT simulation solo cubre tickers que reaparecieron en payloads posteriores (top-15 candidatos); tickers que salieron del universo no tienen historial PCS/rot_score

**Salida:** `docs/data/baseline_comparison.json` (machine-readable con todos los datos)

---

### Performance tracking — update_performance.py (implementado 2026-05-27)

Rellena campos de rendimiento en `shadow_picks.jsonl` usando precios reales de yfinance.
Se ejecuta en el pipeline como **Step 10b** (tras paper_trading.py, antes de Telegram).

**Campos calculados:**

| Campo | Descripción |
|-------|-------------|
| `ret_1d/3d/1w/2w/1m/3m` | Retorno absoluto del ticker (%) a N días hábiles desde la entrada |
| `vs_spy_1m` | Alpha vs SPY al mes = ret_1m − spy_ret_1m |
| `max_gain_1m` | Máximo intradiario alto vs precio entrada en ventana 1 mes (%) |
| `max_drawdown_1m` | Mínimo intradiario bajo vs precio entrada en ventana 1 mes (%) |

**Precio base:** `entry_price` si está disponible (pick real de paper trading), sino close de yfinance en fecha de entrada.

**Disponibilidad de datos:**
- ret_1m / vs_spy_1m: disponibles a partir de ≈21 días hábiles tras la entrada (~2026-06-09 para los primeros picks)
- ret_3m: disponibles a partir de ≈63 días hábiles (~2026-08-05 para los primeros picks)

**Uso manual:**
```bash
py -3 scripts/update_performance.py               # rellena todos los nulls
py -3 scripts/update_performance.py --dry-run     # muestra cambios sin escribir
py -3 scripts/update_performance.py --force       # recomputa filas ya rellenas
py -3 scripts/update_performance.py --report      # imprime resumen de rendimiento
py -3 scripts/update_performance.py --ticker CVE  # actualiza solo un ticker
```

**Resumen de datos actuales (2026-05-27):**
- 61 picks actualizados con ret_1d/ret_1w/ret_2w (horizonte máximo disponible: ~13 días hábiles)
- vs_spy_1m: aún null (necesita 21 días hábiles)
- Picks más destacados a 2 semanas: NBIS +21.3%, CORZ +10.2%
- Picks con mayor drawdown: MSTR -14.8%, COIN -16.9%

---

### Cierre de posiciones — implementado 2026-06-09

El sistema ahora puede cerrar posiciones mediante `open_picks_review` en la respuesta del modelo.

**Cambios en `scripts/paper_trading.py`:**
- `active_picks_relevant` en el payload ahora incluye `current_pcs`, `current_rot_score`, `current_streak_weeks`, `current_ret_4w_vs_spy` y `pcs_min_entry` por posición
- Nueva HARD_RULE: el modelo debe revisar todas las posiciones activas e incluirlas en `open_picks_review` con `action=HOLD|EXIT`
- Criterio de EXIT: `current_pcs < pcs_min_entry AND current_streak_weeks <= 1`, OR `current_rot_score <= 2`
- `update_portfolio` procesa los EXIT: elimina la posición de `positions[]` y añade evento `close` en `history[]` con `close_date`, `close_price` (último cierre del parquet) y `close_reason`
- `validate_model_response` genera `open_picks_review_missing` (soft warning) para posiciones no revisadas

**Schema de respuesta** — nuevo campo:
```json
"open_picks_review": [
  {"ticker": "VAL", "portfolio": "HIGH_CONVICTION", "action": "EXIT", "reason": "..."}
]
```

**Nota:** REDUCE no implementado (reservado para semana 7). Por ahora solo HOLD|EXIT.

### Semana 7 (≈2026-07-01)
- `scripts/review_open_picks.py`: Open Pick Review Engine separado del New Pick Engine. Evalúa posiciones abiertas → HOLD/ADD/REDUCE/EXIT con análisis más profundo. Guarda en `ai_picks_review.jsonl`
- Validación numérica automática: cruzar números citados en reason_full contra el payload, detectar discrepancias >10%
- Campo `rejection_primary_reason` en el schema de respuesta del modelo
- Análisis de correlación entre componentes PCS (A-F) y rendimiento posterior (ret_1m)

---

## Modelos y costes (OpenRouter)

| Modelo | Input $/M | Output $/M | Rol |
|--------|-----------|------------|-----|
| x-ai/grok-4.3 | 1.25 | 2.50 | Activo actual |
| xiaomi/mimo-v2.5-pro | 0.435 | 0.87 | Shadow / fallback (desde 2026-06-20) |
| anthropic/claude-haiku-4.5 | 1.00 | 5.00 | Retirado como shadow |
| anthropic/claude-sonnet-4.6 | 3.00 | 15.00 | Shadow ocasional |

**ACTIVE_MODEL** se configura en GitHub Variables (`vars.ACTIVE_MODEL`). El fallback se aplica automáticamente si el modelo activo falla.

---

## Evaluación general del método (opinión experta externa, 2026-05-13)

> "El método es correcto. Ahora lo importante no es hacerlo más inteligente, sino hacerlo más falsable."

Valoración:
- Calidad conceptual: 8.5/10
- Arquitectura: 8/10
- Riesgo de sobreingeniería: medio-alto
- Potencial de aprendizaje: muy alto

**Principio guía:** no añadir complejidad antes de tener datos que la justifiquen. Mantener siempre baselines simples como referencia.

---

## Convenciones de desarrollo

- Actualizar este CLAUDE.md siempre que se implemente una funcionalidad nueva o se cambie una decisión de diseño
- Los recordatorios futuros van en `docs/data/reminders.json` (no en código)
- Las reglas del modelo van en `HARD_RULES` (paper_trading.py) — se incluyen automáticamente en el payload
- El evaluador externo recibe `eval_bundle_latest.json` generado con `build_eval_bundle.py`
- `baselines.jsonl` se actualiza automáticamente con cada run — no editar manualmente
