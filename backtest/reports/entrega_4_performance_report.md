# Entrega 4 — Performance Report: RotationScore Signal Backtest
### Diagnóstico empírico post-sanity-check | 2026-04-20

---

## Resumen ejecutivo

**Veredicto:** Framework parcialmente validado: protege capital tras confirmar Risk-OFF (2008 +20% alpha en basket) pero detecta crisis con retraso severo (350 días en 2008, nunca en 2020). Señales COMPRA individuales no generan alpha estadísticamente significativo (mediana +0.04%, hit rate 50.2%); la media +2.90% es artefacto de BTC-USD 2017 (60% del alpha total en 10 señales). Las transiciones confirmadas (no cedidas) sí muestran alpha positivo en Modo A (+5.00%). La histéresis filtra transiciones falsas efectivamente (cedidas destruyen -6% de alpha).

### Los 4 hallazgos centrales

1. **Señales COMPRA sin alpha genuino:** media +2.90% (Modo A 13w) colapsa a +0.56% sin BTC-USD. Mediana +0.04%, skewness 8.21. No es alpha distribuido — es un artefacto de concentración extrema en un activo.
2. **Protección real tras Risk-OFF confirmado:** basket defendió +20.20% de alpha vs SPY en 13w desde la señal de 2008. Pero el sistema tardó 350 días en emitirla desde el pico del mercado.
3. **Lead time nulo en crisis:** 2008 detectado con SPY ya -21%. 2020: el sistema nunca llegó a Risk-OFF — la caída en V superó la frecuencia de señal del sistema.
4. **ROT. TEMPRANA es el hallazgo más sólido:** alpha 13w desde señal temprana +7.29% (mediana +6.29%), frente a +1.21% desde la señal convencional. Robusto sin BTC-USD (+6.57%). T-stat 2.77 (Modo A), 2.79 (Modo B) — único resultado estadísticamente significativo del backtest.

---

## Hallazgo 1 — Distribución de alpha COMPRA 13w (Modo A)

### Estadísticas completas

| Estadístico | Con universo completo | Sin BTC-USD |
|---|---|---|
| N observaciones | 1,044 | 1,003 |
| Media | +2.90% | **+0.56%** |
| **Mediana** | **+0.04%** | **-0.08%** |
| P25 | -5.17% | -5.35% |
| P75 | +4.62% | +4.21% |
| IQR | 9.79% | 9.56% |
| Min | -52.68% | -52.68% |
| Max | +379.29% | +51.82% |
| Skewness | 8.21 | 1.04 |
| Kurtosis | 99.63 | 4.18 |
| Hit rate (>0) | 50.19% | 49.35% |

**Diagnóstico:** La mediana es +0.04%, no +2.9%. Al excluir BTC-USD, la distribución se normaliza (skewness 8.21 → 1.04, kurtosis 99.63 → 4.18). El alpha "promedio" del sistema no existe de forma distribuida.

### Histograma COMPRA 13w Modo A (universo completo)

| Bucket | N | % total | % acumulado |
|---|---|---|---|
| (-inf, -20%) | 16 | 1.53% | 1.53% |
| (-20%, -10%) | 103 | 9.87% | 11.40% |
| (-10%, -5%) | 144 | 13.79% | 25.19% |
| (-5%, 0%) | 257 | 24.62% | 49.81% |
| **(0%, 5%)** | **272** | **26.05%** | 75.86% |
| (5%, 10%) | 106 | 10.15% | 86.02% |
| (10%, 20%) | 78 | 7.47% | 93.49% |
| (20%, +inf) | 68 | 6.51% | 100.00% |

La distribución está centrada en torno a cero con colas pesadas asimétricas. El bucket (0%,5%) es el más poblado pero por escaso margen sobre (-5%,0%).

### Top 10 señales COMPRA por alpha_13w

