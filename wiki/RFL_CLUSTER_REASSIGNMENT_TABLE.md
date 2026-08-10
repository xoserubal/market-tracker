# RFL Cluster Reassignment Table

> Fase 1.2 del plan "Relative Flow Lab — Optimización v2". Generada
> escaneando el estado real de `shared/relative-ratio-registry.js`
> (commit `3d4f30b`, ver `backtest/config/rfl_current_state_frozen.yaml`),
> no un inventario recordado ni el aportado por el asesor externo — varias
> entradas de ese inventario no coincidían con el código real (ver
> "Correcciones respecto al plan / al asesor externo" más abajo).
>
> **Firmada el 2026-08-10.** Las 3 decisiones abiertas se resolvieron en
> conversación (ver sección final) — ya no bloquean el arranque de Fase 1.

## Correcciones respecto al plan / al asesor externo

Estas discrepancias se detectaron comparando el plan (y las 4 rondas de
respuestas del asesor externo) contra el registry real. Se listan aparte
porque, si se firmaran sin corregir, producirían IDs duplicados o ratios
inventados:

| Ratio | Lo que decía el plan/asesor | Lo que hay en el código real |
|---|---|---|
| `GDXJ/GDX` | "nuevo, Fase 2.1" | **Ya existe**, en vivo desde 2026-07-29 (`anticipation`, cluster METALS) |
| `SMH/IGV` | "nuevo, Fase 2.1" | **Ya existe**, en vivo desde 2026-07-29 (`rotation`, cluster SECTOR ROTATION) |
| `IWD/IWF` (Value/Growth) | "evaluar antes de incluir" (2.2) | **Ya existe y en vivo** desde 2026-07-29 (`rotation`, cluster STYLE/FACTOR) — no es candidato a evaluación previa, ya tiene ~2 semanas de datos reales corriendo |
| `XLK/SPY` "prominente" | "nuevo" | **Ya existe** como `sector_snapshot` — falta solo promoción visual, no cálculo |
| `DXY/GLD` | "ya existe — reubicar" | **No existe.** Documentado como pendiente desde julio. Es alta (fetch de ticker nuevo `DX-Y.NYB` + cálculo), no una reubicación |
| `FXI/EEM` | Incluido en el YAML de la ronda 4 sin marcar como nuevo | **No existe.** Documentado explícitamente como fuera de alcance en el rediseño de julio |
| `BTC-USD/GLD` | — | El ticker real es `BTC-USD/GC=F` (oro futuro), no `GLD` (ETF) |

## Tabla completa (45 ratios existentes)

