# Entrega 4 — Performance Report: RotationScore Signal Backtest

## Resumen ejecutivo

**Veredicto:** NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)

- Señales COMPRA — alpha medio 13w (Modo A): +2.4%  | hit rate: +49.4%  | t-stat: 0.45
- ROT. TEMPRANA: 44% convergen a COMPRA/ACUMULAR  | lead time mediano: 21w
- Recession basket: alpha medio 13w en transiciones = -1.1%

---

## Sección 1 — Alpha por tipo de señal

### Modo A

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1180 | 18 | +1.1% | -0.2% | +10.3% | 0.46 | +48.1% |
| COMPRA | 13w | 1145 | 18 | +2.4% | -0.1% | +22.6% | 0.45 | +49.4% |
| COMPRA | 26w | 1123 | 18 | +4.6% | -0.8% | +41.2% | 0.47 | +46.7% |
| ACUMULAR | 4w | 1986 | 18 | -0.1% | -0.2% | +5.3% | -0.07 | +47.1% |
| ACUMULAR | 13w | 1973 | 18 | +0.0% | -0.7% | +11.3% | 0.01 | +44.6% |
| ACUMULAR | 26w | 1954 | 18 | +0.0% | -1.2% | +15.7% | 0.01 | +45.9% |
| ROT. TEMPRANA | 4w | 53 | 15 | -1.2% | -0.6% | +5.4% | -0.88 | +43.4% |
| ROT. TEMPRANA | 13w | 47 | 15 | +2.6% | +2.2% | +7.1% | 1.40 | +63.8% |
| ROT. TEMPRANA | 26w | 45 | 14 | +3.8% | +3.5% | +8.8% | 1.64 | +68.9% |
| VIGILAR | 4w | 9580 | 19 | +0.1% | -0.1% | +5.5% | 0.08 | +48.6% |
| VIGILAR | 13w | 9496 | 19 | +0.4% | -0.3% | +12.7% | 0.14 | +47.7% |
| VIGILAR | 26w | 9342 | 19 | +1.2% | -0.4% | +24.5% | 0.21 | +48.1% |
| IGNORAR | 4w | 6211 | 19 | +0.1% | +0.0% | +6.1% | 0.04 | +50.1% |
| IGNORAR | 13w | 6178 | 19 | +0.4% | +0.1% | +11.6% | 0.15 | +50.2% |
| IGNORAR | 26w | 6128 | 19 | +0.8% | -0.5% | +18.3% | 0.18 | +48.2% |
| ACUMULAR* | 4w | 118 | 12 | -1.8% | -1.7% | +8.0% | -0.79 | +36.4% |
| ACUMULAR* | 13w | 118 | 12 | -4.7% | -5.1% | +13.6% | -1.19 | +29.7% |
| ACUMULAR* | 26w | 118 | 12 | -13.3% | -13.4% | +15.0% | -3.08 | +12.7% |

### Modo B

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1123 | 18 | +0.8% | -0.2% | +9.7% | 0.34 | +47.4% |
| COMPRA | 13w | 1096 | 18 | +2.2% | -0.1% | +22.8% | 0.41 | +49.0% |
| COMPRA | 26w | 1090 | 18 | +4.1% | -0.9% | +41.2% | 0.42 | +46.4% |
| ACUMULAR | 4w | 1956 | 18 | +0.0% | -0.1% | +5.2% | 0.01 | +48.0% |
| ACUMULAR | 13w | 1944 | 18 | +0.0% | -0.6% | +11.2% | 0.01 | +45.1% |
| ACUMULAR | 26w | 1931 | 18 | -0.3% | -1.2% | +14.5% | -0.08 | +45.9% |
| ROT. TEMPRANA | 4w | 63 | 16 | +1.2% | -0.7% | +12.4% | 0.39 | +42.9% |
| ROT. TEMPRANA | 13w | 48 | 15 | +2.7% | +2.3% | +7.1% | 1.47 | +64.6% |
| ROT. TEMPRANA | 26w | 45 | 14 | +3.8% | +3.5% | +8.8% | 1.64 | +68.9% |
| VIGILAR | 4w | 9650 | 19 | +0.1% | -0.1% | +5.6% | 0.09 | +48.5% |
| VIGILAR | 13w | 9569 | 19 | +0.4% | -0.3% | +12.8% | 0.15 | +47.6% |
| VIGILAR | 26w | 9394 | 19 | +1.3% | -0.4% | +24.7% | 0.23 | +48.1% |
| IGNORAR | 4w | 6217 | 19 | +0.0% | +0.0% | +6.1% | 0.03 | +50.1% |
| IGNORAR | 13w | 6181 | 19 | +0.4% | +0.1% | +11.6% | 0.15 | +50.3% |
| IGNORAR | 26w | 6131 | 19 | +0.8% | -0.4% | +18.3% | 0.19 | +48.2% |
| ACUMULAR* | 4w | 119 | 11 | -2.0% | -1.9% | +8.1% | -0.82 | +35.3% |
| ACUMULAR* | 13w | 119 | 11 | -5.0% | -5.3% | +13.8% | -1.20 | +29.4% |
| ACUMULAR* | 26w | 119 | 11 | -13.6% | -14.2% | +15.0% | -3.00 | +12.6% |

---

## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 246 | +9.8% | +61.4% | 0.54 |
| Bull Maduro | 695 | +1.3% | +48.8% | 0.31 |
| Transición | 196 | -2.4% | +38.8% | -0.95 |
| Risk-OFF | 8 | -8.9% | +0.0% | -4.58 |

