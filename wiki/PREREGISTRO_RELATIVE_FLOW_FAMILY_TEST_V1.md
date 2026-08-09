# Preregistro — Relative Flow Family Falsification Test v1 (versión acotada)

**Fecha de congelación: 2026-08-10, antes de ejecutar el test sobre el universo ampliado.**
Origen: exploración interactiva no preregistrada sobre `relative.html` (ver
`wiki/ASESOR_EXTERNO_RELATIVE_FLOW_REFUGIO_VS_INDUSTRIAL.md`), que encontró
una posible separación entre activos refugio/especulativos y materias
primas industriales. Este documento congela una prueba diseñada
específicamente para intentar **refutar** esa hipótesis, no para confirmarla.

**Decisión de alcance (2026-08-10):** versión **acotada** — Capa 1
(reproducción) + Capa 2 (universo congelado, métrica primaria, placebos
básicos, leave-one-out, correlación intra-familia, Bonferroni). **Sin**
escenarios de coste múltiples, sin 1.000 simulaciones (100), sin análisis
por tercios temporales, sin infraestructura de forward OOS. Puerta dura
explícita: no se implementa nada de lo anterior sin decidir juntos, después
de leer el informe de esta versión acotada.

---

## 0. Correcciones incorporadas desde la revisión previa

Este preregistro ya incorpora las 7 correcciones acordadas tras la revisión
crítica del diseño original (ver conversación previa):

1. **Duplicados excluidos del análisis principal.** IAU (dup. de GLD,
   correlación 0.9998, verificado 2026-08-10) y SIVR (dup. de SLV,
   correlación 0.9996) se documentan en el YAML con
   `known_duplicate_of`/`include_in_primary_analysis: false`. Se reportan
   aparte como robustez, nunca cuentan hacia el n de la familia.
2. **Familia D dividida en dos sub-familias con pregunta explícita**:
   D.1 (índice ancho: QQQ, IWM — ¿funciona en cualquier equity o solo en
   subconjuntos?) y D.2 (sectorial: XLF, XLK, XLE, XLU, XLY, XLP — ¿funciona
   indistinto por sector?). SPY se excluye de D.1 — no se puede construir el
   ratio SPY/SPY (denominador = numerador, score trivialmente plano).
3. **H7 y H8 eliminadas de v1** (opción C de las tres propuestas). No son
   falsables tal como estaban planteadas (campos manuales sin metodología
   objetiva). Quedan para un v2 solo si v1 sobrevive, con proxy medible
   pendiente de diseñar (p.ej. R² de regresión multifactor).
4. **Placebo aleatorio especificado por escrito**: block bootstrap, bloques
   de 20 sesiones, sobre el retorno diario real del activo — ver sección 6.2.
5. **Ubicación: `research/relative_flow_family_test_v1/`**, fuera de las
   rutas productivas del pipeline (`docs/data/`, `scripts/` de producción),
   para separar investigación de infraestructura en vivo — misma decisión
   que ya se tomó para la exploración original.
6. **YAML en `backtest/config/`**, siguiendo la convención ya establecida
   en el repo (no una carpeta `config/` nueva en la raíz).
7. **Trigger de forward OOS diferido.** No se implementa en esta versión
   acotada — se decide solo si el resultado de Capa 1+2 justifica avanzar.

---

## 1. Hipótesis primaria

**H1:** la regla "entrada paso-a-Improving / salida cualquiera-de-las-dos"
genera mejor exceso de retorno frente a comprar-y-mantener el propio activo
en activos de tipo monetario/refugio de valor/especulativo (Familia A) que
en activos ligados a demanda industrial real (Familia B).

Formulación operativa: `mediana(excess_CAGR_A) > mediana(excess_CAGR_B)`,
con significancia evaluada vía Mann-Whitney U + test de permutación,
corregida por Bonferroni ×4 (ver sección 2).

## 2. Hipótesis rivales evaluadas en v1

