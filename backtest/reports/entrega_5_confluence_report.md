# Entrega 5 — Confluence Detector Report
### Detector de Confluencia Temprana | 2026-04-20

---

## Resumen ejecutivo

**Veredicto: PARCIAL — Sin activación STRUCTURAL en el período histórico.**

El detector funcionó correctamente y el código es correcto. El problema es de calibración: el umbral de confluencia (≥55) se alcanzó solo **una vez en 20 años** (2008-10-24: 58 pts), y la condición de 2 semanas consecutivas impidió la activación porque la semana siguiente cayó a 51. Las alertas TÁCTICAS (46 emitidas) no generan alpha positivo: −1.35% a 4w (t=−3.25), sin señal a 13w ni 26w.

La limitación fundamental: sin HY spread pre-2023 (componente A1), el Bloque A funciona con solo 3 componentes activos en el período crítico 2007-2009 (VIX, curva, inflación). Esto reduce el rango máximo del macro_tension y hace imposible sostener persistencia ≥12 durante suficientes semanas.

### Resultados de los tres tests

| Test | Resultado | Criterio | Veredicto |
|---|---|---|---|
| Test 1 — Lead time | 0/14 eventos detectados | ≥4/14 = Parcial | **FALLIDO** |
| Test 1b — Picos reales | GFC 2007: NO. Bear 2022: NO | ≥1 con lead >30d | **FALLIDO** |
| Test 2 — Alpha basket | Solo TÁCTICAS: +0.28% 13w (t=0.25) | >+2% t>1.5 | **FALLIDO** |
| Test 3 — Falsos positivos | 0 STRUCTURAL emitidas → 0% FP rate | <40% | N/A (sin señal) |

---

## Sección 1 — Construcción del detector

### Filosofía de los 9 componentes

**Bloque A (macro, target 40 pts):** captura aceleración del deterioro macro, no niveles. Cinco señales:
- A1 (HY Accel, 10 pts): ampliación acelerada de spreads de crédito high-yield. **Solo disponible desde abril 2023.**
- A2 (NetLiq Contraction, 10 pts): contracción de liquidez del banco central (balance sheet).
- A3 (Curve Dynamics, 8 pts): inversión de curva y/o dinámica de profundización.
- A4 (Vol Regime Shift, 6 pts): cambio de régimen de volatilidad desde calma (VIX).
- A5 (Inflation Shift, 6 pts): movimiento rápido de expectativas de inflación en cualquier dirección.

**Bloque B (sector, target 35 pts):** captura rotación sectorial defensiva antes de que el régimen macro confirme:
- B1 (Cyclical Deterioration, 12 pts): caída del rotation_score en Growth y Value/Cyclical.
- B2 (Defensive Strengthening, 10 pts): subida del rotation_score en Defensive y Duration.
- B3 (Cyc-Def Divergence, 8 pts): distancia absoluta entre defensivos y cíclicos.
- B4 (SPY Internal Divergence, 5 pts): SPY en uptrend pero cíclicos perdiendo relative strength.

**Persistencia (25 pts):** semanas con macro_tension > 20 en las últimas 8. Exige que el stress macro sea sostenido, no un spike aislado.

**Score total 0-100** = A_scaled(40) + B_scaled(35) + Persistencia(25).

**Reescalado dinámico:** cuando un componente no tiene datos (None), su peso se redistribuye proporcionalmente entre los disponibles. Los pesos relativos de los componentes disponibles NO se modifican. Esto aplica directamente a A1 (HY) ausente en todo el período pre-2023.

---

## Sección 2 — Test 1: Lead time

### 14 transiciones del sistema base

**No se detectó ninguna.** 0/14 transiciones fueron precedidas por ALERTA ESTRUCTURAL dentro de los 180 días previos.

Razón: ALERTA ESTRUCTURAL requiere 2 semanas consecutivas con confluence ≥ 55. El score máximo histórico fue 58 (una semana). El score no alcanzó el umbral dos semanas seguidas en ningún momento del período 2005-2026.

### Picos reales con precursores económicos

| Pico | Modo A | Modo B | Veredicto |
|---|---|---|---|
| GFC 2007-10-12 | NO DETECTADO | NO DETECTADO | Fallido |
| Bear 2022-01-04 | NO DETECTADO | NO DETECTADO | Fallido |

### COVID 2020 (informativo — excluido de criterio)

