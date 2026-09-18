# Entrega 4 — Performance Report: RotationScore Signal Backtest

## Resumen ejecutivo

**Veredicto:** NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)

- Señales COMPRA — alpha medio 13w (Modo A): +2.4%  | hit rate: +49.3%  | t-stat: 0.44
- ROT. TEMPRANA: 40% convergen a COMPRA/ACUMULAR  | lead time mediano: 22w
- Recession basket: alpha medio 13w en transiciones = -1.1%

---

## Sección 1 — Alpha por tipo de señal

### Modo A

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1189 | 18 | +1.1% | -0.2% | +10.2% | 0.47 | +48.3% |
| COMPRA | 13w | 1154 | 18 | +2.4% | -0.1% | +22.5% | 0.44 | +49.3% |
| COMPRA | 26w | 1132 | 18 | +4.5% | -0.8% | +41.1% | 0.47 | +46.6% |
| ACUMULAR | 4w | 1978 | 18 | -0.1% | -0.2% | +5.2% | -0.09 | +47.1% |
| ACUMULAR | 13w | 1965 | 18 | +0.0% | -0.6% | +11.3% | 0.02 | +44.9% |
| ACUMULAR | 26w | 1946 | 18 | +0.0% | -1.2% | +15.7% | 0.01 | +46.0% |
| ROT. TEMPRANA | 4w | 52 | 15 | -1.3% | -0.8% | +5.4% | -0.94 | +42.3% |
| ROT. TEMPRANA | 13w | 46 | 15 | +2.4% | +2.2% | +7.1% | 1.32 | +63.0% |
| ROT. TEMPRANA | 26w | 45 | 14 | +3.8% | +3.5% | +8.8% | 1.64 | +68.9% |
| VIGILAR | 4w | 9560 | 19 | +0.1% | -0.1% | +5.5% | 0.08 | +48.6% |
| VIGILAR | 13w | 9476 | 19 | +0.4% | -0.3% | +12.7% | 0.14 | +47.7% |
| VIGILAR | 26w | 9321 | 19 | +1.2% | -0.4% | +24.5% | 0.21 | +48.1% |
| IGNORAR | 4w | 6232 | 19 | +0.1% | +0.0% | +6.1% | 0.04 | +50.1% |
| IGNORAR | 13w | 6199 | 19 | +0.4% | +0.1% | +11.6% | 0.15 | +50.2% |
| IGNORAR | 26w | 6149 | 19 | +0.8% | -0.5% | +18.3% | 0.18 | +48.2% |
| ACUMULAR* | 4w | 117 | 12 | -1.8% | -1.8% | +8.0% | -0.79 | +36.8% |
| ACUMULAR* | 13w | 117 | 12 | -4.8% | -5.2% | +13.7% | -1.20 | +29.1% |
| ACUMULAR* | 26w | 117 | 12 | -13.3% | -13.3% | +15.0% | -3.06 | +12.8% |

