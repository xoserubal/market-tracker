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

## Risk-Off Monitor en Relative Flow Lab (fix 2026-07-03)

`relative.html` ("Relative Flow Lab", herramienta separada de `rotacion.html`, con su propio sistema de régimen de 4 ratios cruzados — Copper/Gold, Credit/Equities, Utilities/Discretionary, Low Vol/Momentum) tenía la caja "Macro Regime" con un bug real: el contador (`regimeScore`) contaba ratios con `signal==="risk-on"`, no `"risk-off"`, así que con 2 de 4 ratios en risk-off la cabecera mostraba "RISK-OFF (0/4)" — no cuadraba con la tabla.

Renombrado a **Risk-Off Monitor** (no confundir con el régimen de MacroScore v2 de `rotacion.html`/backtest — sistemas completamente distintos). `riskOffCount` ahora cuenta `signal==="risk-off"` correctamente. 5 estados: `0/4→Risk-On/No Warning`, `1/4→Mild Defensive Warning`, `2/4→Mixed/Defensive Rotation Warning`, `3/4→Risk-Off Warning`, `4/4→Confirmed Risk-Off`. Aplicado en el render y en `copyMarkdown`.

---

## Cluster "SECTOR ROTATION" en Relative Flow Lab (implementado 2026-07-17)

Motivación: el usuario señaló que el cluster `COAL / MATERIALS` (Warrior Met/Peabody/Alpha Met — subsector muy nicho) no le aportaba valor accionable, y preguntó cuál era la mejor forma del sistema para ver de qué sectores sale dinero hoy/estos días y hacia dónde entra (otros sectores, bonos, liquidez). Auditoría: ni `relative.html` ni `rotacion.html` cubrían los 11 sectores GICS/SPDR completos como grupo autocontenido — `relative.html` tenía sub-temas dispersos (regiones, sub-sectores de energía, metals, uranium, coal) sin Technology/XLK, Healthcare/XLV, Industrials/XLI, Real Estate/XLRE ni Communication/XLC en ningún ratio.

**Cambio:** nuevo grupo `SECTOR ROTATION` en `RATIO_GROUPS` (`relative.html`), insertado justo después de `RISK / BREADTH`. 14 pares, todos vs `SPY`: los 11 sector ETFs SPDR (XLK, XLF, XLV, XLY, XLP, XLE, XLI, XLB, XLRE, XLC, XLU) más 3 destinos alternativos cuando el dinero sale de acciones — `TLT` (bonos largo plazo), `GLD` (oro), `BIL` (cash proxy, T-Bills). No se creó infraestructura nueva: reutiliza el pipeline `buildRow`/`classify`/`flowChange` ya existente — el ranking "Top 5 Flow Change" (aceleración 5D vs 5D previo) filtrado a este cluster **es** el listado diario de entradas/salidas sectoriales que se pedía, sin métrica nueva que mantener.

**Decisión de diseño:** no se tocó ni se quitó el cluster `COAL / MATERIALS` — 4 filas no penalizan el rendimiento ni saturan la tabla, y el usuario no pidió eliminarlo explícitamente, solo dejó de ser la herramienta principal para lectura de flujos sectoriales. Se aceptó duplicar `Financials vs Market` (XLF/SPY) entre este cluster nuevo y el cluster `FINANCIALS` existente (que lo usa junto a `Regional vs Large Banks`, con un propósito distinto — salud del sistema bancario, no rotación sectorial) en vez de reestructurar clusters existentes, para mantener el cambio acotado a lo pedido.

**Verificado:** `/api/history/:symbol` de `server.js` es genérico (sin whitelist) — confirmado en vivo contra Yahoo para los 6 tickers nuevos que no se usaban ya en otros clusters (XLK, XLV, XLI, XLRE, XLC, BIL, TLT). `relative.html` servido por el proceso local de `server.js` confirma el cluster renderizado.

---

## Koncorde "espejo" — patrón de giro por reversión (implementado 2026-07-03)

Nuevo indicador de seguimiento (no HARD_RULE, no en el payload IA todavía — fase de observación, mismo enfoque que `extension_risk`/`konc_alignment`). Detecta un patrón específico: activo sobrevendido con blue y green ambos negativos que de repente gira — blue cruza a positivo mientras green sigue negativo — simultáneamente en D y 3D (confirma que no es ruido de un día), con W (blue) todavía negativo (la tendencia semanal de fondo no ha girado, lo que sugiere que puede ser el inicio de una mini-tendencia, no solo un rebote de un día).

**Campos nuevos** (`scripts/koncorde_calculator.py`):
- `konc_{d,3d,w}_blue_cross_up`: bool — `blue[-1] >= 0 and blue[-2] < 0` (cruce fresco en la última vela).
- `konc_mirror_signal`: `"mirror_reversal_confirmed"` (cruce fresco en D **y** 3D + green<0 en ambos + W blue<0) | `"mirror_reversal_daily_only"` (solo D, 3D aún no confirma) | `"none"`.

**Decisión de diseño:** se exige cruce fresco en D **y** 3D simultáneamente para el nivel "confirmed" (más estricto que solo exigir que 3D ya esté en estado accumulation) — dado que las velas 3D se actualizan cada 3 sesiones, esto hace que "confirmed" sea intencionalmente más raro que "daily_only" (verificado con datos reales del universo completo 2026-07-03: 3 tickers en `daily_only`, 0 en `confirmed`, de 194).

**Seguimiento — `docs/data/mirror_signals.jsonl` (nuevo):** cada vez que `koncorde_calculator.py` corre, registra TODOS los tickers del universo (no solo picks de la IA) que muestren `mirror_reversal_confirmed`, con precio y valores blue/green/bar_date, para evaluar más adelante si el patrón anticipa subidas. Deduplicado por `(ticker, date)`. `ret_1w`/`ret_2w`/`ret_1m` quedan en `null` — rellenarlos requeriría un script de seguimiento propio al estilo `update_performance.py`, no incluido en este cambio.

