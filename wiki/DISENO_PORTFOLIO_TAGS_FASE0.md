# Portfolio Tracker por temáticas — Fase 0: auditoría y diseño

**Estado:** propuesta para revisión. No hay nada implementado.
**Fecha:** 2026-10-25.
**Decisiones ya acordadas:** fichero `ticker_tags.json` independiente, sin tocar `universe.json` ni `sync_universe.py`; las secciones de `portfolio.json` se conservan; siembra automática marcada como derivada y revisable, sin pisar nunca una corrección manual; drivers macro reservados para más adelante; sector e industria de Yahoo como dato provisional.

---

## 1. Diagnóstico: qué hay hoy

### 1.1 Tres capas que ya existen

| Capa | Fichero | Contenido | Quién lo lee |
|---|---|---|---|
| **Presentación / gestión** | `portfolio.json` → `sections` | 13 secciones manuales, 130 tickers únicos | Ver 1.2. No es solo presentación: dos motores lo usan como cesta temática. |
| **Metadatos de motor** | `docs/data/universe.json` (regenerado desde `backtest/config/individual_stocks.yaml` por `sync_universe.py`) | 150 tickers: `theme` (21), `subtheme`, `region`, `asset_type`, `theme_proxy`, `benchmark` | `pcs_calculator.py` (componente B, `theme_breadth`), `paper_trading.py → compute_theme_concentration`, Ranking Score, `stock_scanner.py` (ROT. TEMPRANA por `subtheme`), carteras Mirror/Cruce Rojo. |
| **Agrupaciones propias de cada módulo** | `CYCLE_MAP` (cycle.html), `CLUSTERS` (rotacion.html), `cluster` del ratio registry (RFL), `SECTIONS` de `market_daily_snapshot.js` | Cada una con su vocabulario | Solo su página, salvo `SECTIONS` de mercado (ver 1.2). |

### 1.2 Dependencias exactas de las secciones de `portfolio.json`

| Consumidor | Uso | ¿Cambia un resultado si se mueve un ticker de sección? |
|---|---|---|
| `scripts/flow_state_lib.py → load_basket_membership` | Secciones (menos `Cartera`, `Watchlist`, `Opciones` y 3 de mercado) = cestas de tema. Une también las `sections` de `market_equities_daily_snapshot.jsonl`. | **Sí.** Alimenta el veto TEMA (`compute_theme_breadth → blocked`) de los filtros Flow. |
| `shared/flow-state-lib.js → fslBuildBasketMembership` | Espejo JS, **solo con secciones de Portfolio** (no las de mercado). | **Sí.** Usado por `screeners.html` y por `scripts/screener_signal_log.js` → afecta al registro histórico de candidatos y a `SCREENER_SHADOW`. |
| `scripts/market_analysis_llm.py` | Agrupa las tablas que ve Sol por sección y añade la columna «Mecánico» (con el veto TEMA). | **Sí.** Cambia el texto que recibe Sol. |
| `scripts/update_insider_activity.py` | `is_open_position` = `shares>0` o sección `Cartera`. | Sí, pero solo la cadencia de caché (2 días frente a 7-10). |
| `scripts/trullas_signal_calculator.py` | Guarda el nombre de la primera sección del ticker para mostrarlo. | Solo la etiqueta mostrada. |
| `scripts/telegram_portfolio_bot.py` | `/portfolio` lista por sección; `/add` escribe en `Watchlist` (vía API de GitHub). | Solo presentación del bot. |
| `portfolio_daily_snapshot.js`, `koncorde_calculator.py`, `ibkr_decision_journal.js`, `trullas.html`, `screeners.html` | Solo la unión de tickers. | No (salvo que se añada o quite un ticker del Portfolio). |

**Hallazgo sobre `compute_theme_breadth`:** no es una métrica de grupo. Calcula, **para un ticker**, la unión de los compañeros de todas sus cestas (él incluido): `breadth = Flow>0 sin veto Koncorde / con dato`, y solo bloquea si es exactamente 0. Si un ticker está en dos cestas, mezcla los dos grupos en un solo denominador. Sirve para su propósito (un veto), pero **no debe reutilizarse para estadísticas por temática**: habría que escribir una función de grupo nueva (ver §7) y dejar esta intacta.

