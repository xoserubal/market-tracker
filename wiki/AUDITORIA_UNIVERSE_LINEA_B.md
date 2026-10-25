# Línea B — Auditoría de integridad de `universe.json`

**Estado:** solo diagnóstico y simulación. No se ha modificado ningún fichero productivo.
**Fecha:** 2026-10-25.
**Alcance:** los 150 registros de `docs/data/universe.json` (149 tickers únicos), que alimentan PCS, carteras y payload IA. Separado de la línea A (`wiki/DISENO_PORTFOLIO_TAGS_DEFINITIVO.md`).

---

## 1. Resumen

- **Hay 39 incidencias objetivas:**
  - **3 símbolos rotos o reutilizados** (GOLD, ASMI, YAN.AX);
  - **4 registros que describen a otra empresa** (VAL, SLP.L, DMX.V, SSV.V);
  - **12 errores de tema o proxy**;
  - **1 cambio de código de bolsa** pendiente de migrar (MRR.XA → NRL.AX);
  - **2 nombres obsoletos por cambio de denominación**;
  - **16 regiones mal**;
  - **1 duplicado** (LLY).

  Aparte, hay **8 decisiones interpretativas** que no mezclo con las objetivas.
- **Los errores han llegado a las decisiones de la IA.** El nombre de la empresa entra en el payload (`compact_candidate → name`).
  - Los payloads recibieron «Vaalco Energy» para VAL en 36 corridas y «Silverpeak Resources» para SLP.L en 43.
  - Los modelos razonaron sobre la identidad equivocada: VAL se seleccionó en HIGH_CONVICTION y CONFIRMED_FLOW_LEADERS (mayo) con el argumento de que «se alinea con el tema petróleo en África» (Valaris es perforación offshore, no una petrolera africana). SLP.L se propuso como «diversificación en plata» (es platino).
- **Impacto en el PCS** (simulación con datos congelados del 2026-10-24):
  - Corregir solo lo objetivo cambia el PCS de **14 tickers** (además de los 3 que se retiran), de −4 a +21 puntos. **Dos cruzan umbrales**: TK (56,2 → 77,2) entra en el rango de CFL, ER y MTB; SLB (41,8 → 62,8) cruza el suelo de 62.
  - Ninguna posición abierta de las cuatro carteras clásicas ni de CAVA_MACRO cambia de PCS. Sí cambian etiquetas o PCS de posiciones abiertas en carteras sombra (MIMO_SHADOW, SCREENER_SHADOW, MACD_COMBO_*, RANKING_SHADOW_EXPERIMENTAL).
- **La causa principal es estructural:** el botón «añadir a AI Picks Lab» de `portfolio.html` mete el ticker en el grupo `Portfolio` del YAML, que no tiene valores por defecto en `sync_universe.py`, así que hereda los de `Growth`. Hay otras seis causas (§4).

---

## 2. Método

**Datos congelados.** Commit `e728e75d` (2026-10-24 22:35 UTC): `universe.json`, `macro_history.json`, `rotation_signals.json`, `stock_candidates.json`, `ai_picks.json` y `individual_stocks.yaml`, extraídos con `git show`.

**Arnés de simulación** (`research/pcs_universe_sim_b/`; `run.sh` lo reproduce todo y comprueba que sale idéntico). Llama a `pcs_calculator.compute_pcs()` **sin modificarlo**, sin red y con `daily=None`: DEMS y `extension_risk` no entran en el PCS, solo en campos informativos.

**Validación del arnés:** con el `universe.json` congelado reproduce el `ai_candidates.json` congelado **149/149 exacto** (PCS, componentes A-F, elegibilidad y tema).

**Escenarios:**
- **B0**: estado actual.
- **B1**: solo correcciones objetivas.
- **B2**: B1 + interpretativas.

**Impacto aguas abajo**, calculado con el código real:
- `paper_trading.compute_theme_concentration` sobre las posiciones congeladas;
- `ranking_score_calculator.build_theme_breadth_index`;
- cruces de los umbrales 82/75/68/62;
- posiciones abiertas afectadas.

