# Meta-análisis del sistema AI Picks Lab
**Periodo:** 8 mayo – 18 junio 2026 (41 días / ~6 semanas de operación)
**Fecha del informe:** 18 junio 2026
**Destinatario:** Asesor externo

---

## 1. Descripción del sistema

Sistema cuantitativo de paper trading que combina señales técnico-fundamentales con un modelo de IA como filtro final de selección.

**Arquitectura de señales (en orden de aplicación):**
1. **MacroScore** — Determina el "permiso de riesgo" del mercado (régimen: Bull Pleno / Bull Maduro / Bear)
2. **rot_score** (0-10) — Fuerza relativa semanal del ticker vs su sector
3. **PCS** (Pick Conviction Score, 0-100) — Score compuesto de 6 componentes (ver sección 4)
4. **DEMS** (Daily Early Momentum Score) — Señal diaria de aceleración de momentum
5. **IA (Grok-4.3 / Claude Haiku-4.5)** — Comité IA que filtra candidatos y aplica hard rules

**Portfolios gestionados:**
| Portfolio | Umbral PCS entrada | Posiciones max | Tamaño posición |
|-----------|-------------------|----------------|-----------------|
| HIGH_CONVICTION | 85 | 8 | 8–15% |
| CONFIRMED_FLOW_LEADERS | 78 | 12 | 5–10% |
| EARLY_ROTATION | 70 | 15 | 4–8% |
| MACRO_THEMATIC_BENEFICIARIES | 65 | 20 | 3–6% |

**Universo cubierto:** 91 tickers (crypto miners, energía, tech AI, healthcare, Argentina, materiales, ETFs)

---

## 2. Historial completo de operaciones (modelo activo)

### 2.1 HIGH_CONVICTION — Operaciones cerradas

| Ticker | Tema | Entrada | Cierre | Precio entrada | Precio cierre | Retorno | PCS entrada |
|--------|------|---------|--------|----------------|---------------|---------|-------------|
| CORZ | crypto_mining | 08-may | 10-jun | 22.92 | 27.01 | **+17.9%** | n/a |
| CVE | oil_gas | 15-may | 10-jun | 30.15 | 27.65 | -8.3% | 85.0 |
| OXY | oil_gas | 19-may | 10-jun | 59.70 | 56.55 | -5.3% | 89.5 |
| QQQ | global_etf | 19-may | 11-jun | 705.88 | 693.69 | -1.7% | 85.5 |
| VAL | oil_gas | 20-may | 10-jun | 111.05 | 87.49 | **-21.2%** | 89.5 |
| VLE.TO | oil_gas | 20-may | 10-jun | 12.91 | 11.05 | **-14.4%** | 86.0 |

**HIGH_CONVICTION — Posición abierta actual:**

| Ticker | Tema | Entrada | Precio entrada | Retorno estimado |
|--------|------|---------|----------------|-----------------|
| NBIS | ai_cloud | 08-may | 177.05 | **+24.3% (1m)** / ~+115% 13w RS |

### 2.2 CONFIRMED_FLOW_LEADERS — Operaciones cerradas

| Ticker | Tema | Entrada | Cierre | Precio entrada | Precio cierre | Retorno | PCS entrada |
|--------|------|---------|--------|----------------|---------------|---------|-------------|
| NVDA | ai_chips | 08-may | 10-jun | 214.95 | 208.19 | -3.1% | n/a |
| MSTR | crypto_btc | 08-may | 10-jun | 187.59 | 117.02 | **-37.6%** | n/a |
| COIN | crypto_btc | 09-may | 10-jun | 216.60 | 155.50 | **-28.2%** | 83.5 |
| KOS | oil_gas | 15-may | 10-jun | 2.93 | 2.79 | -4.8% | 82.0 |
| WCP.TO | oil_gas | 15-may | 16-jun | 16.68 | 16.18 | -3.0% | 80.5 |
| SU | oil_gas | 16-may | 10-jun | 68.29 | 61.20 | -10.4% | 80.5 |
| ASPI | uranium | 27-may | 10-jun | 6.93 | 6.40 | -7.7% | 78.5 |
| EOSE | energy_storage | 29-may | 10-jun | 8.99 | 6.26 | **-30.4%** | 83.0 |
| SASK.V | uranium | 30-may | 10-jun | 1.17 | 0.91 | **-22.2%** | 83.5 |
| RCAT | defense_space | 30-may | 10-jun | 14.50 | 11.49 | **-20.8%** | 83.0 |