### 1.3 Calidad de los metadatos existentes

- **Los universos no coinciden.** 113 tickers en común; 17 del Portfolio no están en `universe.json` (cannabis menos VFF/CRON/TRLV, los ETFs de Opciones, `GSP.MI`, `BNKR.TO`, `AWX.V`, `SLS.TO`, `WRN.TO`, `VIS.MC`, `URA`).
- **`subtheme` vacío en 82 de 150.** `region` mezcla `CA`/`Canada`, `AUS`/`Australia` y `EU`/`Europe`.
- **Valores por defecto erróneos de `sync_universe.py` (`CLUSTER_DEFAULTS`).** Los tickers añadidos desde el YAML heredan el tema del cluster:
  - `GLEN.L` → `us_tech_ai`, región `US`.
  - `SMR.AX` (Stanmore, carbón metalúrgico) → `commodities_copper`.
  - `AFM.V` (Alphamin, estaño en RDC) → `silver_gold_miners`.
  - `WHC.AX`, `YAL.AX`, `AMR`, `HCC` (carbón) → `commodities_metals`.
  - `ADS.DE` y `III.TO` → región `US`.

  **Esto afecta hoy al PCS** (componente B, `theme_breadth`, concentración por tema). Está fuera del alcance de este proyecto, pero conviene decidir aparte si se corrige (ver decisión D10). Para la siembra implica que lo derivado de `universe.json` es de **confianza baja** cuando `subtheme` está vacío.

### 1.4 Prueba de Yahoo (sector/industria), 19 tickers reales

- **Acciones:** sector, industria y país llegan en ~0,3 s por ticker. **ETFs** (`SLV`, `GDXJ`, `BTCC-B.TO`): sin sector ni industria, solo `quoteType=ETF`.
- **Es útil, pero no basta como clasificación temática:**
  - `MSTR` → Software (su exposición económica es bitcoin).
  - `VFF` → Farm Products (cannabis).
  - `ASTS` → Communication Equipment (espacio).
  - `GLEN.L` y `AFM.V` → «Other Industrial Metals & Mining» (diversificada y estaño).
- **El `country` de Yahoo es el domicilio:** `AFM.V` → Mauritius (opera en RDC); `GLNG` → Bermuda (proyecto en Argentina). Confirma la precaución C: el domicilio no es la exposición.
- Necesita `yfinance` en Python (en esta máquina, `py -3.12`; `py -3` no lo tiene).

### 1.5 Persistencia actual

- `POST /api/portfolio` → escribe `portfolio.json` **solo en disco local**, sin push.
- El bot de Telegram escribe `portfolio.json` **por la API de GitHub**. Hay dos escritores del mismo fichero: un riesgo ya existente, no introducido aquí.
- `/api/universe/*` y Situaciones Especiales → commit y push con `gitCommitAndPushWithRetry`.
- `portfolio.json` tiene `shares: 0` en todo. Las posiciones reales están en `private/ibkr/` (solo local, bloqueado por el servidor). El repo es público.

---

## 2. Diseño: cuatro capas separadas

| # | Capa | Fichero | Edita | Leen | Regla |
|---|---|---|---|---|---|
| 1 | **Gestión / presentación** | `portfolio.json` → `sections` | Usuario (UI, bot) | Lo listado en 1.2 | **Sin cambios.** Las etiquetas nunca escriben aquí. |
| 2 | **Metadatos de motor** | `universe.json` | `sync_universe.py` | PCS, carteras, scanner | **Sin cambios.** Ningún motor leerá la capa 4. |
| 3 | **Hechos importados** | `docs/data/ticker_yahoo_meta.json` (nuevo) | Script manual, regenerable | Siembra y UI (informativo) | Nunca se edita a mano; sin juicio, solo lo que dice Yahoo. |
| 4 | **Taxonomía temática** | `docs/data/ticker_tags.json` (nuevo) | Usuario (modal) y siembra (solo propone) | Solo la UI de Portfolio en el MVP; métricas de grupo en la Fase 3 | La única fuente de las vistas por temática. |