**Fuentes de identidad.**
- Yahoo `quoteSummary` (nombre legal, bolsa, sector/industria, país y descripción del negocio) y su histórico de precios, consultados el 2026-10-25.
- Las notas del YAML, que recogen la intención original de quien añadió el ticker.

**Límite:** el ISIN que devuelve `yfinance` no es fiable. Para DPM.TO devuelve `AU0000413890`, un código australiano sin relación con la empresa. Por eso **ninguna identidad queda «verificada» solo con Yahoo**: marco `identity_status = provisional` donde la única fuente sea Yahoo, y recomiendo confirmar en la web de la empresa o en el aviso de la bolsa los casos de símbolo (§6) antes de cambiar nada.

---

## 3. Qué campos de `universe.json` consume cada motor

| Campo | Consumidor | Efecto |
|---|---|---|
| `theme_proxy` | PCS, componente B | **Solo cuenta si el proxy está entre las 22 señales de `rotation_signals.json`**: BTC-USD, HG=F, XLK, XLC, XLY, XLF, XLI, XLB, XLE, XLV, XLRE, XLP, QQQ, IWM, EEM, EFA, FEZ, TLT, GC=F, SI=F, BZ=F, XLU. Hoy, 85 tickers usan su proxy directamente. |
| `theme` | PCS, componente B (alternativa) | Para los **64 tickers** cuyo proxy no está en esa lista (SIL, GDX, COPX, URA, XAR, MSOS, GGAL, KWEB, FXI, vacío…), B sale de la **media del retorno a 13 semanas de los tickers del mismo tema**. Un ticker mal clasificado mueve también el PCS de sus «compañeros» de tema. |
| `theme`, `subtheme` | `compute_theme_concentration` (riesgo de concentración que ve la IA), `theme_breadth` (Ranking Score), ROT. TEMPRANA por subtema (`stock_scanner.py`), `NON_TRADABLE_SUBTHEMES` | Descriptivo para la IA y estructural en las cestas. |
| `tradable`, `priority` | PCS, componente F y elegibilidad | Ninguna corrección propuesta los toca. |
| `name` | **Payload de la IA** | Se envía al modelo (ver §1). |
| `region` | Solo descriptivo | No entra en ningún cálculo ni en el payload. |

---

## 4. Causas raíz

| ID | Causa | Casos |
|---|---|---|
| R1 | **El grupo `Portfolio` del YAML no tiene valores por defecto.** `portfolio.html → toggleStockConfig` añade cada ticker a `Portfolio`, y `sync_universe.py` le aplica los de `Growth` (`us_tech_ai`, proxy XLK, región US). | GLEN.L, y por casualidad ACMR y MU (que sí son tecnológicas) |
| R2 | **Valores por defecto por grupo demasiado gruesos.** Todo lo de `Commodities` se trata como minera de oro (proxy GC=F); todo lo de `Small/EM`, como ETF emergente; todo lo de `Value/Cyclical`, como industrial (XLI). | SLB, MOS, TECK, ASCU.TO, AFM.V; SAIA, KTOS; TK, TTI, GS |
| R3 | **Modal «añadir al universo» sin validación.** La región sale por defecto en `US`, no envía proxies y el tema se elige a mano. | SMR.AX (elegido «cobre»), regiones de ~15 tickers extranjeros |
| R4 | **Metadatos iniciales escritos a mano sin contrastar** (semilla del 2026-05-08). El YAML tiene la nota correcta, pero `universe.json` describe a otra empresa. | VAL, SLP.L, DMX.V, SSV.V |
| R5 | **Ningún control de símbolos muertos, reutilizados o renombrados.** | GOLD (reutilizado), ASMI y YAN.AX (sin datos), MRR.XA (cambio de código), PNPN.V y DPM.TO (cambio de nombre) |
| R6 | **`sync_universe.py` conserva el registro existente para siempre.** Una vez escrito, nada lo revisa de nuevo, así que el error persiste. | Todas las anteriores |
| R7 | **Duplicados.** Un ticker en dos grupos del YAML genera dos registros. | LLY |

---

## 5. Incidencias

### Severidad

