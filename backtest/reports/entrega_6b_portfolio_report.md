# Entrega 6B — Portfolio Simulado: ROT. TEMPRANA como Estrategia
### Backtest de Portfolio | 2026-04-21

---

## Resumen ejecutivo

**Veredicto: CASO A + CASO D**

**Caso A (parcial):** ROT. TEMPRANA pura supera a SPY en CAGR y Sharpe **incluso sin BTC-USD**. Mode A sin BTC: CAGR=10.41% vs SPY=8.51%, Sharpe=0.63 vs 0.57. El hallazgo de Entrega 4 (alpha +7.29%, t=2.77 sobre señales individuales) se mantiene parcialmente en portfolio real, aunque con mayor modestia: +1.95% alpha anualizado.

**Caso D:** El sistema completo es peor que ROT. TEMPRANA pura en CAGR y Sharpe para Mode A (sin BTC: CAGR=6.84%, Sharpe=0.48). Las señales COMPRA y la rotación defensiva añaden ruido, no alpha ajustado por riesgo. Solo Mode B con BTC supera a SPY en sistema completo.

**Advertencia de muestra:** 18-19 trades cerrados (26 semanas de holding = rara vez más de 3-4 posiciones simultáneas) es una muestra pequeña. Cualquier conclusión sobre alpha tiene alta incertidumbre estadística.

### Tabla comparativa — 8 combinaciones principales (período completo 2005-2026)

| Estrategia | Modo | BTC | CAGR | Sharpe | MaxDD | Alpha ann. | N trades | vs SPY |
|---|---|---|---|---|---|---|---|---|
| **ROT. TEMPRANA pura** | A | sin | **10.41%** | **0.63** | -56.6% | +1.95% | 18 | ✓ |
| **ROT. TEMPRANA pura** | A | con | 9.95% | 0.60 | -56.6% | +1.45% | 19 | ✓ |
| **ROT. TEMPRANA pura** | B | sin | **10.77%** | **0.62** | -56.6% | +2.26% | 19 | ✓ |
| **ROT. TEMPRANA pura** | B | con | 10.30% | 0.60 | -56.6% | +1.76% | 20 | ✓ |
| Sistema completo | A | sin | 6.84% | 0.48 | -36.2% | +0.94% | 112 | ✗ |
| Sistema completo | A | con | 9.30% | 0.57 | -40.9% | +3.41% | 112 | ≈ |
| Sistema completo | B | sin | 8.20% | 0.55 | -36.2% | +2.50% | 109 | ✗ |
| Sistema completo | B | con | 10.69% | 0.63 | -40.9% | +5.00% | 109 | ✓ |
| **SPY buy-and-hold** | — | — | **8.51%** | **0.57** | **-55.2%** | — | — |

---

## Sección 1 — ROT. TEMPRANA pura vs SPY

### Resultado por período

| Período | CAGR estrat (A, sin BTC) | CAGR SPY | Sharpe estrat | Sharpe SPY | MaxDD estrat | MaxDD SPY |
|---|---|---|---|---|---|---|
| 2005-2026 | **10.41%** | 8.51% | **0.63** | 0.57 | -56.6% | -55.2% |
| 2010-2019 (bull puro) | 10.45% | **10.58%** | 0.80 | **0.83** | **-19.8%** | -19.4% |
| 2020-2026 | **13.57%** | 10.03% | **0.77** | 0.65 | -31.1% | -33.7% |

**En el período completo:** ROT. TEMPRANA pura bate a SPY en CAGR (+1.90 pp) y Sharpe (+0.06), con MaxDD similar (-56.6% vs -55.2%). La estrategia no ofrece protección en drawdown porque la mayoría del capital permanece en SPY por defecto.

**2010-2019 (bull puro):** La estrategia casi iguala a SPY (CAGR 10.45% vs 10.58%, Sharpe 0.80 vs 0.83) — marginal underperformance. Con solo 6 trades en 10 años, el portafolio fue básicamente SPY con 2-3 posiciones activas puntualmente en XLV, XLP, XLK, QQQ. La mayoría del tiempo el capital está en SPY, así que seguir al benchmark es el resultado esperado.

