# Entrega 4 — Performance Report: RotationScore Signal Backtest

## Resumen ejecutivo

**Veredicto:** NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena)

- Señales COMPRA — alpha medio 13w (Modo A): +2.4%  | hit rate: +49.9%  | t-stat: 0.45
- ROT. TEMPRANA: 41% convergen a COMPRA/ACUMULAR  | lead time mediano: 14w
- Recession basket: alpha medio 13w en transiciones = -0.6%

---

## Sección 1 — Alpha por tipo de señal

### Modo A

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1177 | 18 | +1.1% | -0.2% | +10.3% | 0.47 | +48.0% |
| COMPRA | 13w | 1142 | 18 | +2.4% | -0.0% | +22.6% | 0.45 | +49.9% |
| COMPRA | 26w | 1120 | 18 | +4.6% | -0.9% | +41.3% | 0.47 | +46.5% |
| ACUMULAR | 4w | 1995 | 18 | -0.0% | -0.2% | +5.2% | -0.03 | +47.7% |
| ACUMULAR | 13w | 1982 | 18 | +0.0% | -0.6% | +11.3% | 0.01 | +44.9% |
| ACUMULAR | 26w | 1963 | 18 | +0.0% | -1.2% | +15.7% | 0.01 | +45.8% |
| ROT. TEMPRANA | 4w | 55 | 17 | -1.2% | -0.6% | +5.3% | -0.97 | +41.8% |
| ROT. TEMPRANA | 13w | 49 | 17 | +2.1% | +2.1% | +7.3% | 1.20 | +61.2% |
| ROT. TEMPRANA | 26w | 47 | 16 | +3.5% | +2.4% | +8.8% | 1.58 | +66.0% |
| VIGILAR | 4w | 9591 | 19 | +0.1% | -0.1% | +5.5% | 0.08 | +48.6% |
| VIGILAR | 13w | 9507 | 19 | +0.4% | -0.3% | +12.7% | 0.14 | +47.6% |
| VIGILAR | 26w | 9353 | 19 | +1.2% | -0.4% | +24.5% | 0.21 | +48.1% |
| IGNORAR | 4w | 6192 | 19 | +0.0% | -0.0% | +6.1% | 0.03 | +49.9% |
| IGNORAR | 13w | 6159 | 19 | +0.4% | +0.1% | +11.6% | 0.15 | +50.2% |
| IGNORAR | 26w | 6109 | 19 | +0.8% | -0.5% | +18.3% | 0.18 | +48.1% |
| ACUMULAR* | 4w | 118 | 12 | -1.8% | -1.7% | +8.0% | -0.79 | +36.4% |
| ACUMULAR* | 13w | 118 | 12 | -4.7% | -5.1% | +13.6% | -1.19 | +29.7% |
| ACUMULAR* | 26w | 118 | 12 | -13.3% | -13.4% | +15.0% | -3.08 | +12.7% |

### Modo B

| Señal | Hz | N obs | N ind. | Mean α | Median α | Std | t-stat | Hit% |
|-------|-----|-------|--------|--------|----------|-----|--------|------|
| COMPRA | 4w | 1132 | 18 | +0.8% | -0.2% | +9.7% | 0.34 | +47.3% |
| COMPRA | 13w | 1105 | 18 | +2.1% | -0.1% | +22.7% | 0.39 | +49.0% |
| COMPRA | 26w | 1099 | 18 | +4.0% | -1.1% | +41.1% | 0.41 | +45.8% |
| ACUMULAR | 4w | 1967 | 18 | +0.1% | -0.1% | +5.1% | 0.06 | +48.7% |
| ACUMULAR | 13w | 1955 | 18 | +0.0% | -0.6% | +11.2% | 0.00 | +45.2% |
| ACUMULAR | 26w | 1942 | 18 | -0.3% | -1.2% | +14.4% | -0.08 | +45.9% |
| ROT. TEMPRANA | 4w | 65 | 18 | +1.1% | -0.7% | +12.2% | 0.39 | +41.5% |
| ROT. TEMPRANA | 13w | 50 | 17 | +2.3% | +2.2% | +7.3% | 1.28 | +62.0% |
| ROT. TEMPRANA | 26w | 47 | 16 | +3.5% | +2.4% | +8.8% | 1.58 | +66.0% |
| VIGILAR | 4w | 9647 | 19 | +0.1% | -0.1% | +5.6% | 0.09 | +48.5% |
| VIGILAR | 13w | 9566 | 19 | +0.5% | -0.3% | +12.8% | 0.16 | +47.6% |
| VIGILAR | 26w | 9391 | 19 | +1.3% | -0.4% | +24.7% | 0.23 | +48.2% |
| IGNORAR | 4w | 6198 | 19 | +0.0% | -0.0% | +6.2% | 0.02 | +49.8% |
| IGNORAR | 13w | 6162 | 19 | +0.4% | +0.1% | +11.6% | 0.15 | +50.2% |
| IGNORAR | 26w | 6112 | 19 | +0.8% | -0.5% | +18.3% | 0.19 | +48.2% |
| ACUMULAR* | 4w | 119 | 11 | -2.0% | -1.9% | +8.1% | -0.82 | +35.3% |
| ACUMULAR* | 13w | 119 | 11 | -5.0% | -5.3% | +13.8% | -1.20 | +29.4% |
| ACUMULAR* | 26w | 119 | 11 | -13.6% | -14.2% | +15.0% | -3.00 | +12.6% |