El **mercado de cotización** no se guarda: se deriva al vuelo del sufijo del ticker (`.TO` → Toronto, `.AX` → ASX…), con un helper compartido. No duplica nada y no se puede desincronizar.

Regla de aislamiento: **ningún script de `scripts/`, `backtest/` ni `shared/` usado por el pipeline puede leer `ticker_tags.json` hasta que se decida expresamente** (con su propia sección en CLAUDE.md). Lo garantiza un test (§6, T1).

---

## 3. Esquema de `ticker_tags.json`

```json
{
  "schema_version": 1,
  "dimensions": {
    "industry":     { "label": "Industria",              "exposure": false, "hierarchical": true },
    "commodity":    { "label": "Materia prima",          "exposure": true,  "hierarchical": false },
    "theme":        { "label": "Temática",               "exposure": true,  "hierarchical": true },
    "geo_exposure": { "label": "Exposición geográfica",  "exposure": true,  "hierarchical": false },
    "macro_driver": { "label": "Driver macro",           "exposure": true,  "hierarchical": false, "reserved": true }
  },
  "tags": {
    "industry:mining":         { "label": "Minería",           "parent": null,              "status": "active" },
    "industry:mining_copper":  { "label": "Minería de cobre",  "parent": "industry:mining", "status": "active" },
    "commodity:copper":        { "label": "Cobre",             "parent": null, "status": "active",
                                 "context": { "benchmark": "COPX", "rfl_ratio_ids": ["copper_gold", "xme_spy"] } },
    "geo_exposure:AR":         { "label": "Argentina",         "parent": null, "status": "active",
                                 "context": { "benchmark": "ARGT", "rfl_ratio_ids": ["argt_eem"] } }
  },
  "tickers": {
    "III.TO": {
      "instrument": "stock",
      "assignments": [
        { "tag": "industry:mining_copper", "source": "yahoo",            "review_status": "pending",   "added_at": "2026-10-25" },
        { "tag": "commodity:copper",       "exposure": "primary",   "primary": true,
          "source": "manual",           "review_status": "confirmed", "added_at": "2026-10-26", "reviewed_at": "2026-10-26" },
        { "tag": "commodity:gold",         "exposure": "secondary",
          "source": "derived_universe", "review_status": "pending",   "added_at": "2026-10-25" }
      ],
      "notes": ""
    }
  }
}
```

Reglas:

- **ID estable**: `dimension:slug` en ASCII; no cambia nunca. La etiqueta visible (`label`) sí se puede cambiar. Para retirarla: `status: "retired"`; no se borra, y sus asignaciones siguen visibles como históricas.
- **`source`** (de dónde salió): `manual` | `derived_universe` | `derived_section` | `yahoo`.
- **`review_status`** (si alguien lo ha revisado): `pending` | `confirmed` | `rejected`. Son ejes independientes: un `yahoo` puede estar `confirmed`, y un `manual` puede quedar `pending` si se añadió con dudas.
- **`exposure`** (`primary`/`secondary`/`narrative`): solo en dimensiones con `exposure: true`. En `industry` no aplica (una empresa *es* minera; no tiene una exposición "narrativa" a la minería). Lo valida el servidor.
- **`primary: true`**: como mucho uno por dimensión. Permite la vista «cada ticker una sola vez» (§5).
- **Una corrección manual nunca se pierde**: la siembra solo **añade** asignaciones `pending` que no existan. No modifica ni re-añade nada que esté `confirmed`, `rejected` o con `source: manual`. Rechazar algo deja la fila `rejected`, y eso impide que la siembra lo vuelva a proponer.
- **Retirar una asignación**: `review_status: "rejected"` + `removed_at`. Nunca se borra (sirve para el histórico, §4).
- **`instrument`**: `stock` | `etf` | `etn` | `index` | `crypto`. Hace falta porque 17 tickers no están en `universe.json`; se siembra desde `quoteType` de Yahoo. Los ETFs se tratan aparte en los agregados (§7).
- **Tickers sin entrada**: válidos. Aparecen en el grupo «Sin clasificar» de cada vista.
- `added_at`, `reviewed_at` y `removed_at` los pone el servidor, no el cliente.

