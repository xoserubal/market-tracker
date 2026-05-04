# Entrega 4 — Performance Report: RotationScore Signal Backtest

## Resumen ejecutivo

**Veredicto:** NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)

- Señales COMPRA — alpha medio 13w (Modo A): +2.4%  | hit rate: +49.4%  | t-stat: 0.45
- ROT. TEMPRANA: 51% convergen a COMPRA/ACUMULAR  | lead time mediano: 22w
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
| ROT. TEMPRANA | 4w | 50 | 13 | -0.1% | +0.6% | +5.6% | -0.06 | +54.0% |
| ROT. TEMPRANA | 13w | 50 | 13 | +4.1% | +4.2% | +7.1% | 2.09 | +72.0% |
| ROT. TEMPRANA | 26w | 48 | 13 | +5.0% | +3.1% | +9.1% | 1.97 | +66.7% |
| VIGILAR | 4w | 9657 | 19 | +0.1% | -0.1% | +5.5% | 0.08 | +48.6% |
| VIGILAR | 13w | 9565 | 19 | +0.4% | -0.3% | +12.7% | 0.13 | +47.7% |
| VIGILAR | 26w | 9412 | 19 | +1.2% | -0.4% | +24.5% | 0.21 | +48.1% |
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
| ROT. TEMPRANA | 4w | 52 | 13 | +1.0% | +0.7% | +7.8% | 0.46 | +55.8% |
| ROT. TEMPRANA | 13w | 52 | 13 | +4.8% | +4.3% | +8.1% | 2.12 | +73.1% |
| ROT. TEMPRANA | 26w | 48 | 13 | +5.0% | +3.1% | +9.1% | 1.97 | +66.7% |
| VIGILAR | 4w | 9734 | 19 | +0.1% | -0.1% | +5.5% | 0.07 | +48.4% |
| VIGILAR | 13w | 9642 | 19 | +0.4% | -0.4% | +12.7% | 0.13 | +47.5% |
| VIGILAR | 26w | 9477 | 19 | +1.3% | -0.4% | +24.7% | 0.23 | +48.1% |
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

Total ROT. TEMPRANA emitidas: **102** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **52** (51%)
- Lead time (semanas): media=19.8  mediana=22  IQR=[10, 24]
- Convergencia por señal:
  - ACUMULAR: 30
  - COMPRA: 22

**Alpha 13w desde ROT. TEMPRANA:** +4.5%  | n=102
**Alpha 13w desde señal convencional (convergencia):** +1.9%  | n=52

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

- COMPRA: Modo A α13w=-0.1%  Modo B α13w=-3.3%  nA=176  nB=133
- ACUMULAR: Modo A α13w=-1.9%  Modo B α13w=-1.4%  nA=299  nB=256
- VIGILAR: Modo A α13w=+0.5%  Modo B α13w=+0.5%  nA=1850  nB=1932

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

**¿ROT. TEMPRANA adelanta?**  SI — convergen 51% con lead time mediano 22w.

**¿El framework detecta crisis?**  NO — alpha medio negativo (-1.2% a 13w en transiciones).