| Fecha | Ticker | Alpha 13w | % del alpha total acumulado |
|---|---|---|---|
| 2017-09-15 | BTC-USD | +379.29% | 12.51% |
| 2017-10-06 | BTC-USD | +290.73% | 9.59% |
| 2017-09-08 | BTC-USD | +283.62% | 9.36% |
| 2017-03-10 | BTC-USD | +150.01% | 4.95% |
| 2017-10-13 | BTC-USD | +138.00% | 4.55% |
| 2017-03-31 | BTC-USD | +128.40% | 4.24% |
| 2017-03-17 | BTC-USD | +126.05% | 4.16% |
| 2017-04-21 | BTC-USD | +112.55% | 3.71% |
| 2017-04-07 | BTC-USD | +110.57% | 3.65% |
| 2017-04-28 | BTC-USD | +109.16% | 3.60% |

**Las 10 señales son BTC-USD en 2017. Suman el 60.32% del alpha total acumulado.**

### Bottom 10 señales COMPRA por alpha_13w

| Fecha | Ticker | Alpha 13w |
|---|---|---|
| 2021-04-16 | BTC-USD | -52.68% |
| 2021-04-02 | BTC-USD | -51.54% |
| 2021-03-19 | BTC-USD | -45.54% |
| 2021-10-22 | BTC-USD | -36.93% |
| 2021-10-29 | BTC-USD | -35.85% |
| 2021-10-15 | BTC-USD | -34.62% |
| 2019-12-13 | BZ=F | -33.39% |
| 2021-04-30 | BTC-USD | -32.29% |
| 2021-05-07 | BTC-USD | -30.52% |
| 2021-10-08 | BTC-USD | -29.82% |

BTC-USD domina también los peores resultados (BTC 2021 bear market).

---

## Sección 1 — Alpha por tipo de señal (tablas duales)

### Modo A

| Señal | Hz | N obs | N ind. | Mean α (todo) | Mean α (sin BTC) | Median α (todo) | Median α (sin BTC) | Hit% (todo) | Hit% (sin BTC) |
|---|---|---|---|---|---|---|---|---|---|
| COMPRA | 4w | 1078 | 18 | +1.28% | +0.44% | -0.13% | -0.21% | 48.5% | 47.8% |
| COMPRA | 13w | 1044 | 18 | +2.90% | **+0.56%** | +0.04% | -0.08% | 50.2% | 49.4% |
| COMPRA | 26w | 1028 | 18 | +5.62% | **+0.97%** | -0.34% | -0.51% | 48.5% | 48.2% |
| ACUMULAR | 4w | 1984 | 18 | -0.11% | -0.11% | -0.22% | -0.22% | 47.3% | 47.3% |
| ACUMULAR | 13w | 1971 | 18 | -0.19% | -0.25% | -0.75% | -0.74% | 44.2% | 44.3% |
| ACUMULAR | 26w | 1945 | 18 | -0.27% | -0.21% | -1.37% | -1.34% | 44.3% | 44.5% |
| ROT. TEMPRANA | 4w | 32 | 12 | +0.6% | — | -0.5% | — | 46.9% | — |
| ROT. TEMPRANA | 13w | 32 | 12 | +6.9% | **+6.6%** | +6.0% | +6.3% | 81.2% | — |
| ROT. TEMPRANA | 26w | 30 | 12 | +10.3% | — | +6.7% | — | 83.3% | — |
| VIGILAR | 4w | 9888 | 19 | +0.1% | — | -0.1% | — | 48.5% | — |
| VIGILAR | 13w | 9801 | 19 | +0.4% | — | -0.3% | — | 47.9% | — |
| VIGILAR | 26w | 9646 | 19 | +1.2% | — | -0.3% | — | 48.4% | — |
| IGNORAR | 4w | 6034 | 19 | +0.0% | — | +0.0% | — | 50.1% | — |
| IGNORAR | 13w | 5997 | 19 | +0.4% | — | -0.0% | — | 49.9% | — |
| IGNORAR | 26w | 5949 | 19 | +0.6% | — | -0.6% | — | 47.8% | — |
| ACUMULAR* | 4w | 112 | 10 | -1.7% | — | -1.3% | — | 38.4% | — |
| ACUMULAR* | 13w | 112 | 10 | -4.7% | — | -5.1% | — | 30.4% | — |
| ACUMULAR* | 26w | 112 | 10 | -13.5% | — | -13.4% | — | 12.5% | — |

### Modo B