**CONFIRMED_FLOW_LEADERS — Posiciones abiertas actuales:**

| Ticker | Tema | Entrada | Precio entrada | PCS entrada |
|--------|------|---------|----------------|-------------|
| OSCR | healthcare_special | 28-may | 21.99 | 81.8 |
| BBAR | argentina_financials | 03-jun | 18.87 | 79.0 |
| LOMA | argentina_materials | 13-jun | 12.55 | 83.5 |
| GGAL | argentina_financials | 13-jun | 55.16 | 81.8 |
| QQQ | global_etf | 16-jun | 744.00 | 83.0 |
| TDOC | healthcare_special | 16-jun | 7.46 | 81.0 |
| HIMS | healthcare_special | 17-jun | 31.47 | 80.0 |

### 2.3 EARLY_ROTATION — Operaciones cerradas

| Ticker | Tema | Entrada | Cierre | Precio entrada | Precio cierre | Retorno | PCS entrada |
|--------|------|---------|--------|----------------|---------------|---------|-------------|
| TSLA | ev_auto | 09-may | 10-jun | 445.00 | 396.68 | -10.9% | 75.0 |
| ASTS | defense_space | 23-may | 10-jun | 105.86 | 88.71 | **-16.2%** | 69.8 |
| MLX.AX | commodities_metals | 23-may | 10-jun | 1.74 | 1.51 | -13.2% | 69.5 |

---

## 3. Análisis de rendimiento por fases y temas

### Fase 1: Crypto/AI Tech (8-15 mayo)
- **Ganadores:** NBIS +24.3%, CORZ +17.9%
- **Perdedores:** MSTR -37.6%, COIN -28.2%
- **Diagnóstico:** NBIS y CORZ tenían raíces en señales semanales sólidas (streak 8 semanas, rot_score alto). MSTR y COIN eran activos altamente especulativos con streaks cortos y beta extremo.

### Fase 2: Energía/Oil (15-30 mayo) — Concentración intencional
- **El sistema concentró el 72.5% del portfolio en oil_gas en el peak (20 mayo) — esto fue deliberado** durante la fase de paper trading para estudiar el comportamiento del sistema bajo concentración extrema
- CVE, OXY, VAL, VLE.TO, KOS, WCP.TO, SU: todos cerraron en pérdidas el 10 junio
- Las señales técnicas (8-week streak, rot_score 8-9) eran sólidas en el momento de entrada; el macro giró de forma brusca en las semanas siguientes
- **Retorno medio Fase 2:** aproximadamente -10% a -15% por posición

### Fase 3: Momentum DEMS / Early Rotation (23-30 mayo)
- **Todas las posiciones DEMS-driven perdieron dinero:**
  - ASTS (DEMS 18, extension_risk high): -16.2%
  - MLX.AX (DEMS 18): -13.2%
  - EOSE (DEMS 15): -30.4%
  - SASK.V (DEMS 17): -22.2%
  - RCAT (DEMS 19): -20.8%
- **Patrón:** Entrada en momentum extremo = comprar el pico

### Fase 4: Argentina + Healthcare (3 junio en adelante)
- BBAR, LOMA, GGAL: Argentina rotation — muy reciente, sin datos de rendimiento
- OSCR: abierto 28 mayo, señal semanal (streak 6-8 semanas, rot_score 9) — positivo desde entrada
- TDOC, HIMS, QQQ: nuevas entradas 16-17 junio

---

## 4. Métricas de comportamiento del modelo IA

### Grok-4.3 vs Claude Haiku-4.5

| Métrica | Grok-4.3 | Claude Haiku-4.5 |
|---------|----------|-----------------|
| Hard rule violations por run | **0** (prácticamente siempre) | 0-22 violaciones |
| Quality score medio | **92-100** | 63-80 |
| JSON válido (% de runs) | ~95% | ~60-65% |
| Tendencia a seleccionar | Conservador (1-2 picks/run) | Agresivo (5-9 picks/run) |
| Principal problema Haiku | Pocas violaciones desde jun-11 | Output token overflow (8192 limit) causa truncación y JSON inválido |