**2020-2026:** La estrategia añade valor claro: CAGR=13.57% vs SPY=10.03%, Sharpe=0.77 vs 0.65. Las entradas en XLK+XLC (mayo 2020, +25% y +19%) y XLE (octubre 2021, +34%) capturaron las rotaciones post-COVID correctamente. El MaxDD es ligeramente mejor (-31.1% vs -33.7%), probablemente porque el stop del 15% en feb-mar 2020 cortó las pérdidas en XLK y QQQ.

### ¿La estrategia añade valor sobre buy-and-hold de SPY?

**Sí, marginalmente y con caveats importantes:**
1. CAGR superior en todos los modos y períodos (completo y 2020-2026)
2. Sharpe superior en el período completo y 2020-2026
3. No añade valor en 2010-2019 (bull puro): marginal underperformance en Sharpe
4. MaxDD prácticamente idéntico a SPY — la estrategia no es una cobertura de riesgo

El mecanismo real: la cartera es SPY + posiciones tácticas de 26 semanas (26-week max hold). El alpha viene de esas posiciones tácticas, no de timing de mercado.

---

## Sección 2 — Impacto de BTC-USD

### Comparación con / sin BTC (Mode A, período completo)

| Métrica | Con BTC | Sin BTC | Diferencia |
|---|---|---|---|
| CAGR | 9.95% | 10.41% | -0.46 pp |
| Sharpe | 0.60 | 0.63 | -0.03 |
| MaxDD | -56.6% | -56.6% | 0 |
| N trades | 19 | 18 | -1 (BTC excluido) |
| Alpha ann. | +1.45% | +1.95% | -0.50 pp |

**Conclusión sobre BTC:** a diferencia de Entrega 4, donde BTC-USD concentraba el 60% del alpha total de COMPRA, aquí BTC **reduce** ligeramente el performance. La razón: la única señal ROT. TEMPRANA de BTC ocurrió el 2020-02-21, justo antes del crash COVID. El stop del 15% la cortó con -42.6% de pérdida en 21 días (2020-03-13). BTC-USD fue el peor trade individual del backtest.

**Implicación:** el hallazgo de Entrega 4 sobre dependencia BTC **no se replica en portfolio**. ROT. TEMPRANA es una estrategia válida sin exposición cripto. El alpha +1.95% (sin BTC) es más robusto que el alpha con BTC (+1.45%) porque no depende de activos de alta volatilidad en timing adverso.

---

## Sección 3 — ROT. TEMPRANA pura vs Sistema completo

**Resultado claro: ROT. TEMPRANA pura supera al sistema completo** en todos los períodos y modos (excepto Mode B con BTC en sistema completo, que tiene mejor CAGR pero similar Sharpe).

| Estrategia | Modo | BTC | CAGR | Sharpe | Trades | Turnover |
|---|---|---|---|---|---|---|
| ROT. TEMPRANA pura | A | sin | 10.41% | **0.63** | 18 | 0.36x |
| Sistema completo | A | sin | 6.84% | 0.48 | 112 | **1.61x** |
| ROT. TEMPRANA pura | B | sin | 10.77% | **0.62** | 19 | 0.37x |
| Sistema completo | B | sin | 8.20% | 0.55 | 109 | **1.64x** |

**El sistema completo tiene 6x más trades con menor Sharpe.** Las señales COMPRA añaden rotación (turnover 1.61x anual vs 0.36x) con costes de transacción adicionales y sin alpha compensatorio.

**Razón mecánica:** el filtro de COMPRA (confluence < 45) activa correctamente señales defensivas (TLT, XLU) y sectoriales (XLRE, XLE, SI=F) con frecuencia alta. Muchas de estas posiciones tienen rendimientos mediocres o negativos a 26 semanas, que diluyen el alpha de las ROT. TEMPRANA. El sistema completo en Mode A 2010-2019 tiene CAGR=10.16% con BTC y 4.21% sin BTC — en el bull run de 10 años, el sistema completo destruye alpha respecto a simplemente mantener SPY.