---

## 4. Histórico: point-in-time frente a retrospectivo

- Desde el día en que una asignación pasa a `confirmed`, la pertenencia de ese ticker a esa etiqueta es **point-in-time** en el sentido estricto que permite este sistema: el día X sabíamos que pertenecía. Viene de `reviewed_at`/`removed_at`, no del historial de git.
- Cualquier análisis sobre fechas anteriores (aplicar las etiquetas de hoy a `portfolio_daily_snapshot.jsonl` desde el 2026-08-20) es **retrospectivo**. Tiene sesgo de selección: clasificamos sabiendo qué temas se movieron. Cada fila o informe que lo use llevará `membership_mode: "retrospective"`.
- Regla: **ningún estudio de anticipación (Fase 5) se evalúa con pertenencia retrospectiva.** Puede usarse para explorar y diseñar; la validación solo con el tramo point-in-time, desde la fecha de la primera revisión masiva.
- No hace falta un snapshot diario aparte de pertenencia: con `added_at`/`reviewed_at`/`removed_at`, sin borrados y con fechas puestas por el servidor, la pertenencia de cualquier día se reconstruye exacta. Si en la Fase 3 se calculan métricas diarias por temática, cada fila guardará su lista de componentes de ese día.

---

## 5. Interfaz (MVP)

En `portfolio.html`, sin quitar nada:

- **Selector «Agrupar por»:** Secciones (actual, por defecto) | Temática | Materia prima | Industria | Exposición geográfica | Mercado de cotización | Sin agrupar.
- **Grupos plegables.** Cabecera con números absolutos: «Cobre · 7 (5 acciones, 2 ETF)», sin porcentajes en el MVP. Dentro, la misma tabla con las mismas columnas y la misma ordenación.
- **Ticker en varios grupos:** la fila aparece en cada uno con la marca «↻ también en: Oro, Argentina». Es el mismo objeto, no se duplica ningún dato.
- **Interruptor «cada ticker una vez»:** lo coloca solo en su grupo principal (`primary`); los que no tengan principal van a «Sin principal».
- **Filtros combinables por chips** (AND entre dimensiones, OR dentro de una dimensión) y búsqueda por ticker o nombre.
- **Las asignaciones `pending` se ven con borde discontinuo.** Interruptor «solo confirmadas».
- **Totales de la barra resumen:** siempre sobre tickers únicos.
- **Modal del ticker:** bloque nuevo «Clasificación» con chips por dimensión (confirmar / rechazar / cambiar exposición / marcar como principal) y un desplegable para añadir una etiqueta del vocabulario. **No se crean etiquetas nuevas desde ahí**: hay un formulario aparte, para mantener los IDs controlados. Debajo, solo lectura, lo que dice Yahoo y el `theme` de `universe.json`, como referencia.
- **Export a LLM:** sin cambios en el MVP (decisión D8).
- **Fuera del MVP:** vista por drivers macro y métricas por grupo.

---

## 6. Persistencia y seguridad

- Ruta nueva **`POST /api/ticker-tags`** (en `server.js`). Recibe una operación concreta (`assign`, `review`, `retire`, `create_tag`), no el fichero entero. Valida:
  - que la etiqueta existe en el vocabulario;
  - la dimensión y el uso correcto de `exposure`;
  - como mucho un `primary` por dimensión;
  - un `ticker` con el formato normal.

  Pone las fechas, escribe `docs/data/ticker_tags.json` y hace commit y push con `gitCommitAndPushWithRetry`, el mismo mecanismo que Situaciones Especiales.
- **Un solo escritor**: el servidor local. Ni el pipeline ni el bot de Telegram escriben este fichero. La siembra es un script **manual** que pasa por la misma lógica de fusión. Así no hay conflictos de push con el pipeline.
- **Público por diseño.** Solo contiene clasificación, y qué tickers sigues ya es público en `portfolio.json`. **Nunca** se escribe aquí nada de posiciones, tamaños ni notas privadas.
- **Agregados con posiciones reales** (Fase 3+): los calcula el servidor local leyendo `private/ibkr/` en memoria, sin persistirlos en `docs/`, contando cada ticker una sola vez. El navegador solo los recibe para pintarlos.

