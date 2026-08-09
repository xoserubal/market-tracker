# Refugio de valor vs. materia prima industrial — documento para asesor externo

**Fecha:** 2026-08-09
**Autor:** exploración interactiva ad-hoc (Claude Code) sobre datos reales del backtest de Relative Flow Lab
**Pregunta que se somete a revisión:** ¿es real la separación que hemos encontrado entre "activos refugio/especulativos" y "materias primas industriales", o es un artefacto de una exploración no preregistrada con muestra pequeña? ¿Cómo diseñaríamos el siguiente paso para intentar refutarla en serio?

Este documento es autocontenido: incluye contexto, metodología exacta, la
secuencia completa de hipótesis probadas (incluidas las que se descartaron) y
los datos crudos, para que un tercero pueda criticar el razonamiento sin
acceso al repositorio.

---

## 0. Aviso de origen — por qué esto pesa menos que un hallazgo normal de este proyecto

Este proyecto tiene una disciplina establecida para backtests: preregistro
escrito antes de ver resultados, corte dev/test, congelar combinaciones antes
de evaluarlas (ver `wiki/PREREGISTRO_RELATIVE_FLOW_LAB_V0.md` y
`wiki/RELATIVE_FLOW_LAB_HALLAZGOS.md`, el backtest formal del que sale esta
herramienta). **Esta exploración NO siguió esa disciplina** — fue una sesión
interactiva de "vamos mirando la tabla y probando ideas" sobre una
herramienta de inspección visual construida para ese backtest. Eso significa:

- Las combinaciones de entrada/salida se fueron probando y comparando *después*
  de ver qué pinta tenían los resultados (nunca se congeló nada de antemano).
- Los activos añadidos en cada ronda (metales preciosos, cripto, metales
  industriales, divisa/tipos) se eligieron **a propósito para confirmar o
  refutar la hipótesis del momento** — es decir, no es una muestra aleatoria
  ni siquiera una lista cerrada elegida de antemano. Esto es exactamente el
  patrón de "jugar con combinaciones" que el preregistro del backtest formal
  existe para evitar.
- Se probaron y descartaron **tres hipótesis previas** sobre los mismos datos
  (o subconjuntos crecientes de ellos) antes de llegar a esta — ver sección 2.
  Cada ronda de "prueba una variable, no funciona, prueba otra" sin corrección
  por comparaciones múltiples infla la probabilidad de encontrar algo que
  *parece* sólido sin serlo.

Por eso este documento no pide "confirmar el hallazgo" sino ayuda para
**diseñarlo como una prueba real** — con las garantías que esta sesión no tuvo.

---

## 1. Contexto mínimo

`relative.html` (Relative Flow Lab) puntúa 45 ratios de precios a diario
(`score`, clasificación Leader/Improving/Neutral/Weakening/Laggard, Trend
Up/Down/Mixed) — documentado en `CLAUDE.md`. Un backtest formal reciente
(`wiki/RELATIVE_FLOW_LAB_HALLAZGOS.md`, 2026-08-08) encontró que **el score
no predice alfa futuro de forma útil** (correlación pooled score↔alfa
≈0 en 1w/1m/3m, r=-0.009/+0.003/+0.012).

A partir de ese backtest se construyó una herramienta interactiva (tabla +
gráfico + calculadora de rentabilidad) para inspeccionar manualmente
episodios concretos y ver si un humano detecta algo que el análisis
estadístico agregado no vio. Esta conversación es esa inspección manual.

**Definiciones exactas usadas en toda esta exploración:**

- **Entrada — "paso a Improving":** el `score` (del ratio activo/SPY) cruza
  de <3 a ≥3 respecto al día anterior. Dispara aunque el mismo día el score
  ya salte a ≥8 (confirmado con el usuario, ver conversación previa).
- **Salida — "cualquiera de las dos":** se cierra la posición en cuanto se
  cumple la PRIMERA de estas dos condiciones (unión, no intersección):
  score cruza de ≥8 a <8 (salida ceñida), o score cruza de ≥3 a <3 (salida
  ancha, solo aplica si nunca llegó a cruzar 8).