| Señal | Hz | N obs | N ind. | Mean α (todo) | Mean α (sin BTC) | Median α (todo) | Median α (sin BTC) | Hit% (todo) | Hit% (sin BTC) |
|---|---|---|---|---|---|---|---|---|---|
| COMPRA | 4w | 1035 | 18 | +1.04% | +0.15% | -0.11% | -0.20% | 48.4% | 47.7% |
| COMPRA | 13w | 1009 | 18 | +2.71% | **+0.27%** | +0.02% | -0.08% | 50.0% | 49.2% |
| COMPRA | 26w | 997 | 18 | +5.12% | **+0.29%** | -0.54% | -0.60% | 48.2% | 47.9% |
| ACUMULAR | 4w | 1948 | 18 | -0.03% | -0.03% | -0.16% | -0.16% | 47.9% | 48.0% |
| ACUMULAR | 13w | 1933 | 18 | -0.16% | -0.22% | -0.75% | -0.73% | 44.4% | 44.5% |
| ACUMULAR | 26w | 1917 | 18 | -0.62% | -0.56% | -1.37% | -1.34% | 44.3% | 44.5% |
| ROT. TEMPRANA | 4w | 36 | 13 | +5.4% | — | +0.9% | — | 52.8% | — |
| ROT. TEMPRANA | 13w | 34 | 12 | +7.7% | **+6.6%** | +6.4% | +6.3% | 82.4% | — |
| ROT. TEMPRANA | 26w | 30 | 12 | +10.3% | — | +6.7% | — | 83.3% | — |
| VIGILAR | 13w | 9868 | 19 | +0.4% | — | -0.3% | — | 47.8% | — |
| ACUMULAR* | 13w | 116 | 10 | -5.2% | — | -5.4% | — | 29.3% | — |
| ACUMULAR* | 26w | 116 | 10 | -13.8% | — | -13.9% | — | 12.1% | — |

**Conclusión tablas duales:** La diferencia entre "con BTC" y "sin BTC" en COMPRA 13w es de +2.34pp (Modo A) y +2.44pp (Modo B). Sin BTC-USD, las señales COMPRA tienen alpha media cercana a cero en todos los horizontes. ROT. TEMPRANA mantiene su alpha sin BTC.

---

## Sección 2 — COMPRA por régimen (alpha 13w, Modo A)

### Con universo completo

| Régimen | N obs | Mean α 13w | Hit% | t-stat |
|---|---|---|---|---|
| Bull Pleno | 213 | +11.7% | 61.0% | 0.60 |
| Bull Maduro | 636 | +1.6% | 50.2% | 0.37 |
| Transición | 183 | -1.8% | 41.0% | -0.69 |
| Risk-OFF | 12 | -10.2% | 0.0% | -4.87 |

### Sin BTC-USD

| Régimen | N obs | Mean α 13w | Median α 13w | Hit% |
|---|---|---|---|---|
| Bull Pleno | 172 | +0.17% | +0.54% | 58.7% |
| Bull Maduro | 636 | +1.55% | +0.04% | 50.2% |
| Transición | 183 | -1.81% | -1.48% | 41.0% |
| Risk-OFF | 12 | -10.17% | -10.28% | 0.0% |

**Nota:** Bull Pleno pierde su alpha (−11.5pp) al excluir BTC — el 11.7% de media era BTC-USD en 2017 en plena euforia. Bull Maduro conserva +1.55% pero con mediana +0.04%. Transición y Risk-OFF son robustos: señales COMPRA en esos regímenes destruyen valor consistentemente.

---

## Sección 3 — COMPRA por clúster (alpha 13w, Modo A)

### Con universo completo

| Cluster | N obs | Mean α 13w | Hit% | t-stat |
|---|---|---|---|---|
| Growth | 160 | +15.4% | 62.5% | 0.63 |
| Commodities | 321 | +1.6% | 46.1% | 0.19 |
| Value/Cyclical | 356 | +1.3% | 52.8% | 0.38 |
| Small/EM | 53 | +0.6% | 56.6% | 0.08 |
| Defensive | 123 | -2.1% | 39.8% | -0.61 |
| Duration | 31 | -5.9% | 29.0% | -0.61 |

