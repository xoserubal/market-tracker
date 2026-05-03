# Entrega 4 — Performance Report: RotationScore Signal Backtest

## Resumen ejecutivo

**Veredicto:** NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)

- Señales COMPRA — alpha medio 13w (Modo A): +2.9%  | hit rate: +50.2%  | t-stat: 0.51
- ROT. TEMPRANA: 64% convergen a COMPRA/ACUMULAR  | lead time mediano: 21w
- Recession basket: alpha medio 13w en transiciones = -1.2%

---

## Sección 1 — Alpha por tipo de señal

### Modo A

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1077 | 18 | +1.3% | -0.1% | +10.8% | 0.51 | +48.6% |
| COMPRA | 13w | 1043 | 18 | +2.9% | +0.0% | +24.0% | 0.51 | +50.2% |
| COMPRA | 26w | 1027 | 18 | +5.6% | -0.3% | +43.7% | 0.55 | +48.6% |
| ACUMULAR | 4w | 1985 | 18 | -0.1% | -0.2% | +5.3% | -0.09 | +47.3% |
| ACUMULAR | 13w | 1972 | 18 | -0.2% | -0.8% | +11.0% | -0.08 | +44.2% |
| ACUMULAR | 26w | 1946 | 18 | -0.3% | -1.4% | +15.0% | -0.07 | +44.3% |
| ROT. TEMPRANA | 4w | 32 | 12 | +0.6% | -0.5% | +4.8% | 0.43 | +46.9% |
| ROT. TEMPRANA | 13w | 32 | 12 | +6.9% | +6.0% | +8.6% | 2.77 | +81.2% |
| ROT. TEMPRANA | 26w | 30 | 12 | +10.3% | +6.7% | +14.5% | 2.46 | +83.3% |
| VIGILAR | 4w | 9888 | 19 | +0.1% | -0.1% | +5.5% | 0.07 | +48.5% |
| VIGILAR | 13w | 9801 | 19 | +0.4% | -0.3% | +12.7% | 0.14 | +47.9% |
| VIGILAR | 26w | 9646 | 19 | +1.2% | -0.3% | +24.4% | 0.22 | +48.4% |
| IGNORAR | 4w | 6034 | 19 | +0.0% | +0.0% | +6.1% | 0.03 | +50.1% |
| IGNORAR | 13w | 5997 | 19 | +0.4% | -0.0% | +11.5% | 0.16 | +49.9% |
| IGNORAR | 26w | 5949 | 19 | +0.6% | -0.6% | +17.8% | 0.16 | +47.8% |
| ACUMULAR* | 4w | 112 | 10 | -1.7% | -1.3% | +8.1% | -0.65 | +38.4% |
| ACUMULAR* | 13w | 112 | 10 | -4.7% | -5.1% | +13.4% | -1.12 | +30.4% |
| ACUMULAR* | 26w | 112 | 10 | -13.5% | -13.4% | +15.1% | -2.82 | +12.5% |