---

## 7. Agregados (diseño previo a la Fase 3, no en el MVP)

- **Función de grupo nueva**, separada de `compute_theme_breadth`: `group_stats(members, rows_of_day)`. Devuelve n total, n con dato, n acciones, n ETF, y conteos absolutos (Flow>0, Koncorde D/3D/W en acumulación, sobre SMA50…). Reutiliza solo constantes (`KONC_BEARISH`).
- **ETFs del grupo**: se muestran como fila de referencia y no entran en los conteos de componentes.
- **Grupos pequeños**: con menos de 5 componentes con dato, solo conteos («3 de 4»), nunca porcentajes. Umbral provisional (decisión D6).
- **Totales globales y de posiciones**: siempre sobre tickers únicos.
- **Varias etiquetas del mismo ticker ≠ varias confirmaciones** (precaución A). En vistas cruzadas («cobre ∩ Argentina») el ticker cuenta una vez.

---

## 8. Ejemplo: 15 tickers reales

Leyenda de **origen**: Y = Yahoo · U = `universe.json` · S = sección de Portfolio · P = propuesta mía.
**Ninguna asignación está confirmada todavía.** Todo es `pending` hasta que la revises. La columna «confianza» es mi estimación de lo propuesto.

| Ticker | Sección actual | `theme` en universe.json | Yahoo (sector / industria / país) | Propuesta (dimensión: etiqueta, exposición) | Confianza | Notas |
|---|---|---|---|---|---|---|
| III.TO | Cartera | commodities_copper (región US ✗) | Basic Materials / Copper / Canada | industry:mining_copper · commodity:copper (primary) · commodity:gold (secondary) · geo_exposure:CA (primary) | alta | Corregir región. |
| GLEN.L | Mineras | **us_tech_ai ✗** (US ✗) | Basic Materials / Other Ind. Metals & Mining / Switzerland | industry:mining_diversified · commodity:copper (primary) · commodity:coal (secondary) · commodity:zinc, nickel, cobalt (secondary) · theme:commodity_trading (secondary) · geo_exposure:global | media | Diversificada: «primaria» es discutible. Universe mal. |
| AFM.V | Cartera | **silver_gold_miners ✗** | Basic Materials / Other Ind. Metals & Mining / Mauritius | industry:mining_tin · commodity:tin (primary) · geo_exposure:CD (primary) | alta | Domicilio ≠ operación (RDC). |
| DPM.TO | Cartera | silver_gold_miners / gold_silver | Basic Materials / Gold / Canada | industry:mining_gold · commodity:gold (primary) · commodity:copper (secondary) · geo_exposure:BG (primary) | media | Cotiza en Canadá, opera en Bulgaria. Revisar el cobre. |
| SMR.AX | Carbon | **commodities_copper ✗** | Basic Materials / Coking Coal / Australia | industry:mining_coal · commodity:met_coal (primary) · geo_exposure:AU (primary) | alta | Universe mal. |
| CVE | Petróleo | oil_gas / canadian_oil | Energy / Oil & Gas Integrated / Canada | industry:oil_gas_integrated · commodity:oil (primary) · geo_exposure:CA (primary) · geo_exposure:US (secondary, refino) | alta | |
| GLNG | Argentina | oil_gas / lng (US) | Energy / Oil & Gas Midstream / Bermuda | industry:lng_infrastructure · commodity:lng (primary) · geo_exposure:AR (secondary) | media | Hoy está en la sección Argentina: buen caso de etiqueta secundaria frente a sección. |
| GGAL | Argentina | argentina / argentina_financials | Financial Services / Banks - Regional / Argentina | industry:banks · geo_exposure:AR (primary) | alta | |
| YPF | Argentina | argentina / argentina_oil | Energy / Oil & Gas Integrated / Argentina | industry:oil_gas_integrated · commodity:oil (primary) · commodity:natgas (secondary) · geo_exposure:AR (primary) | alta | |
| NVDA | Semiconductores | us_tech_ai / ai_chips | Technology / Semiconductors / US | industry:semiconductors · theme:ai_infrastructure (primary) · geo_exposure:global | alta | |
| TSLA | Opciones | us_tech_ai / ev_tech | Consumer Cyclical / Auto Manufacturers / US | industry:automakers · theme:ev (primary) · theme:robotics (narrative) · theme:ai (narrative) · theme:musk_ecosystem (primary) | media | Caso típico de etiqueta narrativa. |
| ASTS | Cartera / Opciones | defense_space / space_connectivity | Technology / Communication Equipment / US | industry:satellite_communications · theme:space (primary) · theme:defense (narrative) | media | |
| RCAT | Cartera | defense_space / defense_drones | Industrials / Aerospace & Defense / US | industry:aerospace_defense · theme:drones (primary) · theme:defense (primary) | alta | |
| MSTR | Cartera | crypto / bitcoin_treasury | Technology / Software - Application / US | industry:software · theme:bitcoin (primary) | alta | Yahoo engaña: la exposición económica es bitcoin. |
| GDXJ | Cartera | silver_gold_miners / junior_miners | ETF (sin sector) | instrument:etf · industry:mining_gold · commodity:gold (primary) · commodity:silver (secondary) | alta | ETF: fila de referencia del grupo, fuera de los conteos. |

