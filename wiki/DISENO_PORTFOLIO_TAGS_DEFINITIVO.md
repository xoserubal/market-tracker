# Portfolio Tracker por temáticas — diseño definitivo v2 (línea A)

**Estado:** arquitectura aprobada conceptualmente (2026-10-25). Implementación **no autorizada** todavía.
**Versión:** v2, con tus ajustes de D12, D13, identidad, histórico, ETFs, cabeceras y persistencia. Sustituye a v1 (este mismo fichero) y a `wiki/DISENO_PORTFOLIO_TAGS_FASE0.md`.
**Alcance:** solo la línea A. La línea B está en `wiki/AUDITORIA_UNIVERSE_LINEA_B.md`, con rama, commit y validación propios.

---

## 1. Decisiones

| ID | Estado | Decisión |
|---|---|---|
| D1 | ✅ | Cuatro capas: gestión (`portfolio.json` → secciones), motor (`universe.json`), hechos importados (`ticker_yahoo_meta.json`) y taxonomía (`ticker_tags.json` + registro de eventos). **Ningún motor lee las capas 3 y 4.** Lo garantizan tests permanentes (§9). |
| D2 | ✅ | Etiquetas `dimension:slug` con `parent` opcional; IDs estables y vocabulario extensible. |
| D3 | ✅ ajustada | La asignación separa **fuente**, **confianza** y **revisión**. La exposición se expresa con dos campos, **relación** (`direct`/`indirect`/`narrative`) e **intensidad** (`high`/`low`), y la **etiqueta principal de navegación** (`nav_primary`) es un tercer campo, independiente (§3). |
| D4 | ✅ | El mercado de cotización se deriva del sufijo; la exposición geográfica se revisa a mano. |
| D5 | ✅ | El MVP clasifica los 130 tickers del Portfolio; el esquema admite cualquier instrumento sin alterar universos ni elegibilidad. |
| D6 | ✅ | Umbrales 1-4 / 5-9 / ≥10 **solo para métricas futuras**. Las cabeceras del MVP muestran solo recuentos descriptivos (§6). |
| D7 | ✅ ajustada | Un solo servidor escritor (§8), registro de eventos con escritura anticipada, recuperación comprobable y publicación git de solo dos ficheros. |
| D8 | ✅ | «Copiar para LLM» sin cambios. |
| D9 | ✅ | Vocabulario propuesto por mí, revisado frente a los 130 tickers (§5 y Anexo A). |
| D10 | ✅ | Los errores de `universe.json` van en la línea B. La siembra de A **no usa** los metadatos de `universe.json` de los tickers señalados en B (§7). |
| D11 | ✅ | El veto TEMA de Flow sigue con las secciones. |
| D12 | ✅ ajustada | `stage` ∈ `explorer`/`developer`/`producer`/`mixed`; sin asignación = desconocida. Solo para emisores mineros y de upstream de petróleo y gas (E&P e integradas). Royalty es modelo de negocio y va en `industry` (`oil_gas_royalties`). Servicios, perforación, midstream y GNL no llevan etapa. Solo descriptivo. |
| D13 | ✅ ajustada | **`issuer_id` + `instrument_id`** en vez de `same_issuer_as` (§2). |

---

## 2. Identidad: emisores e instrumentos

**Por qué no `same_issuer_as`:** una referencia entre instrumentos admite cadenas (A → B → C), referencias a tickers inexistentes y ciclos. Con una entidad emisor separada, cada instrumento apunta a **un** emisor y no hay cadenas, por construcción.

```json
"issuers": {
  "iss_0042": {
    "legal_name": "Green Thumb Industries Inc.",
    "aliases": [],
    "identity_status": "provisional",
    "identity_sources": [
      { "type": "yahoo",     "ref": "GTBIF quoteSummary", "checked_at": "2026-10-25" },
      { "type": "yaml_note", "ref": "—",                  "checked_at": "2026-10-25" }
    ]
  }
},
"instruments": {
  "ins_0101": { "ticker": "GTBIF",  "issuer_id": "iss_0042", "role": "operating_company", "leveraged": false, "ticker_history": [] },
  "ins_0102": { "ticker": "R9U2.F", "issuer_id": "iss_0042", "role": "operating_company", "leveraged": false, "ticker_history": [] },
  "ins_0300": { "ticker": "NRL.AX", "issuer_id": "iss_0077", "role": "operating_company", "leveraged": false,
                "ticker_history": [ { "ticker": "MRR.XA", "to": "2026-10-xx", "reason": "cambio de código" } ] }
}
```

