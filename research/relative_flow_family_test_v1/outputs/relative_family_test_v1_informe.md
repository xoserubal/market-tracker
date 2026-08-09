# Relative Flow Family Falsification Test v1 (acotado) — Informe

**Fecha de ejecución:** 2026-08-10
**Preregistro:** `wiki/PREREGISTRO_RELATIVE_FLOW_FAMILY_TEST_V1.md`
**Universo:** `backtest/config/relative_family_test_v1.yaml` (37 activos, congelado)
**Script:** `research/relative_flow_family_test_v1/relative_family_falsification_test.py`
(seed=20260810, 100 simulaciones bootstrap, sin cambios tras ver resultados)

## Veredicto: **NOT SUPPORTED**

La hipótesis primaria (H1: la regla Relative Flow funciona mejor en activos
refugio/monetarios que en materias primas industriales) **no sobrevive** a
la corrección metodológica más básica de este test. No hace falta llegar a
los placebos ni al leave-one-out para descartarla — la métrica primaria ya
la tumba.

---

## 1. Qué cambió y por qué se cae la hipótesis

La exploración original medía Δ TAE (rentabilidad anualizada **solo sobre
los días en que la posición estaba abierta**). Este test usa
`excess_CAGR_calendar` (rentabilidad anualizada sobre **todo el calendario**
de la ventana, con 0% los días fuera de mercado) — el cambio que el propio
diseño de este test exigía para neutralizar H2 (artefacto de métrica).

El resultado es una reversión casi completa:

| Activo | Δ TAE (exploración) | excess_CAGR_calendar (este test) |
|---|---|---|
| Oro (GLD) | +53,3 | **-20,2** |
| Plata (SLV) | +57,7 | **-31,2** |
| Mineras junior (GDXJ) | +51,4 | **-36,7** |
| Mineras de oro (GDX) | -6,3 | **-49,5** |

**La causa es mecánica, no un error:** oro y plata subieron muchísimo en
términos absolutos durante estos 2 años (+77% y +130% de buy&hold). La
estrategia solo estuvo invertida ~20-25% del tiempo. El TAE premiaba
"cuánto ganas por día invertido" — comprimir una ganancia decente en pocos
días parece brillante. El CAGR de calendario completo pregunta algo más
simple y más honesto para un inversor real: "¿ganaste más que si
simplemente hubieras comprado y aguantado todo el periodo?" — y la
respuesta, al estar fuera del mercado ~75-80% de un mercado alcista fuerte,
es que no, por un margen amplio.

## 2. Resultado principal: Familia A (refugio) vs Familia B (industrial)

| Familia | n | mediana excess_CAGR | media | % positivos |
|---|---|---|---|---|
| A — Monetary/store-of-value | 6 | **-25,73** | -18,50 | 33,3% (2/6) |
| B — Industrial/cyclical | 9 | **-25,93** | -24,81 | 0,0% (0/9) |

**Prácticamente idénticas.** Diferencia de medianas: 0,20 puntos — a favor
de B, en la dirección CONTRARIA a H1.

**Test estadístico:**
- Mann-Whitney U: p crudo = 0,523 → **p Bonferroni (×4) = 1,000**
- Test de permutación (10.000 perms): p crudo = 0,579 → **p Bonferroni = 1,000**

No hay ninguna lectura razonable de estos números que sugiera separación
entre familias. El p-valor crudo ya está muy lejos de cualquier umbral
convencional, antes incluso de aplicar la corrección por las 4 hipótesis ya
probadas en la exploración.

## 3. Tabla completa por activo

`*` = añadido tras predicción explícita del usuario (PPLT, PALL, DBB).
`-` = fuera del análisis principal (duplicado, futuro proxy, familia C/D).