---

## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 260 | +9.1% | +61.5% | 0.52 |
| Bull Maduro | 689 | +1.2% | +48.2% | 0.30 |
| Transición | 185 | -1.9% | +42.2% | -0.73 |
| Risk-OFF | 8 | -8.9% | +0.0% | -4.58 |

### Modo B

| Regimen | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Bull Pleno | 260 | +9.1% | +61.5% | 0.52 |
| Bull Maduro | 644 | +0.6% | +46.6% | 0.16 |
| Transición | 182 | -1.7% | +43.4% | -0.66 |
| Risk-OFF | 19 | -5.8% | +15.8% | -2.23 |

---

## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 187 | +12.9% | +65.8% | 0.58 |
| Commodities | 300 | +1.4% | +45.0% | 0.17 |
| Value/Cyclical | 419 | +0.9% | +49.6% | 0.27 |
| Small/EM | 73 | -0.6% | +50.7% | -0.07 |
| Defensive | 139 | -2.2% | +41.0% | -0.66 |
| Duration | 24 | -3.0% | +41.7% | -0.30 |

### Modo B

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---------|-------|------------|------|--------|
| Growth | 187 | +12.9% | +65.8% | 0.58 |
| Value/Cyclical | 397 | +0.8% | +49.1% | 0.25 |
| Commodities | 280 | +0.2% | +42.5% | 0.02 |
| Small/EM | 73 | -0.6% | +50.7% | -0.07 |
| Defensive | 144 | -2.4% | +40.3% | -0.71 |
| Duration | 24 | -3.0% | +41.7% | -0.30 |

---

## Sección 4 — ROT. TEMPRANA

Total ROT. TEMPRANA emitidas: **160** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **66** (41%)
- Lead time (semanas): media=16.5  mediana=14  IQR=[7, 23]
- Convergencia por señal:
  - ACUMULAR: 38
  - COMPRA: 28

**Alpha 13w desde ROT. TEMPRANA:** +2.2%  | n=99
**Alpha 13w desde señal convencional (convergencia):** +1.3%  | n=42

---

## Sección 5 — Recession basket

Transiciones a Risk-OFF/Capitulacion detectadas: **12**

| Fecha | Anterior → Nuevo | INFL | α4w | α13w | α26w |
|-------|-----------------|------|-----|------|------|
| 2008-09-26 | Transición → Risk-OFF | no | +10.1% | +20.2% | +18.7% |
| 2022-11-11 | Transición → Risk-OFF | no | +2.0% | -7.8% | -5.4% |
| 2023-02-10 | Transición → Risk-OFF | no | +1.1% | +2.6% | -9.1% |
| 2023-08-11 | Transición → Risk-OFF | no | -7.4% | -6.2% | -16.1% |
| 2008-09-26 | Transición → Risk-OFF | no | +10.1% | +20.2% | +18.7% |
| 2022-11-11 | Transición → Risk-OFF | no | +2.0% | -7.8% | -5.4% |
| 2023-02-10 | Transición → Risk-OFF | no | +1.1% | +2.6% | -9.1% |
| 2023-07-07 | Transición → Risk-OFF | no | +1.7% | -5.5% | -5.2% |
| 2024-01-12 | Transición → Risk-OFF | no | -5.6% | -13.8% | -19.3% |
| 2024-04-12 | Transición → Risk-OFF | no | +5.0% | -4.5% | -1.9% |
| 2024-10-11 | Transición → Risk-OFF | no | -4.7% | -9.8% | +8.4% |
| 2025-10-10 | Transición → Risk-OFF | no | -3.5% | +2.6% | +3.9% |

**Alpha 13w basket completo:** -0.6%  n=12
**Alpha 13w regimen deflacionario:** -0.6%  n=12
**Alpha 13w regimen inflacionario:** —  n=0
**Falsos positivos (basket underperforma SPY en 4w):** 4/12 (33%)

---

## Sección 6 — Modo A vs Modo B (2023-04-18 en adelante)

- COMPRA: Modo A α13w=-0.0%  Modo B α13w=-5.1%  nA=190  nB=123
- ACUMULAR: Modo A α13w=-1.8%  Modo B α13w=-2.0%  nA=308  nB=275
- VIGILAR: Modo A α13w=+0.5%  Modo B α13w=+0.7%  nA=2295  nB=2372

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

**¿Las señales COMPRA dan alpha?**  Alpha medio 13w = +2.4%, hit rate = +49.9%, t-stat = 0.45. NO CONFIRMADO: alpha positivo pero t-stat < 1.5 (muestra pequena).

**¿ROT. TEMPRANA adelanta?**  DEBIL — solo 41% convergen.

**¿El framework detecta crisis?**  NO — alpha medio negativo (-0.6% a 13w en transiciones).