**Dashboard:** badge "🪞 Confirmado" / "🪞 Solo D" en `portfolio.html`, en dos sitios: junto al ticker en la tabla principal de posiciones por sección (donde se revisa cada posición día a día) y en el widget secundario "Ranking de Setups" (ordenado por Early Flow). El primer intento solo lo puso en el widget secundario, lo que lo hacía casi invisible — corregido el mismo día tras detectarlo el usuario.

**Caso real que motivó esto (2026-07-02):** MSTR mostraba `konc_d_state=accumulation` (blue +8.9, green -10.1), `konc_3d_state=accumulation` (blue +17.1, green -34.7), `konc_w_state=down` (blue -1.1) — el patrón exacto — mientras Flow Score (-1.7, "Débil") y Early Flow Score (0.5, "Sin setup") no lo destacaban en absoluto, porque esas dos métricas están calibradas para detectar acumulación silenciosa y temprana, no rebotes en V tras una paliza. Un día después (2026-07-03) el patrón ya se había resuelto al alza (W pasó a positivo, D pasó a estado "up" con green también positivo) — confirma que la ventana de esta señal es corta por naturaleza.

---

## Cartera MIRROR_ESPEJO — gestionada exclusivamente por Grok (implementado 2026-07-03)

Cartera experimental nueva, con una arquitectura deliberadamente distinta al resto del sistema: **no usa PCS, rot_score, DEMS ni ninguna otra métrica** — solo entra en tickers que muestren la señal Koncorde "espejo" (ver sección anterior), y su salida es 100% mecánica (no pasa por la IA).

**Script nuevo: `scripts/mirror_portfolio.py`** (Step 9d del pipeline, `continue-on-error: true` — si falla no bloquea el resto):

- **Entrada — llamada dedicada a Grok** (`x-ai/grok-4.3`, fijo, independiente de `ACTIVE_MODEL`): un prompt propio, separado por completo del payload multi-cartera de `paper_trading.py` — sin las 14 `HARD_RULES` existentes, sin PCS. Recibe los tickers en `mirror_reversal_confirmed` **y también `mirror_reversal_daily_only`** de **todo el universo Koncorde** (~194 tickers, no solo los candidatos PCS-elegibles de `ai_candidates.json`) que no estén ya en cartera, con su nivel de confirmación (`signal`) y sus valores blue/green/trend D/3D/W. Decisión 2026-07-03: se amplió a incluir `daily_only` (inicialmente solo se consideraba `confirmed`) para no perderse señales tempranas como la de VAL ese mismo día — el prompt explica la diferencia de fiabilidad entre ambos niveles para que Grok pueda ponderarlo. Grok decide si el giro parece creíble o no; puede seleccionar 0 o más. Cada posición guarda `entry_signal` con el nivel real (`confirmed` o `daily_only`) con el que entró.
- **Salida — trailing stop mecánico, sin IA**: cada run, para cada posición abierta, se actualiza `high_water_mark = max(high_water_mark, cierre_de_hoy)`. Si `cierre_de_hoy <= high_water_mark × 0.95`, se cierra automáticamente (`close_reason: "trailing_stop_5pct_from_high"`). Esto se evalúa **antes** de considerar nuevas entradas, y siempre se aplica (no depende de `--apply`, ver más abajo — la salida mecánica es segura por diseño, no cuesta ni una llamada a la IA).
- **Tamaño:** 5% fijo por posición. **Sin límite de posiciones simultáneas** (decisión explícita del usuario — universo pequeño y señal ya de por sí restrictiva).
- **Uso manual:** `py -3 scripts/mirror_portfolio.py` (dry-run: muestra candidatos, no llama a Grok ni escribe nada) · `py -3 scripts/mirror_portfolio.py --apply` (llama a Grok de verdad y aplica cambios — gasta crédito de la API).
- **Logs:** `docs/data/mirror_portfolio_log.jsonl` (coste, tokens, latencia, respuesta cruda por llamada) — versión ligera del `ai_model_test_summary.jsonl` del sistema principal, sin el quality-scoring completo (no aplica aquí, no hay HARD_RULES que violar).
- **Reutiliza** `call_model`/`parse_response`/`compute_cost`/`_model_max_tokens` de `paper_trading.py` (import directo) en vez de duplicar la lógica de llamada a OpenRouter.
- **Telegram:** `MIRROR_ESPEJO: "Espejo (Grok)"` añadido a `_PORTFOLIO_LABELS` en `paper_trading.py` y `notify_telegram.py` — las notificaciones de apertura/cierre ya genéricas del sistema deberían recogerlo sin cambios adicionales (no verificado en producción todavía).

**Verificado (sin gastar API real):** lógica de trailing stop probada con 4 casos (cierre por debajo del stop, nuevo máximo sin cierre, sin dato de precio hoy, cartera vacía/bootstrap) y flujo completo de aplicación de una selección probado con `call_model` mockeado. `build_candidates()` corrido contra datos reales del universo (0 candidatos el día de implementación, esperado — ver sección anterior).

**Pendiente / no incluido en este cambio:** confirmar en producción que las notificaciones de Telegram sí recogen esta cartera nueva sin tocar `notify_telegram.py`/`_notify_changes` más allá del label; el primer `--apply` real (con coste de API) queda para cuando el usuario lo dispare.

---

## Página Sentiment — Fear & Greed (CNN) + link a Finviz Heatmap (implementado 2026-07-06)

Nueva página `sentiment.html` (raíz del repo, servida por `server.js` como el resto de dashboards — `portfolio.html`, `relative.html`, `cycle.html`, `rotacion.html`). Fase puramente visual, sin señal ni hard rule todavía — mismo enfoque que `extension_risk`/Koncorde en su día: observar primero.

