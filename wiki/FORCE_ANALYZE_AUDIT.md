# Force Analyze & Modo Auditoría — Guía completa

Script: `scripts/force_analyze.py`

---

## Para qué sirve

`force_analyze.py` tiene dos usos distintos:

| Modo | Cuándo usarlo |
|------|--------------|
| **Análisis** | Quieres que uno o varios modelos analicen un ticker concreto ahora mismo, fuera del pipeline automático |
| **Auditoría** | Grok y Mimo han llegado a conclusiones opuestas y quieres una tercera opinión con los datos exactos que vieron ambos |

---

## Modo 1 — Análisis forzado

### Uso básico

```bash
# El modelo activo analiza el ticker con datos actuales
py -3 scripts/force_analyze.py NVDA
```

### Con comparación de cartera

El modelo recibe las posiciones abiertas de la cartera especificada, enriquecidas con datos actuales (PCS, rot_score, streak_weeks), y debe argumentar si el nuevo ticker es más o menos convincente que cada una de ellas.

```bash
# Comparar contra todas las carteras
py -3 scripts/force_analyze.py SMCI --compare-portfolio all

# Comparar contra una cartera específica
py -3 scripts/force_analyze.py CORZ --compare-portfolio HIGH_CONVICTION
py -3 scripts/force_analyze.py SE   --compare-portfolio MIMO_SHADOW
```

Portfolios válidos: `HIGH_CONVICTION`, `CONFIRMED_FLOW_LEADERS`, `EARLY_ROTATION`, `MACRO_THEMATIC_BENEFICIARIES`, `MIMO_SHADOW`, `all`.

### Elegir modelos

```bash
# Solo el modelo activo (por defecto)
py -3 scripts/force_analyze.py TSLA

# Modelos específicos (se llaman en paralelo, independientemente)
py -3 scripts/force_analyze.py TSLA --models grok mimo
py -3 scripts/force_analyze.py TSLA --models haiku
py -3 scripts/force_analyze.py TSLA --models sonnet

# Todos los modelos configurados
py -3 scripts/force_analyze.py TSLA --all-models
```

Aliases disponibles: `grok` → `x-ai/grok-4.3` · `mimo` → `xiaomi/mimo-v2.5-pro` · `haiku` → `anthropic/claude-haiku-4.5` · `sonnet` → `anthropic/claude-sonnet-4.6`

También se pueden usar IDs completos de OpenRouter directamente.

### Guardar resultado

```bash
py -3 scripts/force_analyze.py NBIS --all-models --compare-portfolio all --save
```

Con `--save`:
- Crea `docs/data/force_analysis/NBIS_20260625_1930.json` con la respuesta completa
- Actualiza `docs/data/force_analyses.json` (log del visor en el dashboard, máx 100 entradas)

### Tickers fuera del universo

El universo habitual son 91 tickers en `docs/data/ai_candidates.json`. Si pides un ticker que no está:

```bash
py -3 scripts/force_analyze.py AAPL   # no está en el universo
```

El modelo recibe solo el macro_context y trabaja sin datos PCS/DEMS/rot_score. Lo indica explícitamente en su respuesta.

---

## Modo 2 — Auditoría de discrepancias

### Cuándo usarlo

Cuando observas que Grok y Mimo han llegado a decisiones contrarias sobre el mismo ticker en el mismo pipeline run. Ejemplo real: Grok REJECT SE, Mimo SELECT SE (2026-06-25).

### ¿Qué datos usa la auditoría?

A diferencia del análisis normal (que usa `ai_candidates.json` actual), la auditoría carga los archivos históricos del pipeline:

| Fuente | Qué contiene |
|--------|-------------|
| `docs/data/ai_model_payloads/YYYY-MM-DD.json` | Payload exacto enviado a ambos modelos — mismo ticker, mismos números |
| `docs/data/model_tests/YYYY-MM-DD_grok.json` | Respuesta completa de Grok (razones, factores, riesgos) |
| `docs/data/model_tests/YYYY-MM-DD_mimo.json` | Respuesta completa de Mimo |

Esto garantiza que el árbitro ve exactamente lo mismo que vieron los modelos originales — sin diferencias de timing ni de datos.

---

### Opción A — Exportar prompt para copiar-pegar (sin coste de API)

**Este es el modo recomendado.** Genera un texto completo y autocontenido que puedes pegar en cualquier LLM: Claude.ai, ChatGPT, Grok web, Gemini, etc.

```bash
# Run de hoy (usa la fecha de hoy automáticamente)
py -3 scripts/force_analyze.py SE --audit

# Run de una fecha específica
py -3 scripts/force_analyze.py SE --audit --date 2026-06-25

# Guardar también como archivo .txt
py -3 scripts/force_analyze.py SE --audit --save
py -3 scripts/force_analyze.py SE --audit --date 2026-06-25 --save
```