### Modo B

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 246 | +9.8% | +61.4% | 0.54 |
| Bull Maduro | 650 | +0.7% | +47.2% | 0.18 |
| Transición | 162 | -1.0% | +45.7% | -0.42 |
| Risk-OFF | 38 | -7.1% | +13.2% | -2.53 |

---

## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 177 | +13.5% | +64.4% | 0.59 |
| Commodities | 298 | +1.4% | +45.3% | 0.17 |
| Value/Cyclical | 430 | +0.9% | +50.0% | 0.26 |
| Small/EM | 69 | +0.1% | +53.6% | 0.01 |
| Defensive | 143 | -2.6% | +38.5% | -0.77 |
| Duration | 28 | -3.9% | +35.7% | -0.40 |

### Modo B

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 177 | +13.5% | +64.4% | 0.59 |
| Value/Cyclical | 408 | +0.8% | +49.5% | 0.24 |
| Commodities | 278 | +0.2% | +42.8% | 0.03 |
| Small/EM | 69 | +0.1% | +53.6% | 0.01 |
| Defensive | 136 | -2.1% | +40.4% | -0.67 |
| Duration | 28 | -3.9% | +35.7% | -0.40 |

---

## Sección 4 — ROT. TEMPRANA

Total ROT. TEMPRANA emitidas: **158** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **70** (44%)
- Lead time (semanas): media=19.0  mediana=21  IQR=[8, 28]
- Convergencia por señal:
  - ACUMULAR: 42
  - COMPRA: 28

**Alpha 13w desde ROT. TEMPRANA:** +2.6%  | n=95
**Alpha 13w desde señal convencional (convergencia):** +1.6%  | n=44

---

## Sección 5 — Recession basket

Transiciones a Risk-OFF/Capitulacion detectadas: **14**

| Fecha | Anterior → Nuevo | INFL | α4w | α13w | α26w |
|-------|-----------------|------|-----|------|------|
| 2008-09-26 | Transición → Risk-OFF | no | +10.1% | +20.2% | +18.7% |
| 2018-12-28 | Transición → Risk-OFF | no | -1.9% | -6.0% | -5.0% |
| 2022-11-11 | Transición → Risk-OFF | no | +2.0% | -7.8% | -5.4% |
| 2023-02-10 | Transición → Risk-OFF | no | +1.1% | +2.6% | -9.1% |
| 2023-07-07 | Transición → Risk-OFF | no | +1.7% | -5.5% | -5.2% |
| 2008-09-26 | Transición → Risk-OFF | no | +10.1% | +20.2% | +18.7% |
| 2018-12-28 | Transición → Risk-OFF | no | -1.9% | -6.0% | -5.0% |
| 2022-11-11 | Transición → Risk-OFF | no | +2.0% | -7.8% | -5.4% |
| 2023-02-10 | Transición → Risk-OFF | no | +1.1% | +2.6% | -9.1% |
| 2023-07-07 | Transición → Risk-OFF | no | +1.7% | -5.5% | -5.2% |
| 2024-01-12 | Transición → Risk-OFF | no | -5.6% | -13.8% | -19.3% |
| 2024-04-12 | Transición → Risk-OFF | no | +5.0% | -4.5% | -1.9% |
| 2024-07-26 | Transición → Risk-OFF | no | +1.3% | -7.4% | -16.8% |
| 2025-10-10 | Transición → Risk-OFF | no | -3.5% | +2.6% | +3.9% |

**Alpha 13w basket completo:** -1.1%  n=14
**Alpha 13w regimen deflacionario:** -1.1%  n=14
**Alpha 13w regimen inflacionario:** —  n=0
**Falsos positivos (basket underperforma SPY en 4w):** 4/14 (29%)

---

## Sección 6 — Modo A vs Modo B (2023-04-18 en adelante)

- COMPRA: Modo A α13w=+0.0%  Modo B α13w=-4.3%  nA=190  nB=111
- ACUMULAR: Modo A α13w=-1.7%  Modo B α13w=-1.8%  nA=314  nB=279
- VIGILAR: Modo A α13w=+0.5%  Modo B α13w=+0.6%  nA=2343  nB=2434

---

## Sección 7 — Limitaciones y caveats

1. **Autocorrelacion:** una señal COMPRA persistente genera observaciones correlacionadas. Se reporta `n_independent` (primer punto de cada bloque) para el t-stat.
2. **Muestra pequena en ROT. TEMPRANA:** 32-36 señales en total (ambos modos) limita la significancia estadistica.
3. **Un unico ciclo secular:** el periodo 2005-2026 es mayoritariamente alcista; los alphas en regimenes de estres pueden estar infraestimados.
4. **HY ausente pre-2023:** el Modo B infravalora el estres en crisis pre-2023. Afecta regimenes de capitulacion/risk-off historicos.
5. **Sin costes de transaccion ni slippage:** los alphas son brutos.
6. **No es portfolio real:** se analiza el alpha de cada señal individualmente, no una estrategia de portfolio con sizing y rebalance.

---

## Conclusiones

**¿Las señales COMPRA dan alpha?**  Alpha medio 13w = +2.4%, hit rate = +49.4%, t-stat = 0.45. NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena).

**¿ROT. TEMPRANA adelanta?**  DEBIL — solo 44% convergen.

**¿El framework detecta crisis?**  NO — alpha medio negativo (-1.1% a 13w en transiciones).