**Por qué no iframe:** se evaluó embeber directamente `edition.cnn.com/markets/fear-and-greed` y `finviz.com/map`, pero ambos bloquean el embebido — CNN vía CSP `frame-ancestors` (solo dominios `*.cnn.com`/`*.turner.com`), Finviz vía `X-Frame-Options: SAMEORIGIN`. Además el mapa de Finviz ya no es una imagen estática con query params (`mapimg.ashx?...`) sino una app que renderiza el treemap en cliente (SVG/Canvas vía bundles JS) — no hay forma de replicar su selector de universos (S&P 500, Russell, All Stocks...) sin reconstruir el treemap desde cero (constituyentes por índice + precios de miles de tickers). Decisión: para Finviz, solo un botón de salida (`https://finviz.com/map`, `target="_blank"`) — el selector de universos se usa directamente en su web, no en la nuestra.

**Fear & Greed sí se replica en casa**, porque el endpoint que alimenta la página de CNN es JSON abierto (`production.dataviz.cnn.io/index/fearandgreed/graphdata`, `Access-Control-Allow-Origin: *`) y trae exactamente lo que se ve en la web de CNN: el índice compuesto + histórico de ~1 año + los 7 subcomponentes reales (`market_momentum_sp500`, `stock_price_strength`, `stock_price_breadth`, `put_call_options`, `market_volatility_vix`, `junk_bond_demand`, `safe_haven_demand`), cada uno con su propio score 0-100, rating y serie histórica.

**Proxy server-side, no fetch directo desde el navegador** (`server.js`, nueva ruta `/api/fear-greed`): aunque el endpoint de CNN tiene CORS abierto y en teoría el navegador podría llamarlo directo, sin el header `Referer` correcto CNN devuelve `418 "I'm a teapot. You're a bot."` de forma intermitente (bot-detection, no consistente — en las pruebas a veces respondía 200 incluso sin Referer). Proxyearlo evita que esa flakiness dependa del navegador de cada visita y cachea 15 min (mismo patrón que el cache de FRED ya existente en `server.js`), con fallback a la última respuesta cacheada si CNN falla (`stale-but-served`).

**Página** (`sentiment.html`): gauge principal (semicírculo SVG con aguja, 5 tramos de color — reutiliza la paleta de estado ya usada en todo el resto de la app: `#ffcdd2/#b71c1c` extremo-miedo, `#ffe0b2/#bf360c` miedo, `#fff9c4/#e65100` neutral, `#dcedc8/#33691e` codicia, `#c8e6c9/#1b5e20` codicia extrema — la misma que `STATUS`/`FLOW_STYLE` en `index.html`, no una paleta nueva) + 4 comparativas (cierre anterior, 1 semana, 1 mes, 1 año) + sparkline del último año. Debajo, grid de 7 tarjetas de subcomponentes, cada una con su propio mini-gauge + sparkline de la serie histórica cruda (últimas 90 sesiones). Boundaries del gauge (0-25 miedo extremo, 25-45 miedo, 45-55 neutral, 55-75 codicia, 75-100 codicia extrema) son la clasificación estándar de CNN.

**Nav:** pill "Sentiment" (`#00695c`) añadida a las 5 páginas raíz (`index.html`, `portfolio.html`, `relative.html`, `cycle.html`, `rotacion.html`), mismo patrón visual que el resto (sin componente compartido — cada página repite su propia barra, como ya ocurre con el resto de páginas del sistema).

**Verificado:** JSX transpilado con `@babel/core` sin errores de sintaxis; `/api/fear-greed` probado end-to-end contra CNN real (datos correctos, cache funcionando); captura de pantalla vía Playwright (Edge del sistema, headless) confirma render correcto de gauges/agujas/sparklines y cero errores de consola, tanto en `sentiment.html` como en la barra de navegación de las otras 5 páginas tras el cambio.

**Pendiente / fuera de alcance:** no hay heatmap propio del universo interno (91 tickers de `ai_candidates.json` agrupados por `subtheme`) — se descartó por ahora, solo se pidió el link de salida a Finviz. Extraer una señal cuantitativa del Fear & Greed (para PCS, rot_score o HARD_RULES) queda para cuando haya datos suficientes para justificarlo, mismo criterio que el resto de features en fase de observación.

---

## Duration Stress Monitor — BOJ/Treasury Supply Thesis (implementado 2026-07-07)

Nueva página `duration.html` para vigilar una tesis de trade discrecional (posible venta/reducción japonesa de Treasuries ejerciendo presión bajista sobre la duración larga USA), surgida de un análisis externo sobre los datos de este mismo tracker. Panel puramente observacional — no toca PCS, rot_score ni `HARD_RULES` del motor de picks, mismo enfoque que `sentiment.html` en su día.

**Decisión de framing:** el título y la estructura NO asumen que la causa es japonesa — la atribución a Japón es una hipótesis, no un hecho confirmable con datos públicos. Por eso la página separa en 3 secciones visuales:
1. **Market Confirmation** (objetivo): TLT (precio + Koncorde vía datos ya existentes), yields 10Y/2Y/30Y (FRED `DGS10/DGS2/DGS30`, pedidos en vivo — no están en `series.yaml`, no hace falta añadirlos ahí), spreads derivados 30Y-10Y y 10Y-2Y, `DFII10`, `T5YIE`, HY spread (`BAMLH0A0HYM2`), VIX, MOVE (`^MOVE`, con fallback elegante si Yahoo no lo sirve), ratios TLT/IEF y EDV/IEF, y tabla de TBT/IEF/EDV/ZROZ.
2. **Japan/Causality Evidence** (contextual, ambiguo): USDJPY con badge de ambigüedad direccional (yields↑+TLT↓+USDJPY↓ = repatriación/intervención limpia; DXY↑+USDJPY↑ = shock de yields/dólar genérico, no confirma story Japón), oro como cross-check crisis-de-confianza-vs-tipos-reales. Nota explícita: JGB 10Y/30Y y Japan CDS no están disponibles (sin fuente diaria gratuita fiable) — hueco documentado, no cubierto.
3. **Auction Stress**: subastas del Tesoro (Treasury Fiscal Data API, `api.fiscaldata.treasury.gov`), 10Y/30Y priorizadas sobre 2Y. **El endpoint no publica yield when-issued**, verificado contra la API real — no se puede calcular el tail auténtico (`high_yield - WI_yield`). Se muestra en su lugar `auction_high_yield`, `bid_to_cover`, comparativas vs media de las últimas 8 subastas del mismo tenor, y `auction_stress_proxy` (weak_demand/strong_demand/normal), dejando `true_tail_bps: null` explícito en vez de inventar o mal-etiquetar el proxy como tail real.