- **IDs opacos** (`iss_NNNN`, `ins_NNNN`), asignados por el servidor e inmutables. El ticker es un atributo, no la identidad: si cambia, se añade a `ticker_history` y el instrumento conserva su ID y sus etiquetas.
- **`role`**: `operating_company` | `fund` (ETF/ETP; el emisor es el propio fondo) | `leveraged_product` (UCO, UVXY) | `index` (^XSP).
- **Las etiquetas económicas se asignan al emisor**, no al instrumento. Dos instrumentos de la misma empresa comparten etiquetas, pero precios, mercados, monedas y datos técnicos siguen siendo del instrumento. **Las posiciones nunca se fusionan**: siguen asociadas al ticker en sus sistemas.
- **`identity_status`**:
  - `verified`: dos fuentes independientes, una de ellas la bolsa, la empresa o el regulador;
  - `provisional`: una sola fuente, típicamente Yahoo;
  - `disputed`: fuentes contradictorias.

  Yahoo solo **nunca** da `verified`: su ISIN es poco fiable (para DPM.TO devuelve un código australiano). La identidad no se valida por tener etiquetas plausibles: son campos distintos y la UI muestra una marca «identidad sin verificar» mientras no esté `verified`.
- **Resolución determinista**, comprobada por el validador en cada escritura:
  1. cada `ticker` vigente es único entre instrumentos;
  2. un ticker de `ticker_history` no coincide con ningún ticker vigente ni con otro histórico en el mismo periodo;
  3. todo `issuer_id` referenciado existe;
  4. resolución: ticker vigente → instrumento; si no, el histórico cuyo periodo cubra la fecha consultada; si no hay ninguno → «sin clasificar», sin adivinar.
- **Los instrumentos no se mezclan en los conteos**: fondos, índices y productos apalancados aparecen en sus temáticas como **referencia** y nunca cuentan como empresas.
- **No se cambia ningún símbolo productivo** desde aquí. Si la línea B migra MRR.XA → NRL.AX, la línea A solo registra el cambio en `ticker_history`.

---

## 3. Asignaciones: exposición frente a navegación

```json
{
  "tag": "commodity:oil",
  "relation": "indirect",
  "intensity": "high",
  "nav_primary": true,
  "source": "assistant",
  "confidence": "medium",
  "review_status": "pending",
  "effective_from": null,
  "effective_to": null,
  "note": "VAL: perforación offshore; ingresos ligados al gasto de capital petrolero"
}
```

- **`relation`**: la naturaleza económica del vínculo.
  - `direct`: produce, posee o vende eso, u opera allí.
  - `indirect`: depende de ello sin producirlo (servicios, financiación, proveedores, proyectos minoritarios).
  - `narrative`: asociación de mercado sin ingresos significativos.
- **`intensity`** (solo `direct` e `indirect`):
  - `high`: es el factor que mueve la mayor parte del negocio o de la valoración (aproximadamente la mitad o más de ingresos, activos o valor, o el motor reconocido de la acción);
  - `low`: material pero minoritario.

  En `narrative`, `intensity` es nula.
- **`nav_primary`**: dónde se «aloja» el emisor en la vista de esa dimensión. **No es una medida de exposición.** Reglas que valida el servidor:
  1. como mucho una por emisor y dimensión;
  2. solo sobre una asignación `direct`, salvo que el emisor no tenga ninguna `direct` en esa dimensión: entonces se permite sobre una `indirect` y la UI la marca «navegación por vínculo indirecto»;
  3. nunca sobre una `narrative`.
- **Dimensiones descriptivas** (`industry`, `stage`, `asset_class`): no llevan `relation` ni `intensity`.
- **Default para métricas futuras de amplitud empresarial:** `role = operating_company` ∧ `relation = direct` ∧ `intensity = high` ∧ `review_status = confirmed`. Lo indirecto y lo narrativo nunca convierten a un emisor en componente principal de un tema.
- **Siembra desde la notación del Anexo A** (determinista): P → `direct/high`, S → `direct/low`, N → `narrative`, ★ → `nav_primary`. Las excepciones a esa regla están listadas expresamente en §7.

---

## 4. Histórico: registro de eventos como fuente de verdad

`docs/data/ticker_tags_events.jsonl` (append-only) es **la fuente de verdad**. `ticker_tags.json` es el estado actual materializado, que siempre se puede regenerar reproduciendo los eventos.

```json
{"seq": 812, "ts": "2026-10-26T10:12:03Z", "op": "update_assignment", "issuer_id": "iss_0042",
 "tag": "theme:cannabis", "before": {"intensity": "low"}, "after": {"intensity": "high"},
 "base_revision": 811, "actor": "dashboard"}
```

- **Operaciones:** `create_issuer`, `create_instrument`, `change_ticker`, `set_identity`, `assign`, `update_assignment` (relación, intensidad, `nav_primary`, fechas económicas), `review`, `retire_assignment`, `create_tag`, `retire_tag`.
- Cada evento guarda el estado anterior y el posterior. **Nada se borra ni se reescribe.**
- **Dos fechas distintas:** `ts` = cuándo se registró (lo pone el servidor); `effective_from`/`effective_to` = periodo económico al que se refiere (lo pones tú).
- **Pertenencia en una fecha `d`:**
  - **`point_in_time`** = estado obtenido reproduciendo **solo los eventos con `ts` ≤ fin de `d`**. Recoge lo que el sistema sabía entonces, incluidas asignaciones retiradas después, exposiciones cambiadas más tarde y tickers antiguos. Hay una variante «solo confirmadas a fecha `d`».
  - **`retrospective`** = estado actual filtrado por `effective_from`/`effective_to`. Sirve para explorar; **nunca** para demostrar capacidad predictiva.