| Nivel | Significado |
|---|---|
| **S1** | El símbolo es otra empresa o no tiene datos. |
| **S2** | El registro describe a otra empresa, o el PCS cambia ≥ 5 puntos o cruza un umbral. |
| **S3** | Clasificación incorrecta que afecta a la concentración, la amplitud o los subtemas, sin cambio material de PCS hoy. |
| **S4** | Solo descriptivo (nombre o región). |

Los deltas de PCS son de B1, salvo que se indique otra cosa. **Dependen del día**: B toma el `rot_score` del proxy en esa fecha (hoy XLE = 8, COMPRA). Otro día la magnitud será distinta, aunque el signo del error no.

### 5.1 Símbolo e identidad (objetivo)

| Ticker | Registrado | Identidad contrastada (fuente, 2026-10-25) | Actual (tema / subtema / región) | Corrección | Causa | PCS y otros impactos | Sev. |
|---|---|---|---|---|---|---|---|
| GOLD | sin nombre; YAML: «miner oro (Barrick)» | **Gold.com, Inc.** (NYSE, distribución de metales preciosos, ex A-Mark). Su histórico en Yahoo empieza en 2014: el sistema **nunca** ha seguido a Barrick con este símbolo. Barrick cotiza como **B** («Barrick Mining Corporation», renombrada en mayo de 2025). | silver_gold_miners / — / GLOBAL | Sustituir por `B` o retirar (decisión BD1) | R5 | PCS 22, **elegible**: los modelos podían seleccionarlo como «minera». Retirarlo no cambia los tramos de B de sus compañeros. | S1 |
| ASMI | — | Sin datos (delisted en Yahoo). Duplicado económico de ASM.AS (ya en el universo); el ADR sigue como ASMIY (OTC). | us_tech_ai | Retirar del YAML | R5 | PCS 37, no elegible (F = 0). Solo ruido. | S1 |
| YAN.AX | — | Símbolo inexistente. Yancoal es **YAL.AX**, ya presente. | commodities_metals | Retirar del YAML | R5 | PCS 45, no elegible. Solo ruido. | S1 |
| MRR.XA | — | Northstone Resources (ex MinRex, renombrada en octubre de 2026). `MRR.XA` = Cboe Australia (17 sesiones en el último mes); **`NRL.AX` = ASX principal**, con histórico completo desde 2011 (23 sesiones). `MRR.AX` es el código antiguo de ASX, con serie truncada en Yahoo (71 filas desde jul-2026). **Misma empresa en los tres símbolos.** | commodities_metals / — / US | Migrar a `NRL.AX` tras comprobación específica (decisión BD2) | R5 | Sin cambio de PCS simulable (cambia la fuente de datos). Riesgo actual: indicadores calculados sobre un mercado menos líquido. | S3 |
| VAL | «Vaalco Energy» | **Valaris Limited** (NYSE, perforación offshore). La nota del YAML ya decía Valaris. | oil_gas / africa_oil / US | nombre Valaris; subtema `offshore_drilling`; región GLOBAL | R4 | PCS 72 sin cambio. **El modelo lo eligió en HC y CFL en mayo argumentando «tema petróleo en África».** Agrupado por error con KOS en el subtema `africa_oil`. Abierta en MIMO_SHADOW, SCREENER_SHADOW y MACD_COMBO. | S2 |
| SLP.L | «Silverpeak Resources» | **Sylvania Platinum** (LSE/AIM, platino y metales del grupo del platino en Sudáfrica). El YAML lo decía bien. | silver_gold_miners / silver_miners / UK, proxy SIL | nombre; subtema `pgm_miners`; proxy vacío (SIL no tiene efecto); región South Africa | R4 | B1: 0 puntos. B2 (tema → `commodities_metals`): +14. Razonamiento de la IA basado en «plata». Abierta en RANKING_SHADOW_EXPERIMENTAL y SCREENER_SHADOW. | S2 |
| DMX.V | «Dolly Varden Silver» | **District Metals** (TSX-V, exploración de uranio y polimetálicos en Suecia). El YAML lo decía bien. Dolly Varden es otra empresa. | silver_gold_miners / silver_miners | nombre; tema: no es plata (objetivo); destino `uranium_nuclear` o `commodities_metals` (interpretativo, BD3) | R4 | 0 puntos (las dos medias caen en el mismo tramo hoy). Salía como «riesgo alto» de subtema plata por error; pasa a bajo. | S2 |
| SSV.V | «Silver Storm Mining» | **Southern Silver Exploration** (TSX-V). Silver Storm es otra empresa. | silver_gold_miners / silver_miners | solo el nombre | R4 | 0 puntos. El nombre erróneo llegó a 24 payloads. | S3 |