**Arquitectura — sin tocar el pipeline de backtest:** `duration.html` sigue el patrón de `sentiment.html`/`relative.html` (fetch en vivo desde el navegador, no lee `docs/data/*.json`). Casi todo el dato ya era servible por proxies genéricos existentes: `/api/quote/:symbol` (TLT, TBT, IEF, EDV, ZROZ, GC=F, DX-Y.NYB, JPY=X, ^VIX, ^MOVE) y `/api/fred/:series` (yields, HY spread). Solo se añadió una ruta nueva, `/api/treasury-auctions` en `server.js` (mismo patrón caché+stale-fallback que `/api/fear-greed`, TTL 6h ya que las subastas no son intradía). También se añadió el campo `asOf` (timestamp del último dato) a `/api/quote/:symbol`, necesario para mostrar freshness real en vez de solo la hora de fetch del navegador.

**State machine A/B/C/D** (recalculada cada carga, sin histéresis en v1 — se añadirá si en producción resulta "flappy"), evaluada en este orden por seguridad (invalidation primero, para que una reversión clara nunca quede enmascarada por una confirmación de contexto obsoleta):
```
core_break   = (10Y > 4.60%) AND (TLT < 84)
confirmation = (hy_spread_bps > 300) OR (VIX > 20) OR (MOVE > 120, umbral provisional sin baseline propio todavía)
invalidation = (TLT > 86.5) AND (10Y < 4.55%)
pressure     = (TLT < 84.8) OR (10Y > 4.55%)

if invalidation:                  Fase D — Invalidation
elif core_break AND confirmation: Fase C — Systemic Confirmation
elif pressure:                    Fase B — Duration Pressure
else:                             Fase A — Watch
```
`hy_spread_bps = BAMLH0A0HYM2 * 100` — FRED devuelve esta serie en puntos porcentuales, no en bps; normalización aplicada tanto en `duration.html` (JS) como en `duration_monitor.py` (Python). Los niveles trigger están **duplicados a propósito** en ambos archivos (mismo precedente que `calcCMF` duplicado en `server.js`/Python) — mantener sincronizados si cambian.

**Script nuevo: `scripts/duration_monitor.py`** (Step 9e del pipeline, `continue-on-error: true`): obtiene TLT/VIX/MOVE vía yfinance y DGS10/HY spread vía FRED API directa (sin pasar por el paquete `backtest/src`), calcula la misma state machine, y alerta por Telegram solo cuando hay algo nuevo:
- **Transición de fase** (cualquier dirección) — siempre, salvo en el bootstrap.
- **Triggers críticos individuales** (`core_break_10y`, `core_break_tlt`, `invalidation_tlt`, `invalidation_10y`) — deduplicados por `condition_id + dirección de cruce + fecha` en `docs/data/duration_monitor_state.json`, así que una condición que sigue activa en la misma dirección no re-alerta en cada run (pipeline 2×/día). Las métricas de contexto (VIX/HY/MOVE individuales, USDJPY, oro) nunca alertan por sí solas, solo alimentan `confirmation`.
- **`--alert-on-initial`**: en el primer run (sin state file previo) no se alerta nada por defecto, solo se guarda el baseline — evita que el bootstrap dispare una "sorpresa" sobre condiciones que ya eran ciertas antes de que existiera el monitor. Con el flag, sí alerta las condiciones ya activas.
- **`--dry-run`**: imprime en vez de enviar Telegram y no persiste el state file.
- Auctions **no** alimenta la state machine ni las alertas en v1 — es puramente informativo en `duration.html`, ningún trigger crítico depende de ello (mantiene el script de alertas simple, sin duplicar la lógica de subastas en Python).

**Nav:** pill "Duration" (`#37474f`) añadida a las 6 páginas raíz (`index.html`, `portfolio.html`, `relative.html`, `cycle.html`, `rotacion.html`, `sentiment.html`).

**Export a LLM** (añadido 2026-07-07, mismo día): `duration.html` sigue el patrón `buildXMarkdown()` + caché en `localStorage` (`llm_export_duration`/`_ts`) + botón "Copy for LLM" + botón "🗂️ Exportar TODO a LLM" ya usado en `index.html`/`portfolio.html`/`relative.html`/`rotacion.html`/`cycle.html`. Esas 5 páginas se actualizaron para incluir `Duration` en su lista de `parts` del bundle cruzado, y el contador "X/N pestañas" pasó de estar hardcoded a `${parts.length}` en las 6 páginas (evita que se desincronice si se añade una séptima página). `sentiment.html` sigue sin este patrón (nunca lo tuvo, fuera de alcance).

**Sparklines y Trade Structure Playbook** (añadido 2026-07-07, mismo día, a petición del usuario tras ver la v1 — "hago en falta algún sparkline y hacerlo más accionable"):
- Nueva fila "Tendencia — últimos ~6 meses" en la sección Market Confirmation con sparkline de los 4 drivers que alimentan la state machine: TLT y VIX (vía `/api/history/:symbol`, ya genérico, sin cambios en server.js), 10Y yield y HY spread (vía un campo `history` nuevo añadido a la respuesta de `/api/fred/:series` en `server.js` — últimas ~90 observaciones en orden ascendente, reutilizando el mismo fetch/caché ya existente, sin ruta nueva).
- Nueva caja "Trade Structure — TLT Options Playbook" justo debajo del badge de fase: texto fijo por fase (decisión del usuario: playbook fijo, **no** calcula strikes/vencimientos en vivo a partir del precio/ATR actual) que traduce la fase A/B/C/D en la estructura de opciones ya acordada en el análisis original (put spread TLT pequeño en A, añadir TBT/más delta en B, hedge de equities en C, cerrar/reducir en D).
- **Aviso importante de nomenclatura:** las fases A-D de *esta* state machine (A=Watch, D=Invalidation) **no son el mismo eje** que las fases A-D del análisis externo original que motivó esta página (donde la D era "confirmación Japón/yen", una escalada adicional, no una invalidación). El playbook se escribió usando la semántica de *esta* state machine, no una copia literal de las letras del análisis original — comentario dejado en el código (`duration.html`) para que no se reintroduzca la confusión en el futuro.