Lo que muestra el ejemplo (corregido 2026-10-25, ver `DISENO_PORTFOLIO_TAGS_DEFINITIVO.md` §8): 3 de 15 tienen el `theme` de `universe.json` mal (y III.TO, la región), 3 tienen el país de Yahoo distinto de la exposición real, y en 2 la industria de Yahoo no dice nada de la exposición económica. **La siembra servirá como borrador; la revisión manual es el grueso del trabajo.**

---

## 9. Plan por fases (solo se ejecuta lo aprobado)

| Fase | Entregable | Archivos | Complejidad |
|---|---|---|---|
| 1a | Vocabulario inicial (~60-80 etiquetas) | `docs/data/ticker_tags.json` | S (lo decides tú) |
| 1b | Hechos de Yahoo | `scripts/fetch_yahoo_meta.py` (manual, `py -3.12`) → `docs/data/ticker_yahoo_meta.json` | S |
| 1c | Siembra con fusión segura + informe de dudosos | `scripts/seed_ticker_tags.py` → `docs/analysis/ticker_tags_review.md` | M |
| 1d | Revisión manual de los ~166 tickers (unión de ambos universos; 130 si solo Portfolio) | — | M-L (tu tiempo) |
| 2a | Ruta `POST /api/ticker-tags` + validación | `server.js` | S |
| 2b | «Agrupar por», filtros y modal | `portfolio.html` | M |
| 2c | Tests de aislamiento y regresión | `scripts/test_ticker_tags_*.{js,py}` | S |
| 3+ | Métricas de grupo, vínculos RFL, histórico | — | Más adelante |

Sin migraciones: ningún fichero existente cambia de formato.

---

## 10. Pruebas de regresión