### 5.2 Tema o proxy objetivamente incompatible con la actividad

| Ticker | Actividad (Yahoo) | Actual (tema / proxy) | Corrección propuesta | Causa | ΔPCS (B1) | Cruces y otros impactos | Sev. |
|---|---|---|---|---|---|---|---|
| TK | Teekay, petroleros | us_cyclical / XLI | oil_gas / tankers / XLE | R2 | **+21,0** (56,2 → 77,2) | **Cruza 62, 68 y 75**: entra en el rango de selección de CFL, ER y MTB. Concentración: oil_gas «alto». | S2 |
| SLB | Servicios petroleros | silver_gold_miners / GC=F | oil_gas / oilfield_services / XLE | R2 | **+21,0** (41,8 → 62,8) | **Cruza el suelo de 62.** | S2 |
| TTI | Servicios petroleros + bromo | us_cyclical / XLI | oil_gas / oilfield_services / XLE | R2 | +21,0 (26,5 → 47,5) | — | S2 |
| GS | Banca de inversión | us_cyclical / XLI | proxy XLF (tema sin cambio) | R2 | +16,0 | — | S2 |
| MOS | Fertilizantes | silver_gold_miners / GC=F | us_cyclical / fertilizers / XLB | R2 | +16,0 | Destino de tema interpretativo; lo objetivo es que no es una minera de oro. | S2 |
| AFM.V | Estaño (RDC) | silver_gold_miners / GC=F | commodities_metals / tin_nickel / sin proxy | R2 | +15,0 | Abierta en MACD_COMBO_SD. | S2 |
| SMR.AX | Carbón metalúrgico | commodities_copper | commodities_metals / met_coal | R3 | +10,0 (46 → 56) | Abierta en SCREENER_SHADOW y MACD_COMBO. Subtema `met_coal` → «alto» (junto con AMR y HCC). | S2 |
| GLEN.L | Minera diversificada + trading | **us_tech_ai / XLK** | commodities_metals / diversified_miners / sin proxy | R1 | +8,0 | — | S2 |
| TECK | Cobre | silver_gold_miners / GC=F | commodities_copper / copper_miners / COPX | R2 | +1,0 | Tema cobre: el riesgo pasa de alto a bajo. | S3 |
| ASCU.TO | Cobre (desarrollo) | silver_gold_miners / GC=F | commodities_copper / copper_developers / COPX | R2 | +1,0 | No elegible (sin datos). | S3 |
| KTOS | Defensa | smallcap_em / EEM, asset_type **etf** | defense_space / defense / XAR; tipo stock | R2 | +1,0 | — | S3 |
| SAIA | Transporte por carretera (EE.UU.) | smallcap_em / EEM, asset_type **etf** | us_cyclical / XLI; tipo stock; región US | R2 | 0 | — | S3 |

**Efectos de segundo orden (B1):** IE, III.TO y REG.V **pierden 4 puntos** sin tocar su registro. Su componente B sale de la media del tema cobre, y esa media empeora al entrar TECK y ASCU.TO y salir SMR.AX. En B2 la entrada de FCX devuelve la media a su tramo y los tres recuperan su PCS: el resultado de cada ticker depende de qué otros cambios se apliquen a la vez. **Corregir un ticker puede mover el PCS de otros**, así que las pruebas de regresión deben fijar la lista completa de tickers que cambian, no solo los corregidos.

### 5.3 Nombres, regiones y duplicados (S4, sin efecto en el PCS)