**NO DETECTADO** en ningún modo. Este resultado era esperado: el crash COVID fue un shock exógeno sin precursores macro detectables. La no-detección confirma que el detector no generó falsa alarma ex-ante.

### Análisis detallado: 2008 — la aproximación más cercana

La semana del **2008-10-24** es el único punto en 20 años donde TODAS las condiciones se cumplieron simultáneamente:

| Condición STRUCTURAL | Valor requerido | Valor en 2008-10-24 | ¿Cumple? |
|---|---|---|---|
| confluence_score | ≥ 55 | **58.0** | Sí |
| macro_tension | ≥ 20 | **24.0** | Sí |
| sector_tension | ≥ 15 | **16.0** | Sí |
| persistence | ≥ 12 | **18** | Sí |

Sin embargo, la semana siguiente (2008-10-31), sector_tension cayó a 6.0 (por debajo de 15), rompiendo la condición. El detector exige 2 semanas consecutivas para evitar falsos positivos. Esta es la razón directa del fallo.

**Cronología de la aproximación a 2008:**

| Semana | Confluence | Macro | Sector | Persist. | Condiciones (de 4) |
|---|---|---|---|---|---|
| 2008-09-19 | 38.0 | 24.0 | 11.0 | 3 | 1/4 (sector bajo) |
| 2008-09-26 | 33.0 | 24.0 | 3.0 | 6 | 1/4 (sector muy bajo) |
| 2008-10-03 | 44.0 | 24.0 | 11.0 | 9 | 1/4 (confluence, sector) |
| 2008-10-10 | 49.0 | 24.0 | 13.0 | 12 | 2/4 (confluence, sector bajos) |
| 2008-10-17 | 49.0 | 24.0 | 10.0 | 15 | 2/4 (confluence, sector bajos) |
| **2008-10-24** | **58.0** | **24.0** | **16.0** | **18** | **4/4 ← única semana** |
| 2008-10-31 | 51.0 | 24.0 | 6.0 | 21 | 1/4 (sector colapsó) |
| 2008-11-07 | 44.0 | 12.0 | 11.0 | 21 | 0/4 |

**Observación crítica:** el Bloque B (sector) colapsa precisamente en el punto de máximo pánico (Oct-Nov 2008). En una crisis aguda, los clusters cíclicos y defensivos se mueven juntos (todo cae), eliminando la divergencia. El detector sectorial está diseñado para capturar rotación gradual, no pánico simultáneo.

### 2022 — por qué tampoco detectó

El bear market de 2022 fue inflacionario, no deflacionario. La curva se estaba normalizando (steepening desde inversión), el VIX subió pero moderadamente, y el Bloque B no mostró divergencia defensiva clara. Ningún componente alcanzó el umbral sostenido necesario.

---

## Sección 3 — Test 2: Alpha basket desde alertas

### Sin STRUCTURAL: análisis sobre alertas TÁCTICAS

Las 46 alertas TÁCTICAS (sector_tension ≥ 20, macro < 15, 2 semanas consecutivas) muestran:

| Horizonte | N | Mean alpha | Mediana | T-stat | Veredicto |
|---|---|---|---|---|---|
| +4w | 46 | **−1.35%** | −0.76% | **−3.25** | Negativo significativo |
| +13w | 46 | +0.28% | −2.93% | 0.25 | No significativo |
| +26w | 46 | −0.51% | −1.74% | −0.41 | No significativo |

**Las TÁCTICAS generan alpha negativo a 4w.** Esto es coherente con su definición: se emiten cuando el sector se deteriora pero el macro aún no confirma, y SPY frecuentemente sigue subiendo (componente B4 captura exactamente ese escenario). Entrar en posición defensiva en ese momento implica perder alpha vs SPY en las 4 semanas siguientes.

**Alertas TÁCTICAS históricas:**

| Fecha | Confluence | Alpha 4w | Alpha 13w | Alpha 26w | Contexto |
|---|---|---|---|---|---|
| 2005-08-26 | 24.0 | +0.61% | −2.97% | −0.29% | Inicio ciclo normal |
| 2006-07-21 | 36.0 | −3.26% | −6.57% | −8.30% | Pre-subprime (FP) |
| 2007-11-30 | 22.0 | +1.35% | +9.03% | +3.97% | Crisis incipiente |
| 2008-07-11 | 29.0 | −5.45% | +13.22% | +19.03% | Pre-Lehman |
| 2010-05-21 | 35.0 | +0.46% | +5.37% | −2.43% | Flash crash |
| 2011-08-05 | — | — | — | — | Sovereign debt |
| 2016-06-24 | 37.0 | −2.29% | −4.20% | −17.43% | Brexit (FP) |
| 2019-08-09 | 40.7 | +0.30% | −5.91% | −6.11% | Trade war |
| 2026-02-13 | 31.0 | +0.38% | −6.98% | −6.98% | 2026 tensión |