| ID | Par | Type/cluster actual | Cluster propuesto | Sub-cat | Notas |
|---|---|---|---|---|---|
| hyg_spy | HYG/SPY | risk_appetite / RISK APPETITE | RISK-ON/OFF | crédito | cuenta en Risk Appetite Monitor hoy |
| xlu_xly | XLU/XLY | risk_appetite / RISK APPETITE | RISK-ON/OFF | positioning | cuenta en el monitor |
| splv_mtum | SPLV/MTUM | risk_appetite / RISK APPETITE | RISK-ON/OFF | vol/positioning | cuenta en el monitor |
| xly_xlp | XLY/XLP | risk_appetite / RISK APPETITE | RISK-ON/OFF | positioning | cuenta en el monitor |
| iwm_spy | IWM/SPY | risk_appetite / RISK APPETITE | RISK-ON/OFF | positioning | cuenta en el monitor |
| qqq_rsp | QQQ/RSP | risk_appetite / RISK APPETITE | RISK-ON/OFF | positioning | `contextual`, no cuenta en el monitor hoy |
| copper_gold | HG=F/GC=F | risk_appetite / RISK APPETITE | RISK-ON/OFF | positioning | se queda — el monitor sigue en /6 |
| xle_brent | XLE/BZ=F | anticipation / ENERGY | ANTICIPACIÓN | — | sin cambio semántico |
| gdx_gld | GDX/GLD | anticipation / METALS | ANTICIPACIÓN | — | sin cambio |
| gdxj_gdx | GDXJ/GDX | anticipation / METALS | ANTICIPACIÓN | — | **ya existe, no es Fase 2** |
| kre_xlf | KRE/XLF | anticipation / FINANCIALS | ANTICIPACIÓN | — | sin cambio |
| xop_xle | XOP/XLE | anticipation / ENERGY | ANTICIPACIÓN | — | sin cambio |
| silver_gold | SI=F/GC=F | anticipation / METALS | ANTICIPACIÓN | — | sin cambio |
| ura_urnm | URA/URNM | anticipation / URANIUM | ANTICIPACIÓN | — | sin cambio |
| hcc_btu | HCC/BTU | anticipation / COAL | ANTICIPACIÓN | — | sin cambio |
| amr_btu | AMR/BTU | anticipation / COAL | ANTICIPACIÓN | — | sin cambio |
| ccj_urnm | CCJ/URNM | anticipation / URANIUM | ANTICIPACIÓN | — | sin cambio |
| btc_gold | BTC-USD/GC=F | anticipation / CRYPTO | ANTICIPACIÓN | — | sin cambio (nota: par real usa GC=F, no GLD) |
| xlb_xle | XLB/XLE | rotation / ENERGY | ROTACIÓN | — | sin cambio |
| xlk_xlf | XLK/XLF | rotation / SECTOR ROTATION | ROTACIÓN | — | sin cambio |
| iwd_iwf | IWD/IWF | rotation / STYLE-FACTOR | ROTACIÓN | long_term | **ya existe, no evaluar como candidato nuevo** |
| smh_igv | SMH/IGV | rotation / SECTOR ROTATION | ROTACIÓN | — | **ya existe, no es Fase 2** |
| xle_xlk | XLE/XLK | rotation / SECTOR ROTATION | ROTACIÓN | — | sin cambio |
| hcc_xme | HCC/XME | rotation / COAL | ROTACIÓN | — | sin cambio |
| amr_xme | AMR/XME | rotation / COAL | ROTACIÓN | — | sin cambio |
| xlk_spy | XLK/SPY | sector_snapshot / SECTOR ROTATION | ROTACIÓN | — | promoción visual (ya existe, no se duplica) |
| eem_urth | EEM/URTH | regions / REGIONS | REGIONES | hacia_em | sin cambio |
| ewz_eem | EWZ/EEM | regions / REGIONS | REGIONES | dentro_em | sin cambio |
| argt_eem | ARGT/EEM | regions / REGIONS | REGIONES | dentro_em | sin cambio |
| ewj_eem | EWJ/EEM | regions / REGIONS | REGIONES | dentro_em | sin cambio |
| xlf_spy | XLF/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xlv_spy | XLV/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xly_spy | XLY/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xlp_spy | XLP/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xle_spy | XLE/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xli_spy | XLI/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xlb_spy | XLB/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xlre_spy | XLRE/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xlc_spy | XLC/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| xlu_spy | XLU/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | sin cambio |
| tlt_spy | TLT/SPY | sector_snapshot / SECTOR ROTATION | RISK-ON/OFF | duración | termómetro directo (refugio en duración), no BACKGROUND |
| gld_spy | GLD/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | solapa con otros termómetros, parsimonia |
| bil_spy | BIL/SPY | sector_snapshot / SECTOR ROTATION | BACKGROUND | — | flow_chg casi siempre pequeño, valor histórico/cosmético |
| urnm_urth | URNM/URTH | sector_snapshot / URANIUM | BACKGROUND | — | temático puro, no encaja en ningún tipo de pregunta de las 3 |
| xme_spy | XME/SPY | sector_snapshot / MATERIALS | BACKGROUND | — | análogo a los demás sector-vs-SPY |

## Ratios nuevos reales de Fase 2 (no los que decía el plan)