**Verificado:** sintaxis de `server.js`/`duration_monitor.py` válida; llamada real a la API de Fiscal Data confirma los campos disponibles (`high_yield`, `bid_to_cover_ratio`, sin WI yield) y que algunos registros traen `high_yield: "null"` (string, no JSON null) — manejado explícitamente. `duration_monitor.py --dry-run` corrido contra datos reales de hoy (TLT≈84.8, VIX≈16.3, MOVE≈65, 10Y≈4.49%, HY≈272bps → Fase A, como se esperaba). Bootstrap real ejecutado (sin alertas, state file creado) y una segunda ejecución inmediata confirma dedup (cero mensajes). Lógica de transición de fase y dedup por dirección de cruce verificada además con datos sintéticos en aislamiento (A→C→D, cruces detectados con la dirección correcta, tercera llamada idéntica no genera mensajes). Se corrigió además un bug real detectado en esta verificación: los emojis en los mensajes de alerta rompían `print()` en consola Windows (cp1252) — arreglado forzando stdout/stderr a UTF-8 con `errors="replace"` al inicio del script (GitHub Actions ya usa UTF-8 por defecto, así que solo afectaba a pruebas locales, pero debía arreglarse igualmente). Añadidos posteriormente los sparklines/playbook/export-a-LLM verificados igual vía captura de pantalla en Edge headless (sin errores de consola) contra el servidor local real, incluyendo confirmación de que el nuevo campo `history` de `/api/fred/:series` devuelve 90 observaciones reales en orden ascendente.

**Pendiente / fuera de alcance:** JGB 10Y/30Y diario y Japan CDS (sin fuente gratuita fiable); confirmar en producción que `/api/treasury-auctions` sigue respondiendo con el filtro/paginación usados tras cambios futuros de la API; sin histéresis de fase (si resulta demasiado sensible a ruido de un día, se añadirá después); el umbral de MOVE (120) es provisional, sin baseline histórico propio todavía.

### Fix: datos obsoletos sin avisar + TIPS mezclados en Auction Stress (2026-07-27)

El usuario reportó que algunos indicadores en `duration.html` mostraban fechas de "hace una semana". Investigación en vivo reveló dos causas distintas, no una:

**1. `^MOVE` obsoleto de verdad (causa principal del reporte).** Yahoo Finance dejó de publicar closes para `^MOVE` durante 5 sesiones seguidas (`close: null` del 2026-07-20 al 2026-07-24, confirmado contra la API de Yahoo en vivo) sin devolver error — el proxy `/api/quote/:symbol` recorta correctamente los `null` finales, así que sirve el último valor real (2026-07-17) pero sin ninguna marca de que tiene 9-10 días de antigüedad. El dashboard lo mostraba igual que un dato del día. Es un problema de la fuente (ya documentado como riesgo conocido: "MOVE, con fallback elegante si Yahoo no lo sirve"), pero el fallback existente solo cubría ausencia total de datos, no un dato presente pero obsoleto.

**Fix — indicador de staleness genérico (`duration.html`):** nueva función `staleInfo(dateStr, thresholdDays)` (umbral 4 días para quotes de Yahoo, 5 para series FRED — más laxo porque el lag de ~1 día + fin de semana ya es esperado). El componente `Stat` acepta ahora `staleDays` y, cuando está presente, añade un borde punteado naranja, un ⚠️ junto a la etiqueta (con tooltip) y una línea "obsoleto · Nd". Aplicado a los 9 indicadores con fecha propia (TLT, 10Y/2Y/30Y, DFII10, T5YIE, HY Spread, VIX, MOVE). El export a markdown (`buildDurationMarkdown`, usado por "Copy for LLM" y el bundle cruzado) también añade `⚠OBSOLETO(Nd)` en la columna "As of" — necesario porque ese texto se pega directamente a un LLM externo, que no vería el estilo visual de la página.

**2. Bug real en `/api/treasury-auctions`: TIPS mezclados con nominales (`server.js`).** El filtro `security_term:in:(2-Year,10-Year,30-Year)` de la API de Fiscal Data no distingue bonos nominales de TIPS del mismo plazo — el campo `security_type` dice `"Bond"`/`"Note"` para ambos por igual; el campo real que distingue es `inflation_index_security` (`"Yes"`/`"No"`), que no se estaba pidiendo. Resultado verificado en producción: la "última subasta 10-Year" mostrada era en realidad una 10-Year TIPS del 2026-07-23 (yield real 2.44%, `series: "TIPS of..."` confirmado consultando el CUSIP completo) en vez de la Note nominal real más reciente (2026-05-12, yield 4.47%) — un desajuste de ~2 puntos porcentuales que además corrompía `high_yield_vs_recent_avg` y `auction_stress_proxy` cada vez que una TIPS caía dentro de la ventana de 8 subastas recientes. Mismo problema en 30-Year (confirmado: fila de 2026-02-19 con yield 2.47% era en realidad TIPS "of February 2056").

**Fix:** añadido `inflation_index_security` a los `fields` pedidos y filtro `.filter(row => row.inflation_index_security !== "Yes")` antes de construir los buckets por tenor. La fecha de la última subasta 30-Year nominal (2026-05-13) en sí **no era el bug** — es correcta según el calendario trimestral real de esa serie de datos (próxima esperada ~agosto), simplemente coincidía en el tiempo con el bug de TIPS y contribuía a la sensación de "todo desactualizado".

