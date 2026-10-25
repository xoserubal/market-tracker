# Línea B — Escenario B1 definitivo

**Estado:** fusionado en `master` (merge `43d9a0a2`, 2026-10-25; commit de la corrección `ccf68c19`). 54 pruebas superadas sobre el resultado fusionado.
**Fecha:** 2026-10-25.
**Sustituye a** los apartados B1/B2 de `wiki/AUDITORIA_UNIVERSE_LINEA_B.md` (que siguen siendo válidos para el diagnóstico). Las cifras de aquel B1 provisional ya no valen.
**Reproducible:** `py -3 scripts/test_universe_integrity.py` en la rama (54 tests, sin red).

---

## 1. Qué contiene la corrección

Tus decisiones aplicadas:

| Decisión | Aplicada como |
|---|---|
| BD1 | `GOLD` retirado. `B` (Barrick Mining) añadido como instrumento **nuevo**: sin historial de GOLD, sin tocar los picks históricos de GOLD (el 2026-09-13 lo seleccionaron CFL y MIMO_SHADOW con PCS 83,8; siguen como se registraron). |
| BD2 | `NRL.AX` como referencia. Es **instrumento distinto** de `MRR.XA` (mercados distintos: ASX frente a Cboe AU), mismo emisor, sin concatenar series. Comprobado: 1 474 días solapados, ratio de precio medio 1,003 (desviación 0,04, por el tamaño de tick a 1,2-1,7 céntimos); liquidez en ASX ≈ 2× la de Cboe (≈19 k frente a ≈9 k dólares diarios). |
| BD3 | `DMX.V` → tema `uranium_nuclear`, subtema `uranium_exploration`. La clasificación polimetálica secundaria no cabe en `universe.json` (un tema por ticker); queda para la línea A. |
| BD4 | Fail-closed para tickers nuevos (`classification_status="pending"`), con motivo propio `ineligible_reason="unclassified"`, sin usar `tradable=false`. Los registros históricos no cambian de elegibilidad. |
| BD5 | Interpretativas **no** aplicadas (FCX, RIO, carbón térmico, NKE, EOS.AX…). |
| BD6 | Las correcciones objetivas pueden cruzar umbrales. |

Cambios de **datos** (los 3 ficheros fuente):
- `individual_stocks.yaml`: −ASMI, −YAN.AX, −LLY (duplicado de Defensive), GOLD→B, MRR.XA→NRL.AX.
- `universe.json`: 147 registros (149 − 4 retirados + 2 nuevos; el duplicado de LLY ya no existe).

Cambios de **código** (aditivos):
- `sync_universe.py`: tickers nuevos sin clasificar.
- `pcs_calculator.py`: `eligible` además exige no estar `pending`, y se añade el campo `ineligible_reason`. El PCS numérico no cambia.

---

## 2. Decisión de proxies (precisión 1)

**Regla aplicada:** `theme_proxy` solo si el ETF **contiene a la empresa** o su precio responde al **mismo driver económico**. Clasificar bien la empresa (objetivo) y asignarle un proxy (hipótesis de modelado) son cosas distintas. `macro_proxy` no lo lee ningún motor (verificado: solo aparece en `sync_universe.py`), así que no se discutió.

| Ticker | Clasificación (objetiva) | Proxy | Motivo |
|---|---|---|---|
| TK | oil_gas / tankers | **ninguno** | Tarifas de fletes de petroleros ≠ precio de empresas energéticas. |
| TTI | oil_gas / oilfield_services | **ninguno** | No está en XLE y buena parte del negocio es salmueras y agua; mantengo la ausencia por prudencia. |
| SLB | oil_gas / oilfield_services | XLE | Es componente de XLE. |
| VAL | oil_gas / offshore_drilling | XLE (sin cambio) | El driver (gasto de capital petrolero) coincide; no se toca porque es una decisión de modelado previa, no un error de identidad. |
| GS | us_cyclical | XLF | Es componente de XLF (antes XLI, claramente incorrecto). |
| MOS | us_cyclical / fertilizers | XLB | Componente de XLB. |
| TECK, ASCU.TO | commodities_copper | COPX | ETF de mineras de cobre (no está en las señales de rotación, así que en la práctica actúa la media del tema). |
| KTOS | defense_space | XAR | ETF de defensa. |
| SAIA | us_cyclical | XLI | Sector industrial. |
| GLEN.L, AFM.V, SLP.L, SMR.AX | diversified_miners / tin / pgm / met_coal | **ninguno** | No hay un proxy apropiado entre las señales disponibles. |
| DMX.V | uranium_nuclear | URA | Mismo criterio que SASK.V. |
| B | silver_gold_miners / gold_miners | GDX | Mismo criterio que USAU y VGZ. |