```
Familia A — Monetary / Store-of-value
  ETH-USD   exposure=20.4%  CAGR_estrat=  4.09  CAGR_bh=-14.26  excess= +18.34  boot_pct=64
  BTC-USD   exposure=25.6%  CAGR_estrat= 11.60  CAGR_bh=  3.24  excess=  +8.36  boot_pct=76
  GLD       exposure=19.8%  CAGR_estrat= 13.11  CAGR_bh= 33.34  excess= -20.23  boot_pct=91
  SLV       exposure=25.4%  CAGR_estrat= 20.63  CAGR_bh= 51.87  excess= -31.24  boot_pct=65
  GDXJ      exposure=36.6%  CAGR_estrat= 33.84  CAGR_bh= 70.55  excess= -36.71  boot_pct=71
  GDX       exposure=23.4%  CAGR_estrat= 10.63  CAGR_bh= 60.13  excess= -49.50  boot_pct=60
- IAU (dup. GLD)   excess= -20.34   boot_pct=88
- SIVR (dup. SLV)  excess= -27.52   boot_pct=84

Familia B — Industrial / Cyclical Commodities
  XLB       exposure=20.0%  CAGR_estrat=  1.57  CAGR_bh= 11.37  excess=  -9.80  boot_pct=48
  PICK      exposure=30.6%  CAGR_estrat= 17.48  CAGR_bh= 33.75  excess= -16.27  boot_pct=74
* PALL      exposure=25.6%  CAGR_estrat=  4.23  CAGR_bh= 22.92  excess= -18.69  boot_pct=52
* DBB       exposure=18.6%  CAGR_estrat=  0.08  CAGR_bh= 21.03  excess= -20.96  boot_pct=20
  COPX      exposure=32.8%  CAGR_estrat= 25.98  CAGR_bh= 51.92  excess= -25.93  boot_pct=83
  SLX       exposure=17.2%  CAGR_estrat=  4.80  CAGR_bh= 33.52  excess= -28.72  boot_pct=46
  CPER      exposure=26.2%  CAGR_estrat= -3.32  CAGR_bh= 26.33  excess= -29.66  boot_pct=20
* PPLT      exposure=24.0%  CAGR_estrat=  2.81  CAGR_bh= 36.98  excess= -34.17  boot_pct=45
  XME       exposure=23.2%  CAGR_estrat=  3.73  CAGR_bh= 42.84  excess= -39.11  boot_pct=36
- HG=F (futuro)  excess= -30.11   boot_pct=21
- PA=F (futuro)  excess= -35.20   boot_pct=16
- PL=F (futuro)  excess= -46.96   boot_pct=10

Familia C — Rates/FX/Duration (contexto, fuera del test A vs B)
  EDV +5.48  TLT +3.96  DX-Y.NYB +0.94  FXY +0.34  TIP -1.47  IEF -1.72  UUP -3.41  BIL -3.82  FXF -5.04

Familia D — Equity/Sector Controls (contexto, fuera del test A vs B)
  XLF -6.58  XLP -7.61  XLU -7.63  XLY -9.48  IWM -13.34  QQQ -22.72  XLE -25.89  XLK -27.52
```

**Nota sobre Familia C/D:** casi todo negativo también, con la excepción de
duration/bonos (TLT/EDV) que tuvieron un buy&hold propio negativo o casi
plano en este periodo (el mercado de bonos fue flojo), así que ahí "estar
fuera la mayor parte del tiempo" no penaliza tanto. **Esto confirma que el
patrón "casi todo negativo" no es propio de materias primas — es
prácticamente universal en esta ventana**, consistente con haber sido un
periodo de mercado alcista amplio y sostenido en la mayoría de clases de
activo.

## 4. Placebos y diagnóstico adicional

### 4.1 — Percentil frente a bootstrap de bloques (100 sims, bloques de 20 sesiones)

Pregunta que responde: dado que se está expuesto X días, **¿elegir esos
días concretos vale más que elegir X días al azar (en bloques de 20
sesiones) de la propia historia del activo?**

- **GLD (91), IAU (88), SIVR (84), COPX (83), XLY equivalente en familia D
  (86), TLT (74), PICK (74), BTC (76), GDXJ (71)** — el momento elegido por
  la señal supera claramente a la mayoría de las 100 combinaciones
  aleatorias. Esto es una señal real de que el timing NO es ruido puro,
  incluso donde el resultado final contra buy&hold es negativo.
- **CPER (20), DBB (20), PL=F (10), PA=F (16), XLE (3), FXF/FXY/BIL (5-6)**
  — aquí ocurre lo contrario: el timing real es **peor** que la mayoría de
  las combinaciones aleatorias. Para cobre en particular (CPER Y HG=F
  coinciden en percentil ~20), esto es un resultado más dañino que "no hay
  edge" — sugiere que la señal está activamente equivocada de dirección en
  ese activo.

**Interpretación:** el timing de la señal no es uniformemente ruido —
tiene algo de estructura real, positiva en unos activos y negativa en
otros — pero esa estructura no se alinea con la frontera
"refugio/industrial": GLD y COPX (metal industrial) están ambos en el lado
"mejor que el azar", mientras que DBB (metal industrial) y XLE (energía,
familia D) están en el lado "peor que el azar" junto a nada de la familia A.

### 4.2 — Señal invertida

Para **CPER (+4,34 invertida vs -29,66 primaria)**, **HG=F (+1,71 vs
-30,11)** y **PL=F/PA=F (+13-15 vs -35/-47)** la señal invertida es
sustancialmente mejor que la primaria — la familia de cobre/platino/
paladio parece tener la señal apuntando en la dirección equivocada más que
simplemente "sin valor". Para XLE (familia D, +11,27 invertida vs -25,89
primaria) ocurre lo mismo. Para el resto de activos la inversión no mejora
sistemáticamente — no es un patrón universal, es específico de un
subconjunto de materias primas/energía.

### 4.3 — Baseline de momentum simple (precio > SMA200)

**ETH destaca: la regla Relative Flow saca +18,34, pero un simple filtro de
SMA200 saca +42,08** — más del doble. Para BTC ocurre lo contrario
(+8,36 vs -3,13, la señal gana). No hay un patrón consistente de que
Relative Flow añada valor sobre el momentum genérico — a veces gana, a
veces pierde con claridad, sin relación con la familia.