**Patrón Haiku de violaciones (mayo-junio):** El modelo Haiku violaba sistemáticamente la regla de no hacer SELECT sobre posiciones ya abiertas (hard rule principal). Fue corregido gradualmente con mejoras al validador.

### Costes operativos aproximados (modelo activo: Grok-4.3)
- Coste por run (input ~13-18k tokens, output ~1.5-2.5k tokens): ~$0.020-0.032
- Con 2 runs/día × 40 días × 2 modelos: ~$3-4 en total durante el periodo
- Latencia Grok: 8-25 segundos | Latencia Haiku: 30-68 segundos

---

## 5. Análisis de señales — ¿Qué predice el rendimiento?

### Predictores POSITIVOS de rendimiento (observación preliminar):
1. **streak_weeks ≥ 6** + **rot_score ≥ 8** + **ret_13w_vs_spy alto** → señal de calidad (NBIS, OSCR, CORZ)
2. **spike_flag = false** → picks sin spike superan a picks con spike consistentemente
3. **extension_risk LOW** → menos retrasos

### Predictores NEGATIVOS de rendimiento:
1. **DEMS alto (≥15) + extension_risk high** → casi siempre pick tardío (ASTS, RCAT, EOSE)
2. **Theme concentration risk HIGH** → cuando el tema gira, el portfolio sufre mucho
3. **streak_weeks ≤ 2** + entrada por DEMS solamente → malo (RCAT con streak_weeks 1)
4. **ret_4w_vs_spy > 40%** en entrada → extensión excesiva (MSTR en mayo)

### Señal baseline comparada con modelo IA:
NBIS estuvo en top-3-PCS prácticamente TODOS los días desde mayo-13 hasta junio. El modelo lo detectó correctamente el 8 de mayo. La baseline mecánica de "top-3-PCS" hubiera capturado NBIS perfectamente. La pregunta clave: **¿añade valor el filtro IA sobre la baseline mecánica?** Aún no hay suficientes datos para responder con significación estadística.

---

## 6. Evento crítico: Implementación de cierres el 10 junio

El 10-11 junio el sistema cerró **12 posiciones simultáneamente**. Es importante entender exactamente qué ocurrió:

**Contexto técnico:** La funcionalidad de revisión de posiciones abiertas (`open_picks_review`) **no existía en el schema de respuesta del modelo antes del 10 junio**. Fue implementada ese día al revisar el código. Por tanto:
- Los cierres del 10 junio no fueron "disciplina automática tardía" — fueron el **primer momento en que el sistema podía físicamente generar señales de EXIT**
- Los datos de P&L de las posiciones cerradas reflejan el precio en esa fecha, no el precio en el momento en que las señales se habrían disparado de haber estado disponibles antes
- No es posible reconstruir con precisión "qué habría pasado si los EXIT hubieran estado disponibles antes"

**Estado del PCS el 10 junio (primera vez que el modelo pudo revisarlo):**
- VAL: PCS 89.5 (entrada) → **34.0** (10 jun) — colapso de 55 puntos
- MSTR: → **27.5** | COIN: → **27.5** | EOSE: → **32.5** | SASK.V: → **33.8**
- Los PCS habían colapsado masivamente porque el streak_weeks cayó a 0 en todos los tickers de oil/energy al mismo tiempo — efecto cliff de los datos semanales

**Mecanismo del colapso de PCS:** El sistema PCS está muy correlacionado con streak_weeks. Un streak de 8 semanas que se rompe en una semana pone streak_weeks=0, lo que dispara una caída de PCS en múltiples componentes simultáneamente. Esto crea un lag estructural: el mercado gira, pero el PCS no colapsa hasta que los datos semanales confirman el fin del streak (1-2 semanas después).

**Pregunta clave para el asesor:** ¿Debería existir un mecanismo de salida anticipada basado en deterioro de MacroScore semanal o señales diarias (DEMS decayendo, spike_flag activándose), independiente del PCS individual? ¿O el coste de las salidas prematuras supera al beneficio?