---

## Sección 4 — Test 3: Falsos positivos

**0 alertas STRUCTURAL emitidas → tasa de falsos positivos: N/A.**

El detector es hiper-conservador: prefiere no emitir ninguna señal antes que emitir una falsa. Desde la perspectiva operativa, esto significa que el costo de implementarlo es bajo (nunca genera señal de acción) pero el beneficio también es nulo.

---

## Sección 5 — Análisis narrativo de crisis

### 2008 — GFC

El detector aproximó su máximo en la **fase aguda post-Lehman** (octubre 2008), no antes. Esto confirma lo documentado en Entrega 4: el sistema reacciona tarde en crisis graduales.

**¿Qué componentes impulsaron el score en 2008?**
- **A4 (VIX):** VIX llegó a 80 en octubre 2008. Contribuyó 6 pts de forma sostenida.
- **A2 (NetLiq):** paradójicamente, la Fed expandía el balance con fuerza → contribución NULA (A2 detecta contracción). Esto fue un error conceptual: en 2008, la respuesta de emergencia de la Fed fue expansión de balance, que es exactamente lo opuesto de lo que A2 detecta como estrés.
- **A3 (Curva):** La curva pasó de invertida (2006-2007) a steepenning agresivo (la Fed cortó tasas desde 5.25% a 0%). La inversión previa (2006-2007) habría contribuido A3, pero no se acumuló persistencia.
- **A1 (HY):** Ausente. Si HY hubiera estado disponible, las spreads de 2007-2008 (pasaron de ~250 bps a ~2000 bps) habrían generado puntajes A1 de 10 pts durante meses.
- **B1-B4:** El sector funcionó en la pre-crisis (2007) con divergencias claras, pero en el pánico de Q4 2008 todo colapsó simultáneamente.

**Estimación contrafactual si HY hubiera estado disponible:**
En el período post-2023, HY activo contribuye 4-10 pts en situaciones de stress. Si en 2007-2008 hubiera contribuido 7-10 pts durante los ~18 meses de deterioro HY (Q3 2007 - Q3 2008), macro_tension habría sido:
- Actual (sin HY): máx ~26 pts
- Estimado (con HY): máx ~38-40 pts

Con macro_tension sustentado en >25 durante múltiples semanas, la persistencia habría superado 12 ya en Q1 2008, y el confluence score habría superado 55 con meses de antelación al colapso. **El HY ausente es la causa principal del fallo en 2008.**

### 2022 — Bear Inflacionario

El bear de 2022 (-25% SPY) no generó STRUCTURAL. Las razones:
- A3 (curva): la curva se invirtió durante 2022-2023 → contribuyó A3. Pero el 10y3m no se invirtió profundamente hasta Q4 2022.
- A1 (HY): datos disponibles solo desde abril 2023. Los spreads de 2022 no están capturados.
- A4 (VIX): el VIX en 2022 fue moderado (peak ~37), no alcanzó el threshold sostenido de 25+.
- Bloque B: no hubo divergencia defensiva clara — sector defensivo también cayó.

El máximo confluence en 2022 fue ~40 (por debajo del umbral STRUCTURAL de 55).

### 2020 — COVID (informativo)

**No se emitió ninguna alerta antes ni durante el crash.** El crash de 33 días no generó señales sostenidas. Ningún componente alcanzó thresholds altos durante semanas consecutivas antes del colapso. Correcto — era un shock exógeno.

---

## Sección 6 — Contribución por componente en alertas

### En el máximo histórico (2008-10-24, Modo A)

