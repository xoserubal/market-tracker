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

Calculado en `scripts/pcs_calculator.py`. Informe exhaustivo (fórmulas exactas,
verificación de techos, primera evidencia empírica de poder de ranking) en
`wiki/ASESOR_EXTERNO_PCS_INFORME.md` (2026-08-05) — este resumen es solo el
recordatorio corto.

Componentes — **techo real, no el "0-100" nominal** (verificado 2026-08-05
trazando cada rama del código + confirmado empíricamente contra
`ai_candidates.json`; la tabla anterior de este archivo tenía los techos mal
— ni coincidía con los comentarios de cabecera del código ni con el máximo
real alcanzable):

| Componente | Techo real | Descripción |
|------------|-----|-------------|
| A — macro_permission | 14.0 | MacroScore y régimen — idéntico para todos los tickers de una misma corrida |
| B — theme_flow | 24.0 | Flujo del tema sectorial |
| C — individual_rs | 23.0 | Relative strength individual |
| D — individual_flow | 20.0 | Flujo técnico (MACD, RSI, OBV) |
| E — early_acceleration | 9.0 | DEMS y señales diarias |
| F — data_quality | 5.0 | Calidad y completitud de datos |
| **Suma (techo real del PCS)** | **95.0** | no 100 |

**Riesgos conocidos:**
- **Doble conteo** entre componentes (`ret_4w_vs_spy`, `rot_score`,
  `streak_weeks` correlacionados entre sí, entrando en C/B/D/E por caminos
  distintos). Pendiente análisis formal (ver roadmap semana 7).
- **El PCS no ordena resultados por encima del umbral de cartera** (hallazgo
  2026-08-05, ver diagnóstico CFL más abajo): correlación global PCS↔ret_1m
  = **-0.007** sobre 136 picks de las 5 carteras combinadas, signo
  inconsistente cartera por cartera. Funciona como puerta de elegibilidad,
  no como ranking — no verificado hasta este análisis, siempre fue un
  supuesto implícito del diseño.

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
| `/picks` | `/picks` | Muestra las posiciones abiertas del AI Picks Lab con precio actual. |
| `/gainers` | `/gainers` | Top 5 tickers del portfolio con mayor subida en el día. |
| `/losers` | `/losers` | Top 5 tickers del portfolio con mayor caída en el día. |
| `/macro` | `/macro` | MacroScore actual, régimen y tendencia del pipeline. |
| `/alert` | `/alert TICKER PRECIO [(nota opcional)]` | Activa una alerta de precio. El bot te avisa cuando TICKER cruce PRECIO. La nota entre paréntesis es opcional y se muestra en /alerts y en el aviso. |
| `/alerts` | `/alerts` | Lista tus alertas de precio activas. |
| `/delalert` | `/delalert TICKER` | Elimina la alerta de precio de un ticker. |
| `/kalert` | `/kalert TICKER TIMEFRAME CONDICION  |  /kalert <texto libre>` | Crea una alerta sobre una condición de Koncorde (blue/green/estado, en D/3D/W). Acepta sintaxis exacta o una petición en lenguaje natural (se interpreta con IA). También se puede crear mandando una nota de voz al bot. |
| `/kalerts` | `/kalerts` | Lista tus alertas de Koncorde activas. |
| `/delkalert` | `/delkalert TICKER` | Elimina la(s) alerta(s) de Koncorde de un ticker. |
| `/help` | `/help` | Muestra este mensaje de ayuda. |

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
| 2026-05-28 | semana3_metricas_horizonte | Prompt para implementar métricas por horizonte + comparativa vs baselines + análisis spike_flag — ✅ disparado, ver "Roadmap de mejoras pendientes" |
| 2026-07-01 | semana7_motor_avanzado | Prompt para Open Pick Review Engine + validación numérica + rejection_primary_reason + análisis doble conteo PCS — ✅ disparado, parcialmente implementado (ver "Roadmap de mejoras pendientes"; `review_open_picks.py` sigue sin construir) |
| 2026-09-03 | ranking_score_fase1_analisis | Inicio de Fase 1 (análisis exploratorio) del Ranking Score, incluida la evaluación de Koncorde como subsección propia. Sustituye a `koncorde_research_log_revision` (cancelado 2026-08-06, fusionado aquí) |
| 2026-09-15 | rfl_v2_fase6_instrumentacion_y_calibracion | Revisar `state_ux_instrumentation.json` (uso real de Fase 6) + calibrar contra `relative_flow_history` los umbrales sin calibrar de Fase 4 (coherencia Top 3 In/Out) y Fase 5a (matriz cross-módulos) |

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

## Cycle Tracker — optimización de fases, métricas nuevas y Off-cycle Themes (implementado 2026-07-29)

`cycle.html` es una pestaña puramente JS del dashboard (sin conexión al pipeline Python) que estima la fase del ciclo económico (marco Dow Theory / Stovall-Pring) promediando el alfa vs SPY (70%×3M + 30%×1M) de tickers asignados manualmente a cada fase. Se recibió una hoja de instrucciones detallada de 9 partes señalando 6 problemas concretos: muestras desbalanceadas entre fases, una fase "Late Bull → Top" contaminada al mezclar Oil+Uranium+Coal (ciclos poco correlacionados), sin medida de aceleración de segundo orden, sin breadth ni dispersión intra-fase, y sin cobertura de temas de rotación no cíclicos (crypto, AI cloud, defensa/espacio, Argentina). Cambio acotado a este único archivo — sin tocar AI Picks Lab, Portfolio Tracker ni ningún otro módulo.

### 1. Restructuración de `CYCLE_MAP` (10 fases clásicas, antes 8)

La fase única "Late Bull → Top — Energy (Oil · Uranium · Coal)" se separó en tres fases independientes, cada una puntuada por separado aunque comparten posición narrativa en el ciclo: **Oil & Gas** (8: XLE, XOM, CVX, COP, EOG, DVN, FANG, SLB — se retiró PXD, adquirida por Exxon en 2024, sustituida por FANG como productor shale de referencia), **Uranium** (8: URNM, URA, CCJ, NXE, DNN, LEU, UEC, BWXT) y **Coal & Steel Inputs** (6: HCC, AMR, BTU, CLF, TECK — ver nota sobre CNR abajo).

Otras fases ganaron tickers para acercarse al objetivo de 8 slots por fase (Parte 7 de la hoja): Transportation +ODFL/FDX (grupo nuevo "Trucking & Logistics"), Technology +AVGO (y ASML pasa de subsegment a leader), Capital Goods +DE, Utilities +SO/AEP/D/XEL. Materials, Staples & Healthcare y Financials & Cyclicals quedaron sin cambios (Financials mantiene sus 10 slots por decisión explícita del usuario de no fusionarlo con Early Bull).

**Bug real encontrado en verificación, no en la hoja original:** `ARCH` (Arch Resources) está delisted — Arch Resources se fusionó con CONSOL Energy en enero de 2025 para formar **Core Natural Resources**, cotizando como `CNR` en NYSE. El ticker `ARCH` devolvía 404 de Yahoo en producción (confirmado contra la API real antes de decidir el fix). Sustituido por `CNR` en Coal & Steel Inputs.

### 2. Off-cycle Themes — segunda estructura de datos en paralelo (`OFFCYCLE_THEMES`)

4 sub-categorías que no encajan en el ciclo económico clásico porque se mueven por narrativa propia, no por "expansión → pico → contracción → recuperación": **Crypto & Mining** (IBIT, MSTR, COIN, CORZ, MARA, RIOT — se eligió IBIT como proxy único frente a "IBIT o BITX" de la hoja original, por ser el más líquido), **AI Cloud & Infrastructure** (NBIS, SMCI, DELL, ANET, sin proxy), **Defense & Space** (ITA, ASTS, RTX, RCAT, LMT) y **Latam Emerging** (ARGT, GGAL, BBAR, YPF, VIST, PAM).

Deliberadamente **no** se añadió a `CYCLE_MAP` — vive en un array separado, sin campo `order`, excluido de `PhaseTimeline` (la barra de posición en el ciclo) y del resumen visual global (Parte 9) porque ambos responden "¿dónde estamos en el ciclo?", pregunta que no aplica a estos temas. Paleta de color deliberadamente fría/apagada (familia slate `#37474f`/`#eceff1`/`#90a4ae`, igual en las 4 sub-categorías) frente a los colores cálidos y distintos de las 10 fases clásicas, para que se lea visualmente como "fuera del marco cíclico" — sugerencia del revisor externo del plan, no solo el texto de la sección.

Se renderiza en su propia sección "Off-cycle Themes" (grid de 4 tarjetas + tabla de ranking propia, reutilizando `PhaseCard`/`PhaseRankings` sin modificarlos) debajo de la grid de las 10 fases clásicas.

### 3. `calcPhaseScores` generalizado — α por ticker como primitiva única

La función ahora acepta una lista de fases (`calcPhaseScores(list, rows)`) para poder llamarse tanto con `CYCLE_MAP` como con `OFFCYCLE_THEMES`. Cambio de fondo: antes promediaba relM3 y relM1 *por separado* entre tickers y solo componía el alfa a nivel de fase; ahora se calcula `alpha_ticker = 0.7×relM3 + 0.3×relM1` **por ticker primero**, y todo lo demás (score, breadth, dispersión, ranking) se deriva de ese array — es lo que pide literalmente la hoja ("score_fase = promedio(α_ticker)") y es necesario de todos modos para breadth/dispersión/rank por ticker.

Campos nuevos por fase: `breadth` (`{pos, total, pct}`, % de tickers con alfa>0), `dispersion` (desviación estándar poblacional del alfa entre tickers de la fase), `acceleration` (`{pp, symbol}` — `▲▲/▲/▽/▽▽` según `>+2pp / 0..+2pp / -2..0pp / <-2pp`, calculado como `relM1avg − (relM3avg−relM1avg)/2`) y `tickerRanks` (mapa ticker→{rank, alpha} para el ranking dentro de la fase).

**Fallback `relM1 ?? relM3` por ticker:** cuando falta el 1M de un ticker, su alfa colapsa a 100%×relM3 solo para ese ticker (aceptable — pensado para el estado de carga inicial, no para tickers delgados en producción). Se añadió `console.debug('[cycle] relM1→relM3 fallback applied:', ...)` por fase cuando esto ocurre, para detectar sesgo silencioso si empezara a pasar con tickers de baja cobertura (uranio junior, ADRs latam) — sugerencia del revisor externo del plan.

### 4. UI: tabla de ranking, resumen global, columnas nuevas en el detalle

`PhaseRankings` pasó de una fila de pills a una tabla real (columnas # / Fase / Score / Aceleración / Breadth / Disp. / Cargados) — necesario al pasar de 4 a 7 columnas de datos; se reutiliza para el ranking de Off-cycle Themes con un `title` distinto.

Nuevo componente `CycleSummary` (Parte 9): línea de lectura instantánea con Fase dominante, Fase perdedora, Fase con mayor aceleración y Fase con mayor desaceleración — calculado solo sobre las 10 fases clásicas (no sobre Off-cycle Themes), renderizado entre `PhaseTimeline` y `PhaseRankings`.

`PhaseCard` (detalle por fase) gana dos columnas estrechas tras α: **Rk** (posición del ticker dentro de su fase por alfa, desde `tickerRanks`) y **±** (▲/▽ según signo del alfa) — Parte 8 de la hoja.

`buildCycleMarkdown` (export a LLM) espeja todo lo anterior: bloque `## RESUMEN` al principio, columnas Breadth/Disp en las tablas de ranking, columnas rank/sign en el detalle por fase, y una sección `## OFF-CYCLE THEMES` completa (ranking + detalle) después de la sección clásica.

### Verificado

Playwright headless (Edge/Chromium) contra el servidor local real (`node server.js`, puerto 3000): las 10 fases clásicas + 4 off-cycle cargan sin errores de consola tras el fix de `ARCH→CNR` (antes daba un 404 real en `/api/quote/ARCH`, confirmado contra Yahoo directo). Verificación numérica cruzada (script Python independiente replicando la fórmula) contra 4 fases pedidas explícitamente en la revisión del plan — Oil & Gas (score -3.0, breadth 3/8, disp 4.6, accel +10.5pp), Uranium (score -26.7, breadth 0/8 — caída amplia y genuina de los 8 tickers, no un outlier aislado), Utilities (score -2.9, confirma que SO/AEP/D/XEL no rompen ni distorsionan el cálculo) y Latam Emerging off-cycle (score +3.7, breadth 4/6, impulsado por BBAR/GGAL/YPF) — los 4 coinciden exactamente con lo mostrado en pantalla. Export "Copiar para LLM" verificado end-to-end: el markdown en `localStorage.llm_export_cycle` contiene el bloque RESUMEN, las columnas Breadth/Disp y la sección OFF-CYCLE THEMES completa.

**Fuera de alcance (explícito, según la hoja original):** convertir la pestaña en predictiva, conectar con AI Picks Lab, añadir señales de Koncorde/DEMS/PCS, o cambiar la fórmula del alfa individual (70%×3M+30%×1M) — solo cambió la agregación por fase.

---

## Relative Flow Lab v2 — ratio_registry y vista por pregunta (implementado 2026-07-29)

Rediseño de `relative.html` a partir de una hoja de instrucciones detallada del usuario. Problema de partida: la vista mezclaba en el mismo ranking/cluster ratios conceptualmente distintos (risk-on/off, rotación sectorial, anticipación interna, regiones), lo que generaba lecturas confusas — p. ej. el antiguo "Risk-Off Monitor" (ver sección "Risk-Off Monitor en Relative Flow Lab" más arriba) ya tenía el naming correcto, pero seguía mezclando 4 ratios macro con el resto sin declarar qué pregunta respondía cada uno. Principio rector aplicado: *"un ratio sin pregunta explícita es ruido"*. Cambio acotado a `relative.html` + un fichero de datos nuevo — no toca PCS, rot_score, HARD_RULES ni el motor IA.

### 1. `shared/relative-ratio-registry.js` (nuevo)

Registry central de 45 ratios, cada uno con metadata interpretativa explícita: `id`, `label`, `pair`, `type` (la pregunta que responde: `risk_appetite | anticipation | rotation | regions | sector_snapshot`), `cluster` (agrupación narrativa heredada, solo para la Cluster View secundaria), `signalDirection` (`higher_is_risk_on | higher_is_risk_off | higher_is_bullish | contextual`), `primaryQuestion`, `positiveMeaning`, `negativeMeaning`, `primaryUse`, `actionability`. `type` y `cluster` son campos independientes — un ratio puede vivir en un `cluster` heredado (p. ej. `COAL`) pero clasificarse por `type` en el bloque que le corresponde (p. ej. `anticipation` o `rotation`), sin que ningún ratio existente se pierda ni quede sin metadata. Cargado en `relative.html` vía `<script src="/shared/relative-ratio-registry.js">` antes del script Babel (mismo patrón que `shared/flow-score.js` en `portfolio.html`).

**Composición de los 45 ratios:**
- `risk_appetite` (7): fusiona los 4 ratios de la antigua "Capa 1" (Copper/Gold, Credit vs Equities, Utilities vs Discretionary, Low Vol vs Momentum) con 3 del antiguo cluster `RISK / BREADTH` (Small Caps vs SPY, Nasdaq vs Equal Weight, Discretionary vs Staples). `XLY/XLP` vive solo aquí (no duplicado en `rotation`, siguiendo la sugerencia explícita de la hoja para evitar el mismo ratio en dos bloques). `QQQ/RSP` es el único con `signalDirection: "contextual"` — su lectura (concentración en mega-cap growth) no tiene una dirección risk-on/off inequívoca (puede reflejar tanto apetito por riesgo como un mercado defensivo concentrado en pocos valores de calidad); se muestra en la tabla pero **no cuenta** en el agregado del monitor.
- `anticipation` (11): 6 ratios existentes (Energy Equities vs Brent, Gold Miners vs Gold, Regional vs Large Banks, E&P vs Integrated, Silver vs Gold, Broad Nuclear vs Uranium Miners) + `GDXJ/GDX` y `BTC-USD/GC=F` (nuevos, Fase 1) + 3 huérfanos reclasificados (`HCC/BTU`, `AMR/BTU`, `CCJ/URNM` — texto de metadata dictado literalmente por el usuario).
- `rotation` (7): `XLB/XLE` (reclasificado, antes en cluster ENERGY) + 4 pares nuevos (`XLK/XLF`, `IWD/IWF`, `SMH/IGV`, `XLE/XLK` — solo `IWD/IWF` y `SMH/IGV` requieren tickers nuevos, `XLK/XLF`/`XLE/XLK` combinan tickers ya usados) + 2 huérfanos (`HCC/XME`, `AMR/XME`). Todos con `signalDirection: "contextual"` — responden "hacia dónde rota el capital", no "es esto alcista".
- `regions` (4): sin cambios (EM vs World, Brazil/EM, Argentina/EM, Japan/EM). `FXI/EEM` y `KWEB/EEM`, mencionados en la hoja original como "ratios iniciales" de este bloque, **no** se añadieron — no estaban en la lista explícita de Fase 1 acordada con el usuario ni en los criterios de aceptación; quedan pendientes (ver Roadmap).
- `sector_snapshot` (16): los 14 sector-vs-SPY existentes + 2 huérfanos (`URNM/URTH`, `XME/SPY`) — bloque deliberadamente secundario (`actionability: "medium-low"` en casi todos), tal como pide la hoja ("no núcleo del módulo, duplica info del Cycle Tracker").

**Efecto colateral aceptado:** el cluster `FINANCIALS` de la Cluster View ahora solo contiene `KRE/XLF` (antes también repetía `XLF/SPY`, duplicación documentada en la sección "Cluster SECTOR ROTATION" de este mismo archivo). Con un registry único por par, `XLF/SPY` vive solo en su cluster `SECTOR ROTATION`; se aceptó perder esa duplicación intencional previa por ser un efecto secundario menor de pasar a una fuente de datos única por ratio.

### 2. `relative.html` — nueva jerarquía visual

1. **Risk Appetite Monitor** (antes "Risk-Off Monitor") — mismo mecanismo de conteo que antes (`riskAppetiteMonitorState`, estados 0/1/2/3/4+ sin cambios), generalizado de 4 a 6 ratios contables (excluye `QQQ/RSP` contextual) vía `getRiskAppetiteSignal(row, signalDirection)`. Denominador dinámico en el header y en la caja grande (`X/6 warnings`, antes hardcodeado `/4`). Columna nueva "Dirección" en la tabla mostrando el `signalDirection` de cada fila.
2. **Early Flow Detector** — sin cambios funcionales, ahora alimentado por los 45 ratios del registry en vez de los ~39 anteriores.
3. **Question-Based Views** (nuevo, primario) — 4 bloques (`QuestionBlock` component), uno por `type` restante (`anticipation`, `rotation`, `regions`, `sector_snapshot`), cada uno con: título + pregunta (`RATIO_TYPES[type].question`), "Top 3" ordenado por score con label + interpretación corta, y tabla completa con columna nueva **Interpretation** (`interpretationFor(row)`: `positiveMeaning` si `score>=0`, si no `negativeMeaning`). La clasificación Leader/Improving/Weakening/Laggard (`classify()`) no cambia — sigue siendo momentum puro; la columna Interpretation es la que traduce esa etiqueta a la pregunta real del bloque (p. ej. `XLU/XLY` sigue pudiendo ser "Leader" mientras su interpretación dice "señal defensiva").
4. **Most Extreme Relative Moves** (reemplaza "Top 5 by Score") — ranking global por `|score|` descendente, no por score crudo, y explícitamente no llamado "best signals". "Top 5 Flow Change" se mantiene sin cambios.
5. **Cluster Coherence View** (secundaria, antes "Capa 2") — mecánica sin cambios (`clusterSummary`/`biasStyle`), ahora derivada del campo `cluster` del registry; 11 clusters (antes 8): se suman `RISK APPETITE` (los 7 ratios de risk_appetite, invisibles en Cluster View hasta ahora porque los 4 de Capa 1 nunca habían participado), `STYLE / FACTOR` (`IWD/IWF`) y `CRYPTO` (`BTC-USD/GC=F`).
6. **Raw Ratio Tables — by cluster** (terciaria, antes la única tabla) — se mantiene igual (Rank global, 6M, From 52W High, sparkline) para quien quiera el detalle técnico completo agrupado por cluster.

### Verificado

Node `--check` sobre el registry + transpilación con `@babel/standalone` del script JSX sin errores de sintaxis. Página cargada end-to-end con Edge headless (CDP directo, sin Playwright instalado en el proyecto) contra `node server.js` real: 4 `QuestionBlock` renderizados, 7 filas en Risk Appetite Monitor, 11 clusters, cero mensajes de consola de error/excepción. Confirmado por consola: `QQQ/RSP` muestra badge "Contextual" y no participa en el conteo (4/6 defensive warnings, no 4/7). Export a Markdown (`localStorage.llm_export_relative`) verificado con contenido real: bloque Risk Appetite Monitor con columna Dirección, las 4 secciones de pregunta con Top Signals + tabla + Interpretation, Most Extreme Relative Moves, Cluster View y Raw Ratio Tables. Tickers nuevos (`IWD`, `IWF`, `SMH`, `IGV`, `GDXJ`, `BTC-USD`) verificados contra `/api/history/:symbol` real antes de integrarlos; `BTC-USD/GC=F` se alinea correctamente porque `alignRatio` indexa por las fechas de `GC=F` (futuro, sin fines de semana), descartando automáticamente las velas de fin de semana de BTC sin lógica adicional.

### Fuera de alcance (explícito, decidido con el usuario antes de implementar)

- **Fase 2 de ratios** (prioridad media en la hoja original): `DX-Y.NYB/GC=F` (DXY vs Gold), `JPY=X/^N225` (USDJPY vs Nikkei), `IJS/IJT` (Small Cap Value vs Growth), `TLT/IEF`, `EDV/IEF`. Nota del usuario: `TLT/IEF`/`EDV/IEF` probablemente encajan también en `duration.html` — evaluar ahí antes de decidir dónde viven.
- **`FXI/EEM` y `KWEB/EEM`** (mencionados en la hoja original para el bloque Regions pero fuera de la lista de Fase 1 acordada) — pendiente de decisión explícita si se quiere ampliar el bloque `regions`.
- **Persistencia diaria** (`docs/data/relative_flow_history.jsonl`, marcada como opcional en la hoja original) — no implementada: requeriría un script nuevo (Python o Node) en el pipeline para loguear score/signal/interpretation_state por ratio y día, fuera del alcance de "rediseño interpretativo de `relative.html`". Si se implementa más adelante, permitiría evaluar qué ratios anticipan mejor rendimiento posterior (mismo patrón que `koncorde_signals_history.jsonl`).
- Rediseño de la fórmula de `score` (1W×0.5 + 1M×0.7 + 3M×0.25 + ajustes) — sin cambios, solo se reinterpretó visualmente vía `type`/`signalDirection`/Interpretation.

---

## Flujos & Rotación v2 — optimización (Fases 1-5, completo) (implementado 2026-07-29/30)

Rediseño en curso de `rotacion.html` a partir de una hoja de instrucciones de 5 fases (histórico, Δ dinámicas, coherencia régimen-rotación, registry de divergencias, refinamientos). Trabajo acordado con el usuario **fase por fase con verificación entre cada una** — esta entrada cubre solo la Fase 1 (infraestructura), base de la que dependen las Fases 2-4.

**Decisión de arquitectura previa (aclarada con el usuario antes de escribir código):** `rotacion.html` no tiene backend Python — a diferencia de AI Picks Lab, todo el scoring (A/B/C), régimen y señales se calculan en el navegador (React client-side, como `relative.html`/`duration.html`), sin paso en el pipeline de GitHub Actions. La hoja de instrucciones original asumía "snapshot en cada run del sistema" como si hubiera un cron 2×/día — no aplica aquí. Dos opciones sobre la mesa: (a) extender el mecanismo ya existente de `state.json` (mismo patrón que `macro_score_history`/`early_rotation_candidates`, client → POST a `/api/state`) o (b) portar todo el cálculo A/B/C + régimen a un script Python nuevo commiteado a `docs/data/`. Se eligió (a) explícitamente — evita el riesgo de drift JS/Python ya documentado (bug de `calcCMF` desincronizado, sección "Koncorde Plus v2" más arriba) a cambio de que el histórico solo persista en la máquina donde corre `node server.js` (no se commitea a git — `state.json` está en `.gitignore` — ni aparece en GitHub Pages). Mismo trade-off ya aceptado hoy para `macro_score_history`.

**Implementación:** nuevo campo `rotation_history: { [ticker]: [...] }` en `state.json` (`DEFAULT_STATE` en `server.js` y en `rotacion.html`). Un registro por ticker por día natural, escrito en `load()` justo después de `updateStateFromData()`, usando el estado *ya actualizado* (`newState`: régimen resuelto por histéresis, streaks del día ya aplicados) para que lo persistido coincida exactamente con lo que la UI renderiza en ese ciclo. Dedup por fecha — mismo patrón que `macro_score_history`/`early_rotation_candidates`: si la pestaña se recarga varias veces el mismo día, la fila de hoy se sobrescribe (no se duplica). Cap de 70 entradas por ticker (~10 semanas), mismo valor que `macro_score_history`. SPY excluido (es el benchmark, no un candidato de rotación).

Cada entrada: `{date, score, signal, blockA, blockB, blockC, fit, macro_regime, macro_score, rs_1w, rs_4w, rs_13w}`. `macro_regime` guarda el nombre canónico del régimen (`Bull Maduro`, no el nombre de display+trend `Risk-On Maduro Stable`) — necesario para que la Fase 3 (coherencia régimen-rotación) pueda cruzar directamente contra `REGIMES[].defaultLeaders`, que ya existe en el código y usa esos mismos 5 nombres canónicos.

**Refactor sin cambio de comportamiento:** para poder calcular el snapshot con el mismo resultado exacto que ve el usuario en pantalla, se extrajeron tres funciones que antes vivían inline dentro del `useMemo` de `rows` y de `effectiveRegime`: `computeEffectiveRegime()`, `buildEarlyRotQualifyMap()`, `computeTickerRow()`. Ahora se llaman tanto desde el render (`rows` useMemo) como desde `load()` (snapshot) — evita que la lógica persistida diverja de la lógica renderizada, mismo criterio que motivó centralizar `HARD_RULES`/`compact_candidate` en `ai_shared.py` en el pipeline Python.

**No hay "cierre de viernes" explícito** (a diferencia de lo sugerido en la hoja original) — como esta pestaña no tiene un cron propio, solo se computa cuando alguien abre la página, el dedup diario ya es la unidad natural de "un run" aquí. Las Δ semanales de Fase 2 se calcularán buscando la entrada más cercana a N días atrás sobre estos días naturales (mismo patrón `findClosestAtOrBefore` que ya usa `computeMacroTrend` con `macro_score_history`), sin exigir huecos exactos de 7 días.

**Fallback UI durante el bootstrap:** nuevo `useMemo` `rotHistoryBootstrap` (fecha del primer snapshot + si ya han pasado ≥7 días naturales). Nota discreta bajo el header "Mapa de Rotación" mientras `ready=false`: *"Métricas históricas... disponibles a partir de la segunda semana desde YYYY-MM-DD."* Las Fases 2-4 deberán usar este mismo flag para no mostrar deltas falsos antes de tener histórico suficiente.

**Verificado en producción real** (Edge headless vía CDP directo, mismo enfoque que otras páginas — sin Playwright instalado en el proyecto): sintaxis del script JSX transpila sin errores (`@babel/standalone`); carga de `rotacion.html` contra `node server.js` real sin excepciones nuevas en consola (el único `console.error` presente — claves duplicadas `LLY` en `StockCandidates` — es preexistente y no relacionado); tras una carga real, `state.json` quedó con 22 tickers (todo `UNIVERSE` menos SPY) con snapshot del día, valores plausibles (p. ej. XLF: score 8, COMPRA, blockA/B/C 4/2/2, fit=true, macro_regime="Bull Maduro", coincide con lo mostrado en pantalla); segunda carga el mismo día no duplicó filas (`XLF` siguió con 1 entrada); reinicio real de `node server.js` (kill + restart) confirmó que el histórico sobrevive (persistencia en disco, no en memoria).

**Nota de naming:** el repo ya tenía `backtest/data/processed/rotation_history.parquet` (histórico de scoring del backtest Python, cosa completamente distinta). Coincidencia de nombre sin colisión real — viven en `state.json` (gitignored, cliente) vs un parquet commiteado (pipeline Python) — pero puede confundir en una búsqueda futura; queda anotado aquí.

### Fase 2 — Lectura dinámica sobre el histórico (implementado 2026-07-29)

Construida sobre `rotation_history` de la Fase 1. Todas las métricas nuevas dependen del mismo flag `rotHistoryBootstrap.ready` (≥7 días naturales desde el primer snapshot) — antes de eso muestran "—", nunca un delta inventado.

**Δ Score 1W + flecha (2.1/2.6):** `findHistEntryAtOrBefore(history, 7)` generaliza el helper que ya usaba `computeMacroTrend` para `macro_score_history` (misma semántica "closest at or before N days ago", sin exigir hueco exacto de 7 días — coherente con que esta pestaña no tiene cron propio). Umbrales del plan sin cambios: ≥+2 ↗ verde, -1..+1 → gris, ≤-2 ↘ rojo. Columna nueva al final de la tabla "Mapa de Rotación" + flecha junto al score.

**Badge UPGRADED/DOWNGRADED (2.2):** compara `row.sig.label` actual (ya post-Master-Filter) contra el signal guardado en la entrada de hace ~7 días — como el snapshot de Fase 1 ya guarda el label final renderizado, el badge hereda automáticamente el efecto del Master Filter sin lógica adicional. Requiere un orden de calidad de señal para decidir qué es "mejor": `SIGNAL_RANK = {COMPRA:5, ACUMULAR:4, ROT.CONFIRMADA:3, ROT.TEMPRANA:2, VIGILAR:1, —:0}` — mismo orden que el cascade if/elif de `getSignal()` (no una escala inventada aparte). Badge junto al ticker en la tabla.

**Semanas en señal (2.3):** cuenta días naturales (no nº de snapshots guardados) desde que empezó la racha actual de la misma señal, dividido entre 7. Se basa en tiempo transcurrido precisamente porque el histórico puede tener huecos (la pestaña solo graba cuando alguien la abre) — un hueco de varios días no rompe la racha si la señal es la misma antes y después.

**Distancia al siguiente umbral (2.4) — con recorte deliberado de alcance:** solo calculada para tickers `fit=true` (líderes efectivos del régimen actual). Es el único tramo con un umbral de score limpio y objetivo (VIGILAR=3 / ACUMULAR=5 / COMPRA=buyThreshold). Los caminos ROT.CONFIRMADA/ROT.TEMPRANA dependen de streak+clúster, no de un único umbral de score — se dejan fuera (`null`) en vez de inventar un pseudo-umbral. Si el Master Filter está activo (SPY<SMA200), la distancia sobre el score crudo dejaría de coincidir con la señal mostrada en pantalla (degradada 1 nivel) — en ese caso se marca `masterFilterBlocking:true` en vez de devolver un número engañoso. Emergency mode tiene su propio tramo único (`ACUMULAR*`, min=6).

**Nota sobre el ejemplo del plan original:** el ejemplo de la hoja ("XLK score 6/10, buyThreshold 8 → -3 a la baja para caer a VIGILAR desde ACUMULAR") tiene una inconsistencia aritmética — con ACUMULAR.min=5, hace falta perder 2 puntos (6→4), no 3, para caer a VIGILAR. Se implementó la lógica correcta (`bufferDown = score - tierActual.min`, un "colchón" sobre el umbral, no "puntos hasta el umbral inferior literal") en vez de replicar el número del ejemplo.

**Watchlist promoción/degradación (2.5):** dos tablas nuevas ("↗ Próximos a subir" / "↘ Próximos a caer") entre el bloque Oportunidades/Rotación y el Mapa de Rotación. Promoción = `fit` tickers con `pointsUp===1`, ordenados por Δ1W descendente. Degradación = `fit` tickers con `bufferDown===0` (exactamente en el borde, sin colchón), ordenados por Δ1W ascendente. Ambas vacías/ocultas mientras el Master Filter está activo (nota explicativa en su lugar) o antes de la segunda semana de histórico.

**Export a LLM:** `buildMD()` sincronizado — nueva sección `## WATCHLIST PROMOCIÓN/DEGRADACIÓN` y columnas `Δ1W`/`Sem.` añadidas a la tabla `## ROTACIÓN COMPLETA`, con el mismo fallback "—"/nota de bootstrap que la UI.

**Verificado:** sintaxis Babel sin errores tras los cambios; carga real contra `node server.js` sin excepciones nuevas (mismo único warning preexistente de `StockCandidates`/`LLY`, no relacionado); con solo 1 día de histórico real se confirmó que el bootstrap note aparece, las columnas Δ1W/Sem. muestran "—", y la watchlist no se renderiza (gating correcto). Como el score de "hoy" siempre se recalcula con datos de mercado en vivo (no se puede fabricar un ticker "a 1 punto del umbral" contra el servidor real), la aritmética de Δ1W/badge/racha/distancia-a-umbral se verificó aparte con 21 tests unitarios sobre las funciones puras extraídas letra-por-letra de `rotacion.html` (diff automático confirmó que el código bajo test es idéntico al de producción, solo difieren comentarios/blancos) — cubren: delta positivo+UPGRADED, delta negativo+DOWNGRADED, sin cambio de señal, sin dato a 7+ días, racha cortada por un cambio de señal intermedio, ladder estándar, borde exacto sin colchón, ticker no-fit→null, Master Filter bloqueando, CREDIT_COMPLACENCY subiendo el buyThreshold a 8, y el tramo único de emergencia. 21/21 passed.

### Fase 3 — Coherencia régimen vs rotación (implementado 2026-07-29)

**3.1 Líderes teóricos por régimen — sin trabajo nuevo:** ya existían como `REGIMES[].defaultLeaders` (5 regímenes canónicos). Se reutilizan **post-condicionales** vía `effectiveLeaders` (el mismo array ya usado para `fit`/"Líderes activos" en el resto de la pestaña, con los ajustes de `getEffectiveLeaders` — filtro IWM, filtro Gold, Inflation Overlay — ya aplicados), no la lista estática. Decisión confirmada con el usuario: sin granularidad por trend (Improving/Stable/Deteriorating) — los 5 regímenes canónicos bastan, el trend informa dirección, no composición.

**3.2 Tabla "Líderes efectivos en el régimen actual":** nueva sección entre "Condiciones Macro para Compra" y el bloque Oportunidades/Rotación. Columnas Ticker/Score/Señal/Δ1W/Sem./Confirma, reutilizando `row.dyn` de Fase 2 sin recalcular nada. "Confirma régimen" = señal actual con rank ≥ ACUMULAR en `SIGNAL_RANK` (COMPRA o ACUMULAR/ACUMULAR* cuentan; ROT.CONFIRMADA/ROT.TEMPRANA NO cuentan aunque sean señales válidas — no implican que el ticker sea uno de los líderes reconocidos del régimen).

**3.3 Banner de coherencia:** `computeRegimeCoherence(signalByTicker, leaders)` — confirm/total/pct sobre `effectiveLeaders`. Umbrales literales del plan: `>70%` verde "régimen confirmado", `40-70%` ámbar "régimen mixto / transición", `<40%` rojo "régimen no confirmado por rotación — posible cambio en curso" (con el borde en 70/40 resuelto como `pct>70`/`pct>=40`, verificado con test de bordes exactos).

**3.4 Δ coherencia 1W:** nuevo `regime_coherence_history: [{date,pct,confirm,total,macro_regime}]` en `state.json` (mismo patrón dedup-por-día/cap-70 que `rotation_history`/`macro_score_history`, escrito en el mismo bloque de `load()`). El % se calcula una vez en el loop de snapshot existente (reutiliza los `row.sig.label` ya computados para `rotation_history`, sin recalcular `getSignal`) y una segunda vez en vivo para el render (`regimeCoherence` useMemo sobre `rows`/`effectiveLeaders` actuales) — necesario porque el snapshot persistido puede ser de una carga anterior el mismo día. El delta usa `findHistEntryAtOrBefore` (mismo helper genérico de Fase 2, ya funcionaba sobre cualquier array con `.date`).

**Export a LLM:** `buildMD()` gana sección `## COHERENCIA RÉGIMEN vs ROTACIÓN` con el banner + tabla de líderes, en el mismo punto del documento que en la UI.

**Verificado en producción real:** sintaxis Babel sin errores; carga contra `node server.js` real sin excepciones nuevas. Caso real observado en pantalla y confirmado en `state.json`: régimen Bull Maduro, 7 líderes efectivos (XLF/XLI/XLB/XLE/SI=F/BZ=F/HG=F — GC=F excluido por el filtro `goldOk`), 6/7 confirman (todos menos XLI, que está en VIGILAR) → banner "6/7 (86%) — régimen confirmado", tabla de líderes con XLI marcado ✗ y el resto ✓ — coincide exactamente con lo persistido en `regime_coherence_history`. Los primeros dos intentos de verificación con el navegador headless dieron falsos negativos por errores del propio arnés de prueba (búsqueda de texto en la sección equivocada del DOM, y una espera fija de 13s insuficiente en un run más lento) — no eran bugs de la app; se corrigieron pasando a un polling de "listo" antes de leer el DOM, igual que ya hacía la verificación de Fase 1. Igual que en Fase 2, la aritmética de Δ coherencia 1W y los umbrales de nivel se verificaron aparte con 12 tests unitarios sobre las funciones extraídas letra por letra de producción (diff normalizado confirmó código idéntico, solo difieren comentarios/espacios) — suman 33/33 tests pasados entre Fase 2 y Fase 3.

**Nota lateral (no relacionada con este cambio):** durante la verificación se detectó que la unidad de `%TEMP%` del usuario está al 100% de uso (223G/223G, ~364M libres) — no causado por este trabajo (los perfiles de Edge headless usados para verificar sumaban solo unos cientos de MB, ya limpiados). Vale la pena que el usuario revise qué está llenando esa unidad, porque con tan poco margen cualquier proceso que escriba en Temp (incluidas futuras verificaciones de este tipo) puede empezar a fallar con `ENOSPC`.

### Fase 4 — Registry de divergencias (implementado 2026-07-30)

**4.1/4.2 Registry — 8 relaciones, no todas son pares simples de 2 tickers.** El plan listaba 8 relaciones (Copper/Silver, Crude/Energy Equities, Integrated/E&P, Financials/Bonds, Tech Sector/Index, Cyclicals/Copper, Defensives/Risk-on, Healthcare/régimen), pero solo 4 de ellas encajan en "comparar 2 tickers en la misma dirección": Financials vs Bonds es una relación **inversa** (risk-on coherente = uno confirma y el otro no, ambos confirmando a la vez es la lectura ambigua); Cyclicals vs Copper y Defensives vs Risk-on comparan un **grupo** de tickers; Healthcare vs régimen compara un ticker contra el **estado del régimen actual**, no contra otro ticker. En vez de escribir 8 evaluadores sueltos (lo que sí sería la "lógica ad hoc" que el plan prohíbe en 4.4), se tipificaron en 5 `type` reutilizables — `pair_same_direction`, `pair_inverse_risk`, `group_vs_ticker`, `group_vs_regime_leaders`, `ticker_vs_regime` — cada uno con su propia función evaluadora fija, y el registry (`DIVERGENCE_REGISTRY`, array literal en `rotacion.html`) solo declara qué tickers/grupo participan y el `theme` (frase que particulariza la plantilla de interpretación). No se creó un `.json` externo — vive como const en el mismo archivo, igual que `REGIMES`/`UNIVERSE`/`CLUSTERS`, por coherencia con el resto del módulo (todo client-side, sin pipeline Python).

**Ticker nuevo — XOP añadido a `UNIVERSE`.** "Integrated Energy vs E&P" necesitaba una pata E&P que no existía en el universo de 23 tickers; se añadió `XOP` (SPDR S&P Oil & Gas E&P ETF), verificado contra `/api/quote/XOP` real antes de integrarlo (mismo criterio que el fix de `ARCH→CNR` en Cycle Tracker — no asumir que un ticker resuelve). XOP participa en el heatmap/`rotation_history`/Fase 2-3 como cualquier otro ticker, pero no es líder de ningún régimen (`fit` siempre `false`), así que no afecta Oportunidades ni la watchlist.

**5ª categoría `neutral`, no pedida por el plan.** El plan define 4 estados (strong_confirmation/partial_confirmation/divergence/warning) pero sus propias condiciones de ejemplo (4.1) no son exhaustivas: si ninguno de los dos lados confirma, ninguna de las 4 aplica. Se añadió `neutral` ("ninguno de los dos lados sugiere fuerza suficiente") como quinta categoría para que la cascada sea exhaustiva en todos los `type`, con su propio icono (`·` gris) e interpretación en el mismo vocabulario obligatorio. Orden de evaluación = prioridad en una sola cascada if/elif por evaluador (mismo criterio que `_konc_alignment` en `koncorde_calculator.py`): `warning` siempre se comprueba primero para que el estado más alarmante no quede enmascarado por una confirmación parcial.

**4.4 Lenguaje interpretativo — se siguió la regla, no el ejemplo del plan.** El ejemplo de la hoja en 4.1 ("Reflation broadly confirmed by both...") usa "confirmed" sin matiz "partial", violando su propia regla de 4.4 ("prohibido 'confirms' sin el matiz partial"). Se implementó la regla literal: las 5 plantillas de interpretación (una por estado, fijas, parametrizadas solo por `entry.theme`) usan exclusivamente "sugiere confirmación fuerte/parcial", "no confirmado por" y "warning: ambiguous" — nunca "confirma"/"contradice"/"significa" como afirmación conclusiva sobre la relación (sí se usa "confirma" para describir el hecho mecánico de que la señal de un ticker individual alcanza ACUMULAR+, terminología ya usada en la columna "Confirma" de Fase 3 — no es la afirmación conclusiva que la regla prohíbe). Verificado con un test automático que escanea las 5 plantillas en busca de vocabulario prohibido y confirma la presencia de vocabulario obligatorio.

**Refactor menor:** se extrajo `confirmsSignal(label)` (antes `(SIGNAL_RANK[x]??0)>=SIGNAL_RANK['ACUMULAR']` repetido inline en 3 sitios de Fase 3) — usada ahora por `computeRegimeCoherence`, la tabla de líderes efectivos, y los 5 evaluadores de Fase 4.

**Render:** nuevo bloque "Divergencias y Confirmaciones (8 relaciones monitorizadas)" entre la tabla de líderes efectivos (Fase 3) y Oportunidades, grid de 2 columnas con icono/estado/interpretación por relación. Export a LLM (`buildMD`) sincronizado con la misma sección.

**Verificado en producción real:** sintaxis Babel sin errores; carga real sin excepciones nuevas; las 8 relaciones renderizan con estados coherentes con los datos reales del momento (ej. Copper vs Silver en `WARNING` porque HG=F=9/COMPRA vs SI=F=4/VIGILAR, gap de 5 puntos con señales distintas; Defensives vs Risk-on en `STRONG CONFIRMATION` porque XLU/XLP no confirman mientras la coherencia de régimen estaba en 71%; Healthcare vs régimen en `NEUTRAL` porque el régimen activo es Bull Maduro, no Transición, y XLV no confirma) — verificado cruzando manualmente cada resultado contra los datos crudos de la tabla. `XOP` confirmado con datos reales y plausibles en el heatmap (24 activos, antes 23) y en `rotation_history` de `state.json`. Igual que en Fases 2-3, la aritmética de los 5 evaluadores y el cumplimiento de la regla de lenguaje se verificaron con **50 tests unitarios** sobre las funciones extraídas letra por letra de producción (diff normalizado confirmó código idéntico) — 8/8 casos por tipo de evaluador (incluye bordes: falta un lado por fetch fallido → `neutral` sin crash, gap>4 con prioridad sobre `divergence`) más el escaneo de vocabulario prohibido/obligatorio sobre las 5 plantillas. Total acumulado Fases 2-4: 83/83 tests pasados.

### Fase 5 — Refinamientos secundarios (implementado 2026-07-30, cierra el rediseño)

**5.1 Fit gradual — deriva de datos ya existentes, sin tabla nueva.** En vez de inventar una asociación ticker↔nivel aparte, `computeFitLevel(ticker, regime, effectiveLeaders)` compara contra lo que ya existía: `core` = está en `effectiveLeaders` (líder activo ahora); `secondary` = está en la lista estática `regime.defaultLeaders` pero un condicional (goldOk/iwmOk/Inflation Overlay) lo excluyó de `effectiveLeaders` ahora mismo; `contrary` = es líder estático de **otro** régimen (no del actual) — "activo típico de otro régimen", tal como pide el plan; `neutral` = no aparece en ningún régimen. El booleano `fit` (= `core`) no se tocó — sigue siendo la base de Oportunidades/watchlist/Fase 3-4; `fitLevel` es un campo nuevo puramente de display, calculado en el `useMemo` de `rows` (no en `computeTickerRow`, que también corre en el snapshot de Fase 1 y no necesita persistir esto). Anomalía (score≥6 + `contrary`): fila resaltada en el heatmap (fondo ámbar + borde izquierdo naranja) — umbral 6 elegido por ser el punto medio entre los suelos de ACUMULAR(5) y COMPRA(7), no un umbral nuevo inventado aparte de los ya usados en el sistema.

**5.2 Balance de subscores — cascada literal del plan, con un hallazgo real.** `computeSubscoreProfile(rot)` implementa las 7 reglas en el orden exacto del plan (primera coincidencia gana) + un fallback `undetermined` no pedido por el plan (mismo criterio que `neutral` en Fase 4: las 7 reglas no son exhaustivas). **Hallazgo verificado por fuerza bruta sobre las 80 combinaciones válidas de A∈[0,4]/B∈[0,3]/C∈[0,3]:** `fragile_no_technical` (`score≥6 && C===0`) es **estructuralmente inalcanzable** con los pesos reales de `RotationScore v2` de este proyecto (blockA máx 4, blockB máx 3, blockC máx 3) — con C=0, alcanzar score≥6 exige A+B≥6, y dados esos máximos eso solo es posible con A≥2 Y B≥2 simultáneamente, lo que ya dispara `flow_supported` (evaluado antes en la cascada). No es un bug de esta implementación — es del propio orden de reglas del plan combinado con los máximos reales de este proyecto (que el plan no necesariamente asumía). Se dejó la regla en el código tal cual la pide el plan (no se reordenó ni se "arregló" el dead branch) y se documenta aquí para que quede constancia. **Verificado el criterio de aceptación explícito del propio plan:** XLK con subscore real 3/0/0 sale como `momentum_only` — confirmado tanto en el test unitario como en pantalla contra datos reales.

**5.3 MacroScore sparkline + régimen anterior.** Componente `Spark` (SVG minimalista, mismo patrón que `sentiment.html`/`relative.html`/`duration.html` — cada página mantiene su propia copia, sin módulo compartido) alimentado con `appState.macro_score_history` ya existente (cap 70 entradas ≈10 semanas — no son 13 semanas exactas como pedía el plan, es el histórico real disponible dado que esta pestaña no tiene cron propio, ver Fase 1). "Régimen actual (desde hace N sem.)" ya era derivable de `regime_entered_date`; "Régimen anterior (durante N sem.)" es nuevo — requirió añadir `previous_regime: {label, entered_date, exited_date}` a `state.json`, capturado en el único punto donde la histéresis de `updateStateFromData` sobrescribe `current_regime` (antes de la reasignación). **Simplificación deliberada:** no se muestra el trend (Improving/Stable/Deteriorating) del régimen anterior — ese trend es un valor calculado en el momento a partir de `macro_score_history`, no algo que quede registrado retroactivamente por régimen sin añadir otra estructura de histórico; fuera de alcance para un refinamiento de Fase 5. Self-heal añadido (`if (s.previous_regime === undefined) s.previous_regime = null`) para que `state.json` anteriores a este campo no dejen la clave ausente — mismo patrón que ya usan `macro_score_history`/`rotation_history`.

**5.4 Tooltips en indicadores macro — gap real, no existían.** `MacroCard` no tenía ningún tooltip antes de este cambio (verificado leyendo el componente). Se añadió un campo `tooltip` (texto fijo: qué mide, rango normal) a cada uno de los 5 `MACRO_ITEMS`, compuesto en `MacroCard` con el valor/status actual en el momento de mostrarse. Requirió un componente nuevo, `Tip` — copia de `ThTip` pero envolviendo un `<div>` en vez de un `<th>` (`MacroCard` no vive dentro de una tabla), mismo mecanismo de portal/posición.

**Verificado en producción real:** sintaxis Babel sin errores en cada paso; carga real sin excepciones nuevas. Los 4 niveles de Fit confirmados con datos reales del momento: XLF `core`(✓)/Equilibrado, GC=F `secondary`(◐, filtrado por `goldOk`)/Solo técnico, XOP `neutral`(○)/—, TLT `contrary`(⚠, líder de Transición/Risk-OFF/Capitulación, no de Bull Maduro)/—. "Régimen actual: Risk-On Maduro (desde hace 1 sem.)" renderizado correctamente; "Régimen anterior" correctamente ausente (no ha habido ningún cambio de régimen en lo que lleva corriendo esta implementación). 15 tests unitarios adicionales sobre las funciones extraídas letra por letra de producción (`computeFitLevel` ×5 casos, `computeSubscoreProfile` ×7 + el test de inalcanzabilidad por fuerza bruta, `regimeContext` ×2). Total acumulado Fases 2-5: **98/98 tests pasados**.

---

## Cierre del rediseño Flujos & Rotación v2 (Fases 1-5, 2026-07-29/30)

Las 5 fases del plan original se completaron en su totalidad, trabajando fase por fase con verificación entre cada una (según lo acordado con el usuario al empezar). Resumen de las desviaciones deliberadas respecto al plan original, todas documentadas en su sección correspondiente arriba:
- El histórico (Fase 1) vive en `state.json` local (client-side), no en un pipeline Python — decisión de arquitectura explícita, evita el riesgo de drift JS/Python ya vivido con `calcCMF`.
- Sin "cierre de viernes" — dedup diario es la unidad natural de "un run" dado que esta pestaña no tiene cron propio.
- Se añadió una 5ª categoría `neutral` tanto en Fase 4 (registry de divergencias) como en Fase 5 (`undetermined` en balance de subscores) porque las reglas del plan, en ambos casos, no son exhaustivas.
- Fase 4: 4 de las 8 relaciones no eran pares simples de 2 tickers — se tipificaron en 5 evaluadores reutilizables en vez de lógica ad hoc. Se añadió `XOP` al universo (no existía pata E&P). Se siguió la regla de lenguaje (4.4) del plan por encima de su propio ejemplo (4.1), que la incumple.
- Fase 5: se documentó un dead branch real (`fragile_no_technical`, inalcanzable con los pesos A:4/B:3/C:3 de este proyecto) en vez de alterar el orden de reglas que pedía el plan.

Ningún cambio tocó AI Picks Lab, Portfolio Tracker, Cycle Tracker, Relative Flow Lab ni ningún otro módulo — todo el trabajo quedó contenido en `rotacion.html` + los campos nuevos de `state.json` (+ `server.js` para los `DEFAULT_STATE` correspondientes), tal como pedía el plan original.

---

## Flechas de tendencia en Flow Score y ATR% — Portfolio Tracker (implementado 2026-08-02)

`portfolio.html` mostraba Flow Score y ATR% como foto estática (solo el valor de hoy). El usuario pidió indicar tendencia respecto de la sesión anterior con flechas de distinto grado de inclinación (no solo ↑/↓ binario), y para ATR% además comparar contra la media histórica propia del ticker.

**Fuente de datos — se reutilizó infraestructura ya existente, no una nueva.** `signals_history.json` (servido vía `/api/signals`, `server.js`) ya registraba `flowScore` una fila por ticker/día desde hace tiempo, pero solo se usaba para escribir (POST), nunca se leía de vuelta para mostrar nada — `portfolio.html` no lo cargaba en ningún estado. `atrPct` no se registraba en absoluto en ese histórico (verificado leyendo el POST antes de tocar código); se añadió como campo nuevo al objeto que se empuja a `/api/signals` en el `useEffect` de guardado de snapshot.

**Implementación (`portfolio.html`):**
- Nuevo estado `signalsHistory` (fetch de `/api/signals` en la carga inicial, junto a `/api/portfolio`/`/api/stock-config`/`/api/universe`).
- `buildPrevSessionMap(history)`: para cada ticker, la fila más reciente con fecha estrictamente anterior a hoy — "sesión anterior" real, no un promedio multi-día (así lo pidió el usuario explícitamente).
- `buildAtrAvgMap(history)`: media histórica de `atrPct` por ticker sobre todas las filas disponibles, con contador `n`.
- Componente `TrendArrow({delta, strongTh, mildTh, color})`: 4 niveles con inclinación distinta — `↑↑`/`↗`/`↘`/`↓↓` — más un 5º nivel `flat` que **no** renderiza flecha (evita ruido visual en cambios insignificantes). Umbrales de primera pasada (no calibrados contra datos históricos, es una mejora puramente visual/observacional): Flow Score `strongTh=2, mildTh=0.6` (la escala del Flow Score va de single dígitos negativos a ~50+ en momentum extremo — ver `computeFlowScore` en `shared/flow-score.js`); ATR% `strongTh=0.8pp, mildTh=0.25pp`.
- Celda Flow Score: color de la flecha = `st.fg` (el mismo blanco que ya usa el texto del badge) en vez del color semántico verde/naranja/rojo por defecto — el badge ya tiene fondo saturado (verde/dorado/rojo de `FLOW_STYLE`) y una flecha con su propio color ahí encima quedaba con poco contraste o chocaba visualmente; se decidió tras verlo en pantalla, no a priori.
- Celda ATR%: fondo neutro (blanco), así que ahí la flecha sí usa el color semántico verde/naranja/rojo. Media histórica se muestra como `·X.X%` en gris solo cuando `n>=10` (bootstrap — con menos de 10 sesiones el promedio no es representativo, mismo criterio que el resto del proyecto para features nuevas de observación).

**Nota de bootstrap real:** como `atrPct` nunca se había guardado en `signals_history.json`, en el momento de implementar esto **la tendencia y la media de ATR% no tienen todavía ningún dato previo que mostrar** — empezarán a aparecer a partir de la sesión siguiente a este cambio, y la media a partir de ~10 sesiones/aperturas de la página. Verificado en pantalla: columna ATR% solo con el valor (`7.7%`, `8.9%`, ...), sin flecha ni media, mientras que Flow Score sí mostró flechas reales desde el primer momento (`4.2↑↑`, `-32.0↑↑`, `-29.8↓↓`, y correctamente sin flecha cuando el cambio era insignificante) porque `flowScore` ya llevaba historial acumulado.

**Verificado:** sintaxis JSX transpila sin errores (`@babel/core` + `@babel/preset-react`, ejecutado en Node fuera del navegador ya que el proyecto no tiene esa dependencia instalada localmente — solo carga Babel standalone vía CDN en el propio HTML). Carga real contra `node server.js` con Edge headless (CDP directo): tabla principal de posiciones (`Cartera`, 63 tickers reales) renderiza las flechas de Flow Score con el ángulo y color esperado, tooltip con el delta exacto (`title="+3.00 vs sesión anterior"`), cero errores de consola/excepciones JS. El widget separado "Ranking de Setups" (que también muestra Flow Score) se dejó sin cambios a propósito — el pedido del usuario era sobre "las acciones en el portfolio" (la tabla principal por posición), no ese ranking secundario.

---

## Reintento de tickers fallidos en Koncorde — 2h después del run principal (implementado 2026-08-02)

**Origen:** el usuario notó en `portfolio.html` que MU y GLEN.L no mostraban ningún dato de Koncorde (Blue/Green/Trend/Estado en blanco), a diferencia del resto de sus posiciones. Diagnóstico antes de tocar código: `koncorde_calculator.py → run()` sí incluye **todos** los tickers de `portfolio.json` en el universo (no solo los 91 candidatos del AI Picks Lab — corrección de una respuesta anterior en esta misma sesión que asumía lo contrario sin leer el código). Reproducida la descarga exacta que hace el script (mismo batch de yfinance, mismo rango de fechas): **MU y GLEN.L descargan perfectamente bien**, tanto individualmente como en el batch real de 25 tickers al que pertenecen en el universo actual (201 tickers). El snapshot vigente de `koncorde_data.json` (fecha `2026-08-01`) simplemente no los tiene — conclusión: fallo transitorio de yfinance en esa descarga por lotes concreta (comportamiento no determinista ya conocido de yfinance con `group_by="ticker"`), no una exclusión real ni un problema estructural.

**Caso distinto encontrado en el mismo diagnóstico — `BNKR.TO`:** sí tiene entrada en `koncorde_data.json`, pero con todos los campos `konc_*` a `null`. Causa real, no un fallo: Yahoo solo tiene histórico bajo el símbolo `BNKR.TO` desde 2026-03-25 (90 sesiones) — es el mismo ticker que graduó de TSX Venture (`BNKR.V`) a la bolsa principal el 2026-07-10 (ver commit `e182645`), y el histórico del símbolo viejo no se traspasa al nuevo. `MIN_BARS` exige ≥100 barras para una lectura Diaria — le faltan ~10 sesiones, y 3D/W necesitan bastante más warmup. **No se implementó ningún fix para este caso** — no es un fallo de descarga, es falta de historial real; se resolverá solo según pasen las sesiones.

**Implementación — `scripts/koncorde_calculator.py`:**
- `run()` ahora persiste la lista de tickers fallidos de cada pasada completa en `docs/data/koncorde_failed_state.json` (`{ticker: timestamp_ISO}`), reescribiendo el fichero entero cada vez — un ticker que fallaba y ahora tiene éxito simplemente deja de estar en `failed`, así que desaparece solo del fichero sin lógica de merge.
- `retry_failed(min_age_hours=2.0)`: lee ese estado, reintenta solo los tickers cuyo fallo lleva ≥2h (evita reintentar antes de que Yahoo tenga margen para recuperarse), descarga+calcula solo esos, y hace merge puntual en `koncorde_data.json` existente (no reescribe el fichero completo). Se retiran del estado tanto los que tienen éxito como los que vuelven a fallar — estos últimos se recapturan solos en el siguiente `run()` completo con timestamp nuevo, más simple que llevar la cuenta de reintentos repetidos aquí.
- **Deliberadamente fuera del retry:** inyección de `konc_*` en `ai_candidates.json`, `mirror_signals.jsonl`, `koncorde_signals_history.jsonl` — son artefactos de universo completo pensados para la pasada principal; un reintento parcial de 2-3 tickers no debe tocarlos. Se resuelven solos en el siguiente `run()` completo (máx. 12h después).
- CLI: `python scripts/koncorde_calculator.py --retry-failed` (vs. el `run()` normal sin flag).

**Por qué un workflow nuevo y no un paso dentro del mismo run:** un retraso real de 2h no se puede hacer dentro de un único job de CI sin tener el runner ocioso quemando minutos gratis de GitHub Actions. Se creó `.github/workflows/koncorde-retry.yml`, cron `'0 10,22 * * *'` (10:00/22:00 UTC — 2h después de `market-update.yml`, que corre a las 08:00/20:00), mismo patrón de steps (checkout → setup Python → install deps → run script → commit) que el workflow principal, pero minimalista (sin el resto del pipeline) y con `timeout-minutes: 15`.

**Verificado:** sintaxis Python compila (`py_compile`); YAML del workflow nuevo parseable con PyYAML, mismo resultado que el workflow existente ya funcional (confirma que la clave `on:` como booleano `True` en YAML 1.1 es un no-issue preexistente, no algo introducido aquí). Lógica de `retry_failed` probada end-to-end de forma aislada (paths redirigidos a un directorio temporal, sin tocar datos reales): (1) fallo con timestamp de "ahora" → correctamente NO reintenta y lo deja pendiente; (2) fallo con timestamp de hace 3h → reintenta de verdad contra Yahoo, ambos tickers descargan y se escriben en el `koncorde_data.json` de prueba, y el estado queda vacío tras el éxito; (3) estado vacío → no-op limpio. **Aplicado además contra los datos reales de producción** (no solo la prueba aislada): sembrado `docs/data/koncorde_failed_state.json` con MU/GLEN.L a timestamp de hace 3h y ejecutado `--retry-failed` real — ambos ahora tienen datos de Koncorde reales en `docs/data/koncorde_data.json` (`konc_d_state`/`konc_3d_state`/`konc_w_state` = `up` los tres para ambos), cerrando el gap que reportó el usuario sin esperar al próximo run programado. Cambio no commiteado — queda en el árbol de trabajo para que el usuario lo revise.

---

## Flechas de Flow Score/ATR% — 3 niveles (1/2/3 flechas), recalibrado con datos reales (implementado 2026-08-02)

Ajuste sobre "Flechas de tendencia en Flow Score y ATR%" (sección de más arriba, mismo día). Tras ver las flechas en producción, el usuario pidió dos cosas: (1) reservar 1 sola flecha para un movimiento normal y usar 2/3 flechas solo para movimientos violentos/extremos — el diseño original solo tenía 2 niveles (`↗`/`↘` leve, `↑↑`/`↓↓` fuerte); (2) explicar por qué algunas casillas no mostraban ninguna flecha.

**Diagnóstico de la pregunta 2 antes de tocar nada — con datos reales, no supuestos.** Se descargaron cotizaciones en vivo para los 112 tickers del Portfolio Tracker y se comparó el Flow Score de hoy contra `signals_history.json`: **109/112 tenían sesión anterior válida**. De esos 109: 19 (~17%) tenían un cambio genuinamente insignificante (|delta|<0.6) — sin flecha por diseño, no es un fallo. Solo **GLEN.L** carecía de historial (resuelto aparte, ver sección anterior sobre Koncorde — el fetch de precio para ese ticker no se había completado antes); `TSND.V` y `PLNHF` ni siquiera devolvían cotización (`PLNHF` confirmado "possibly delisted" contra Yahoo directamente). Conclusión: la inmensa mayoría de casillas sin flecha son "cambio de sesión insignificante", no "sin datos" — pero con los umbrales originales (`mildTh=0.6, strongTh=2`) **el 61% de las casillas con dato (67/110) caían ya en el nivel "fuerte"** — demasiado sensible, vaciaba de sentido la distinción que pedía el usuario.

**Recalibración con percentiles reales del propio portfolio**, no umbrales a ojo: distribución de |delta| del Flow Score día-anterior sobre los 109 tickers válidos → p50=2.0, p75=4.8, p80=5.2, p90=7.5, p95=9.8, p98=13.2, máx=17.7. Elegidos `mildTh=0.6` (sin cambios, ya daba ~17% sin flecha, razonable), `strongTh=5` (≈p80) y `extremeTh=10` (≈p95). Resultado verificado en producción tras el cambio: de 63 casillas con dato en la tabla `Cartera`, 15 sin flecha (24%) · 29 con 1 flecha (46%) · 15 con 2 flechas (24%) · 4 con 3 flechas (6%) — distribución con forma de campana, mayoría en "movimiento normal", cola larga hacia lo extremo, tal como se pedía.

**Implementación (`portfolio.html`):** `trendBucket()` pasó de 2 umbrales (`strongTh`/`mildTh`) a 3 (`mildTh`/`strongTh`/`extremeTh`), devolviendo 6 buckets direccionales + `flat`. `TREND_ARROWS` cambió de glifos diagonales (`↗`/`↘` para "leve") a flechas rectas repetidas (`↑`/`↑↑`/`↑↑↑`) — el usuario pidió explícitamente "una flecha hacia arriba" para el nivel normal, no una diagonal; usar el mismo glifo repetido en vez de cambiar de símbolo hace más legible la escalada 1→2→3. `trendColor()` añadió un tercer tono más oscuro/saturado por dirección (`extremeUp:'#063d17'`, `extremeDown:'#7a1810'`) para que el nivel extremo también destaque cromáticamente, no solo por el número de flechas.

**ATR% no se recalibró con datos reales** (mismo motivo que la sección anterior: el historial de `atrPct` empezó a registrarse hoy mismo, no hay deltas reales todavía contra los que calibrar) — se mantuvo `mildTh=0.25`/`strongTh=0.8` del primer diseño y se añadió `extremeTh=1.5` como estimación razonable (no verificada), mismo criterio de "primera pasada, pendiente de revisión con datos" que el resto de umbrales nuevos del proyecto.

**Verificado:** sintaxis JSX transpila sin errores. Carga real contra `node server.js` con Edge headless (CDP directo, proceso aislado por `--user-data-dir` propio y terminado por PID exacto al final — lección aprendida de la sesión anterior, donde un `taskkill /IM msedge.exe` sin filtrar cerró de más). Captura de pantalla de la tabla `Cartera` confirma visualmente los 4 niveles conviviendo en la misma columna (ej. `-29.8 ↓↓↓` en rojo oscuro junto a `4.2 ↑` en dorado y `28.9` sin flecha), cero errores de consola.

---

## Integración de Cava AI — motor de decisión macro externo (en curso, 2026-08-02)

Integración de un sistema experto externo ("Cava AI", destilación del conocimiento del analista José Luis Cava) como capa macro de una cartera nueva. **Fase de diseño y validación histórica COMPLETADA; falta el despliegue en pipeline y el script de cartera.**

### Qué es y qué NO es

No es un LLM: es un **árbol de decisión determinista en Python** (~1200 líneas) sobre un corpus de 112 DecisionFrames extraídos de vídeos diarios. Mismo input → mismo output, sin temperatura. El TipBank (804 tips) **no está conectado al motor** — solo lo usa su chatbot, y no se distribuye en el paquete.

**Hallazgo que reorientó el proyecto:** de nuestros 128 candidatos, solo **3** (NVDA, QQQ, MSTR) solapan con los 137 activos canónicos de Cava — nuestro universo son microcaps del TSX Venture, utilities argentinas, mineras... de las que Cava nunca ha hablado. Los tips a nivel de activo son inaplicables al 98 %. Por eso el rol del agente se reenfocó a **marco estructural** (leer el régimen y dictar el campo de juego), no a selección de tickers. Con eso la cobertura pasa de 3 a **91 de 128 candidatos (71 %)**.

### Arquitectura acordada

- **In-process, no HTTP.** Paquete `pip` desde repo privado con tag fijado (`cava-decision-engine@v1.1.0`). Motivo: GitHub Actions no alcanza un FastAPI local, y fijar versión permite atribuir rendimiento (un agente que cambia a mitad de un periodo de medición invalida los datos de ese periodo).
- **Reparto:** Cava dicta exposición (`deterministic_risk_posture`), AI Picks Lab elige vehículo (PCS). Cava **sustituye** al MacroScore en su cartera, no se mezcla — mezclar haría inatribuible el resultado.
- **1 query al día**, no una por candidato: el régimen es global.

### Ficheros creados

| Fichero | Qué hace |
|---|---|
| `scripts/cava_mapping.py` | Traducción bidireccional: estado macro → vocabulario controlado (7 dimensiones) y categorías de Cava → nuestros `theme`. Enumeración cerrada de 15 categorías como contrato duro. |
| `scripts/test_cava_mapping.py` | **106 tests**, sin pytest. Incluye anclajes con los episodios reales de 2024-08, 2025-04 y 2026-03. |
| `scripts/cava_state_history.py` | Reconstruye el estado macro de cualquier fecha desde 2004, sin mirar al futuro. Caché de precios en `docs/data/_cava_price_cache.parquet` (gitignorable). |
| `scripts/cava_test_1c.py` | Prueba 1C — validación histórica sobre 20 años. |
| `wiki/AGENTE_EXTERNO_*.md` | 8 documentos: cuestionario inicial, rondas 2-5, notas pre-desarrollo, verificación de la entrega y resultados. |

**El motor externo vive en `C:/Users/Kunio/Dropbox/AI/cava-decision-engine`** (fuera de este repo), importado por ruta absoluta en `cava_test_1c.py`.

### Resultados de la Prueba 1C (5.408 sesiones, 2005-2026)

```
postura         n     fwd 3m   peor 1m   vol 1m
risk_on      2177      2.24%    -2.19%   12.20%
risk_off      852      2.40%    -4.65%   26.63%
```

- **Como predictor de retorno: NO funciona.** `risk_on` tiene el peor retorno a 3 meses, por debajo de `risk_off`. Usarlo para decidir cuándo estar invertido sería peor que estar invertido siempre (2,95 % de media).
- **Como discriminador de riesgo: SÍ funciona.** `risk_off` precede al doble de volatilidad y al doble de caída máxima.
- **Bate a nuestro MacroScore en separación de riesgo:** 14,4 pp de volatilidad vs 11,9 pp; 2,46 pp de drawdown vs 2,23 pp. Y lo hace operando "ciego" de crédito antes de 2023-08 (el spread HY no existe antes en FRED), así que estos números **infravaloran** el marco completo.
- Nuestro MacroScore sufre **la misma inversión** en retorno (`Risk-OFF` precede al mejor retorno a 3 meses) — no es defecto del marco de Cava, es la naturaleza del dato: los suelos son a la vez lo más peligroso y lo de mejor retorno posterior.

**Decisión derivada:** `deterministic_risk_posture` modula **exposición**, nunca selección, y `risk_off` significa "no añadir riesgo", **no** "vender todo" — cerrar en `risk_off` sería justo el error que los datos desaconsejan.

### Dos errores propios detectados por la verificación (documentados para no repetirlos)

1. **Rama muerta en `cava_mapping.py`:** `DRAWDOWN_WEAK` y `NEAR_HIGHS_PCT` valían ambos −3.0, así que el estado `range` era inalcanzable. Mismo patrón que el `fragile_no_technical` de `rotacion.html`. Lo detectó un test, no una revisión.
2. **Reconstrucción en cadencia semanal:** borraba las caídas que se recuperan dentro de la semana. De los episodios de estrés de 2024-2026 solo 2 de 3 se registraban; el desarme del carry del yen (agosto 2024, VIX diario 38,6) desaparecía entero. Reescrito para que **cada dimensión use su cadencia real** — precio/volatilidad/crédito diarios, liquidez y régimen semanales.

### Cartera CAVA_MACRO — en marcha desde 2026-08-03

`scripts/cava_portfolio.py` (Step 10d del pipeline, `continue-on-error: true`).
Primer `--apply` ejecutado: 10 posiciones abiertas, 10 filas en `shadow_picks.jsonl`.

**Reparto:** Cava decide cuántas posiciones (postura) y qué temas son elegibles
(categorías) · PCS decide qué tickers · las salidas son mecánicas.

**La postura se aplica BINARIA, no en escalera.** Es la decisión menos obvia y la
que más fácil sería "mejorar" mal en el futuro, así que los números están escritos
junto a la constante `MAX_POSITIONS_BY_POSTURE`. Medido sobre las 5.345 sesiones
con dato de futuro:

```
postura       %tiempo  caída media  mediana  % meses malos    vol   fwd 3m
risk_on           40%       -2.20%   -1.33%           12%   12.1%    2.24%
reduce_risk       34%       -2.29%   -1.19%           13%   14.2%    3.09%
neutral           11%       -2.63%   -1.80%           17%   17.1%    5.96%
risk_off          16%       -4.65%   -3.10%           34%   26.6%    2.40%
```

- `reduce_risk` **no** es más peligroso que `risk_on` (13 % de meses malos frente
  a 12 %, mediana de caída incluso menor) y rinde bastante más. Recortar ahí, un
  tercio del tiempo, costaría retorno sin evitar riesgo.
- El orden de las etiquetas **no sigue al riesgo**: `neutral` es más peligroso que
  `reduce_risk`. Cualquier escalera sobre esos nombres estaría construida sobre
  distinciones que los datos no sostienen.
- Solo `risk_off` separa: 34 % de meses malos, casi el triple. Ahí se corta a cero.

**`risk_off` no cierra posiciones**, solo impide abrir nuevas: su retorno posterior
es mejor que el de `risk_on` (los suelos rebotan), así que vender ahí sería el
error que los datos desaconsejan.

**Salidas mecánicas** (`review_positions`), reutilizando los criterios que ya usa
el resto del sistema: `left_universe`, `pcs < 62`, `rot_score <= 2`, más un
trailing stop del 25 % desde máximos como **cortacircuitos** — está para que una
posición no se vaya a cero sin que nadie se entere, no para hacer timing; de ahí
que sea ancho (nuestro universo son small caps con ATR de varios puntos).

**Dos topes de concentración, no uno.** Además del máximo de 3 por `theme` que
fijó su equipo, hay un tope de 4 por categoría de Cava: sanidad ocupa dos temas
nuestros (`healthcare_largecap` y `healthcare_special`) que son una sola categoría
suya, y sin el segundo tope la primera versión metió 6 de 10 posiciones en
sanidad — justo el sector donde Cava declara no tener opinión.

**Expectativa a vigilar:** de 37 candidatos elegibles el primer día, solo 3 caían
en categorías que Cava favorece; el 92 % quedó como "sin opinión". En la práctica
Cava decide cuántas posiciones y el PCS decide cuáles. El log de cada run guarda
`n_cava_favored` vs `n_no_opinion` para que dentro de unos meses sea un dato
medido y no una impresión.

### PENDIENTE para retomar

1. ~~Verificar que el secret `CAVA_ENGINE_TOKEN` está en GitHub Actions.~~
   **Confirmado y arreglado 2026-08-07.** No estaba — `gh secret list` no lo
   listaba, y los logs de **todas** las corridas del pipeline desde el
   2026-08-03 (~18 corridas, 2×/día) mostraban `CAVA_TOKEN: ` vacío →
   `fatal: Authentication failed` en el `pip install` → `cava_portfolio.py
   --apply` fallando con `No module named 'cava_engine'`. Ambos pasos tienen
   `continue-on-error: true`, así que el pipeline entero se marcaba
   "success" en la pestaña Actions — el fallo llevaba 4 días siendo
   invisible ahí, mismo patrón exacto que el incidente del token de Telegram
   vacío (ver sección correspondiente). La cartera llevaba esos 4 días
   congelada con las 10 posiciones originales del único `--apply` manual,
   sin ninguna revisión ni entrada nueva. El usuario añadió el secret;
   verificado que autentica (`git ls-remote` contra el repo privado en
   local) y disparado un `workflow_dispatch` manual para confirmar
   end-to-end en CI real: `pip install` completó, `cava_portfolio.py
   --apply` corrió — 5 salidas mecánicas (`pcs < 62`, suelo absoluto:
   III.L/OSCR/YPF/PAM/KOS) + 5 entradas nuevas (URI/GS/PLTR/SE/DHR) — y
   Telegram notificó los 5 cierres, confirmando en producción por primera
   vez el fix de `"event":"close"` de más abajo (que llevaba desde el
   2026-08-03 sin verificar por falta de cierres reales).
2. ~~El primer run del pipeline con esto dentro no se ha visto.~~ Visto
   arriba — era el mismo problema del punto 1.
3. **`entry_price` de las 5 posiciones nuevas queda a `null`** hasta el
   siguiente pase (mismo patrón ya documentado: entran antes del cierre,
   `update_performance` necesita una sesión cerrada) — autocorregible, no
   requiere seguimiento activo.
4. **Prueba 1B** (circuito completo sobre los 76 payloads de may-ago 2026) — sin
   hacer. Es comprobación de fontanería, no de rentabilidad: ese periodo es
   uniformemente alcista.
5. **Empaquetado**: pedimos mover `corpus/` dentro de `cava_engine/` y resolver
   la ruta desde el módulo; su equipo lo hizo y `pip install` funciona desde
   fuera del repo (verificado). El `Homepage` del `pyproject.toml` sigue
   apuntando a `cava-ai/decision-engine`, que no existe — despistó una vez ya.
6. La validación real sigue siendo el **forward testing en modo sombra**, no el
   backtest. Empezó el 2026-08-03, pero de facto no operó hasta el
   2026-08-07 por el punto 1 — el reloj de "cuántas semanas de forward
   testing llevamos" debería contarse desde aquí, no desde el 2026-08-03.

**Bug encontrado y corregido (2026-08-03): CAVA_MACRO no aparecía en el dashboard.**
`ai_picks.json` ya tenía las 10 posiciones reales del primer `--apply`, pero
`docs/index.html` nunca se actualizó al añadir la cartera — las pestañas de AI
Picks Lab se generan desde `Object.keys(PTF_LABELS)` (línea ~773), y `PTF_LABELS`/
`PTF_THRESHOLDS` (línea ~732) no tenían la entrada `CAVA_MACRO`, así que la
posición existía en los datos pero no tenía dónde renderizarse. Mismo patrón que
tener que añadir cada cartera nueva a `_PORTFOLIO_LABELS` en `paper_trading.py`
para Telegram — aquí es el equivalente en el dashboard, y se quedó fuera al
crear la cartera. Arreglado añadiendo `CAVA_MACRO` a `PTF_LABELS` ('Cava Macro'),
`PTF_THRESHOLDS` (62, el `PCS_MIN_ENTRY` real de `cava_portfolio.py`) y a
`GROK_PTFS` del mini-panel de overview (portada) — cuenta como posición "Grok"
porque el vehículo lo elige PCS igual que el resto de carteras Grok, Cava solo
decide postura/categorías elegibles. La tabla de posiciones usa el layout
genérico (mismas columnas que el resto): como las posiciones de Cava no tienen
`conviction`/`rationale`/`entry_signal`, esas columnas caen a '—' — funcional,
no roto, pero menos informativo que en otras carteras; no se creó una columna
específica con `theme`/`cava_favor` por mantener el fix acotado al bug de
visibilidad reportado.

**Bug encontrado y corregido (2026-08-03): los cierres mecánicos de CAVA_MACRO
y MIRROR_ESPEJO nunca disparaban el aviso de Telegram.** Al confirmar quién
abre/cierra las posiciones de CAVA_MACRO (`cava_portfolio.py` mismo, sin IA:
`select()` para altas, `review_positions()` para bajas — `left_universe`,
`pcs<62`, `rot_score<=2`, trailing stop 25%), se detectó que `review_positions()`
añadía cada cierre a `ptf["history"]` con `close_date`/`close_price`/
`close_reason` pero **sin** la clave `"event": "close"` — solo la pone
`update_portfolio()` en `paper_trading.py` para los cierres decididos por la IA.
`mirror_portfolio.py` (cartera Espejo, implementada 2026-07-03) tenía el mismo
problema desde el principio. `notify_telegram.py → _find_unnotified()` filtra
los cierres exactamente con `if ev.get("event") != "close": continue` — sin esa
clave, el cierre nunca entra en `new_closes`. No es un retraso: como el estado
de notificados (`notify_state.json`) solo registra lo que sí se llega a enviar,
un cierre así se queda sin avisar para siempre, no solo hasta el siguiente run.
`docs/index.html` no se ve afectado (su render de "Historial de operaciones" no
exige `event==="close"`, solo trata distinto a `event==="open"` — comentario
explícito en el código sobre por qué, ya pensado para Espejo). Arreglado
añadiendo `"event": "close"` en los dos puntos donde falta (`cava_portfolio.py
→ review_positions()`, `mirror_portfolio.py` → cierre por trailing stop).
**Verificado en producción 2026-08-07** (ver punto 1 de "PENDIENTE para
retomar" más arriba): los primeros 5 cierres reales de CAVA_MACRO
dispararon aviso de Telegram correctamente (`notify_telegram.py` reportó
"5 close(s) not yet notified" → "OK"). MIRROR_ESPEJO sigue sin verificar —
no ha cerrado ninguna posición todavía.

---

## Diagnóstico CONFIRMED_FLOW_LEADERS — fixes + shadow logging (implementado 2026-08-05)

El usuario preguntó cómo evaluar el rendimiento de las carteras de AI Picks
Lab. Al mirar `shadow_picks.jsonl` se encontraron dos problemas de datos antes
de poder responder con confianza: 9 posiciones "zombi" de mayo cerradas de
golpe el 2026-06-10 (el cierre de posiciones no existía hasta el 2026-06-09,
ver sección "Cierre de posiciones" — no reflejan decisiones del modelo) y,
al indagar más, **26+ filas realmente duplicadas** (mismo modelo, ticker,
fecha y PCS) causadas por re-ejecuciones manuales del mismo día. Con eso
limpio, CONFIRMED_FLOW_LEADERS (CFL) mostró underperformance real y
consistente (alpha vs SPY -5%, no explicado por el mercado) y un patrón claro:
el retorno a 1 semana predice fuertemente el de 1 mes (corr +0.72, solo 2/30
picks negativos a 1 semana recuperan a 1 mes) en las 4 carteras, no solo CFL.
Diagnóstico completo, datos crudos y metodología en
`wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md`.

El usuario revisó ese diagnóstico y aprobó un plan acotado — arreglar la causa
raíz de los duplicados, e instrumentar (no operar) la hipótesis de salida a 1
semana antes de considerar activar nada real:

### P0 — fix del bug de duplicados (en la fuente, no solo en el análisis)

`_log_shadow_picks()` (`paper_trading.py`) — nueva función
`_todays_shadow_signatures(today)` que lee las filas ya escritas hoy en
`shadow_picks.jsonl` y construye el set de `(model, ticker, portfolio, pcs)`
ya vistos; antes de escribir cada selección se comprueba esa firma y se
descarta si es idéntica. **Deliberadamente no deduplica por fecha+ticker sin
más** — si el mismo modelo reevalúa el mismo ticker el mismo día con un PCS
distinto (información nueva real), se loguea igual; solo se descarta la
repetición exacta. No toca duplicados ya escritos en el histórico (ver abajo).

`compare_vs_baselines.py` gana `dedup_same_day_reruns()`, aplicado nada más
cargar `shadow_picks.jsonl` en `run_analysis()`: colapsa `(model, ticker,
portfolio, date)` a la primera ocurrencia cronológica del día. Limpia tanto el
histórico ya escrito antes del fix de arriba como cualquier duplicado futuro
que se cuele por otra vía. `build_run_groups()` ya deduplicaba por `(ticker,
portfolio)` pero solo **dentro de un mismo `run_id`** — no servía contra el
caso real encontrado (6 `run_id` distintos el mismo día, 10:13 a 11:00,
claramente ejecuciones manuales de prueba). Verificado en producción:
`--no-fetch` sobre los datos reales reporta "dropped 32 same-day rerun
duplicates (246 raw -> 214 unique market events)".

### P1 — `scripts/cfl_followthrough_shadow.py` (Step 10f, shadow-only)

Evalúa cada posición abierta de CFL una sola vez, en cuanto cumple ~5 sesiones
(`RET_1W_TRADING_DAYS`) desde la entrada — dedup por `position_id =
f"{ticker}__{entry_date}"` contra lo ya logueado, así que una posición nunca
se re-evalúa. **Nunca toca `ai_picks.json`** — no cierra nada, solo escribe a
`docs/data/cfl_followthrough_shadow.jsonl`.

Cuatro reglas evaluadas por posición: `ret_1w_negative` (la única validada en
el diagnóstico — es la que decide `shadow_decision`), `ret_1w_below_minus3`,
`ret_1w_vs_spy_below_minus2`, `atr_adjusted_breach` (pérdida > 1× el ATR% de
entrada — `None` si no hay ATR de entrada disponible). También registra
`mfe_1w`/`mae_1w` (máximo favorable/adverso en la primera semana),
`entry_extension_risk` (buscado primero en `shadow_picks.jsonl` en vivo, si no
en el reconstruido de P2) y `current_pcs`/`current_rot` desde
`ai_candidates.json`. `entry_rot` queda `None` — no se captura hoy en el
momento de la entrada en ningún sitio estructurado (solo aparece en texto
libre dentro de `rationale`); no se intentó parsear ese texto por ser frágil.

Verificado contra la única posición CFL abierta ahora mismo (TMO, entrada
2026-07-25): `ret_1w=+1.02% -> WOULD_HOLD`. Segunda ejecución inmediata
confirma dedup ("All open CFL positions already evaluated").

### P2 — `scripts/reconstruct_extension_risk_historical.py` (Step 10e)

`extension_risk` es un campo en fase de observación desde 2026-05-16, pero un
bug de lookup en `_log_shadow_picks` (arreglado 2026-07-02, ver sección
"Koncorde Plus v2") lo dejó a `null` en ~96% de los picks históricos — justo
la variable necesaria para separar "se entró tarde" de "se eligió mal" en el
diagnóstico de CFL. Este script lo reconstruye por ticker+fecha de entrada,
**usando solo barras con fecha ≤ entry_date** (sin look-ahead), y reutiliza
`pcs_calculator.compute_extension_risk()` **importada directamente** (no
reimplementada) para que la puntuación no pueda desincronizarse — mismo
criterio que motivó centralizar `HARD_RULES` en `ai_shared.py`.

Campos nuevos que no existían en el cálculo en vivo (pedidos explícitamente
para este diagnóstico): `atr_pct`, `atr_percentile_126d`,
`bb_width_percentile_126d`, `days_since_20d_high_breakout`,
`days_since_55d_high_breakout`. Salida en
`docs/data/extension_risk_reconstructed.jsonl`, idempotente (dedup por
ticker+fecha, `--force` para recomputar).

**Bug real encontrado en la primera pasada:** `atr_percentile_126d` salía
idéntico para todas las fechas del mismo ticker — la función de percentil
recibía la serie de ATR completa (hasta hoy) en vez de recortada hasta
`entry_date`, es decir, look-ahead real colándose en un script diseñado
explícitamente para evitarlo. `bb_width_percentile_126d` sí estaba bien
recortada desde el principio (`.iloc[:pos+1]`) — sirvió de contraste para
detectar que ATR no lo estaba. Corregido antes de escribir ningún dato real.

**Validado contra 4 picks que ya tenían `extension_risk` calculado en vivo**
(post-fix 2026-07-02): coincidencia exacta en las 4, incluidos los puntos
(`AFM.V`, `LLY`, `ROOT`, `SE`) — no solo el nivel de riesgo.

**Primer resultado real sobre CFL** (185 ticker-fecha reconstruidos; n
pequeño, no concluyente): `extreme` sale claramente peor que el resto
(ret_1m medio -16% a -18%, 0% de aciertos, n=4-5), pero `low`/`medium`/`high`
no forman una escalera limpia — no hay evidencia todavía de que "entrar
extendido" sea la explicación principal del underperformance de CFL, solo de
que el extremo superior lo es. Pregunta abierta, no resuelta por este cambio.

### P3 — `scripts/cfl_reentry_cooldown_shadow.py` (Step 10g, shadow-only)

Pregunta: si CFL reentra repetidamente en los mismos nombres (ASPI 11 veces,
SASK.V 11 veces — ver diagnóstico §3.6), ¿qué pasaría si un ticker que acaba
de fallar follow-through a 1 semana (`ret_1w<0`) quedara bloqueado para
reselección 18 sesiones (punto medio del rango 15-20 pedido)?

**A diferencia de P1/P2, este script reconstruye su salida entera cada vez**
en lugar de acumular con append — documentado explícitamente en el docstring
del script: el veredicto de cooldown de un pick depende de si los picks
*anteriores* de ese ticker fallaron, y `ret_1w` de esos picks anteriores llega
de forma asíncrona vía `update_performance.py` días después de loguearse el
pick. Un log append-only habría congelado el veredicto de cada pick con la
información parcial que existía el día en que se evaluó por primera vez.
Reconstruir es barato (cálculo puro sobre un jsonl local pequeño, sin red), así
que ese trade-off sale gratis.

Corre enteramente retroactivo sobre `shadow_picks.jsonl` (con el mismo dedup
de P0 y la misma exclusión del bloque zombi que el diagnóstico) — no necesita
descargar precios nuevos porque `ret_1w`/`ret_1m` ya están ahí. Resultado real
sobre las 18 selecciones activas limpias de CFL: solo 2 habrían sido
bloqueadas por el cooldown (SASK.V, URI) — muestra demasiado pequeña para
saber si el cooldown habría ayudado.

### Pipeline

Los tres scripts nuevos corren como Steps 10e/10f/10g en
`.github/workflows/market-update.yml`, después de Step 10b
(`update_performance.py`, para que `ret_1w`/`ret_1m` estén frescos) y antes de
Step 11 (Telegram). Los tres con `continue-on-error: true` — son observación
pura, un fallo no debe tumbar el resto del pipeline. `git add docs/data/` en
el step de commit ya es recursivo, así que los tres archivos de salida nuevos
se commitean sin tocar el workflow más allá de añadir los steps.

### Explícitamente fuera de alcance (por ahora)

No se activó ningún stop real, no se subió el umbral de PCS, no se cambió el
sizing, no se declaró CFL "invalidada", no se añadió ninguna HARD_RULE nueva.
Criterio acordado con el usuario para promover cualquiera de estas reglas
shadow a real: ~100-150 eventos independientes, al menos 2 regímenes de
mercado distintos, validación fuera de muestra, y mejora de expected value sin
cortar demasiados ganadores futuros. Con n=18-48 y un solo régimen de 3 meses,
ninguna de las reglas de este cambio cumple ese criterio todavía.

---

## Ranking Score + PCS reframing — plan revisado y preregistro firmado (2026-08-06)

El usuario propuso un plan de implementación grande (PCS reframing + Ranking
Score shadow + cartera experimental `RANKING_SHADOW_EXPERIMENTAL`) para
atacar el hallazgo del diagnóstico CFL: el PCS no ordena rendimiento por
encima del umbral (corr global PCS↔ret_1m = -0.007, ver sección "Diagnóstico
CONFIRMED_FLOW_LEADERS" más arriba). Antes de arrancar, se revisó el plan
contra el estado real del repo — varias de sus asunciones ya estaban
resueltas o eran verificables directamente:

- **P0 (dedup) ya estaba hecho.** El plan lo pedía como paso previo
  obligatorio; se implementó el 2026-08-05 (ver sección CFL). El -0.007 que
  cita el plan como motivación ya es la cifra post-dedup.
- **La pregunta abierta del plan sobre si es viable retropoblar
  `pcs_components` históricos tiene respuesta: sí.** `pcs_calculator.py` ya
  calcula y persiste `pcs_components` (A-F) en `ai_candidates.json` en cada
  run, y ese archivo se commitea 2×/día desde 2026-05-08 (174 commits). Se
  reconstruye con `git show <commit>:docs/data/ai_candidates.json` en vez de
  recalcular — es el valor real del momento de la decisión.
- **Cobertura verificada con datos reales, no asumida** (159 picks
  2026-05-09→07-07, deduplicados): `extension_risk` 100% (ya reconstruido),
  `rot_score` reconstruible al 100% vía git-history (presente desde el
  primer commit), `theme_breadth` reconstruible por el mismo método,
  `konc_3d_state`/`konc_w_state` con techo real de solo ~15% incluso con
  reconstrucción — Koncorde no existía como feature en `ai_candidates.json`
  antes de 2026-06-30 (confirmado en git history), no es un gap de logging
  recuperable. Cobertura en candidatos **en vivo** (hoy): 100% en todos los
  campos — el gate de cobertura del plan no bloquea Fase 2, solo acota lo
  que Fase 1 puede analizar retrospectivamente.

**Decisiones tomadas con el usuario antes de firmar el preregistro:**
1. Recortar el peso documental del plan original (informes de 20-30 páginas,
   preregistro extenso) manteniendo el mismo rigor estadístico — preregistro
   de ~2 páginas, informes de Fase 1/3 de 3-5/5-8 páginas en vez de 10-15/20-30.
2. **Fusionar el Koncorde Research Log** (recordatorio `koncorde_research_log_revision`,
   agendado para 2026-08-18) dentro de la Fase 1 del Ranking Score en vez de
   mantenerlo como review independiente — mismo dataset, misma metodología,
   evitaba duplicar trabajo y arriesgaba veredictos contradictorios sobre el
   mismo dato. Koncorde no tiene camino de promoción independiente; su
   promoción a componente operativo va acoplada a la del Ranking Score.
   Recordatorio cancelado en `docs/data/reminders.json`, sustituido por
   `ranking_score_fase1_analisis` (2026-09-03).
3. Dado el hallazgo de cobertura (~15% de techo para Koncorde en el dataset
   histórico vs 100% para el resto), Koncorde se evalúa en Fase 1 en una
   **subsección separada** con su propia n e IC95%, nunca mezclada en las
   mismas tablas que componentes con historial completo desde 2026-05-08.
   Clasificación provisional; si entra en el Ranking Score shadow, peso
   inicial conservador dentro del bucket Flow Institucional.

**Preregistro firmado:** `wiki/PREREGISTRO_RANKING_SCORE_V0.md` — lista
congelada de componentes/pesos, reglas de `RANKING_SHADOW_EXPERIMENTAL`,
7 baselines shadow, criterios de promoción a piloto/productivo, criterios de
descarte anticipado, checklist de registro de cartera nueva (dashboard/
Telegram/evento `close`) para no repetir el bug ya visto dos veces con
`CAVA_MACRO` y `MIRROR_ESPEJO`.

**Estado:** preregistro firmado. Fase 0.2/0.3/0.4 (campos PCS + persistencia +
retropoblación) implementada 2026-08-07 — ver detalle abajo. Pendiente de
Fase 0: los dos scripts de reconstrucción vía git-history para
`rot_score_delta`/`theme_breadth` (necesarios antes de Fase 1, no antes de
poder usar los campos PCS ya implementados).

### Fase 0.2/0.3/0.4 — campos PCS reframing + persistencia + retropoblación (implementado 2026-08-07)

Aditivo puro sobre `pcs_calculator.py` — no cambia la fórmula del PCS, los
6 componentes A-F ni la elegibilidad. Definiciones tomadas literalmente del
plan de implementación original (pegado por el usuario 2026-08-06, texto
completo recuperado y usado como fuente de verdad en vez de inferir):

```
pcs_raw        = pcs (alias, mismo valor, claridad semántica en datasets con varias variantes pcs_*)
pcs_ex_macro   = pcs_raw - component_A   (aísla la parte que sí varía entre tickers en la misma corrida)
pcs_ceiling    = 95.0 constante          (techo real, ver wiki/ASESOR_EXTERNO_PCS_INFORME.md §5)
pcs_normalized = (pcs_raw / pcs_ceiling) × 100   — SOLO display/análisis, nunca decisiones
component_A..F          = mismo valor que pcs_components (alias top-level, más cómodo para análisis tabular)
component_A..F_ceiling  = 14.0 / 24.0 / 23.0 / 20.0 / 9.0 / 5.0 (constantes, del mismo informe)
```

**Persistencia (0.3) — en los 4 sitios que documentan una decisión** (no solo
`ai_candidates.json`):
- `docs/data/ai_candidates.json` — automático, campos añadidos a `compute_pcs()`.
- `docs/data/ai_model_payloads/YYYY-MM-DD.json` — vía `compact_candidate()` en
  `scripts/ai_shared.py` (compartido con `build_eval_bundle.py`, que hereda el
  cambio sin tocarlo — mismo motivo por el que existe ese archivo compartido).
- `docs/data/shadow_picks.jsonl` — vía `_log_shadow_picks()`, valor en el
  momento de la selección.
- `docs/data/ai_picks.json` — vía `update_portfolio()`, con prefijo `entry_`
  (`entry_pcs_raw`, `entry_pcs_ex_macro`, ...) siguiendo la convención ya
  existente (`entry_price`, `entry_pcs`, `entry_signal`) — se añadió un
  parámetro `cand_snapshot` nuevo a `update_portfolio()` (antes solo recibía
  `cand_pcs`, un mapa ticker→pcs) y se pasó en ambos call sites (cartera
  activa y carteras shadow).
- `docs/data/model_tests/YYYY-MM-DD_{model}.json` — **no aplica** (verificado):
  ese archivo guarda la respuesta cruda del modelo + metadata de validación,
  nunca el desglose de PCS del candidato, así que no hay nada que persistir ahí.

**Fuera de alcance deliberado:** `cava_portfolio.py` y `mirror_portfolio.py`
tienen su propia lógica de apertura de posición (no pasan por
`update_portfolio()`) y no ganaron estos campos — no estaban mencionados en
el plan original, y Cava/Espejo no usan el PCS de la misma manera (Espejo no
usa PCS en absoluto; Cava lo usa solo como puerta binaria ≥62). Si más
adelante se necesitan ahí, es un cambio aparte.

**Retropoblación histórica (0.4)** — el plan dejaba esto como pregunta abierta
("¿es viable?"). Respuesta verificada: **sí, 100% viable**, porque
`pcs_components` (desglose A-F) lleva en `docs/data/ai_candidates.json` desde
el primer commit (2026-05-08, confirmado vía `git log --follow`) con el mismo
esquema de claves sin cambios. A diferencia de `extension_risk` (que necesitó
recomputar desde OHLCV con una fórmula proxy) o Koncorde (que no existía como
feature antes de 2026-06-30), aquí el valor histórico real ya está commiteado
— no hace falta aproximar nada, solo **leerlo** de la snapshot correcta.

Script nuevo: `scripts/reconstruct_pcs_components_historical.py`. Para cada
tupla (ticker, fecha, pcs) de `shadow_picks.jsonl`, busca entre los commits de
`ai_candidates.json` del mismo día natural (el pipeline corre 1-3×/día, así
que puede haber varias snapshots por fecha) el que tenga exactamente ese `pcs`
para ese ticker — el cruce por valor de PCS desambigua entre corridas AM/PM
del mismo día sin ambigüedad. Si no hay match exacto el mismo día, amplía a
±1 día (cubre picks logueados cerca de la medianoche UTC). Sin match exacto en
ningún commit: la fila queda `reconstructed: false` — nunca se aproxima ni se
inventa. Salida: `docs/data/pcs_components_reconstructed.jsonl` (mismo patrón
que `extension_risk_reconstructed.jsonl`: append-only, dedup por
ticker+fecha+pcs, `--force` para recomputar, `--dry-run` para previsualizar,
`--report` para ver cobertura).

**Resultado real (190 picks únicos en `shadow_picks.jsonl`, 2026-05-08 →
2026-08-06):** 189/190 reconstruidos (99.5%) — 187 con match exacto el mismo
día, 2 (`SASK.V`, `VGZ`, 2026-06-20) con match en el día anterior, 1 sin
match (`CLS`, 2026-06-24 — el propio registro en `shadow_picks.jsonl` no
tenía `pcs` logueado, no es un fallo de esta reconstrucción). Verificado
cruzando manualmente una fila reconstruida (`AFM.V`, 2026-07-04) contra
`git show <commit>:docs/data/ai_candidates.json` del commit real — coincidencia
exacta en pcs_components y en la suma A-F = pcs.

**No se implementó en este cambio** (parte de la lista "trabajo pendiente"
del preregistro §0, no de la Fase 0.2-0.4 original): los scripts de
reconstrucción de `rot_score_delta` y `theme_breadth` vía git-history —
necesarios antes de Fase 1, pero conceptualmente distintos (dependen de
definir la ventana de comparación y la agrupación por tema) y no bloquean el
uso de los campos PCS ya implementados aquí. **Implementados el 2026-08-07,
ver siguiente sección — con esto Fase 0 del preregistro queda completa.**

### Fase 0 — cierre: reconstrucción de rot_score_delta y theme_breadth (implementado 2026-08-07)

Los dos scripts que quedaban pendientes de §0 del preregistro
(`wiki/PREREGISTRO_RANKING_SCORE_V0.md`), mismo patrón de
`reconstruct_pcs_components_historical.py` — **importan `list_commits()`,
`candidates_at_commit()` y `find_match()` de ese script en vez de
reimplementarlos**, para que la lógica de desambiguación AM/PM por `pcs`
exacto no pueda desincronizarse entre los tres.

**`scripts/reconstruct_rot_score_delta_historical.py`** — `rot_score_delta_4w`
por ticker+fecha: `rot_score` del snapshot de entrada menos `rot_score` del
snapshot más cercano a `entry_date - 28 días naturales` (ventana de búsqueda
±5 días alrededor de ese objetivo, prefiriendo el día más cercano; sin match
en esa ventana → `null`, nunca aproximado). Salida:
`docs/data/rot_score_delta_reconstructed.jsonl`.

**`scripts/reconstruct_theme_breadth_historical.py`** — `theme_breadth` por
ticker+fecha: nº de candidatos `eligible=true` con el mismo `theme` en el
snapshot del día de entrada (ambos campos ya viven en cada candidato de
`ai_candidates.json`, es un lookup directo, no un recálculo). También guarda
`theme_total` (elegibles + no elegibles) de contexto. Salida:
`docs/data/theme_breadth_reconstructed.jsonl`.

Ambos con las mismas flags que el resto de la familia de scripts de
reconstrucción (`--force`, `--dry-run`, `--report`), dedup por
ticker+fecha+pcs, idempotentes.

**Resultado real (190 picks únicos en `shadow_picks.jsonl`):**
`theme_breadth` 189/190 reconstruido (el único hueco es `CLS` 2026-06-24, la
misma fila sin `pcs` logueado que ya dejaba sin reconstruir a
`pcs_components_reconstructed.jsonl` — no es un fallo de este script).
`rot_score_delta_4w` 106/190 (56%) — los 84 sin reconstruir se concentran casi
todos en picks de las primeras ~4 semanas del sistema (2026-05-08 →
~2026-06-05), donde "28 días antes" cae fuera del propio arranque del
historial de git — un límite real de los datos, no un bug de la ventana de
búsqueda (verificado: el resto de huecos sueltos fuera de ese rango son
tickers que esa semana no estaban en el snapshot cercano, p. ej. por rotar
fuera del universo de 91 candidatos, y quedan `null` correctamente en vez de
aproximarse).

**Con esto, Fase 0 del preregistro queda completa.** Próximo paso: Fase 1
(informe descriptivo de 3-5 páginas sobre estos componentes + PCS reframing +
Koncorde en subsección separada), agendada para 2026-09-03
(`ranking_score_fase1_analisis` en `docs/data/reminders.json`).

**Nota 2026-08-07 (revertido):** se llegó a adelantar e implementar Fase 1
completa el mismo día (script + informe + resultados) a petición puntual del
usuario, pero se revirtió tras aclarar el motivo de la fecha 2026-09-03: no
era una dependencia de código sino dar tiempo a que maduraran datos —
heredado del recordatorio `koncorde_research_log_revision` (2026-07-21,
"revisión prevista en 4-8 semanas"), fusionado en esta Fase 1 el 2026-08-06.
El intento adelantado (n=48) ya mostraba el problema: `rot_score_delta_4w`
solo tenía n=14 y Koncorde n=5 (la mitad de esa muestra era el mismo evento
de mercado contado dos veces), justo la falta de potencia estadística que la
fecha de septiembre estaba pensada para evitar. Se recupera el plan
original: Fase 1 espera a 2026-09-03.

---

## Backtest histórico de Relative Flow Lab — descartado como señal (implementado 2026-08-08)

Plan aprobado el 2026-08-07 (`wiki/PLAN_RELATIVE_FLOW_LAB_BACKTEST.md`) y
ejecutado completo al día siguiente: reconstruir históricamente el scoring
de `relative.html` (45 ratios, Score/Leader-Improving-Weakening-Laggard/
Trend) desde precios reales de yfinance y comprobar si predice alfa vs SPY,
con la misma disciplina dev/test + preregistro ya usada en Ranking Score
(`wiki/PREREGISTRO_RANKING_SCORE_V0.md`) para no "jugar con combinaciones"
sin red de seguridad.

**Ficheros nuevos:**
- `scripts/relative_flow_lib.py` — puerto vectorizado literal de
  `alignRatio`/`ret`/`retWindow`/`sma`/`calcRSI`/`buildRow`/`classify`
  (`relative.html` líneas ~143-219). RSI de Wilder como pase único
  expandible desde el origen de cada serie — converge al mismo valor que
  la ventana de 3 años re-sembrada de la página en vivo pasadas ~300
  barras (memoria exponencial de Wilder).
- `scripts/test_relative_flow_lib.py` — 47 tests sin pytest, incluido un
  **chequeo dorado**: las funciones JS reales de `relative.html` ejecutadas
  en Node contra `/api/history/:symbol` en `server.js` real, comparadas
  contra la reconstrucción Python. Coincidencia casi exacta en pares sin
  dividendo relevante en la ventana (`ura_urnm`, `gdxj_gdx`); en `xlk_spy`
  (yield no trivial) diverge ~0.1-0.35pp en r3m/r6m/score por el ajuste de
  dividendo (`auto_adjust=True` en la reconstrucción vs sin ajustar en
  `server.js`) — desviación declarada de antemano en el plan, magnitud
  confirmada pequeña.
- `scripts/reconstruct_relative_flow_historical.py` — descarga
  `period="max"` para los ~47 tickers únicos del registry, reconstruye
  228.893 filas diarias (45 pares × histórico completo, 1998-2026 según el
  ETF) con retorno futuro a 5/21/63 sesiones sobre el calendario propio de
  cada activo (nunca el del ratio alineado). Reconstrucción completa en
  cada ejecución, no append-only. Salida
  (`docs/data/relative_flow_history_reconstructed.jsonl`, **163MB — NO
  commiteada**, por encima del límite duro de 100MB/archivo de GitHub;
  añadida a `.gitignore` junto con la cache de precios
  `_relative_flow_price_cache.parquet`; regenerable en ~2-3 min con
  `--save-cache` la primera vez y `--no-fetch` después).
- `scripts/analyze_relative_flow_signal.py` — baseline incondicional,
  correlación (Pearson+Spearman, IC95% vía Fisher z), stats por grupo
  (label×trend, t-test vs. baseline) y grid search (~200 combinaciones,
  `label×trend` + `score_min×trend` × 3 horizontes), todo sobre el jsonl ya
  reconstruido — sin red, barato de re-ejecutar. `--confirm-test` solo
  evalúa las combinaciones ya congeladas en el preregistro, con aviso
  explícito en consola — mismo patrón de "barrera de código" que
  `ranking_score`/`cava_mapping`.
- `wiki/PREREGISTRO_RELATIVE_FLOW_LAB_V0.md` — GRID congelado, corte
  dev/test (fecha única, hoy−365 días naturales, no % por par), regla de
  selección (top-3 por horizonte desde dev, congeladas antes de tocar
  test) y criterio modesto de "plausible" (mismo signo dev/test, win
  rate≥55%, n≥20) fijados **antes** de correr el grid search real.
- `wiki/RELATIVE_FLOW_LAB_HALLAZGOS.md` — informe completo.

**Resultado: el score no predice alfa futuro de forma útil.** Correlación
pooled score↔alfa indistinguible de cero en 1w/1m/3m (r=-0.009/+0.003/
+0.012, mismo orden de magnitud que el hallazgo PCS↔ret_1m=-0.007 de
`wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md`). Del grid search en dev, las
top-3-por-horizonte congeladas (7 combinaciones distintas tras dedup) se
evaluaron una sola vez en test: **6 de 7 no soportadas** (la mayoría
invierte el signo entre dev y test), **1 de 7 "plausible"**
(`label=Leader, trend=Mixed, horizonte 3 meses`: dev mean α=+1.02, test
mean α=+1.28, win rate=57.1%, n=63) — con ~200 combinaciones probadas sin
corrección por comparaciones múltiples, 1 superviviente de 7 es
aproximadamente lo esperable por azar, no una confirmación fuerte. El
único matiz por `type`: `anticipation` es el único bucket con correlación
positiva y creciente con el horizonte (r=0.068 a 3m), pero demasiado
pequeña (r²<0.5%) para ser accionable.

**No se integra nada en `paper_trading.py`, `pcs_calculator.py` ni ninguna
cartera viva** — alcance de investigación desde el inicio, confirmado por
los propios resultados. Mismo patrón que el hallazgo de PCS: el score
funciona como filtro narrativo/interpretativo para lectura humana, no como
ranking predictivo.

**Continuación 2026-08-10:** una exploración interactiva posterior sobre
esta misma herramienta (fuera del repo) sugirió una posible señal dentro
del ruido — ver la sección "Relative Flow Family Falsification Test v1"
más abajo para el resultado final (hipótesis refutada).

---

## Relative Flow Family Falsification Test v1 — hipótesis refugio/industrial refutada (2026-08-10)

Tras el backtest formal (sección anterior) hubo una exploración interactiva
adicional, no preregistrada, inspeccionando manualmente la herramienta de
revisión construida sobre ese backtest (tabla + gráfico + calculadora de
rentabilidad, mantenida fuera del repo por decisión explícita — ver
`wiki/ASESOR_EXTERNO_RELATIVE_FLOW_REFUGIO_VS_INDUSTRIAL.md`). Esa
exploración sugería que la regla "entrada paso-a-Improving / salida
cualquiera-de-las-dos" batía a comprar-y-mantener en activos refugio/
monetarios/especulativos (GLD, SLV, GDXJ, BTC, ETH) y perdía sistemáticamente
en materias primas industriales (cobre, platino, paladio, DBB, XME/GDX),
medido con Δ TAE (rentabilidad anualizada sobre días con posición abierta).

Se diseñó y ejecutó una prueba preregistrada para intentar refutarlo —
`wiki/PREREGISTRO_RELATIVE_FLOW_FAMILY_TEST_V1.md`, versión acotada (Capa
1+2: universo congelado, métrica primaria, placebos básicos, leave-one-out,
correlación intra-familia, Bonferroni ×4 — sin escalar a costes/1.000
simulaciones/sub-muestras temporales/forward OOS). Universo de 37 activos
en 4 familias (`backtest/config/relative_family_test_v1.yaml`), script y
salidas en `research/relative_flow_family_test_v1/` (fuera de las rutas
productivas, mismo criterio que el resto de esta exploración).

**Resultado: hipótesis refutada — NOT SUPPORTED.** La corrección
metodológica central del test (usar `excess_CAGR_calendar` — CAGR de la
estrategia con cash cuando está fuera, sobre el calendario completo — en
vez de Δ TAE, que solo anualiza sobre días expuestos) revierte casi por
completo el hallazgo original: mediana de familia refugio = -25.73,
mediana de familia industrial = -25.93 — prácticamente empatadas, en la
dirección contraria a la hipótesis. Mann-Whitney y test de permutación dan
p≈0.52-0.58 en crudo, p=1.000 tras Bonferroni ×4 (por las 4 hipótesis ya
probadas informalmente en la exploración previa: retorno propio, sin
rendimiento intrínseco, tipos/divisa, refugio/industrial). Ninguno de los
criterios preregistrados de "suggestive" se cumple de forma conjunta.

**Causa mecánica del espejismo original, no un error de cálculo:** oro y
plata subieron mucho en términos absolutos en el periodo (+77%/+130% de
buy&hold); la estrategia solo estuvo invertida ~20-25% del tiempo. Δ TAE
premia comprimir una ganancia en pocos días de exposición sin penalizar el
coste de oportunidad de estar fuera el resto del tiempo — en un mercado
alcista amplio y sostenido (casi todos los activos de las 4 familias
tuvieron `excess_CAGR_calendar` negativo, no solo los industriales), eso
basta para producir una separación aparente que no sobrevive a una métrica
que sí cuenta el tiempo fuera del mercado.

**Lo que sí sobrevive, sin ser el hallazgo principal:** el placebo de
bootstrap por bloques (100 sims, bloques de 20 sesiones) sugiere que el
timing de la señal no es puro ruido en varios activos concretos
(percentiles 70-91 en GLD, COPX, PICK, BTC, GDXJ frente a la distribución
aleatoria) — pero esa estructura no sigue la frontera refugio/industrial
(aparece y desaparece en ambos lados). La señal invertida funciona
sustancialmente mejor que la primaria en cobre/platino/paladio/XLE,
sugiriendo posible dirección invertida en ese subconjunto. Ninguno de los
dos matices se opera ni se investiga más — cada uno necesitaría su propio
preregistro, no una reinterpretación de estos datos.

**Sin impacto en el sistema en vivo** — no se toca `paper_trading.py`,
`pcs_calculator.py`, ninguna cartera ni el motor IA, tal como estaba
acordado desde el inicio de la exploración. Puerta dura del preregistro
resuelta como "descartar" — no se escala a la versión completa del test
(costes × 3, 1.000 simulaciones, sub-muestras temporales, forward OOS): el
resultado ya es inequívoco con la versión acotada, más rigor no cambiaría
la conclusión.

---

## Principio: métrica primaria para estrategias con exposición intermitente (2026-08-10)

Derivado directamente del hallazgo anterior. **Ninguna estrategia con
exposición <50% del calendario debe evaluarse con una métrica anualizada
solo sobre días expuestos** (Δ TAE, retorno medio por trade × frecuencia,
o cualquier variante que mida "cuánto se gana estando dentro" sin penalizar
"cuánto se pierde por no estar dentro"). La métrica primaria debe ser
`excess_CAGR_calendar`: CAGR de la estrategia (con retorno 0% o proxy de
cash los días fuera de mercado) menos CAGR de comprar-y-mantener el propio
activo/benchmark, ambos anualizados sobre el mismo calendario completo de
la ventana. Métricas exposure-based pueden reportarse como secundarias,
nunca como base de decisión.

**Por qué:** en un mercado alcista sostenido, cualquier estrategia con baja
exposición pierde frente a buy&hold por el coste de oportunidad de estar en
cash, aunque cada operación individual sea rentable — Δ TAE puede mostrar
+50 puntos de "alfa" en una estrategia que en realidad perdió -25 puntos
frente a simplemente aguantar la posición todo el periodo (caso real, ver
sección anterior). En un mercado bajista el efecto se invierte y Δ TAE
tampoco lo captura bien.

**Aplicar retroactivamente** a cualquier análisis futuro de reglas de
entrada/salida en Relative Flow Lab, a Ranking Score si se plantea con
exposición intermitente, y a cualquier baseline mecánica shadow calculada
sobre subconjuntos del universo. Mismo espíritu que el resto de disciplina
de este proyecto (preregistro antes de mirar datos, placebos con misma
exposición, baseline mecánica siempre al lado — ver
`wiki/PREREGISTRO_RANKING_SCORE_V0.md`).

---

## Detalle de subastas (indirect/dealer) + módulo nuevo CoT Positioning (implementado 2026-08-10)

Un asesor externo propuso 4 mejoras sobre el sistema (detalle de subastas,
posicionamiento CFTC, breadth de mercado propio, componentes diarios de Net
Liquidity). Antes de implementar nada se verificó cada afirmación contra
datos reales — dos de las cuatro no eran del todo exactas:

- **Auction Stress (punto 1, correcto):** `indirect_bidder_accepted`,
  `primary_dealer_accepted` y `direct_bidder_accepted` sí están en el mismo
  endpoint `auctions_query` de Treasury Fiscal Data que ya usa
  `/api/treasury-auctions` — solo faltaba pedirlos.
- **Net Liquidity diario (punto 4, parcialmente incorrecto — no implementado):**
  RRPONTSYD es diario en FRED (ya se fetchea a diario), pero **WTREGEN
  (TGA) es semanal**, no diario — verificado contra observaciones reales de
  FRED (cada 7 días exactos). TGA diario de verdad exigiría cambiar de
  fuente al Daily Treasury Statement de Treasury FiscalData, no "pedirle
  más a FRED". Diferido — no se ha tocado nada de Net Liquidity en esta
  ronda.
- **Breadth de mercado propio (punto 3): diferido** — requeriría un
  universo de cientos de acciones (vs. los ~45-90 tickers de cualquier otro
  módulo del proyecto) y la información ya entra al sistema hoy vía los
  subcomponentes del Fear & Greed en `sentiment.html`.

### 1. Auction Stress — indirect bidders y dealer takedown (`server.js`)

`/api/treasury-auctions` amplía el `fields` pedido con
`indirect_bidder_accepted,primary_dealer_accepted,direct_bidder_accepted,total_accepted`
y calcula `indirect_pct`/`dealer_pct`/`direct_pct` (% del total aceptado) +
comparación vs. la media de las 8 subastas recientes del mismo tenor —
mismo patrón que ya existía para `high_yield`/`bid_to_cover`. **No** se ha
metido todavía en `auction_stress_proxy` (fase de observación, mismo
criterio que `extension_risk`/Koncorde: exponer primero, calibrar un umbral
real después de ver datos).

**Bug real encontrado y corregido durante la implementación:** `sort=-auction_date`
también trae subastas **anunciadas pero no ejecutadas todavía** (fecha en
el futuro), con todos los campos numéricos en `null` porque el resultado
aún no existe. Sin filtrar esto, "la más reciente" para 10Y/30Y podía ser
una subasta que ni siquiera había pasado — produciendo el propio
"insufficient_data" que motivó la mejora. Arreglado filtrando
`auction_date <= hoy` antes de elegir la última subasta de cada tenor.

**Verificado contra datos reales (2026-08-10):** 2-Year (29/7): indirect
56,9% / dealer 33,1% / direct ~0% — típico de una nota corta. 10Y (12/5) y
30Y (13/5, antes del fix quedaban ocultas tras la subasta anunciada del
12-13/8): indirect ~52-54% / dealer ~9-10% / direct ~18-19% — reparto
plausible para deuda larga. 30Y salió `weak_demand` por yield/bid-to-cover
mientras indirect/dealer apuntaban en sentido contrario (indirect +2,3pp,
dealer -1,7pp) — confirma en vivo por qué no se ha fusionado todavía con el
proxy de estrés: las dos lecturas no siempre coinciden.

### 2. CoT Positioning — módulo nuevo (`positioning.html`, `/api/cot/:contract`)

Página nueva, mismo patrón que `sentiment.html`/`duration.html` (React +
Babel standalone, fetch client-side, export a LLM). Cubre posicionamiento
semanal de Managed Money ("specs") en Oro, Plata, Cobre y WTI Crude —
elegidos por ser justo los activos trabajados en la exploración de
Relative Flow Lab de estos días (ver sección "Relative Flow Family
Falsification Test v1" más arriba).

**Fuente:** CFTC Commitments of Traders, informe "Disaggregated Futures
Only" (API pública Socrata, `publicreporting.cftc.gov/resource/72hh-3qpy.json`).
Semanal (viernes, posiciones del martes anterior) — cache de 12h en
`/api/cot/:contract`.

**Bug real encontrado antes de integrar (mismo patrón que el mislabeling
TIPS-vs-nominal de `/api/treasury-auctions`):** el nombre de contrato
"obvio" para WTI Crude Oil en este dataset — `CRUDE OIL, LIGHT SWEET - NEW
YORK MERCANTILE EXCHANGE` — lleva **congelado desde 2022-02-01**,
confirmado contra la API real. CFTC renombró el contrato principal a
`WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE` en algún punto intermedio.
Usar el nombre viejo habría servido un dato de más de 4 años de antigüedad
en silencio. Los otros tres (`GOLD - COMMODITY EXCHANGE INC.`,
`SILVER - COMMODITY EXCHANGE INC.`, `COPPER- #1 - COMMODITY EXCHANGE INC.`)
sí tenían el nombre esperado, verificado con datos frescos (2026-08-04)
antes de fijarlos en `COT_CONTRACTS`.

**Cálculo:** `mm_net` = largos − cortos de Managed Money. Percentil sobre
la ventana de historial disponible en el dataset (~170 semanas, ~3,3 años)
— umbrales de interpretación (≥90 extremo largo, ≤10 extremo corto)
fijados a ojo, sin calibrar contra rendimiento futuro (misma fase de
observación que el resto de features nuevas del proyecto).

**Verificado con datos reales (2026-08-04):** Oro percentil 58 (neutral),
Plata percentil 32 pese al rally reciente (no está sobre-posicionada,
contra la intuición inicial), **Cobre percentil 100** (extremo largo real
— exactamente el tipo de lectura que motivó pedir este módulo), WTI
percentil 34.

**Nav pill "Positioning" (`#5d4037`)** añadida a las 7 páginas raíz
existentes (`index.html`, `portfolio.html`, `relative.html`, `cycle.html`,
`rotacion.html`, `duration.html`, `sentiment.html`), y entrada
`llm_export_positioning` sumada al array `parts` compartido de exportación
a LLM en las 8 páginas (ahora 8 entradas).

**Fuera de alcance (explícito):** no se ha fusionado el percentil de
positioning con ninguna señal existente (extension_risk, auction_stress_proxy,
Koncorde) — cada una vive observacionalmente hasta que haya evidencia que
justifique combinarlas. No se toca PCS, rot_score, HARD_RULES ni ninguna
cartera.

---

## Relative Flow Lab — Optimización v2, Fase 1.2 (tabla firmada) + Fase 1 de código (implementado 2026-08-10/11)

Continuación del rediseño de `relative.html` documentado en "Relative Flow
Lab v2 — ratio_registry y vista por pregunta" (arriba). Una hoja de
instrucciones externa ("Relative Flow Lab — Optimización v2") pedía
reorganizar los 45 ratios del registry en una taxonomía nueva
(RISK-ON/OFF, ANTICIPACIÓN, ROTACIÓN, REGIONES, BACKGROUND) y añadir varios
ratios nuevos.

**Fase 1.2 (2026-08-10) — auditoría antes de tocar código.** Se escaneó el
estado real de `shared/relative-ratio-registry.js` (commit `3d4f30b`,
congelado en `backtest/config/rfl_current_state_frozen.yaml`) en vez de
fiarse del inventario de la hoja/asesor externo, y se encontraron 7
discrepancias reales: `GDXJ/GDX`, `SMH/IGV` e `IWD/IWF` ya existían en
producción (la hoja los daba por "nuevos"); `XLK/SPY` ya existía, solo le
faltaba promoción visual; `DXY/GLD` y `FXI/EEM` no existían en absoluto
(la hoja los daba por existentes); `BTC-USD/GLD` no es el par real, que es
`BTC-USD/GC=F`. Tabla de reasignación firmada y congelada en
`wiki/RFL_CLUSTER_REASSIGNMENT_TABLE.md` — de las 45 filas, **solo 2 ratios
cambian realmente de sección** (`TLT/SPY`, `XLK/SPY`); el resto de la
"nueva taxonomía" confirma el mapeo `type` ya existente sin cambios.

**Fase 1 de código (2026-08-11) — reasignación quirúrgica de 2 ratios +
infraestructura de persistencia**, alcance explícitamente acotado a lo que
la tabla firmada dejaba listo para arrancar (los 5 ratios nuevos reales de
"Fase 2" — `HYG/LQD`, `VVIX/VIX`, `USDJPY/Nikkei`, `DX-Y.NYB/GC=F`,
`IJS/IJT` — quedan fuera, no se añade ningún ticker nuevo en este cambio):

1. **`shared/relative-ratio-registry.js`:** `tlt_spy` pasa de
   `type: "sector_snapshot"` a `type: "risk_appetite"`
   (`signalDirection: "higher_is_risk_off"`) — termómetro directo de
   refugio en duración, mismo nivel que `HYG/SPY`/`XLU/XLY`, no encajaba en
   sector_snapshot por omisión. `xlk_spy` pasa de `sector_snapshot` a
   `rotation` ("promoción visual", ya existía, ahora se muestra una sola
   vez en su bloque nuevo — sin duplicar). El campo `cluster` (narrativo,
   usado solo por la Cluster Coherence View secundaria) no se toca en
   ningún ratio, tal como fija la tabla firmada.

   **Auditabilidad — por qué TLT/SPY no cuenta en el Risk Appetite
   Monitor:** el monitor (`riskOffCount`/`riskAppetiteCountable` en
   `relative.html`) contaba hasta ahora 6 de los 7 ratios `risk_appetite`
   (excluye `QQQ/RSP` por `signalDirection: "contextual"` — sin lectura
   risk-on/off inequívoca). Mover `TLT/SPY` a `risk_appetite` sin más lo
   habría sumado al agregado, pasando el denominador de `/6` a `/7` y
   alterando un umbral que ya lleva semanas en producción, sin ninguna
   evidencia que lo justifique. Decisión explícita con el usuario: se
   muestra en la tabla (con lectura direccional real, no "Contextual" —
   TLT/SPY sí tiene lectura inequívoca, a diferencia de QQQ/RSP) pero
   **no cuenta** en el agregado. Mecanismo: campo nuevo
   `countedInMonitor: false` en el registry (no se reutilizó
   `signalDirection: "contextual"` para esto porque corrompería su
   semántica — ese valor significa "sin lectura direccional", y aquí sí la
   hay). `riskOffCount`/`riskAppetiteCountable` en `relative.html` ganan el
   filtro `m.countedInMonitor !== false`; la columna "Dirección" ya
   existente en la tabla muestra `· no cuenta` para las filas marcadas así,
   mismo tratamiento visual que el "Contextual" de `QQQ/RSP`.

2. **`relative.html`:** sin cambios en la lógica de los `QuestionBlock` —
   al iterar genéricamente sobre `DEFS_BY_TYPE` por `type`, la reasignación
   del registry basta para reubicar `TLT/SPY` y `XLK/SPY` en su bloque
   nuevo. Nueva persistencia diaria: `relative_flow_history` en
   `state.json` (via `/api/state`, hasta ahora sin usar en esta página),
   un array por cada uno de los 45 ratios con `{date, score, signal,
   flowChange, type}`, mismo patrón de dedup-por-día y cap de 70 entradas
   ya usado para `rotation_history` en `rotacion.html`
   (`rotacion.html:1592-1625`) — reescrito aquí porque cada página del
   proyecto mantiene su propia copia de estos helpers, sin módulo
   compartido. **Bloqueante para una futura Fase 2 de lectura dinámica**
   (deltas/flechas de tendencia, análoga a la ya construida en
   `rotacion.html`) — en este cambio solo se siembra el dato, no se
   consume todavía.

3. **`server.js`:** `relative_flow_history: {}` añadido a `DEFAULT_STATE`,
   junto a `rotation_history: {}`. La ruta `/api/state` (GET/POST) ya era
   genérica — no necesitó cambios.

**Fuera de alcance (explícito):** los 5 ratios nuevos de Fase 2; cualquier
UI que lea `relative_flow_history` (deltas, flechas); renombrado de las
etiquetas de UI existentes (hoy en inglés) a la nomenclatura española de
la tabla firmada — se trató como gloss conceptual de planificación, no
como copy pendiente de aplicar.

**Verificado en producción real** (Edge headless vía CDP directo, mismo
patrón que el resto del proyecto — sin Playwright instalado, servidor
`node server.js` reiniciado tras el cambio en `server.js`): header del
Risk Appetite Monitor se mantuvo en `4/6 warnings` (no `/7`) tras la
reasignación; fila de `TLT/SPY` visible en esa tabla con badge
Risk-On/Risk-Off/Neutral real (no "Contextual") y marca `· no cuenta`;
`XLK/SPY` aparece únicamente en el bloque "Rotation Between Blocks" (8
filas, antes 7) y desapareció de "Sector Relative Snapshot" (14 filas,
antes 16, sin duplicar en ningún sitio); Cluster Coherence View sigue
agrupando ambos ratios bajo `SECTOR ROTATION` sin cambios (confirma que
`cluster` no se tocó); cero errores nuevos de consola. `state.json` quedó
con `relative_flow_history` poblado para los 45 ratios tras la primera
carga; una segunda carga el mismo día no duplicó ninguna entrada (dedup
confirmado). Export a LLM (`buildRelativeMarkdown`/`llm_export_relative`
en `localStorage`) verificado con contenido real: incluye `TLT/SPY`, la
marca `no cuenta`, el denominador `4/6 defensive`, y `XLK/SPY` solo en la
sección de Rotación — sin cambios de código adicionales, al derivarse
genéricamente de los mismos `DEFS_BY_TYPE`.

---

## Relative Flow Lab — Optimización v2, Fase 2 (5 ratios nuevos) (implementado 2026-08-11)

Continuación directa de la sección anterior. Los 5 ratios que la tabla
firmada dejaba pendientes (`wiki/RFL_CLUSTER_REASSIGNMENT_TABLE.md`,
sección "Ratios nuevos reales de Fase 2") se añadieron a
`shared/relative-ratio-registry.js` — registry pasa de 45 a 50 ratios.
Antes de tocar código se verificó cada ticker nuevo contra `/api/history/`
en vivo (mismo criterio que `XOP` en la sección "Cluster SECTOR ROTATION"
o el fix `ARCH→CNR` en Cycle Tracker — no asumir que un ticker resuelve):
`HYG`, `LQD`, `^VVIX`, `^VIX`, `JPY=X`, `^N225`, `DX-Y.NYB`, `IJS`, `IJT`
— los 8 con 731-778 barras en 3 años y sin huecos en las últimas 30
sesiones. Esto también resuelve la duda de "Ratios a evaluar por
velocidad (Fase 2.2)" que la tabla dejaba abierta para `IJS/IJT` — datos
limpios, sin bloqueante.

**`hyg_lqd`** (High Yield vs Investment Grade, `HYG`/`LQD`) y **`vvix_vix`**
(Vol-of-Vol vs Volatility, `^VVIX`/`^VIX`) — ambos `type: risk_appetite`,
cluster RISK APPETITE. **Decisión explícita con el usuario: sí cuentan en
el agregado del Risk Appetite Monitor** (denominador pasa de `/6` a `/8`)
— a diferencia de `TLT/SPY` (Fase 1, arriba), que quedó excluido por ser
la *reasignación* de un ratio con historial previo bajo otra clasificación.
Estos dos son ratios genuinamente nuevos sin ese problema de continuidad,
y el monitor ya había crecido antes sin fricción (de 4 a 6 ratios
contables en el rediseño de julio) — mismo criterio de expansión normal,
no una excepción.

**`usdjpy_nikkei`** (`JPY=X`/`^N225`) y **`dxy_gld`** (`DX-Y.NYB`/`GC=F`,
id mantenido como `dxy_gld` por convención con `copper_gold`/`silver_gold`/
`btc_gold` aunque el ticker real ya no sea `GLD`) — ambos `type: regions`,
sub-cat `fx_estructural` por ser el bucket más cercano de los 5 de la
taxonomía firmada (no hay un bucket "FX" propio). **`signalDirection:
"contextual"` en ambos**, no `higher_is_bullish` como el resto de
`regions` — decisión propia de esta sesión, no especificada en la tabla
firmada: `USDJPY/Nikkei` no es una comparación región-vs-región limpia
como `EEM/URTH`, y el propio proyecto ya trata USDJPY como
direccionalmente ambiguo en `duration.html` (yields↑+TLT↓+USDJPY↓ puede
ser repatriación limpia, o un shock de yields/dólar genérico que no
confirma la tesis Japón) — mismo criterio aplicado aquí por consistencia,
y extendido a `DXY/GLD` por construcción análoga (dólar fuerte vs oro
también es estructuralmente ambiguo: puede ser demanda de dólar por tipos
reales, no necesariamente vuelo a la seguridad).

**`ijs_ijt`** (Small Cap Value vs Growth, `IJS`/`IJT`) — `type: rotation`,
cluster STYLE / FACTOR, mismo eje que `IWD/IWF` en su versión small-cap.

**Verificado en producción real** (Edge headless vía CDP, `node
server.js` reiniciado tras el cambio en el registry): Risk Appetite
Monitor pasó a 10 filas con header `5/8 warnings` (no `/6` ni un número
distinto de 8); bloque Regions ganó `USDJPY vs Nikkei` y `Dollar Index vs
Gold` (6 filas, antes 4); bloque Rotation ganó `Small Cap Value vs Growth`
(9 filas, antes 8 tras la Fase 1); cluster `STYLE / FACTOR` en la Cluster
Coherence View muestra ahora `IWD/IWF` e `IJS/IJT` juntos, coherencia
100% calculada correctamente sobre los 2; cero errores nuevos de consola.
`state.json` → `relative_flow_history` pasó a 50 claves tras la carga,
con las 5 nuevas sembradas y las 45 anteriores sin duplicar (mismo día,
dedup correcto).

**Fuera de alcance (sin cambios respecto a la Fase 1):** `TLT/IEF` y
`EDV/IEF` (prioridad media en el plan original) siguen pendientes — el
usuario ya había apuntado que probablemente encajan mejor en
`duration.html`, evaluar ahí antes de decidir dónde viven. Lectura
dinámica sobre `relative_flow_history` (deltas/flechas) sigue sin
empezar — el usuario priorizó explícitamente esta Fase 2 de ratios sobre
esa fase de lectura al elegir cómo continuar.

---

## Relative Flow Lab — lectura dinámica sobre `relative_flow_history` (implementado 2026-08-11)

Continuación directa de la sección anterior — el usuario eligió esta fase
(deltas/flechas de tendencia) sobre completar los ratios `TLT/IEF`/`EDV/IEF`
pendientes. Puerto directo del patrón ya construido en `rotacion.html`
(Flujos & Rotación v2, Fase 2: `findHistEntryAtOrBefore`/
`computeRotationDynamics`/`SIGNAL_RANK`) sobre `relative_flow_history` en
`state.json`, sembrado desde la Fase 1 de código de RFL v2 pero sin
consumirse hasta ahora.

**`relative.html`:** `findHistEntryAtOrBefore` (idéntica, "closest at or
before N days ago", sin exigir hueco exacto de 7 días — esta pestaña
tampoco tiene cron propio) + `RATIO_SIGNAL_RANK` (`Leader:5 > Improving:4 >
Neutral:3 > Weakening:2 > Laggard:1`, orden de `classify()`) +
`computeRelativeFlowDynamics(history, currentScore, currentSignal)` →
`{delta1w, arrow, badge, weeksInSignal}`, mismos umbrales que rotacion
(`≥+2`→↗, `≤-2`→↘) porque el score de RFL usa la misma escala que sus
propios cortes de clasificación (Leader≥8, Improving≥3).

`rowsByType` (consumido por los 4 `QuestionBlock`) gana `row.dyn`, leído de
`appState.relative_flow_history[row.id]`. Nuevo `relFlowHistoryBootstrap`
(mismo criterio que `rotHistoryBootstrap`: `ready` solo si han pasado ≥7
días naturales desde el primer snapshot) gatea todo — antes de eso, Δ1W/
Sem./badge muestran `—`, nunca un delta inventado, con nota explicativa
bajo "📍 Question-Based Views".

**Alcance deliberadamente acotado a las 4 tablas por pregunta**
(anticipation/rotation/regions/sector_snapshot) — no se tocó el Risk
Appetite Monitor (su clasificación es risk-on/risk-off/neutral, no
Leader..Laggard; extender `SIGNAL_RANK` ahí habría exigido un esquema de
orden distinto, no pedido) ni las tablas de Cluster View/Raw Ratio Tables
(usan `rowsByGroup`, una agrupación paralela por `cluster` que recalcula
`buildRow` independientemente de `rowsByType` — mismo patrón de
redundancia ya existente antes de este cambio, no introducido aquí). No se
implementó el widget separado "Rotaciones detectadas" con nota de cautela
citando el Family Test v1 que preveía el plan original de 6 fases para su
propia "Fase 3" — eso queda como pieza distinta, no pedida en este alcance.

**Export a LLM (`buildRelativeMarkdown`):** las 4 tablas por tipo ganan
columnas `Δ1W`/`Sem.` y el badge se anexa entre corchetes al label de
Signal (`Leader [UPGRADED]`), mismo patrón que `[UPGRADED]`/`[DOWNGRADED]`
en el export de `rotacion.html`. Nota de bootstrap añadida al final del
bloque si `!ready`.

**Verificado en producción real** (Edge headless vía CDP directo, proceso
aislado por `--user-data-dir` propio y terminado por PID exacto resuelto
vía `netstat` — no por `taskkill /IM msedge.exe`, lección ya documentada en
la sección de flechas de Flow Score/ATR%): sintaxis JSX transpila sin
errores (`@babel/standalone` en Node, instalado en un proyecto npm aparte
en el scratchpad de la sesión, no en el repo); carga real contra `node
server.js` sin excepciones nuevas — los 4 `QuestionBlock` muestran las
columnas `Δ1W`/`Sem.` en el orden esperado, celda de ejemplo con `—`/`—`
(bootstrap correctamente no listo el mismo día en que se sembró el
histórico) y el resto de columnas con datos reales; nota de bootstrap
visible en el DOM. `state.json` → `relative_flow_history` confirmado con
50 claves, cada una con 2 entradas (`2026-08-10`, `2026-08-11`) tras varias
cargas de verificación el mismo día — dedup diario correcto, no duplicó
ninguna entrada de hoy. `localStorage.llm_export_relative` verificado con
contenido real: incluye las columnas `Δ1W`/`Sem.` y la nota de bootstrap.

**Fuera de alcance:** `TLT/IEF`/`EDV/IEF` (sin cambios, ver sección
anterior); Fase 4 (Top 3 in/out, reemplaza "Top 5 Flow Change"); Fase 5a/5b
(matriz cross-módulos con Cycle Tracker + `rotation_history` de
`rotacion.html`); Fase 6 (instrumentación de uso).

---

## Relative Flow Lab — Fase 4: Top 3 Flow In/Out (implementado 2026-08-11)

Reemplaza el panel "Top 5 Flow Change" (ranking crudo por `flowChange`,
solo positivo) por un panel "Top 3 Flow In/Out": dos listas de 3 (entradas
más coherentes / salidas más coherentes), con un toggle "Sin filtro" que
recupera el ranking crudo anterior sin perder esa vista.

**Filtro de coherencia — criterio acordado explícitamente con el usuario**
antes de implementar, porque el texto original del plan de 6 fases (que
mencionaba un "filtro de coherencia adaptativo" opcional) nunca se
commiteó al repo y solo sobrevivía como resumen en memoria, sin la fórmula
exacta. Mismo principio que ya usa el Early Flow Detector de esta misma
página (flowChange + RSI + r1m + trend deben confirmarse entre sí, no un
solo indicador aislado) — evita que un pico de `flowChange` de un único
día, sin respaldo del score o de la tendencia de medias, aparezca como
señal de rotación real. Formulación simétrica:

```
Entrantes: flowChange > 0  AND score >= 0  AND trend !== "Down"
Salientes: flowChange < 0  AND score <= 0  AND trend !== "Up"
```

Implementado en `coherentFlowDirection(row)` (`relative.html`). `topFlowIn`/
`topFlowOut` filtran `flatRows` por esta función y ordenan por `|flowChange|`
descendente, top 3 cada uno — pueden salir vacíos si ningún ratio cumple
las tres condiciones ese día (mensaje "Sin candidatos coherentes hoy" en
vez de forzar 3 filas). El toggle (`flowFilterOff`, estado local del
componente) alterna entre esta vista filtrada y el `accelerationRows`
crudo que ya existía (top 5 por `flowChange`, sin ningún filtro) — ambas
conviven, no se perdió ninguna capacidad.

**Export a LLM (`buildRelativeMarkdown`):** sección `## Top 3 Flow In/Out`
con las dos subtablas (`### Entrando`/`### Saliendo`) y el criterio de
coherencia en texto, seguida de `## Top 5 Flow Change (sin filtro)` con el
ranking crudo — ambas versiones se exportan siempre (a diferencia de la
UI, el markdown no tiene estado de toggle interactivo).

**Verificado en producción real** (Edge headless vía CDP, PID resuelto por
`netstat` y terminado exacto): sintaxis JSX transpila sin errores; carga
real contra `node server.js` sin excepciones nuevas; panel por defecto
("Sin filtro" visible como opción, filtro activo) mostró 3 entrantes (XME/SPY,
GLD/SPY, GDX/GLD, todas con score≥0 y trend no-Down) y 3 salientes
(JPY=X/^N225, HG=F/GC=F, BTC-USD/GC=F, todas con score≤0 y trend no-Up) —
consistente con el criterio; clic real en el botón (vía CDP, no simulado)
confirmó el toggle: pasa a "Top 5 Flow Change (sin filtro)" con 5 filas
(el quinto puesto, XLB/SPY, no habría entrado en la vista filtrada por no
tener los tres signos alineados) y el botón cambia a "Con filtro". Export
a LLM verificado con contenido real: ambas secciones presentes, criterio
de coherencia incluido como texto.

**Fuera de alcance:** Fase 5a/5b (matriz cross-módulos con Cycle Tracker);
Fase 6 (instrumentación de uso); `TLT/IEF`/`EDV/IEF` (sin cambios).

---

## Relative Flow Lab — Fase 5a: matriz de coherencia cross-módulos (implementado 2026-08-11)

Cruza `relative.html` con Cycle Tracker (`cycle.html`) y Flujos & Rotación
v2 (`rotacion.html`) — los tres módulos independientes del proyecto que
leen "hacia dónde se mueve el capital" con horizontes distintos. El texto
original del plan de 6 fases de RFL v2 (que mencionaba esta matriz) no
sobrevivió commiteado en ningún sitio; el diseño exacto (estructura de
tabla, 5 estados de coherencia, lenguaje interpretativo, mapping sectorial
previo obligatorio) se reconstruyó con el usuario antes de escribir código
— mismo patrón ya usado para el filtro de Fase 4.

### 1. `wiki/MAPPING_SECTORIAL_CANONICO.md` (nuevo, firmado antes del código)

Precondición explícita pedida por el usuario: sin fijar qué ticker/fase/
ratio de cada módulo representa el "mismo" sector, la matriz cruzaría
cosas distintas bajo el mismo nombre y daría falso consenso o falsa
divergencia. Verificado contra el código real de los tres módulos (no
asumido): de las 10 fases clásicas de `CYCLE_MAP`, **8 tienen cobertura
completa en los 3 módulos** (Technology, Capital Goods, Materials, Oil &
Gas, Staples, Healthcare, Utilities, Financials & Cyclicals — Staples y
Healthcare se separan en 2 filas porque `rotacion.html`/RFL las tratan
como sectores independientes aunque compartan fase "Early Bear"); 3 no
(Transportation — sin ticker en `rotacion.html` `UNIVERSE` ni en el
registry de RFL; Uranium — sin ticker en `UNIVERSE`; Coal & Steel Inputs —
sin ETF proxy real ni ratio *_spy en RFL, solo comparaciones stock-vs-stock
dentro del cluster COAL). Off-cycle themes de `cycle.html` excluidos por
la misma razón que el propio Cycle Tracker los mantiene fuera de
`PhaseTimeline`: no responden a "¿dónde estamos en el ciclo?".

### 2. Fuente de cada columna — decisión de implementación explícita

- **Cycle (3M):** NO es el score compuesto del cesto completo de la fase
  en `cycle.html` (reimplementar `calcPhaseScores` + descargar el
  histórico de ~90 tickers adicionales que RFL no toca hoy sería
  desproporcionado para una "matriz mínima"). Se usa el **r3m del mismo
  ratio `*_spy` de RFL** para el ticker que Cycle Tracker marca
  `role:"proxy"` en esa fase — mismo instrumento, mismo concepto (alfa a 3
  meses), sin fetch ni cálculo nuevo. Aproximación declarada, documentada
  en la UI (tooltip), en el export a LLM y en el wiki — nunca presentada
  como si fuera literalmente el dato de Cycle Tracker.
- **Flujos (semanal):** última entrada de `rotation_history[ticker]` en
  `state.json` (ya sembrado por `rotacion.html` desde su propia Fase 1,
  `state.json` es compartido entre páginas — no hizo falta ninguna
  persistencia nueva). Bucketizado con los mismos umbrales que esa página
  usa para sus propias señales: `score≥5`→Bullish (ACUMULAR),
  `score<3`→Bearish, 3-4→Neutral (VIGILAR).
- **RFL (5-10d):** `flowChange` (5D vs 5D previos) del mismo ratio
  `*_spy` — el campo de horizonte más corto que ya calcula esta página,
  mismo dato que alimenta el Early Flow Detector y el filtro de la Fase 4.

Umbrales de bucketización (`bucketFromReturn`, `bucketFromFlowChange`,
`bucketFromRotScore` en `relative.html`) son de primera pasada, sin
calibrar contra rendimiento posterior — mismo criterio observacional que
el resto de features nuevas del proyecto.

### 3. Los 5 estados de coherencia (`computeCoherenceState`)

Exigen lectura en **los 3 módulos** para poder ser CONFIRMACIÓN/
DIVERGENCIA/PARCIAL/NEUTRAL — si falta cualquiera, siempre `NO EVALUABLE`,
nunca se rellena con un dato inventado (aplica automáticamente a
Transportation, Uranium y Coal & Steel Inputs, las 3 filas sin cobertura
completa del mapping):
```
CONFIRMACIÓN: los 3 coinciden (3 Bullish o 3 Bearish)
DIVERGENCIA:  hay al menos un Bullish y un Bearish a la vez
PARCIAL:      2 coinciden en dirección, el resto no opuesto
NEUTRAL:      los 3 en Neutral
NO EVALUABLE: falta lectura en algún módulo
```

**Lenguaje interpretativo** — mismo vocabulario obligatorio ya usado en el
registry de divergencias de `rotacion.html` (Fase 4 de Flujos & Rotación
v2): "sugiere consenso" / "plantea lectura ambigua" / "no garantiza
continuación de tendencia" — nunca "confirma"/"contradice" en sentido
conclusivo. Texto fijo bajo la tabla, y en el export a LLM.

### 4. Verificado en producción real

Edge headless vía CDP (PID resuelto por `netstat`, terminado exacto):
sintaxis JSX transpila sin errores; carga real contra `node server.js` sin
excepciones nuevas; las 11 filas renderizan correctamente — Transportation
y Coal & Steel Inputs con las 3 columnas en `—` y `No evaluable`; Uranium
con Cycle+RFL leídos pero Flujos en `—` → `No evaluable` (confirma que
exigir los 3 módulos funciona, no solo mayoría); Healthcare y Financials &
Cyclicals en `Confirmación` (los 3 en Bullish, datos reales del momento);
el resto en `Parcial`/`Divergencia` según los datos de mercado del día.
Export a LLM verificado con contenido real: tabla completa + texto de
lenguaje conservador + referencia al wiki de mapping.

**Fuera de alcance:** Fase 5b tal como se había nombrado en el plan
original (enriquecer con una "tercera columna" cuando Flujos completara
sus Fases 1-2) queda absorbida dentro de esta implementación — la columna
Flujos ya está presente desde el primer commit de la matriz, no como
fase separada posterior, porque `rotation_history` ya estaba listo desde
2026-07-30. Fase 6 (instrumentación de uso); `TLT/IEF`/`EDV/IEF` (sin
cambios); histéresis o suavizado de la matriz (se recalcula en vivo en
cada carga, igual que el resto de RFL).

---

## Relative Flow Lab — Fase 6: instrumentación de uso (implementado 2026-08-11)

Cierra el plan de 6 fases de RFL v2. El resumen de memoria de esta fase
("contadores agregados semanales + timestamp de última interacción, sin
opt-in") describía una estructura (`clusters` con expand/collapse,
`ratios_opened_detail`, un widget "Rotaciones detectadas") que asume UI que
**no existe** en `relative.html` — no hay clusters colapsables, no hay
detalle expandible por ratio, y el widget de rotaciones se descartó
explícitamente al implementar la lectura dinámica (ver esa sección más
arriba). Acordado con el usuario tras señalarlo: instrumentar solo lo que
existe hoy, alcance reducido a propósito ("mejor pequeña y honesta que
grande con datos ruidosos", palabras del usuario) — mismo principio de "no
meter infraestructura antes de tener datos que la justifiquen" que rige el
resto del proyecto.

**Cuatro eventos reales instrumentados:**
1. `page_load` — cada carga de `relative.html` (da el denominador; sin él,
   "un botón se usó 15 veces" no dice nada sin saber sobre cuántas cargas).
2. `button_click / copy_for_llm` — botón "Copy for LLM" ya existente.
3. `button_click / export_all_to_llm` — botón "🗂️ Exportar TODO a LLM".
4. `button_click / toggle_unfiltered_top` — toggle "Sin filtro" del panel
   Top 3 Flow In/Out (Fase 4).
5. `widget_interaction / cross_module_matrix_hover` y `..._click` — sobre
   la matriz de coherencia cross-módulos (Fase 5a), el bloque nuevo más
   complejo del rediseño; medir si se mira es la pregunta que más importa
   responder de las cinco.

**`server.js`, nuevo endpoint `/api/ux-instrumentation` (GET+POST):** a
diferencia de `relative_flow_history`/`rotation_history` (patrón GET-
modifica-POST-objeto-completo, seguro porque una sola pestaña escribe con
datos ya computados), aquí el **servidor** hace el incremento — el cliente
solo dispara `{kind, name}` y no necesita leer nada primero. Evita la
carrera de dos pestañas incrementando el mismo contador a la vez a partir
de una lectura desactualizada. Semana ISO empezando en lunes
(`isoWeekStartMonday`), cap de retención 12 semanas (~3 meses, mismo
espíritu que el cap de 70 entradas/~10 semanas de `rotation_history`).
Whitelist explícita de nombres válidos (`UX_VALID_BUTTONS`/
`UX_VALID_WIDGETS`) — un `kind`/`name` no reconocido devuelve 400, nunca se
escribe una clave arbitraria al archivo.

**`state_ux_instrumentation.json`** (nuevo, mismo directorio raíz que
`state.json`, añadido a `.gitignore` igual que ese archivo — dato local del
servidor, no se commitea):
```json
{ "weeks": { "2026-08-10": {
  "week_starting": "2026-08-10", "page_loads": 3,
  "buttons_clicked": { "toggle_unfiltered_top": 1, "copy_for_llm": 1 },
  "widget_interactions": { "cross_module_matrix_click": 1, "cross_module_matrix_hover": 1 },
  "last_interaction": "2026-08-11T14:44:33.548Z"
}}}
```

**`relative.html`:** `trackUxEvent(kind, name)` — fire-and-forget POST,
nunca bloquea ni interrumpe la UI si falla (`.catch(() => {})`). El hover
de la matriz se cuenta **una sola vez por sesión de página**
(`xmodHoverTrackedRef`) — mide "¿se mira el panel?", no cada movimiento del
ratón dentro de él; el clic no se limita (repetición de clics es señal
igual de válida, incluso podría indicar confusión — el usuario esperando
que la fila haga algo). `page_load` disparado una vez por montaje
(`pageLoadTrackedRef`, mismo patrón guard-ref que el resto de efectos
one-shot de esta página).

**Verificado en producción real:** `server.js` reiniciado (edita una ruta
`/api/*`, proceso persistente — ver [[project_dev_server_persistent]]);
sintaxis JSX transpila sin errores; Edge headless vía CDP confirmó los 5
eventos escribiendo correctamente en `state_ux_instrumentation.json` (clic
real en el toggle, clic simulado en "Copy for LLM", hover real con evento
`mouseover` bubbling — el primer intento con `mouseenter`/`bubbles:false`
no disparó el handler de React, que internamente escucha `mouseover` en la
raíz y sintetiza `onMouseEnter`; corregido en la verificación, no en el
código de producción, que usa el `onMouseEnter` estándar de React y
funciona igual en interacción real de usuario) y clic real en una fila de
la matriz; endpoint GET devolvió el JSON acumulado correctamente. Archivo
de prueba borrado tras verificar (gitignored, se regenera solo).

**Con esto, las 6 fases del plan original de RFL v2 quedan completas.**

---

## Cierre TLT/IEF y EDV/IEF — corrección: ya existían en Duration Stress Monitor (2026-08-11)

Las secciones de RFL v2 de arriba (Fase 2, lectura dinámica, Fase 4, Fase
5a, Fase 6) venían arrastrando `TLT/IEF`/`EDV/IEF` como "pendiente,
decidir dónde viven" — **error propio, no del usuario**: esos dos ratios ya
estaban implementados en `duration.html` desde el 2026-07-07 (commit
`9c2b01c`, sección "Sparklines y Trade Structure Playbook"), como
`ratioTltIef`/`ratioEdvIef` (precio crudo, no retorno) mostrados vía
`<Stat label="TLT / IEF">`/`<Stat label="EDV / IEF">` en la sección
"1. Market Confirmation", con su fila en el export a Markdown. Se citó
"pendiente" varias veces sin comprobar el código real de `duration.html`
— se debería haber verificado antes de escribir esa nota la primera vez.

**Decisión del usuario (arquitectura, sin necesidad de refactor):**
Duration Stress Monitor es la vocación semántica correcta para estos dos
ratios — "RFL es horizontal (lectura amplia de flujos); Duration Stress
Monitor es vertical (profundidad en duración). Los ratios intra-duración
son detalle que aporta a la lectura vertical, no a la horizontal." `TLT/
SPY` se queda donde está en RFL (cluster RISK APPETITE, sub-categoría
duración) porque es "duración vs equity" y sí sirve a la lectura
horizontal — no se mueve.

**Estado real de la profundidad analítica:** ambos `Stat` usan
`style={C.neutral}` (sin threshold de color) — mismo nivel que sus
vecinos en la misma sección (`2Y Yield`, `30Y Yield`, spreads, `DFII10`,
`Breakeven 5Y`): son contexto informativo, no alimentan la state machine
A/B/C/D de la tesis (que solo usa TLT/10Y/HY/VIX/MOVE). Es el nivel de
profundidad ya decidido para esa sección desde 2026-07-07, no un hueco
nuevo — no se ha tocado nada de `duration.html` en esta sesión, solo se
corrige la documentación.

**No se implementó ningún cambio de código** — no hacía falta. Si en el
futuro se quiere subir `TLT/IEF`/`EDV/IEF` al mismo nivel que los 5
indicadores centrales (threshold de color, quizás alimentar la state
machine), es una decisión aparte, no derivada de este cierre.

---

## PCS-floor whipsaw monitor (implementado 2026-08-12)

Origen: al investigar por qué SE (`force_analyze.py`) no fue SELECT en su
ventana de mejores métricas (PCS 82.2, extension_risk low, 2026-08-05),
apareció un hallazgo distinto y más concreto al revisar su historial real de
entradas. Sus dos entradas reales (`CONFIRMED_FLOW_LEADERS` 2026-07-07,
`MACRO_THEMATIC_BENEFICIARIES` 2026-07-15) se cerraron **ambas exactamente 1
día después** por la regla `current_pcs < 62` (suelo absoluto, ver sección
"Cierre de posiciones"), con el precio prácticamente plano (-0.73%, +1.89%).
Rastreado en el histórico de `ai_candidates.json` (vía git): el caso de CFL
se explica por un vuelco de un solo componente — `B_theme_flow` (techo 24)
pasó de 22.0 a 6.0 en una sola sesión y volvió a 18.0 al día siguiente,
mientras el resto de componentes y el propio precio de SE no se movieron.
Ruido de un día en el flujo del tema `china_em`, no deterioro del valor.

Escaneando las 30 salidas por suelo de PCS del sistema completo desde junio
(todas las carteras, no solo CFL), 3 comparten la misma firma —
cierre en ≤2 días con precio prácticamente plano (SE×2, y **NVDA**, cerrado
el mismo día 2026-07-16 en `MACRO_THEMATIC_BENEFICIARIES` por el mismo
motivo). Las otras 27 son deterioro real y consistente (ej. NBIS -15% a
-16% en 2 días, TDOC -21.6% en 32 días). n=3 es demasiado pequeño para
tocar la regla de salida — mismo criterio que el resto del proyecto
(~100-150 eventos independientes, 2+ regímenes, ver
`wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md`) — así que en vez de dejarlo como
una anécdota se creó un monitor shadow para acumular el conteo real
automáticamente.

**Script nuevo: `scripts/pcs_floor_whipsaw_shadow.py`** (Step 10h del
pipeline, `continue-on-error: true`, después de `cfl_reentry_cooldown_shadow.py`).
A diferencia de `cfl_followthrough_shadow.py` (que proyecta un "habría
salido / se habría mantenido" hipotético), esta regla **ya se disparó de
verdad** — el script solo clasifica, a posteriori, cada cierre por suelo de
PCS de todas las carteras (no solo CFL — el caso de NVDA fue en
`MACRO_THEMATIC_BENEFICIARIES`) como `flat_price_whipsaw`
(`holding_days<=2 AND |price_change_pct|<3.0`, primera pasada sin calibrar,
mismo criterio que el resto de umbrales nuevos del proyecto) o
`likely_real_deterioration`, y atribuye el vuelco de PCS al componente (A-F)
que más se movió entre el día de entrada y el de cierre.

**Reutiliza `list_commits`/`candidates_at_commit`/`find_match` de
`reconstruct_pcs_components_historical.py`** en vez de reimplementar la
búsqueda de commit por ticker+fecha+pcs — mismo criterio que motivó
`ai_shared.py`: que la lógica de "qué commit de `ai_candidates.json`
corresponde a este ticker en esta fecha" no pueda desincronizarse entre dos
scripts. El PCS del día de cierre no está guardado como campo estructurado
en `ai_picks.json` (solo dentro del texto libre de `close_reason`, con al
menos 8 formatos de redacción distintos observados) — se extrae con un
regex laxo (`pcs[^0-9]{0,20}?(\d+\.?\d*)`, primer número que aparece cerca
de la palabra "pcs") en vez de intentar parsear cada formato; validado
contra los 30 `close_reason` reales del sistema antes de escribir el
script: 30/30 extracciones correctas.

Lee `docs/data/ai_picks.json → portfolios[].history[]` (todas las carteras),
filtra cierres cuyo `close_reason` contenga "floor", y escribe
`docs/data/pcs_floor_whipsaw_shadow.jsonl` (append-only, dedup por
ticker+portfolio+entry_date+close_date — no por posición, porque un mismo
ticker puede tener varios ciclos de entrada/salida distintos). Nunca toca
`ai_picks.json` ni cierra nada real.

**Verificado:** `--dry-run` contra los datos reales de producción reproduce
exactamente los 3 casos encontrados a mano (SE×2, NVDA) con los mismos
componentes y deltas (`B_theme_flow 22.0→6.0` para el caso de SE/CFL,
coincide con el hallazgo manual); segunda ejecución sin `--dry-run` no
duplicó ninguna fila; `--report` resume 27 `likely_real_deterioration` / 3
`flat_price_whipsaw` con el componente de mayor vuelco por caso.

**Plan de revisión:** cuando el log acumule más eventos (el pipeline corre
2×/día, pero las salidas por suelo de PCS son relativamente raras — 30 en
~3 meses), evaluar si `flat_price_whipsaw` sigue concentrándose en
`B_theme_flow` o en algún componente concreto, y si el patrón se sostiene
con n mayor. Solo con evidencia suficiente se plantearía suavizar la regla
de suelo (ej. exigir 2 lecturas consecutivas por debajo de 62 en vez de 1,
o excluir el componente más ruidoso del cálculo del suelo) — no antes.

---

## Precursores de rebote tras capitulación v1 — sin señal fiable (2026-08-12)

A raíz de una pregunta del usuario sobre 21 tickers del Portfolio Tracker que
capitularon y luego rebotaron (localizados con un escaneo puntual sobre 6
meses de precios yfinance), se exploró si RSI/volumen/forma de vela avisaban
con antelación — sin grupo de control, ninguno lo hacía de forma clara, el
único patrón era retrospectivo (vela de cierre fuerte al día *siguiente* del
suelo, no en el propio día). Para no quedarse con una impresión sobre n=21
sin comparación, se preregistró y ejecutó una prueba con grupo de control real
— `wiki/PREREGISTRO_CAPITULACION_PRECURSORES_V1.md`,
`research/capitulation_precursors_v1/`.

**Dataset:** 590 eventos de capitulación (caída ≥18% en ≤15 sesiones desde un
máximo de 40 sesiones) en los 112 tickers del portfolio, 5 años de histórico,
etiquetados por si rebotaron después (≥18% sostenido ≥5 sesiones) o no —
52% base rate de rebote, split DEV (529, 2021-2026-02) / TEST (61,
2026-02→07) por fecha única congelada de antemano.

**Resultado — NOT SUPPORTED.** De 9 features candidatas (nivel de RSI,
cambio de RSI, divergencia alcista, pico de volumen, racha de días bajistas,
peor caída diaria, expansión de ATR, magnitud y velocidad de la caída) más 7
reglas compuestas congeladas, solo `rsi14_T0` sobrevivió Bonferroni en DEV
(p=0.0033, efecto pequeño: mediana 40.9 vs 38.2) — y no replicó en la
confirmación única de TEST (p=0.27). Ninguna regla de la rejilla batió la
tasa base en DEV. **Volumen no discrimina en absoluto** (p=0.61) — confirma
con n=590 lo que la exploración puntual ya insinuaba. Informe completo:
`wiki/HALLAZGOS_CAPITULACION_PRECURSORES_V1.md`.

Mismo patrón que el resto de exploraciones "descartadas" del proyecto (PCS↔
rendimiento, Relative Flow Lab↔alfa, Relative Flow Family Test): lo que
parece un patrón claro en un puñado de casos sin control no sobrevive al
añadirlo. No se crea ninguna señal shadow ni se toca `paper_trading.py`,
`koncorde_calculator.py` ni ninguna cartera — el preregistro solo
contemplaba promover algo si sobrevivía la prueba, y nada lo hizo.

---

## Marca manual de patrón Koncorde predictivo, por timeframe (implementado 2026-08-12)

El usuario observó que en algunas acciones el posicionamiento del azul de
Koncorde (D/3D/W) sí anticipa históricamente los giros alcistas/bajistas —
distinto de lo que se puede afirmar en general para todo el universo. Para
poder acumular evidencia y en su momento diseñar una alerta específica sobre
esos tickers concretos, se añadió en `portfolio.html` una marca manual por
timeframe, mismo enfoque de "observar primero" que `extension_risk`/
`konc_mirror_signal`/`theme_concentration_risk` en su día.

**Tres casillas independientes, no una sola** — una por D (fila principal),
otra por 3D y otra por W (sus sub-filas), porque el patrón puede confirmarse
en un timeframe y no en otro. Colocadas justo a la derecha de "Estado" y a
la izquierda de "MACD" en cada fila/sub-fila, tal como pidió el usuario tras
ver la primera versión (una sola casilla al final de la fila).

**Persistencia:** campos `koncPatternD`/`koncPatternDDate`,
`koncPattern3D`/`koncPattern3DDate`, `koncPatternW`/`koncPatternWDate` en
cada item de `portfolio.json` (mismo mecanismo de autoguardado con debounce
de notas/shares). Al marcar, guarda la fecha de hoy; al desmarcar, limpia
ambos campos — así dentro de un año se sabe qué ventana concreta revisar
para ampliar la validación. Sincronizado en el export a Markdown/LLM como
`D:✅fecha 3D:✅fecha W:✅fecha` (solo los timeframes marcados).

**Verificado en producción real** (Edge headless vía CDP, `.click()` sobre
el checkbox — el `Input.dispatchMouseEvent` sintético de CDP no disparaba el
`onChange` de React sobre un `<input type=checkbox>` nativo en este Edge
headless, pese a que `elementFromPoint` confirmaba que las coordenadas caían
exactamente sobre el checkbox; sí funcionó igual que en verificaciones
anteriores del proyecto con botones — parece un quirk específico de checkbox
nativos bajo CDP sintético, no del código de la página): las tres casillas
son independientes (marcar 3D no afecta D ni W), la cabecera queda
`...Estado | 🔮 | MACD...`, persiste con la fecha correcta y el revert limpia
ambos campos. Cero errores de consola.

**Fuera de alcance (explícito):** ninguna señal ni alerta todavía — el
preregistro de una señal operativa espera a tener suficientes tickers
marcados con fecha, mismo criterio que el resto de features en fase de
observación del proyecto.

---

## Mini-gráfico Koncorde por fila — últimas 5 sesiones (implementado 2026-08-14)

El usuario pidió una representación visual (estilo Koncorde clásico) de las
últimas 5 sesiones por fila en `portfolio.html`, para detectar patrones a
simple vista sin leer los números. Antes de construirlo se auditó qué
calcula realmente `koncorde_calculator.py`: solo `blue`/`green` estaban
expuestos; no existía ninguna "línea roja". El usuario pidió implementarla
también, y acabó pasando la fórmula real de ProRealTime/Blai5 para
verificarla — el diseño final tardó 3 rondas de corrección visual contra
capturas reales suyas (JD) antes de quedar bien; se documenta solo el
resultado final + los hallazgos de fondo, no cada iteración intermedia.

### Las 4 series reales (`_calc_koncorde_plus()`, `scripts/koncorde_calculator.py`)

| Serie | Fórmula | Rol visual |
|---|---|---|
| `blue` | NVI acumulado → EMA(15) → oscilador normalizado (min-max, ventana 90) | Área azul, primer plano — "tiburones" |
| `green` | `trend + osc_pos` (PVI-based, mismo tratamiento que blue) | Área verde, fondo — "pececillos" |
| `trend` | `(RSI14 + MFI14 + BollOsc25 + Stoch21,3/3) / 2`, todo sobre `ohlc4` | Área ocre — la "marrón" cruda, sin suavizar |
| `trend_ma` | `EMA(trend, 15)` | Línea roja suelta — señal/media de la marrón, **sin área propia** |

Verificado línea por línea contra la fórmula que pasó el usuario (RSI14 y
Stochastic21,3 sobre `TotalPrice`=`ohlc4`, MFI14, BollOsc25 con mult=2,
composición `(rsi+mfi+bollosc+stoc/3)/2`, EMA15 final): coincide exacta con
el código — no hizo falta cambiar ninguna fórmula, solo exponer `trend`
(que ya se calculaba pero no se guardaba en ningún `_last5`) y corregir un
bug real en `_ema()`.

**Bug real encontrado — `trend_ma` ya estaba calculado pero siempre salía
`null`.** `_ema()` sembraba con los primeros `period` valores **literales**
del array (`series[:period]`) en vez de los primeros `period` valores
**no-NaN**: como `trend` tarda ~20-26 barras en tener su primer valor válido
(warmup de RSI/MFI/BB/Stoch, más largo que `MA_TREND_LEN=15`), la ventana
semilla siempre pillaba algún NaN y la función devolvía NaN para siempre —
incluso con los 820 días de histórico del pipeline. Confirmado con datos
reales antes del fix: `konc_d_trend_ma` era `null` en el 100% de
`koncorde_data.json`. Fix: busca la primera ventana de `period` valores
consecutivos sin NaN en vez de asumir que empieza en el índice 0. Los otros
dos llamadores de `_ema()` (`pvi_ema`, `nvi_ema`) no tienen warmup propio,
así que el fix no les cambia el comportamiento.

**Arrays de 5 sesiones** (`_last_n()`, nuevo helper): `konc_{tf}_blue_last5`,
`konc_{tf}_green_last5`, `konc_{tf}_trend_last5`, `konc_{tf}_trend_ma_last5`
por timeframe — la cola de 5 de los arrays completos que
`_calc_koncorde_plus()` ya calculaba internamente, no un recálculo sobre una
ventana corta. Como el array D/3D/W ya representa barras reales no
solapadas (D=sesión, 3D=bloque de 3 sesiones, W=semana — ver sección
"Koncorde Plus v2" más arriba), la cola de 5 son 5 barras cerradas reales de
ese timeframe, no 5 ejecuciones del pipeline. `server.js` no necesitó ningún
cambio: `getKoncordeData()` ya expone el objeto completo del ticker vía
spread (`...(getKoncordeData()[symbol] ?? {})` en `/api/quote/:symbol`), así
que los campos nuevos llegan solos.

### `KoncMiniChart` (`portfolio.html`) — estructura final

SVG inline, mismo patrón `Spark` que el resto de páginas del proyecto (cada
una con su propia copia, sin módulo compartido). **3 áreas con línea propia
del mismo dato** (verde/ocre/azul) + **1 línea roja suelta sin área propia**
(`trend_ma`, la señal/media de la ocre — no un dato independiente de mano
fuerte/débil):

- **Z-order (fondo→frente), determinado por el orden del array `areaSeries`**
  (SVG pinta en orden de aparición): verde → ocre (`trend` crudo) → azul.
  Azul siempre visible por completo, nunca tapado. La roja se pinta la
  última de todas (encima incluso del azul) — al no tener relleno, nada
  puede taparla, se ve entera en todo el trayecto.
- **Rellenos SÓLIDOS (`fillOpacity={1}`), no semi-transparentes.** Con
  opacidad baja las áreas superpuestas suman color (blending); con opacidad
  completa la capa de encima oculta de verdad a la de detrás (occlusion) —
  así se ve el Koncorde real: donde la ocre cubre al verde, el verde no
  transparenta, solo se ve la porción que sobresale por encima.
- Colores: línea/área azul `#1a5cb0`/`#8fb8e6`, línea/área verde
  `#1a7a1a`/`#a8d5a2`, área ocre `#e0c184` (sin línea propia), línea roja
  `#c0392b` (sin área). Escala Y compartida entre las 4 series, incluyendo
  siempre el 0 en el rango para que la línea base sea comparable entre
  tickers.

**Colocación:** una celda nueva (📈) entre "Estado" y la casilla de patrón
manual (🔮), en las 3 filas — D (principal) y las sub-filas 3D/W — a
petición explícita del usuario tras preguntarle (la alternativa "solo D" se
descartó). El widget separado "Ranking de Setups" no lleva gráfico — mismo
criterio que ya se aplicó ahí para el checkbox de patrón manual: ese widget
es secundario, el pedido era sobre la tabla principal.

**Verificado con datos reales, en dos pasadas completas del pipeline
(`py -3 scripts/koncorde_calculator.py`, en local) sobre los 198 tickers del
universo real** (candidatos + portfolio + posiciones abiertas) — necesario
porque la caché de 10 min de `server.js` sirve lo que haya en disco, y sin
correr el pipeline ningún ticker tiene `_last5` real: 196/198 computados
ambas veces (2 fallos — `ASMI`, `TSND.V`, ambos posiblemente deslistados,
sin relación con este cambio). Capturada la tabla real vía Edge headless
(CDP directo — `puppeteer.connect({browserURL})` a una instancia lanzada a
mano con `--remote-debugging-port`, más fiable en este entorno que
`puppeteer.launch()`, que fallaba al spawnear el proceso) tras cada cambio
de diseño — la versión final confirma visualmente verde asomando por
encima de la ocre, roja recorriendo el borde superior de la ocre, y azul
como banda fina siempre visible en la base, coherente con las capturas
ProRealTime de JD que pasó el usuario. Cero errores de consola (solo un 404
de recurso no relacionado). `docs/data/koncorde_data.json`, `ai_candidates.json`,
`koncorde_failed_state.json` y `koncorde_signals_history.jsonl` quedan
modificados/actualizados de verdad en el árbol de trabajo (no revertidos
esta vez), pendientes de que el usuario los revise y decida si commitear.

**Fuera de alcance:** ninguna señal ni alerta basada en el gráfico —
puramente visual/observacional, mismo criterio que el resto de features
nuevas del proyecto.

---

## ATLAS Mini (Blai5) — estrechamiento de Bollinger Bands, junto al MACD (implementado 2026-08-14)

Indicador nuevo, columna a la derecha de MACD en `portfolio.html`, mismo día
que el mini-gráfico Koncorde. El usuario pasó la fórmula pública
(ProRealCode "Blai5 ATLAS Mini"): detecta estrechamientos matemáticamente
significativos de Bollinger Bands(20), que suelen preceder a movimientos
bruscos — **sin dar dirección**, solo avisa de compresión. Por eso vive junto
al MACD: MACD aporta el sesgo direccional que ATLAS no da por sí solo.

```
dbb    = sqrt((BBupper20(close) − BBlower20(close)) / BBupper20(close)) × 20
dbbmed = EMA(dbb, 120)
factor = dbbmed × 4/5
atl    = dbb − factor
señal  = atl ≤ 0   (compresión relevante)
```

**Decisión de arquitectura — JS en `server.js`, no Python en
`koncorde_calculator.py`.** A diferencia del mini-gráfico Koncorde (que sí
vive en el pipeline Python porque necesita OHLCV+volumen de 194 tickers y
persistencia batch), ATLAS solo necesita `close` — exactamente el mismo dato
que ya usa `calcMACD()`, que **ya vive en `server.js`**, calculado en vivo
en cada `/api/quote/:symbol` sobre los `closes` de 3 años que esa ruta ya
descarga (de sobra para el warmup real: 20 barras para el primer `dbb` +
120 para el `EMA` = ~140, muy por debajo de las ~750 sesiones de 3 años).
Mismo patrón que `calcMACD`/`calcATR`/`calcCMF`/`calcOBV`, todas ya en ese
archivo — se evitó introducir una quinta fuente de verdad. `calcAtlasMini()`
añadida junto a esas funciones, enganchada con `...calcAtlasMini(closes)`
justo después de `...calcMACD(closes)` en la respuesta de `/api/quote/:symbol`.

**Columna ticker-level, no por timeframe D/3D/W** — mismo criterio que MACD
(que tampoco se repite en las sub-filas 3D/W, solo vive en la fila
principal). El `colSpan` de relleno de las sub-filas pasó de `6` a `7` para
seguir cubriendo la columna nueva (MACD+ATLAS+ATR%+Flow+Early+Notas+Acciones).

**Glifo — 🗜️ descartado tras verlo en pantalla.** El emoji de compresión no
renderiza en el Edge usado para verificar (sale un glifo de reemplazo/tofu,
no el emoji real) — soporte de emoji poco fiable entre plataformas para ese
carácter concreto (U+1F5DC). Sustituido por `●` (compresión, color ocre
`#a9720f`) / `·` (sin señal, gris claro) — mismo lenguaje visual que los
▲/▼ de MACD, glifos ASCII/Unicode básicos con soporte universal.

**Tooltip:** `dbb=X · umbral=Y · atl=Z` en el `title` del `<td>`, para poder
ver los números crudos sin añadir otra columna.

**Verificado con datos reales:** función probada con curl contra un
servidor temporal (`server.verify.js`, copia de un solo uso en el puerto
3099 — necesario porque el `server.js` real corre en la terminal del
usuario y no se quería reiniciar sin avisar; borrada al terminar) sobre 11
tickers reales del portfolio — valores planeados coherentes (ej. JD:
dbb=7.75, atl=1.54, sin señal; `DMX.V`: dbb=7.57, atl=-0.39, señal activa;
`FXPO.L`: dbb=0, atl=-5.72, caso extremo de banda plana, también señal
activa). Capturado en pantalla vía Edge headless (CDP directo) contra ese
mismo servidor temporal, con y sin señal — glifo correcto, tooltip correcto,
cero errores de consola relevantes tras el cambio de emoji a `●`/`·`.

**Fuera de alcance:** ATLAS no se combina automáticamente con MACD en una
señal compuesta (ej. "compresión + MACD alcista = posible ruptura al alza")
— se deja que el usuario lea ambas columnas juntas visualmente, mismo
criterio de observación-antes-que-automatización del resto del proyecto.
No se ha tocado el pipeline Python ni ninguna cartera.

---

## Insider Activity (Form4API) — piloto, capa de confirmación contextual (implementado 2026-08-16)

Nueva integración con [Form4API](https://www.form4api.com) (SEC Form 4 / EDGAR)
para mostrar compras/ventas de insiders junto a las señales técnicas ya
existentes. **No es una señal de compra/venta automática** — es una capa de
confirmación contextual, mismo criterio "observar primero" que
`extension_risk`/Koncorde/`konc_mirror_signal` en su día. `insider_activity_score`
no entra en PCS, no entra en `rot_score`, no cambia carteras, no dispara
órdenes.

### Alcance — decidido explícitamente con el usuario antes de implementar

El proyecto tiene dos sistemas de posiciones independientes (AI Picks Lab vs
Portfolio Tracker). Se decidió con el usuario 2026-08-16:
- **Universo: solo Portfolio Tracker (`portfolio.json`)**, NO la cartera de
  candidatos del AI Picks Lab (`ai_candidates.json`/`ai_picks.json`).
- **Dashboard: `portfolio.html`**, junto al Ranking de Setups.
- **Pipeline: sí, pero solo el run de la mañana** (Step 9f, gateado con el
  mismo `steps.time_check.outputs.is_morning` que ya usa Mirror Espejo) — la
  actividad insider (SEC Form 4) no cambia varias veces al día, así que una
  consulta diaria basta y evita duplicar cuota del plan gratuito entre los
  dos runs del pipeline.

**Definiciones operativas que el plan original dejaba ambiguas** (documentadas
en el docstring de `scripts/update_insider_activity.py`, no solo aquí):
`portfolio.json` no distingue "posición real" de "watchlist" con datos de
verdad — los 112 tickers actuales tienen `shares:0` en todas las secciones,
incluida "Cartera" (es una lista curada, no un feed sincronizado con el
broker). `is_open_position` (sección `"Cartera"` O `shares>0`) se definió
igual, pero **ya no es un trigger de cola por sí solo** — corregido
2026-08-16 a petición del usuario tras ver el primer `--dry-run` real: por
sí solo metía 99/112 tickers en la cola (casi todo "Cartera") solo por estar
en el portfolio, sin ninguna señal real detrás. Ahora `is_open_position`
solo se usa para la cadencia de caché (refresco cada 2 días en vez de 7/10
una vez que el ticker YA entró en cola por algún otro motivo) — un ticker
que simplemente está en "Cartera" sin ninguna señal de Koncorde/PCS ya no
gasta ninguna request. Verificado: la cola bajó de 99 a 89 tickers tras el
cambio (los 10 que salieron eran exactamente los que solo calificaban por
`open_position`, sin ningún otro trigger).

**`watchlist principal` (P3) eliminado por completo** — mismo día, misma
petición del usuario: era `sección literal "Watchlist"`, ya no dispara nada
(la sección en sí no se toca, solo deja de ser motivo para consultar
Form4API). Verificado: la cola se mantuvo en 89/112 tras quitarlo — ningún
ticker calificaba *solo* por estar en Watchlist, todos los de esa sección
que seguían en cola lo hacían ya por Koncorde/PCS.

**`PCS >= 75` (P3) eliminado por completo** — mismo día, misma petición del
usuario. Con esto desaparece la categoría P3 entera y el script deja de
leer `ai_candidates.json` (`load_candidates_by_ticker()`, `CANDIDATES_PATH`
y el parámetro `candidates` de `build_insider_request_queue()` se
eliminaron del código, no solo se desactivaron). Verificado: la cola bajó de
89 a 86 tickers — los 3 que salieron (`NBIS`, `LLY`, `HUM`) eran justo los
que solo calificaban por `pcs_ge_75`, sin ninguna señal de Koncorde.

**Criterio único — solo estado `accumulation` literal (4ª y última vuelta de
recorte, mismo día).** El usuario preguntó si los 86 eran "los que tienen
acumulación en Koncorde hoy" — no lo eran: solo 7/86 tenían de verdad algún
timeframe (D/3D/W) en estado `accumulation` en ese momento; los otros 79
entraban solo por dos criterios más laxos de P2
(`konc_d_blue_positive_days_6_ge4`/`konc_d_blue_up_count_6_ge4` — azul
subiendo, que también se da en estado `up` sin ser `accumulation`). A
petición del usuario ("vamos a dejarlo solo para los 7, ese criterio"),
`build_insider_request_queue()` se redujo a una sola comprobación:
¿`konc_w_state`, `konc_3d_state` o `konc_d_state` es literalmente
`"accumulation"` hoy? Se eliminaron también `konc_alignment_accumulation_setup`
y las 3 transiciones frescas (`konc_{w,3d,d}_new_transition_to_accumulation`)
por ser redundantes con la comprobación directa de estado — una transición
fresca a `accumulation` implica que el estado actual YA es `accumulation`,
así que no se pierde ningún ticker al quitarlas, solo el detalle de "es
nuevo hoy o ya llevaba tiempo". El helper `_transitioned_to_accumulation()`/
`_konc_state()` quedó sin uso y se eliminó del código.

**Estado final de la cola:** dos niveles, ambos leyendo directamente
`konc_{d,3d,w}_state` de `docs/data/koncorde_data.json`, sin ningún otro
campo derivado:
- **P1** = `konc_w_state=="accumulation"` O `konc_3d_state=="accumulation"`
  (semanal/3D — la lectura menos ruidosa, ver "Koncorde Plus en el payload
  del modelo" más arriba).
- **P2** = `konc_d_state=="accumulation"` (diario — más ruidoso, prioridad
  más baja a propósito, no eliminado).

Verificado: 7/112 tickers en cola (`VNOM`, `TGS`, `TSLA`, `ISRG` en P1;
`JD`, `CRESY`, `UNH` en P2), coincide exactamente con el recuento manual
que motivó el cambio.

### Presupuesto de 20 requests/minuto — ya cubierto, no requirió cambios

El usuario preguntó qué pasaría si algún día hicieran falta más de 20
requests en un momento dado (el límite real del plan gratuito es 20/min,
`MAX_FORM4API_REQUESTS_PER_MINUTE` ya estaba fijado en 15 por margen). La
clase `RateLimiter` ya existente en el script cubre esto — no fue necesario
ningún cambio de código. Antes de cada llamada HTTP real
(`fetch_form4api_transactions`), `rate_limiter.wait_if_needed()` calcula
cuántas requests van en los últimos 60s y **duerme** el tiempo necesario en
vez de fallar o exceder el límite; `rate_limiter.record()` registra cada
llamada real después de hacerla. Con la paginación (hasta 3 páginas/ticker)
y ahora solo 7 tickers en cola, el peor caso son 21 requests — cabría en
poco más de un minuto de espera, muy por debajo del timeout de 60 min del
job de GitHub Actions.

Verificado con una prueba de lógica pura (reloj simulado, sin llamadas
reales ni esperas de verdad): 21 peticiones simuladas nunca superaron 15 en
ninguna ventana deslizante de 60s, y el limitador durmió (`time.sleep`)
en vez de lanzar un error al alcanzar el tope — confirma que el mecanismo
ya presente resuelve el escenario planteado.

`is_open_position` sigue en los metadatos del universo (`load_universe()`) y
sigue afectando la cadencia de refresco de caché (2 días en vez de 7/10),
pero no gatea la entrada a la cola. Ningún otro campo de `portfolio.json`
(sección, PCS, watchlist) participa ya en la decisión de a quién consultar.

### Verificación de la API real antes de escribir código

Documentación pública consultada dos veces de forma independiente antes de
implementar (mismo hábito que el resto del proyecto: no fiarse de un único
resumen). **Las dos consultas dieron nombres de campo distintos para el mismo
flag** (`isTenPercentOwner` vs `is10PctOwner`, `directOrIndirect` vs
`directIndirect`) — señal de que ninguna de las dos fuentes es
100% fiable sin contraste contra la API real. `normalize_transaction()` lee
ambas variantes con un `_pick()` defensivo y **siempre** guarda el `raw`
completo sin recortar — el primer response real de la sesión imprime sus
claves por consola (`[diagnostic] first live transaction raw fields: ...`)
para poder confirmar/corregir contra la API de verdad en el primer piloto
real, en vez de confiar ciegamente en la documentación.

Endpoint real: `GET https://api.form4api.com/v1/transactions` (header
`X-Api-Key`), filtros `ticker`/`from`/`to`/`per_page`/`page` — los filtros
`significant`/`exclude_10b5`/`min_value` son Pro+, no disponibles en el plan
gratuito, así que la clasificación P/S vs derivatives/10b5-1 se hace
localmente sobre la respuesta cruda (`classify_transaction()`), tal como
pedía el plan original.

### Mapeo de tickers — Form4API es EE.UU. únicamente (SEC EDGAR)

Verificado contra el universo real de `portfolio.json`: 34/112 tickers
llevan sufijo Yahoo de bolsa extranjera (`.TO`, `.V`, `.AX`, `.L`, `.DE`,
`.AS`, `.MI`, `.F`, `.ST`) — se marcan `unsupported_non_us_or_no_data`
**sin gastar ninguna request** (`map_ticker_to_form4api()` corta antes de
llamar a la API). El mapeo guion→punto para tickers de doble clase
(`BRK-B`→`BRK.B`) es una suposición sin verificar — no existe ningún ticker
así en el universo actual para contrastar contra un ejemplo real; si falla,
la propia API devuelve unsupported/sin-datos y `coverage_status` lo refleja,
en vez de fabricar un falso positivo en silencio.

### Ventanas, clasificación y score

Una sola consulta de ~12-15 meses por ticker (no 4 consultas de 3 meses),
agregada localmente en 4 ventanas (`0_3m`/`3_6m`/`6_9m`/`9_12m`). Paginación
capada a 3 páginas/ticker (300 filas) como salvaguarda de presupuesto.

`net_open_market_value` = compras discrecionales − ventas discrecionales
**(las ventas 10b5-1 planificadas NO restan)** — decisión explícita, es la
traducción literal de "las ventas 10b5-1 no deben penalizar igual" del plan
original a una fórmula concreta, que el plan no daba.

`insider_activity_score` (0-5) y `koncorde_insider_context`
(`strong_confirmation`/`moderate_confirmation`/`neutral`/`warning`/
`ignored_selling`/`not_evaluable`) son cascadas if/elif de una sola pasada,
documentadas en el propio código — primera versión sin calibrar contra
rendimiento posterior, mismo criterio de observación que el resto de scores
nuevos del proyecto.

### Presupuesto y caché

```
MAX_FORM4API_REQUESTS_PER_DAY   = 400   (plan gratuito: 500/día)
FORM4API_SAFETY_STOP            = 450   (circuit breaker duro)
MAX_FORM4API_REQUESTS_PER_MINUTE = 15   (plan gratuito: 20/min)
```

Caché por ticker vía `last_fetch` en `insider_activity_snapshot.json`:
posiciones abiertas cada 2 días, resto de P1 cada 7 días, P2/P3 cada 10 días.
Log de auditoría completo (`docs/data/form4api_usage_log.jsonl`) con una fila
por ticker considerado cada día, incluidos los `skipped_cached`/
`skipped_limit`/`unsupported` — no solo las peticiones reales.

### Ficheros

| Fichero | Qué hace |
|---|---|
| `scripts/update_insider_activity.py` | Script principal — cola de prioridad, fetch, normalización, agregación, snapshot |
| `docs/data/insider_activity_snapshot.json` | Estado actual por ticker (reescrito cada run) |
| `docs/data/insider_activity_transactions.jsonl` | Transacciones normalizadas, raw incluido, dedup por accession+code+fecha+shares+precio |
| `docs/data/form4api_usage_log.jsonl` | Auditoría de cuota — una fila por ticker considerado/día |
| `docs/analysis/insider_activity_pilot_report.md` | Generado con `--pilot-report`, responde las 9 preguntas del piloto |

CLI: `--dry-run` (sin llamadas), `--max-requests N`, `--force`,
`--tickers A,B,C`, `--priority P1|P2|P3`, `--report` (resumen consola),
`--pilot-report` (informe markdown).

### Dashboard (`portfolio.html`) y export a LLM

Bloque nuevo "Insider Activity — confirmación contextual (no señal de
trading)" entre el Ranking de Setups y las secciones de cartera, alimentado
vía `p.insider` en la respuesta ya existente de `/api/quote/:symbol`
(`server.js` gana `getInsiderActivityData()`, mismo patrón de caché de 10 min
que `getKoncordeData()`). `buildPortfolioMarkdown()` gana una sección
`## INSIDER ACTIVITY` a juego con el resto de exports a LLM del proyecto.

**Verificado con datos reales (dashboard, sin API):** `--dry-run` inicial
contra el universo real disparó 99/112 tickers (la mayoría por
`open_position`, ver corrección de prioridad más abajo). Bloque de dashboard
verificado end-to-end con Edge headless (CDP directo) contra un snapshot
fabricado con 3 casos representativos (compra con cluster buying, venta
discrecional pesada, ticker no-US) inyectado temporalmente en
`docs/data/insider_activity_snapshot.json` y borrado tras la verificación —
las 3 filas, columnas, colores y badges renderizan correctamente, orden por
score descendente correcto, cero errores de consola. Ruta `/api/quote/:symbol`
confirmada sirviendo `insider: null` cuando no hay snapshot. Sintaxis JSX
transpila sin errores (`@babel/core`).

**Verificado en vivo contra la API real (2026-08-16, tras añadir `FORM4API_KEY`
al `.env`):** `py -3 scripts/update_insider_activity.py --tickers HIMS --force
--max-requests 5` — 294 transacciones reales descargadas (3 páginas, tope de
paginación activado correctamente para un ticker con mucho volumen de
insiders), 3/400 requests consumidas. El diagnóstico de campos confirmó los
nombres reales (`is10PctOwner`, `directIndirect`, sin campo `value` — solo
`totalValue`), todos ya cubiertos por el `_pick()` defensivo sin necesidad de
tocar código. Clasificación correcta: un grant RSU (código `A`, derivative)
quedó excluido del cálculo de compra/venta; una compra discrecional de un
director sí contó (`director_purchase`, `net_buying_last_3m`,
`insider_activity_score=4`). Cruce con Koncorde correcto: HIMS estaba en
`distribution`/`distribution`/`up` (D/3D/W) → `koncorde_insider_context=neutral`,
no forzó una confirmación falsa. Caché verificada: una segunda llamada al
mismo ticker el mismo día no gastó ninguna request (`skipped_cached`).
Dedup de transacciones verificado (294 filas, 294 claves únicas). `--report`
y `--pilot-report` verificados generando salida coherente con el snapshot real.

**Corrección de prioridad (2026-08-16, mismo día, a petición del usuario):**
tras ver el `--dry-run` real disparando 99/112 tickers, el usuario pidió que
"posiciones abiertas" dejara de ser un trigger de cola por sí solo — ver
`is_open_position` más arriba. Verificado: la cola bajó a 89/112 tras el
cambio, y los 10 tickers que salieron eran exactamente los que solo
calificaban por estar en "Cartera" sin ninguna señal de Koncorde/PCS detrás.

### Pendiente del lado del usuario

Nada bloqueante — `FORM4API_KEY` ya está en `.env` local y verificado contra
la API real. Queda añadir el mismo secret a GitHub Secrets antes del próximo
run matutino en CI — sin él, el Step 9f fallará con `continue-on-error: true`
(pipeline en verde en la pestaña Actions aunque este paso no corra, mismo
patrón de fallo silencioso ya vivido con `TELEGRAM_BOT_TOKEN` y
`CAVA_ENGINE_TOKEN`) — conviene revisar el log del Step 9f manualmente tras
el primer run en CI, no solo el check verde.

### Fuera de alcance (explícito)

Universo de AI Picks Lab (`ai_candidates.json`), cualquier hard rule o
cambio de PCS/rot_score/carteras, `candidate_ranking_score_shadow`/
`EarlyFlow`/RFL como triggers (fuentes de datos no disponibles todavía,
ver arriba).

---

## Alertas Koncorde personalizadas — texto y voz vía Telegram (implementado 2026-08-17)

Origen: el usuario vio en `portfolio.html` que CRESY tenía compra de insiders
y, al mirar el detalle, Koncorde azul positivo en diario (débil) pero no en
3D ni W. Pidió poder programar una alerta específica ("avisar cuando CRESY
tenga señal azul en Koncorde positiva en semanal"), creable desde el propio
bot de Telegram, en texto o por nota de voz.

**Se construyó reutilizando la infraestructura de alertas de precio ya
existente en `telegram_portfolio_bot.py`** (`/alert TICKER PRECIO` →
`bot_alerts.json` → chequeo periódico → aviso + auto-borrado), en vez de
crear un sistema paralelo — mismo bot que ya corre en continuo en Railway
(hay `Procfile`, `USE_GITHUB_API` cuando `RAILWAY_ENVIRONMENT` está
presente) y también 2×/día vía pipeline (`--once`, Step 12).

### Almacenamiento — fichero separado, no mezclado con las alertas de precio

`docs/data/koncorde_bot_alerts.json` (nuevo), no `bot_alerts.json`.
**Deliberado, no un descuido:** `check_alerts()`/`cmd_alert_delete()`/
`cmd_alerts_list()` ya existentes iteran `_load_alerts()` asumiendo que cada
entrada tiene `target`/`direction` numéricos — si una alerta Koncorde
(`ticker`/`timeframe`/`condition`) hubiera entrado en esa misma lista,
`check_alerts()` la habría leído como alerta de precio con
`target=0, direction="above"` y disparado un aviso falso en el primer
chequeo (cualquier precio real es ≥0), borrándola además por el mismo
mecanismo de auto-limpieza. Fichero separado con sus propias
`_load_konc_alerts()`/`_save_konc_alerts()` (mismo patrón dual GitHub-API/
archivo-local que el resto de loaders del bot) — cero cambios en el camino
de las alertas de precio, cero riesgo para una función ya en producción.

### Vocabulario de condición — cerrado, en módulo compartido

`scripts/koncorde_alert_conditions.py` — mismo criterio que
`ai_shared.py`/`cava_mapping.py`: un enum cerrado que tanto el parser NL
(bot) como el evaluador (pipeline) importan, para que no puedan
desincronizarse en qué significa cada condición. 7 condiciones sobre los 3
timeframes (`d`/`3d`/`w`) que `koncorde_calculator.py` ya calcula:
`blue_positive`, `blue_negative`, `blue_cross_up`, `green_positive`,
`green_negative`, `state_accumulation`, `state_distribution`
(`evaluate()` lee directo `konc_{tf}_blue`/`_green`/`_blue_cross_up`/
`_accumulation_flag`/`_distribution_flag` de `koncorde_data.json` — sin
recalcular nada). Un campo ausente devuelve `None`, nunca `False` — evita
que a un ticker sin dato para ese timeframe se le dé por incumplida la
condición.

### Creación — sintaxis exacta o lenguaje natural (texto o voz)

`/kalert TICKER TIMEFRAME CONDICION` (ej. `/kalert CRESY w blue_positive`)
se parsea sin IA (`_parse_koncorde_alert_strict`, 3 tokens exactos). Si no
encaja, cae a `_parse_koncorde_alert_nl()`: una llamada barata a Haiku vía
OpenRouter (reutilizando `call_model`/`parse_response` de
`paper_trading.py` — mismo patrón de reutilización que `mirror_portfolio.py`
con `call_model`), con el prompt restringido al enum de
`koncorde_alert_conditions.py` y obligado a devolver
`{"error": "..."}` en vez de adivinar cuando el ticker/timeframe/condición
no queden claros — nunca se guarda una alerta con un campo inventado.
Confirmación siempre explícita en texto (`"✅ Alerta creada: CRESY — ..."`)
para poder detectar un mal-parseo al momento con `/delkalert`.

**Voz:** cualquier nota de voz enviada al bot se trata como intento de
`/kalert` (única función que usa voz en v1). `_download_telegram_file()`
(`getFile` + descarga del `.ogg`) → `_transcribe_voice_groq()`
(`api.groq.com/openai/v1/audio/transcriptions`, `whisper-large-v3-turbo`,
`language="es"` fijo — el proyecto y el usuario son hispanohablantes) → el
texto transcrito entra por el mismo `cmd_kalert()` que el texto escrito, sin
lógica duplicada. El bot siempre repite lo que entendió transcrito antes de
parsear, para poder pillar un error de transcripción a simple vista.

Ambos requieren secrets nuevos que **no** estaban en `.env`/GitHub
Secrets/Railway: `OPENROUTER_API_KEY` (para el parser NL — sí existe ya en
GitHub Secrets para `paper_trading.py`, pero hay que confirmarlo también en
las variables de entorno de Railway) y `GROQ_API_KEY` (nuevo, para
transcripción — proveedor elegido con el usuario por precio/velocidad).
Sin ellos el bot degrada con avisos explícitos en vez de fallar en
silencio: `_parse_koncorde_alert_nl()`/`_transcribe_voice_groq()` devuelven
`None` si falta la clave, y `handle_voice_message()` responde
"No puedo transcribir notas de voz todavía" en vez de no hacer nada.

### Evaluación — paso del pipeline, no el polling de precio del bot

Koncorde solo cambia cuando corre `koncorde_calculator.py` (2×/día +
reintento a las 2h) — comprobarlo en el polling continuo del bot (~2.5 min)
no aportaría nada. Script nuevo `scripts/check_koncorde_alerts.py`, Step 9c2
del pipeline (`continue-on-error: true`), justo después de Step 9c
(Koncorde shadow exits): lee `koncorde_bot_alerts.json` +
`koncorde_data.json`, evalúa cada alerta con
`koncorde_alert_conditions.evaluate()`, y para las que se cumplen, avisa
por Telegram y las borra — **un solo disparo, igual que las alertas de
precio** (no hay re-armado automático; si el usuario quiere volver a
vigilar la misma condición, crea la alerta de nuevo). Mismo patrón
"fail loud" que `duration_monitor.py`: si hay algo que disparar pero faltan
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, `sys.exit(1)` en vez de callar —
visible en la pestaña Actions aunque el step tenga `continue-on-error`.

**Bug real encontrado en la propia verificación (antes de dar el cambio por
bueno):** los mensajes con emoji (`🔮`) crashean `print()` en consola
Windows (cp1252) — mismo incidente ya documentado y arreglado una vez en
`duration_monitor.py`. Aplicado el mismo fix (`sys.stdout`/`stderr`
`.reconfigure(encoding="utf-8", errors="replace")`) tanto en
`check_koncorde_alerts.py` como, preventivamente, en
`telegram_portfolio_bot.py` (que ahora también puede imprimir mensajes de
error de la IA en consola).

**Verificado sin gastar ninguna llamada a API real (primera pasada):**
`evaluate()` contra el snapshot real de `koncorde_data.json` reproduce
exactamente el caso que motivó el cambio — CRESY: D `blue_positive=True`
(azul débil pero positivo), 3D `blue_positive=False`, W `blue_positive=False`
(ambos en distribución), tal como lo describió el usuario. Flujo completo
probado en un sandbox con ficheros temporales: crear 2 alertas Koncorde
para el mismo ticker con condiciones distintas (coexisten), `/kalerts` las
lista, `/delkalert` borra ambas, `check_koncorde_alerts.py` dispara solo la
condición verdadera (D) y deja intacta la falsa (W) y la de un ticker sin
datos — confirmado que `bot_alerts.json` (precio) nunca se toca.

**Verificación en producción (2026-08-17, tras añadir `GROQ_API_KEY` a
GitHub Secrets y Railway):**

- **Bug real encontrado y corregido:** `KONC_PARSE_MODEL` usaba el alias de
  Haiku de `force_analyze.py` (`anthropic/claude-haiku-4-5-20251001`), que
  OpenRouter rechaza hoy con `400 not a valid model ID` — habría hecho que
  el parser NL fallara silenciosamente en producción (degradando siempre a
  "no he podido entender la alerta"). Corregido al slug que sí usa
  `paper_trading.py`/`MODEL_PRICING` (`anthropic/claude-haiku-4.5`),
  confirmado con una llamada real. Con el fix, 2/3 peticiones NL de prueba
  parsearon correctamente (incluida la frase original del usuario sobre
  CRESY); la tercera ("...entre en acumulación en 3 dias") la rechazó el
  modelo por ambigüedad entre "timeframe 3D" y "dentro de 3 días" —esperado
  y no un fallo: el parser nunca adivina, y la sintaxis exacta
  (`/kalert NVDA 3d state_accumulation`) sigue disponible como vía segura.
- **Circuito completo probado con Telegram real** (no simulado): creada una
  alerta real (`CRESY d blue_positive`, sintaxis exacta) → mensaje real
  "✅ Alerta creada" enviado → `check_koncorde_alerts.py` ejecutado contra
  el snapshot real de Koncorde → condición evaluada `True` → mensaje real
  "🔮 Alerta Koncorde" enviado → alerta autoeliminada
  (`koncorde_bot_alerts.json` quedó en `[]`). Confirma la cadena completa
  creación→persistencia→evaluación→notificación→autoborrado con las
  credenciales de producción.
- **Pendiente de confirmar por el usuario, no verificable desde aquí:** que
  ambos Telegram realmente llegaron (no hay forma de leer el chat desde el
  entorno de desarrollo), y la transcripción de voz real vía Groq —  no hay
  `GROQ_API_KEY` en el `.env` local, así que esa llamada concreta no se ha
  probado end-to-end todavía; queda confirmarla enviando una nota de voz
  real al bot (Railway ya tiene la clave) o añadiendo la clave también al
  `.env` local para una prueba aquí mismo.

### Fuera de alcance (explícito)

Condiciones sobre otros indicadores (MACD, ATLAS Mini, RSI, insider
activity) — el vocabulario cerrado cubre solo Koncorde blue/green/estado
por timeframe, ampliable si hace falta. Re-armado automático tras
dispararse (alertas de un solo uso, igual que las de precio). Cualquier
cambio a PCS/rot_score/carteras — esto es una utilidad del bot, no toca el
motor de picks.

**Nota 2026-08-18:** la confirmación interactiva antes de guardar una
alerta mal-parseada, listada aquí originalmente como "fuera de alcance",
sí se implementó — ver sección siguiente ("Fixes de producción...").

---

## Fixes de producción + confirmación de ticker + multi-timeframo — Alertas Koncorde (implementado 2026-08-18)

El día después de lanzar las alertas Koncorde (sección anterior), varias
sesiones de depuración en vivo con el usuario encontraron 4 problemas
reales de producción, todos en `scripts/telegram_portfolio_bot.py`.

### 1. Fallos silenciosos — mismo patrón ya visto con los tokens de Telegram/Cava

`cmd_kalert_set()`/`cmd_kalert_delete()` enviaban "✅ Alerta creada"/"eliminada"
**incondicionalmente**, sin comprobar si `_save_konc_alerts()` (escritura vía
GitHub API en Railway) había fallado de verdad — el usuario podía recibir
confirmación de éxito sobre una alerta que nunca se guardó. `_save_konc_alerts()`
ahora devuelve `bool` y ambos comandos avisan explícitamente si el guardado falla.

`_download_telegram_file()` (paso previo a transcribir una nota de voz)
envolvía cualquier excepción en un `"No pude descargar la nota de voz."`
genérico, sin exponer la causa real — obligaba a mirar logs de Railway
(a los que el usuario no siempre tiene acceso a mano) para saber si era un
timeout, un fallo de la API de Telegram, etc. Ahora devuelve
`(bytes|None, error_detail|None)` y el mensaje al usuario incluye el detalle
del error directamente en el chat.

`_parse_koncorde_alert_nl()` devolvía `None` en silencio si faltaba
`OPENROUTER_API_KEY`, indistinguible de "el modelo no entendió la petición"
— `cmd_kalert()` comprueba ahora la env var por separado antes de llamar al
parser NL y da un mensaje específico ("falta configurar OPENROUTER_API_KEY")
en vez del genérico "no he podido entender la alerta".

**Hallazgo de diagnóstico, no bug:** en la investigación se confirmó que
Railway sí corre en continuo y sí escribe correctamente vía GitHub API
(commits `bot: update state` recurrentes) — el problema real en cada caso
fue la falta de visibilidad del error, no que el mecanismo estuviera roto.

### 2. Ticker inferido del nombre de la empresa, con confirmación

El prompt original de `_parse_koncorde_alert_nl()` decía explícitamente "no
inventes un ticker si no hay uno reconocible" — con esto, decir el nombre de
la empresa en vez del símbolo (ej. "Loma" en lugar de "LOMA", el ticker real
de Loma Negra) hacía que el modelo rechazase la petición entera. Demasiado
rígido para lenguaje natural/voz, donde la gente dice nombres, no símbolos.

Cambio: el modelo puede ahora proponer un ticker inferido con su
conocimiento general (`"Loma"->LOMA`, `"Apple"->AAPL`, `"banco Galicia"->GGAL`),
marcado `"ticker_guessed": true`. `cmd_kalert()` **no crea la alerta
directamente** en ese caso — la deja pendiente
(`_pending_ticker_confirmation`, dict en memoria por `chat_id`, sin
persistir a GitHub) y pide confirmación.

**Primera versión (descartada el mismo día, feedback del usuario):** pedía
reescribir el comando completo en sintaxis exacta para confirmar — "un
rollo" según el usuario, sobre todo viniendo de una nota de voz. Sustituido
por: responder **"ok"** (o vale/sí/confirmo/correcto) confirma la propuesta
tal cual; escribir directamente un ticker distinto la corrige manteniendo
el mismo timeframe/condición ya parseados — sin repetir nada.

Ventana de confirmación: 15 minutos, en memoria únicamente (no en
`state.json`/GitHub) — bot de un solo usuario, y si Railway se reinicia a
mitad de una confirmación pendiente, el coste es simplemente volver a mandar
la petición original, igual que cualquier otro reinicio transitorio. No
justifica la complejidad de persistirlo.

Un mensaje de texto plano sin confirmación pendiente activa, o que no
coincide con "ok"/ticker, se ignora tal cual (comportamiento previo, sin
cambios) — no se ha añadido gestión general de conversación al bot, solo
esta única ventana de confirmación acotada.

### 3. Alertas en varios timeframes con semántica OR

Petición real que motivó esto: *"avisar si banco de Galicia... pasa a azul
positivo o bien en la vela diaria o bien en la vela semanal"* — el schema
solo admitía un timeframe por alerta, así que el parser NL rechazaba la
petición completa con "timeframe ambiguo: solicita 'd' o 'w', pero no
especifica cuál es prioritario" (correcto según su instrucción de entonces,
pero la petición del usuario no era ambigua — pedía ambos con un OR).

Solución **sin tocar el evaluador** (`koncorde_alert_conditions.py`,
`check_koncorde_alerts.py` siguen operando sobre un timeframe por fila, sin
cambios): tanto la sintaxis exacta (`/kalert GGAL d,w blue_positive`, lista
separada por comas) como el parser NL (campo `"timeframes"`, ahora siempre
una lista) devuelven varios timeframes, y `cmd_kalert_set()` crea **una fila
independiente por cada uno** en `koncorde_bot_alerts.json`. Como cada fila
ya se evaluaba y autoeliminaba de forma independiente, esto da la semántica
OR pedida (avisa con la que se cumpla primero, las demás siguen activas)
sin ninguna lógica nueva de evaluación multi-timeframe.

### Verificado

Los 4 cambios probados con las peticiones reales que fallaron en producción
(`_parse_koncorde_alert_nl()` llamado en vivo contra OpenRouter, no
mockeado): "Loma" → propone `LOMA` con `ticker_guessed=True`; "banco de
Galicia... diario o semanal" → `GGAL`, `timeframes=['d','w']`,
`ticker_guessed=True`. Flujo de confirmación completo probado con
`_send`/`_load_konc_alerts`/`_save_konc_alerts` redirigidos a un directorio
temporal (sin tocar datos reales ni gastar llamadas a Telegram): "ok" crea
las 2 filas (`GGAL`/`d` y `GGAL`/`w`) con un único mensaje combinado;
responder con otro ticker corrige manteniendo timeframe/condición; un
mensaje no relacionado no consume la confirmación pendiente; una
confirmación con más de 15 minutos expira y se ignora. Confirmado además en
producción real (no solo local) que las alertas de IRS y LOMA de sesiones
anteriores del mismo día quedaron correctamente guardadas vía GitHub API.

### Fuera de alcance (explícito)

Persistir `_pending_ticker_confirmation` fuera de memoria. Multi-ticker o
multi-condición en una sola petición (solo multi-*timeframe*, que era lo
pedido). Deshacer la propuesta de ticker si el usuario no responde nada
(expira sola a los 15 min, no hay mensaje de "se ha cancelado").

---

## GEX (dealer gamma exposure) — piloto, no integrado (2026-08-18)

Origen: un análisis externo sobre `duration.html` señaló que evaluar la
fuerza de un "desanclaje" de tipos requiere saber el posicionamiento de
gamma de los dealers (largo vs corto), dato que el proyecto no tenía.
Acordado con el usuario: montar un piloto DIY antes de decidir si
incorporarlo. Piloto completo en `research/gex_monitor_pilot/` (script +
`HALLAZGOS.md` con el detalle de la verificación).

**Qué se construyó:** `gex_pilot.py` descarga la cadena de opciones real de
`^SPX` vía yfinance (verificado: 53 vencimientos con OI/IV reales, no solo
disponible para ETFs) y calcula Net GEX con la convención estándar de la
mayoría de explicadores públicos (dealers asumidos largos en calls/cortos
en puts que compran los clientes): `GEX = Gamma_BlackScholes × OI × 100 ×
Spot² × 0.01`, `Net = Σcalls − Σputs`, más el nivel de "gamma flip"
(zero-gamma) por barrido de spot hipotético.

**Verificación — resultado matizado, no un simple sí/no:** el primer
contraste (Net GEX del piloto vs una cifra pública de flashalpha.com)
mostró signo opuesto, lo que en un primer momento pareció indicar un fallo
de metodología. Al mirar el nivel de gamma flip en vez de solo el signo, el
piloto (7746.7) y el externo (7739) coincidían casi exactamente (~0.1%) —
el signo distinto se explicaba por un movimiento real de SPX cruzando esa
zona entre los dos momentos comparados (7785→7745→7701 en 3 sesiones), no
por un error de cálculo. Pero, al intentar recontrastar el spot que citaba
la página externa contra el histórico intradía real de Yahoo para esa misma
franja horaria, aparecía un desajuste de ~30 puntos que ninguna barra real
del día explicaba — no se pudo confirmar que esa fuente "gratis" sirviera
datos realmente frescos al consultarla de forma automatizada, así que
tampoco sirvió como benchmark limpio.

**Conclusión — no integrado, no por un bug sino por falta de forma de
verificarlo:** el cálculo corre correctamente sobre datos reales y el flip
level es plausible, pero (1) no se encontró ninguna fuente gratuita
verificablemente en vivo contra la que contrastar signo/magnitud con
confianza, y (2) la convención "toda la OI de puts es venta de dealers" es
una aproximación — el dato que la resolvería de verdad (desglose
customer/firm/market-maker de la OCC) es de pago (Cboe Options Open-Close
Volume Summary, DataShop). A diferencia del proxy de MOVE en
`duration.html` (calibrado contra 5 años de histórico real) o
`calcAtlasMini`/`calcCMF` (fórmulas deterministas sin ambigüedad), aquí no
hay forma barata de saber si el número de un día cualquiera es correcto —
mismo principio del proyecto: no mostrar un número al usuario sin poder
verificarlo. No se toca `duration.html`, `positioning.html` ni ninguna
cartera. El script queda en `research/` como base de cálculo reutilizable
si en el futuro aparece una fuente con desglose real de posicionamiento.

---

## Captura diaria completa de Portfolio Tracker (implementado 2026-08-20)

Origen: el usuario preguntó por qué algunas celdas de Flow Score/ATR% en
`portfolio.html` no mostraban flecha de tendencia ni tooltip. Diagnóstico:
`signals_history.json` (el histórico que alimenta esas flechas) solo se
escribía desde un `useEffect` del navegador, y solo si
`computeFlowScore()`/`computeEarlyFlowScore()` no salían `null` ese día —
si fallaba un solo input, se perdía la fila entera, incluido el ATR%. Más
de fondo: **toda la captura dependía de que alguien tuviera el dashboard
abierto** — si no se abría `portfolio.html` un día, no quedaba ningún
registro. El usuario pidió corregirlo con un objetivo más amplio: un
registro diario completo e independiente de la consulta, para poder
evaluar/backtestear estas señales a posteriori.

**Decisión de arquitectura (confirmada con el usuario antes de tocar
código):** correr la captura como step nuevo del pipeline de GitHub Actions
(único sitio que cumple literalmente "aunque yo no lo consulte" — funciona
aunque el PC esté apagado, a diferencia de una tarea programada local),
acotada a los tickers de `portfolio.json` (no todo el universo de AI Picks
Lab), en un archivo nuevo dedicado (`docs/data/portfolio_daily_snapshot.jsonl`)
en vez de extender `signals_history.json` — así no hereda la limitación de
"sin flowScore no se guarda nada".

### Refactor previo — `shared/quote-lib.js` (nuevo)

Para que la captura del pipeline no pudiera divergir de lo que muestra el
dashboard en vivo (mismo riesgo ya vivido con `calcCMF` duplicado entre
JS/Python, ver sección "Koncorde Plus v2"), se extrajo de `server.js` toda
la lógica de `/api/quote/:symbol` — `calcRSI`, `calcMACD`, `calcAtlasMini`,
`calcATR`, `calcSMA`, `calcCMF`, `calcOBV`, `getKoncordeData`,
`getInsiderActivityData`, `fetchYahooChartRaw`/`fetchYahooChartFresh`, y el
propio ensamblado de la respuesta — a un módulo CommonJS requerible tanto
desde `server.js` (la ruta ahora es un wrapper de 6 líneas sobre
`buildQuoteData()`) como desde un script Node standalone sin arrancar
Express. `shared/flow-score.js` ganó un export CommonJS opcional al final
del archivo (`if (typeof module !== 'undefined' && module.exports)`) —
sigue cargándose igual como `<script>` plano en el navegador (donde
`module` no existe), pero ahora también es `require()`-able.

### `scripts/portfolio_daily_snapshot.js` (nuevo) — Step 9g del pipeline

Lee `portfolio.json` (raíz del repo), construye el universo único de
tickers de todas las secciones, y para cada uno llama a
`buildQuoteData()` (idéntica a la que sirve `/api/quote/:symbol`) más
`computeFlowScore()`/`computeEarlyFlowScore()` de `shared/flow-score.js` —
el `prev` que necesita Early Flow (transición de estado Koncorde,
compresión de ATR%) se lee de la fila más reciente de ese mismo ticker en
el propio snapshot, no de `portfolio.json.lastSessionSnapshot` — así el
script es autosuficiente y no depende de que el navegador haya corrido
antes.

**Sin la puerta de `signals_history.json`:** escribe la fila completa
(121 campos — precio, retornos, RSI, MACD, ATLAS Mini, ATR%, CMF, Koncorde
D/3D/W con las 5 últimas barras de cada serie, insider activity, SMAs, OBV,
anti-extensión) siempre que el fetch a Yahoo funcione, con
`flowScore`/`earlyFlow` como campos añadidos que pueden salir `null` sin
que eso tumbe el resto de la fila. Corrige de raíz el gap que motivó la
pregunta original.

Dedup por `date+ticker` (mismo patrón que `rotation_history`/
`mirror_signals.jsonl`/etc.) — si un ticker ya tiene fila hoy, se omite;
así el pipeline puede correr 2×/día sin duplicar. Lotes de 8 tickers
concurrentes con pausa de 300ms entre lotes (buen ciudadano con Yahoo, sin
rate limiter dedicado — no hace falta, Yahoo no impone cuota diaria como
Form4API). `--dry-run`/`--tickers=A,B,C`/`--report` para pruebas y
auditoría manual.

### Pipeline (`.github/workflows/market-update.yml`)

Primer script Node del pipeline — hasta ahora era 100% Python. Steps
nuevos: `actions/setup-node@v4` (Node 20, cache npm) + `npm install
--omit=dev` (sin dependencias nuevas — `node-fetch`/`express`/`cors`/
`dotenv` ya estaban en `package.json` para `server.js`), antes de Step 10
(paper trading). Step 9g corre en **ambos** runs del día (a diferencia de
Insider Activity/Mirror Espejo, que son solo mañana) — esto es una
captura de mercado con datos que sí cambian intradía, no una consulta con
cuota diaria limitada. `continue-on-error: true`, mismo criterio que el
resto de steps de observación del pipeline.

**Verificado con datos reales:** `buildQuoteData()` extraída probada
contra Yahoo en vivo (AAPL: 118 campos, valores plausibles; ticker
inválido → `Error` con `.httpStatus=404`, igual que el comportamiento HTTP
anterior de la ruta). Escritura real + dedup probados con 2 tickers
(segunda ejecución el mismo día: 0 filas nuevas, confirma dedup). Captura
completa contra los 111 tickers reales de `portfolio.json`: 110/111
capturados (único fallo: `TSND.V`, ya documentado como posiblemente
deslistado en la sección de Koncorde mini-chart — no es un fallo de este
cambio), 100% con `flowScore` no-null ese día. YAML del workflow validado
con PyYAML tras la edición (36 steps, parseable). `server.js` sigue
corriendo en la terminal del usuario tras el refactor de
`/api/quote/:symbol` — pendiente de que el usuario lo reinicie para que
recoja el cambio (mismo aviso que [[project_dev_server_persistent]]).

### Fuera de alcance (explícito)

Universo AI Picks Lab (`ai_candidates.json`) — el usuario pidió
explícitamente acotar a Portfolio Tracker. Backfill retroactivo de fechas
anteriores a 2026-08-20 (Yahoo no tiene snapshots de "lo que se veía ese
día" para insider/Koncorde, solo precio — un backfill parcial sería
engañoso). Ningún análisis/backtest sobre los datos capturados todavía —
este cambio es solo la instrumentación, mismo criterio de "observar primero"
que el resto de features nuevas del proyecto.

---

## Botón "Exportar histórico" — Portfolio Tracker (implementado 2026-08-20)

Continuación directa de la captura diaria completa (sección anterior). Con
`portfolio_daily_snapshot.jsonl` ya acumulando datos, el usuario pidió un
botón separado (no integrado en "Copiar para LLM"/"Exportar TODO a LLM",
que solo exportan el snapshot de HOY) para exportar el histórico de uno o
varios tickers en un rango de fechas — pensado para pegarlo en un LLM
externo y pedirle un backtest/estudio ad-hoc.

**Dos decisiones confirmadas con el usuario antes de implementar** (ambas
más amplias que la propuesta inicial): exportar los **121 campos crudos**
tal cual están en el jsonl (no una tabla curada como el resto de exports)
y permitir **selección múltiple/todos los tickers**, no solo uno.

**`server.js` — dos endpoints nuevos**, filtrado server-side (no se manda
el jsonl completo al navegador — ese archivo solo crece):
`GET /api/portfolio-history/meta` (lista de tickers + rango de fechas
disponible, para poblar el modal) y `GET /api/portfolio-history?tickers=A,B&from=...&to=...`
(`tickers` vacío = todos). Pre-filtro por regex sobre la línea cruda antes
de `JSON.parse` — evita parsear filas que no van a coincidir cuando el
archivo crezca a decenas de MB.

**`portfolio.html` — `HistoryExportModal`**, mismo patrón que
`PositionModal`/`UniverseModal` (añadido al discriminador `modal?.type`
existente). Checkbox "Todos los tickers" + grid de checkboxes individual,
2 inputs de fecha (rango disponible real como min/max), y **dos acciones**
en vez de una: "Copiar" (clipboard, como el resto de exports) y "Descargar
.md" — añadida la segunda a propósito porque combinar todos los campos
crudos + todos los tickers puede generar un export grande (verificado: 110
tickers × 1 día = 587 KB de markdown) que crecerá con el rango de fechas;
"Descargar" no tiene el límite práctico que sí puede tener pegar un bloque
enorme en el portapapeles/chat de un LLM.

**Formato:** no es una tabla markdown de 121 columnas (ilegible) — un
`## TICKER (N días)` por ticker con un bloque ` ```json ` conteniendo el
array de filas crudas, ordenadas por fecha. Mantiene el "estilo" del resto
de exports (headers markdown, cabecera con metadata) sin sacrificar
completitud de datos.

**Verificado en producción real** (Edge headless vía CDP, servidor
reiniciado tras los cambios en `server.js`): los dos endpoints probados
con curl contra datos reales (`meta` devuelve 110 tickers + rango
2026-08-20→2026-08-20; filtro por 2 tickers devuelve exactamente esas 2
filas con 121 campos cada una; rango sin datos devuelve `count:0`; sin
filtros devuelve todo). Flujo de UI completo probado con Puppeteer
conectado por CDP: botón abre el modal, `meta` carga y puebla las fechas
por defecto, desmarcar "Todos" revela la grid de tickers, seleccionar uno
y pulsar "Copiar" genera el markdown real (interceptando
`navigator.clipboard.writeText`) y muestra el toast correcto — cero errores
de consola. Exportación "todos los tickers, hoy" verificada aparte (587 KB,
formato correcto, sin errores).

---

## Situaciones Especiales — sistema unificado de alertas compuestas (implementado 2026-08-26)

Origen: el usuario quiso hacer seguimiento de una tesis de trade discrecional
sobre ADS.DE (Adidas) — Flow Score cruzando a positivo, ratio ADS/FEZ
mejorando, Koncorde D pasando a acumulación, todo simultáneamente — y pidió
explícitamente **no** construir un sistema de alertas paralelo a `/kalert`:
*"Mi preferencia sería caminar hacia un sistema único de alertas que
permitiese desde las más simples hasta las más complejas"*. Este cambio
generaliza `/kalert` (1 condición Koncorde sobre 1 ticker) a un sistema de N
condiciones de distinto tipo, todas exigidas a la vez (AND), con una UI en
`portfolio.html` para componerlas — en vez de crear una arquitectura nueva.

**Un único fichero, un único evaluador, esquema generalizado con
compatibilidad retroactiva.** `docs/data/koncorde_bot_alerts.json` sigue
siendo el único almacén — las ~2 alertas simples ya activas (IRS, GGAL,
creadas vía `/kalert`) no se migraron ni se tocaron, se leen igual vía un
shim de compatibilidad en tiempo de lectura.

### 1. `scripts/koncorde_alert_conditions.py` — generalizado, no reemplazado

`evaluate()`/`describe()`/`CONDITIONS`/`VALID_TIMEFRAMES`/`TIMEFRAME_LABELS`
(las 7 condiciones Koncorde de siempre) quedan **sin tocar** —
`telegram_portfolio_bot.py` los sigue importando igual. Todo lo nuevo es
aditivo:

- `get_conditions(row)` — shim de lectura: si la fila ya tiene `conditions`
  (formato nuevo), la devuelve tal cual; si no (fila vieja de `/kalert`,
  `ticker`/`timeframe`/`condition` sueltos), la envuelve en
  `[{"type":"koncorde", "timeframe":..., "condition":...}]`. Nunca reescribe
  el fichero — es una traducción al vuelo, no una migración.
- `evaluate_flow(rows, op)` — condición sobre Flow Score
  (`cross_positive`/`improving`), usando las 2 filas más recientes de
  `docs/data/portfolio_daily_snapshot.jsonl` para ese ticker (ver sección
  "Captura diaria completa de Portfolio Tracker" más arriba — ya cubre TODOS
  los tickers de `portfolio.json`, incluidos los de solo watchlist con
  `shares:0`, así que añadir ADS.DE al portfolio ya da Flow/ΔFlow gratis).
- `evaluate_ratio(trend, op)` — condición sobre un ratio custom
  (`improving` = por encima de su SMA reciente), delega el fetch en
  `ratio_signal.py` (punto 2).
- `evaluate_single_condition(condition, ctx)` / `evaluate_conditions(conditions, ctx)`
  — dispatcher + AND compuesto, con la misma semántica de tres valores que
  ya tenía `evaluate()`: `True` (dispara), `False` (al menos una condición
  es definitivamente falsa — gana sobre cualquier `None`), `None` (ninguna
  es `False` pero falta dato en alguna — sigue pendiente, nunca se
  descarta ni se dispara con datos a medias).
- `describe_conditions(ticker, conditions)` — resumen en ES para Telegram y
  para la UI, generaliza `describe()`.

### 2. `scripts/ratio_signal.py` (nuevo)

Distinto de `shared/relative-ratio-registry.js`/`relative_flow_lib.py`
(registro fijo de ~50 pares macro/sector) — aquí el usuario elige **cualquier
par de tickers** desde la UI (ADS.DE/FEZ, ADS.DE/NKE), sin necesidad de dar
de alta un ratio en el registro. `fetch_ratio_trend(ticker_a, ticker_b,
sma_window=20)`: `yf.download` de ambos, join por fecha (`dropna`), ratio =
`close_a/close_b`, `improving` = ratio de hoy por encima de su SMA de 20
sesiones — misma convención que "precio sobre su SMA20" ya usada en el
proyecto. **Caveat conocido, no arreglado en v1:** sin conversión de divisa
— `ADS.DE/NKE` (EUR/USD) mezcla rendimiento relativo real con movimiento
EUR/USD. **Corrección 2026-08-27:** la nota original de este mismo párrafo
decía que `ADS.DE/FEZ` era EUR/EUR "limpio" — verificado ahora contra
`fast_info`/`get_info()` de yfinance que **FEZ cotiza en USD** (NYSE Arca,
"State Street SPDR EURO STOXX 50 ETF" — el nombre sigue un índice
denominado en EUR, pero el ETF en sí cotiza en dólares), así que
`ADS.DE/FEZ` **también es cross-currency (EUR/USD)**, igual que `ADS.DE/NKE`
— la afirmación anterior no estaba verificada con el cuidado habitual del
proyecto. `EXV5.DE` (iShares STOXX Europe 600 Consumer Discretionary UCITS
ETF, Xetra) sí cotiza en EUR — es el benchmark limpio de verdad si se
necesita comparar ADS.DE contra algo sin ruido de divisa. Verificado en
vivo: `ADS.DE/FEZ ratio_now=2.1031 sma20=2.2201 improving=False`,
`ADS.DE/EXV5.DE ratio_now=3.8167 sma20=3.8961 improving=False`,
`ADS.DE/NKE ratio_now=3.9011 sma20=3.8646 improving=True`.

### 3. `scripts/check_koncorde_alerts.py` — generalizado

`run()` ahora: construye `conditions` de cada alerta vía `get_conditions()`,
carga `portfolio_daily_snapshot.jsonl` una sola vez por ejecución **solo si**
alguna alerta tiene una condición tipo `flow`, y llama a `ratio_signal.py`
(con caché en memoria por par, una sola llamada por par aunque varias
alertas lo compartan) **solo si** alguna tiene una condición tipo `ratio` —
evita gasto de red/proceso en el caso simple de solo-Koncorde, que sigue
funcionando exactamente igual que antes. Dispara y auto-borra (one-shot,
igual que siempre) solo cuando `evaluate_conditions()` devuelve `True` para
**todas** las condiciones de la alerta.

### 4. `server.js` — nuevas rutas, mismo patrón que `/api/universe/add`

Sin credenciales nuevas — se reutiliza el mecanismo ya probado de
`/api/universe/add` (escribe el fichero en disco + `git add/commit/push
origin master` en background, fire-and-forget) en vez del PAT que usa
`telegram_portfolio_bot.py`. Decisión explícita del usuario
("Push local automático (Recomendado)") tras comparar ambos mecanismos —
ver también el hallazgo de que `/api/portfolio`/`/api/state` **no** hacen
push (solo disco local), así que no eran una base válida para esto.

- `GET /api/special-situations` — lista todas las entradas.
- `POST /api/special-situations` — crea/edita (upsert por `id`).
- `POST /api/special-situations/delete` — borra por `id`.

**`_readSpecialSituations()` aplica su propio shim de compatibilidad, en el
mismo espíritu que `get_conditions()` en Python pero resolviendo un problema
distinto:** las alertas viejas de `/kalert` no tienen campo `id` en absoluto,
y tanto el `key` de React como el `filter(s => s.id !== id)` del borrado
necesitan uno. Se les asigna un id sintético determinista
(`legacy_{ticker}_{timeframe}_{condition}`) **solo en memoria al leer**,
nunca se reescribe el fichero por esto — si el usuario edita una alerta
vieja desde la UI nueva, el POST la persiste con ese mismo id ya en el
formato `conditions:[...]`, migrándola de forma natural al primer toque.
Bug real encontrado y corregido en la propia verificación: sin este shim,
las dos alertas legacy (IRS, GGAL) comparten `id: undefined` → React avisaba
de "duplicate key" y el botón de borrar de cualquiera de las dos fallaba con
`400 id required`.

### 5. `portfolio.html` — sección "Situaciones Especiales" + `SpecialSituationModal`

Widget nuevo entre "Ranking de Setups" e "Insider Activity" (mismo patrón
visual `border:1px solid #e0e0e0` / header `background:#354f73` que el
resto de tablas de la página), no una pestaña aparte — reutiliza el ciclo de
fetch y los `prices`/`prevSessionMap` ya cargados en el componente.

- **Evaluador cliente** (`checkKoncordeCond`/`checkFlowCond`/`checkRatioCond`/
  `evaluateSituationConditions`) — réplica deliberada en JS del evaluador
  Python de `koncorde_alert_conditions.py` (mismos 3 valores True/False/None,
  mismo AND), para mostrar el estado en vivo con los datos ya en memoria del
  navegador sin pedirle nada al backend. Mismo patrón de duplicación
  JS/Python ya aceptado en el proyecto (ver `calcCMF`) — constantes
  compartidas explícitamente (`SMA_WINDOW=20` en ambos lados).
- **Ratios en cliente:** `fetchRatioTrendClient(tickerA, tickerB)` reutiliza
  `/api/history/:symbol` (ya genérico) en vez de pedirle a `server.js` una
  ruta de ratio nueva — join por fecha + SMA20 en el navegador, cacheado en
  `ratioTrends` por par, un fetch por par referenciado por cualquier
  situación (no por fila).
- **`SpecialSituationModal`** — mismo patrón visual que `UniverseModal`
  (`.overlay`/`.modal`, estilos locales `inp`/`sel`, `.field`/`.row2`):
  ticker, etiqueta, selector de Flow Score, 3 selects Koncorde D/3D/W, hasta
  3 pares de ratio (ticker + label + checkbox "exigir mejora" para que
  cuente como condición). Ticker deshabilitado en modo edición.
  Tabla lista cada situación con badges de color por condición
  (✓/✗/… pendiente) y un indicador compuesto "Armada" (🔥 SÍ / No /
  pendiente).

### Verificado end-to-end (Edge headless vía CDP, servidor local real)

Sintaxis JSX transpila sin errores (`@babel/standalone`). Con el servidor
real corriendo: las 2 alertas legacy renderizan correctamente vía el shim
(`✗ Blue positivo (W)`, dato real de hoy); creación de una tesis ADS.DE de
prueba (Flow cross_positive + Koncorde D state_accumulation + ratio
ADS.DE/FEZ improving) vía la UI real — las 3 condiciones se evalúan con
datos en vivo (2 pendientes por falta de historial de 2 sesiones para
ADS.DE en el snapshot/falta de Koncorde para ese ticker, 1 resuelta de
verdad contra Yahoo real), compuesto "Armada: No" correcto (una condición
en pendiente + ninguna en false puro en este caso concreto, evaluado
correctamente por la cascada False-gana-sobre-None); apertura del modal de
edición confirma los datos precargados y el ticker bloqueado; borrado desde
la UI confirmado con el toast correcto y el `git push` real en el log del
servidor (`chore: remove situación especial ... from dashboard`). Cero
errores/warnings de consola tras el fix del `id` sintético del punto 4.
Los commits de prueba (`TESTX`, `ads_de_...`) se crearon y revirtieron
durante la verificación — `docs/data/koncorde_bot_alerts.json` quedó de
nuevo con exactamente las 2 alertas legacy, confirmado con `git log`.

### Explícitamente fuera de alcance (v1)

Componer tesis multi-condición por voz/texto libre en Telegram (el parser NL
de `/kalert` sigue cubriendo solo 1 condición Koncorde simple — la
composición de tesis complejas es solo-UI en v1). Lógica OR/booleana más
allá de AND. Ratios de más de 2 patas o fórmulas custom más allá de `A/B`.
Conversión de divisa en `ratio_signal.py`. Ningún cambio en
`.github/workflows/market-update.yml` — el Step 9c2 ya ejecuta
`check_koncorde_alerts.py` y `yfinance` ya es dependencia del pipeline.

### Primera tesis real: ADS.DE — starter en reversión (creada 2026-08-27)

Primer uso real del sistema, creada vía `POST /api/special-situations`
(id `ads_de_starter_reversal`) directamente contra el servidor local del
usuario ya en marcha — mismo path de producción que si se hubiera creado
desde el modal de `portfolio.html`.

**Condiciones exigidas (AND):**
```
Flow Score cruza de negativo a positivo
+ ADS.DE/FEZ mejora (por encima de su SMA20)
+ Koncorde D: blue_positive
```
`"Koncorde D → Acumulación/Alza"` (como lo pidió el usuario) se tradujo a
la condición ya existente `blue_positive`, no a una condición nueva: por
definición de los 4 estados Koncorde (`Alza`: blue≥0,green≥0 · `Acumulación`:
blue≥0,green<0 · `Distribución`/`Baja`: blue<0), "Acumulación o Alza" es
exactamente `blue≥0` — no hace falta lógica OR nueva, `blue_positive` ya lo
cubre con precisión.

**Ratios de seguimiento no obligatorios** (`ratio_pairs`, sin marcar
"exigir mejora"): `ADS.DE/EXV5.DE` (iShares STOXX Europe 600 Consumer
Discretionary UCITS ETF — el "sector consumo europeo" pedido) y
`ADS.DE/NKE`. Se fetchean igual en segundo plano (el `useEffect` de
`portfolio.html` itera todos los `ratio_pairs` de cada situación, no solo
los marcados como condición) pero **no aparecen como fila en la tabla de
condiciones de la UI** — v1 solo renderiza lo que está en `conditions[]`.
Si se quiere verlos en pantalla habría que añadir una vista de "métricas de
contexto" separada de las condiciones de disparo — no incluido en este
cambio.

**Bug real encontrado y corregido en el propio proceso de creación:** un
primer intento de crear la situación vía `curl -d '{...}'` con el guion
largo "—" y una "ó" incrustados directamente en el string de shell corrompió
esos caracteres a `�` (carácter de reemplazo Unicode) **de verdad en
disco** — no era un artefacto de visualización de la terminal, se guardó
corrupto en `docs/data/koncorde_bot_alerts.json`. Diagnosticado leyendo el
fichero directamente (no vía `curl | python -m json.tool`, que enmascaraba
el problema con su propio round-trip de encoding). Corregido escribiendo el
payload a un fichero JSON (encoding garantizado) y usando
`curl --data-binary @archivo` en vez de un string inline — la entrada
corrupta se borró y se recreó limpia (con el label en ASCII plano para
evitar el problema de raíz, no solo mitigarlo). **Lección para futuras
escrituras a `docs/data/*.json` con acentos/rayas vía curl+bash en este
entorno:** preferir siempre `--data-binary @archivo` a un string inline.

**Corrección de dato de mercado, no solo de código:** verificando el ratio
`ADS.DE/FEZ` se descubrió que la nota previa de este archivo (arriba, en la
sección de `ratio_signal.py`) que llamaba a ese par "EUR/EUR, limpio" era
incorrecta — FEZ cotiza en USD, no en EUR (ver corrección fechada 2026-08-27
en esa sección). El caveat de mezcla de divisa aplica también a la condición
obligatoria `ADS.DE/FEZ`, no solo al ratio de contexto `ADS.DE/NKE`.

**Datos sembrados manualmente el mismo día para no esperar al próximo run
programado** (2026-08-27, fuera del pipeline 08:00/20:00 UTC): `python
scripts/koncorde_calculator.py` (pasada completa, 202/204 tickers del
universo, incluye ADS.DE por primera vez — antes no tenía ninguna entrada en
`koncorde_data.json`) + `node scripts/portfolio_daily_snapshot.js
--tickers=ADS.DE` (primera fila de `flowScore` para el ticker). Snapshot del
día de creación: `konc_d_state=accumulation` (blue=11.58, ya cumple
`blue_positive`), `konc_3d_state=distribution`, `konc_w_state=distribution`,
`flowScore=-12.4`. Con solo 1 sesión de historial, la condición de Flow
queda en pendiente (`None`, nunca `False`) hasta que exista una segunda
fila — se resolverá sola en la próxima captura diaria (pipeline 2×/día).
Resultado del día: `overall=False` (el ratio ADS.DE/FEZ está por debajo de
su SMA20 hoy) — la tesis correctamente no está armada todavía.

**No implementado, señalado en vez de inventado:** `ΔFlow 5d` como métrica
formal (distinta del delta día-a-día ya existente vía `TrendArrow`) e
`InflectionScore` — ninguno de los dos existe en el sistema; no se
construyeron ad hoc para esta tesis. `Early` (Early Flow Score) y el estado
Koncorde W ya son visibles gratis para cualquier ticker de `portfolio.json`
en la tabla "Ranking de Setups" una vez tiene `flowScore`/`earlyFlow`
reales, sin cambio adicional.

Los ficheros de datos tocados por la pasada manual (`ai_candidates.json`,
`koncorde_data.json`, `koncorde_failed_state.json`,
`koncorde_signals_history.jsonl`, `portfolio_daily_snapshot.jsonl`) se
dejaron sin commitear en el árbol de trabajo, mismo criterio que la sección
"Mini-gráfico Koncorde por fila" — el próximo run programado los
sobrescribirá de todos modos en unas horas.

---

## Orden en tabla "Acciones individuales — candidatos por cluster" + fix de /api/state (2026-08-28)

### Orden por columna (`rotacion.html`, `StockCandidates`)

A petición del usuario, las 13 columnas de la tabla de candidatos individuales
(`⚡ Acciones individuales — candidatos por cluster`) se pueden ordenar
ascendente/descendente pulsando la cabecera — mismo mecanismo y misma
convención visual que ya usaba la tabla principal "Mapa de Rotación" (`Th()`
en el componente `App`): primer click en una columna nueva ordena con
`dir=-1` (etiquetado `▼` en este código, aunque produce orden ascendente —
convención ya existente, no se corrigió aquí, solo se replicó para no crear
una excepción visual en la misma pestaña), segundo click invierte a `▲`
descendente. Estado de orden (`scSortCol`/`scSortDir`) local a
`StockCandidates`, independiente del de la tabla principal — compartido entre
la tabla de candidatos activos y la de "ignorados" (mismo toggle).

`SC_COLS` ganó un campo `key` por columna, mapeado a un comparador genérico
(`scCompare`) que trata números/strings por separado y manda los valores sin
dato (`null`/`''`) siempre al final, en cualquier dirección. La columna
"Señal" ordena por un ranking propio de esta tabla
(`SC_SIGNAL_RANK = {CANDIDATO:3, EN_RADAR:2, VIGILAR:1, IGNORAR:0}`) — vocabulario
distinto del `SIGNAL_RANK` de la tabla ETF principal (COMPRA/ACUMULAR/...),
no reutilizable entre ambos.

**Verificado con Edge headless vía CDP contra el servidor local real:**
click en "Score" → 6→9 ascendente (`Score ▼`); segundo click → 9→6
descendente (`Score ▲`); click en "Ticker" → alfabético, resetea la flecha
de la columna anterior. Cero errores de consola nuevos.

### Fix real encontrado durante la verificación: `POST /api/state` devolvía 413 desde el 2026-08-20

Mientras se verificaba el cambio de arriba apareció en consola
`Failed to load resource: 413 (Payload Too Large)` para `POST /api/state`.
Diagnóstico: las 9 rutas `POST` de `server.js` usaban `express.json()` sin
`limit` — el límite por defecto de Express es **100 KB**. `state.json` (que
guarda `rotation_history`, `macro_score_history`, `relative_flow_history`,
`regime_coherence_history`, etc. — ver "Flujos & Rotación v2" y "Relative
Flow Lab v2" más arriba) llevaba tiempo por encima de eso: **169.8 KB**, con
fecha de modificación del **2026-08-20** — es decir, llevaba más de una
semana sin poder guardar ningún dato nuevo, en completo silencio: la página
sigue funcionando porque todo se recalcula en memoria en cada carga, así que
nadie lo habría notado mirando la UI. Mismo patrón exacto de fallo silencioso
ya vivido con `TELEGRAM_BOT_TOKEN` y `CAVA_ENGINE_TOKEN` (ver secciones
correspondientes) — aquí sin ningún secret de por medio, solo un límite de
body por defecto que el crecimiento normal de estos históricos acabó
superando.

**Fix:** las 9 llamadas a `express.json()` en `server.js` (`/api/signals`,
`/api/portfolio`, `/api/stock-config`, `/api/ux-instrumentation`,
`/api/state`, `/api/universe/add`, `/api/universe/remove`,
`/api/special-situations`, `/api/special-situations/delete`) pasan ahora
`{ limit: '5mb' }` — margen amplio y deliberado frente al ~170 KB actual de
`state.json`, para que este mismo fallo no se repita a corto plazo con
ninguno de los otros ficheros que estas rutas escriben (`portfolio.json` ya
en 46 KB y creciendo con Situaciones Especiales).

**Verificado:** `curl -X POST /api/state --data-binary @state.json` → antes
`413`, tras el fix `200`. Recarga real de `rotacion.html` en Edge headless
tras el fix: cero respuestas ≥400, cero errores de consola. `state.json`
pasó de 169.800 bytes (20-ago) a 177.068 bytes con timestamp del momento de
la verificación — confirma que el histórico volvió a persistir.

**Pendiente de verificar en el futuro:** cuánto histórico se perdió durante
la semana de silencio (2026-08-20 → 2026-08-28) — `rotation_history`/
`relative_flow_history`/etc. seguramente tienen un hueco de esas fechas; no
se ha intentado reconstruirlo (no hay snapshots intermedios de los que
recuperarlo, a diferencia de `ai_candidates.json` en el pipeline Python, que
sí se commitea a git en cada run).

---

## Relative Flow Lab — Fase 1: arquitectura de información (contexto sectorial antes de anticipación interna) (implementado 2026-08-28)

Propuesta de un asesor externo, revisada contra el código real antes de
implementar (mismo criterio que el resto del proyecto: no fiarse de un
resumen sin contrastar contra el registry). Diagnóstico correcto: en el RFL,
un ratio de detalle intra-sectorial (ej. `XLE/BZ=F`, "Anticipation") podía
leerse como "Leader" sin que el lector hubiera visto antes que el propio
sector pierde flujo agregado vs mercado (`XLE/SPY`, "Sector Relative
Snapshot", 4 secciones más abajo) — no es un problema de datos, es de orden
de lectura. Fase 1 (esta) resuelve el orden; Fase 2 (estados derivados +
interpretaciones condicionales) queda pendiente, deliberadamente no mezclada
en la misma sesión.

### 1. Reordenamiento de secciones (`relative.html`)

Nuevo orden: Risk Appetite Monitor → **Sector Relative Snapshot** (adelantada,
antes en posición ~6) → Early Flow Detector → Summary → Anticipation /
Internal Conviction → Rotation Between Blocks → Regions / EM Leadership →
Most Extreme Relative Moves / Top 3 Flow In-Out / Top 5 Flow Change →
Coherencia Cross-Módulos → Cluster Coherence View → Raw Ratio Tables.

Los 4 `QuestionBlock` (anticipation/rotation/regions/sector_snapshot) vivían
como un único bloque visual bajo una sola cabecera "📍 Question-Based Views"
+ una sola nota de bootstrap sobre Δ1W. Sacar `sector_snapshot` a una
posición temprana exigió separar ese bloque en dos: `sector_snapshot` solo
(sin la etiqueta "Question-Based Views", ya que su propio `QuestionBlock`
ya muestra su título) + los 3 restantes bajo la etiqueta original. La nota
de bootstrap se extrajo a un componente `BootstrapNote({bootstrap})` para no
duplicar la condición ahora que aparece en dos puntos. `RATIO_TYPE_ORDER`
(usado por `rowsByType`/`DEFS_BY_TYPE`) no se tocó — el reordenamiento es
puramente de JSX/render, no de la estructura de datos. El export a Markdown
(`buildRelativeMarkdown`) usa una constante local
`MARKDOWN_TYPE_ORDER = ["sector_snapshot", "anticipation", "rotation", "regions"]`
para el mismo efecto, e intercala la sección "Early Flow" justo después de
Sector Snapshot (antes vivía fija justo tras Risk Appetite).

### 2. `context_ratio_id` — Market Context column (`shared/relative-ratio-registry.js`, `relative.html`)

Campo opcional nuevo por ratio: id de OTRO ratio ya existente en el registry
cuyo estado se muestra como "Market Context" junto a este. Nunca se inventa
un ratio nuevo solo para servir de contexto — si no hay uno natural entre
los existentes, se deja sin asignar (ver `smh_igv` más abajo).

Asignados en Fase 1 — 5 de los 6 sugeridos por el asesor, tras verificar
contra el registry real:

```
xle_brent (XLE/BZ=F) → xle_spy   (Energy vs Market)
xop_xle   (XOP/XLE)  → xle_spy
kre_xlf   (KRE/XLF)  → xlf_spy   (Financials vs Market)
gdx_gld   (GDX/GLD)  → gld_spy   (Gold vs Market)
xlk_xlf   (XLK/XLF)  → xlf_spy
smh_igv   (SMH/IGV)  → (sin asignar, ver más abajo)
```

**Hallazgo real que corrigió 2 de las 6 sugerencias originales del
asesor:** `xlk_spy` (Technology vs Market) se reclasificó de
`sector_snapshot` a `type:"rotation"` el 2026-08-11 (ver sección "Relative
Flow Lab v2 — ratio_registry" más arriba) — hoy vive en la sección
"Rotation Between Blocks", la misma que `smh_igv`/`xlk_xlf`. Usarlo como su
`context_ratio_id` habría sido circular (el contexto no se leería antes,
sería fila hermana en la misma tabla — justo el problema que esta Fase 1
resuelve, reintroducido por la puerta de atrás). `xlk_xlf` usa `xlf_spy` en
su lugar (Financials es una de sus dos patas). `smh_igv` se queda sin
`context_ratio_id`: no hay hoy ningún ratio limpio "Technology vs Market"
en `sector_snapshot` (la alternativa que proponía el asesor, `XLC/SPY`, es
Comunicación — no encaja semánticamente con semis/software), y crear uno
nuevo está fuera de alcance de Fase 1.

Columna "Market Context" (formato `<pair>: <signal>, flow <flowChange>%`,
o `—` si no hay `context_ratio_id` o el contexto tiene error) añadida al
final de las tablas de **Anticipation, Rotation y Regions** — no en Sector
Relative Snapshot (que ya ES el contexto) ni en Risk Appetite (bloque
propio, no usa `QuestionBlock`). Resuelta vía `marketContextLabel(row,
rowById)`, reutilizando el `rowById` (lookup plano id→row) que ya existía
para la Coherencia Cross-Módulos — sin fetch ni cálculo nuevo.

### 3. `alsoShowIn` — visualización cruzada sin duplicar datos ni inflar agregados

El hueco de `smh_igv` reveló un problema de diseño más de fondo (según el
propio asesor): un ratio puede tener utilidad conceptual en varias
secciones (`xlk_spy` sirve tanto de "Rotation" como de contexto sectorial
de Tecnología), y el modelo de asignación única (`type`) no lo captura. El
asesor propuso esperar 2-3 semanas de uso real antes de decidir; el usuario
prefirió resolverlo ya, dado que el coste es bajo — decisión explícita del
usuario, no del asesor.

Implementado como campo opcional `alsoShowIn: string[]` en el registry
(hoy solo en `xlk_spy: alsoShowIn: ["sector_snapshot"]`) — **no** cambia el
`type` real del ratio (sigue siendo `rotation`, sigue contando una sola vez
en Risk Appetite Monitor, Cluster Coherence View, Most Extreme Relative
Moves, Raw Ratio Tables — ninguno de los cuales se tocó). Es puramente un
mecanismo de visualización: `rowsByTypeExtras[t]` (nuevo `useMemo` en
`relative.html`) filtra `ALL_RATIO_DEFS` por `alsoShowIn.includes(t)` y
`QuestionBlock` las añade a su tabla marcadas `crossListed:true` — badge
"↳ Rotación" junto al nombre en la UI, `[también en Rotation Between
Blocks]` en el Markdown. Las filas cruzadas quedan **excluidas** del
mini-ranking "Top Signals" de cada bloque (no son miembros nativos de esa
pregunta) y no tienen `dyn` (Δ1W/Sem./badge) calculado — solo Score/Flow
Chg de referencia, no seguimiento histórico duplicado.

**Deliberadamente NO se generalizó** a "un ratio puede pertenecer a varias
secciones" como modelo formal — es un mecanismo aditivo acotado a este único
caso, siguiendo el propio consejo del asesor de no construir el refactor
general hasta ver 3-4 huecos similares.

### Verificado end-to-end (Edge headless vía CDP, servidor local real)

Sintaxis JSX transpila sin errores (`@babel/core` + `preset-react` en Node).
Orden de secciones confirmado en la UI real y en el Markdown exportado
(`Copy for LLM`, clic real interceptando `navigator.clipboard.writeText`):
idéntico en ambos, Sector Relative Snapshot antes de Early Flow y de
Anticipation. Los 5 `context_ratio_id` verificados con datos reales del
momento (ej. `XLE/BZ=F` → `XLE/SPY: Improving, flow -6.2%`; `SMH/IGV` →
`—`), coincidentes byte a byte entre la tabla UI y el export Markdown (misma
función `marketContextLabel` en ambos). `xlk_spy` confirmado apareciendo dos
veces en el HTML (Sector Snapshot con badge cruzado + Rotation nativo, sin
`context_ratio_id` propio) sin inflar ningún agregado: "Ratios cargados"
del summary se mantuvo en `50/50` (no 51) tras el cambio. Cero errores de
consola en ambas pasadas.

### Fuera de alcance (Fase 2, explícito, no abordado en esta sesión)

Estados derivados (`state_detail`, `context_state`, `context_confirmation`),
interpretaciones textuales condicionales (~200 frases sobre los 45 ratios),
Theme Context Cards. No se toca PCS, rot_score, AI Picks, carteras, ni
reglas de entrada/salida — mismo alcance acordado desde el inicio.

---

## Fix: la vela semanal de Koncorde se recalculaba a diario sobre semanas incompletas (implementado 2026-08-30)

Origen: revisando por qué PLTR mostraba `konc_d_state=distribution` sostenido
desde el 22-jul mientras `konc_w_state=up` desde finales de junio (caso real,
resultó ser ruido del diario, no una divergencia problemática — ver el hilo
de esa fecha), salió a la luz un problema de fondo distinto y más serio en
`_resample_weekly()` (`scripts/koncorde_calculator.py`): a diferencia de
`_resample_3d()` (que ya descarta correctamente el bloque de 3 sesiones en
curso si está incompleto), el resample semanal (`df.resample("W-FRI")`) no
excluía la semana en curso — emitía un bin para ella usando solo las sesiones
acumuladas hasta ese día, etiquetado con la fecha del viernes que todavía no
había llegado.

**Verificado contra los commits reales del pipeline** (semana 24-28 ago,
PLTR): `konc_w_blue` cambiaba cada día dentro de la misma semana —
10.70 (viernes anterior, cerrado) → 5.23 (martes, 2 sesiones) → 1.96
(miércoles, 3 sesiones) → 6.88 (jueves, 4) → 15.41 (viernes, semana completa)
— es decir, el campo que el resto del sistema trata como "la lectura
estable, de confirmación" (`konc_alignment`, alertas `/kalert TICKER w ...`,
Situaciones Especiales, la guía del prompt IA "weight 3D and W more heavily")
podía en realidad ser una vela de 2 sesiones a mitad de semana — más
ruidosa que el propio diario en ese momento, tratada con la confianza
contraria.

**Fix — `_resample_weekly()` ahora replica la disciplina que ya tenía
`_resample_3d()`:** tras el resample, si la última sesión diaria disponible
no es en sí misma un viernes (`idx[-1].weekday() != 4`), se descarta el
último bin (la semana en curso) y se devuelve la última semana ya cerrada.
Con esto `konc_w_state`/`konc_w_blue`/etc. pasan a actualizarse una vez por
semana (al cierre del viernes), no una vez por día — igual que su nombre
promete. `konc_w_bar_closed` (ya existía, hardcodeado a `True` con el
comentario "flip to false if run intraday on a partial bar") pasa a ser
honesto sin necesitar lógica nueva: con el fix, nunca se le da a `_compute_tf`
un DataFrame semanal cuya última fila sea parcial.

**Caso borde deliberadamente aceptado, no arreglado:** una semana que cierra
en jueves por festivo (el viernes no tiene sesión) se retrasa un poco — su
bin no se emite como "última" hasta que la semana siguiente cierre en un
viernes real, momento en el que dejará de ser la última fila y se mostrará
con normalidad. No se pierde el dato, solo se demora unos días en el caso
raro de una semana acortada por festivo — mismo criterio de "simple y
conservador" ya aceptado en `_resample_3d()` (que tampoco tiene en cuenta
el calendario de festivos, solo cuenta múltiplos de 3 sesiones).

**Verificado:** 3 casos sintéticos (semana parcial sola → vacío; semana
completa + parcial siguiente → solo la completa; dos semanas completas
terminando en viernes → ambas) + verificación end-to-end contra datos reales
de PLTR (yfinance): recalcular en miércoles 26-ago da exactamente el mismo
resultado (`bar_date=2026-08-21, blue=10.68`) que recalcular el viernes
anterior 21-ago, y el viernes 28-ago sí rueda a la semana nueva
(`blue=15.74`, consistente con el 15.41/15.77 ya visto en producción antes
del fix). `py_compile` limpio.

**Efecto colateral esperado, no verificado en producción todavía:** el
payload IA, `konc_alignment`, las alertas Koncorde ya creadas (`/kalert
IRS w ...`, `/kalert GGAL w ...`) y Situaciones Especiales pasan a leer una
`W` más lenta pero más fiable — el próximo cierre de viernes real será la
primera confirmación en producción del comportamiento nuevo. No se tocó
`_resample_3d()` (ya tenía este cuidado) ni ningún otro consumidor de
`konc_w_*` — el fix vive enteramente en la función de resample.

**Deliberadamente fuera de alcance:** un campo "W en vivo" (semana en
curso, parcial, para quien quiera adelantarse) — no pedido, mismo criterio
de "no añadir complejidad antes de que haya un caso de uso real" que el
resto de features en fase de observación del proyecto. Si hace falta más
adelante, sería un campo nuevo y explícitamente etiquetado, sin volver a
mezclarlo con `konc_w_state`.

---

## CoT Positioning — escala y selector de rango en los sparklines (implementado 2026-08-30)

A petición del usuario: los sparklines de `positioning.html` (Oro/Plata/Cobre/
WTI, posicionamiento neto de Managed Money) no mostraban escala numérica y
siempre pintaban todo el historial disponible sin poder elegir ventana.

**`server.js` — `COT_HISTORY_WEEKS` 170 → 270 (~5.2 años).** El límite
anterior (~3.3 años) era un tope autoimpuesto sin relación con lo que la API
de CFTC realmente tiene — verificado en vivo antes de tocar el código: Oro y
Plata llegan hasta 2006 bajo el mismo nombre de mercado que ya usa el
sistema, así que ampliar el límite les da más historial real, no inventado.
Cobre y WTI sí tienen un techo real: su nombre de mercado actual en el
dataset solo existe desde 2022-02-08 (mismo rename ya documentado para WTI en
la sección de creación de este módulo) — con el límite nuevo la API
simplemente devuelve todo lo que hay (238 filas, confirmado en vivo) sin
error, así que el rango "5A" del selector para esos dos contratos muestra en
la práctica ~4.5 años, no 5. El percentil (`percentile`, `n_weeks`) sigue
calculándose sobre **todo** el historial que llega del servidor — al crecer
la ventana de fetch, la ventana del percentil crece con ella (Oro pasó de
calcularse sobre ~170 semanas a 270; percentil real verificado tras el
cambio: 80 de 270 semanas). Es el mismo diseño de siempre ("percentil sobre
la ventana disponible"), solo que la ventana disponible ahora es mayor.

**`positioning.html`:**
- `Spark()` gana `showScale` (activado por defecto): máx/mín numéricos
  (arriba/abajo del gráfico) + rango de fechas mostrado + una etiqueta "0"
  posicionada sobre la línea de cero cuando la serie cruza de signo (ya
  existía la línea punteada, le faltaba el número).
- Selector de rango nuevo (`SPARK_RANGES`: 3M/6M/1A/3A/5A), un único control
  a nivel de página que filtra `history` por fecha antes de pasarlo a los 4
  sparklines a la vez — no per-tarjeta, es "cambiar la vista", no cuatro
  controles independientes. **Filtra solo lo que se dibuja** — el percentil
  y el resto de la tarjeta (neto, largos/cortos, cambio 1 semana) no
  cambian con el selector, están anclados a la última lectura real,
  aclarado explícitamente en el `section-sub` para que no se lea como que
  el percentil también se recalcula por rango.
- Rango por defecto: `5y` — el más parecido al comportamiento previo
  (mostrar todo lo disponible), ahora con un techo explícito en vez de "todo
  lo que llegue".

**Verificado en producción real** (Edge headless vía CDP directo, cliente
CDP raro este caso: sin Playwright ni puppeteer-core instalados en el
proyecto, así que se usó el `WebSocket` nativo de Node 24 hablando el
protocolo CDP a pelo, contra un `server.js` temporal en el puerto 3098,
terminado y borrado al acabar): `/api/cot/gold` real devuelve 270 semanas
(antes 170), oldest=2021-06-29 (antes ~2023); `/api/cot/wti` devuelve 238
(el máximo real, sin error). En la UI: los 5 botones de rango presentes,
"5A" activo por defecto, tarjeta de Oro muestra escala real (máx 219.029,
mín -43.094, rango de fechas 2021-08-31→2026-08-25, percentil "80 de 270
semanas"); clic real en "3M" actualiza la escala (máx/mín/fechas se
recalculan sobre la ventana de 3 meses) sin tocar el percentil ("80 de 270
semanas" idéntico antes y después). Cero errores de consola nuevos (solo el
aviso preexistente de Babel en desarrollo, presente en todas las páginas del
proyecto).

**Fuera de alcance:** ningún cambio en la tabla completa de abajo (no lleva
sparkline); ningún cambio en el export a Markdown/LLM (no incluye series
históricas, solo el snapshot actual — el selector de rango es puramente
visual).

---

## Cartera CRUCE_ROJO_D — 100% mecánica, sin IA en ningún punto (implementado 2026-08-30)

Origen: el usuario propuso una idea de cartera nueva ("línea negra por debajo
de 0, cruza al alza a la línea roja → entra; cruza a la baja → sale") sobre
Koncorde diario. Antes de implementar nada se validó con un backtest
retroactivo sobre el universo Koncorde completo (198-202 tickers,
2022-06→2026-08-30, `research/koncorde_cross_backtest_2026-08/`) — mismo
criterio que Mirror Espejo/Cava en su día: no operar una idea nueva sin
evidencia primero.

**Aclaración de terminología, verificada con datos reales antes de construir
nada:** "línea negra" = `konc_d_trend` (la composición cruda RSI+MFI+BB+Stoch,
que este proyecto ya venía llamando internamente "marrón/ocre" en el
mini-gráfico de `portfolio.html`), "línea roja" = `konc_d_trend_ma` (EMA-15 de
esa composición, ya calculada y guardada desde el fix del 2026-08-14). La
condición literal "por debajo de 0" resultó casi inexistente en la práctica:
esa serie es casi siempre positiva por construcción (3 de sus 4 componentes,
RSI/MFI/Stoch, son ≥0) — verificado: solo el 2,3% de las lecturas del universo
completo están por debajo de cero, dando apenas 12-13 señales en 4+ años sobre
198-202 tickers. Se sustituyó por dos condiciones combinadas, elegidas tras
comparar varias alternativas en el backtest: **percentil propio del marrón
≤10 sobre su ventana móvil de 252 sesiones** (sobreventa relativa al propio
histórico del valor, no un nivel absoluto) **Y RSI(14) < 30**. Esta
combinación fue la de mejor perfil de las probadas: 38 señales/4 años, media
+5,39%, peor caso solo -8,7% (frente a -54%/-99% de la versión sin filtro o
con un solo filtro suelto).

**Hallazgo de calidad de datos durante el backtest, no relacionado con la
señal en sí:** dos tickers `.L` (LSE) mostraron saltos de precio de exactamente
100x — el mismo error GBX/GBP (peniques vs libras) que Yahoo comete
ocasionalmente. `MAI.L` fue un glitch transitorio de 3 sesiones (corregido,
reescalado). `FXPO.L` mostró el mismo salto pero **persistente desde
2026-05-18, sin revertir** — no se corrigió a ciegas, se excluyó del universo
del backtest. Sin esta limpieza, el "peor caso" de varias condiciones salía en
-99%, puro artefacto de datos.

### Por qué esta cartera no necesita IA (a diferencia de Mirror Espejo)

Mirror Espejo sí llama a Grok porque su señal base (blue cruzando de negativo
a positivo) es más laxa y necesita que alguien juzgue "si el giro parece
creíble". Aquí el doble filtro (percentil bajo + RSI bajo) ya hace ese trabajo
de forma determinista — entrada y salida son ambas una comparación numérica
sin ambigüedad que resolver. Es la primera cartera del sistema sin ningún
modelo en ningún punto de la decisión (Cava tampoco usa IA para elegir ticker,
pero sí decide la postura macro; Mirror Espejo sí llama a Grok para la
entrada).

**Decisiones tomadas con el usuario antes de implementar** (cada una cambia
el comportamiento real de la cartera):
- Umbral estricto (percentil≤10 + RSI<30), no el más laxo (percentil≤25) —
  prioriza calidad/peor-caso sobre frecuencia. La cartera pasará la mayor
  parte del tiempo con pocas posiciones o vacía (~9-10 señales/año sobre todo
  el universo).
- 5% fijo, sin límite de posiciones — mismo patrón que MIRROR_ESPEJO.
- **Sin cortacircuito de precio** (a diferencia de MIRROR_ESPEJO 5% / CAVA_MACRO
  25%) — decisión explícita del usuario, fiel a la regla tal como la describió:
  la única salida es el cruce a la baja del marrón sobre la roja.
- Universo Koncorde completo (~198-202 tickers), no solo los 91-128 candidatos
  PCS — coherente con que esta cartera no usa PCS para nada.

### Campos nuevos en Koncorde (`scripts/koncorde_calculator.py`)

`_compute_tf()` ahora también devuelve los arrays completos de `trend`/
`trend_ma` (antes solo `blue`, para `_compute_research_fields()`) — cambio de
firma de 2-tupla a 4-tupla, actualizado en los 3 sitios donde se llama
(D/3D/W). Nueva función `_compute_cross_signal_fields()` (deliberadamente
separada de `_compute_research_fields()`, que está documentada como "no
gated en ninguna señal" — estos campos sí alimentan una decisión operativa
real):

- `konc_d_rsi14` — RSI(14) de Wilder sobre `close` (reutiliza `_rsi()`, ya
  existente, solo alimentada con `close` en vez de `ohlc4`).
- `konc_d_trend_pctile252` — percentil (0-100) del `trend` de hoy dentro de su
  propia ventana móvil de 252 sesiones.
- `konc_d_trend_cross` — `"up"`/`"down"`/`"none"`, nueva función genérica
  `_cross_series(a, b)` (generaliza `_cross_up()`, que solo compara una serie
  contra el nivel fijo 0, a dos series cruzándose entre sí).

Verificado exacto contra un caso real conocido (BBAR, 2025-09-17→18): cruce
"up" con rsi14=23.1/pctile252=9.2 el día de entrada del backtest, cruce
"down" al día siguiente — coincide con el propio backtest que motivó la
cartera.

### `scripts/cruce_rojo_d_portfolio.py` (nuevo, Step 9c3 del pipeline)

Mismo patrón que `mirror_portfolio.py` (`fetch_last_closes`, persistencia en
`ai_picks.json`, `"event": "close"` desde el primer commit — para no repetir
el bug ya visto dos veces con CAVA_MACRO/MIRROR_ESPEJO) pero sin ninguna
llamada a modelo. Corre en **ambos** pases del pipeline (no solo por la
mañana, a diferencia de Mirror Espejo/Insider Activity) — coste mínimo, sin
llamada a OpenRouter. `py -3 scripts/cruce_rojo_d_portfolio.py` (dry-run) /
`--apply` (aplica de verdad). Log ligero en
`docs/data/cruce_rojo_d_log.jsonl`.

**Registro en dashboard/Telegram** (checklist de
`wiki/PREREGISTRO_RANKING_SCORE_V0.md`, para no repetir el bug de
CAVA_MACRO/MIRROR_ESPEJO invisibles): añadida a `PTF_LABELS`
(`docs/index.html`, "Cruce Rojo D") — deliberadamente **fuera** de
`GROK_PTFS`/`MIMO_PTFS` del mini-panel de overview, porque no tiene modelo y
ninguna de las dos etiquetas la describiría bien; sigue teniendo su propia
pestaña completa. Añadida a `_PORTFOLIO_LABELS` en `paper_trading.py` y
`notify_telegram.py`.

**Hallazgo colateral durante este registro:** `CAVA_MACRO` nunca se había
añadido a `_PORTFOLIO_LABELS` en ninguno de los dos scripts (sí se arregló en
`docs/index.html` el 2026-08-03, pero no ahí) — sus avisos de Telegram
llevaban mostrando el nombre crudo `"CAVA_MACRO"` en vez de una etiqueta
legible. Corregido de paso, no bloqueante pero real.

**Verificado end-to-end:** pipeline real corrido en local
(`koncorde_calculator.py` completo, 203/205 tickers, campos nuevos poblados y
verificados exactos contra PLTR); test aislado con datos sintéticos (ticker
que califica entra con todos los campos `_at_entry`, ticker en cartera con
cruce a la baja se cierra con `event=close`, ticker con cruce alcista pero
sin sobreventa no entra) — las 4 aserciones pasaron; `--apply` real contra
`ai_picks.json` de producción registró la cartera (vacía, 0 candidatos reales
hoy — la propia rareza del umbral estricto, consistente con lo esperado);
dashboard verificado con Edge headless vía CDP contra el servidor local real
— pestaña "Cruce Rojo D" visible en AI Picks Lab, navegable, muestra "0
posiciones abiertas" correctamente, cero errores de consola nuevos.

**Nota de infraestructura descubierta durante la verificación:** `server.js`
sirve estáticos desde la raíz del repo (`express.static(__dirname)`), y hay
**dos** `index.html` distintos — uno en la raíz (56KB, sin relación con AI
Picks Lab) y `docs/index.html` (el dashboard real, 90KB) — así que
`localhost:3000/index.html` sirve el equivocado; hay que pedir
`localhost:3000/docs/index.html` explícitamente. No es un bug, ya era así
antes de este cambio, pero no estaba anotado en ningún sitio y costó una
verificación fallida descubrirlo.

**Fuera de alcance (explícito):** confirmación 3D/semanal (el backtest y la
cartera son deliberadamente solo-D, de ahí el nombre); cortacircuito de
precio; ampliar a otros timeframes. Si el umbral estricto resulta demasiado
restrictivo con datos reales, replantear con el usuario antes de tocar los
números — no ajustar umbrales unilateralmente sobre la marcha.

### CRUCE_ROJO_D_25 — segunda variante, misma familia (implementado 2026-08-30)

El usuario pidió una segunda cartera idéntica pero con el umbral laxo del
mismo backtest (percentil≤25 en vez de ≤10 — la otra fila de la tabla de
`research/koncorde_cross_backtest_2026-08/README.md`: 134 señales/4 años,
media +3.70%, peor caso -11.9%, frente a 38 señales/+5.39%/-8.7% de la
estricta). RSI<30, 5% fijo, sin límite de posiciones y misma salida (cruce a
la baja) — todo igual, solo cambia el umbral de entrada.

**Refactor de `scripts/cruce_rojo_d_portfolio.py` a multi-config en vez de
duplicar el archivo** — decisión directamente derivada de la conversación de
esa misma tarde sobre reutilización del motor de ejecución (ver "Hoja de
ruta consolidada" más abajo): en vez de copiar ~250 líneas a un segundo
script (el mismo patrón de duplicación ya visto y corregido varias veces en
este proyecto — `calcCMF`, `HARD_RULES` antes de `ai_shared.py`), el script
pasó a tener una lista `CONFIGS` (`CRUCE_ROJO_D` percentil≤10,
`CRUCE_ROJO_D_25` percentil≤25) y funciones parametrizadas
(`qualifies_for_entry(k, config)`, `check_exits(..., config)`,
`run_for_config(...)`) — un solo pase lee `koncorde_data.json` una vez y
evalúa ambas variantes, cada una con su propio slot en `ai_picks.json` y su
propia fila en el log compartido `docs/data/cruce_rojo_d_log.jsonl` (ahora
con campo `"portfolio"` para distinguirlas).

**Bug real encontrado en la propia verificación:** el primer refactor solo
escribía `ai_picks.json` si `any(n_added or n_closed)` en cualquiera de las
dos — regresión respecto al comportamiento original ("persistir siempre que
`--apply` esté activo, aunque no haya cambios hoy, para que la cartera
aparezca en el dashboard desde el primer run incluso vacía"). Con eso,
`CRUCE_ROJO_D_25` no se registraba en absoluto el día de su creación (0
candidatos, 0 cierres). Corregido: se escribe siempre que `apply=True`,
igual que antes del refactor.

Registrada en dashboard (`docs/index.html` PTF_LABELS, fuera de
GROK_PTFS/MIMO_PTFS y de PTF_THRESHOLDS, mismo motivo que `CRUCE_ROJO_D` —
no tiene modelo ni usa PCS) y Telegram (`_PORTFOLIO_LABELS` en
`paper_trading.py` y `notify_telegram.py`) desde el primer commit — sin
repetir el hueco de `CAVA_MACRO` que se encontró al registrar la primera
variante. `scripts/ai_picks_decision_state.py` (P0) también actualizado:
`ALL_LIVE_PORTFOLIOS` y las ramas de `compute_mechanical_exit()`/lookup de
`model` cubren ahora las dos variantes con la misma lógica (`portfolio in
("CRUCE_ROJO_D", "CRUCE_ROJO_D_25")`).

**Verificado:** test aislado con datos sintéticos — un ticker que solo
califica para la variante laxa (percentil 20, entre 10 y 25), otro que
califica para ambas, y una posición abierta solo en la estricta que cruza a
la baja — confirma que las dos carteras no se contaminan entre sí (la
laxa tiene ambos candidatos, la estricta solo el que de verdad cumple ≤10,
el cierre solo afecta a la estricta). `--apply` real contra producción:
ambas carteras registradas (vacías, 0 candidatos reales el día de creación —
ningún ticker con cruce alcista hoy tiene RSI<30, confirmado manualmente).
Dashboard verificado con Edge headless — pestaña "Cruce Rojo D 25" presente
y navegable, cero errores de consola.

**Nota de naming:** el nombre interno de cartera (`CRUCE_ROJO_D_25`) sigue
la convención `SCREAMING_SNAKE_CASE` del resto de claves de
`ai_picks.json.portfolios`; la etiqueta visible es "Cruce Rojo D 25", tal
como la pidió el usuario.

---

## Hoja de ruta consolidada — Auditoría de carteras IA (firmada 2026-08-30) — P0 arrancado

El usuario trajo una hoja de ruta consolidada (v1.2, "FINAL — arquitectura
congelada") de tres rondas de revisión externa sobre
`wiki/ASESOR_EXTERNO_AUDITORIA_CARTERAS_IA.md` — no está commiteada en el
repo (documento externo, se referencia aquí por lo que activa, no se
reproduce). Estructura: P0 (persistencia diaria, fundación) → Rama A
(P1A/P1C/P2/P3, ejecución/salidas) + Rama B (P1B/P4/P5/P6, selección/
timing) → P7 (datos nuevos, bloqueado hasta que las ramas anteriores den
lectura). Discutido con el usuario antes de empezar: **Rama A reduce el
"giveback" de la salida mecánica pero no genera alfa por sí sola** — el
alfa real, si existe, sale de P1B (H7: sobreextensión de 5 sesiones en la
entrada) y P4 (Ranking Score componentes C-F), con P7 como el pago gordo si
ambas concluyen "problema de señales". Objeción propia planteada al
usuario, no bloqueante: los umbrales de promoción de P1A/P1C (n≥40
operaciones/≥30 eventos) están por debajo del criterio que este mismo
proyecto ya se exigió en otras rondas (~100-150 eventos, 2+ regímenes) —
queda como pregunta a los asesores, no como condición para firmar.

**Decisión de arquitectura acordada, aplicable más allá de este programa:**
P1A/P1C (motor de riesgo — trailing/ATR stops, no leen PCS ni Koncorde, solo
precio/ATR) se construirán desde el principio como módulo compartido
(`scripts/risk_engine.py`, pendiente), no acoplados a una cartera — para
que el día que se gestione algo con criterios de selección completamente
distintos, el motor de riesgo ya esté separado y validado. Cuando llegue
P1A, migrar también la lógica ya duplicada de `mirror_portfolio.py`
(trailing 5%) y `cava_portfolio.py` (cortacircuito 25%) al mismo módulo en
vez de mantener tres copias — mismo patrón que motivó centralizar
`HARD_RULES` en `ai_shared.py`.

### P0 — `scripts/ai_picks_decision_state.py` (implementado 2026-08-30, Step 10i)

Fundación de la que dependen todos los experimentos — sin captura diaria no
hay muestra que analizar. Distinto de `portfolio_daily_snapshot.js`
(captura Portfolio Tracker/`portfolio.json`, un sistema aparte) — este es
específico del AI Picks Lab (`ai_picks.json`, las 8 carteras con posiciones:
HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS, EARLY_ROTATION,
MACRO_THEMATIC_BENEFICIARIES, MIMO_SHADOW, CAVA_MACRO, MIRROR_ESPEJO,
CRUCE_ROJO_D — REJECTED_HIGH_SCORE excluida, nunca tiene posiciones).

**Mínimo viable v1** (no la versión "deseable" completa del documento — que
él mismo avisa de no convertir en proyecto): una fila por (posición, día) en
`docs/data/ai_picks_decision_state.jsonl`, dedup por posición+fecha. Corre
al final del pipeline (Step 10i, tras Step 10/paper_trading y Step
10d/Cava — Mirror y Cruce Rojo D ya corrieron antes, en 9d/9c3) para que el
SELECT de hoy quede capturado en su propia fila de entrada sin necesitar un
hook por cartera.

**`T_active` (definición formal del suelo, §6 de la hoja de ruta):**
`max(62, pcs_min_entry si streak_weeks≤1)` — implementado en
`compute_t_active()`, solo aplica a las 5 carteras PCS-gated
(`PCS_GATED_PORTFOLIOS`); MIRROR_ESPEJO/CAVA_MACRO/CRUCE_ROJO_D no usan PCS,
quedan `None` con `trigger_threshold_source="not_pcs_gated"` documentado —
nunca un valor inventado.

**`mechanical_exit_trigger`/`exit_rule_id` — réplica en Python puro, no
importación.** La regla 13 real (`ai_shared.py`) vive repartida entre
`paper_trading.py`/`cava_portfolio.py`/`mirror_portfolio.py` sin factorizar
en funciones puras reusables — `compute_mechanical_exit()` la reimplementa.
**Riesgo de drift conocido y documentado en el propio código a propósito**:
es exactamente lo que el test de concordancia de P3 (§7 de la hoja de ruta)
va a validar o desmentir cuando corra. No se ha intentado extraer la lógica
real a una función compartida en este cambio — haría el cambio mucho más
grande y P3 es precisamente el mecanismo que decidiría si merece la pena.

**Campos aproximados, documentados, no inventados:**
- `fromHigh52w` — sobre la ventana descargada (~4 meses, `period="4mo"` de
  yfinance), no 252 sesiones reales. Se documenta la limitación en vez de
  fingir un 52 semanas con menos datos; corregible más adelante ampliando
  la descarga si hace falta.
- `RS` (relative strength) — proxy con `ret_4w_vs_spy` de
  `ai_candidates.json`, el campo más parecido a "fuerza relativa" que ya
  existe en el pipeline. No se ha inventado un cálculo nuevo.
- `prompt_version`/`scoring_version`/`data_version` — constantes fijas
  `"v1"`, no un sistema de versionado real (no existe todavía).
- `PCS_delta_1d/3d/5d` — se calculan leyendo hacia atrás el propio
  `ai_picks_decision_state.jsonl` (fila más cercana a N días atrás para la
  misma `position_id`), no reconstrucción vía git-history — más simple,
  correcto desde el día en que hay suficiente histórico propio acumulado
  (los primeros ~5 días de vida de P0 tendrán estos campos a `null`, es
  esperado, no un fallo).

**Verificado con datos reales:** primer run real (`--apply` implícito, sin
flag) capturó 33 filas (31 posiciones distintas — 2 duplicadas entre
MIMO_SHADOW y otra cartera, mismo evento de mercado, correcto) en 5 de las
8 carteras vivas (las otras 3 —EARLY_ROTATION, MACRO_THEMATIC_BENEFICIARIES,
CRUCE_ROJO_D— sin posiciones abiertas hoy). 33/33 con
`mechanical_exit_trigger` evaluable. Segunda ejecución inmediata: 0 filas
nuevas (dedup confirmado). Bug real encontrado y corregido en la propia
verificación: los componentes A-F se leían mal (`pcs_components` usa claves
largas, `"A_macro_permission"` no `"A"` — corregido para leer directamente
los campos planos `component_A`.._F` que ya existen en `ai_candidates.json`
desde la Fase 0.2 del Ranking Score). `entry_price=None` (caso real,
VIT-B.ST en CAVA_MACRO, entrada de ayer sin precio todavía) manejado sin
crashear — MFE/MAE/running_high/running_low quedan `null` correctamente en
vez de reventar.

**Pendiente, explícitamente no bloqueante para P0:** los "deseable v1.1"
(flowScore/earlyFlow/MACD/Koncorde D/3D/W por posición) — no implementados
todavía, el nivel obligatorio ya es capturable y es lo que bloquea el resto
del programa. `risk_engine.py` compartido — pendiente de P1A, no de P0.

### Monitor de umbrales — `scripts/p1_readiness_monitor.py` (implementado 2026-08-30, Step 10j)

El usuario pidió aviso por Telegram para cuando toque continuar con P1, en
vez de tener que comprobarlo a mano. Cuenta episodios/eventos acumulados
desde la fecha de firma (`FIRMA_DATE = "2026-08-30"`, el día que arrancó P0
— todo "post-firma" de los preregistros se cuenta desde aquí, no desde el
arranque del sistema en mayo) y avisa **una sola vez por umbral** (dedup vía
`docs/data/p1_readiness_state.json`, mismo patrón que `duration_monitor.py`):

- **P2** — ≥14 días desde la firma (gate simple de calendario, §6).
- **P1A/P1C** — ≥40 cierres nuevos Y ≥30 eventos independientes
  (`event_id=ticker+entry_date`) en el ámbito exacto de §3: HIGH_CONVICTION,
  CONFIRMED_FLOW_LEADERS, EARLY_ROTATION, MACRO_THEMATIC_BENEFICIARIES,
  CAVA_MACRO — MIRROR_ESPEJO excluida a propósito, tal como especifica la
  hoja de ruta.
- **P1B** — ≥60 eventos de SELECT independientes, sin restricción de
  cartera (contando posiciones abiertas y cerradas — un cierre no borra el
  evento de haber entrado).
- **Cláusula de potencia calendario (§3/§6)** — si a los 90 días de la firma
  P1A/P1C todavía no alcanzó su umbral, avisa igual, pero con el mensaje
  correcto: publicar informe intermedio y alargar el plazo, **nunca** tocar
  parámetros ni mirar resultados por brazo.

No decide ni ejecuta nada — solo cuenta y avisa. La decisión de arrancar
cada experimento sigue siendo manual. Reutiliza `send_telegram()` de
`notify_telegram.py` en vez de reimplementar el envío.

**Verificado:** sanity check contra el histórico real completo
(`FIRMA_DATE` forzado a `2026-05-01` en una prueba aislada, sin tocar el
estado real) dio 57 cierres en el ámbito P1A/P1C — coincide exacto con la
suma manual de la auditoría del día anterior (HC 8 + CFL 26 + ER 6 + MTB 2 +
Cava 15 = 57), confirmando que la lógica de conteo es correcta contra datos
reales, no solo sintéticos. Los 4 mensajes (P2, P1A/P1C listos, P1B listo,
checkpoint 90 días sin cumplir) probados con datos sintéticos — texto y
umbrales correctos. Envío real de confirmación disparado a producción
("Monitor P1 activo") sin tocar el `p1_readiness_state.json` real, para no
silenciar las alertas de verdad cuando toquen. Mismo bug de emoji/consola
Windows ya documentado en `duration_monitor.py`/`check_koncorde_alerts.py`
encontrado y arreglado aquí también (mismo fix, `reconfigure` a UTF-8).

---

## Situaciones Especiales — condición de precio (implementado 2026-08-30)

Origen: el usuario intentó crear por nota de voz en Telegram *"avisar si TNZ
supera 70 y en vela diaria azul positivo"*. Falló porque el vocabulario
cerrado de `koncorde_alert_conditions.py` (7 condiciones Koncorde, más
`flow`/`ratio` desde "Situaciones Especiales") no tenía ningún tipo de
condición de precio — ni siquiera el sistema compuesto la soportaba. Se le
ofreció como alternativa dos alertas independientes; el usuario la rechazó
explícitamente: *"no, quiero que la alerta pueda contemplar que se cumplan
las dos condiciones a la vez"*. Cuarto tipo de condición del sistema
(`koncorde`/`flow`/`ratio`/**`price`**), mismo patrón AND de
`evaluate_conditions()` (three-valued True/False/None, False gana sobre
None) — sin tocar nada de lo ya existente.

**`scripts/price_signal.py` (nuevo)** — mismo espíritu que `ratio_signal.py`
(módulo pequeño, dedicado, fetch en vivo bajo demanda, sin registro):
`fetch_current_price(ticker)` descarga los últimos 5 días vía yfinance y
devuelve el último close disponible, o `None` si falla — nunca falso
positivo/negativo por dato ausente, mismo principio que el resto del sistema.

**`scripts/koncorde_alert_conditions.py`** — `PRICE_OPS = {"above", "below"}`,
`evaluate_price(current_price, op, threshold)` (devuelve `None` si
`current_price` es `None`, nunca `False`), enganchado en
`evaluate_single_condition()` (`ctype == "price"` → lee `ctx["current_price"]`)
y en `describe_conditions()` (`"Precio por encima/debajo de N"`).

**`scripts/check_koncorde_alerts.py`** — fetch de precio gateado igual que
`needs_flow`/ratio: solo se llama a `price_signal.fetch_current_price()` si
la alerta en cuestión tiene alguna condición `price`, con caché en memoria
por ticker (`price_cache`) para no repetir la descarga si varias alertas
comparten ticker.

**`portfolio.html` (`SpecialSituationModal` + evaluador cliente)** — nuevo
checkbox "Precio" en el modal; al marcarlo aparecen un select
(`PRICE_OP_OPTIONS`: por encima de / por debajo de) y un input numérico de
umbral. `handleSave()` valida el umbral (`parseFloat`, rechaza vacío/no
numérico) antes de añadir `{type:'price', op, threshold}` al array de
`conditions`. Evaluador cliente `checkPriceCond(p, op, threshold)` — réplica
en JS del evaluador Python, reutilizando `p.price` (el mismo precio ya
cargado para la tabla principal "Cartera" vía `/api/quote/:symbol`, sin
ningún fetch adicional) — enganchado en `evaluateSituationConditions()` y en
el segundo punto de despacho (render de badges por condición en la tabla de
situaciones), con descripción `"Precio > N"` / `"Precio < N"`.

**Verificado end-to-end** (Edge headless vía CDP directo, servidor local
real): backend — 3 casos sintéticos con `evaluate_conditions()` (precio+konc
ambos true → dispara; precio falla → False gana; precio ausente/fetch
fallido → pending, nunca True/False) más un test real contra
`check_koncorde_alerts.py` con `price_signal.fetch_current_price("TNZ.TO")`
en vivo (precio real ~64.64, condición `above 70` correctamente no disparada,
condición `below 1000` sí, auto-borrado one-shot confirmado, la alerta no
disparada permanece intacta en el fichero). Frontend — sintaxis JSX
transpila sin errores; flujo real de UI (clic en checkbox, relleno de select
+ input numérico vía setters nativos de React, clic en "Crear situación")
confirmado con el `POST /api/special-situations` real capturado por
Network — `conditions` incluye `{"type":"price","op":"above","threshold":70}`
con `threshold` como número, no string; la fila de la tabla renderiza
`"Precio > 70"` junto al resto de condiciones con badge "pendiente"
(ticker de prueba sin datos reales, correcto). Cero errores de consola.
Situación de prueba (`TESTPX`) creada y eliminada tras verificar — el
mecanismo de auto-commit+push de `server.js` en Situaciones Especiales
generó y revirtió esos 2 commits de prueba en `origin/master`, ya limpiados
(mismo patrón ya aceptado para `TESTX`/`ads_de_...` en la sección anterior).

**Fuera de alcance de esta primera pasada (ver corrección inmediatamente
abajo):** el parser NL de `/kalert` (voz/texto vía Telegram) — la petición
original del usuario solo pedía que "Situaciones Especiales" (solo-UI)
pudiera contemplarlo. Conversión de divisa (no aplica, es un umbral absoluto
en la moneda nativa del ticker). Re-armado automático tras dispararse
(alertas de un solo uso, igual que el resto del sistema).

### Corrección el mismo día: `/kalert` (texto y voz) también soporta precio

El usuario probó de nuevo la petición original por voz en Telegram
(*"avisar si TNZ supera 70 y en vela diaria azul positivo"*) y seguía
fallando — la extensión de arriba solo cubría "Situaciones Especiales"
(la UI web), no `/kalert`, que es como el usuario realmente interactúa con
las alertas. Corregido extendiendo también `scripts/telegram_portfolio_bot.py`
al mismo modelo de condición compuesta, sin crear un sistema paralelo:

- **Sintaxis exacta** — 4º token opcional: `/kalert TNZ d blue_positive >70`
  (`_parse_price_clause()`, regex `^([<>])(\d+(?:\.\d+)?)$`). Sin el 4º token,
  comportamiento y almacenamiento byte a byte idénticos a antes.
- **Lenguaje natural/voz** — `_parse_koncorde_alert_nl()` gana un campo
  `"price"` opcional en el JSON que pide al modelo (Haiku), con la misma
  disciplina "no inventes nada" que ya regía ticker/timeframe/condition: si
  el usuario menciona un precio pero el umbral o la dirección quedan
  ambiguos, se rechaza la alerta entera (nunca se crea a medias, ignorando
  el precio en silencio).
- **Almacenamiento** — `cmd_kalert_set()` gana un parámetro `price` opcional.
  Sin él, escribe la fila plana legacy de siempre. Con él, escribe la fila en
  el esquema compuesto `conditions:[...]` que ya usa "Situaciones
  Especiales" — mismo almacén (`koncorde_bot_alerts.json`), mismo
  evaluador (`evaluate_conditions()` en `koncorde_alert_conditions.py`, sin
  ningún cambio), solo un segundo *escritor* para un formato que ya existía.
  Con varios `timeframes` (sintaxis "diario o semanal"), cada uno se
  convierte en su propia fila con el precio ANDed dentro — mismo mecanismo
  OR-entre-filas ya usado para multi-timeframe, sin lógica nueva.
- **`cmd_kalerts_list()`** pasa a usar `get_conditions()`/`describe_conditions()`
  (el shim de compatibilidad ya existente) en vez de asumir el formato plano
  — así `/kalerts` renderiza correctamente tanto las alertas antiguas como
  las nuevas compuestas, con manejo defensivo (`try/except KeyError`) para
  filas malformadas.
- **Confirmación de ticker deducido** (`_pending_ticker_confirmation`) — el
  precio viaja también en la propuesta pendiente y se aplica igual tanto si
  el usuario responde "ok" como si corrige el ticker directamente.

**Verificado:** 5 tests unitarios sobre `_parse_koncorde_alert_strict`
(sin precio, con `>`/`<`+decimal, 4º token malformado → rechazo total,
multi-timeframe+precio). Llamada real a OpenRouter (Haiku) reproduciendo la
petición original del usuario palabra por palabra — parseada correctamente
(`TNZ`, `d`, `blue_positive`, `price:{above,70.0}`); más 2 llamadas reales
adicionales confirmando que una petición sin precio sigue devolviendo
`price:None` (sin regresión) y que "cae por debajo de 50" mapea a
`below`. Flujo completo `cmd_kalert()` → `cmd_kalert_set()` probado con
Telegram/GitHub-API mockeados: caso con ticker deducido ("Loma") + precio
queda correctamente en confirmación pendiente (no crea la alerta hasta que
el usuario confirme), y al responder "ok" crea la fila compuesta correcta.
Dedup verificado: repetir la misma alerta no duplica fila; el mismo
ticker+timeframe+condición con un umbral de precio distinto sí coexiste
como fila independiente.

---

## Alertas Koncorde — condiciones de dirección/giro de flecha por línea (implementado 2026-08-31)

El usuario pidió poder alertar sobre "el cambio de la flecha que indica el
trend" — la flecha de dirección que el mini-panel de `portfolio.html`
dibuja para cada línea Koncorde — en verde, en azul o "en global" (la línea
*trend*, la marrón/roja), para cada uno de los 3 timeframes. El vocabulario
cerrado de `koncorde_alert_conditions.py` no tenía nada sobre pendiente/giro
de ninguna línea (solo signo de blue/green, `blue_cross_up`, y estado
acumulación/distribución).

**12 condiciones nuevas** = 3 líneas (`blue`, `green`, `trend`) × 4 tipos,
mismo estilo "cerrado y estrecho" que las 7 existentes (dos de nivel + dos
de evento, como ya había `blue_positive` nivel vs `blue_cross_up` evento):

| id | qué evalúa | campo(s) de `koncorde_data.json` |
|---|---|---|
| `{line}_rising` | flecha hacia arriba ahora | `konc_{tf}_{line}_delta1 > 0` |
| `{line}_falling` | flecha hacia abajo ahora | `konc_{tf}_{line}_delta1 < 0` |
| `{line}_turns_up` | la flecha gira al alza en la última barra cerrada (venía plana/bajando) | `konc_{tf}_{line}_last5`: `v[-1]-v[-2] > 0 AND v[-2]-v[-3] <= 0` |
| `{line}_turns_down` | gira a la baja en la última barra cerrada | `konc_{tf}_{line}_last5`: `v[-1]-v[-2] < 0 AND v[-2]-v[-3] >= 0` |

`{line}` ∈ `blue` / `green` / `trend`. `trend` = la línea `konc_{tf}_trend`
(la "marrón/roja" del mini-gráfico, lo que el usuario llama "global") — **no**
`trend_ma` ni el estado global de 4 estados. Los 3 timeframes (`d`/`3d`/`w`)
salen gratis vía `VALID_TIMEFRAMES` como el resto.

**Sin cambios en el dato ni en el pipeline.** `konc_{tf}_{line}_delta1` y
`konc_{tf}_{line}_last5` (blue, green, trend) ya se calculan y guardan en
`koncorde_data.json` desde el mini-gráfico de `portfolio.html` (2026-08-14).
`v[-1]-v[-2]` de `_last5` == `delta1` exactamente (verificado con datos
reales), así que la condición coincide con la flecha que se ve en pantalla.
`check_koncorde_alerts.py` no necesitó tocarse — ya pasa el dict completo
del ticker (`konc_tickers.get(ticker)`) al evaluador.

**Archivos:**
- `scripts/koncorde_alert_conditions.py` — 12 entradas nuevas en `CONDITIONS`
  + `_ARROW_CONDITIONS` (frozenset) + `_arrow_eval()` (helper) + una rama en
  `evaluate()` que despacha las 12 con `condition.split("_", 1)`. Dato
  ausente/corto → `None` (nunca `False`), mismo principio que el resto.
- `scripts/telegram_portfolio_bot.py` — solo ejemplos de mapeo NL añadidos
  al prompt de `_parse_koncorde_alert_nl()` ("la flecha verde gira al
  alza" → `green_turns_up`, "la línea marrón gira a la baja" →
  `trend_turns_down`, "blue subiendo" → `blue_rising`…). El parser estricto
  (`/kalert GGAL 3d green_turns_up`) y el listado (`/kalerts`) recogen las
  condiciones nuevas solos porque leen `KONC_CONDITIONS` dinámicamente.
- `portfolio.html` — 12 opciones nuevas en `KONC_COND_OPTIONS` (con etiquetas
  ES y ↑/↓) disponibles en los 3 selectores D/3D/W del `SpecialSituationModal`
  + rama nueva en `checkKoncordeCond()` (espejo JS literal de `_arrow_eval`,
  mismo patrón de duplicación JS/Python ya aceptado — `calcCMF`, etc.).

**Verificado:** `py_compile` de los 3 scripts Python OK. Evaluador Python
probado contra datos reales (`AAG.V`, `koncorde_data.json`) — los 12 ids en
los 3 timeframes producen valores coherentes con `delta1`/`last5`
(p. ej. `w blue_turns_up`=True porque `_last5` semanal `[…,10.9,9.41,12.42]`
gira de -1.49 a +3.01; `d trend_turns_down`=True; `3d blue_turns_down`=False
porque venía cayendo sin giro fresco). Parser estricto acepta las nuevas
condiciones + cláusula de precio ANDed. `describe_conditions` / `describe`
generan texto correcto para filas legacy y compuestas. Mirror JS de
`checkKoncordeCond` extraído y ejecutado en Node contra los mismos datos
reales — coincidencia exacta con el evaluador Python en los 8 casos
probados, y `blue_positive` legacy sigue funcionando. No se pudo transpilar
`portfolio.html` con Babel (no instalado localmente) — pendiente de
verificación visual en Edge headless contra `node server.js` cuando el
usuario lo tenga en marcha.

**Fuera de alcance (en su momento, cerrado 2026-09-03 — ver sección
siguiente):** cruce trend↔trend_ma como condición de `/kalert`.
Condiciones sobre `slope` de N barras (se usa `delta1`, la barra inmediata,
que es lo que muestra la flecha); estados `up`/`down` sueltos (siguen sin
condición propia, solo `accumulation`/`distribution`).

---

## Alertas Koncorde — cruce trend/trend_ma ("línea roja"), en los 3 timeframes (implementado 2026-09-03)

El usuario intentó crear `/kalert QXO konkorde en vela diaria cruce al alza
de linea roja` y falló en silencio — correctamente, según el diseño: el
vocabulario cerrado de `koncorde_alert_conditions.py` no tenía ninguna
condición de "cruce" entre dos líneas (solo `blue_cross_up`, que es blue
cruzando **cero**, no dos líneas cruzándose entre sí), así que el parser NL
no tenía ningún id al que mapear la petición y la rechazó ("no inventes
nada"). Era exactamente el hueco ya anotado como "Fuera de alcance" en la
sección anterior — la propia base de la cartera `CRUCE_ROJO_D`
(`konc_d_trend_cross`, el cruce de la línea negra `trend` sobre su línea
roja de señal `trend_ma`), calculada desde el 2026-08-30 pero nunca
expuesta como condición de alerta, y solo para D.

**`scripts/koncorde_calculator.py`:** nueva `_compute_trend_cross(tf_name,
trend_a, tma_a)` — mismo `_cross_series()` que ya usaba
`_compute_cross_signal_fields()` (D), ahora también llamada para 3D y W en
`compute_for_ticker()` (antes esas dos ramas descartaban `trend_a`/`tma_a`
con `_, _, _`). Da `konc_3d_trend_cross`/`konc_w_trend_cross`, mismo formato
`"up"/"down"/"none"` que el de D — que se deja intacto, sin tocar
`_compute_cross_signal_fields()` (RSI14/percentil siguen siendo D-only, no
se pidieron para 3D/W y no se han añadido).

**`scripts/koncorde_alert_conditions.py`:** condiciones nuevas
`trend_cross_up`/`trend_cross_down`, leyendo `konc_{tf}_trend_cross`.
**Distintas de `trend_turns_up`/`trend_turns_down`** (que solo miran si la
propia pendiente de `trend` gira, sección anterior) — aquí "cruce" es
dos líneas cruzándose entre sí (trend vs trend_ma), no una línea sola
cambiando de dirección. `"none"` (valor real, "no hay cruce hoy") evalúa a
`False`; solo la ausencia del campo (timeframe sin datos/no calculado
todavía) da `None`/pendiente — mismo principio de siempre.

**`scripts/telegram_portfolio_bot.py`:** ejemplo nuevo en el prompt del
parser NL, con aviso explícito de no confundirlo con `trend_turns_up/down`.

**Verificado:** `evaluate()` con datos sintéticos (up/down/none/ausente,
los 4 casos); pipeline real corrido para QXO vía yfinance —
`konc_{d,3d,w}_trend_cross` ahora se calculan en los 3 timeframes (antes
3D/W ni siquiera tenían el campo); llamada real a
`_parse_koncorde_alert_nl()` con el texto exacto que falló al usuario —
ahora resuelve `{ticker: QXO, timeframes: [d], condition: trend_cross_up}`;
sintaxis exacta (`/kalert QXO d trend_cross_up`) también verificada.
QXO hoy (2026-09-02) no tiene cruce activo en ningún timeframe (trend por
debajo de su trend_ma en los 3) — la alerta creada quedará correctamente
pendiente hasta que ocurra un cruce real.

**Pendiente del lado del usuario:** el campo `konc_{3d,w}_trend_cross`
todavía no existe en el `koncorde_data.json` de producción — se generará
en el próximo run del pipeline (o con `--retry-failed`/un run manual). Debe
crear la alerta de nuevo: `/kalert QXO d trend_cross_up` (sintaxis exacta)
o repetir la petición por voz/texto tal cual la formuló.

---

## Fix: GEX ZeroGEX Fase 2 fallaba en las 3 corridas desde que arrancó (2026-08-31)

**Nota lateral:** el piloto GEX ZeroGEX (`gex-zerogex-fase1.yml`/`-fase2.yml`,
`research/gex_zerogex_pilot_v1/`, `wiki/PREREGISTRO_GEX_ZEROGEX_V1.md`) nunca
se documentó en este archivo cuando se construyó — la única entrada GEX de
aquí ("GEX (dealer gamma exposure) — piloto, no integrado", 2026-08-18) es de
un experimento *anterior y distinto* (`research/gex_monitor_pilot/`, cálculo
DIY vía Black-Scholes, descartado por falta de benchmark) que Fase 1/2
retoman y sí llegan a contrastar contra un proveedor de pago (ZeroGEX). Esta
entrada documenta solo el fix de hoy, no reconstruye el historial completo
del piloto — ver el preregistro en `wiki/` para el diseño completo.

El usuario reportó el workflow "GEX ZeroGEX Fase 2 — DIY Calibration" en
rojo en GitHub Actions. Las 3 corridas desde que Fase 2 arrancó
(2026-08-26/28/29) habían fallado — **0 snapshots reales recogidos en 5
días**. Causa real, en dos capas independientes:

1. **Deriva del cron de GitHub.** El cron programado (`55 19 * * 1-5`,
   19:55 UTC = 15:55 ET) se ejecutó en la práctica con 2h36m, ~6.5h y ~8h de
   retraso en las 3 corridas observadas (confirmado en los logs de cada
   run) — deriva conocida de la plataforma bajo carga, no un fallo de este
   repo. El script (`run_diy_calibration.py`) hizo lo correcto: detectó que
   caía fuera de su ventana de aceptación (15:30-16:15 ET, ya pensada con
   margen para un cron lento) y no recogió nada — comportamiento diseñado,
   no un bug.
2. **El bug real:** el step "Commit snapshot" del workflow hacía `git add`
   incondicional de `fase2_calibration.jsonl` — como nunca se había
   recogido nada (por el punto 1, en todas las corridas), ese fichero no
   existe. `git add` sobre un pathspec inexistente sale con exit 128, y eso
   era lo que marcaba el job entero como fallido — no la ausencia de datos
   en sí, que era correcta y esperada.

**Fix (`gex-zerogex-fase2.yml`):**
- El step de commit ahora comprueba `[ -f "$FILE" ]` antes de tocar git —
  una corrida sin nada que commitear (fuera de ventana, fin de semana, día
  ya recogido por el dedup interno del script) termina en éxito limpio,
  mismo tratamiento que el resto del pipeline da a los pasos "no-op".
- Cron cambiado de un único disparo diario (`55 19 * * 1-5`) a
  `*/15 18-20 * * 1-5` — cada 15 min entre 18:00-20:45 UTC (≈14:00-16:45 ET,
  12 disparos/día). **No cambia la metodología congelada del preregistro**
  (la ventana de aceptación real del script sigue siendo exactamente
  15:30-16:15 ET, sin tocar) — solo aumenta la frecuencia de sondeo para que,
  sea cual sea el retraso de GitHub ese día, alguna de las 12 ejecuciones
  tenga buenas probabilidades de caer dentro de la ventana real. Coste
  extra despreciable: las ejecuciones fuera de ventana no llegan a llamar a
  la API de ZeroGEX (el check de ventana es anterior al fetch), solo gastan
  ~35-40s de minutos de Actions cada una.

**Verificado:** los 3 casos del step de commit probados en aislado (fichero
ausente → exit 0 sin tocar git; fichero presente sin diff → no commitea;
fichero presente con diff nuevo → commitea correctamente) contra un repo git
temporal. YAML del workflow validado con PyYAML tras el cambio.

**Fuera de alcance:** no se ha tocado `gex-zerogex-fase1.yml` (inactivo,
solo `workflow_dispatch`, su fichero de salida ya existe en el repo desde
que Fase 1 concluyó con éxito — mismo bug de clase, pero sin riesgo real
hoy). Si algún día se relanza Fase 1 a mano contra un checkout limpio sin
ese fichero, aplicaría el mismo guard.

---

## Ranking Score — Fase 1 (análisis exploratorio) completada (implementado 2026-09-04)

Disparado por el recordatorio `ranking_score_fase1_analisis`
(`docs/data/reminders.json`, 2026-09-03). Implementa literalmente la sección
"FASE 1 — Análisis exploratorio" del plan original (texto pegado por el
usuario 2026-09-04), acotada por lo ya firmado en
`wiki/PREREGISTRO_RANKING_SCORE_V0.md` (informe de 3-5 páginas, no 10-15; el
gate de cobertura del 1.7 no bloquea Fase 2, ya resuelto en el preregistro
§0). **Nota de proceso:** antes de escribir código se detectó y se corrigió
un cruce de documentos — el usuario pegó primero, por error, el texto de
`P1A/P1B/P1C` de la "Hoja de ruta consolidada — Auditoría de carteras IA"
(sección de arriba) en vez del texto de Fase 1 del Ranking Score; se
verificó contra `p1_readiness_state.json` (ningún umbral disparado
todavía) y contra el propio recordatorio antes de proceder, en línea con
[[feedback_rigor_ask_for_literal_spec]].

Script nuevo: `scripts/ranking_score_fase1_analysis.py`.

**Dataset limpio de P0 (definición operativa de este análisis):**
`dedup_same_day_reruns()` de `compare_vs_baselines.py` (reutilizado, no
reimplementado) sobre `shadow_picks.jsonl` (303→271 filas), filtrado a
`valid_for_performance_tracking != False` (271→150) — excluye runs con
violaciones de HARD_RULES o `forced_run=True`, que nunca se convirtieron en
decisión real de portfolio. De esas 150, 98 ya tienen `ret_1m` y 33
`ret_3m`.

**Paso previo — refrescar reconstrucciones de la Fase 0, no repetirlas
desde cero:** `reconstruct_pcs_components_historical.py`,
`reconstruct_rot_score_delta_historical.py` y
`reconstruct_theme_breadth_historical.py` se habían quedado congelados en
190 filas desde el 2026-08-07 mientras `shadow_picks.jsonl` seguía
creciendo — se re-ejecutaron (idempotentes, solo añaden filas nuevas, sin
`--force`) y subieron a 238 filas cada uno antes de construir el dataset de
Fase 1.

**Consolidación con git-history, más allá de lo que la Fase 0 había
construido:** el plan de Fase 1 pide "régimen macro en el momento de
entrada", `streak_weeks_delta` y `theme_flow_delta` (delta de
`component_B`) — ninguno tenía script de reconstrucción propio (la Fase 0
solo cubrió `rot_score_delta`/`theme_breadth`, ver preregistro §0). En vez
de construir infraestructura nueva, el script reutiliza el
`matched_commit`/`prior_matched_commit` que la reconstrucción de PCS y de
`rot_score_delta` ya habían resuelto por ticker+fecha, y simplemente lee
campos adicionales (`macro_context.regime`, `streak_weeks`,
`pcs_components.B_theme_flow`) del mismo commit de `ai_candidates.json` ya
localizado — cero búsquedas nuevas por fecha, solo más lectura sobre un
commit ya encontrado. Resultado: `macro_regime_at_entry` cubre 150/150,
`streak_weeks_delta` y `theme_flow_delta` ~102-106/150.

**Metodología de clasificación (fijada en esta ejecución, el preregistro
deja el criterio en términos cualitativos):** por componente, Spearman rho
vs `ret_1m`/`ret_3m`, IC95% vía Fisher-z (misma convención que
`analyze_relative_flow_signal.py`). `not_usable_missing_data` si n<15 o
cobertura<30%; `suspicious_redundant` si `|rho|`>=0.70 contra otro
componente preregistrado; `plausible` si `|rho pooled|`>=0.15, p<=0.10, sin
inversión de signo en ningún segmento (cartera/régimen, n>=10) y — solo
para Entry Quality, que sí tiene dirección a priori en el plan — el signo
coincide con lo esperado; `inconclusive` en cualquier otro caso.

**Bug real encontrado y corregido durante la propia ejecución:** la primera
versión calculaba el signo esperado por componente (`expected_sign` en
`COMPONENT_SPECS`) pero nunca lo usaba en la regla de clasificación —
`spike_flag` salió "plausible" con signo **positivo** (spike asociado a
mejor retorno, lo contrario de la hipótesis de extensión) antes del fix.
Corregido añadiendo el chequeo de signo esperado como condición necesaria
de `plausible`; tras el fix, `spike_flag` baja a `inconclusive` (correcto:
señal débil y en la dirección equivocada, no debe contar como evidencia a
favor).

**Resultado (n=98 con `ret_1m`):** de los 14 componentes preregistrados,
solo **`dist_sma20_atr`** clasifica `plausible` (rho=-0.268, p=0.008,
n=98, IC95%=[-0.443,-0.073] — mayor distancia a SMA20 en unidades de ATR
predice peor retorno a 1 mes, en la dirección esperada). El resto queda
`inconclusive` — con n=98 y muestras menores por componente, es el
resultado esperable de una muestra aún pequeña, no evidencia de que el
diseño esté mal (documentado explícitamente así en el informe, para no
malinterpretarlo). Ninguna pareja de componentes cruza el umbral de
redundancia (0.70) todavía, pero 4 parejas quedan cerca (0.53-0.66) y se
listan en el informe como "vigilar, no actuar" — incluye
`konc_3d_state_ord`↔`konc_alignment_ord` (rho=0.663, esperable por
construcción, ya que `konc_alignment` deriva en parte de `konc_3d_state`).

**Koncorde, subsección separada tal como exige el preregistro §1:** n=32-33
frente a `ret_1m` (cobertura 33-41% sobre las 150 filas limpias, muy por
debajo del resto — no es un hueco de logging, Koncorde no existía como
feature antes de 2026-06-30). Los 3 campos (`konc_3d_state`,
`konc_w_state`, `konc_alignment` como proxy de "coherencia D/3D/W")
quedan `inconclusive` frente a `ret_1m`, pero la coherencia D/3D/W muestra
una asociación con MAE (`max_drawdown_1m`) que sí cruza p<0.05
(rho=+0.293, p=0.018, n=65 — más alcista asociado a drawdowns menos
profundos, no a mejor retorno medio) — anotado como patrón a vigilar, sin
ninguna implicación de diseño (§1.1 lo prohíbe explícitamente).

**Gate de cobertura del preregistro §1.7 — no bloqueante (ya resuelto en
el preregistro §0), reportado por transparencia:** Koncorde 3D/W 41.3%,
`rot_score_delta_4w` 68.0% — ambos por debajo del 80% nominal del plan
original, pero el preregistro ya fijó que este gate no detiene Fase 2.
`extension_risk` y `theme_breadth` sí llegan a 100%.

**`vehicle_vs_theme_strength`:** confirmado por grep que no existe como
campo calculado en ningún punto del codebase — reportado directamente como
`not_usable_missing_data`, cobertura 0%, sin inventar un proxy no pedido.

**Salidas:**
- `docs/data/ranking_score_fase1_dataset.jsonl` — dataset consolidado, 1
  fila/pick, 150 filas (formato `.jsonl` en vez de `.csv/.parquet` del
  plan original — mismo contenido tabular, consistente con el resto de
  `docs/data/`).
- `docs/data/ranking_score_fase1_results.json` — correlaciones +
  clasificación completas, incluido el detalle por segmento que el
  informe no lista para mantenerse en 3-5 páginas.
- `docs/analysis/ranking_score_fase1_informe.md` — informe (~4 páginas).

**No se tocó** `pcs_calculator.py`, ninguna cartera, ni el diseño
preregistrado — tal como exige el preregistro §1.1/§5. Próximo paso: Fase
2 (Ranking Score shadow + cartera `RANKING_SHADOW_EXPERIMENTAL` + 7
baselines shadow), sin fecha fija — el preregistro no la agenda por
calendario, arranca cuando el usuario lo decida.

---

## Ranking Score — Fase 2 (shadow + cartera experimental) implementada (2026-09-04)

Mismo día que el cierre de Fase 1, a petición del usuario ("arrancamos").
Implementa literalmente el texto de Fase 2 (pegado por el usuario
2026-09-04, secciones 2.1-2.6) sobre los pesos de bucket congelados en
`wiki/PREREGISTRO_RANKING_SCORE_V0.md` §1-3.

### Fórmula del score — decisión de esta sesión, no parte del preregistro

Ni el preregistro ni el texto de Fase 2 fijan sub-pesos **dentro** de cada
bucket (solo los pesos de bucket 30/25/20/15/10 y qué componentes entran en
cada uno) — confirmado explícitamente con el usuario antes de escribir
código (ver [[feedback_rigor_ask_for_literal_spec]]). Regla adoptada,
documentada aquí para que sea auditable:

- Cada componente se transforma a un sub-score 0-100 con una función
  monótona simple y acotada (dirección tomada literalmente de cómo el plan
  describe cada componente, nunca de los resultados de Fase 1 — que
  prohíbe explícitamente recalibrar).
- Dentro de cada bucket: **media equitativa** de los sub-scores
  disponibles, renormalizada si falta alguno (`vehicle_vs_theme_strength`
  siempre falta — nunca se implementó, confirmado por grep en Fase 1 — así
  que Contexto Sectorial es en la práctica solo `theme_breadth` hasta que
  exista otro dato).
- Score final: suma ponderada de los 5 buckets por sus pesos del
  preregistro, renormalizada sobre los buckets con dato disponible (`cooldown_score`
  siempre tiene valor — 100 si el ticker nunca se pickeó antes — así que en
  la práctica solo Entry Quality/Flow/Cambio/Contexto pueden faltar).

Transformaciones exactas (`scripts/ranking_score_calculator.py`):
`extension_risk` low/medium/high/extreme→100/66.7/33.3/0 · `dist_sma20_atr`
100 en 0 ATR, 0 en ≥3.0 ATR (mismo umbral "extreme" ya usado en
`pcs_calculator.compute_extension_risk`) · `spike_flag`/`momentum_decay`
100 si false · RSI 45-65→100 dentro/0 fuera · `konc_3d_state`/`konc_w_state`
accumulation/up/down/distribution→100/75/25/0 · `konc_alignment` (proxy de
coherencia D/3D/W) bearish_aligned→0 … bullish_aligned→100 ·
`rot_score_delta_4w`/`streak_weeks_delta`/`theme_flow_delta` 50±50·delta/tope
(topes 5/4/12, elegidos por ser aproximadamente el rango real de cada delta
dado los techos de `rot_score`/`streak_weeks`/`component_B`) ·
`theme_breadth` 0-15 peers→0-100 · `cooldown_days` rampa lineal 0→100 sobre
28 días (mismo horizonte que la regla de no-reentrada de la propia cartera).

`ranking_score_data_quality`/`ranking_score_missing_fields`/
`ranking_score_eligible` reutilizan **exactamente** la misma definición que
ya fijó `scripts/ranking_score_fase1_analysis.py` (mismos 5 campos críticos
— `extension_risk`, `konc_3d_state`, `konc_w_state`, `rot_score_delta_4w`,
`theme_breadth` —, mismo umbral 0.80), sin campo `macro_regime_at_entry`
(ese solo servía para la segmentación de Fase 1, no es un input del score).

### `rot_score_delta_4w`/`streak_weeks_delta`/`theme_flow_delta` — via git-history, no un fichero de serie temporal nuevo

En vez de arrancar un `docs/data/*.jsonl` desde cero (con semanas de espera
hasta acumular 28 días, como le pasó a otros históricos de este proyecto),
se reutiliza `list_commits()`/`candidates_at_commit()` de
`reconstruct_pcs_components_historical.py` (Fase 0): el historial ya existe
en git, commiteado 2×/día desde 2026-05-08. Cada corrida busca el commit
más cercano a "hoy − 28 días" (ventana ±5 días) una sola vez (no por
ticker — todos los tickers comparten la misma fecha objetivo, así que es 1
`git show` cacheado, no ~130), y lee `rot_score`/`streak_weeks`/
`pcs_components.B_theme_flow` de ese commit para cada ticker. Da
profundidad histórica completa desde el primer día, sin bootstrap.

**`daily_signals` — hallazgo real durante la implementación:**
`dist_sma20_atr`/`spike_flag`/`rsi_14`/`momentum_decay` (Entry Quality) NO
son campos de nivel superior en `ai_candidates.json` como se asumía al
diseñar la fórmula — viven anidados bajo `candidate["daily_signals"]`
(`pcs_calculator.py`, ya calculados y persistidos ahí desde antes, solo
había que leerlos del sitio correcto). Cobertura real verificada:
127-129/132 candidatos vivos, no hizo falta tocar `pcs_calculator.py`.

`theme_breadth` (Contexto) se calcula en vivo sobre el snapshot de hoy —
misma definición exacta que `reconstruct_theme_breadth_historical.py`
(nº de candidatos `eligible=true` del mismo `theme`, el propio ticker
cuenta si es elegible) — no hacía falta ningún fichero nuevo, es un conteo
directo sobre `data["candidates"]`.

**"shadow" es literal, verificado, no solo nominal:** `compact_candidate()`
en `ai_shared.py` construye un diccionario explícito por whitelist (no
`{**c}`) — los campos `ranking_score_*`/`candidate_ranking_score_shadow`
nunca se añadieron a esa whitelist, así que no pueden llegar al payload del
LLM ni influir en las 4 carteras clásicas por construcción, no por
convención.

**Verificado con datos reales:** `--report` sobre los 132 candidatos
vivos: 117 `ranking_score_eligible=true`, score 30.4-88.9 (mediana 63.0).
Aritmética de un candidato (VLE.TO) verificada a mano campo por campo
contra la fórmula — coincide exacta con el output del script.

### Cartera `RANKING_SHADOW_EXPERIMENTAL` (`scripts/ranking_score_experimental_portfolio.py`)

100% mecánica — el LLM no participa en ningún punto (ni HARD_RULES ni
ranking). Universo: `pcs≥62` **y** `ranking_score_eligible=true`, excluye
ETFs apalancados (denylist explícito — `UCO`/`TQQQ`/etc, ninguno presente
hoy en el universo de 132 pero es la HARD_RULE literal del texto) +
`NON_TRADABLE_SUBTHEMES` (reutilizado de `ai_shared.py`, no reimplementado)
+ tickers ya abiertos en las 4 carteras clásicas + tickers en cooldown de
**esta misma cartera** (cerrados hace <28 días). Selección: top-5 por
`candidate_ranking_score_shadow` (empate a `pcs`), tamaño 5% fijo, máx. 10
posiciones simultáneas.

**Cadencia — auto-gate interno, no en el YAML:** a diferencia del gate
`is_morning` (Mirror Espejo/Insider Activity, resuelto en un step propio
del workflow), aquí el propio script comprueba
`datetime.now(timezone.utc).weekday()==4` (viernes) antes de considerar
entradas nuevas — `--force` lo salta para pruebas manuales. Las salidas
mecánicas se revisan **todos los días**, no solo los viernes.

**Salidas — solo hard failure cierra, literal del texto ("no hay salida
basada en Ranking Score"):** si un ticker desaparece por completo de
`ai_candidates.json` un día, se cierra (`event:"close"`,
`close_reason:"left_universe..."`) — es la única salida automática.
`PCS<55` y "llevar ≥4 semanas abierta" se guardan como **flags visibles**
(`pcs_review_flag`, `review_due`) en la propia posición, nunca cierran nada
— el propio texto de Fase 2 remite esa decisión al "Follow-through engine
(Fase 4)", que no existe todavía; inventar una regla de salida ahí habría
violado la restricción explícita de la sección 2.3.

**Tracking de rendimiento — reutiliza la infraestructura ya existente, sin
tabla nueva:** cada SELECT se loguea también en `shadow_picks.jsonl`
(`model:"ranking-score-shadow-v0"`, `portfolio:"RANKING_SHADOW_EXPERIMENTAL"`,
`valid_for_performance_tracking:true`) con el mismo patrón que ya usa
`cava_portfolio.py` — así `update_performance.py` (Step 10b) rellena
`ret_1w/2w/1m/3m`/MFE/MAE sin ningún script nuevo. Verificado en
producción: `update_performance.py --ticker SLP.L` backfilleó
`entry_price` real en `ai_picks.json` y lo sincronizó a `shadow_picks.jsonl`
en la primera pasada.

**7 baselines shadow (§2.5)** — `docs/data/ranking_score_baselines.jsonl`,
calculadas la misma cadencia semanal: top-5 por `pcs`, `pcs_ex_macro`,
`rot_score`, `ret_13w_vs_spy`, `ret_4w_vs_spy`, `entry_quality_score`, y
`random` con 5 semillas fijas (0-4, para promediar varianza más adelante) —
universo `pcs≥62` únicamente, **sin** exigir `ranking_score_eligible`
(literal del texto: "mismo universo (PCS ≥ 62)", más laxo a propósito que
el de la cartera experimental).

**Métricas semanales (§2.4)** — `docs/data/ranking_score_weekly_metrics.jsonl`:
overlap rate contra las 4 clásicas (mismo día, vía `shadow_picks.jsonl`),
tickers solo-experimental/solo-clásicas. La correlación Ranking
Score→rendimiento y el Rank IC semanal (§2.4) no se calculan todavía en
este script — con n=5 picks/semana no hay potencia para nada semanal
aislado; se evaluarán en Fase 3 sobre el acumulado, tal como hace el resto
del programa (mismo criterio que el resto de análisis de este proyecto:
esperar a tener muestra, no fabricar un número semanal sin sentido
estadístico).

### Registro obligatorio (checklist del preregistro §2, para no repetir el hueco de CAVA_MACRO/MIRROR_ESPEJO)

`_PORTFOLIO_LABELS` en `paper_trading.py` y `notify_telegram.py`
("Ranking Score (shadow)"); `PTF_LABELS`/`PTF_THRESHOLDS` (62, el
`PCS_MIN_UNIVERSE` real) en `docs/index.html` — fuera de
`GROK_PTFS`/`MIMO_PTFS` del mini-panel de overview, mismo criterio que
`CRUCE_ROJO_D` (no tiene modelo). Evento `"event":"close"` explícito desde
el primer commit de `review_positions()`.

### Pipeline (`.github/workflows/market-update.yml`)

Dos steps nuevos, ambos `continue-on-error: true`:
- **Step 9h** (Ranking Score calculator) — justo después de Step 9b
  (Koncorde), antes de Step 9c — necesita PCS y Koncorde del día ya
  escritos.
- **Step 10d2** (cartera experimental + baselines) — justo después de Step
  10d (Cava), antes de Step 10b (`update_performance.py`) — mismo motivo
  que Cava: los picks de hoy entran en el mismo pase de
  `update_performance` sin esperar 12h, y necesita que Step 10
  (`paper_trading.py`) ya haya escrito el SELECT de hoy de las 4 clásicas
  para calcular el overlap semanal correctamente.

**Primer `--apply --force` real ejecutado 2026-09-04** (jueves, fuera del
calendario natural de viernes — mismo criterio que el primer `--apply`
manual de CAVA_MACRO/CRUCE_ROJO_D, sembrar ahora en vez de esperar): 5
posiciones abiertas (SLP.L, LCX.V, DPM.TO, DHR, KOS), 11 filas de baselines
(6 top-N + 5 semillas random), 1 fila de métricas semanales
(`overlap_rate=0.0` — ninguno de los 5 coincidía con un SELECT de las
clásicas ese mismo día). YAML del workflow validado con PyYAML tras los
cambios (42 steps).

### Explícitamente fuera de alcance (Fase 2)

Correlación Ranking Score→rendimiento y Rank IC semanal (esperan a Fase 3,
n insuficiente cada semana por separado). Cualquier ajuste de pesos o
componentes basado en resultados de Fase 1 (prohibido por el propio
preregistro §1.1/§5). Integración con `ai_picks_decision_state.py` (P0 de
la Hoja de ruta consolidada, programa distinto) — el tracking de esta
cartera vive enteramente en `shadow_picks.jsonl`, sin cruzar ambos
programas. Follow-through engine (Fase 4) para decidir salida en los casos
de `pcs_review_flag`/`review_due`.

---

## Ranking Score — monitor de aviso para Fase 3 (implementado 2026-09-04)

A petición del usuario ("crea una alarma para el bot que me avise cuando
tenemos que pasar a Fase 3"), mismo día que Fase 2. Script nuevo
`scripts/ranking_score_readiness_monitor.py`, mismo patrón que
`p1_readiness_monitor.py` (cuenta y avisa una sola vez por umbral vía
state file, no decide ni ejecuta nada) pero para los umbrales de
`wiki/PREREGISTRO_RANKING_SCORE_V0.md` §4, no los de la Hoja de ruta
consolidada.

**Fecha de arranque para "meses desde":** 2026-09-04, el día del primer
`--apply` real de `RANKING_SHADOW_EXPERIMENTAL` (no la fecha del
preregistro ni la de Fase 1, que son anteriores pero no tienen picks reales
detrás).

**Tres alertas, umbrales literales de §4, sin inventar ninguno:**
- 🟢 **Piloto** — ≥30 picks con `ret_1m` maduro Y ≥90 días (~3 meses) desde
  el arranque.
- 🟢 **Productivo** — ≥75 picks con `ret_1m` Y ≥75 con `ret_3m` Y ≥180 días
  (~6 meses).
- 🔴 **Descarte anticipado** — solo se evalúa a partir de 42 días (6
  semanas): retorno acumulado proxy (suma simple de `ret_1m` de los picks
  con entrada en las últimas 6 semanas — no una NAV real de cartera, pero
  con tamaño 5% fijo por posición es aproximadamente proporcional al drag
  real) **por debajo de -10% Y** Spearman(`candidate_ranking_score_shadow`,
  `ret_1m`) **negativo** sobre todos los picks maduros hasta la fecha —
  ambas condiciones a la vez, literal del texto ("rendimiento < -10%
  acumulado tras 6 semanas con correlación negativa"). Solo avisa, no cierra
  la cartera ni toca nada.

**Sin dependencia de scipy/pandas** — Spearman implementado a mano
(`spearman()`, ranking con desempate por rango promedio), mismo criterio de
"scripts monitor ligeros" que `duration_monitor.py`/
`check_koncorde_alerts.py`: un fallo de dependencias no debe quitarle
utilidad a un script que solo cuenta y avisa. Verificado contra
`scipy.stats.spearmanr` con datos sintéticos, con y sin empates —
coincidencia exacta (diferencia ~1e-16, redondeo de punto flotante).

**Wired al pipeline:** Step 10k, después de Step 10b (`update_performance.py`
— necesita `ret_1m`/`ret_3m` ya rellenos) y de Step 10j (P1 readiness
monitor, el de la otra hoja de ruta). `continue-on-error: true`.

**Verificado en producción:** `--dry-run` contra los datos reales de hoy
(0 días desde el arranque, 0 picks con `ret_1m` — recién sembrados) confirma
que ningún umbral dispara todavía, como se espera. Mensaje de confirmación
real enviado a Telegram ("Monitor Ranking Score Fase 3 activo") sin tocar
`ranking_score_readiness_state.json` real — mismo patrón ya usado para
confirmar `p1_readiness_monitor.py` en su día.

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
- ✅ Validación numérica automática: implementada 2026-08-07, ver sección abajo.
- ~~Campo `rejection_primary_reason`~~ — descartado 2026-08-07: ya existe `rejection_category` (HARD_RULE, enum en `ai_shared.py → VALID_REJECT_CATS`) cubriendo el mismo propósito. Añadir un segundo campo con un enum solapado habría reproducido justo el tipo de deriva que `ai_shared.py` se creó para evitar (`HARD_RULES` duplicadas entre `paper_trading.py`/`build_eval_bundle.py`). Decisión del usuario: no duplicar.
- Análisis de correlación entre componentes PCS (A-F) y rendimiento posterior (ret_1m) — cubierto por la iniciativa Ranking Score (ver sección "Ranking Score + PCS reframing"), no se duplica aquí.

---

## Validación numérica automática (implementado 2026-08-07)

Roadmap "Semana 7". Detecta cuando el modelo cita en su razonamiento un
número (PCS, rot_score, streak_weeks, ret_4w/13w_vs_spy, dist_52w_high,
dems, streak_days, ret_5d/10d_vs_spy, outperform_d10) que no coincide con
el valor real que tenía delante en el payload de ese run.

**Implementado como `soft_warning` (`r.warn`), no como `HARD_RULE` (`r.add`)
— desviación deliberada de lo que pedía el roadmap literal ("añádelas como
violaciones").** Motivo: `is_valid_run = v.schema_valid and
v.hard_rule_violations == 0`, y `is_valid_run=False` hace que
`update_portfolio()` no se llame **para todo el run**, incluida la cartera
ACTIVA real. Un match por regex de keyword+número es un heurístico, no una
certeza — convertirlo en violación dura habría podido bloquear selecciones
reales de la cartera en vivo por un falso positivo del validador. Cada
otro check añadido incrementalmente a `validate_model_response()`
(`extension_risk_not_acknowledged`, `KONC_3D_*_WARNING`,
`open_picks_review_missing`, `hold_below_floor`) ya sigue este mismo patrón
— ninguno es `r.add()`. Mismo criterio que el resto del proyecto: observar
primero, endurecer después solo si los datos lo justifican.

**Implementación** (`scripts/paper_trading.py`): `_find_numeric_claims()`
busca pares keyword+número en el texto (ambos órdenes — "PCS=80" y "79.0
PCS" — más un patrón específico y estricto para "N-week streak"/"N-day
streak"), `_nearest_ticker()` decide de qué ticker habla cada número
(el propio del item por defecto, o un ticker distinto si se nombra en la
misma cláusula — "MARA (PCS=80)" — pero nunca cruzando a la frase anterior),
`_is_numeric_discrepancy()` compara contra el valor real del payload
(>10% relativo Y >0.5 absoluto; `dist_52w_high` se compara por magnitud,
no por signo, porque el payload lo guarda con signo pero el modelo casi
siempre lo describe como distancia sin signo — "59.14% por debajo del
máximo de 52 semanas"). Se aplica a `selected[].{reason_short,reason_full,
comparative_edge,key_supporting_factors,key_risks_or_contradictions}`,
`watch[].{reason,watch_trigger}` y `rejected[].reason`.

**Historia real de calibración — 3 iteraciones sobre ~150 respuestas
históricas reales (`docs/data/model_tests/*.json` + `ai_model_payloads/`),
no solo tests sintéticos:**
1. Primera versión (gap de 12-20 caracteres "cualquier cosa menos dígito"
   en ambas direcciones): **3944 warnings sobre 130 items seleccionados**
   — a todas luces roto, no "el modelo alucina en casi cada pick". Causa:
   el gap generoso saltaba por encima de palabras y puntuación para
   emparejar un keyword con un número de una frase completamente distinta
   (p. ej. "...+45.3%), high rotation score (8.0)" emparejaba el 45.3 con
   `rot_score` en vez de con `ret_13w_vs_spy`).
2. Segunda versión (gaps más cortos, 4/3 caracteres): bajó a 205, pero
   persistían dos bugs de fondo: `_NUM_RE` capturaba un punto final de
   frase como si fuera un punto decimal (`"16."` seguido de espacio se
   comía el punto y dejaba `_GAP_BEFORE` conectar con el keyword de la
   frase siguiente), y `\s` en las clases de gap incluía `\n` — cruzando
   directamente el separador `\n` usado a propósito para no mezclar campos
   distintos (`reason_full` vs `comparative_edge` vs cada item de
   `key_supporting_factors`).
3. Tercera versión (regex de número exige dígito tras el punto decimal,
   gaps con `[ \t]` explícito nunca `\s`, corte de frase en `_nearest_ticker`
   antes del `.`/`!`/`?`/`\n` más cercano): **135 warnings sobre 130 items**,
   ratio mucho más creíble. Verificado a mano contra el payload real un caso
   típico que sobrevivió (SASK.V, 2026-05-12, sonnet-4.6): el modelo escribió
   literalmente `"dems=6"` en su razonamiento cuando el payload de ese día
   traía `dems=4` — confirma que el validador ya está detectando alucinaciones
   reales, no solo ruido de regex.

**Tests de regresión:** `scripts/test_numeric_claims_validation.py` (23
tests, sin pytest, mismo patrón que `test_cava_mapping.py`) — cada uno
reproduce uno de los bugs reales encontrados en la calibración de arriba
(punto decimal de fin de frase, `\n` cruzado por `\s`, atribución a un
ticker de la frase anterior, tolerancia de signo en `dist_52w_high`, caso
end-to-end con y sin discrepancia real).

**No implementado a propósito:** promoción a `HARD_RULE`. Si en producción
la tasa de falsos positivos resulta lo bastante baja tras varias semanas de
observación (visible en `ai_model_test_summary.jsonl → soft_warnings`, sin
penalizar `quality_score`), se puede reconsiderar — mismo camino que siguió
`extension_risk`/Koncorde antes de convertirse en señales con peso real.

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