- Todo resultado temático futuro guarda `membership_mode` y el `seq` usado.
- No se implementa ningún análisis histórico ni backtesting en el MVP; solo se garantiza que el registro lo permita.

---

## 5. Vocabulario: cambios respecto a v1

- **`industry → consumer`** se divide en:
  - **`consumer_discretionary`**: `internet_retail`, `autos`, `apparel_footwear`, `luxury`;
  - **`consumer_staples`**: `food_beverage`, `household_personal`, `food_retail`, `food_ingredients`.

  `meal_kits` pasa a `consumer_staples → food_retail` (HelloFresh: Yahoo lo clasifica como «Grocery Stores»), y `packaging` → `consumer_staples → food_ingredients` (Viscofan). Hoy, el grupo Consumer Staples del Portfolio nace con HFG.DE y VIS.MC; crece al añadir tickers.
- **`geo_exposure`**: añade `BA` (Bosnia y Herzegovina) bajo `europe`.
- **`stage`**: `explorer`, `developer`, `producer`, `mixed` (se retira `royalty`).
- **`role`** (en el instrumento, no es etiqueta): `operating_company`, `fund`, `leveraged_product`, `index`.
- El resto del vocabulario de v1 no cambia.

---

## 6. Interfaz (MVP)

- **Cabecera de grupo, solo recuentos descriptivos**: `Cannabis — 9 instrumentos · 8 empresas · 1 fondo · 0 sin clasificar`. «Empresas» = emisores distintos con `role = operating_company`. Fondos, índices y apalancados se cuentan aparte. **No hay «x de y» ni porcentajes** hasta que exista una métrica con numerador y denominador definidos.
- **Marcas en las filas:**
  - rol (`fondo`, `índice`, `apalancado`), con los no-empresa como fila de referencia al final del grupo;
  - `indirecto` / `narrativo` en la asignación por la que la fila está en el grupo;
  - «identidad sin verificar»;
  - «↻ también en…».
- **Filtros por defecto:** muestra `direct` e `indirect`; `narrative` se activa con un interruptor. Interruptor «solo confirmadas».
- **Resto** como en v1: «Agrupar por», grupos plegables, misma tabla y ordenación, búsqueda, edición desde el modal del ticker y totales globales sobre instrumentos únicos.

---

## 7. Siembra: reglas y excepciones

- **Cuarentena de identidad.** Los emisores señalados en la línea B se siembran con `identity_status = provisional` y **sin usar** nombre, tema ni subtema de `universe.json`: VAL, SLP.L, DMX.V, SSV.V, PNPN.V, DPM.TO, MRR.XA, GLEN.L, SMR.AX, AFM.V, y todos los que tienen región por defecto `US`. Su nombre sale de Yahoo, también provisional.
- **Excepciones a la notación del Anexo A:**

| Emisor | Asignación | Siembra |
|---|---|---|
| VAL | commodity:oil | `indirect / high`, `nav_primary` (no tiene ninguna `direct` en commodity) |
| TTI | commodity:oil | `indirect / high`, `nav_primary`; lithium → `narrative` |
| GLNG | geo_exposure:AR | `direct / low`, sin `nav_primary`; theme:vaca_muerta → `indirect / low`, sin `nav_primary`; navegación geográfica en `global` |
| BUR | geo_exposure:AR | `narrative` (pleito de YPF); `global` → `direct / high`, `nav_primary` |
| PAM, TGS | theme:vaca_muerta | `direct / low` |
| CORZ | theme:bitcoin | `direct / low` |
| KOS | commodity:lng | `direct / low` |
| ETFs, índice, apalancados | todas | sobre el emisor-fondo; `role` según §2; nunca cuentan como empresas |

- **DPM.TO (DPM Metals, ex Dundee; compró Adriatic Metals en 2025):** commodity gold `direct/high` ★, copper `direct/low`, silver `direct/low`, zinc `direct/low`, lead `direct/low`; geo BG `direct/high` ★, BA `direct/low`, RS `direct/low`, EC `direct/low`; confianza **media**, pendiente de comprobar el reparto vigente de activos. **No asumo** que Bulgaria y Serbia sean toda su exposición.
- **MRR.XA / NRL.AX:** el instrumento se siembra con el ticker vigente en el Portfolio (`MRR.XA`) e `identity_status = provisional`. Si la línea B migra a `NRL.AX`, se registra con `change_ticker`. Hecho comprobado: Yahoo da el mismo emisor en `MRR.XA` (Cboe AU), `NRL.AX` (ASX, histórico desde 2011) y `MRR.AX` (código antiguo, serie truncada).
- `stage` se retira de FRU.TO y VNOM (royalties); su `industry` ya lo recoge.

---

## 8. Persistencia, concurrencia y recuperación