- El retorno de cada tramo es el retorno del precio real del activo (no del
  ratio) entre el cierre del día de entrada y el cierre del día de salida.
  Si la posición sigue abierta al final de la ventana, se cierra al último
  precio disponible y se cuenta igual.
- **TAE (Tasa Anual Equivalente):** `retorno_diario = (1+retorno)^(1/sesiones)-1`,
  luego `TAE = (1+retorno_diario)^252 - 1`. Para la estrategia, `sesiones` =
  solo los días en que la posición estuvo abierta (suma de todos los tramos).
  Para buy&hold, `sesiones` = todos los días de la ventana. **Esto es
  intencional** — mide eficiencia de capital, no solo retorno bruto — pero
  hace que el TAE sea muy sensible al ruido cuando el retorno o el nº de
  días es pequeño (ver limitación en sección 4).
- **Δ TAE = TAE(estrategia) − TAE(buy&hold)** del mismo activo en la misma
  ventana. Es la métrica que se reporta en todas las tablas de abajo.
- **Ventana:** últimos ~730 días naturales desde hoy (2026-08-09), es decir,
  aprox. 2026-08-09 hacia atrás hasta 2024-08-09. Un único periodo histórico,
  sin partición dev/test — a diferencia del backtest formal.
- Todos los ratios son **activo / SPY** (excepto donde se indica lo
  contrario) — precios ajustados por dividendo vía yfinance (`auto_adjust=True`).

---

## 2. Secuencia de hipótesis — las tres que NO se sostuvieron

**H1 — "Los pares con retorno propio fuerte hacen ganar a la estrategia."**
Sobre los 17 pares vs-SPY del backtest original: r=+0.66, p=0.004 entre
retorno propio del activo (`bh_ret`) y Δ TAE. Parecía sólido.
**Al ampliar a 32 pares vs-SPY** (añadiendo 15 activos nuevos elegidos sin
relación con esta hipótesis — ver sección 3): **r cae a +0.21, p=0.26. No
significativo.** Contraejemplos directos: ARGT (+58% propio, Δ TAE -19.6),
Uranio (+95% propio, Δ TAE -20.9), Defensa (+81% propio, Δ TAE -26.4),
Semiconductores (+161% propio, la mayor subida de toda la muestra, Δ TAE
-9.3). **Descartada.**

**H2 — "Funciona en activos sin rendimiento intrínseco (oro/plata/cripto,
sin cupón ni dividendo)."** Oro, plata y bitcoin salían muy bien (Δ TAE
+53, +58, +51). Pero el cobre —mismo tipo de activo, sin rendimiento
intrínseco propio— salió con Δ TAE **-34.1**, de los peores de toda la
muestra. **Descartada** por el propio contraejemplo que pedimos comprobar.

**H3 — "Funciona en activos ligados a tipos de interés / divisa."**
Se añadieron mineras de oro, mineras junior, Ethereum. Los 5 salieron bien
(oro, plata, junior miners, bitcoin, ethereum: Δ TAE entre +36 y +58). Pero
al añadir los instrumentos de tipos/divisa *puros* — el índice dólar (DXY)
y TIPS — el patrón se rompe: DXY sale ligeramente negativo (-5.3), TIPS
solo modestamente positivo (+16.2), muy por debajo del resto del grupo.
**Refinada a H4**, no exactamente descartada — el matiz importa.

---

## 3. H4 — hipótesis actual: refugio de valor vs. materia prima industrial

**Enunciado:** la combinación entrada-Improving/salida-cualquiera bate a
comprar-y-mantener en activos que funcionan como refugio de valor o vehículo
especulativo (oro, plata, bitcoin, ethereum, mineras junior de oro), y
pierde sistemáticamente en materias primas cuyo precio depende de la demanda
industrial real (cobre, platino, paladio, metales base, mineras de oro
"normales"), incluso cuando estas últimas tuvieron retornos propios muy
altos en el periodo.