- **Renombradas, misma empresa:** PNPN.V (Power Nickel → Power Metallic Mines) y DPM.TO (Dundee → **DPM Metals**, septiembre de 2025; hoy con proyectos en Bulgaria, **Bosnia y Herzegovina**, Serbia y Ecuador tras comprar Adriatic Metals). El nombre llega al payload; corregirlo es objetivo.
- **Región por defecto `US` en tickers extranjeros:** III.TO, YAL.AX, WHC.AX, SMR.AX, ADS.DE, REG.V, SLG.V, MRR.XA, GHM.AX, MOH.HM, GTE, BUR, NBIS, RIO, TK y RYM.NZ. No afecta a ningún cálculo.
- **Duplicado:** LLY tiene dos registros (grupos `Defensive` y `Salud_Largecap` del YAML). Sin efecto en el PCS (el diccionario se queda con uno), pero ensucia el fichero.

### 5.4 Decisiones interpretativas (B2; requieren tu criterio)

| Ticker | Opción | ΔPCS | Comentario |
|---|---|---|---|
| FCX | us_cyclical → commodities_copper (COPX) | +5,0 | El YAML lo puso a propósito como «proxy del ciclo global». |
| RIO | us_cyclical → commodities_metals | +15,0 | Mismo argumento. |
| SLP.L | silver_gold_miners → commodities_metals | +14,0 | El platino es metal precioso; las dos lecturas son defendibles. |
| WHC.AX, YAL.AX | commodities_metals → oil_gas (thermal_coal) | 0 | El motor no tiene un tema «carbón»; el carbón térmico es energía. |
| NKE | us_defensive → us_cyclical | −4,0 | Arrastra a CMCSA (+3,0) por la media del tema. |
| EOS.AX | smallcap_speculative → defense_space | 0 | |
| TSND.TO, PLNH | proxy XLY → MSOS (coherencia con VFF y CRON) | −7,0 cada uno | Hoy XLY da B directo; MSOS da la media del tema. |
| BUR, RYM.NZ | sin propuesta | — | Litigios (relación con Argentina por el pleito de YPF) y residencias de mayores: no encajan en el vocabulario del motor. |

---

## 6. Resultados agregados de la simulación

| | B0 actual | B1 objetivo | B2 + interpretativo |
|---|---|---|---|
| Tickers en el universo | 149 | 146 | 146 |
| Elegibles | 143 | 142 | 142 |
| PCS ≥ 82 (entrada HC) | 1 | 1 | 1 |
| PCS ≥ 75 (CFL) | 16 | **17** (+TK) | 17 |
| PCS ≥ 68 (ER) | 28 | **29** | 29 |
| PCS ≥ 62 (MTB / suelo) | 34 | **36** (+TK, +SLB) | 36 |
| Tickers con ΔPCS ≠ 0 | — | 14 | 18 |

**`theme_breadth` del Ranking Score (B1), como (elegibles, total):**
- `silver_gold_miners`: (19, 20) → (13, 13)
- `oil_gas`: (18, 18) → (21, 21)
- `commodities_metals`: (9, 11) → (12, 13)
- `us_tech_ai`: (13, 14) → (12, 12)

**Riesgo de concentración** (el campo que ve la IA): cambia para 31 tickers en B1. Lo más visible:
- el cobre pasa de «alto» a «bajo» (IE, III.TO, REG.V, TECK);
- `commodities_metals` pasa de «medio» a «alto» (GLEN.L, MLX.AX, PNPN.V, carbón…);
- DMX.V deja de contar como plata.

**Posiciones abiertas afectadas:** ninguna en HIGH_CONVICTION, CFL, ER, MTB ni CAVA_MACRO. En carteras sombra:
- VAL (MIMO_SHADOW, SCREENER_SHADOW, MACD_COMBO_CD/SD): solo subtema y nombre;
- SLP.L (RANKING_SHADOW_EXPERIMENTAL, SCREENER_SHADOW): subtema, y además +14 de PCS en B2;
- SMR.AX (SCREENER_SHADOW, MACD_COMBO): +10 de PCS;
- AFM.V (MACD_COMBO_SD): +15 de PCS;
- REG.V (SCREENER_SHADOW): −4 de PCS.