**Un solo escritor** (elegido frente a coordinar varios):
- Las escrituras solo se habilitan si el nombre de la máquina coincide con `TICKER_TAGS_WRITER_HOST` del `.env`. En cualquier otra máquina la API responde **403** y la página indica «modo lectura en esta máquina».
- **Restricción documentada:** el repo está en Dropbox, y la otra máquina puede ver un estado con retraso; no puede escribir.
- Al arrancar y antes de cada escritura, el servidor busca copias en conflicto de Dropbox (`*conflicted copy*`, `*copia en conflicto*`) de los dos ficheros. Si existe alguna, bloquea la escritura y avisa.

**Cada escritura**, con un cerrojo interno del proceso:
1. validar contra el estado actual y su `base_revision` (si no coincide → 409);
2. **añadir el evento al registro y forzarlo a disco** (`fsync`);
3. escribir `ticker_tags.json` de forma atómica (temporal → `fsync` → `rename`), con `revision = seq`;
4. responder.

**Recuperación** (al arrancar y antes de cada escritura):

| Situación | Qué pasa |
|---|---|
| `revision` = último `seq` | Correcto. |
| JSON por detrás del registro (fallo entre 2 y 3) | Se regenera reproduciendo los eventos y se anota la recuperación. |
| Última línea del registro truncada (fallo durante 2) | Se descarta: nunca se confirmó al cliente. |
| JSON por delante del registro, o la reproducción no coincide con el JSON | Solo lectura + aviso. No debería ocurrir; si ocurre, no se intenta arreglar a ciegas. |

Invariante comprobable: `replay(eventos) == ticker_tags.json`. Lo verifica un test y una ruta de estado.

**Publicación** (función propia; **no** reutiliza `gitCommitAndPushWithRetry`, ver hallazgo abajo):
1. `git commit --only -m "…" -- docs/data/ticker_tags.json docs/data/ticker_tags_events.jsonl`. Solo entran esos dos ficheros, aunque haya otros cambios preparados o sin preparar.
2. `git push`. Si lo rechazan: `git fetch` + `git rebase --autostash origin/master` y reintento.
3. **Conflicto** en estos ficheros → abortar el rebase, conservar el commit local y devolver el error a la página. Como solo escribe una máquina, un conflicto aquí indica una anomalía.
4. **Fallo de red** → el commit queda local; la página muestra «1 commit sin publicar» y un botón de reintento.
5. La ruta devuelve el resultado real a la UI, no solo al log del servidor.

**Hallazgo en el helper actual `gitCommitAndPushWithRetry`** (lo usan Situaciones Especiales, el universo y `stock-config`):
- hace `git commit -m` sin rutas, así que **arrastra cualquier otro fichero que estuviera preparado**;
- hace `git rebase` sin `--autostash`, así que **con el árbol sucio** (por ejemplo, `portfolio.json` modificado, que es lo habitual) el rebase falla y el push no se completa. Ese fallo solo queda en la consola del servidor.

No lo corrijo dentro de la línea A. Propongo un cambio pequeño y separado (decisión X1).

---

## 9. Pruebas

Los arneses se construyen y pasan **antes** de cualquier cambio funcional en `server.js` o `portfolio.html`, y **se quedan en la suite**.

| ID | Qué | Detalle |
|---|---|---|
| I1-I5 | Invariancia de Flow Python, Flow JS, Sol, PCS y carteras con reconstrucción local | Como v1: datos congelados de un commit fijo, sin red, tres escenarios (sin etiquetas, siembra completa, mutaciones). Para PCS se usa el arnés ya validado en la línea B (149/149 exacto). Las fuentes de no determinismo (fecha de hoy, marcas de tiempo, orden de diccionarios) se fijan o se excluyen explícitamente de la comparación. |
| I6 | Carteras con red | Detector de lecturas + invariancia de entradas (hashes). |
| I7 | Estático | `grep` con lista blanca. |
| F1 | Validación | Entradas inválidas → 400/409 sin escribir. |
| F2 | Fusión de la siembra | Lo confirmado, rechazado y manual queda intacto. |
| F3 | Recuperación | Fallo simulado entre el paso 2 y el 3, línea truncada, JSON adelantado. |
| F4 | Invariante | `replay == JSON` tras cada operación de una secuencia aleatoria. |
| F5 | Recuentos | Instrumentos, empresas y fondos; R9U2.F/GTBIF = 1 empresa; ETF fuera de «empresas». |
| F6 | UI | Edge headless; `portfolio.json` byte a byte igual; cero errores de consola. |
| F7 | Point-in-time | Asignar → confirmar → cambiar intensidad → retirar; consultar fechas intermedias reproduce cada estado exacto. Contraste con el modo retrospectivo. |
| F8 | Identidad | Ticker duplicado, histórico solapado, emisor inexistente, cambio de ticker que conserva etiquetas → validación correcta. |
| F9 | Publicación | Repo de prueba con otro fichero preparado y `portfolio.json` sucio: el commit solo contiene los dos ficheros; rechazo y rebase; conflicto devuelto a la UI; red caída → commit local pendiente. |
| F10 | Escritor único | Nombre de máquina distinto → 403; copia en conflicto presente → solo lectura. |

**Permanencia:** `scripts/run_tags_tests.sh` ejecuta toda la suite en local. Propongo además un workflow ligero `tags-isolation.yml`, en cada push a `master`, que ejecute I1-I7 con el fixture fijado (decisión X2). No toca `market-update.yml`.