**Verificado:** llamada directa a Fiscal Data API confirmó el campo `inflation_index_security` y el mislabeling vía CUSIP completo antes de tocar código. Tras el fix, reinicio de `server.js` (proceso persistente — ver [[project_dev_server_persistent]]) y comparación antes/después de `/api/treasury-auctions`: 10-Year pasó de yield 2.438%/`auction_date=2026-07-23` a 4.468%/`2026-05-12` (consistente con DGS10≈4.71% de FRED). Captura de pantalla en Edge headless de `duration.html` contra el servidor local real confirma: badge "⚠ MOVE obsoleto · 9d" visible con borde punteado, tabla de Auction Stress con yields nominales plausibles en las 3 filas, cero errores de consola.

### MOVE proxy de respaldo — volatilidad realizada de TLT calibrada contra 5y de histórico (2026-07-27)

Tras el fix de staleness de arriba, el usuario pidió una fuente alternativa para cuando Yahoo deja de servir `^MOVE` (no solo un aviso, un respaldo funcional). Investigado antes de implementar: FRED no tiene el MOVE ni equivalente (`VXTYN`/TYVIX, el único parecido, está discontinuado por Cboe desde 2020); Stooq ahora exige un challenge JS anti-bot no viable server-side; el MOVE real es un índice propietario de ICE sin fuente gratuita fiable. Alternativa elegida: estimar un "MOVE equivalente" a partir de la volatilidad **realizada** de TLT (no implícita — ojo, no es lo mismo, ver caveat abajo), dato que ya se descarga siempre vía `/api/history/TLT`.

**Calibración (no a ojo):** descargados 5 años de histórico diario TLT y `^MOVE` directo de Yahoo, 1219 sesiones solapadas reales (excluyendo huecos conocidos de `^MOVE`). Se probaron ventanas de volatilidad realizada de 5 a 60 sesiones — r² sube con la ventana (5d→0.28, 20d→0.51, 60d→0.60) pero una ventana larga reacciona más lento a un shock, justo lo contrario de lo que necesita un monitor de alerta temprana. Se eligió **20 sesiones** (mismo horizonte que `SMA20`/`dist_sma20_atr` ya usado en el resto del proyecto, trade-off aceptado entre ajuste y velocidad de reacción) sobre la regresión lineal `MOVE_est = 43.96 + 3.876 × TLT_rvol20` (`TLT_rvol20` = stdev anualizada % de retornos log de TLT a 20 sesiones), r²=0.51, residual stdev=16.9 puntos MOVE. Correlación moderada, no un sustituto exacto — MOVE es volatilidad implícita de opciones sobre futuros de bonos, esto es volatilidad realizada de precio; por eso se muestra siempre como rango (±1 residual stdev), nunca como número puntual.

**Implementación (`duration.html`, todo client-side, sin fetch nuevo):** constante `MOVE_PROXY` con los coeficientes calibrados arriba (comentario en el código deja explícito de dónde salen, para no perder la trazabilidad si se recalibra más adelante) + `calcRealizedVol()`/`moveProxyFromTlt()`, calculados sobre `histories['TLT'].series` (ya se pedía para el sparkline de TLT, 6 meses de histórico, de sobra para una ventana de 20 sesiones).

- Se activa (`moveIsProxy`) solo cuando el MOVE real está ausente **o** marcado obsoleto por `staleQuote` — nunca sustituye a un dato real y fresco.
- **Sí alimenta la state machine A/B/C/D**: `moveEffective` (proxy si falta el real, dato real si no) reemplaza a `move?.price` en el `confirmation` check de `computePhase` — es un respaldo funcional, no solo decorativo, tal como se pidió. Reutiliza los mismos umbrales `LEVELS.confirmMove=120`/100 que el MOVE real porque la regresión ya está calibrada a esa misma escala.
- **Nunca silencioso:** tarjeta nueva "MOVE proxy (TLT rvol20)" en el grid (con rango y r², solo visible si `moveIsProxy`), nota explícita dentro de la caja de fase cuando el proxy participa en el check de confirmación, y línea equivalente en el export a markdown (`buildDurationMarkdown`) — para que si esto se pega en un LLM externo, quede claro que ese MOVE no es el dato real.

**Verificado:** con el `^MOVE` real todavía obsoleto (10d) al momento de la implementación, captura de pantalla en Edge headless confirma la tarjeta proxy mostrando `~73 (rango 56–90 · r²=0.51)`, coherente con Fase B (VIX 18.6, HY 277bps, proxy 73 — ninguno supera su umbral de confirmación, checkbox "Confirmación estrés" correctamente sin marcar), aviso de proxy visible en la caja de fase, cero errores de consola.

**Fuera de alcance:** no se implementó ningún fallback automático de fuente de datos (Stooq, proveedores de pago) — descartado por fragilidad/coste, ver arriba. Recalibración periódica no automatizada — si en el futuro se sospecha que la relación TLT-vol-realizada/MOVE se ha desplazado, repetir el proceso de arriba a mano.

---

## Export a LLM de Sentiment (implementado 2026-07-28)

`sentiment.html` se quedó fuera del patrón `buildXMarkdown()` + `localStorage` (`llm_export_*`/`_ts`) + botones "Copy for LLM"/"🗂️ Exportar TODO a LLM" cuando se creó (2026-07-06) — quedó documentado como "fuera de alcance". El usuario lo pidió explícitamente el 2026-07-28 tras notar que el bundle cruzado no incluía Sentiment.

Añadido `buildSentimentMarkdown()` (score actual + 4 comparativas temporales + tabla de los 7 subcomponentes, con el mismo rating textual que ya usa el gauge) más el mismo `useEffect`/`copyMarkdown`/`copyAllForLLM`/toast que las otras 6 páginas. Sumada la entrada `{ key: 'llm_export_sentiment', label: 'Sentiment' }` al array `parts` de `index.html`, `portfolio.html`, `relative.html`, `rotacion.html`, `cycle.html` y `duration.html` (las 6 páginas comparten el mismo array literal, ahora con 7 entradas en las 7 páginas).

