# "Fallo de MACD" (fallo bajista de implicaciones alcistas) — backtest v1

Origen: el usuario describió el patrón literal del método Trullás para
incorporarlo como detector en la pestaña Trullás:

> 1. El precio cae y la línea MACD se encuentra por debajo de su señal.
> 2. Se produce una recuperación y el MACD cruza por encima de la señal.
> 3. El precio vuelve a caer y establece un nuevo mínimo.
> 4. El MACD también retrocede, pero no consigue cruzar de nuevo por
>    debajo de su señal.
> 5. La línea MACD vuelve a girarse al alza. Ese intento fallido
>    constituye el fallo bajista de implicaciones alcistas.

Se preguntó al usuario antes de construir nada, y se acordó: **validar con
backtest primero** (mismo criterio que el propio sistema Trullás, Cruce Rojo
D, Mirror Espejo); condición del paso 4 **estricta** (el MACD debe permanecer
por encima/igual a su señal en TODO el tramo entre el cruce alcista y el
nuevo mínimo, no solo en el instante del mínimo); "nuevo mínimo" = **pivote
fractal confirmado** (mismo `find_pivots_low`, ventana de 5 sesiones, que ya
usa el resto del sistema Trullás); y, si el backtest resulta favorable, el
alcance inicial es **solo un panel visual** en `trullas.html` — sin conectar
a `TRULLAS_SHADOW` ni al sistema de alertas hasta que haya evidencia que lo
justifique.

## Diferencia con la divergencia estándar ya validada

El sistema Trullás en producción (`evaluate_pivot_pair`) exige
`macd[b] > macd[a]` — el **valor crudo** del MACD es mayor en el pivote
nuevo que en el antiguo. El "fallo de MACD" es un gate distinto, sobre la
**relación línea-vs-señal**: exige que la línea nunca vuelva a cruzar por
debajo de su señal en todo el tramo entre la recuperación y el nuevo
mínimo — una condición más específica sobre la forma de la recuperación,
no solo sobre el nivel final.

Implementado en `evaluate_macd_failure_swing()` (`scripts/trullas_lib.py`),
con un flag `require_turn_up` (paso 5) para poder medir su sensibilidad por
separado.

## Metodología

- Universo y caché: mismos 117 tickers y mismo rango 2019→hoy que
  `research/trullas_divergence_backtest_v1/ohlcv_cache.json` — sin
  descargar nada nuevo.
- Pares de pivotes de mínimo **consecutivos** (`zip(pivots, pivots[1:])`),
  mismo criterio que el resto de backtests Trullás.
- Swing mínimo del 3% (`MIN_SWING_PCT`, la misma constante que ya usa el
  resto del sistema) — el usuario no especificó un umbral en la
  descripción del patrón, se reutilizó el ya existente para no introducir
  un parámetro nuevo sin pedir, y para que "nuevo mínimo" no cuente un
  ruido de un día como si fuera la secuencia descrita.
- Dos mediciones por cada par que califica:
  - **(A) Descriptiva pura** — retorno del precio a 5/21/63 sesiones desde
    el primer día en que el pivote `b` es REALMENTE confirmable
    (`b + PIVOT_WINDOW`), nunca desde `b` mismo (sesgado por construcción —
    mismo bug ya encontrado y corregido en
    `research/trullas_extended_divergence_v1`).
  - **(B) Trade ejecutable** — misma estructura Fibonacci y mismo modelo de
    ejecución ya validado como el más realista del sistema
    (`find_entry_executable`: orden límite real en la apertura, zona
    23-25% del swing `a→b`, TP 38.2%, stop = `close[b]`, time-stop 20
    sesiones) — para comparar en las mismas unidades que el baseline ya
    conocido (`V1_EXECUTABLE`, n=54, mean=+1.27%).
- Se reporta también el solape con el método estándar (cuántos pares que
  aquí califican YA calificaban con `evaluate_pivot_pair`) y una variante
  de sensibilidad sin el paso 5 (`require_turn_up=False`).

## Resultado

**Patrón muy raro y, con los datos disponibles, sin evidencia de aportar
algo mejor que el método ya validado.**