---

## 10. Archivos (Fases 1 y 2)

**Nuevos:**
- `shared/ticker-tags-lib.js` (esquema, validación, reproducción de eventos, resolución de identidad, agrupación, recuentos);
- `docs/data/ticker_tags.json` y `docs/data/ticker_tags_events.jsonl`;
- `docs/data/ticker_yahoo_meta.json` y `scripts/fetch_yahoo_meta.py`;
- `scripts/seed_ticker_tags.js` → `docs/analysis/ticker_tags_review.md`;
- `scripts/test_ticker_tags_lib.js`, `scripts/test_tags_invariance.{py,js}`, `scripts/run_tags_tests.sh`;
- `tests/fixtures/tags_invariance/`;
- `research/pcs_universe_sim_b/` (el arnés de PCS de la línea B, reutilizado en I4).

**Modificados:** `server.js` (rutas de etiquetas + publicación propia), `portfolio.html`, `CLAUDE.md`, `.env.example` (`TICKER_TAGS_WRITER_HOST`).

**No tocados:** los mismos de v1. El posible workflow de X2 sería un fichero nuevo, sin modificar los existentes.

---

## 11. Orden propuesto

1. **Línea B, primero, en su propia rama:**
   1. convertir el arnés de `research/pcs_universe_sim_b/` en test de regresión;
   2. aplicar las correcciones aprobadas (BD1-BD6);
   3. validador;
   4. cierre de R1/R2;
   5. comparar el primer `ai_candidates.json` real con la simulación.
2. **A-2c:** arneses de invariancia, con el fixture fijado en un commit **posterior** a la línea B, verdes sobre el código sin cambios.
3. **A-1a/1b:** vocabulario y hechos de Yahoo.
4. **A-1c:** siembra e informe de dudosos; **A-1d**, tu revisión, empezando por los emisores con identidad provisional.
5. **A-2a:** librería y rutas (escritor único, registro de eventos, recuperación, publicación) con F1-F4 y F7-F10.
6. **A-2b:** interfaz con F5-F6; volver a pasar toda la suite.
7. Validación final del alcance contigo antes de dar por desplegado el MVP.

---

## 12. Decisiones nuevas

| ID | Decisión | Propuesta |
|---|---|---|
| X1 | Corregir aparte los dos fallos de `gitCommitAndPushWithRetry` (commit con rutas explícitas + `--autostash`) | Sí, en un cambio pequeño e independiente, con su propia prueba. |
| X2 | Workflow `tags-isolation.yml` para que los tests de aislamiento corran en cada push | Sí. |
| X3 | ¿Qué máquina es la escritora (`TICKER_TAGS_WRITER_HOST`)? | La tuya habitual; dime cuál. |

Las decisiones de la línea B (BD1-BD6) están en su informe, §8.

---

## Anexo A — Propuesta para los 130 tickers

**Todo `review_status: pending`, `source: assistant`.** La conversión de esta notación a `relation`/`intensity`/`nav_primary` y sus excepciones están en §3 y §7; esas reglas prevalecen sobre cualquier celda de este anexo.

Leyenda:
- Exposición: **P** = primary, **S** = secondary, **N** = narrative. **★** = grupo principal de la dimensión.
- Confianza (Conf.): **A** = alta, **M** = media, **B** = baja.
- Etapa: exp = explorer, dev = developer, prod = producer, mixed = activos en varias etapas.
- Fuente de los hechos: resumen y sector/industria de Yahoo (2026-10-25) más conocimiento general. Donde no tengo datos fiables, la confianza es baja.

### Cartera