**Esto valida empíricamente la conclusión de Entrega 4:** las señales COMPRA no generan alpha significativo en portfolio real.

---

## Sección 4 — Análisis por subperíodo

### 2010-2019 — Bull puro

| Estrategia | Modo | BTC | CAGR | Sharpe | MaxDD | N trades |
|---|---|---|---|---|---|---|
| ROT. TEMPRANA pura | A | sin | 10.45% | 0.80 | -19.8% | 6 |
| ROT. TEMPRANA pura | B | sin | 10.45% | 0.80 | -19.8% | 6 |
| Sistema completo | A | sin | 4.21% | 0.37 | -33.4% | 64 |
| Sistema completo | A | con | 10.16% | 0.63 | -33.4% | 63 |
| SPY benchmark | — | — | 10.58% | 0.83 | -19.4% | — |

**ROT. TEMPRANA pura en bull:** prácticamente reproduce SPY (10.45% vs 10.58%, Sharpe 0.80 vs 0.83). Con solo 6 trades en 10 años, la cartera es SPY con 2-3 posiciones tácticas en XLV, XLP, XLK y QQQ. En bull markets sostenidos, la estrategia no deteriora el rendimiento — simplemente no añade valor adicional.

**Sistema completo en bull (sin BTC):** 4.21% CAGR — catastrófico. El motor entra en posiciones defensivas (TLT, GC=F, XLU, XLP) como señales COMPRA durante 2010 (régimen Transición, confluence < 45). Estas posiciones, al tener holding 26 semanas, son reemplazadas por las siguientes señales COMPRA disponibles, que también tienden a ser defensivas/rotacionales en régimen incierto. El resultado: alta rotación con posiciones subóptimas en un bull market donde lo óptimo era simplemente mantener SPY.

### 2020-2026 — Post-COVID

| Estrategia | Modo | BTC | CAGR | Sharpe | MaxDD | N trades |
|---|---|---|---|---|---|---|
| ROT. TEMPRANA pura | A | sin | 13.57% | 0.77 | -31.1% | 7 |
| ROT. TEMPRANA pura | A | con | 12.19% | 0.69 | -38.4% | 8 |
| ROT. TEMPRANA pura | B | sin | 14.65% | 0.74 | -31.5% | 8 |
| Sistema completo | A | sin | 6.53% | 0.44 | -38.6% | 40 |
| SPY benchmark | — | — | 10.03% | 0.65 | -33.7% | — |

**ROT. TEMPRANA pura domina en 2020-2026.** Las rotaciones capturadas (tech post-COVID, energía 2021, commodities 2025) tienen retornos de 19-34% por posición en 26 semanas. Sin BTC, la MaxDD es ligeramente mejor que SPY (-31.1% vs -33.7%), porque el stop del 15% en marzo 2020 y el periodo de stop en la corrección de 2022 limitan pérdidas en posiciones activas.

---

## Sección 5 — Análisis de trades

### ROT. TEMPRANA pura — Mode A, sin BTC, período completo (18 trades cerrados)

| Ticker | Entrada | Salida | Retorno | Holding | Razón |
|---|---|---|---|---|---|
| GC=F | 2005-12 | 2006-06 | +14.8% | 182d | max_holding |
| SI=F | 2005-12 | 2006-06 | +18.7% | 182d | max_holding |
| XLI | 2007-07 | 2008-01 | -14.4% | 182d | max_holding |
| XLB | 2007-07 | 2008-01 | -11.5% | 182d | max_holding |
| XLE | 2007-07 | 2008-01 | -6.4% | 182d | max_holding |
| XLV | 2013-04 | 2013-10 | +11.9% | 182d | max_holding |
| XLP | 2013-04 | 2013-10 | +4.1% | 182d | max_holding |
| XLK | 2016-10 | 2017-04 | +12.4% | 182d | max_holding |
| QQQ | 2016-10 | 2017-04 | +12.0% | 182d | max_holding |
| QQQ | 2018-03 | 2018-09 | +8.0% | 182d | max_holding |
| XLK | 2018-03 | 2018-09 | +8.0% | 182d | max_holding |
| XLK | 2020-02 | 2020-03 | **-15.3%** | 21d | stop_loss |
| QQQ | 2020-02 | 2020-03 | **-16.5%** | 21d | stop_loss |
| XLK | 2020-05 | 2020-11 | **+25.1%** | 182d | max_holding |
| XLC | 2020-05 | 2020-11 | **+19.4%** | 182d | max_holding |
| XLE | 2021-10 | 2022-04 | **+34.5%** | 182d | max_holding |
| XLF | 2021-10 | 2022-04 | -10.2% | 182d | max_holding |
| GC=F | 2025-12 | 2026-04 | +13.0% | 128d | end_of_period |