De **11.464 pares de pivotes consecutivos** en todo el universo, solo
**74 (0,65%)** cumplen el gate completo — coherente con que la secuencia
descrita es específica y poco frecuente, no un ruido de cualquier rebote.
El paso 5 (giro al alza confirmado) casi nunca es la condición que decide:
de 75 candidatos sin exigirlo, 74 ya lo cumplían de todos modos — una vez
que la línea se mantiene todo el tramo por encima de su señal, es raro que
no gire al alza para cuando el pivote se confirma.

**Embudo hasta convertirse en trade ejecutable** (de los 74 candidatos):

| Resultado | n | % |
|---|---:|---:|
| Invalidado (rompe el stop antes de entrar) | 42 | 57% |
| Nunca vuelve a la zona de entrada en 15 sesiones | 26 | 35% |
| Entra de verdad | 6 | 8% |

**El 57% de los candidatos se invalida antes siquiera de poder operarse**
— es decir, más de la mitad de las veces que aparece esta secuencia, el
precio sigue cayendo por debajo del mínimo que la originó, en vez de
formar un suelo. Eso ya es una señal de alarma sobre la hipótesis de
"implicaciones alcistas", independiente de cómo se mida el resto.

**(A) Descriptivo — retorno de precio desde la confirmación (n=74):**

| Horizonte | n | media | mediana | win% | peor | mejor |
|---|---:|---:|---:|---:|---:|---:|
| 5 sesiones | 74 | +1.90% | +0.79% | 51.4% | -25.5% | +69.0% |
| 21 sesiones | 74 | +5.56% | **-2.74%** | **48.6%** | -57.9% | +140.6% |
| 63 sesiones | 72 | +5.77% | **-1.36%** | **47.2%** | -59.3% | +165.5% |

La media positiva está sostenida por unos pocos casos extremos (mejor
+140-165%, peor -58/-59%, desviación típica 31-43 puntos) — la **mediana**
es negativa en los dos horizontes más largos y el **win% está por debajo
del 50%** en ambos. Para un patrón que se presenta como "de implicaciones
alcistas", que más de la mitad de los casos tengan retorno negativo a
21-63 sesiones no es el resultado que la hipótesis predice.

**(B) Ejecutable — mismo modelo Fibonacci que el baseline (n=6, insuficiente
para conclusión, reportado por completitud):**

| Variante | n | media | mediana | win% | peor | mejor |
|---|---:|---:|---:|---:|---:|---:|
| Baseline ya validado (`V1_EXECUTABLE`, divergencia estándar) | 54 | +1.27% | +2.02% | 66.7% | -19.4% | +39.4% |
| Fallo de MACD — todos | 6 | +1.85% | +2.63% | 66.7% | -2.3% | +5.5% |
| Fallo de MACD — **solo los que el método estándar NO capturaba** | **2** | **-0.19%** | -0.19% | 50.0% | -1.8% | +1.4% |

66,7% de los 6 trades ejecutables (4/6) **ya calificaban** con el método de
divergencia estándar que produce el baseline — es decir, este gate nuevo
aporta muy poca cobertura genuinamente distinta, y los **2 casos realmente
nuevos** (JNJ y SLS, ver tabla abajo) tienen media negativa.

Los 6 trades ejecutables, para referencia:

| Ticker | Pivote A | Pivote B | Swing | ¿Ya lo capturaba el método estándar? | Retorno | Salida |
|---|---|---|---:|:---:|---:|---|
| BSX | 2026-02-11 | 2026-03-12 | 6.7% | Sí | -2.32% | stop |
| CEPU | 2022-07-05 | 2022-07-21 | 4.0% | Sí | +4.45% | tp |
| EOSE | 2026-02-27 | 2026-03-30 | 22.8% | Sí | +5.52% | tp |
| JNJ | 2023-01-30 | 2023-03-09 | 6.6% | **No** | -1.82% | stop |
| MSTR | 2025-11-21 | 2025-12-31 | 10.9% | Sí | +3.81% | tp |
| SLS | 2020-01-13 | 2020-02-03 | 8.1% | **No** | +1.44% | tp |

## Conclusión

**No se recomienda construir el panel** con la evidencia actual:

1. El patrón es extremadamente raro (74 de 11.464 pares, 0,65%) — un panel
   basado en esto estaría vacío la inmensa mayoría de los días sobre el
   universo de Portfolio Tracker.