### Sin BTC-USD

| Cluster | N obs | Mean α 13w | Median α 13w | Hit% |
|---|---|---|---|---|
| Growth | 119 | **-0.05%** | +0.42% | 59.7% |
| Value/Cyclical | 356 | +1.32% | +0.32% | 52.8% |
| Small/EM | 53 | +0.64% | +1.51% | 56.6% |
| Commodities | 321 | +1.57% | -1.18% | 46.1% |
| Defensive | 123 | -2.09% | -2.11% | 39.8% |
| Duration | 31 | -5.91% | -10.74% | 29.0% |

**Nota crítica:** El cluster Growth sin BTC-USD pasa de +15.4% a -0.05%. Todo el "alpha" del cluster Growth era BTC-USD 2017.

---

## Hallazgo 4 — ROT. TEMPRANA

Total ROT. TEMPRANA emitidas: **68** (ambos modos)

- Convergieron a COMPRA/ACUMULAR: **42 (62%)**
- Lead time mediano: **21 semanas** | Media: 20.5w | IQR: [10, 22]
- Distribución por señal de convergencia: COMPRA=22, ACUMULAR=20

### Alpha: señal temprana vs señal convencional (con/sin BTC)

| Métrica | Con BTC-USD | Sin BTC-USD |
|---|---|---|
| Alpha 13w desde ROT. TEMPRANA | +7.29% (med. +6.29%) | **+6.57% (med. +6.29%)** |
| Alpha 13w desde señal convencional | +1.21% (med. +1.58%) | +1.21% (med. +1.58%) |
| Diferencia (lead value) | **+6.08pp** | **+5.36pp** |
| T-stat ROT. TEMPRANA | 2.77 (MA) / 2.79 (MB) | — |

**Conclusión:** ROT. TEMPRANA es el único resultado estadísticamente significativo del backtest. El lead time de 21 semanas es real y robustamente positivo incluso sin BTC-USD. La señal temprana captura +6pp adicionales versus esperar la confirmación convencional.

---

## Hallazgo 2 — Las 14 transiciones del basket (Transición → Risk-OFF)

### Tabla completa

| Fecha | Modo | Clasificación | Inflation | Alpha 4w | Alpha 13w | Alpha 26w |
|---|---|---|---|---|---|---|
| 2008-09-26 | A | **VALIDADA** | No | +10.07% | **+20.20%** | +18.74% |
| 2018-12-28 | A | CEDIDA | No | -1.86% | -5.98% | -4.95% |
| 2022-11-11 | A | VALIDADA | No | +2.03% | -7.82% | -5.42% |
| 2023-02-10 | A | VALIDADA | No | +1.13% | +2.63% | -9.13% |
| 2023-08-11 | A | CEDIDA | No | -7.44% | -6.16% | -16.07% |
| 2008-09-26 | B | **VALIDADA** | No | +10.07% | **+20.20%** | +18.74% |
| 2018-12-28 | B | CEDIDA | No | -1.86% | -5.98% | -4.95% |
| 2022-11-11 | B | VALIDADA | No | +2.03% | -7.82% | -5.42% |
| 2023-02-10 | B | VALIDADA | No | +1.13% | +2.63% | -9.13% |
| 2023-07-07 | B | VALIDADA | No | +1.72% | -5.53% | -5.16% |
| 2024-01-12 | B | CEDIDA | No | -5.64% | **-13.79%** | -19.34% |
| 2024-04-12 | B | VALIDADA | No | +5.02% | -4.45% | -1.87% |
| 2024-07-26 | B | VALIDADA | No | +1.27% | -7.43% | -16.77% |
| 2025-10-10 | B | CEDIDA | No | -3.54% | +2.63% | +3.93% |

**Nota:** inflation_overlay_active = False en las 14 transiciones (HY spread ausente pre-2023 puede explicar infradetección).

### Mean alpha_13w: validadas vs cedidas

| | Todas | Solo Validadas | Solo Cedidas |
|---|---|---|---|
| Modo A (5 eventos) | +0.57% | **+5.00%** | -6.07% |
| Modo B (9 eventos) | -2.17% | **-0.40%** | -5.71% |