- **H2 — Artefacto de métrica:** el patrón depende de usar Δ TAE
  (anualizado sobre días expuestos) en vez de `excess_CAGR_calendar`
  (anualizado sobre el calendario completo, con cash=0 cuando está fuera).
  **Se neutraliza de raíz**: v1 usa `excess_CAGR_calendar` como métrica
  primaria desde el diseño, no como comparación a posteriori.
- **H3 — Artefacto de volatilidad/frecuencia de operaciones:** el patrón se
  explica por volatilidad, nº de trades o duración media, no por familia.
  Se reporta correlación simple de `excess_CAGR` contra estas variables
  (diagnóstico, no regresión multivariante completa — esa queda para v1
  completo si se decide escalar).
- **H6 — Selección de activos:** el patrón depende de qué activos se vieron
  durante la exploración. Se reporta por separado
  `seen_in_exploration=true` vs `false`, y `seen_direction_biased=true`
  (PPLT, PALL, DBB — añadidos tras predicción explícita del usuario) con
  asterisco.
- **H9 — Efecto liquidez:** el edge aumenta cuando baja la liquidez. Proxy
  medible: `liquidity_bucket` (alto/medio/bajo, asignado por AUM/volumen
  conocido de cada ETF/activo). Se reporta `excess_CAGR` por bucket.

**Diferidas a v2 (no falsables con proxy objetivo todavía):** H4
(momentum/trendiness — se aproxima parcialmente con el baseline SMA200, no
como hipótesis formal completa), H5 (risk-on/risk-off — necesitaría un
indicador de régimen que no se ha construido), H7 y H8 (ver sección 0.3).

## 3. Universo congelado

Definido en `backtest/config/relative_family_test_v1.yaml`. Resumen:

| Familia | Sub-familia | Activos (símbolo) | n primario |
|---|---|---|---|
| A — Monetary/store-of-value | A.1 Precious metals | GLD, SLV (IAU/SIVR excluidos, dup.) | 2 |
| | A.2 Crypto speculative | BTC-USD, ETH-USD | 2 |
| | A.3 Gold equity beta | GDXJ, GDX | 2 |
| B — Industrial/cyclical | B.1 Commodities físicas | CPER, DBB*, PPLT*, PALL* | 4 |
| | B.2 Equities cíclicas mineras | XME, COPX, SLX, PICK | 4 |
| | B.3 Sector materiales | XLB | 1 |
| | B.4 Futures proxy (aparte) | HG=F, PL=F, PA=F | 0 (reportado aparte) |
| C — Rates/FX/Duration (aparte) | — | TLT, IEF, EDV, TIP, UUP, DX-Y.NYB, FXY, FXF, BIL | 0 (reportado aparte) |
| D — Equity controls | D.1 Índice ancho | QQQ, IWM | 2 |
| | D.2 Sectorial | XLF, XLK, XLE, XLU, XLY, XLP | 6 |

`*` = `seen_direction_biased: true` (añadidos tras predicción explícita del
usuario de que saldrían mal — resultado marcado con asterisco en el informe).

**n primario del test principal (A vs B): 6 vs 9.** Familias C y D se
reportan como contexto/diagnóstico, no entran en el test de H1.

**Fuera de v1 por decisión explícita** (no reasignadas a ninguna
sub-familia D tras la revisión): VGK, EWZ, FXI (mercados regionales —
quedaban sin sub-familia clara tras la división D.1/D.2; se documenta el
hueco en vez de inventar una tercera sub-familia sin acordarla).

Campos por activo en el YAML: `id, symbol, family, subfamily,
tradable_type, ratio_denominator, seen_in_exploration,
seen_direction_biased, liquidity_bucket, known_duplicate_of,
include_in_primary_analysis, notes`.

**No se añaden ni quitan activos tras ejecutar el test**, salvo ticker roto
documentado.

## 4. Regla congelada (idéntica a la exploración original)

- **Entrada:** `score` del ratio activo/SPY cruza de <3 a ≥3 respecto al
  día anterior.
- **Salida:** primera de: `score` cruza de ≥8 a <8, o `score` cruza de ≥3
  a <3.
- **Retorno:** precio real del activo, nunca el ratio.
- Posición abierta al final de la ventana → se cierra al último precio
  disponible.
