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
scripts/koncorde_calculator.py → Koncorde Plus D/3D/W (blue/green/trend/state) → koncorde_data.json + ai_candidates.json
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

**Regla endurecida 2026-07-01:** un candidato con pcs≥62 no seleccionado debe aparecer en **exactamente una** de `watch`/`rejected`, nunca en ambas. Antes la regla decía solo "must appear in watch or rejected", y el 2026-07-01 (run `2026-07-01_1123`) mimo-v2.5-pro interpretó el "or" como inclusivo: puso los mismos 10 tickers dudosos en ambas listas con justificaciones distintas (quality_score cayó a 77 por 10 violaciones "Duplicate ticker"). Reforzado el texto en `HARD_RULES` y en el prompt (`build_prompt`) para dejar explícito que es exclusión mutua y que aparecer en dos listas es una hard rule violation.

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

## Incidente: avisos Telegram de entrada/salida silenciosamente rotos (resuelto 2026-07-02)

**Síntoma:** ningún aviso automático de apertura/cierre de posición llegaba a Telegram, en ninguna cartera (incluida `MIMO_SHADOW`), desde que el sistema de avisos en tiempo real se introdujo el 2026-06-18.

**Causa raíz:** el secret `TELEGRAM_BOT_TOKEN` en GitHub Actions (Settings → Secrets and variables → Actions) estaba vacío. `TELEGRAM_CHAT_ID` sí estaba configurado. Tanto `_notify_changes()` (aviso inmediato en `paper_trading.py`, Step 10) como `notify_telegram.py` (fallback, Step 11) comparten la misma comprobación `if not token or not chat_id: skip` — con el token vacío, ambos salían en silencio en cada run, sin marcar el step como fallido.

**Por qué los comandos manuales del bot (`/check`, `/portfolio`...) sí funcionaban:** `telegram_portfolio_bot.py` se ejecuta también en local en modo continuo (`py -3 scripts/telegram_portfolio_bot.py`, ver sección "Telegram Portfolio Bot"), leyendo el `.env` local — que sí tiene el token correcto. El pipeline en GitHub Actions es un entorno separado con sus propios Secrets; ahí es donde faltaba.