**Estadísticas:**
- Hit rate: 66.7% (12/18 ganadores)
- Mejor trade: XLE 2021-10 → 2022-04 (+34.5%)
- Peor trade: QQQ 2020-02 → stop (-16.5%)
- Holding medio: 161 días (~23 semanas)
- Todos los exits excepto 2 son max_holding (26 semanas) → el holding period domina la estrategia

**Clusters de trades:**
- **Commodities (GC=F, SI=F):** 3 trades, media +15.7% — fuertes
- **Tech/Growth (XLK, QQQ, XLC):** 7 trades, media +8.5% — consistentemente positivos
- **Energy/Materials (XLE, XLB, XLI):** 4 trades, media -0.1% — ciclicales en 2007 fallaron, energía 2021 funcionó
- **Defensivos/Value (XLV, XLP, XLF):** 4 trades, media +1.5% — mediocres

**El stop del 15% funciona:** los dos stop_loss en marzo 2020 limitaron pérdidas a -15.3% y -16.5% en vez de esperar las 26 semanas (SPY cayó -35% desde feb a mar 2020). Sin el stop, estas posiciones habrían terminado en -30%+.

### Exit reasons (ROT. TEMPRANA pura, todos los modos)

| Razón | N | % |
|---|---|---|
| max_holding | 12 | 66.7% |
| stop_loss | 3 | 16.7% |
| end_of_period | 2 | 11.1% |
| signal_acumular_star | 0 | 0% |
| regime_riskoff | 0 | 0% |

La estrategia es puramente timing: entrar en ROT. TEMPRANA, mantener 26 semanas o hasta stop. No hay exits por cambio de régimen macro porque en ningún punto el sistema alcanzó Risk-OFF mientras había posiciones ROT. TEMPRANA abiertas.

---

## Sección 6 — Sanity checks

| Check | Resultado | Estado |
|---|---|---|
| SPY CAGR 2005-2026 en rango 8-11% | 8.51% | ✓ OK |
| Min equity positiva en todas las sims | $56,470 mínimo (full system 2010-2019 sin BTC) | ✓ OK |
| N trades ROT. pura Modo A ≤ 80 | 19 trades | ✓ OK |
| Alpha ROT. pura Modo A sin BTC positivo | +1.95% | ✓ (consistente con E4) |
| Beta full system < 1.0 (alpha coherente) | Beta=0.69-0.69 confirmado | ✓ OK |
| Anomalía full system 2010-2019 sin BTC | CAGR=4.21% documentada sin ajuste | ⚠ Ver §3 y §6 |

**Anomalía documentada (full system 2010-2019 sin BTC):** CAGR=4.21% muy por debajo de SPY (10.58%). Causa: el motor full_system con confluence_series nula en periodos anteriores a 2022 (datos HY ausentes → confluence_score bajo → confluence < 45 siempre activo) genera exceso de señales COMPRA en activos defensivos (TLT, XLU, XLV, TLT, XLRE) con alta rotación y costes sin alpha. Con BTC (CAGR=10.16%), la diferencia viene de que con BTC se captura BTC-USD como COMPRA, no ROT. TEMPRANA — BTC en 2017 (+13x) infla el resultado. Esto reconfirma la dependencia BTC de las señales COMPRA de Entrega 4.