- Score calculado con `relative_flow_lib.compute_pair_series` (importado
  directamente del pipeline real, nunca reimplementado — evita el drift ya
  documentado en otras partes de este proyecto con `calcCMF`/`HARD_RULES`).

**No se optimizan los umbrales 3/8. No se prueban combinaciones nuevas como
regla primaria en v1.**

## 5. Métrica primaria y ventana

**`excess_CAGR_calendar` = CAGR(estrategia) − CAGR(buy&hold)**, ambos
anualizados sobre el **calendario completo** de la ventana
(`365.25 / días_naturales_transcurridos`), no sobre días de exposición.

- `strategy_equity_curve`: retorno diario real del activo en días con
  posición abierta; **0% en días sin posición (cash=0)**.
- `buy_hold_equity_curve`: retorno diario real del activo todos los días.
- `CAGR = (equity_final / equity_inicial)^(365.25/días_naturales) - 1`.

Esto corrige explícitamente la sensibilidad al ruido de Δ TAE (anualizado
sobre pocos días de exposición) detectada en TLT/HYG durante la
exploración — ver H2.

**Ventana:** últimos 730 días naturales desde 2026-08-10 (misma ventana que
la exploración — sigue sin ser un tramo de test limpio, ver sección 8).

## 6. Placebos incluidos en v1 (básicos)

### 6.1 — Señal invertida
Estar dentro exactamente cuando la señal primaria diría fuera, y viceversa.
Mismo cálculo de `excess_CAGR_calendar`.

### 6.2 — Señal aleatoria (block bootstrap, ~100 simulaciones)
Especificación exacta (resuelve la objeción de infra-especificación):
1. Tomar la serie de retornos diarios reales del activo.
2. Construir un pool de todos los bloques contiguos posibles de 20
   sesiones de esa serie.
3. Por simulación: concatenar bloques de 20 sesiones muestreados con
   reemplazo del pool hasta alcanzar el mismo nº total de días de
   exposición que la estrategia real (`open_days`).
4. Componer el retorno total de esa secuencia sintética.
5. Repetir 100 veces → distribución nula de "retorno de estar expuesto el
   mismo nº de días, en bloques de 20 sesiones de la propia historia real
   del activo, elegidos al azar".
6. Reportar el percentil del retorno compuesto REAL de la estrategia
   dentro de esa distribución.

**Criterio de sanidad:** si la estrategia real no supera el percentil 75
de las 100 simulaciones, no hay edge de timing más allá de la volatilidad
propia del activo.

### 6.3 — Señales desplazadas (lag)
- `lag_minus_1d`: entrada/salida un día ANTES de lo que realmente marcó la
  señal (imposible en la práctica — control técnico anti-lookahead). Si
  esto mejora el resultado de forma notable, hay un bug de lookahead que
  invalida todo lo demás.
- `lag_1d`, `lag_5d`: entrada/salida retrasada 1 y 5 sesiones (ejecución
  realista con retraso).

### 6.4 — Baseline de momentum simple
`precio > SMA200` como regla de entrada/salida alternativa, mismo cálculo
de `excess_CAGR_calendar`. Si el momentum simple iguala o supera a la
regla de Relative Flow, el "edge" es momentum genérico, no algo específico
de este sistema.

### 6.5 — Buy & hold del propio activo
Ya integrado en la métrica primaria (no es un placebo aparte, es la base
de comparación).

**Diferidos a v1 completo:** placebo de "no-señal con misma exposición
temporal" (10.6 del diseño original), 3 escenarios de coste, análisis por
tercios temporales.

## 7. Análisis de robustez incluidos en v1

- **Leave-one-out** para familias A y B (n primario ≥4 en ambas): recalcular
  la mediana de familia excluyendo cada activo uno a uno. Si el resultado
  depende de 1-2 activos, se reporta explícitamente como tal.
- **Correlación intra-familia**: matriz de correlación de retornos diarios
  del activo (no del ratio) dentro de cada familia primaria. Si la media
  es alta (>0.7), se advierte que el n efectivo es menor que el n nominal.
