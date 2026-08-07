# Entrega 4 — Performance Report: RotationScore Signal Backtest

## Resumen ejecutivo

**Veredicto:** NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)

- Señales COMPRA — alpha medio 13w (Modo A): +2.6%  | hit rate: +49.8%  | t-stat: 0.46
- ROT. TEMPRANA: 41% convergen a COMPRA/ACUMULAR  | lead time mediano: 22w
- Recession basket: alpha medio 13w en transiciones = -1.1%

---

## Sección 1 — Alpha por tipo de señal

### Modo A

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1057 | 17 | +1.0% | -0.3% | +10.0% | 0.39 | +47.1% |
| COMPRA | 13w | 1030 | 17 | +2.6% | -0.0% | +23.4% | 0.46 | +49.8% |
| COMPRA | 26w | 1008 | 17 | +5.0% | -0.8% | +43.1% | 0.48 | +46.4% |
| ACUMULAR | 4w | 1869 | 17 | -0.1% | -0.3% | +5.0% | -0.10 | +46.5% |
| ACUMULAR | 13w | 1857 | 17 | -0.1% | -0.7% | +11.0% | -0.03 | +44.0% |
| ACUMULAR | 26w | 1839 | 17 | +0.1% | -1.0% | +15.3% | 0.02 | +46.2% |
| ROT. TEMPRANA | 4w | 53 | 15 | -1.2% | -0.6% | +5.4% | -0.88 | +43.4% |
| ROT. TEMPRANA | 13w | 47 | 15 | +2.6% | +2.2% | +7.1% | 1.40 | +63.8% |
| ROT. TEMPRANA | 26w | 45 | 14 | +3.8% | +3.5% | +8.8% | 1.64 | +68.9% |
| VIGILAR | 4w | 9248 | 18 | +0.1% | -0.1% | +5.4% | 0.11 | +48.9% |
| VIGILAR | 13w | 9164 | 18 | +0.5% | -0.3% | +12.6% | 0.17 | +48.2% |
| VIGILAR | 26w | 9018 | 18 | +1.4% | -0.3% | +24.5% | 0.24 | +48.6% |
| IGNORAR | 4w | 5813 | 18 | +0.1% | +0.0% | +5.7% | 0.07 | +50.2% |
| IGNORAR | 13w | 5780 | 18 | +0.4% | +0.1% | +10.7% | 0.17 | +50.6% |
| IGNORAR | 26w | 5734 | 18 | +1.0% | -0.3% | +17.7% | 0.24 | +48.9% |
| ACUMULAR* | 4w | 117 | 11 | -1.8% | -1.7% | +8.0% | -0.75 | +36.8% |
| ACUMULAR* | 13w | 117 | 11 | -4.7% | -5.1% | +13.7% | -1.14 | +29.9% |
| ACUMULAR* | 26w | 117 | 11 | -13.4% | -13.6% | +14.9% | -2.98 | +12.0% |