| Ticker | Empresa | industry | commodity | theme | geo_exposure | stage | Conf. | Nota |
|---|---|---|---|---|---|---|---|---|
| FDR.AX | Finder Energy | oil_gas_ep | oil P★, natgas S | — | AU P★, GB S | exp | M | NW Shelf + UK |
| EOS.AX | Electro Optic Systems | aerospace_defense | — | defense P★, drones S, space S | AU P★ | — | M | antidrones, láser, seguimiento de satélites |
| MLX.AX | Metals X | mining_tin | tin P★ | critical_metals S | AU P★ | prod | A | Renison (50 %) |
| R9U2.F | Green Thumb (Fráncfort) | cannabis_mso | — | cannabis P★ | US P★ | — | A | **mismo emisor que GTBIF** (instrumento distinto) |
| GSP.MI | Gas Plus | oil_gas_ep | natgas P★ | — | IT P★ | prod | A | |
| HFG.DE | HelloFresh | food_retail (consumer_staples) | — | — | north_america P★, europe S | — | M | ingresos sobre todo en Norteamérica, revisar |
| ASM.AS | ASM International | semi_equipment | — | ai_infrastructure S | global P★ | — | A | |
| FXPO.L | Ferrexpo | mining_iron_ore | iron_ore P★ | — | UA P★ | prod | A | datos de precio en cuarentena (escala GBX) |
| SLP.L | Sylvania Platinum | mining_pgm | pgm P★, chrome S | — | ZA P★ | prod | A | |
| KIST.L | Kistos | oil_gas_ep | natgas P★ | — | GB P★, NL S, NO S | prod | A | |
| SEDANA.ST | Sedana Medical | medtech | — | — | europe P★ | — | A | |
| JD | JD.com | internet_retail | — | — | CN P★ | — | A | |
| BABA | Alibaba | internet_retail | — | ai_infrastructure S | CN P★ | — | A | Alibaba Cloud |
| AFM.V | Alphamin | mining_tin | tin P★ | critical_metals S | CD P★ | prod | A | domicilio en Mauricio |
| DMX.V | District Metals | mining_polymetallic | uranium P★, vanadium S, molybdenum S | nuclear S | SE P★ | exp | M | Viken (Suecia) |
| VAL | Valaris | offshore_drilling | oil S★ | — | global P★ | — | A | perforación offshore (exposición indirecta al crudo) |
| BNKR.TO | Bunker Hill | mining_polymetallic | silver P★, zinc S, lead S | — | US P★ | dev | A | Silver Valley, Idaho |
| UCO | ProShares Ultra Crude | — (asset_class commodity) | oil P★ | — | — | — | A | ETF, `leveraged` |
| QQQ | Invesco QQQ | — (asset_class equity_index) | — | — | US P★ | — | A | ETF, referencia |
| VLE.TO | Valeura | oil_gas_ep | oil P★, natgas S | — | TH P★, TR S | prod | A | |
| TNZ.TO | Tenaz | oil_gas_ep | natgas P★, oil S | — | NL P★, CA S | prod | A | |
| UVXY | ProShares Ultra VIX | — (asset_class volatility) | — | — | — | — | A | ETF, `leveraged` |
| BTCC-B.TO | Purpose Bitcoin ETF | — (asset_class crypto) | — | bitcoin P★ | — | — | A | ETF |
| ROOT | Root | insurance | — | — | US P★ | — | A | insurtech |
| SE | Sea Ltd | internet_retail | — | — | asia_pacific P★, BR S | — | M | Shopee/Garena/fintech |
| AAG.V | Aftermath Silver | mining_silver | silver P★, copper S, manganese S | — | PE P★, CL S | exp | M | Berenguela |
| GRSL.V | GR Silver | mining_silver | silver P★, gold S | — | MX P★ | exp | B | Yahoo: «sin operaciones significativas», revisar |
| EXK | Endeavour Silver | mining_silver | silver P★, gold S | — | MX P★ | prod | A | |
| COIN | Coinbase | crypto_exchange | — | crypto P★, bitcoin S | US P★ | — | A | |
| CORZ | Core Scientific | data_centers | — | ai_infrastructure P★, bitcoin S | US P★ | — | M | colocación IA + minería de bitcoin |
| DPM.TO | DPM Metals (ex Dundee) | mining_gold | gold P★, copper S, silver S, zinc S, lead S | — | BG P★, BA S, RS S, EC S | mixed | M | ver §7; Vareš (BA) tras comprar Adriatic |
| QXO | QXO | building_products_distribution | — | — | north_america P★ | — | A | |
| GDXJ | VanEck Junior Gold Miners | mining_gold (asset_class equity_sector) | gold P★, silver S | — | global P★ | — | A | ETF, referencia del grupo |
| AG | First Majestic | mining_silver | silver P★, gold S | — | MX P★ | prod | A | |
| TDOC | Teladoc | telehealth | — | — | US P★ | — | A | |
| NBIS | Nebius | cloud_ai_infrastructure | — | ai_infrastructure P★ | global P★ | — | A | |
| ASTS | AST SpaceMobile | communication_equipment | — | space P★, defense N | US P★ | — | M | |
| VFF | Village Farms | agriculture | — | cannabis P★ | CA P★, US S | — | M | invernaderos + cannabis |
| HIMS | Hims & Hers | telehealth | — | glp1_obesity N | US P★ | — | M | |
| III.TO | Imperial Metals | mining_copper | copper P★, gold S | — | CA P★ | prod | A | |
| OSCR | Oscar Health | managed_care | — | — | US P★ | — | A | |
| AWX.V | ArcWest | mining_copper | copper P★, gold S | — | CA P★ | exp | M | Todd Creek, BC |
| SLS.TO | Solaris Resources | mining_copper | copper P★, molybdenum S, gold S | — | EC P★ | dev | M | Warintza |
| WRN.TO | Western Copper & Gold | mining_copper | copper P★, gold S, molybdenum S | — | CA P★ | dev | A | Casino, Yukon |
| USAU | U.S. Gold | mining_gold | gold P★, copper S | — | US P★ | dev | M | CK Gold, Wyoming |
| VGZ | Vista Gold | mining_gold | gold P★ | — | AU P★ | dev | A | Mt Todd |
| PNPN.V | Power Metallic | mining_polymetallic | copper P★, nickel S, pgm S | critical_metals S | CA P★, CL S | exp | B | revisar qué metal es el principal |
| IE | Ivanhoe Electric | mining_copper | copper P★ | — | US P★ | dev | A | Santa Cruz, Arizona |
| RCAT | Red Cat | aerospace_defense | — | drones P★, defense S | US P★ | — | A | |
| BOGO.V | Borealis Mining | mining_gold | gold P★, silver S | — | US P★ | dev | M | Nevada |
| EOSE | Eos Energy | electrical_equipment | — | electrification P★ | US P★ | — | A | baterías de zinc |
| ASPI | ASP Isotopes | specialty_chemicals | — | nuclear P★ | ZA P★, US S | — | M | isótopos médicos y HALEU |
| MSTR | Strategy | software | — | bitcoin P★ | US P★ | — | A | Yahoo dice software; la exposición es bitcoin |
| SSV.V | Southern Silver | mining_silver | silver P★, zinc S, lead S | — | MX P★ | exp | A | Cerro Las Minitas |
| SASK.V | Atha Energy | mining_uranium | uranium P★ | nuclear S | CA P★ | exp | A | Athabasca |
| LCX.V | Lycos Energy | oil_gas_ep | oil P★ | — | CA P★ | prod | A | crudo pesado |
| TTI | TETRA Technologies | oilfield_services | oil S★, lithium N | electrification N | US P★ | — | M | salmueras de bromo/litio |
| VIS.MC | Viscofan | food_ingredients (consumer_staples) | — | — | global P★ | — | A | tripas para embutidos |
| GTE | Gran Tierra | oil_gas_ep | oil P★ | — | CO P★, EC S, CA S | prod | A | |