- **Diferido a v1 completo:** leave-two-out, análisis por sub-muestras
  temporales (tercios).

## 8. Estado dev/test

La ventana de 730 días **ya está contaminada por la exploración previa**
(no es un tramo nuevo). Este test, aunque preregistrado y con placebos
formales, sigue siendo **replicación exploratoria ampliada**, no
confirmación limpia. La única confirmación real vendría de un forward OOS
posterior — explícitamente diferido a una decisión posterior a este informe
(sección 0.7).

## 9. Corrección estadística

- Test principal: Mann-Whitney U + test de permutación (10.000
  permutaciones de las etiquetas de familia dentro del universo primario
  A∪B) sobre `excess_CAGR_calendar`.
- Reportar p-valor bruto y **p-valor × 4** (corrección Bonferroni por las
  4 hipótesis ya probadas informalmente durante la exploración: H1
  retorno-propio, H2 sin-rendimiento-intrínseco, H3 tipos/divisa, H4
  refugio-vs-industrial — ver `ASESOR_EXTERNO_RELATIVE_FLOW_REFUGIO_VS_INDUSTRIAL.md`).
- **No se declara significancia si solo sobrevive en el p-valor bruto.**

## 10. Criterios de interpretación

Idénticos en espíritu al diseño original, aplicados aquí a la versión
acotada (sin los criterios que dependen de piezas diferidas: costes,
sub-muestras temporales):

**Suggestive** si TODOS se cumplen:
- mediana(excess_CAGR_A) > mediana(excess_CAGR_B)
- ≥60% de activos de A (primario) con excess_CAGR>0
- ≥60% de activos de B (primario) con excess_CAGR≤0
- la regla primaria supera a invertida, aleatoria (percentil ≥75) y
  momentum baseline en la familia A
- no depende de 1 activo extremo (leave-one-out)
- correlación intra-familia <0.7 en ambas familias, o si es mayor, se
  ajusta explícitamente la interpretación de n efectivo
- diferencia A vs B con p-valor Bonferroni <0.05

**Inconclusive** si: el efecto solo aparece en variantes de sensibilidad no
congeladas, se explica por H3/H9, no sobrevive a leave-one-out, o el
aleatorio/momentum iguala al resultado real.

**Not supported** si: A no supera a B en la métrica primaria, o la
diferencia no sobrevive Bonferroni, o `lag_minus_1d` mejora sustancialmente
el resultado (bug de lookahead).

**No se usa la palabra "confirmado"** en ningún caso — eso exige forward
OOS, explícitamente fuera de alcance de esta versión.

## 11. Qué NO se puede cambiar tras ejecutar

Idéntico al diseño original: no tocar umbrales 3/8, no mover activos entre
familias, no usar Δ TAE como métrica primaria, no reportar solo los
resultados favorables, no añadir/quitar activos, no usar esto para señales
reales de trading, no tocar PCS/rot_score/carteras/motor IA, no
incorporarlo como hard rule.

## 12. Salidas esperadas

Todas bajo `research/relative_flow_family_test_v1/`:

- `relative_family_falsification_test.py` (script)
- `outputs/relative_family_test_v1_results.json`
- `outputs/relative_family_test_v1_trades.csv`
- `outputs/relative_family_test_v1_asset_summary.csv`
- `outputs/relative_family_test_v1_family_summary.csv`
- `outputs/relative_family_test_v1_leave_one_out.csv`
- `outputs/relative_family_test_v1_informe.md` (informe final con veredicto)

## 13. Puerta dura antes de escalar

Tras leer `outputs/relative_family_test_v1_informe.md`, se decide
explícitamente entre usuario y Claude Code si:
(a) descartar la hipótesis aquí,
(b) escalar a v1 completo (costes × 3, 1.000 sims, sub-muestras
temporales, leave-two-out, regresión multivariante), o
(c) diseñar directamente el forward OOS si el resultado es
suficientemente fuerte para justificarlo sin pasar por (b).

**Ninguna capa adicional se implementa sin esa decisión explícita.**