### Modo B

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1043 | 18 | +1.2% | -0.1% | +10.8% | 0.47 | +48.4% |
| COMPRA | 13w | 1009 | 18 | +2.7% | +0.0% | +24.2% | 0.48 | +50.0% |
| COMPRA | 26w | 997 | 18 | +5.1% | -0.5% | +43.8% | 0.50 | +48.2% |
| ACUMULAR | 4w | 1946 | 18 | -0.0% | -0.2% | +5.3% | -0.04 | +48.0% |
| ACUMULAR | 13w | 1933 | 18 | -0.2% | -0.8% | +10.9% | -0.06 | +44.4% |
| ACUMULAR | 26w | 1917 | 18 | -0.6% | -1.4% | +13.6% | -0.19 | +44.3% |
| ROT. TEMPRANA | 4w | 34 | 12 | +2.2% | +0.3% | +8.1% | 0.95 | +50.0% |
| ROT. TEMPRANA | 13w | 34 | 12 | +7.7% | +6.4% | +9.5% | 2.79 | +82.4% |
| ROT. TEMPRANA | 26w | 30 | 12 | +10.3% | +6.7% | +14.5% | 2.46 | +83.3% |
| VIGILAR | 4w | 9955 | 19 | +0.1% | -0.1% | +5.5% | 0.07 | +48.4% |
| VIGILAR | 13w | 9868 | 19 | +0.4% | -0.3% | +12.7% | 0.14 | +47.8% |
| VIGILAR | 26w | 9701 | 19 | +1.3% | -0.3% | +24.6% | 0.24 | +48.4% |
| IGNORAR | 4w | 6034 | 19 | +0.0% | +0.0% | +6.1% | 0.03 | +50.0% |
| IGNORAR | 13w | 5997 | 19 | +0.4% | +0.0% | +11.5% | 0.16 | +50.0% |
| IGNORAR | 26w | 5949 | 19 | +0.7% | -0.6% | +17.8% | 0.16 | +47.9% |
| ACUMULAR* | 4w | 116 | 10 | -1.9% | -1.5% | +8.1% | -0.73 | +37.1% |
| ACUMULAR* | 13w | 116 | 10 | -5.2% | -5.4% | +13.5% | -1.22 | +29.3% |
| ACUMULAR* | 26w | 116 | 10 | -13.8% | -13.9% | +15.1% | -2.89 | +12.1% |

---

## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 213 | +11.7% | +61.0% | 0.60 |
| Bull Maduro | 638 | +1.5% | +50.0% | 0.35 |
| Transición | 180 | -1.6% | +41.7% | -0.63 |
| Risk-OFF | 12 | -10.2% | +0.0% | -4.87 |

### Modo B

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 213 | +11.7% | +61.0% | 0.60 |
| Bull Maduro | 607 | +1.0% | +48.8% | 0.24 |
| Transición | 148 | -0.1% | +50.7% | -0.04 |
| Risk-OFF | 41 | -8.0% | +9.8% | -2.81 |

---

## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 160 | +15.4% | +62.5% | 0.63 |
| Commodities | 322 | +1.5% | +46.0% | 0.18 |
| Value/Cyclical | 356 | +1.3% | +52.8% | 0.38 |
| Small/EM | 53 | +0.6% | +56.6% | 0.08 |
| Defensive | 121 | -1.9% | +40.5% | -0.57 |
| Duration | 31 | -5.9% | +29.0% | -0.61 |

### Modo B

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 160 | +15.4% | +62.5% | 0.63 |
| Value/Cyclical | 345 | +1.4% | +53.0% | 0.40 |
| Small/EM | 53 | +0.6% | +56.6% | 0.08 |
| Commodities | 305 | +0.4% | +43.6% | 0.05 |
| Defensive | 115 | -1.6% | +43.5% | -0.49 |
| Duration | 31 | -5.9% | +29.0% | -0.61 |

---

## Sección 4 — ROT. TEMPRANA

Total ROT. TEMPRANA emitidas: **66** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **42** (64%)
- Lead time (semanas): media=20.5  mediana=21  IQR=[10, 22]
- Convergencia por señal:
  - COMPRA: 22
  - ACUMULAR: 20

**Alpha 13w desde ROT. TEMPRANA:** +7.3%  | n=66
**Alpha 13w desde señal convencional (convergencia):** +1.2%  | n=42

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

- COMPRA: Modo A α13w=+0.6%  Modo B α13w=-3.5%  nA=144  nB=112
- ACUMULAR: Modo A α13w=-1.7%  Modo B α13w=-1.6%  nA=286  nB=240
- VIGILAR: Modo A α13w=+0.4%  Modo B α13w=+0.5%  nA=1854  nB=1926

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

**¿Las señales COMPRA dan alpha?**  Alpha medio 13w = +2.9%, hit rate = +50.2%, t-stat = 0.51. NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena).

**¿ROT. TEMPRANA adelanta?**  SI — convergen 64% con lead time mediano 21w.

**¿El framework detecta crisis?**  NO — alpha medio negativo (-1.2% a 13w en transiciones).

