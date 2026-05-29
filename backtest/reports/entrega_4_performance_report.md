# Entrega 4 — Performance Report: RotationScore Signal Backtest

## Resumen ejecutivo

**Veredicto:** NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)

- Señales COMPRA — alpha medio 13w (Modo A): +2.4%  | hit rate: +49.4%  | t-stat: 0.45
- ROT. TEMPRANA: 52% convergen a COMPRA/ACUMULAR  | lead time mediano: 20w
- Recession basket: alpha medio 13w en transiciones = -1.2%

---

## Sección 1 — Alpha por tipo de señal

### Modo A

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1246 | 18 | +1.1% | -0.2% | +10.1% | 0.45 | +48.1% |
| COMPRA | 13w | 1211 | 18 | +2.4% | -0.1% | +22.4% | 0.45 | +49.4% |
| COMPRA | 26w | 1188 | 18 | +4.5% | -0.9% | +40.7% | 0.46 | +46.1% |
| ACUMULAR | 4w | 2047 | 18 | -0.1% | -0.2% | +5.2% | -0.11 | +46.8% |
| ACUMULAR | 13w | 2034 | 18 | -0.1% | -0.7% | +10.9% | -0.04 | +44.1% |
| ACUMULAR | 26w | 2015 | 18 | -0.1% | -1.3% | +14.9% | -0.03 | +45.8% |
| ROT. TEMPRANA | 4w | 67 | 15 | -0.2% | +0.4% | +5.7% | -0.12 | +52.2% |
| ROT. TEMPRANA | 13w | 61 | 15 | +3.3% | +3.0% | +7.1% | 1.81 | +68.9% |
| ROT. TEMPRANA | 26w | 58 | 15 | +4.0% | +2.9% | +9.2% | 1.66 | +63.8% |
| VIGILAR | 4w | 9640 | 19 | +0.1% | -0.1% | +5.5% | 0.08 | +48.6% |
| VIGILAR | 13w | 9554 | 19 | +0.4% | -0.3% | +12.7% | 0.14 | +47.7% |
| VIGILAR | 26w | 9402 | 19 | +1.2% | -0.4% | +24.5% | 0.21 | +48.1% |
| IGNORAR | 4w | 6005 | 19 | +0.1% | +0.0% | +6.2% | 0.04 | +50.1% |
| IGNORAR | 13w | 5974 | 19 | +0.4% | +0.1% | +11.7% | 0.17 | +50.5% |
| IGNORAR | 26w | 5924 | 19 | +0.8% | -0.4% | +18.3% | 0.19 | +48.3% |
| ACUMULAR* | 4w | 123 | 12 | -1.8% | -1.7% | +7.9% | -0.80 | +36.6% |
| ACUMULAR* | 13w | 123 | 12 | -4.8% | -5.2% | +13.4% | -1.23 | +28.5% |
| ACUMULAR* | 26w | 123 | 12 | -13.1% | -13.1% | +14.7% | -3.09 | +12.2% |

### Modo B

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1201 | 18 | +1.0% | -0.2% | +10.2% | 0.43 | +48.0% |
| COMPRA | 13w | 1166 | 18 | +2.2% | -0.1% | +22.5% | 0.42 | +49.2% |
| COMPRA | 26w | 1152 | 18 | +4.0% | -0.9% | +40.7% | 0.42 | +45.9% |
| ACUMULAR | 4w | 2011 | 18 | -0.1% | -0.2% | +5.2% | -0.05 | +47.7% |
| ACUMULAR | 13w | 1998 | 18 | -0.0% | -0.7% | +10.9% | -0.01 | +44.7% |
| ACUMULAR | 26w | 1984 | 18 | -0.4% | -1.2% | +13.6% | -0.14 | +45.8% |
| ROT. TEMPRANA | 4w | 69 | 15 | +0.7% | +0.4% | +7.4% | 0.34 | +53.6% |
| ROT. TEMPRANA | 13w | 63 | 15 | +3.9% | +3.6% | +8.0% | 1.87 | +69.8% |
| ROT. TEMPRANA | 26w | 58 | 15 | +4.0% | +2.9% | +9.2% | 1.66 | +63.8% |
| VIGILAR | 4w | 9717 | 19 | +0.1% | -0.1% | +5.5% | 0.08 | +48.4% |
| VIGILAR | 13w | 9631 | 19 | +0.4% | -0.4% | +12.8% | 0.13 | +47.5% |
| VIGILAR | 26w | 9467 | 19 | +1.3% | -0.4% | +24.7% | 0.23 | +48.1% |
| IGNORAR | 4w | 6005 | 19 | +0.1% | +0.0% | +6.2% | 0.04 | +50.1% |
| IGNORAR | 13w | 5974 | 19 | +0.5% | +0.1% | +11.7% | 0.17 | +50.6% |
| IGNORAR | 26w | 5924 | 19 | +0.8% | -0.4% | +18.3% | 0.20 | +48.3% |
| ACUMULAR* | 4w | 125 | 11 | -2.0% | -1.8% | +7.9% | -0.83 | +35.2% |
| ACUMULAR* | 13w | 125 | 11 | -5.1% | -5.4% | +13.5% | -1.25 | +28.0% |
| ACUMULAR* | 26w | 125 | 11 | -13.3% | -13.3% | +14.8% | -2.99 | +12.0% |

