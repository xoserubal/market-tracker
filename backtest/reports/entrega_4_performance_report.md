# Entrega 4 — Performance Report: RotationScore Signal Backtest

## Resumen ejecutivo

**Veredicto:** NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)

- Señales COMPRA — alpha medio 13w (Modo A): +2.4%  | hit rate: +49.8%  | t-stat: 0.45
- ROT. TEMPRANA: 37% convergen a COMPRA/ACUMULAR  | lead time mediano: 21w
- Recession basket: alpha medio 13w en transiciones = -0.5%

---

## Sección 1 — Alpha por tipo de señal

### Modo A

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1185 | 18 | +1.2% | -0.1% | +10.2% | 0.48 | +48.3% |
| COMPRA | 13w | 1150 | 18 | +2.4% | -0.0% | +22.6% | 0.45 | +49.8% |
| COMPRA | 26w | 1128 | 18 | +4.6% | -0.9% | +41.2% | 0.47 | +46.5% |
| ACUMULAR | 4w | 1983 | 18 | -0.0% | -0.2% | +5.2% | -0.03 | +47.8% |
| ACUMULAR | 13w | 1970 | 18 | +0.1% | -0.6% | +11.3% | 0.02 | +45.2% |
| ACUMULAR | 26w | 1951 | 18 | +0.0% | -1.1% | +15.6% | 0.01 | +46.1% |
| ROT. TEMPRANA | 4w | 54 | 17 | -1.3% | -0.8% | +5.3% | -1.03 | +40.7% |
| ROT. TEMPRANA | 13w | 48 | 17 | +2.0% | +2.0% | +7.3% | 1.12 | +60.4% |
| ROT. TEMPRANA | 26w | 47 | 16 | +3.5% | +2.4% | +8.8% | 1.58 | +66.0% |
| VIGILAR | 4w | 9576 | 19 | +0.1% | -0.1% | +5.5% | 0.08 | +48.6% |
| VIGILAR | 13w | 9492 | 19 | +0.4% | -0.3% | +12.7% | 0.14 | +47.6% |
| VIGILAR | 26w | 9337 | 19 | +1.2% | -0.4% | +24.5% | 0.21 | +48.1% |
| IGNORAR | 4w | 6213 | 19 | +0.0% | -0.0% | +6.1% | 0.02 | +49.8% |
| IGNORAR | 13w | 6180 | 19 | +0.4% | +0.1% | +11.6% | 0.15 | +50.2% |
| IGNORAR | 26w | 6130 | 19 | +0.8% | -0.5% | +18.3% | 0.18 | +48.1% |
| ACUMULAR* | 4w | 117 | 12 | -1.8% | -1.8% | +8.0% | -0.79 | +36.8% |
| ACUMULAR* | 13w | 117 | 12 | -4.8% | -5.2% | +13.7% | -1.20 | +29.1% |
| ACUMULAR* | 26w | 117 | 12 | -13.3% | -13.3% | +15.0% | -3.06 | +12.8% |

### Modo B

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1143 | 18 | +1.0% | -0.2% | +10.2% | 0.41 | +47.9% |
| COMPRA | 13w | 1114 | 18 | +2.1% | -0.1% | +22.6% | 0.39 | +48.9% |
| COMPRA | 26w | 1108 | 18 | +3.9% | -1.1% | +40.9% | 0.41 | +45.7% |
| ACUMULAR | 4w | 1962 | 18 | +0.0% | -0.1% | +5.2% | 0.02 | +48.6% |
| ACUMULAR | 13w | 1947 | 18 | +0.0% | -0.6% | +11.2% | 0.01 | +45.5% |
| ACUMULAR | 26w | 1934 | 18 | -0.3% | -1.2% | +14.4% | -0.08 | +46.1% |
| ROT. TEMPRANA | 4w | 55 | 17 | -0.8% | -0.6% | +6.8% | -0.46 | +41.8% |
| ROT. TEMPRANA | 13w | 49 | 17 | +2.1% | +2.1% | +7.3% | 1.19 | +61.2% |
| ROT. TEMPRANA | 26w | 47 | 16 | +3.5% | +2.4% | +8.8% | 1.58 | +66.0% |
| VIGILAR | 4w | 9634 | 19 | +0.1% | -0.1% | +5.5% | 0.09 | +48.5% |
| VIGILAR | 13w | 9546 | 19 | +0.5% | -0.3% | +12.8% | 0.15 | +47.6% |
| VIGILAR | 26w | 9370 | 19 | +1.3% | -0.4% | +24.7% | 0.23 | +48.2% |
| IGNORAR | 4w | 6216 | 19 | +0.0% | -0.0% | +6.1% | 0.02 | +49.8% |
| IGNORAR | 13w | 6183 | 19 | +0.4% | +0.1% | +11.6% | 0.15 | +50.2% |
| IGNORAR | 26w | 6133 | 19 | +0.8% | -0.4% | +18.3% | 0.19 | +48.1% |
| ACUMULAR* | 4w | 118 | 11 | -2.0% | -2.0% | +8.1% | -0.82 | +35.6% |
| ACUMULAR* | 13w | 118 | 11 | -5.1% | -5.4% | +13.9% | -1.21 | +28.8% |
| ACUMULAR* | 26w | 118 | 11 | -13.6% | -13.9% | +15.1% | -2.98 | +12.7% |