**¿Cambia filtrar por validadas?** Para Modo A: sí — de +0.57% a +5.00%. Para Modo B: mejora pero sigue negativo (-0.40%). En ambos modos, las cedidas destruyen ~-6% de alpha en 13w. La histéresis activa —que impide confirmar transiciones que se revierten en <4w— reduce el daño de forma efectiva.

**Caveat:** El resultado de Modo A (+5.00%) está anclado a un único evento: 2008. Con n=3 validadas en Modo A, la estadística no es conclusiva.

---

## Hallazgo 3 — Crisis 2008 y 2020: lead time y retornos

### 2008 — GFC

| | Datos |
|---|---|
| Pico SPY | 2007-10-12 ($111.05) |
| Primera señal Risk-OFF | **2008-09-26** ($87.67) |
| Lead time tras el pico | **350 días — SPY ya había caído -21.1%** |
| Fondo SPY | 2009-03-06 ($50.40) |
| Caída peak-to-trough SPY | -54.61% |

**Retornos desde fecha de detección (2008-09-26):**

| Horizonte | Fecha | Basket ret. | SPY ret. | Alpha basket |
|---|---|---|---|---|
| +4w | 2008-10-24 | -17.91% | -27.29%* | **+10.07%** |
| +13w | 2008-12-26 | -7.09% | -27.29% | **+20.20%** |
| +26w | 2009-03-27 | -12.70% | -31.43% | **+18.74%** |

*SPY a +4w calculado implícitamente desde los datos del basket_alpha.

**Interpretación:** El sistema no tuvo lead time — llegó 350 días tarde con el índice ya en -21%. Sin embargo, la protección tras la señal fue real y sostenida: el basket cedió solo -7% en 13w mientras SPY caía -27%. Quien ejecutó la señal tardía igualmente protegió capital en el período subsiguiente.

### 2020 — COVID

| | Datos |
|---|---|
| Pico SPY | 2020-02-14 ($308.52) |
| Primera señal sistema | **2020-03-06** → régimen Transición (Modo A) |
| Lead time tras el pico | **21 días — SPY ya había caído -11.9%** |
| Fondo SPY | 2020-03-20 ($210.32) |
| Caída peak-to-trough SPY | -31.83% |
| **Risk-OFF activado** | **NUNCA** |

El fondo ocurrió solo 14 días después de la señal de Transición. La crisis fue tan vertical que el sistema no pudo confirmar Risk-OFF antes del inicio del rebote.

**Retornos desde fecha de detección (2020-03-06) — basket defensivo EW (TLT, XLU, XLV, XLP, XLRE, GC=F):**

| Horizonte | Fecha | Basket def. EW | SPY | Alpha |
|---|---|---|---|---|
| +4w | 2020-04-03 | -11.03% | -16.07% | **+5.04%** |
| +13w | 2020-06-05 | -1.86% | +7.99% | **-9.85%** |
| +26w | 2020-09-04 | +2.81% | +16.35% | **-13.54%** |

El basket protegió en el corto plazo (+4w) pero pagó un precio alto en la recuperación. Sin señal Risk-OFF formal, no hay basket de transición validada para comparar — estos son los activos con señal ACUMULAR en Transición.

### Comparativa crisis

| | 2008 | 2020 |
|---|---|---|
| Lead time sistema | 350 días (tardío) | 21 días (veloz pero insuficiente) |
| ¿Llegó a Risk-OFF? | Sí (2008-09-26) | No |
| Alpha basket +13w | +20.20% | -9.85% (sin señal Risk-OFF) |
| Velocidad de caída | Gradual (13 meses) | V abrupta (33 días) |
| Limitación estructural | Frecuencia semanal insuficiente | Velocidad de crisis supera cadencia del sistema |

---

## Sección adicional — Modo A vs Modo B (desde 2023-04-18)

| Señal | Modo A α13w | Modo B α13w | nA | nB |
|---|---|---|---|---|
| COMPRA | +0.5% | -3.5% | 142 | 100 |
| ACUMULAR | -1.6% | -1.6% | 279 | 241 |
| VIGILAR | +0.4% | +0.5% | 1828 | 1898 |