---

## 7. Datos disponibles para análisis profundo

| Dataset | Descripción | Disponibilidad |
|---------|-------------|----------------|
| `shadow_picks.jsonl` | 160 registros con picks de todos los modelos, ret_1d/3d/1w/2w/1m | Completo |
| `ai_model_test_summary.jsonl` | 154 runs con calidad, tokens, coste, violaciones | Completo |
| `baselines.jsonl` | Top-3 mecánico por PCS/rot_score/ret_4w/ret_13w para cada run | Completo |
| `ai_picks.json` | Historial de posiciones abiertas/cerradas con precios reales | Completo |
| `ai_model_payloads/` | Payload exacto enviado al modelo (34 fechas) | Completo |
| `model_tests/` | Respuesta completa del modelo por fecha (67 archivos) | Completo |
| `macro_history.json` | Evolución MacroScore semanal | Completo |
| `ai_candidates.json` | Estado actual de los 91 tickers (PCS, métricas) | Diario |

**Gaps de datos:**
- ret_1m solo disponible en picks de mayo-8 a mayo-10 (los primeros ~21 días hábiles)
- vs_spy_1m: solo disponible en picks de mayo-8 (el batch inicial)
- ret_3m: no disponible aún (necesita hasta agosto-2026)
- No hay datos de performance para shadow picks de shadow model (solo active_model)

---

## 8. Preguntas abiertas para el asesor

1. **¿Es DEMS una señal contraria (detector de techos)?** Todos los picks donde DEMS alto (≥15) fue el criterio primario fallaron con un patrón consistente: rebote de +1 día seguido de -15% a -30% en 2 semanas. Esto sugiere que DEMS extremo no es señal de entrada sino de **exhaustión de momentum** — potencialmente utilizable como señal contraria o de alerta de salida para posiciones existentes. Requiere estudio.

2. **¿Tiene sentido el EARLY_ROTATION portfolio como está diseñado?** De 3 posiciones cerradas, las 3 perdieron (-10%, -16%, -13%). Si DEMS alto señala techos más que entradas, el portfolio de "rotación temprana" podría reformularse: ¿criterios alternativos para detectar rotación real sin depender de spikes DEMS?

3. **Concentración temática:** El sistema llegó al 72.5% oil_gas de forma deliberada (paper trading, modo observación). El periodo demostró empíricamente qué ocurre bajo concentración extrema cuando el tema gira. ¿En qué umbral de concentración tiene sentido implementar un límite duro?

4. **PCS como predictor de rendimiento:** Los tickers con PCS más alto no necesariamente ganaron más. NBIS (PCS ~88) ganó +24% pero MSTR (PCS ~79) perdió -38%, OXY (PCS 89.5) perdió -5%. ¿Qué componente del PCS tiene mayor poder predictivo?

5. **Timing de salida:** ¿Deberían aplicarse reglas de trailing stop basadas en drawdown intraposición, complementarias al criterio actual de PCS < pcs_min_entry?

6. **Grok vs Haiku:** ¿Vale la pena mantener Haiku como shadow model si tiene calidad 60-80 vs 90-100 de Grok? ¿Qué valor aporta como segundo comité?

7. **Macro regime change:** El sistema no detectó el cambio de régimen que causó el colapso de oil en junio. ¿Qué indicadores adelantados podría incorporar el MacroScore para detectar giros antes?

---

## 9. Contexto de mercado (mayo-junio 2026)

- **Mayo:** Macro regime "Bull Maduro Improving" → favorecía picks agresivos
- **Inicio de junio:** El petróleo cayó fuertemente → todo el bloque energy sufrió un rerating de PCS masivo (el streak se rompió)
- **Mid-junio:** Argentina rally (política económica favorable), healthcare liderando, tech (QQQ) rebotando
- El SPY subió ~5-8% en el período, lo que sugiere que el mercado en general fue positivo mientras la selección del sistema fue negativa o neutral en el agregado

---

*Documento generado automáticamente a partir de los archivos de datos del sistema AI Picks Lab.*
*Para análisis interactivo: contactar con el equipo del proyecto.*