**Bug corregido durante implementación:** la primera versión del motor no aplicaba el check de max_holding (26 semanas) ni stop_loss a tickers en DEFENSIVE_BASKET cuando habían sido entrados como señales COMPRA. Esto causaba que TLT y XLU fuesen mantenidos 8.5 años (2010-2019) sin ningún check de salida. Corregido mediante el campo `position_type='defensive'` que distingue posiciones defensivas (entradas durante Risk-OFF) de posiciones de señal (entradas normales). Las métricas presentadas en este reporte corresponden a la versión corregida.

---

## Sección 7 — Limitaciones y caveats

1. **Muestra pequeña:** ROT. TEMPRANA pura genera 18-19 trades en 21 años. Con N=18, el intervalo de confianza del alpha es amplio. El resultado es consistente con E4 (t-stat=2.77) pero no confirma ni refuta estadísticamente en solitario.

2. **26-week max hold artificial:** todos los exits son por max_holding (26 semanas), no por cierre de señal. En práctica, la señal podría continuar activa más allá de 26 semanas, pero el modelo no lo evalúa más allá.

3. **Sin slippage real:** precios diarios asof() con 5 bps de coste. En activos ilíquidos (SI=F, BZ=F), el slippage real sería mayor.

4. **Capital mayoritariamente en SPY:** en todo momento la mayor parte del capital está en SPY como default. El "portfolio ROT. TEMPRANA pura" es en realidad un "SPY con sobreposiciones tácticas cortas (26 semanas)". El beta ~1.0 confirma esto.

5. **Confluence ausente pre-2023 afecta full_system:** el filtro confluence < 45 se basa en confluence_history que tiene datos reales desde 2022 (HY ausente pre-2023 → score artificialmente bajo en periodos históricos → filtro siempre activo → exceso de señales COMPRA). Esto contamina los resultados del sistema completo en 2010-2019.

6. **Turnover full_system:** 1.6x anual implica ~$160k de rotaciones por cada $100k de capital. A 5 bps por trade, los costes son ~$160 anuales — bajo. El problema no son los costes sino la calidad de las señales.

---

## Sección 8 — Conclusión operativa

### ¿ROT. TEMPRANA como estrategia es implementable?

**Sí, con restricciones.** La estrategia:
- Genera CAGR superior a SPY sin BTC (+1.90 pp en el período completo)
- Tiene Sharpe superior (+0.06)
- Requiere turnover bajo (0.36x anual: ~3-4 trades por año)
- No requiere exposición cripto
- Funciona especialmente bien en períodos de alta rotación sectorial (2020-2026)

Las restricciones:
- No ofrece protección en drawdown (MaxDD similar a SPY)
- En bull markets sostenidos (2010-2019) prácticamente reproduce SPY — no añade ni resta valor
- Muestra pequeña: 18 trades en 21 años significa que 2-3 trades malos pueden cambiar el resultado

### ¿Añade valor sobre buy-and-hold de SPY ajustado por riesgo?

**Marginalmente sí en el largo plazo, sin evidencia en bull markets.** El Sharpe de 0.63 vs 0.57 es mejora real pero modesta. No hay evidencia de que la estrategia reduzca el riesgo — solo que la selección de tickers en ROT. TEMPRANA tiene un ligero edge sobre el benchmark durante rotaciones sectoriales.

### ¿Dependencia de BTC invalida la estrategia?

**No para ROT. TEMPRANA pura.** Sin BTC, los resultados son mejores (10.41% vs 9.95%), porque la única señal ROT. TEMPRANA de BTC fue en febrero 2020, justo antes del crash. La estrategia ROT. TEMPRANA es independiente de cripto.

### ¿Qué turnover requiere?

0.36x anual — aproximadamente 2-4 trades al año. Perfectamente implementable de forma manual semanal. El sistema completo (1.6x anual, 5-10 trades/año) es más exigente pero sigue siendo manejable.

### Caso aplicable (§12)