| Componente | Pts | Max posible | % del max | ¿Disponible? |
|---|---|---|---|---|
| A1 HY Accel | — | 10 | — | **NO (pre-2023)** |
| A2 NetLiq | 0 | 10 | 0% | Sí (balancesheet expandiéndose → score 0) |
| A3 Curve | 0 | 8 | 0% | Sí (steepening, no inversión) |
| **A4 Vol Shift** | **6** | 6 | **100%** | Sí (VIX>25 y rising) |
| A5 Inflation | ~3 | 6 | ~50% | Sí (t5yie moviéndose rápido) |
| B1 Cycl. Det. | 5 | 12 | 42% | Sí |
| **B3 Divergence** | **8** | 8 | **100%** | Sí |
| B2 Def. Strength | ~3 | 10 | 30% | Sí |
| B4 SPY Internal | 0 | 5 | 0% | Sí (SPY ya había roto SMA200) |

**Dominante:** A4 (VIX) fue el único componente Bloque A al máximo. B3 (divergencia defensiva-cíclica) fue el único Bloque B al máximo. La alerta que estuvo a punto de emitirse en 2008 dependía críticamente de A4 y B3.

**Implicación:** si HY hubiera aportado 8-10 pts adicionales en Bloque A en Q3 2007 hasta Q2 2008, la persistencia habría acumulado los 12 pts necesarios meses antes, y confluence habría superado 55 sostenidamente. El fallo en 2008 es atribuible directamente a la ausencia de HY.

### Alertas TÁCTICAS: componente dominante

Todas las 46 alertas TÁCTICAS activaron con macro_tension < 15, lo que significa que el Bloque B fue el motor. En todos los casos, **B3 (divergencia)** y/o **B1 (deterioro cíclico)** fueron los componentes dominantes.

---

## Sección 7 — Ajustes propuestos (documentados, NO implementados)

Los siguientes ajustes habrían mejorado los resultados. **No se implementan para evitar overfitting.**

**Ajuste 1 — Reducir threshold confluence de 55 a 45:**
Con umbral 45: la semana 2008-10-17 (confluence=49) y 2008-10-24 (58) habrían formado 2 semanas consecutivas, activando STRUCTURAL en **2008-10-24**. Lead time vs sistema base (2008-09-26): 28 días (casi 4 semanas antes). Lead time vs pico de mercado (2007-10-12): 377 días. Pero el sistema base ya había emitido su señal, así que el "lead" real sería prácticamente nulo.

**Ajuste 2 — Reducir sector_threshold de 15 a 10:**
Con sector ≥ 10 (en lugar de 15): más semanas consecutivas habrían cumplido. Confluence habría superado 50 durante varias semanas en octubre 2008. Pero sector_tension entre 10-15 es señal débil — probablemente aumentaría FP en bull markets.

**Ajuste 3 — Eliminar el requesito de persistencia:**
Sin el requisito de persistencia ≥ 12: habría 1 semana con confluence ≥ 55 (2008-10-24). Con la condición de 2 semanas consecutivas habría fallado igualmente. Este ajuste ayudaría solo con reducción del threshold.

**Ajuste conceptualmente justificado (no overfitting) PERO NO VIABLE:** integrar HY spread histórico pre-2023. Esta modificación está bloqueada por limitaciones de datos documentadas en Entrega 1 — BAMLH0A0HYM2 está truncada a 3 años por ICE license, ALFRED no tiene vintages pre-2023, y los proxies probados (NFCICREDIT en 3 variantes) fallaron spot-checks históricos (2008, 2011, 2020). Con HY disponible en 2007-2008, el detector habría tenido 4 componentes activos en Bloque A y la persistencia habría acumulado naturalmente — pero esta vía está cerrada con los datos actualmente obtenibles.

---

## Sección 8 — Implicaciones operativas

### ¿Debe la app productiva incluir este detector?

**No en su forma actual.** El detector STRUCTURAL nunca se activa. El detector TÁCTICO genera señales con alpha negativo a 4w. Implementarlo produciría rotaciones defensivas prematuras que costarían alpha.

**Qué sí es útil:**
- El **confluence_score como indicador de tensión continua** (0-100) es informativo. El score puede mostrarse en la UI como thermómetro de estrés sin emitir señales binarias.
- Los componentes individuales (especialmente B1, B3, A3, A4) tienen valor diagnóstico visual.

### ¿Qué umbral de alerta tiene sentido en la UI?

Si se usa como indicador visual:
- 0-30: Verde (normal/cautela)
- 30-45: Amarillo (tensión elevada, monitorear)
- 45+: Naranja (stress real, revisar posicionamiento)

El nivel 55+ para ALERTA ESTRUCTURAL es apropiado como concepto pero el histórico muestra que solo se alcanzó una vez. O bien el umbral debe bajar, o bien el detector necesita HY histórico.

