# Integración de un agente externo en AI Picks Lab — cuestionario para su desarrollador

> **Para el desarrollador del agente:** este documento describe el sistema al que
> se conectaría tu agente y recoge las preguntas que necesitamos responder antes
> de escribir una línea de código. No necesitas conocer nuestro repo para
> contestarlas — todo el contexto necesario está aquí.
>
> Las preguntas marcadas **[BLOQUEANTE]** condicionan el diseño entero; sin ellas
> no se puede empezar. Las marcadas **[AJUSTE]** se pueden decidir sobre la marcha.

---

## 1. Qué es el sistema al que te conectas

**AI Picks Lab** es un sistema de *paper trading* (cartera simulada, sin dinero
real) que evalúa si un modelo de IA aporta valor como filtro final sobre señales
cuantitativas ya calculadas. La filosofía es explícita:

```
MacroScore                    →  permiso de riesgo (campo de juego)
rot_score + relative strength →  hacia dónde se mueve el capital
PCS (Pick Conviction Score)   →  qué vehículo concreto lo captura
IA                            →  decide si la señal es suficientemente limpia
```

La IA **no predice el mercado**: filtra candidatos ya puntuados. Esto es
importante porque tu agente puede tener una filosofía distinta — y eso está bien,
pero necesitamos saberlo para diseñar la integración y la medición.

### Cadencia y datos

- El pipeline corre **2 veces al día** (08:00 y 20:00 UTC) en GitHub Actions.
- Trabajamos con **datos de cierre diario** (Yahoo Finance, FRED). **No hay datos
  intradía, ni tick, ni order book, ni profundidad de mercado.**
- Todo se versiona en git: cada decisión, su razonamiento y su resultado quedan
  registrados de forma auditable.

### Carteras existentes

Hoy conviven 7 carteras con mandatos distintos (`HIGH_CONVICTION`,
`CONFIRMED_FLOW_LEADERS`, `EARLY_ROTATION`, `MACRO_THEMATIC_BENEFICIARIES`,
`REJECTED_HIGH_SCORE` (control), `MIMO_SHADOW`, `MIRROR_ESPEJO`). Tu agente
gestionaría **una cartera nueva e independiente**, sin interferir con las demás.

### Cómo encajaría tu agente (el molde ya existe)

Ya tenemos un precedente exacto: la cartera `MIRROR_ESPEJO` la gestiona un modelo
distinto al del sistema principal, con su propio prompt y sus propias reglas,
**sin** usar PCS ni las reglas del motor principal. Tu agente seguiría ese mismo
molde:

1. Cada ejecución le pasamos un **payload JSON** con los candidatos y su contexto.
2. Tu agente devuelve un **JSON** con sus decisiones (entradas y, si procede, salidas).
3. Nosotros aplicamos esas decisiones a la cartera y **medimos el resultado real**
   a 1 semana, 2 semanas, 1 mes... comparándolo contra *baselines* mecánicas
   (ej. "comprar simplemente los 3 de mayor PCS") y contra las otras carteras.

**El objetivo es que sea falsable.** Si tu agente no bate a una baseline mecánica
tonta, queremos que eso se vea en los datos.

---

## 2. Preguntas

### Bloque A — Acceso técnico

**A1. [BLOQUEANTE] ¿Cómo se invoca al agente desde código?** Marca la que aplique:

- [ ] **Modelo alojado en OpenRouter** (tiene un slug tipo `miorg/mi-modelo`).
      *Es el caso más sencillo: nuestro código ya llama a OpenRouter, solo
      habría que pasarle otro identificador.*
- [ ] **API HTTP propia** (endpoint REST/gRPC, local o en cloud).
      → Indica: URL, método, formato de autenticación, y si es accesible desde
      internet (GitHub Actions necesita alcanzarla) o solo desde red local.