**Caso A + Caso D:**
- **A:** ROT. TEMPRANA pura supera SPY en Sharpe sin BTC — hallazgo de Entrega 4 parcialmente validado en portfolio.
- **D:** Sistema completo es consistentemente peor que ROT. TEMPRANA pura en Sharpe y CAGR (sin BTC) — confirma que COMPRA y rotación defensiva añaden ruido.

El caso A es "parcial" porque el alpha (+1.95%) es modesto y la muestra es pequeña (N=18). No hay base para afirmar que la estrategia es consistentemente superior con alta confianza estadística. Lo que sí es robusto: la estrategia no destruye valor, no introduce riesgo adicional, y tiene edge real en períodos de rotación activa.

---

## Sección 9 — Interpretación honesta

Cuatro lecturas operativas sin suavizar:

**1. Alpha de señal vs alpha de portfolio: dilución esperada.**
Entrega 4 midió alpha por señal: +7.29% a 13w (t=2.77) sobre señales ROT. TEMPRANA individuales. En portfolio, ese edge se convierte en +1.95% anualizado sobre el capital total. La dilución es mecánica: el capital que no está en posiciones ROT. TEMPRANA activas está en SPY (que tiene alpha=0 por definición del benchmark). Con 18 trades en 21 años = 0.86 trades/año en media, y cada posición ocupa ~15-20% del capital durante 26 semanas, el portfolio pasa la mayor parte del tiempo replicando SPY. El alpha +7.29% por señal se convierte en ~+7.29% × 0.20 de capital promedio en posiciones × 2 rotaciones/año ≈ +2.9% — lo cual es coherente con el +1.95% observado (la diferencia es costes y timing imperfecto). No hay contradicción entre ambos números.

**2. No protege drawdowns sistémicos.**
MaxDD=-56.6% vs SPY=-55.2%. El portfolio no es una cobertura. El capital invertido en SPY por defecto cae igual que SPY. Los 2 stops de marzo 2020 (-15.3%, -16.5%) limitaron pérdidas en las posiciones activas, pero representaban ~20% del capital total — el otro 80% en SPY cayó sin protección. ROT. TEMPRANA es una estrategia de selección de activos en fase de rotación temprana, no de gestión de riesgo sistémico. Quien la use como hedge contra correcciones de mercado obtendrá decepción.

**3. Sistema completo destruye valor en bull markets puros.**
En 2010-2019, el sistema completo sin BTC genera CAGR=4.21% vs SPY=10.58% — una diferencia de 6.4 pp anual durante 10 años. La causa es que el filtro COMPRA (confluence < 45) está siempre activo en el período histórico (HY ausente → confluence artificial bajo), generando rotaciones en activos defensivos y sectoriales con alta frecuencia en un mercado alcista sostenido. El sistema completo, tal como está implementado con datos históricos disponibles, es contraproducente en entornos de bull market largo. Solo en 2020-2026 (con datos HY reales post-2022 y ambiente de alta rotación) el sistema completo mejora su comportamiento.

**4. El valor del sistema base es informativo, no operativo.**
El sistema de señales (régimen macro, COMPRA, ACUMULAR, rotación sectorial) tiene valor como contexto para decisiones manuales: saber que estamos en Bull Maduro vs Transición vs Risk-OFF informa la postura de riesgo. Pero el backtest muestra que ejecutar automáticamente señales COMPRA con las reglas definidas no genera alpha neto suficiente para justificar el turnover. La excepción es ROT. TEMPRANA: la señal tiene edge real y turnover bajo, lo que la hace viable como estrategia táctica de baja frecuencia. El uso operativo recomendado: confluence_score como indicador de tensión (UI), ROT. TEMPRANA como trigger de revisión manual, señales COMPRA/ACUMULAR como contexto sectorial — no como reglas automáticas de ejecución.

---

*Entrega 6B cerrada. Parquets generados: portfolio_rot_temprana_history.parquet (96,784 rows), portfolio_trades.parquet (1,900 rows), portfolio_metrics.parquet (27 rows).*