**Hallazgo que conviene decidir:** el mecanismo de «sin proxy» **no es neutral**. Con `theme_proxy` vacío, el PCS (componente B) usa el promedio de rendimiento relativo del *tema*. TK queda en `oil_gas` y recibe 18 puntos por lo que hacen las petroleras, no por los fletes. Sensibilidad (PCS final):

| Variante | TK | TTI | SLB |
|---|---|---|---|
| Publicado hoy | 56,2 | 26,5 | 41,8 |
| **B1 definitivo** (TK y TTI sin proxy; SLB con XLE) | **71,2** | **41,5** | **62,8** |
| TK y TTI con XLE | 77,2 | 47,5 | 62,8 |
| TK sin proxy **y sin tema** (B = 10 fijo) | 63,2 | 41,5 | 62,8 |
| SLB también sin proxy | 71,2 | 41,5 | 56,8 |

Si quieres que TK no reciba ninguna señal temática, la opción es dejar también el tema vacío, pero eso lo saca de la concentración `oil_gas` y es otra decisión de clasificación. No lo he hecho.

---

## 3. Resultados del escenario definitivo

Datos congelados del commit `e728e75d`. El código de PCS reproduce **149/149** el `ai_candidates.json` publicado antes de cambiar nada (test T1).

### Tickers retirados y nuevos

| | Ticker | PCS / estado |
|---|---|---|
| Retirado | GOLD | 22,0, **elegible** (era Gold.com) |
| Retirado | ASMI | 37,0, no elegible (sin datos) |
| Retirado | YAN.AX | 45,0, no elegible |
| Retirado | MRR.XA | sustituido por NRL.AX |
| Nuevo | B | **PCS 27,0, elegible** (calculado con el scanner real; sin datos del scanner es `no_signal_data`, no `unclassified`). |
| Nuevo | NRL.AX | **PCS 49,2, elegible.** Su B (18) también viene de la media del tema. |

Hasta el primer run, B y NRL.AX **no son elegibles** (el scanner aún no los ha procesado): el universo pasa de 143 a 141 elegibles, y a 143 en cuanto el scanner los incluya. Ninguno cruza umbrales de selección y su entrada **no cambia el PCS de ningún compañero**. Verificación: ejecuté el scanner real (`scan_stocks`) para ambos más tres controles publicados (USAU, VGZ, MRR.XA), que reproducen exactamente los valores de `e728e75d`.

### Cambios de PCS (18 registros cambian; 14 en PCS)

| Ticker | PCS antes → después | Δ | Origen |
|---|---|---|---|
| GS | 27,8 → 43,8 | +16,0 | corrección propia (proxy) |
| MOS | 22,8 → 38,8 | +16,0 | corrección propia |
| AFM.V | 22,0 → 37,0 | +15,0 | corrección propia |
| TK | 56,2 → 71,2 | +15,0 | corrección propia · **cruza ER (68) y MTB (62)** |
| TTI | 26,5 → 41,5 | +15,0 | corrección propia |
| SLB | 41,8 → 62,8 | +21,0 | corrección propia · **cruza el suelo de 62** |
| SMR.AX | 46,0 → 56,0 | +10,0 | corrección propia |
| GLEN.L | 37,0 → 45,0 | +8,0 | corrección propia |
| TECK, ASCU.TO, KTOS | +1,0 cada uno | +1,0 | corrección propia |
| IE, III.TO, REG.V | −4,0 cada uno | −4,0 | **segundo orden**: sin tocar su registro, empeora la media del tema cobre |
| VAL, SLP.L, DMX.V, SAIA | sin cambio de PCS | 0 | cambian tema o subtema, no el PCS |