**Verificado** (Playwright, Edge headless contra el servidor local real): `localStorage.llm_export_sentiment`/`_ts` se pueblan solos al cargar la página, sin pulsar nada; "Copy for LLM" en `sentiment.html` copia el markdown correcto; "Exportar TODO a LLM" en `index.html` incluye la sección de Sentiment en el bundle combinado; cero errores de consola nuevos.

---

## Fix del veto absoluto de `konc_alignment` + Koncorde Research Log (implementado 2026-07-21)

**Origen — retrospectiva TNZ.TO (2026-07-17):** TNZ.TO llevaba ~2 semanas acumulando en Koncorde diario (blue subiendo casi monótono) y W había girado alcista, pero justo el día en que el precio "despegó" (2026-07-16), `konc_alignment` pasó de `bullish_aligned` a `distribution_warning` — la etiqueta más alarmante. Causa raíz: `_konc_alignment()` daba **veto absoluto** a un único `state_3d == "distribution"` (o a `blue_down_2_bars_3d`), sin importar lo que dijeran D y W. El 3D es una vela no solapada de 3 sesiones, así que en fases de acumulación de varias semanas es más sensible a dónde cae el corte de la vela que a la tendencia real — en TNZ.TO osciló distribution↔up 5 veces en 10 sesiones. Verificado en producción el 2026-07-21 contra el snapshot de `koncorde_data.json` del día anterior: **138/197 tickers (70%) del universo mostraban `distribution_warning`**, 87 por `state_3d == "distribution"`, y **13 con D y W ambos alcistas** (el patrón exacto de TNZ.TO) — no era un caso aislado.

Se pasó el diagnóstico a un asesor externo (vía `force_analyze.py --audit` / copy-paste manual) para una segunda opinión antes de tocar código. Confirmó el diagnóstico y propuso una cascada revisada + un log de investigación; se adoptó con recorte deliberado del alcance (ver "Fuera de alcance" abajo) — mismo criterio que el resto del proyecto: no añadir señales operativas nuevas sobre un único caso.

### 1. `_konc_alignment()` — ya no es un veto absoluto (`scripts/koncorde_calculator.py`)

Firma nueva: recibe también `state_d` (antes solo `state_3d`/`state_w`/`blue_down_2_bars_3d`). Nuevo estado **`bullish_pending_3d_confirmation`**: si D y W están ambos en `up`/`accumulation` y 3D lee `distribution` (o `blue_down_2_bars_3d`) **sin corroboración de otro timeframe**, ya no salta a `distribution_warning` — se degrada a esta etiqueta intermedia. `distribution_warning` ahora exige que la lectura débil de 3D esté corroborada por D o W también en estado bajista (`distribution`/`down`).

Orden de evaluación = prioridad, documentado como una sola cascada if/elif en el docstring de la función (no una lista de prioridad en prosa separada del código — ese desajuste apareció en el primer borrador del asesor externo y se corrigió antes de implementar, para que prioridad declarada y orden real de evaluación no puedan desincronizarse).

**Verificado:** 12 casos unitarios sintéticos (incluye los cruces D bearish/W bullish, blue_down_2_bars solo, W ausente → neutral) + 8 tickers reales con el patrón exacto de hoy (`ARGT`, `DHR`, `DNN`, `EEM`, `EXH8.DE`, `FXI`, `IWM`, `KWEB`) descargados en vivo — todos los que tenían D+W bullish con 3D débil sin corroborar pasan correctamente a `bullish_pending_3d_confirmation` en vez de `distribution_warning`. `TNZ.TO` en vivo (2026-07-21) muestra hoy D=up/3D=up/W=distribution con `blue_down_2_bars_3d=true` → `distribution_warning` correctamente mantenido (la corroboración de W sí está presente) — confirma que el fix no eliminó el warning real, solo el falso positivo por 3D aislado.

Actualizado también el texto de guía al modelo IA en `paper_trading.py` (sección `OBSERVATION FIELDS`) para explicar el nuevo estado y su severidad relativa a `distribution_warning`.

### 2. Koncorde Research Log (`docs/data/koncorde_signals_history.jsonl`, nuevo)

Una fila diaria por ticker, para **todo el universo Koncorde** (no solo los candidatos PCS), con `konc_d/3d/w_state`, `konc_alignment`, `konc_mirror_signal`, y 8 "ingredientes" objetivos para estudiar más adelante el patrón de acumulación escalonada tipo TNZ.TO — todos calculados en `scripts/koncorde_calculator.py` a partir del OHLCV diario que ya se descarga por ticker (sin llamada extra a yfinance): `konc_d_blue_slope_3/6`, `konc_w_blue_slope`, `konc_d_blue_positive_days_6`, `konc_d_blue_up_count_6`, `volume_vs_20d`, `low_break_20d`, `close_reclaim_3d`, `distance_to_sma20_atr`, `price_range_20d_position`. Deduplicado por `(ticker, date)`, mismo patrón que `mirror_signals.jsonl`. `ret_1w/2w/1m` quedan en `null` (a rellenar por un script de seguimiento futuro, no incluido aquí).

**`distance_to_sma20_atr` se recalcula aquí, no se reutiliza de `pcs_calculator.py`:** el campo ya existía como `dist_sma20_atr` en `pcs_calculator.py`, pero solo para los 128 tickers de `ai_candidates.json` — el universo Koncorde es más amplio (197) y TNZ.TO en concreto nunca estuvo en esos 128, que es justo el gap que motivó esto. Se usa la misma fórmula exacta `(close - SMA20) / ATR14` para no repetir el incidente ya documentado de `calcCMF` duplicado y desincronizado entre JS y Python.