### Cannabis

| Ticker | Empresa | industry | theme | geo | Conf. | Nota |
|---|---|---|---|---|---|---|
| CRON | Cronos | cannabis_lp | cannabis P★ | CA P★ | A | |
| MAPS | WM Technology | software | cannabis P★ | US P★ | A | |
| MSOS | AdvisorShares US Cannabis | cannabis_mso (asset_class equity_sector) | cannabis P★ | US P★ | A | ETF |
| GTBIF | Green Thumb | cannabis_mso | cannabis P★ | US P★ | A | emisor principal de R9U2.F |
| OGI | Organigram | cannabis_lp | cannabis P★ | CA P★ | A | |
| GLAS | Glass House | cannabis_mso | cannabis P★ | US P★ | A | California |
| TRLV | Trulieve | cannabis_mso | cannabis P★ | US P★ | A | |

### Petróleo

| Ticker | Empresa | industry | commodity | theme | geo | stage | Conf. |
|---|---|---|---|---|---|---|---|
| CVE | Cenovus | oil_gas_integrated | oil P★ | — | CA P★, US S | prod | A |
| SU | Suncor | oil_gas_integrated | oil P★ | — | CA P★ | prod | A |
| WCP.TO | Whitecap | oil_gas_ep | oil P★, natgas S | — | CA P★ | prod | A |
| FRU.TO | Freehold Royalties | oil_gas_royalties | oil P★, natgas S | — | CA P★, US S | — | A |
| VNOM | Viper Energy | oil_gas_royalties | oil P★ | — | US P★ | — | A |
| OXY | Occidental | oil_gas_ep | oil P★, natgas S | — | US P★ | prod | A |
| TLW.L | Tullow Oil | oil_gas_ep | oil P★ | — | GH P★ | prod | A |
| KOS | Kosmos | oil_gas_ep | oil P★, lng S | — | GH P★, US S | prod | M |

### Argentina

| Ticker | Empresa | industry | commodity | theme | geo | Conf. | Nota |
|---|---|---|---|---|---|---|---|
| SUPV | Supervielle | banks | — | — | AR P★ | A | |
| GGAL | Galicia | banks | — | — | AR P★ | A | |
| BBAR | BBVA Argentina | banks | — | — | AR P★ | A | |
| CRESY | Cresud | agriculture | — | — | AR P★, BR S | A | también inmobiliario (vía IRSA) |
| CEPU | Central Puerto | utilities_power | — | — | AR P★ | A | |
| YPF | YPF | oil_gas_integrated | oil P★, natgas S | vaca_muerta P★ | AR P★ | A | |
| VIST | Vista Energy | oil_gas_ep | oil P★ | vaca_muerta P★ | AR P★ | A | domicilio en México |
| PAM | Pampa Energía | utilities_power | natgas S | vaca_muerta S | AR P★ | A | electricidad + gas |
| IRS | IRSA | real_estate | — | — | AR P★ | A | |
| LOMA | Loma Negra | building_materials | — | — | AR P★ | A | |
| TGS | TGS | oil_gas_midstream | natgas P★ | vaca_muerta S | AR P★ | A | |
| GLNG | Golar LNG | lng_infrastructure | lng P★ | vaca_muerta S | global P★, AR S | M | FLNG en Argentina |
| BUR | Burford Capital | litigation_finance | — | — | global P★, AR N | M | pleito YPF |

### Opciones · Watchlist