**Fix aplicado:**
- `scripts/notify_telegram.py`: si faltan `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, ahora hace `sys.exit(1)` en vez de retornar en silencio — el step de Actions se marca como fallido (visible en la pestaña Actions) en lugar de desaparecer en los logs.
- `.github/workflows/market-update.yml`, Step 11: añadido `continue-on-error: true` para que ese fallo sea visible sin bloquear los steps siguientes (Step 12 comandos Telegram, commit de datos).
- `_notify_changes()` en `paper_trading.py` (Step 10) se dejó igual (skip silencioso) a propósito: esa función vive dentro del pipeline principal de picks, y no queremos que un secret de Telegram ausente tumbe la selección de picks — para eso existe el fallback dedicado en Step 11, que ahora sí falla de forma visible.
- Añadido `"MIMO_SHADOW": "Mimo Shadow"` a `_PORTFOLIO_LABELS` en `paper_trading.py` (faltaba, aunque no era la causa del silencio — solo afectaba al texto del aviso).

**Pendiente del lado del usuario:** rellenar `TELEGRAM_BOT_TOKEN` en GitHub Secrets con el mismo valor que hay en `.env` local. Tras eso, el próximo run debería notificar todo lo acumulado sin avisar desde el 2026-06-18.

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

## Koncorde Plus en el payload del modelo (implementado 2026-07-02)

`scripts/koncorde_calculator.py` (Step 9b) ya calculaba Koncorde Plus D/3D/W e inyectaba los campos `konc_*` en `docs/data/ai_candidates.json` desde antes, pero `_compact_candidate()` en `paper_trading.py` no los incluía en la whitelist enviada al modelo — el dato existía pero se perdía en la última milla. Detectado en revisión externa 2026-07-02.

**Campos añadidos a `_compact_candidate()`** (`paper_trading.py` y su copia en `build_eval_bundle.py`, que debe mantenerse en sync):
`konc_d_state`, `konc_3d_state`, `konc_3d_blue`, `konc_3d_green`, `konc_3d_trend`, `konc_w_state`.

No se mandan los 18+ campos posibles (D/3D/W × blue/green/trend/estado) para no saturar al modelo. Se manda el estado clasificado de los tres timeframes (la señal ya destilada) más los valores numéricos del 3D — el timeframe con mejor relación señal/ruido: el diario es ruidoso, el semanal es lento.

**Guidance añadida al prompt** (sección OBSERVATION FIELDS, sin HARD_RULE ni penalización de quality_score):
> Koncorde 3D and W states indicate institutional flow direction. When konc_3d_state="distribution" or konc_w_state="distribution", note this in your reasoning for any SELECT decision. Koncorde daily (konc_d_state) is noisy — weight 3D and W more heavily.

**Decisión de diseño — Early Flow Detector (JS) no se porta a Python todavía.** Early Flow (`shared/flow-score.js`, solo dashboard) y `extension_risk` (payload) son complementarios, no redundantes: extension_risk responde "¿es mala entrada?" (dist_sma20_atr, ret_4w_vs_spy, spike_flag, momentum_decay); Early Flow responde "¿es buena entrada?" (giro Koncorde D + confirmación 3D/W + compresión ATR + RSI en zona de recuperación). Orden de trabajo acordado: (1) Koncorde en el payload — hecho aquí; (2) observar si el modelo lo usa bien en su razonamiento; (3) solo si no lo hace, valorar portar Early Flow como campo calculado.

**Resuelto 2026-07-02 (ver sección "Koncorde Plus v2 + Rotation/Macro v2" más abajo):** el drift de `HARD_RULES`/`_compact_candidate()` entre `paper_trading.py` y `build_eval_bundle.py` señalado aquí se cerró centralizando ambos en `scripts/ai_shared.py`. `DAILY_SIGNALS_RULES`/`REASONING_STYLE_RULES`/`EVALUATION_RUBRIC` siguen siendo específicos de `build_eval_bundle.py` (no aplica centralizarlos, son propios del bundle de evaluación externa).

---

## Koncorde Plus v2 + Rotation/Macro v2 (implementado 2026-07-02)

Se recibió una hoja de instrucciones extensa ("Flujos & Rotación v2 + Koncorde Plus D/3D/W"). Antes de implementar se auditó el repo y se confirmó que la mayor parte ya existía (Koncorde Plus D/3D/W, MacroScore v2, Rotation Score de 3 bloques, clusters macro, histéresis de régimen, flags CREDIT_COMPLACENCY/INFLATION_OVERLAY/TERM_PREMIUM_EXTREME/EMERGENCY_MODE) — este cambio cierra los gaps concretos que quedaban, sin tocar PCS ni rot_score principal (Koncorde sigue fuera de ambos, tal como pedía la hoja).

### 1. Campos Koncorde que faltaban (`scripts/koncorde_calculator.py`)

Añadidos por timeframe (D/3D/W): `konc_{tf}_blue_down_2_bars`, `konc_{tf}_accumulation_flag`, `konc_{tf}_distribution_flag`, `konc_{tf}_bar_closed` (fijo `true` — pipeline end-of-day, sin velas parciales), `konc_{tf}_bar_date` (fecha de la última vela cerrada, usada para deduplicar shadow exits, ver más abajo).

Nuevo campo top-level **`konc_alignment`**, con prioridad explícita (no la del orden literal de la hoja original — corregido tras revisión):
```
distribution_warning > bearish_aligned > accumulation_setup > bullish_aligned > mixed > neutral
```
`accumulation_setup` (3D=accumulation, W no bajista) tiene prioridad sobre `bullish_aligned` aunque W también sea alcista — el setup de acumulación es operativamente más relevante que una alineación genérica.

`run()` ahora también recoge tickers de posiciones abiertas en `ai_picks.json` (todas las carteras) para el universo de cálculo — así un ticker que sale de los 91 candidatos (`left_universe=true`) sigue teniendo Koncorde mientras la posición siga abierta (necesario para los shadow exits).

### 2. Payload IA compacto, snapshots ricos (`scripts/paper_trading.py`, `scripts/ai_shared.py`)

**`scripts/ai_shared.py` (nuevo):** centraliza `HARD_RULES`, `NON_TRADABLE_SUBTHEMES`, `VALID_REJECT_CATS` y `compact_candidate()` — antes duplicados y desincronizados entre `paper_trading.py` y `build_eval_bundle.py` (build_eval_bundle.py tenía solo 8 de 14 reglas). Ambos scripts ahora importan de aquí; evita que el drift vuelva a pasar.

El payload que ve el modelo solo gana `konc_alignment` (además de los `konc_*` ya existentes: `konc_d_state`, `konc_3d_state`, `konc_3d_blue`, `konc_3d_green`, `konc_3d_trend`, `konc_w_state`) — se mantiene compacto a propósito.

**`shadow_picks.jsonl` ahora guarda un set rico** por pick seleccionado: `konc_3d_state`, `konc_3d_blue`, `konc_3d_green`, `konc_3d_blue_slope`, `konc_3d_blue_down_2_bars`, `konc_3d_distribution_flag`, `konc_w_blue`, `konc_w_state`, `konc_alignment`, `konc_3d_bar_date`, `konc_w_bar_date` — necesario para analizar más adelante si Koncorde 3D anticipa peor rendimiento (ret_1w/2w/1m).

**Bug encontrado y corregido:** `_log_shadow_picks()` construía su lookup de candidato (`cand_lookup`) esperando una `list`, pero recibía el dict `{ticker: pcs}` — la condición `isinstance(cand_pcs, list)` era siempre falsa, así que `cand_lookup` estaba siempre vacío. Resultado: **`extension_risk`/`extension_points`/`extension_flags`/`theme_concentration_risk`/`subtheme_concentration_risk` se han guardado como `null` en el 100% de los 201 picks registrados desde que esas features se implementaron (2026-05-16)** — nunca funcionaron. Arreglado añadiendo un parámetro `cand_snapshot` (dict ticker→candidato crudo + concentración, construido en el caller) que reemplaza la lógica rota. Verificado con datos reales: tras el fix, 41/128 tickers muestran `theme_risk` no-"low" (antes: 0/201 siempre null).

### 3. Warnings soft de Koncorde para la IA (`scripts/paper_trading.py → validate_model_response`)

Tres warnings nuevos, igual de "soft" que `extension_risk_not_acknowledged` (logueados en `ai_model_test_summary.jsonl`, **sin penalizar `quality_score`**, fase de observación):
- `KONC_3D_DISTRIBUTION_WARNING`: SELECT con `konc_3d_state=distribution` sin mencionar "koncorde"/"distribution"/"institutional" en el razonamiento.
- `KONC_3D_BLUE_DOWNTREND_WARNING`: SELECT con `konc_3d_blue_down_2_bars=true`.
- `DEMS_EXTREME_KONC_DISTRIBUTION_WARNING`: SELECT con `dems>=15 AND extension_risk in (high,extreme) AND konc_3d_state=distribution`.

Prompt (`OBSERVATION FIELDS`) actualizado con la guidance completa: 3D es la lectura operativa principal, D es ruido, W confirma estructuralmente.

### 4. Shadow exits por Koncorde 3D (`scripts/koncorde_shadow_exits.py`, nuevo — Step 9c del pipeline)

Contrafactual puro: no cierra posiciones reales, solo registra en `docs/data/shadow_exits.jsonl` cuándo una posición abierta (todas las carteras, incluida `MIMO_SHADOW`) muestra deterioro en Koncorde 3D:
- `EXIT_SHADOW_KONC3_BLUE_CROSS_DOWN` (cruce blue≥0→<0)
- `EXIT_SHADOW_KONC3_DISTRIBUTION` (transición a estado distribution)
- `EXIT_SHADOW_KONC3_BLUE_SLOPE_NEGATIVE_2_BARS` (nivel persistente)

Lee Koncorde de `koncorde_data.json` (no de `ai_candidates.json`) para cubrir tickers que salieron del universo de 91. **Deduplicación por `(position_id, signal, konc_3d_bar_date)`** vía `docs/data/koncorde_shadow_state.json` — imprescindible porque el pipeline corre 2×/día pero la vela 3D solo cambia cada 3 sesiones; sin esto, una condición persistente se re-loguearía en cada run. Verificado en producción: primera ejecución detectó 3 señales reales (URI, CAT, ABBV), la segunda ejecución el mismo día no duplicó ninguna.

### 5. CMF real + fin del mislabeling "Koncorde Azul" (`server.js`, `rotacion.html`, `backtest/src/rotation/score.py`)

Se descubrió que `data.konAzul` en `calcRotScore()` (rotacion.html) siempre era `undefined` — `server.js` nunca había calculado ni devuelto CMF bajo ningún nombre. El criterio CMF del Bloque B del RotScore (1 de 10 puntos) **nunca puntuó para ningún ticker en el dashboard** desde que existe esa tabla. No era solo un problema de naming.

Arreglado de raíz: `calcCMF(closes, highs, lows, volumes, period=20)` nuevo en `server.js` (mismo patrón que `calcATR`/`calcOBV`), fórmula estándar Chaikin Money Flow, devuelto como `cmf20` en `/api/quote/:symbol`. `rotacion.html` usa `data.cmf20 > 0.05` (umbral endurecido, no `> 0` — decisión previa del usuario que tampoco estaba reflejada en la réplica Python). `backtest/src/rotation/score.py` (que ya tenía `cmf20` real desde antes, vía `indicators.py`) se corrigió al mismo umbral `> 0.05` (usaba `> 0.0`).

### 6. ROT. CONFIRMADA (antes "ROT. TEMPRANA") + nueva ROT. TEMPRANA por inflexión

La señal que se llamaba "ROT. TEMPRANA" exigía persistencia de 3 semanas — no era temprana. Renombrada a **ROT. CONFIRMADA** en `rotacion.html` (`isConfirmedRotation`/`getConfirmedRotMeta`) y en los comentarios/docstrings de `backtest/src/rotation/early_rotation.py` (los nombres internos de función/campos de ese módulo de backtest —`evaluate_early_rotation`, `is_early_rotation`— NO se renombraron: cambiarlos rompería el esquema de `rotation_history.parquet` ya persistido; solo se documentó el cambio semántico).

Nueva **ROT. TEMPRANA** (`isNewEarlyRotation`/`qualifiesForNewEarlyRotation` en JS, `_qualifies_new_early_rotation` en Python), basada en inflexión — 4 condiciones individuales + gate de clúster:
1. Score actual ≥ 6/10
2. Inflexión: score mejora ≥2 pts vs lectura anterior (nuevo campo `prev_score` en `early_rotation_candidates`, capturado una vez por día antes de sobrescribir `last_score`)
3. RS 4 semanas vs SPY > 0
4. `konc_3d_state != distribution` — **primer uso de Koncorde como condición real, no solo informativa**, justificado porque la hoja lo pide explícitamente para esta señal
5. ≥2 activos del mismo clúster cumplen 1-4 simultáneamente ("ambos", no solo el ticker evaluado) + filtro benchmark (SPY>SMA200 o NetLiq>+300B)

Prioridad si ambas señales aplican: CONFIRMADA > TEMPRANA. Ninguna de las dos se degrada por el Master Filter (cada una lleva su propio filtro de benchmark). El backtest histórico (`simulator.py`) no implementa la señal nueva — Koncorde Plus solo tiene histórico desde 2026-06-30, insuficiente para backtest retroactivo del gate.

**Fase 6b — subtheme_cluster:** la nueva ROT. TEMPRANA se calcula también a nivel de acciones individuales agrupando por `subtheme` (`docs/data/universe.json`, 21 temas finos: Crypto/Miners, AI Infrastructure, Uranium, etc.) en `backtest/src/rotation/stock_scanner.py`, independiente del `macro_cluster` (6 grupos ETF) usado por la señal CONFIRMADA. Campos nuevos por stock: `rotation_cluster_type` (`"macro_cluster"|"subtheme_cluster"`), `rotation_cluster_name`. `main_stocks.py` pasa `universe_path`/`koncorde_path` a `scan_stocks()`.

**Rename de campo `cluster_has_rot_temprana` → `cluster_has_confirmed_rotation`** (y `active_rot_temprana_clusters` → `active_confirmed_rotation_clusters`) en `stock_scanner.py`/`main_stocks.py`/`rotacion.html`/`server.js` — seguro porque `stock_candidates.json` se regenera completo en cada run (no es histórico persistido). **Importante:** este rename tenía más consumidores de los detectados inicialmente — `scripts/export_to_json.py` y `scripts/pcs_calculator.py` (2 sitios, alimenta el flag `is_early` de la IA) también leían el nombre viejo y se actualizaron; sin este fix habrían roto silenciosamente la clasificación `is_early` en el payload.

### 7. Regímenes macro — capa de display, sin tocar el motor (`rotacion.html`, `docs/index.html`)

Decisión explícita: los nombres canónicos (`Bull Pleno`, `Bull Maduro`, `Transición`, `Risk-OFF`, `Capitulación`) **no se tocan** — siguen igual en `backtest/src/macro/regime.py`, `backtest/src/portfolio/engine.py` (que tiene lógica real tipo `if regime in ('Risk-OFF','Capitulación')`), `clusters.py`, `fit.py`, ~15 archivos de test, y cualquier parquet histórico ya persistido. Se detectó que renombrar ahí tenía un blast radius mucho mayor de lo previsto (lógica de portfolio engine + tests + histórico), así que se optó por una capa de display únicamente.

Función `displayRegimeName(regime)` (una sola definición por archivo, en `rotacion.html` y en `docs/index.html` — son dos dashboards independientes sin módulo JS compartido para esto) aplicada solo en los puntos donde se muestra texto al usuario:
```
Bull Pleno   → Risk-On Fuerte
Bull Maduro  → Risk-On Maduro
Transición   → Transición
Risk-OFF     → Risk-Off
Capitulación → Estrés / Capitulación
```
Nunca usada en comparaciones de lógica (histéresis, `current_regime`/`pending_regime` siguen canónicos).

**`macro_delta_1w`/`macro_delta_4w`/`macro_trend`** (nuevo en `rotacion.html` — `docs/index.html` ya tenía delta_1w/delta_1m de otra fuente, solo se le aplicó el display de nombre): nuevo `macro_score_history` en el estado persistido (una entrada diaria, mismo patrón de protección multi-refresh que los streaks), función `computeMacroTrend()` calcula deltas vs la lectura más cercana a 7/28 días atrás y clasifica `improving`/`stable`/`deteriorating`. Mostrado junto al badge de régimen: p.ej. "Risk-On Fuerte Improving".

### Fuera de alcance (explícito)

Koncorde dentro de PCS o rot_score principal, hard rules universales por Koncorde, sustituir `computeFlowScore` legacy por FlowScore v2 completo, gate Koncorde en el backtest histórico retroactivo, renombrar regímenes en el motor Python/tests/histórico.

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
- Criterio de EXIT: `current_pcs < pcs_min_entry AND current_streak_weeks <= 1`, OR `current_rot_score <= 2`, OR `current_pcs < 62` (suelo absoluto — por debajo del min_entry más bajo del sistema, independiente del streak), OR `left_universe=true`
- Campo `left_universe: true` añadido a cada posición cuando el ticker ha caído fuera de los 91 tickers de `ai_candidates.json` (2026-07-02). En ese caso todos los `current_*` son `null` y la HARD_RULE obliga al modelo a hacer EXIT obligatoriamente.
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