---

## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 261 | +9.1% | +61.7% | 0.56 |
| Bull Maduro | 692 | +1.2% | +48.1% | 0.30 |
| Transición | 187 | -1.8% | +42.2% | -0.71 |
| Risk-OFF | 10 | -9.4% | +0.0% | -5.23 |

### Modo B

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 261 | +9.1% | +61.7% | 0.56 |
| Bull Maduro | 646 | +0.6% | +46.4% | 0.15 |
| Transición | 186 | -1.6% | +43.5% | -0.61 |
| Risk-OFF | 21 | -6.3% | +14.3% | -2.43 |

---

## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 187 | +12.9% | +65.8% | 0.58 |
| Commodities | 309 | +1.3% | +44.7% | 0.16 |
| Value/Cyclical | 419 | +0.9% | +49.6% | 0.27 |
| Small/EM | 73 | -0.6% | +50.7% | -0.07 |
| Defensive | 138 | -2.2% | +41.3% | -0.65 |
| Duration | 24 | -3.0% | +41.7% | -0.30 |

### Modo B

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 187 | +12.9% | +65.8% | 0.58 |
| Value/Cyclical | 397 | +0.8% | +49.1% | 0.25 |
| Commodities | 289 | +0.1% | +42.2% | 0.02 |
| Small/EM | 73 | -0.6% | +50.7% | -0.07 |
| Defensive | 144 | -2.4% | +40.3% | -0.71 |
| Duration | 24 | -3.0% | +41.7% | -0.30 |

---

## Sección 4 — ROT. TEMPRANA

Total ROT. TEMPRANA emitidas: **149** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **55** (37%)
- Lead time (semanas): media=17.9  mediana=21  IQR=[5, 24]
- Convergencia por señal:
  - ACUMULAR: 29
  - COMPRA: 26

**Alpha 13w desde ROT. TEMPRANA:** +2.0%  | n=97
**Alpha 13w desde señal convencional (convergencia):** +1.0%  | n=40

---

## Sección 5 — Recession basket

Transiciones a Risk-OFF/Capitulacion detectadas: **12**

| Fecha | Anterior → Nuevo | INFL | α4w | α13w | α26w |
|-------|-----------------|------|-----|------|------|
| 2008-09-26 | Transición → Risk-OFF | no | +10.1% | +20.2% | +18.7% |
| 2022-11-11 | Transición → Risk-OFF | no | +2.0% | -7.8% | -5.4% |
| 2023-02-10 | Transición → Risk-OFF | no | +1.1% | +2.6% | -9.1% |
| 2023-07-07 | Transición → Risk-OFF | no | +1.7% | -5.5% | -5.2% |
| 2008-09-26 | Transición → Risk-OFF | no | +10.1% | +20.2% | +18.7% |
| 2022-11-11 | Transición → Risk-OFF | no | +2.0% | -7.8% | -5.4% |
| 2023-02-10 | Transición → Risk-OFF | no | +1.1% | +2.6% | -9.1% |
| 2023-07-07 | Transición → Risk-OFF | no | +1.7% | -5.5% | -5.2% |
| 2024-01-12 | Transición → Risk-OFF | no | -5.6% | -13.8% | -19.3% |
| 2024-04-12 | Transición → Risk-OFF | no | +5.0% | -4.5% | -1.9% |
| 2024-10-11 | Transición → Risk-OFF | no | -4.7% | -9.8% | +8.4% |
| 2025-10-10 | Transición → Risk-OFF | no | -3.5% | +2.6% | +3.9% |

**Alpha 13w basket completo:** -0.5%  n=12
**Alpha 13w regimen deflacionario:** -0.5%  n=12
**Alpha 13w regimen inflacionario:** —  n=0
**Falsos positivos (basket underperforma SPY en 4w):** 3/12 (25%)

---

## Sección 6 — Modo A vs Modo B (2023-04-18 en adelante)

- COMPRA: Modo A α13w=+0.2%  Modo B α13w=-4.9%  nA=206  nB=146
- ACUMULAR: Modo A α13w=-1.8%  Modo B α13w=-2.1%  nA=330  nB=305
- VIGILAR: Modo A α13w=+0.4%  Modo B α13w=+0.7%  nA=2428  nB=2503

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

**¿Las señales COMPRA dan alpha?**  Alpha medio 13w = +2.4%, hit rate = +49.8%, t-stat = 0.45. NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena).

**¿ROT. TEMPRANA adelanta?**  DEBIL — solo 37% convergen.

**¿El framework detecta crisis?**  NO — alpha medio negativo (-0.5% a 13w en transiciones).