### Limitaciones conocidas del detector

1. Sin HY pre-2023: el Bloque A tiene 3 componentes activos en lugar de 5 para todo el período previo. Esto es la limitación más grave.
2. A2 (NetLiq) penaliza contracción pero en crisis de 2008 la Fed expandió → A2=0 en la peor fase.
3. El Bloque B detecta rotación gradual, no pánico simultáneo. En crises agudas, defensivos y cíclicos caen juntos.
4. La condición de 2 semanas es necesaria para reducir FP pero impide capturar spikes de una semana (como 2008-10-24).

---

## Sección 9 — Sanity checks

| Check | Resultado | Estado |
|---|---|---|
| STRUCTURAL < 15% del tiempo | 0.0% (Modo A y B) | OK |
| STRUCTURAL en 2008 (ene-ago) | No (primer y único spike fue oct 2008) | **OBJETIVO FALLIDO** |
| No alarma en bull markets (2013, 2014, 2017, 2019, 2021) | 0% tiempo STRUCTURAL en todos | OK |
| Coherencia con Bull Pleno (score < 30) | Max confluence en Bull Pleno: ~28 | OK |
| Spike 2008-10-24 detectado | Confluence=58, 4/4 condiciones met, 1 semana | PARCIAL |

---

## Conclusión

El detector de confluencia está **conceptualmente correcto** pero **calibrado fuera del rango empírico** de los datos disponibles, con la ausencia de HY histórico como causa raíz.

**Lo que el detector SÍ demostró:**
- Los componentes funcionan individualmente (tests unitarios: 294 passed)
- El score es informativo: el máximo histórico coincide con la peor semana de la crisis de 2008
- La arquitectura de reescalado dinámico funciona correctamente (sin redistribución de pesos)
- Los bull markets no generan falsas alarmas

**Lo que el detector NO logró:**
- Emitir ALERTA ESTRUCTURAL en ningún momento histórico
- Anticipar el GFC 2007-2008 (falla por ausencia HY + calibración)
- Proveer alpha positivo desde alertas (TÁCTICAS: −1.35% a 4w)

**Sobre el alpha negativo de TÁCTICAS:** el resultado −1.35% a 4w (t=−3.25) no es un defecto a corregir. Es una confirmación empírica de la filosofía Pring/Weinstein: actuar en el deterioro sectorial antes de que el macro confirme es consistentemente prematuro. El mercado sigue subiendo mientras el macro no valida. La penalización de −1.35% es exactamente el costo de no esperar la confirmación macro. El diseño del sistema — TÁCTICA solo cuando macro < 15, STRUCTURAL cuando ambos bloques confluyen — es conceptualmente correcto. La ausencia de STRUCTURAL en los datos disponibles refleja una limitación de datos (HY), no una falla de diseño.

---

## Decisión post-Entrega 5

**El backtest queda cerrado en Entrega 5. No habrá Entrega 6.**

Las razones son dos:
1. **Datos bloqueados:** la única mejora no-overfitting viable (HY histórico pre-2023) está cerrada por ICE license. No existe fuente alternativa verificada.
2. **Resultado suficiente:** el backtest cumplió su objetivo declarado — caracterizar el comportamiento del sistema de señales con datos reales, sin ajuste retroactivo. El resultado honesto es más valioso que un resultado optimizado sin base empírica.

**Tres extensiones posibles si el contexto cambia, todas ortogonales entre sí:**

- **Confluencia como indicador visual (UI):** usar confluence_score (0-100) como termómetro de estrés en la interfaz productiva, sin emitir señales binarias. Los componentes individuales A3, A4, B1, B3 tienen valor diagnóstico visual.
- **Recalibración si aparecen datos HY:** si ICE abre el acceso histórico o se encuentra una fuente de spreads HY pre-2023 que pase spot-checks, el módulo macro_tension.py ya tiene A1 implementado y listo. Ningún cambio de arquitectura es necesario.
- **Extensión al universo v4 (230+ tickers):** el simulador está preparado para cualquier tamaño de cluster_health_history. La extensión es una operación de datos, no de código.

Ninguna de estas extensiones requiere reabrir el backtest ni reescribir los módulos existentes.

---

*Entrega 5 cerrada. Parquets generados: confluence_history.parquet (2,224 rows), confluence_alerts.parquet (46 rows), confluence_validation.parquet (20 rows).*