| ID | Qué garantiza | Cómo |
|---|---|---|
| T1 | Ningún motor lee las etiquetas | Test estático: ningún fichero del pipeline (`scripts/*.py|js`, `backtest/`, `shared/*.js` cargados por scripts) contiene `ticker_tags`/`ticker_yahoo_meta`, salvo una lista blanca explícita (`server.js`, `portfolio.html`, siembra y fetch). Falla si alguien los conecta sin decidirlo. |
| T2 | Cestas de Flow idénticas | Hash de `load_basket_membership()` (Python) y de `fslBuildBasketMembership(portfolio.sections)` (JS) antes y después del cambio. Deben ser byte a byte iguales. |
| T3 | Editar etiquetas no cambia nada de lo anterior | Fixture con mutaciones grandes del fichero de etiquetas (añadir, rechazar, retirar). Se repiten T2, T4 y T5 y la salida debe ser idéntica. |
| T4 | Sol recibe lo mismo | `market_analysis_llm.py` en dry-run sobre una fecha fija: el mensaje de usuario es idéntico, salvo la marca de tiempo. |
| T5 | Screener y su registro idénticos | `screener_signal_log.js` evaluado sobre una fecha pasada fija: mismas filas. |
| T6 | PCS sin cambios de entrada | Hash de `universe.json` e `individual_stocks.yaml` sin cambios, y `pcs_calculator.py` sin referencias nuevas (cubierto por T1). No hace falta recalcular el PCS, porque sus entradas no cambian. |
| T7 | La UI no toca `portfolio.json` | Edge headless: abrir el modal, asignar, rechazar y guardar → `portfolio.json` byte a byte igual. Se comprueban también ordenación, notas, casillas Koncorde y Situaciones. |
| T8 | Contar una sola vez | Fixture con un ticker en 3 grupos: totales globales, «cada ticker una vez» y agregados cuentan 1. |
| T9 | La fusión de la siembra no pisa | Fixture con una asignación `confirmed`, otra `rejected` y otra `manual` → tras re-sembrar, las tres quedan intactas y no reaparece la rechazada. |
| T10 | Validación de la ruta | Etiqueta inexistente, `exposure` en `industry`, dos `primary` en una dimensión, ticker inválido → 400, sin escribir. Probar con entradas inválidas, no solo válidas. |

---

## 11. Riesgos

1. **Confundir capas en el futuro.** Alguien conecta `ticker_tags` al veto TEMA o al PCS «porque ya está ahí». Mitigación: T1 y una sección en CLAUDE.md.
2. **Taxonomía que crece sin control.** Mitigación: no se crean etiquetas desde el modal y hay un vocabulario revisado.
3. **Sesgo retrospectivo** en estudios de temáticas. Mitigación: §4, `membership_mode` obligatorio.
4. **Coste de revisión** (~166 tickers). Mitigación: revisar primero los grupos que uses y dejar el resto `pending` visible.
5. **Yahoo cambia o falla.** Es un fichero de hechos regenerable y la UI funciona sin él.
6. **Ya existente, no introducido aquí:** dos escritores de `portfolio.json` (local y bot) y las etiquetas erróneas de `universe.json` que afectan al PCS.

---

## 12. Mínimo producto útil

Fases 1a-1c + 2a-2c, con la revisión (1d) solo de los grupos que más uses. Resultado: agrupar el Portfolio por temática, materia prima, industria o geografía, filtrar y editar desde el modal. Sin métricas, sin RFL y sin cambiar ningún motor.

---

## 13. Decisiones que necesito

| ID | Decisión | Propuesta |
|---|---|---|
| D1 | Cuatro capas (§2) y la regla de aislamiento | Sí |
| D2 | Etiquetas planas `dimension:slug` con `parent` opcional en `industry` y `theme`, en vez de estructuras por dimensión | Sí |
| D3 | `source` y `review_status` como ejes separados; `exposure` solo en commodity, theme, geo y macro | Sí |
| D4 | Mercado de cotización derivado del sufijo, no guardado | Sí |
| D5 | Ámbito: unión de Portfolio y `universe.json` (~166), o solo Portfolio (130) | Solo Portfolio en el MVP; el resto, cuando tenga sentido |
| D6 | Umbral para mostrar porcentajes en un grupo | ≥ 5 componentes con dato |
| D7 | Persistencia con commit y push automático (como Situaciones) | Sí |
| D8 | ¿Incluir las etiquetas en «Copiar para LLM» del Portfolio? | No en el MVP |
| D9 | ¿Quién propone el vocabulario inicial? | Yo un borrador desde lo existente; tú lo apruebas antes de sembrar |
| D10 | Los `theme` erróneos de `universe.json` (GLEN.L, SMR.AX, AFM.V, carbón…) afectan hoy al PCS | Fuera de este proyecto: decidir aparte si se corrigen (cambia el PCS) |
| D11 | ¿El veto TEMA de Flow migrará algún día a etiquetas? | No ahora; solo con decisión expresa y pruebas propias |