Con `--save` crea: `docs/data/force_analysis/SE_20260625_1932_audit_prompt.txt`

**Flujo de trabajo:**
1. Ejecutas el comando → el prompt aparece en el terminal
2. Seleccionas todo el texto del terminal (o abres el `.txt`)
3. Lo pegas en el LLM que prefieras
4. El LLM responde con su veredicto, comparativa de los dos modelos y factores decisivos

**Estructura del prompt exportado:**
```
======================================================================
  MODEL ARBITRATION — SE  (pipeline date: 2026-06-25)
======================================================================

[Instrucciones para el árbitro]

[MACRO CONTEXT — régimen, MacroScore, delta_1w, delta_1m, trend]

[TICKER DATA — PCS, rot_score, streak_weeks, DEMS, spike_flag,
               ret_4w/13w, dist_52w_high, extension_risk, flags...]

[PORTFOLIO MANDATES — umbrales de cada cartera para referencia]

[MODEL DECISIONS — decisión completa de cada modelo con razones,
                   factores y riesgos tal como los expresó cada uno]

[YOUR ARBITRATION — qué se pide al árbitro]
```

---

### Opción B — Llamar a un modelo árbitro por API (gasta créditos)

```bash
# Sonnet como árbitro (más potente, ~$0.03)
py -3 scripts/force_analyze.py SE --audit --models sonnet

# Haiku como árbitro (más barato, ~$0.005)
py -3 scripts/force_analyze.py SE --audit --models haiku

# Múltiples árbitros a la vez
py -3 scripts/force_analyze.py SE --audit --models haiku sonnet

# Con fecha específica y guardado
py -3 scripts/force_analyze.py SE --audit --date 2026-06-25 --models sonnet --save
```

**Nota:** Si el árbitro es el mismo modelo que ya tomó una decisión original (ej: pedir a Grok que arbitre entre Grok y Mimo), el script lo advierte pero lo permite igualmente. En ese caso, preferir sonnet o haiku como árbitros independientes.

Con `--save`:
- Crea `docs/data/force_analysis/SE_20260625_1930.json` con el veredicto estructurado
- Actualiza `docs/data/force_analyses.json` con `"type": "audit"` para que el dashboard lo distinga

---

## Resumen de flags

| Flag | Descripción |
|------|-------------|
| `--models MODEL [MODEL ...]` | Alias o ID de modelos específicos |
| `--all-models` | Todos los modelos configurados (activo + shadows) |
| `--compare-portfolio PORTFOLIO` | Contrasta con posiciones abiertas de esa cartera |
| `--audit` | Modo auditoría (carga datos históricos del pipeline) |
| `--date YYYY-MM-DD` | Fecha del run a auditar (por defecto: hoy) |
| `--save` | Guarda resultado en disco + actualiza log del dashboard |

---

## Combinaciones típicas

```bash
# "¿Debería entrar en NVDA ahora?"
py -3 scripts/force_analyze.py NVDA --compare-portfolio all --save

# "¿Grok o Mimo tenía razón sobre SE?"  → copiar-pegar en Claude.ai
py -3 scripts/force_analyze.py SE --audit --date 2026-06-25 --save

# "Que sonnet arbitre el caso de SE de ayer"
py -3 scripts/force_analyze.py SE --audit --date 2026-06-24 --models sonnet --save

# "Ver qué opina cada modelo sobre MSTR y si encaja en HIGH_CONVICTION"
py -3 scripts/force_analyze.py MSTR --all-models --compare-portfolio HIGH_CONVICTION --save

# "Segunda opinión rápida y barata sobre un ticker"
py -3 scripts/force_analyze.py CORZ --models haiku
```

---

## Ver resultados en el dashboard

AI Picks Lab → pestaña **Force Analysis**

- Las entradas de análisis normal muestran: acción recomendada, cartera, señal, factores clave, riesgos, comparaciones con posiciones.
- Las auditorías se muestran con badge morado **AUDITORÍA** e incluyen: decisiones originales de cada modelo (expandibles) + veredicto del árbitro con `agrees_with`, `decisive_factors` y resumen de arbitraje.

Los resultados más recientes aparecen primero. El log guarda un máximo de 100 entradas.

---

## Archivos de salida

| Archivo | Cuándo se crea |
|---------|---------------|
| `docs/data/force_analysis/TICKER_YYYYMMDD_HHMM.json` | Análisis o auditoría API con `--save` |
| `docs/data/force_analysis/TICKER_YYYYMMDD_HHMM_audit_prompt.txt` | Exportación texto sin `--models` con `--save` |
| `docs/data/force_analyses.json` | Log acumulado del dashboard (siempre con `--save`) |