### Cruces de umbrales de selección

| Umbral | Antes | Después |
|---|---|---|
| ≥ 82 (entrada HC) | 1 | 1 |
| ≥ 75 (CFL) | 16 | 16 (**TK queda en 71,2**, ya no entra aquí) |
| ≥ 68 (ER) | 28 | 29 (+TK) |
| ≥ 62 (MTB / suelo) | 34 | 36 (+TK, +SLB) |

### Efectos de segundo orden

- IE, III.TO y REG.V pierden 4 puntos (media del tema cobre). Es el único canal de segundo orden con efecto en PCS.
- La entrada de B y NRL.AX (con sus retornos estimados) **no mueve el PCS de ningún otro ticker**: las medias de tema cambian, pero ningún compañero cambia de tramo.

### Concentración temática (campo que ve la IA)

Cambia para 33 tickers. Lo más visible: el riesgo del tema cobre baja de «alto» a «bajo»; `commodities_metals` sube de «medio» a «alto» (GLEN.L, MLX.AX, PNPN.V, carbón…); DMX.V deja de contar como plata. Detalle en `tests/fixtures/universe_integrity/golden_b1.json`.

### Posiciones abiertas afectadas (estado congelado)

- **HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS, EARLY_ROTATION, MACRO_THEMATIC_BENEFICIARIES y CAVA_MACRO: ninguna.**
- Carteras sombra, solo etiqueta de tema o subtema: VAL (MIMO_SHADOW, SCREENER_SHADOW, MACD_COMBO_CD/SD), SLP.L (RANKING_SHADOW_EXPERIMENTAL, SCREENER_SHADOW).
- Carteras sombra con cambio de PCS: SMR.AX +10 (SCREENER_SHADOW, MACD_COMBO_CD/SD), AFM.V +15 (MACD_COMBO_SD), REG.V −4 (SCREENER_SHADOW).

**Los logs históricos no se reescriben.** `shadow_picks.jsonl`, `ai_picks.json` y el resto conservan lo registrado, incluidos los picks de GOLD de septiembre. La corrección es prospectiva.

---

## 4. Pruebas de regresión

`scripts/test_universe_integrity.py`, 54 tests (T1-T7). Se probó que **detecta** regresiones reintroduciendo cuatro errores a mano, todos atrapados:

| Error reintroducido | Test que falla |
|---|---|
| TK vuelve a `us_cyclical` / XLI | T3 (campos aprobados) |
| GOLD reaparece en `universe.json` | T3 (símbolos retirados, 1:1 con el YAML, B no es GOLD) y T6 |
| Se quita el gate de elegibilidad | T5 |
| La sincronización vuelve a heredar defaults | T4 (tres tests) |

Limitación conocida: el golden (T2) usa una copia **congelada** del universo corregido, no el fichero vivo, porque el universo cambia a diario. La protección del fichero real son los campos aprobados de T3. Si alguien edita a mano otro campo de uno de esos tickers, T2 no lo detecta.

---

## 5. Estado tras el merge

- Fusionado con `--no-ff` (revertible con `git revert -m 1 43d9a0a2`) y publicado. Los registros históricos (`shadow_picks.jsonl`, `ai_picks.json`, logs de picks) no se han modificado; la corrección es prospectiva.
- El run del pipeline anterior al merge (2026-10-25 13:16 UTC) sirve de línea base real para comparar con el primer run posterior (ver `wiki/VERIFICACION_B_POSTMERGE.md`).
- `MRR.XA` sigue en `portfolio.json`: no se ha cambiado ningún símbolo productivo del Portfolio Tracker.
- Con la política fail-closed, un ticker nuevo añadido desde el botón «añadir a AI Picks Lab» entra como `pending` y no es elegible hasta revisarlo (procedimiento en `CLAUDE.md`).

## 6. Fuera de esta corrección (decidido)

Interpretativas (BD5); validador `validate_universe.py`; el modal «añadir al universo» sigue con región `US` por defecto; incidencia de concentración (documento aparte).