**Deliberadamente fuera de este log — Flow Score / Early Flow Score:** el plan acordado con el asesor pedía loguear también estos dos scores (`shared/flow-score.js`), pero un port fiel necesita retornos relativos a SPY, RSI/MACD de precio y distancia al máximo de 52 semanas — datos que el pipeline Python no calcula para el universo Koncorde completo (solo para los 128 candidatos PCS, vía otro script). Rellenar esos inputs con defaults a cero habría producido valores de Flow Score que no coinciden con lo que muestra el dashboard — inventar el dato es peor que no loguearlo. Queda como seguimiento explícito, no descartado en silencio.

**No se implementaron `accumulation_ramp`/`flush_reclaim`/"Koncorde Radar" como los propuso el asesor originalmente** (señales de WATCH/radar visibles) — recorte deliberado: esas señales están inspiradas en un único caso (TNZ.TO) y el proyecto tiene como principio no añadir complejidad operativa antes de tener datos que la justifiquen (mismo patrón que `extension_risk`/`theme_concentration_risk`/`konc_mirror_signal`, todos lanzados primero como campos observacionales). Los 8 campos "ingrediente" cubren exactamente lo que se necesitaría para construir esas señales más adelante, ya logueados.

### Plan de revisión (4-8 semanas desde 2026-07-21)

Cuando `koncorde_signals_history.jsonl` tenga suficiente histórico con `ret_1w/2w/1m` rellenos: evaluar si alguna combinación de los 8 campos ingrediente (p. ej. `low_break_20d` reciente + `close_reclaim_3d=true` + `konc_d_blue_up_count_6>=4`) predice mejor rendimiento que el ruido. Solo si los datos lo justifican, promover a una señal operativa (`accumulation_ramp`/`flush_reclaim`) visible en dashboard — no antes.

### Fuera de alcance (explícito)

Score continuo (`konc_composite_score`) ponderando D/3D/W — dirección correcta a largo plazo según el asesor, pero no implementado; sigue siendo cascada categórica en v1 del fix. Port de Flow Score/Early Flow Score a Python (ver arriba). Ampliar el gate de ROT.TEMPRANA al universo Koncorde completo (opción C original) — el asesor la revisó a "Koncorde Radar" separado sin tocar `ai_candidates`/ROT.TEMPRANA, y ni siquiera esa versión reducida se implementó todavía, queda para cuando el research log tenga datos.

---

## Cierre del bucle de medición del Koncorde Research Log + magnitud/aceleración (implementado 2026-07-28)

Contexto: el research log (`koncorde_signals_history.jsonl`, ver sección "Fix del veto absoluto…") llevaba desde el 2026-07-21 acumulando ingredientes objetivos por ticker/día pero con `ret_1w/2w/1m` a `null` en el 100% de las filas (1.379 filas, 7 días, 0 etiquetas) — sin las etiquetas de rendimiento el log es infalsable, no se puede saber qué combinación de ingredientes detecta las mejores oportunidades. Este cambio cierra ese bucle y añade las dos primitivas que faltaban para poder estudiar "grandes magnitudes" y "giros bruscos".

### 1. Dos campos nuevos en `_compute_research_fields` (`scripts/koncorde_calculator.py`)

- **`konc_d_blue_z`** — z-score del `blue` diario contra su propia distribución móvil de ~90 barras (`(blue[-1] − mean) / std`, requiere ≥60 valores válidos). El `blue` es un oscilador cuya magnitud cruda no es comparable entre los ~197 tickers del universo; el z-score responde "¿cuánto dinero entra, *para este ticker*, ahora?" de forma comparable. Verificado: SE blue=47.5 → z=2.52 (magnitud alta genuina); NVDA blue=−29.1 → z=−0.74.
- **`konc_d_blue_accel`** — aceleración = `slope_3 − slope_6` (ambas ya son pendientes por-barra, misma escala). accel>0 = el dinero no solo entra, entra acelerando (primitiva de inflexión/giro brusco). Verificado: NVDA slope_3=−0.65, slope_6=+4.29 → accel=−4.93 (blue desacelerando/girando a la baja).

Ambos se loguean crudos en el research log (no gated en ninguna señal/HARD_RULE) — mismo criterio que el resto de ingredientes: primero se etiquetan con rendimiento, luego los datos —no pesos elegidos a mano— deciden si un compuesto magnitud+aceleración predice retornos antes de promoverlo. Es el `konc_composite_score` continuo que el asesor externo marcó como dirección correcta, sembrado como campos observacionales.

### 2. `scripts/update_koncorde_performance.py` (nuevo — Step 10c del pipeline)

Compañero de `update_performance.py` (que etiqueta `shadow_picks.jsonl`), adaptado al research log. Rellena in-place `ret_1w/2w/1m` (5/10/21 sesiones) **y `vs_spy_1w/2w/1m`** (alpha vs SPY — necesario para distinguir "mejor oportunidad" de "subió con el mercado"). Entrada = cierre del primer día hábil ≥ fecha de la fila. Un horizonte queda `null` hasta que madura, así que es seguro correrlo en cada pass del pipeline (rellena cada fila según van pasando sesiones). Flags `--dry-run/--force/--ticker/--report`. `end` de yfinance es exclusivo → se pide `today+1` para incluir la barra de hoy cuando ya cerró. Cableado como Step 10c con `continue-on-error: true` (fallo de yfinance no tumba el pipeline). Plantilla de nulls del log ampliada a los 6 campos `ret_/vs_spy_`.

**Verificado:** campos nuevos calculados contra datos reales (aritmética de accel/z-score cuadra exacto); `compute_row_metrics` cruzado contra cálculo manual (SE entrada 2026-04-01 → ret_1m 4.92% ✓, +21 sesiones = 2026-05-01). En el primer run real no maduró ningún horizonte todavía (log de 5 sesiones, barra de hoy sin cerrar) — esperado; el primer lote de `ret_1w` se rellenará en el siguiente run.

**Plan de revisión** (extiende el de la sección del research log): con 4-8 semanas de `ret_/vs_spy_` rellenos, evaluar si `konc_d_blue_z` alto + `konc_d_blue_accel>0` (± los otros 8 ingredientes) predice mejor rendimiento que el ruido. Solo entonces promover a señal operativa.

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