**Nota de sesgo de selección — léase antes de los datos:** platino, paladio
y metales base se añadieron *porque el usuario predijo explícitamente que
saldrían mal* ("intuyo que funciona excepcionalmente mal, podríamos
añadirlos para comprobar"). Que la predicción se cumpliera es una señal
más débil que si esos activos se hubieran elegido a ciegas — un patrón que
uno mismo predice y luego confirma con datos que uno mismo eligió es
exactamente el escenario que un revisor externo debe presionar más.

### 3.1 — Grupo refugio/especulativo (5 de 5 positivos)

| Activo | Retorno propio (2a) | Δ TAE |
|---|---|---|
| Plata (SLV) | +130,0% | **+57,7** |
| Oro (GLD) | +77,4% | **+53,3** |
| Mineras junior de oro (GDXJ) | +189,8% | **+51,4** |
| Bitcoin | +6,6% | **+50,6** |
| Ethereum | -26,4% | **+36,1** |

### 3.2 — Grupo materia prima industrial (5 de 5 negativos)

| Activo | Retorno propio (2a) | Δ TAE |
|---|---|---|
| Cobre (HG=F) | +65,1% | **-34,1** |
| Platino (PPLT) | +87,2% | **-25,0** |
| Metales base (DBB) | +46,3% | **-20,8** |
| Paladio (PALL) | +50,9% | **-5,4** |
| Mineras de oro "normales" (GDX) | +155,6% | **-6,3** |

### 3.3 — Divisa/tipos puros (no encajan limpiamente en ninguno de los dos grupos)

| Activo | Retorno propio (2a) | Δ TAE |
|---|---|---|
| TIPS (TIP) | +6,5% | +16,2 |
| Índice dólar (DXY) | -3,4% | -5,3 |

---

## 4. Tabla completa — los 41 pares vs SPY probados, ordenados por Δ TAE

n_trades = nº de tramos entrada→salida en la ventana. comp_ret = retorno
compuesto de la estrategia (bruto, no anualizado).

```
pair        activo    bh_ret  n_trades  comp_ret  delta_tae
vgk_spy     VGK          47.9        18      23.1     +105.1
xlf_spy     XLF          40.0        18      24.9      +78.1
slv_spy     SLV         130.0        29      45.3      +57.7
gld_spy     GLD          77.4        24      27.8      +53.3
gdxj_spy    GDXJ        189.8        28      78.8      +51.4
btc_spy     BTC-USD       6.6        27      24.5      +50.6
fxi_spy     FXI          49.0        25      21.1      +39.6
eth_spy     ETH-USD     -26.4        22       8.3      +36.1
xly_spy     XLY          39.8        18      18.4      +33.2
ewz_spy     EWZ          34.9        27      28.1      +31.7
iwm_spy     IWM          49.3        29      18.6      +30.5
hyg_spy     HYG          14.7        15       5.5      +21.7
ita_spy     ITA          81.0        48      31.0      +20.5
ewy_spy     EWY         179.5        25      60.9      +19.8
kre_spy     KRE          51.9        36      19.2      +16.7
tip_spy     TIP           6.5        13       3.5      +16.2
xlv_spy     XLV          14.3        24       5.5      +14.1
xlu_spy     XLU          25.4        27       8.9      +12.2
xop_spy     XOP          27.9        25       8.1      +11.7
tlt_spy     TLT          -6.2        19       1.6       +9.7
xlk_spy     XLK          85.0        29      18.0       +4.3
xli_spy     XLI          53.1        25      11.4       +0.3
bil_spy     BIL           8.4        16       0.7       -0.5
xlre_spy    XLRE         15.0        20       1.1       -2.8
xlb_spy     XLB          23.9        22       3.2       -3.3
argt_spy    ARGT         58.3        37      14.1       -3.6
dxy_spy     DX-Y.NYB     -3.4        24      -1.6       -5.3
pall_spy    PALL         50.9        38       8.6       -5.4
qqq_spy     QQQ          62.2        25       9.7       -5.5
gdx_spy     GDX         155.6        27      22.3       -6.3
smh_spy     SMH         161.1        29      21.1      -14.5
xlp_spy     XLP          13.3        17      -2.3      -15.2
inda_spy    INDA         -9.1        16      -4.7      -18.2
dbb_spy     DBB          46.3        29       0.2      -20.8
pplt_spy    PPLT         87.2        33       5.7      -25.0
xme_spy     XME         103.5        30       7.6      -26.0
xlc_spy     XLC          33.7        31      -4.2      -27.0
xbi_spy     XBI          65.5        36      -1.9      -34.0
copper_spy  HG=F         65.1        39      -2.9      -34.1
xle_spy     XLE          37.0        25     -16.7      -66.5
ura_spy     URA          95.5        33     -36.8     -113.0
```

Total: 41 pares vs SPY, 22 positivos / 19 negativos.

---

## 5. Limitaciones metodológicas explícitas

1. **Sin partición dev/test.** Todo esto es "dev" — nunca se reservó un
   tramo para confirmar sin retocar, a diferencia del backtest formal que
   sí lo hizo (`PREREGISTRO_RELATIVE_FLOW_LAB_V0.md`).
2. **Universo elegido a propósito, no aleatorio ni exhaustivo.** Cada ronda
   de activos nuevos se añadió para poner a prueba la hipótesis del momento
   — primero para ampliar n, luego específicamente para intentar refutar
   ("los metales van a salir mal, vamos a comprobarlo"). Esto reduce el
   valor probatorio de que la predicción se cumpliera.
3. **Múltiples hipótesis probadas sobre datos parcialmente solapados sin
   corrección estadística.** H1→H2→H3→H4 se probaron secuencialmente; cada
   "no funciona, probemos otra cosa" es una comparación más, y no se ha
   corregido por ello en ningún p-valor reportado.
4. **Un único régimen de mercado.** Los ~2 años de ventana son un solo
   periodo histórico (con al menos un shock conocido, abril 2025 — ver
   conversación previa sobre IWM). No hay manera de saber si el patrón
   sobrevive a un régimen distinto sin datos de otro periodo.
5. **El TAE es ruidoso para retornos/exposición pequeños.** Ya detectado en
   TLT/HYG en una ronda anterior: el retorno bruto de la estrategia puede
   ser mejor que buy&hold y aun así el TAE salir peor, simplemente por
   anualizar sobre pocos días de exposición. No se ha revisado si esto
   afecta a alguno de los 41 resultados de la tabla.
6. **n=10 en el núcleo de la hipótesis actual** (5 refugio + 5 industrial).
   Suficiente para una separación visualmente limpia, insuficiente para
   cualquier prueba estadística formal seria.
7. **No hay coste de transacción, slippage, ni impuesto** en ningún cálculo.

---

## 6. Lo que pedimos concretamente

1. **¿Es esta hipótesis (refugio de valor vs. industrial) falsable de forma
   más rigurosa con los datos que ya tenemos**, o hace falta más universo?
   Si hace falta más universo, ¿cómo se elegiría sin repetir el sesgo de
   selección de la sección 3?
2. **¿Cómo diseñaríamos una partición dev/test para esto** dado que ya se ha
   "mirado" toda la ventana disponible de 2 años — ¿hace falta esperar a que
   pase más tiempo, o hay una forma de partición retrospectiva honesta
   (por activo en vez de por fecha, por ejemplo) que no esté ya contaminada?
3. **¿Qué corrección aplicaríamos por las 4 hipótesis ya probadas** (H1-H4)
   sobre datos solapados, si quisiéramos dar un p-valor honesto a la
   separación de la sección 3?
4. **¿Existe una definición objetiva y verificable de "refugio de valor vs.
   industrial"** (más allá de nuestra clasificación manual) que se pudiera
   aplicar a un universo más amplio sin intervención humana caso por caso —
   por ejemplo, correlación histórica con TIPS/oro real, o con el ciclo de
   manufactura global (PMI)?
5. Dado el hallazgo previo de que el score de Relative Flow Lab no predice
   alfa pooled (`RELATIVE_FLOW_LAB_HALLAZGOS.md`), **¿qué umbral de evidencia
   debería exigirse antes de considerar esto un sub-régimen real** del
   mismo sistema, en vez de ruido que hemos organizado narrativamente?