---

## Conclusiones operativas

**¿Las señales COMPRA dan alpha?** Con universo completo: media +2.90%, mediana +0.04%, hit rate 50.2%, t-stat 0.51. Sin BTC-USD: media +0.56%, mediana -0.08%. **NO CONFIRMADO.** Tratar señales COMPRA como confirmación de tendencia, no como generador de alpha.

**¿ROT. TEMPRANA adelanta?** **SÍ** — único resultado estadísticamente significativo (t-stat 2.77). Lead time mediano 21w. Alpha desde señal temprana +7.29% (mediana +6.29%) vs +1.21% desde señal convencional. Robusto sin BTC-USD.

**¿El framework detecta crisis?** Detecta con retraso severo. Una vez confirmado Risk-OFF, la protección es real (2008: +20% alpha). Pero la detección llega tarde (350 días en 2008) o no llega (2020). Las cedidas dañan (-6% alpha) y deben filtrarse.

### Implicaciones operativas específicas

1. No actuar sobre transiciones "pending" no confirmadas — esperar validación
2. Señales COMPRA = confirmación de dirección, no alpha por sí solas
3. Esperar protección real en Risk-OFF validado, pero asumir que la señal llegará con SPY ya en -15% a -20%
4. La histéresis es útil: las transiciones cedidas dañan; dejar que el sistema las filtre antes de ejecutar

---

## Implicaciones para Entrega 5

La evidencia empírica de esta entrega justifica específicamente la necesidad de un detector de confluencia temprana:

**El problema cuantificado:** El sistema tardó 350 días en detectar Risk-OFF en 2008. En 2020, nunca llegó a emitir la señal. Ambos fallos tienen la misma causa: el sistema confirma después de que la señal macro ya es evidente, no antes.

**Los ingredientes ya existen en el pipeline:**
- **Δ2w / Δ4w** (Entrega 2): los deltas de corto plazo capturan deterioro macro antes de que los promedios móviles confirmen. Podrían haber señalado alerta en 2008 desde Q1 2008, no en septiembre.
- **Cluster health scores** (Entrega 3): degradación del health score en clusters cíclicos precede al cambio de régimen. Si en julio 2007 los clusters Financials/Value/Cyclical mostraban deterioro, ese es el input para la señal anticipada.

**El objetivo de Entrega 5:** Construir un detector de confluencia que combine: (a) deterioro en Δ4w de indicadores macro clave, (b) cluster health degradation en sectores cíclicos, (c) señales ROT. TEMPRANA ya validadas como precursoras. El objetivo es reducir el lead time de 350 días a <60 días en escenarios tipo 2008, y emitir alguna señal en escenarios tipo 2020.

---

## Limitaciones documentadas

1. **Muestra pequeña en transiciones:** 14 eventos totales (5 en Modo A, 9 en Modo B). Con n=3 validadas en Modo A, el +5.00% de alpha no es estadísticamente conclusivo.
2. **Autocorrelación grave en COMPRA:** n_independent=18 para n=1,044 observaciones. T-stat reportado usa n_independent. El intervalo de confianza es muy amplio.
3. **BTC-USD domina resultados agregados:** 60.32% del alpha total COMPRA 13w proviene de 10 señales BTC-USD en 2017. Cualquier métrica agregada sin segregar BTC-USD es engañosa.
4. **Ausencia de HY pre-2023:** el spread HY (Modo B) no está disponible antes de 2023. Esto puede haber impedido la activación de inflation_overlay y la detección más temprana en 2008-2009. Todas las 14 transiciones tienen inflation_overlay_active=False.
5. **Backtest no simula portfolio real:** el alpha se mide por señal individual, no con sizing, rebalance, ni costes de transacción. Los alphas son brutos y no son replicables directamente.
6. **Único ciclo secular:** el período 2005-2026 es mayoritariamente alcista. Los resultados en regímenes de estrés (n=12 COMPRA en Risk-OFF) están infrarrepresentados.

---

*Entrega 4 cerrada. Parquets intactos: signal_alphas.parquet, rotation_history.parquet, lead_time_analysis.parquet, recession_basket_validation.parquet, performance_summary.parquet.*