- [ ] **System prompt + RAG sobre un modelo comercial** (el "conocimiento
      específico" no es un fine-tune, sino contexto inyectado).
      → Indica qué modelo base y si el RAG lo gestionas tú o hay que replicarlo.
- [ ] **Script o proceso local** no expuesto como servicio.
      → Esto implica decidir dónde se ejecuta (probablemente fuera de GitHub
      Actions), coméntalo.
- [ ] Otro: _______________

**A2. [BLOQUEANTE] Si es API propia:** ¿es *stateless* (cada llamada independiente,
le mandamos todo el contexto) o mantiene estado/memoria entre llamadas (recuerda
sus posiciones y decisiones previas)?

*Por qué importa: si mantiene estado, hay que decidir quién es la fuente de verdad
sobre la cartera — él o nosotros — y qué pasa si se desincronizan.*

**A3. [AJUSTE] Límites operativos:** ¿hay límite de peticiones, coste por llamada,
o latencia máxima esperada? (Nuestro pipeline tolera hasta ~180 s por llamada.)

**A4. [AJUSTE] ¿Es determinista?** ¿Con el mismo input devuelve siempre lo mismo,
o hay temperatura/aleatoriedad? *Afecta a si podemos reproducir una decisión para
auditarla después.*

---

### Bloque B — Operativa

**B1. [BLOQUEANTE] ¿Cuál es el horizonte temporal de sus operaciones?**

- [ ] **Swing (días a semanas)** — encaja directamente con nuestro pipeline.
- [ ] **Posicional (semanas a meses)** — encaja, pero habría que añadir
      horizontes de medición más largos (hoy medimos bien hasta 1 mes).
- [ ] **Intradía / muy corto plazo** — ⚠️ **incompatible de raíz**: solo tenemos
      datos de cierre y 2 ejecuciones al día. Requeriría infraestructura nueva
      completa. Dilo cuanto antes si es el caso.
- [ ] Mixto / aún por definir.

**B2. [BLOQUEANTE] ¿Sobre qué universo de activos debe poder operar?**

- [ ] Los **~128 candidatos** que ya puntuamos (tienen PCS, rot_score, Koncorde,
      señales diarias, riesgo de extensión). *Máxima comparabilidad.*
- [ ] El **universo Koncorde (~197 tickers)** — incluye las posiciones reales del
      usuario. Tienen Koncorde y precios, pero no PCS ni rot_score.
- [ ] **Libre**: cualquier ticker que él decida. ⚠️ Para tickers fuera de nuestro
      universo no tendremos métricas propias — habría que ampliar el pipeline o
      renunciar a compararlo con las baselines.
- [ ] Solo un subconjunto concreto: _______________ (ej. solo un sector, solo
      un mercado, solo ETFs...)

**B3. [BLOQUEANTE] ¿Quién decide las salidas (cierres de posición)?**

- [ ] **El agente, con red de seguridad mecánica** *(nuestra recomendación)*: él
      revisa las posiciones abiertas y decide mantener o cerrar, pero existe un
      stop mecánico por debajo que cierra pase lo que pase. Mide su criterio sin
      riesgo de que una posición quede olvidada si el agente falla.
- [ ] **Solo el agente**: control total. Máxima fidelidad a su método.
- [ ] **Solo mecánica** (ej. trailing stop fijo): la IA solo elige entradas.
      Aísla la calidad de la selección respecto al *timing* de salida.

**B4. [AJUSTE] Tamaño de posición:** ¿lo decide el agente (y con qué criterio:
convicción, volatilidad, Kelly...) o fijamos un tamaño fijo por posición?

**B5. [AJUSTE] ¿Cuántas posiciones simultáneas como máximo?** ¿Y hay reglas de
concentración (máximo por sector/tema, correlación entre posiciones)?

**B6. [AJUSTE] ¿El agente opera solo en largo, o también en corto?** *Nuestro
sistema actual asume solo largos; los cortos requerirían cambios en la medición.*

---

### Bloque C — Datos que necesita el agente

Esta es la parte más importante para que la integración sea útil de verdad.

**C1. [BLOQUEANTE] Del inventario del Anexo (sección 3), ¿qué campos necesita tu
agente para decidir?** Márcalos o lístalos.

**C2. [BLOQUEANTE] ¿Qué necesita que NO esté en ese inventario?** Sé concreto —
por ejemplo:

- Datos fundamentales (PER, márgenes, deuda, crecimiento de ingresos, guidance)
- Fechas de resultados / calendario corporativo
- Datos de opciones (volatilidad implícita, open interest, put/call por ticker)
- Sentiment o noticias por ticker
- Datos macro específicos no cubiertos
- Insider trading, posicionamiento institucional (13F), short interest
- Otros: _______________

*Nota: distingue entre "imprescindible para funcionar" y "mejoraría la decisión".
Añadir una fuente nueva al pipeline es trabajo real; queremos priorizar bien.*

**C3. [AJUSTE] ¿Necesita histórico o le basta la foto del día?** Si necesita
histórico: ¿de qué campos y con cuánta profundidad? *Ahora mismo el payload que
enviamos es una foto del día actual más, opcionalmente, el snapshot de la semana
anterior.*

**C4. [AJUSTE] ¿Necesita conocer el estado de la cartera** (posiciones abiertas,
precio de entrada, P&L actual, días en posición) **para decidir?**

---

### Bloque D — Formato de la respuesta

**D1. [BLOQUEANTE] ¿En qué formato devuelve sus decisiones?** Necesitamos JSON
parseable de forma fiable. Nuestro esquema mínimo sería algo así (adáptalo a lo
que tu agente ya produzca — es más fácil que nos adaptemos nosotros):

```json
{
  "date": "2026-08-02",
  "selected": [
    {
      "ticker": "XXX",
      "conviction": "high|medium|low",
      "size_pct": 5.0,
      "reason": "justificación citando datos concretos"
    }
  ],
  "open_positions_review": [
    {"ticker": "YYY", "action": "HOLD|EXIT", "reason": "..."}
  ],
  "rejected": [
    {"ticker": "ZZZ", "reason": "por qué no lo selecciona"}
  ]
}
```

**D2. [BLOQUEANTE] ¿Puede justificar cada decisión citando los datos concretos que
recibió?** *Esto no es cosmético: es lo que nos permite detectar alucinaciones. En
el sistema actual detectamos casos reales de un modelo confundiendo la métrica de
un ticker con la de otro, o inventando comparaciones con semanas anteriores que
nunca vio. La justificación es la única forma de pillarlo.*

**D3. [AJUSTE] ¿Devuelve también los candidatos que descarta y por qué?** *Muy
valioso: nos deja medir no solo sus aciertos, sino lo que se dejó fuera.*

**D4. [AJUSTE] ¿Expone alguna medida de confianza/incertidumbre** por decisión?

---

## 3. Anexo — Inventario de datos ya disponibles

Todo esto existe hoy, calculado por ticker, sin trabajo adicional. Si el agente
necesita algo de aquí, es cuestión de añadirlo al payload (trivial).

### Puntuaciones propietarias

| Campo | Descripción |
|---|---|
| `pcs` | Pick Conviction Score, 0–100 |
| `pcs_components` | Desglose en 6 componentes: permiso macro (15), flujo temático (22), fuerza relativa individual (23), flujo técnico (18.5), aceleración temprana (7), calidad del dato (3.5) |
| `rot_score` | Score de rotación del sector/tema (0–10) |
| `signal` | Señal cualitativa derivada |
| `eligible` | Si pasa los filtros mínimos |
| `is_early` | Si está en fase de rotación temprana |
| `streak_weeks` | Semanas consecutivas manteniendo la señal |

### Retornos y fuerza relativa

`ret_4w_vs_spy`, `ret_13w_vs_spy` (alfa vs S&P 500), `dist_52w_high`
(distancia al máximo de 52 semanas).

### Señales diarias (bloque `daily_signals`)

`daily_early_momentum_score` (DEMS, 0–20), `ret_5d_vs_spy`, `ret_10d_vs_spy`,
`ret_20d_vs_spy`, `outperform_days_10d`, `streak_days`, `momentum_accel`,
`vol_5d_vs_20d`, `spike_flag`, `dist_sma20_atr`, `rsi_14`, `momentum_decay`.

### Koncorde Plus (indicador de flujo institucional vs minorista)

Calculado en **3 marcos temporales** (diario `D`, 3 días `3D`, semanal `W`). Por
cada uno: `blue` (dinero institucional), `green` (dinero minorista), `trend`,
`state` (`accumulation`/`up`/`distribution`/`down`), más deltas, pendientes,
cruces y flags. Además:

- `konc_alignment` — lectura resumida cruzando los 3 marcos
- `konc_mirror_signal` — patrón de giro por reversión
- `konc_d_blue_z` — z-score del flujo institucional vs su propia distribución
- `konc_d_blue_accel` — aceleración del flujo

### Riesgo de extensión ("¿llego tarde?")

`extension_risk` (low/medium/high/extreme), `extension_points`, `extension_flags`.
Combina distancia a la media móvil en ATRs, retorno de 4 semanas, RSI, decaimiento
de momentum y detección de *spikes*.

### Concentración temática

`theme`, `subtheme` (21 temas finos), `cluster`, `region`, más el riesgo de
concentración de la cartera por tema y subtema.

### Otros técnicos

`volume_vs_20d`, `low_break_20d`, `close_reclaim_3d`, `price_range_20d_position`,
`distance_to_sma20_atr`, `macd_pts`, `rsi_pts`.

### Contexto macro (global, no por ticker)

`score` (MacroScore), `regime` (5 regímenes: Bull Pleno, Bull Maduro, Transición,
Risk-OFF, Capitulación), `trend`, `phase_quality`, `delta_1w`, `delta_1m`.

### Fuera del payload pero disponible en el sistema

Fear & Greed de CNN con sus 7 subcomponentes, monitor de estrés de duración
(yields, spreads de crédito, subastas del Tesoro), ~45 ratios de fuerza relativa
entre activos, fase del ciclo económico estimada sobre 10 fases clásicas + 4 temas
fuera de ciclo.

---

## 4. Lo que necesitamos para empezar

Con las respuestas a las preguntas **[BLOQUEANTE]** podemos escribir el diseño
concreto. Lo mínimo imprescindible:

1. **A1** — cómo se invoca al agente (y credenciales/endpoint si aplica)
2. **B1** — horizonte temporal
3. **B2** — universo de activos
4. **B3** — quién decide las salidas
5. **C1 + C2** — qué datos necesita, y cuáles le faltan
6. **D1 + D2** — formato de salida y si justifica sus decisiones

Idealmente, además: **un ejemplo real de input y output del agente** (aunque sea
de una prueba manual). Vale más que cualquier descripción.