---

## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 260 | +9.6% | +61.2% | 0.54 |
| Bull Maduro | 739 | +1.3% | +48.7% | 0.32 |
| Transición | 204 | -2.5% | +38.7% | -0.96 |
| Risk-OFF | 8 | -8.9% | +0.0% | -4.58 |

### Modo B

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 260 | +9.6% | +61.2% | 0.54 |
| Bull Maduro | 701 | +0.8% | +47.6% | 0.21 |
| Transición | 165 | -1.0% | +46.1% | -0.39 |
| Risk-OFF | 40 | -7.3% | +12.5% | -2.60 |

---

## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 189 | +13.2% | +64.0% | 0.58 |
| Commodities | 308 | +1.4% | +45.5% | 0.17 |
| Value/Cyclical | 465 | +0.9% | +49.9% | 0.27 |
| Small/EM | 71 | +0.2% | +53.5% | 0.02 |
| Defensive | 149 | -2.6% | +38.3% | -0.78 |
| Duration | 29 | -4.3% | +34.5% | -0.43 |

### Modo B

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 189 | +13.2% | +64.0% | 0.58 |
| Value/Cyclical | 447 | +1.0% | +50.1% | 0.29 |
| Commodities | 291 | +0.3% | +43.0% | 0.03 |
| Small/EM | 71 | +0.2% | +53.5% | 0.02 |
| Defensive | 139 | -2.1% | +40.3% | -0.67 |
| Duration | 29 | -4.3% | +34.5% | -0.43 |

---

## Sección 4 — ROT. TEMPRANA

Total ROT. TEMPRANA emitidas: **184** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **95** (52%)
- Lead time (semanas): media=19.4  mediana=20  IQR=[10, 24]
- Convergencia por señal:
  - ACUMULAR: 59
  - COMPRA: 36

**Alpha 13w desde ROT. TEMPRANA:** +3.6%  | n=124
**Alpha 13w desde señal convencional (convergencia):** +1.2%  | n=60

---

## Sección 5 — Recession basket

Transiciones a Risk-OFF/Capitulacion detectadas: **14**

| Fecha | Anterior → Nuevo | INFL | α4w | α13w | α26w |
|-------|-----------------|------|-----|------|------|
| 2008-09-26 | Transición → Risk-OFF | no | +10.1% | +20.2% | +18.7% |
| 2018-12-28 | Transición → Risk-OFF | no | -1.9% | -6.0% | -5.0% |
| 2022-11-11 | Transición → Risk-OFF | no | +2.0% | -7.8% | -5.4% |
| 2023-02-10 | Transición → Risk-OFF | no | +1.1% | +2.6% | -9.1% |
| 2023-08-11 | Transición → Risk-OFF | no | -7.4% | -6.2% | -16.1% |
| 2008-09-26 | Transición → Risk-OFF | no | +10.1% | +20.2% | +18.7% |
| 2018-12-28 | Transición → Risk-OFF | no | -1.9% | -6.0% | -5.0% |
| 2022-11-11 | Transición → Risk-OFF | no | +2.0% | -7.8% | -5.4% |
| 2023-02-10 | Transición → Risk-OFF | no | +1.1% | +2.6% | -9.1% |
| 2023-07-07 | Transición → Risk-OFF | no | +1.7% | -5.5% | -5.2% |
| 2024-01-12 | Transición → Risk-OFF | no | -5.6% | -13.8% | -19.3% |
| 2024-04-12 | Transición → Risk-OFF | no | +5.0% | -4.5% | -1.9% |
| 2024-07-26 | Transición → Risk-OFF | no | +1.3% | -7.4% | -16.8% |
| 2025-10-10 | Transición → Risk-OFF | no | -3.5% | +2.6% | +3.9% |

**Alpha 13w basket completo:** -1.2%  n=14
**Alpha 13w regimen deflacionario:** -1.2%  n=14
**Alpha 13w regimen inflacionario:** —  n=0
**Falsos positivos (basket underperforma SPY en 4w):** 5/14 (36%)

---

## Sección 6 — Modo A vs Modo B (2023-04-18 en adelante)

- COMPRA: Modo A α13w=-0.1%  Modo B α13w=-3.3%  nA=200  nB=141
- ACUMULAR: Modo A α13w=-1.9%  Modo B α13w=-1.4%  nA=318  nB=274
- VIGILAR: Modo A α13w=+0.5%  Modo B α13w=+0.5%  nA=2231  nB=2325

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

**¿ROT. TEMPRANA adelanta?**  SI — convergen 52% con lead time mediano 20w.

**¿El framework detecta crisis?**  NO — alpha medio negativo (-1.2% a 13w en transiciones).