### Modo B

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1006 | 17 | +0.8% | -0.3% | +10.0% | 0.33 | +46.7% |
| COMPRA | 13w | 982 | 17 | +2.4% | -0.1% | +23.6% | 0.41 | +49.3% |
| COMPRA | 26w | 976 | 17 | +4.5% | -0.9% | +43.1% | 0.43 | +46.1% |
| ACUMULAR | 4w | 1849 | 17 | -0.0% | -0.2% | +5.0% | -0.04 | +47.4% |
| ACUMULAR | 13w | 1835 | 17 | -0.1% | -0.7% | +10.9% | -0.02 | +44.6% |
| ACUMULAR | 26w | 1822 | 17 | -0.3% | -1.0% | +14.0% | -0.08 | +46.2% |
| ROT. TEMPRANA | 4w | 54 | 15 | -0.6% | -0.6% | +6.9% | -0.36 | +44.4% |
| ROT. TEMPRANA | 13w | 48 | 15 | +2.7% | +2.3% | +7.1% | 1.47 | +64.6% |
| ROT. TEMPRANA | 26w | 45 | 14 | +3.8% | +3.5% | +8.8% | 1.64 | +68.9% |
| VIGILAR | 4w | 9316 | 18 | +0.1% | -0.1% | +5.4% | 0.11 | +48.8% |
| VIGILAR | 13w | 9231 | 18 | +0.5% | -0.3% | +12.7% | 0.18 | +48.1% |
| VIGILAR | 26w | 9065 | 18 | +1.5% | -0.3% | +24.8% | 0.26 | +48.6% |
| IGNORAR | 4w | 5814 | 18 | +0.1% | +0.0% | +5.7% | 0.07 | +50.2% |
| IGNORAR | 13w | 5781 | 18 | +0.4% | +0.1% | +10.7% | 0.18 | +50.6% |
| IGNORAR | 26w | 5735 | 18 | +1.0% | -0.3% | +17.7% | 0.25 | +49.0% |
| ACUMULAR* | 4w | 118 | 10 | -2.0% | -1.9% | +8.1% | -0.78 | +35.6% |
| ACUMULAR* | 13w | 118 | 10 | -5.0% | -5.3% | +13.9% | -1.14 | +29.7% |
| ACUMULAR* | 26w | 118 | 10 | -13.7% | -14.3% | +15.0% | -2.89 | +11.9% |

---

## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 246 | +9.8% | +61.4% | 0.54 |
| Bull Maduro | 580 | +1.4% | +49.3% | 0.34 |
| Transición | 196 | -2.4% | +38.8% | -0.95 |
| Risk-OFF | 8 | -8.9% | +0.0% | -4.58 |

### Modo B

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 246 | +9.8% | +61.4% | 0.54 |
| Bull Maduro | 536 | +0.7% | +47.4% | 0.19 |
| Transición | 162 | -1.0% | +45.7% | -0.42 |
| Risk-OFF | 38 | -7.1% | +13.2% | -2.53 |

---

## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 177 | +13.5% | +64.4% | 0.59 |
| Commodities | 183 | +2.0% | +44.8% | 0.19 |
| Value/Cyclical | 430 | +0.9% | +50.0% | 0.26 |
| Small/EM | 69 | +0.1% | +53.6% | 0.01 |
| Defensive | 143 | -2.6% | +38.5% | -0.77 |
| Duration | 28 | -3.9% | +35.7% | -0.40 |

### Modo B

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 177 | +13.5% | +64.4% | 0.59 |
| Value/Cyclical | 408 | +0.8% | +49.5% | 0.24 |
| Small/EM | 69 | +0.1% | +53.6% | 0.01 |
| Commodities | 164 | -0.0% | +40.2% | -0.00 |
| Defensive | 136 | -2.1% | +40.4% | -0.67 |
| Duration | 28 | -3.9% | +35.7% | -0.40 |

---

## Sección 4 — ROT. TEMPRANA

Total ROT. TEMPRANA emitidas: **149** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **61** (41%)
- Lead time (semanas): media=20.2  mediana=22  IQR=[8, 39]
- Convergencia por señal:
  - ACUMULAR: 33
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

- COMPRA: Modo A α13w=+0.1%  Modo B α13w=-4.3%  nA=185  nB=116
- ACUMULAR: Modo A α13w=-1.8%  Modo B α13w=-1.8%  nA=304  nB=278
- VIGILAR: Modo A α13w=+0.6%  Modo B α13w=+0.8%  nA=2285  nB=2372

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

**¿Las señales COMPRA dan alpha?**  Alpha medio 13w = +2.6%, hit rate = +49.8%, t-stat = 0.46. NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena).

**¿ROT. TEMPRANA adelanta?**  DEBIL — solo 41% convergen.

**¿El framework detecta crisis?**  NO — alpha medio negativo (-1.1% a 13w en transiciones).