### Modo B

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1134 | 18 | +1.0% | -0.2% | +10.2% | 0.41 | +47.9% |
| COMPRA | 13w | 1105 | 18 | +2.2% | -0.1% | +22.7% | 0.40 | +48.9% |
| COMPRA | 26w | 1099 | 18 | +4.1% | -0.9% | +41.1% | 0.42 | +46.3% |
| ACUMULAR | 4w | 1951 | 18 | -0.0% | -0.1% | +5.2% | -0.03 | +48.0% |
| ACUMULAR | 13w | 1936 | 18 | +0.1% | -0.6% | +11.2% | 0.02 | +45.4% |
| ACUMULAR | 26w | 1923 | 18 | -0.3% | -1.2% | +14.4% | -0.08 | +46.1% |
| ROT. TEMPRANA | 4w | 53 | 15 | -0.7% | -0.6% | +6.9% | -0.41 | +43.4% |
| ROT. TEMPRANA | 13w | 47 | 15 | +2.6% | +2.2% | +7.1% | 1.39 | +63.8% |
| ROT. TEMPRANA | 26w | 45 | 14 | +3.8% | +3.5% | +8.8% | 1.64 | +68.9% |
| VIGILAR | 4w | 9637 | 19 | +0.1% | -0.1% | +5.5% | 0.09 | +48.5% |
| VIGILAR | 13w | 9549 | 19 | +0.4% | -0.3% | +12.8% | 0.15 | +47.6% |
| VIGILAR | 26w | 9373 | 19 | +1.3% | -0.4% | +24.7% | 0.23 | +48.1% |
| IGNORAR | 4w | 6235 | 19 | +0.0% | +0.0% | +6.1% | 0.03 | +50.0% |
| IGNORAR | 13w | 6202 | 19 | +0.4% | +0.1% | +11.6% | 0.15 | +50.3% |
| IGNORAR | 26w | 6152 | 19 | +0.8% | -0.4% | +18.3% | 0.19 | +48.2% |
| ACUMULAR* | 4w | 118 | 11 | -2.0% | -2.0% | +8.1% | -0.82 | +35.6% |
| ACUMULAR* | 13w | 118 | 11 | -5.1% | -5.4% | +13.9% | -1.21 | +28.8% |
| ACUMULAR* | 26w | 118 | 11 | -13.6% | -13.9% | +15.1% | -2.98 | +12.7% |

---

## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 247 | +9.8% | +61.5% | 0.59 |
| Bull Maduro | 698 | +1.3% | +48.7% | 0.32 |
| Transición | 199 | -2.4% | +38.7% | -0.93 |
| Risk-OFF | 10 | -9.4% | +0.0% | -5.23 |

### Modo B

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 247 | +9.8% | +61.5% | 0.59 |
| Bull Maduro | 652 | +0.6% | +47.1% | 0.18 |
| Transición | 164 | -0.8% | +47.0% | -0.33 |
| Risk-OFF | 42 | -7.4% | +9.5% | -2.84 |

---

## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 177 | +13.5% | +64.4% | 0.59 |
| Commodities | 307 | +1.4% | +45.0% | 0.17 |
| Value/Cyclical | 430 | +0.9% | +50.0% | 0.26 |
| Small/EM | 69 | +0.1% | +53.6% | 0.01 |
| Defensive | 143 | -2.6% | +38.5% | -0.77 |
| Duration | 28 | -3.9% | +35.7% | -0.40 |

### Modo B

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 177 | +13.5% | +64.4% | 0.59 |
| Value/Cyclical | 408 | +0.8% | +49.5% | 0.24 |
| Commodities | 287 | +0.2% | +42.5% | 0.03 |
| Small/EM | 69 | +0.1% | +53.6% | 0.01 |
| Defensive | 136 | -2.1% | +40.4% | -0.67 |
| Duration | 28 | -3.9% | +35.7% | -0.40 |

---

## Sección 4 — ROT. TEMPRANA

Total ROT. TEMPRANA emitidas: **147** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **59** (40%)
- Lead time (semanas): media=20.8  mediana=22  IQR=[10, 39]
- Convergencia por señal:
  - ACUMULAR: 33
  - COMPRA: 26

**Alpha 13w desde ROT. TEMPRANA:** +2.5%  | n=93
**Alpha 13w desde señal convencional (convergencia):** +1.3%  | n=42

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

- COMPRA: Modo A α13w=+0.2%  Modo B α13w=-4.1%  nA=207  nB=134
- ACUMULAR: Modo A α13w=-1.8%  Modo B α13w=-1.9%  nA=330  nB=299
- VIGILAR: Modo A α13w=+0.4%  Modo B α13w=+0.6%  nA=2429  nB=2523

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

**¿Las señales COMPRA dan alpha?**  Alpha medio 13w = +2.4%, hit rate = +49.3%, t-stat = 0.44. NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena).

**¿ROT. TEMPRANA adelanta?**  DEBIL — solo 40% convergen.

**¿El framework detecta crisis?**  NO — alpha medio negativo (-1.1% a 13w en transiciones).