**Observación lateral (no es un error de datos, fuera de alcance):** `compute_theme_concentration` suma las posiciones de **todas** las carteras, también las sombra. Por eso hoy `healthcare_largecap` y `oil_gas` aparecen con 48 posiciones cada uno, y casi todo sale con riesgo «alto». Conviene revisar aparte si es el comportamiento buscado.

---

## 7. Recomendación de corrección en origen (no aplicada)

1. **Corregir los registros en `universe.json` y las notas en `individual_stocks.yaml`.** Como `sync_universe.py` conserva lo existente, la corrección persiste. Los símbolos se cambian en el YAML (que define el universo) y, si procede, en `portfolio.json`.
2. **Cerrar R1 y R2 en `sync_universe.py`.** Un ticker nuevo sin metadatos explícitos no debería heredar un tema inventado. Opciones (BD4):
   - **(a)** añadir valores por defecto propios para `Portfolio` (tema vacío, sin proxy, `needs_classification: true`). Ojo: con el tema vacío, B da 10 puntos fijos (`no_theme_data`), lo que también cambia el PCS de los tickers nuevos.
   - **(b)** que la sincronización avise y se niegue a dar elegible un ticker sin clasificar.
3. **Validar el modal «añadir al universo» (R3):** sin región por defecto, tema obligatorio y proxy sugerido según el tema.
4. **Validador nuevo `scripts/validate_universe.py`** en el pipeline, solo como aviso (nunca bloquea), con `continue-on-error`. Comprueba:
   - tema y subtema dentro del vocabulario;
   - proxy en la lista efectiva o vacío a sabiendas;
   - duplicados;
   - símbolos sin datos en N días;
   - nombre de `universe.json` frente al nombre legal en Yahoo (avisa de discrepancias, no corrige);
   - región frente al sufijo del ticker.

   Cierra R5-R7 y evita que vuelva a pasar en silencio.
5. **Pruebas de regresión** (en el mismo cambio que la corrección):
   - el arnés de este informe, guardado en el repo con los datos congelados;
   - un test que fija **exactamente** la lista de tickers con ΔPCS ≠ 0 y sus valores, incluidos los de segundo orden;
   - que todos los demás tickers den PCS idéntico;
   - un test de que `sync_universe.py` ya no asigna `us_tech_ai` a un ticker del grupo `Portfolio`.
6. **Orden:**
   1. símbolos (S1, BD1/BD2);
   2. identidades (VAL, SLP.L, DMX.V, SSV.V y renombres);
   3. temas y proxies objetivos;
   4. R1/R2 en la sincronización + validador;
   5. interpretativas, solo las que apruebes.

   Una rama y un commit independientes de la línea A. Tras desplegar, el primer `ai_candidates.json` real se compara con la simulación.

---

## 8. Decisiones pendientes de la línea B

| ID | Decisión | Propuesta |
|---|---|---|
| BD1 | GOLD: ¿sustituir por `B` (Barrick) o retirar? | Sustituir por `B`, si quieres seguir una minera de oro grande. Si no, retirar. |
| BD2 | MRR.XA → NRL.AX (YAML, universo y `portfolio.json`) | Migrar, tras confirmar el aviso de ASX; conservar `MRR.XA` como alias histórico (en la línea A, `ticker_history`). |
| BD3 | Tema de DMX.V: `uranium_nuclear` o `commodities_metals` | `commodities_metals` (polimetálico + REE, según tu nota del YAML). |
| BD4 | Comportamiento de `sync_universe.py` con tickers sin clasificar: (a) o (b) del §7.2 | (b): aviso y no elegible hasta clasificar. Es lo más seguro, pero cambia la elegibilidad de los tickers nuevos. |
| BD5 | Qué interpretativas del §5.4 aplicar | Ninguna en la primera corrección; revisarlas aparte. |
| BD6 | ¿Aplicar las correcciones objetivas aunque TK y SLB entren en rango de selección? | Sí: el PCS actual de ambos está calculado con un proxy equivocado. |