| Ticker | Empresa | industry / asset_class | commodity | theme | geo | Conf. |
|---|---|---|---|---|---|---|
| TSLA | Tesla | autos | — | ev P★, musk_ecosystem P, robotics N, ai N | global P★ | M |
| SLV | iShares Silver Trust | asset_class commodity | silver P★ | — | — | A |
| TLT | iShares 20+ Treasury | asset_class bonds | — | — | US P★ | A |
| SPY | SPDR S&P 500 | asset_class equity_index | — | — | US P★ | A |
| ^XSP | Mini-SPX (índice) | asset_class equity_index | — | — | US P★ | A |
| URA | Global X Uranium | mining_uranium (asset_class equity_sector) | uranium P★ | nuclear P | global P★ | A |
| URI | United Rentals | equipment_rental | — | — | US P★ | A |

### Calidad/Growth · Value/Turnaround · Defensivo Pharma

| Ticker | Empresa | industry | theme | geo | Conf. |
|---|---|---|---|---|---|
| LLY | Eli Lilly | pharma | glp1_obesity P★ | global P★ | A |
| ISRG | Intuitive Surgical | medtech | robotics S | global P★ | A |
| SYK | Stryker | medtech | — | global P★ | A |
| TMO | Thermo Fisher | life_science_tools | — | global P★ | A |
| DHR | Danaher | life_science_tools | — | global P★ | A |
| BSX | Boston Scientific | medtech | — | global P★ | A |
| VRTX | Vertex | biotech | — | global P★ | A |
| PLTR | Palantir | software | ai_software P★, defense S | US P★ | A |
| UNH | UnitedHealth | managed_care | — | US P★ | A |
| HUM | Humana | managed_care | — | US P★ | A |
| CI | Cigna | managed_care | — | US P★ | A |
| CVS | CVS Health | managed_care | — | US P★ | A |
| NKE | Nike | apparel_footwear | — | global P★ | A |
| MOH.HM | LVMH (Hamburgo) | luxury | — | global P★ | A |
| JNJ | Johnson & Johnson | pharma | — | global P★ | A |
| MRK | Merck | pharma | — | global P★ | A |
| ABBV | AbbVie | pharma | — | global P★ | A |
| PFE | Pfizer | pharma | — | global P★ | A |
| SLS | SELLAS Life Sciences | biotech | — | US P★ | A |

### Semiconductores · Mineras · Carbón · LWS Ago

| Ticker | Empresa | industry | commodity | theme | geo | stage | Conf. | Nota |
|---|---|---|---|---|---|---|---|---|
| ACMR | ACM Research | semi_equipment | — | — | CN P★ | — | A | |
| MU | Micron | semiconductors | — | ai_infrastructure P★ | global P★ | — | A | |
| NVDA | NVIDIA | semiconductors | — | ai_infrastructure P★ | global P★ | — | A | |
| AMD | AMD | semiconductors | — | ai_infrastructure P★ | global P★ | — | A | |
| GLEN.L | Glencore | mining_diversified | copper P★, met_coal S, thermal_coal S, zinc S, nickel S, cobalt S | — | global P★ | prod | M | trading + minería |
| REG.V | Regulus | mining_copper | copper P★, gold S, silver S | — | PE P★ | exp | A | AntaKori |
| SLG.V | San Lorenzo Gold | mining_gold | gold P★, copper S | — | CL P★ | exp | M | Salvadora |
| MRR.XA | Northstone Resources (ex MinRex) | mining_gold | gold P★, silver S, copper S | — | RS P★ | exp | M | Tlamino (sur de Serbia); símbolo → BD2 de la línea B |
| GHM.AX | Golden Horse | mining_gold | gold P★ | — | AU P★ | exp | M | Western Australia |
| YAL.AX | Yancoal | mining_coal | thermal_coal P★, met_coal S | — | AU P★ | prod | A | |
| WHC.AX | Whitehaven | mining_coal | thermal_coal P★, met_coal S | — | AU P★ | prod | A | |
| SMR.AX | Stanmore | mining_coal | met_coal P★ | — | AU P★ | prod | A | |
| AMR | Alpha Metallurgical | mining_coal | met_coal P★ | — | US P★ | prod | A | |
| HCC | Warrior Met Coal | mining_coal | met_coal P★ | — | US P★ | prod | A | |
| ADS.DE | adidas | apparel_footwear | — | — | global P★ | — | A | |
| CMCSA | Comcast | telecom_media | — | — | US P★ | — | A | |
| FOUR | Shift4 | payments | — | — | US P★ | — | A | |

**Recuento:** 130 instrumentos, 118 empresas (R9U2.F y GTBIF = 1) y 11 no-empresa: 8 fondos (GDXJ, URA, MSOS, SLV, TLT, SPY, QQQ, BTCC-B.TO), 2 apalancados (UCO, UVXY) y 1 índice (^XSP). **Revisar primero:** los emisores con identidad provisional (§7) y los de confianza baja o media en metal o país (GRSL.V, PNPN.V, MRR.XA, HFG.DE, SE, DPM.TO, KOS).

**Grupos que nacen pequeños** (D6, solo cantidades): `musk_ecosystem` (1), `glp1_obesity` (2), `drones` (2), `space` (2-3), `robotics` (2), `mining_tin` (2), `mining_pgm` (1), `vaca_muerta` (5, ya con aviso de muestra pequeña).
