# Preregistro — Ranking Score v0

**Fecha de firma:** 2026-08-06
**Autor:** usuario + Claude (revisión conjunta del plan de implementación)
**Alcance:** Fase 1 (análisis exploratorio) → Fase 3 (evaluación out-of-sample) del
Ranking Score shadow y la cartera `RANKING_SHADOW_EXPERIMENTAL`. No cubre
Fase 4 (Follow-through, documento aparte).

> Este documento fija el diseño **antes** de mirar el informe de Fase 1.
> Cualquier cambio posterior a esta fecha se marca "post-preregistro" con
> justificación conceptual escrita — nunca numérica ni motivada por el
> resultado del análisis.

---

## 0. Punto de partida (verificado 2026-08-06, no asumido)

- **P0 (dedup) ya estaba resuelto** antes de escribir este documento —
  `_log_shadow_picks()` (2026-08-05) + `dedup_same_day_reruns()` en
  `compare_vs_baselines.py`. La correlación PCS↔ret_1m=-0.007 citada como
  motivación de este plan ya es la cifra post-dedup (`wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md`).
- **Cobertura verificada sobre el dataset de trabajo** (159 picks con `pcs` y
  `ret_1m` disponibles, deduplicados, 2026-05-09 → 2026-07-07):

  | Componente | Cobertura histórica | Método |
  |---|---|---|
  | `extension_risk` | 100% | ya reconstruido, `extension_risk_reconstructed.jsonl` |
  | `rot_score_delta` | 0% directo | reconstruible al 100% vía `git log` de `ai_candidates.json` (`rot_score` presente desde el primer commit, 2026-05-08) |
  | `theme_breadth` | 0% directo | reconstruible por el mismo método (contar candidatos elegibles del mismo `theme` en el snapshot del día) |
  | `konc_3d_state` / `konc_w_state` | 3.1% directo, **techo ~15% incluso con reconstrucción** | Koncorde no existía como feature antes de 2026-06-30 (verificado en git history) — no es un gap de logging, es ausencia real de la señal en ese periodo |

  Cobertura en candidatos **en vivo** (hoy): 100% en todos los campos
  anteriores — el gate de 80% de la Fase 1.7 del plan original **no bloquea
  Fase 2**, solo condiciona qué puede analizarse retrospectivamente en Fase 1.

- **Trabajo pendiente antes de arrancar Fase 1:** dos scripts de
  reconstrucción vía git-history (mismo patrón que
  `reconstruct_extension_risk_historical.py`, que importa el cálculo real en
  vez de reimplementarlo):
  - `rot_score_delta` por ticker+fecha (rot_score en entry_date vs N días antes).
  - `theme_breadth` por ticker+fecha (nº de candidatos elegibles del mismo
    theme en el snapshot de ese día).

---

## 1. Lista congelada de componentes candidatos