### 4.4 — Placebo de lag (anti-lookahead) — limitación de diseño, no bug

`lag_minus_1d` mejora los resultados de forma sistemática y grande en casi
todos los activos (ej. BTC +8,36→+87,51, ETH +18,34→+112,47). **Esto no se
interpreta como bug de look-ahead en el cálculo del score** — `score` se
calcula con `relative_flow_lib.compute_pair_series`, ya validado
estructuralmente como causal (cada fila usa solo `values[0:t+1]`, con test
explícito para ello) en la sesión que construyó ese módulo. La mejora con
lag=-1 es esperable por construcción para *cualquier* señal de cruce de
umbral basada en momentum: el día del cruce suele contener el propio
movimiento de precio que causó el cruce, así que "capturarlo un día antes"
casi siempre mejora el resultado, sea la señal real o inventada. **Este
placebo, tal como está implementado aquí, no distingue bien entre "hay un
bug" y "es una señal de momentum"** — se documenta como limitación del
diseño de v1, no como hallazgo de bug. No se necesita ninguna corrección de
código a partir de este resultado.

## 5. Leave-one-out

Familia A: mediana oscila entre -20,23 (excluyendo SLV o BTC o ETH — quedan
los mismos valores porque son los extremos que definen la mediana con n=5)
y -31,24 (excluyendo GLD). Familia B: oscila entre -23,45 y -27,32. **En
ningún caso 1 activo cambia la conclusión** — la ausencia de separación
entre familias no depende de ningún outlier.

## 6. Correlación intra-familia

Familia A: 0,493. Familia B: 0,609. Ambas por debajo del umbral de aviso
(0,7) fijado en el preregistro — el n nominal (6 y 9) no está inflado de
forma dramática por activos que se muevan todos juntos, aunque la
correlación de B es notablemente más alta (los metales industriales
comparten más driver común — probablemente el ciclo manufacturero
chino/global — que los activos de la familia A entre sí).

## 7. Contraste contra los criterios preregistrados

**Suggestive** requería TODOS estos puntos — ninguno se cumple de forma
conjunta:
- ❌ mediana(A) > mediana(B): -25,73 vs -25,93, prácticamente empatadas.
- ❌ ≥60% de A con excess_CAGR>0: solo 33,3% (2/6).
- ✅ ≥60% de B con excess_CAGR≤0: 100% (9/9) — este punto sí se cumple, pero aislado no basta.
- ❌ primaria supera a invertida/aleatoria/momentum de forma consistente en A: mixto, no consistente (ver sección 4).
- ✅ no depende de 1 activo (leave-one-out): se cumple.
- ✅ correlación intra-familia <0,7: se cumple.
- ❌ p Bonferroni <0,05: p=1,000.

**Conclusión formal: NOT SUPPORTED**, no "inconclusive" — el criterio de
descarte más simple (A no supera a B en la métrica primaria) ya se cumple
de forma clara, sin ambigüedad.

## 8. Qué queda de valor de este ejercicio

- **El hallazgo real de este test no es sobre familias de activos — es
  sobre la métrica.** La separación "refugio vs industrial" de la
  exploración original parece haber sido, en buena parte, un artefacto de
  usar Δ TAE (que no penaliza estar fuera del mercado) en un periodo donde
  casi todo subió mucho. Esto es un resultado útil en sí mismo: confirma
  que H2 (rival hypothesis del preregistro) tenía razón, y que **cualquier
  métrica de este tipo de sistemas debe evaluarse siempre en calendario
  completo, no solo sobre días expuestos**, antes de sacar ninguna
  conclusión.
- **El bootstrap por bloques sugiere que el timing no es puro ruido** en
  varios activos (percentiles 70-90+), pero esa estructura no se alinea
  con la hipótesis de familia — aparece tanto en refugio (GLD) como en
  industrial (COPX, PICK), y su ausencia/inversión también aparece en
  ambos lados (DBB por un lado, XLE/XLK por otro).
- Si en el futuro se quiere investigar **"¿hay timing skill real,
  independiente de familia de activo?"**, es una hipótesis distinta y
  necesitaría su propio preregistro (comparando percentil de bootstrap
  contra una referencia neutra, sin agrupar por familia) — no una
  reinterpretación de estos datos.

## 9. Recomendación

**No escalar a v1 completo** (costes × 3, 1.000 simulaciones, sub-muestras
temporales, leave-two-out, regresión multivariante, forward OOS). El
resultado ya es claro con el test acotado — la hipótesis primaria no
sobrevive ni siquiera antes de aplicar más rigor, así que invertir el
esfuerzo adicional no cambiaría la conclusión, solo la confirmaría con más
detalle innecesario. La puerta dura del preregistro (sección 13) se
resuelve aquí: **opción (a), descartar la hipótesis**.

No se toca `paper_trading.py`, `pcs_calculator.py`, ninguna cartera ni el
motor IA — como estaba acordado desde el inicio.