2. El 57% de los candidatos se invalida antes de confirmar nada — el
   patrón no protege de forma fiable contra que el precio siga cayendo.
3. La medición descriptiva pura (la que menos supuestos de ejecución
   introduce) tiene mediana negativa y win%<50% a 21-63 sesiones.
4. La parte que sí aporta cobertura nueva frente al método ya validado
   (2 de 6 trades ejecutables) rinde peor que el baseline, no mejor.
5. Relajar la condición 4 (versión laxa, ver sección siguiente) no lo
   rescata — al contrario, la media de los trades ejecutables cae de
   +1.85% a +0.03% y los casos genuinamente nuevos empeoran de -0.19% a
   -3.76%. No hay ningún umbral de estrictez entre las dos versiones
   probadas donde el patrón funcione.

Ninguno de estos puntos es individualmente concluyente con un n tan
pequeño — pero todos apuntan en la misma dirección (nada, o negativo), no
hay ningún indicio a favor que los contrapese, y relajar la condición más
sospechosa (la 4) hace el resultado peor, no mejor. Mismo patrón que otras
hipótesis descartadas en este proyecto (Capitulación Precursores, Relative
Flow Family Test v1): una descripción de manual que suena razonable, pero
que no sobrevive al contraste con datos reales de este universo concreto.

**No se ha tocado nada en producción** — `evaluate_macd_failure_swing()`
vive en `scripts/trullas_lib.py` marcada explícitamente como
"investigación, no en producción" (mismo patrón que el resto de funciones
de esta familia: `evaluate_early_candidate_b0`, `classify_extended_divergence`),
sin ningún llamador desde `trullas_signal_calculator.py` ni
`trullas_shadow_portfolio.py`. `trullas.html` no se ha tocado.

## Variante laxa de la condición 4 (2026-09-24) — tampoco mejora, es peor

El usuario pidió probar la alternativa que había quedado descartada de
entrada: en vez de exigir que la línea MACD permanezca por encima/igual de
su señal en **todo** el tramo entre el cruce alcista y el nuevo mínimo
(`strict_stretch=True`), exigir solo que lo esté **en el instante del
nuevo mínimo** (`strict_stretch=False`, permite que haya oscilado por
debajo en algún punto intermedio). Implementado como parámetro de
`evaluate_macd_failure_swing()`, sin tocar el comportamiento por defecto
(sigue siendo la versión estricta).

**No mejora nada — si acaso empeora:**

| | Estricta (primaria) | Laxa |
|---|---:|---:|
| Candidatos descriptivos | 74 | 145 |
| Trades ejecutables (n) | 6 | 7 |
| Trades ejecutables — media | +1.85% | **+0.03%** |
| Trades ejecutables — win% | 66.7% | 57.1% |
| Trades **nuevos** (no capturados por el método estándar) — n / media | 2 / -0.19% | 3 / **-3.76%** |
| Descriptivo, mediana a 21 sesiones | -2.74% | **0.0%** |
| Descriptivo, mediana a 63 sesiones | -1.36% | **0.0%** |
| Descriptivo, win% a 21/63 sesiones | 48.6% / 47.2% | 49.7% / 47.9% |

La versión laxa **duplica aproximadamente el número de candidatos** (145
vs 74, como cabía esperar al relajar la condición), pero la calidad no
sube con la cantidad — al contrario: la media de los trades ejecutables
cae de +1.85% a prácticamente cero (+0.03%), y los 3 casos genuinamente
nuevos que aporta frente al método estándar (JNJ/SLS de la versión
estricta, más uno adicional) tienen media **-3.76%**, peor incluso que los
-0.19% ya débiles de la versión estricta. La mediana descriptiva pasa de
negativa a exactamente 0.0% en vez de a positiva — sigue sin haber
evidencia de nada, solo más ruido alrededor de cero.

Conclusión sin ambigüedad: **relajar la condición no rescata el patrón**.
Ambas versiones (estricta y laxa) se descartan igual.

## Fuera de alcance de este backtest

Ampliar el universo más allá de Portfolio Tracker. Costes de transacción
(con n=6-7 ejecutables no aporta nada nuevo). Cualquier preregistro con
split dev/test — no aplica, este backtest nunca llegó al punto de proponer
operar nada.