| Ratio | Cluster propuesto | Sub-cat | Nota |
|---|---|---|---|
| `HYG/LQD` | RISK-ON/OFF | crédito | nuevo de verdad |
| `VVIX/VIX` (`^VVIX`/`^VIX`) | RISK-ON/OFF | vol | probado en vivo 2026-08-10, 22 barras continuas — seguro |
| `USDJPY/Nikkei` (`JPY=X`/`^N225`) | REGIONES | fx_estructural | nuevo de verdad |
| `DXY/GLD` → `DX-Y.NYB/GC=F` | REGIONES | fx_estructural | nuevo de verdad, no reubicación — par decidido: `GC=F` (oro futuro), consistente con `copper_gold`/`silver_gold`/`btc_gold`, no con el ETF del bloque BACKGROUND |

## Ratios a evaluar por velocidad (Fase 2.2)

Ninguno — `IWD/IWF` ya está en producción (ver corrección arriba). El único
candidato real que queda pendiente de evaluar es:

- `IJS/IJT` (Small Value/Growth) — no existe todavía, sí es nuevo de verdad.

## Decisiones cerradas (firmadas 2026-08-10)

**1. `copper_gold` (HG=F/GC=F) — se queda en RISK-ON/OFF.**
Cuenta hoy como uno de los 6 ratios contables del Risk Appetite Monitor
(el denominador `/6` en el header es dinámico — cuenta los 7 ratios
`risk_appetite` menos `qqq_rsp`, marcado `contextual`). Moverlo a
ANTICIPACIÓN habría recalculado el monitor a `/5` sin ninguna evidencia
que lo justifique. Razón conceptual adicional: los demás miembros de
ANTICIPACIÓN comparten estructura "equity vs fundamental subyacente"
(XLE vs BZ=F, GDX vs GLD...) — Copper/Gold son dos commodities físicos
comparados entre sí, no encaja en esa estructura. Si en el futuro los
datos muestran que funciona mejor como señal de anticipación, se mueve
con evidencia, no por preferencia conceptual.

**2. Los 5 huérfanos — tratamiento diferenciado, no todos a BACKGROUND.**
- `TLT/SPY` → **RISK-ON/OFF**, subcategoría nueva `duración` (distinta de
  `crédito`: es lectura de tipos/refugio en duración, no de spread
  corporativo). Es un termómetro tan directo como `HYG/SPY` — no
  encajaba en el plan original por omisión, no por diseño.
- `GLD/SPY` → BACKGROUND (solapa con termómetros ya existentes, parsimonia).
- `BIL/SPY` → BACKGROUND (T-bills vs equity es risk-on/off puro en teoría,
  pero `flow_chg` va a ser casi siempre ruido pequeño dominado por SPY —
  valor histórico/cosmético, no operativo).
- `URNM/URTH`, `XME/SPY` → BACKGROUND (temáticos puros, no responden a
  ninguna de las 3 preguntas estructurales del sistema).

**3. `DXY/GLD` → `DX-Y.NYB/GC=F`.**
Consistencia con los vecinos reales del cluster REGIONES/fx_estructural
(comparación índice-dólar vs refugio-metal, análoga a yen-vs-Nikkei) y
con la familia de ratios que ya usan oro-futuro como denominador
(`copper_gold`, `silver_gold`, `btc_gold`) — no con el bloque BACKGROUND,
que es un cluster distinto y su convención no aplica aquí.

## Ratios eliminados

Ninguno. Sin cambios respecto al criterio ya acordado (degradar a
BACKGROUND, no eliminar).

---

**Tabla firmada y congelada.** Fase 1 lista para arrancar: reorganización
de clusters en `shared/relative-ratio-registry.js` (campo `cluster`/nuevo
campo de taxonomía, sin YAML nuevo — ver justificación de arquitectura en
el hilo de decisiones previas) + reordenación visual en `relative.html`
según lo cerrado en esta tabla. Persistencia diaria de `flowChange` por
ratio en `state.json` (bloqueante para Fases 3+, acordado como parte de
Fase 1) se implementa como paso separado dentro de la misma fase.