Tomada literalmente del documento de plan original (sección "Diseño del
Ranking Score"), sin ajuste por resultados de ningún análisis:

| Bucket | Peso | Componentes individuales (Fase 1 los evalúa, no los redefine) |
|---|---|---|
| Entry Quality | 30% | extension_risk, dist_sma20_atr, spike_flag, RSI 45-65 vs fuera, momentum_decay |
| Flow Institucional | 25% | konc_3d_state, konc_w_state, coherencia D/3D/W |
| Cambio de Señal | 20% | rot_score_delta 4w, streak_weeks_delta, theme_flow_delta |
| Contexto Sectorial | 15% | theme_breadth, vehicle_vs_theme_strength |
| Cooldown | 10% | días desde último pick del mismo ticker |

**Justificación conceptual de los pesos** (no ajustada a datos): Entry
Quality pesa más porque es la pregunta directa que el Ranking Score existe
para responder ("¿es buena esta entrada, ahora?"). Flow Institucional pesa
segundo porque es la señal más independiente del PCS (Koncorde no entra en
PCS ni en rot_score). Cambio de Señal pesa por delante de Contexto porque un
delta reciente es más accionable que un nivel estático. Cooldown pesa menos
porque es un filtro de higiene (evitar reentradas repetidas tipo
ASPI/SASK.V), no una señal de calidad.

**Nota Koncorde (decisión explícita 2026-08-06):** dentro de Flow
Institucional, Koncorde se evalúa en Fase 1 en una **subsección separada**,
nunca en la misma tabla de correlaciones que componentes con historial
completo. Cada correlación reportada para Koncorde debe incluir su n real y
el intervalo de confianza al 95% — su cobertura útil arranca en 2026-07-21,
no en 2026-05-08 como el resto. Su clasificación en Fase 1 (`plausible` /
`inconclusive` / etc.) tiene **carácter provisional**, señalado como tal en
el informe. Si en Fase 2 el Ranking Score entra en shadow con Koncorde
dentro, su peso inicial dentro de Flow Institucional debe ser conservador
dada la asimetría de evidencia frente al resto — el argumento conceptual
(3D reduce ruido, capta acumulación institucional temprana) es sólido, pero
no hay todavía evidencia cuantitativa comparable en volumen a la de los
demás componentes.

---

## 2. Reglas de la cartera experimental — `RANKING_SHADOW_EXPERIMENTAL`

(Idénticas al plan original §2.3, fijas durante todo el experimento — ver
prohibiciones en §5.)

- Universo: PCS ≥ 62 **y** `ranking_score_eligible = true` (data_quality ≥ 0.80, ningún campo crítico totalmente missing).
- Selección: top-N por `candidate_ranking_score_shadow` (N=5 por defecto), semanal (tras el run del viernes).
- Tamaño: 5% fijo. Máx. 10 posiciones simultáneas.
- Cooldown: sin reentrada al mismo ticker hasta 4 semanas desde su cierre.
- HARD_RULES codificadas en Python (no delegadas al LLM): excluir ETFs apalancados, excluir tickers ya en `active_picks_relevant` de otras carteras, excluir datos incompletos críticos.
- LLM (opcional): solo comentario textual posterior, sin poder sobre la selección.
- Salida: revisión cada 4 semanas (HOLD/EXIT). PCS < 55 fuerza revisión (flag, no EXIT automático). Hard failure (delisting, sale del universo) sí cierra. **Sin salida basada en Ranking Score** — el experimento evalúa entrada, no salida.
- Convive con las 4 carteras clásicas sin restricción de solapamiento; tracking independiente por cartera.
- **Checklist de registro obligatorio al crear la cartera** (gap real que ya pasó dos veces — `CAVA_MACRO` y `MIRROR_ESPEJO` quedaron invisibles/sin aviso semanas por no completarlo):
  - `_PORTFOLIO_LABELS` en `paper_trading.py` y `notify_telegram.py`.
  - `PTF_LABELS` / `PTF_THRESHOLDS` en `docs/index.html`.
  - Evento `"event": "close"` explícito en cada cierre (no solo `close_date`/`close_reason`) — sin esto, `_find_unnotified()` nunca detecta el cierre y el aviso de Telegram se pierde para siempre, no solo se retrasa.

---

## 3. Baselines shadow obligatorias (§2.5 del plan original, sin cambios)

top-N por: PCS · pcs_ex_macro · rot_score · ret_13w_vs_spy · ret_4w_vs_spy ·
entry_quality_score · random (múltiples semillas). Las 7 se calculan y
guardan cada semana, no operan.

---

## 4. Criterios de promoción y descarte

Idénticos al plan original §3.1–3.3, sin recortar (son la parte del
documento que más importa mantener literal):

- **Piloto:** ≥30 picks, ≥3 meses, Spearman(Ranking Score, ret_1m) > 0,
  outperformance vs baseline PCS y baseline rot_score, MFE/MAE y max
  drawdown no peores que baseline PCS.
- **Productivo:** ≥75-100 picks, ≥6 meses, idealmente 2 regímenes macro (o
  cambio significativo de MacroTrend), Spearman > 0.15 en ret_1m **y**
  ret_3m, outperformance vs **las 7 baselines**, no dependencia de 1-2
  winners extremos, consistencia en ≥2 de 3 sub-períodos.
- **Descarte anticipado:** rendimiento < -10% acumulado tras 6 semanas con
  correlación negativa, overlap >80% con carteras clásicas, error
  metodológico detectado en el cálculo.
- El PCS **nunca desaparece** aunque el Ranking Score se promocione —
  sigue siendo puerta de elegibilidad.

---

## 5. Prohibiciones durante el experimento

No ajustar pesos con la muestra actual. No mover picks entre carteras. No
cambiar reglas de selección ni de baselines. Cualquier cambio para el
experimento activo: parar, marcar "post-preregistro", justificar por
escrito, reiniciar el reloj.

---

## 6. Timeline (recortado — sin informes de 20-30 páginas)

1. P0 — ya verificado (este documento, §0).
2. Fase 0 — campos `pcs_ex_macro`/`pcs_ceiling`/`pcs_normalized`/`component_*`
   en `pcs_calculator.py` + persistencia en snapshots + los dos scripts de
   reconstrucción (rot_score_delta, theme_breadth) — antes de Fase 1.
3. Fase 1 — informe descriptivo de **3-5 páginas** (no 10-15), con la
   subsección Koncorde separada (§1). ~2-3 semanas.
4. Fase 2 — Ranking Score shadow + `RANKING_SHADOW_EXPERIMENTAL` + 7 baselines. ~mes 2.
5. Fase 3 — informe final de **5-8 páginas** (no 20-30), mes 5-6+.

---

## 7. Referencias

- Plan de implementación original (pegado por el usuario, 2026-08-06).
- `wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md` — diagnóstico que motiva este plan.
- `wiki/ASESOR_EXTERNO_PCS_INFORME.md` — techos reales del PCS.
- Recordatorio `koncorde_research_log_revision` (2026-08-18) — **cancelado**
  2026-08-06, subsumido en Fase 1 de este documento. Nuevo recordatorio:
  `ranking_score_fase1_analisis` (2026-09-03).
