# Trullás — divergencia con ventana extendida (6 meses), v1

Origen: revisando QXO a mano (2026-09-22/23) se encontró una divergencia
alcista real de marzo a agosto 2026 que el método estándar de
`evaluate_pivot_pair` (solo compara los DOS ÚLTIMOS pivotes consecutivos)
no detecta, porque un rebote intermedio (23-jun) "resetea" la cadena de
comparación. El usuario preguntó si ampliar la ventana de detección (6
meses) y comparar contra el mínimo más significativo, en vez de solo el
inmediato anterior, podría capturar estos casos — total o parcialmente.

## Metodología

Para cada par de pivotes consecutivos `(a, b)` que el método **estándar**
NO califica (si ya calificara, no hay nada nuevo que aportar):

1. Se busca una **referencia extendida `r`**: el pivote con el **precio
   más bajo** entre los que caen en una ventana de 126 sesiones (~6 meses)
   antes de `b`, exigiendo que sea estrictamente anterior a `a`.
2. Se clasifica la relación `r -> b` en 4 categorías
   (`trullas_lib.classify_extended_divergence`):
   - **FULL**: precio hace mínimo más bajo que `r` Y MACD más alto —
     divergencia completa, misma definición que el método estándar,
     aplicada a un par más separado en el tiempo.
   - **PARTIAL_FLAT_PRICE_RISING_MOMENTUM**: precio prácticamente igual a
     `r` (doble suelo) pero MACD mejora con claridad — sin caída de precio
     que retraceder.
   - **PARTIAL_LOWER_LOW_STALLING_MOMENTUM**: precio hace mínimo más bajo,
     MACD no llega a ser más alto, pero cae mucho menos de lo esperable
     dado su propio rango en la ventana (umbral 25% del rango, sin
     calibrar, primera pasada).
   - **NONE**: nada de lo anterior.

## Bug real encontrado y corregido durante la propia verificación — dos veces

**1. Selección de la referencia por MACD más negativo era tautológica.**
La primera versión elegía `r` como el pivote de **MACD** más negativo en
la ventana. Pero entonces "MACD de hoy > MACD de la referencia" es casi
una tautología (la referencia YA ES el mínimo por construcción) —
disparó "divergencia" en 896 casos con 100% de acierto a 5 días, algo
imposible para una señal de mercado real. Corregido seleccionando `r` por
el **precio** más bajo (eje independiente del que se prueba) — ahora que
el precio de hoy sea más bajo que ese mínimo histórico, y que el MACD de
hoy sea más alto que el de aquel mínimo de precio, son comparaciones
genuinamente no garantizadas.

**2. Medir "retorno futuro" desde el propio cierre del pivote es
tautológico para el horizonte de 5 sesiones.** `find_pivots_low` exige que
los 5 cierres siguientes a un pivote sean TODOS más altos que el propio
pivote — es la definición misma de "mínimo estricto en la ventana". Medir
`fwd_ret_5d` desde `close[b]` está garantizado positivo por construcción
(confirmado: 690/690 casos ganadores en la categoría `PARTIAL_FLAT` antes
de corregirlo). Corregido midiendo desde el primer día en que el pivote es
REALMENTE confirmable (`b + PIVOT_WINDOW`), que no tiene ninguna garantía
estructural. Tras el fix, esa categoría queda en ruido puro (ver abajo) —
el hallazgo real es que **no** predice nada, no que predijera algo.

Este segundo sesgo es una propiedad general de `find_pivots_low` (no
específica de este backtest) — cualquier análisis futuro que use pivotes
confirmados y mida retornos desde el propio cierre del pivote en un
horizonte ≤ `PIVOT_WINDOW` (5 sesiones) hereda el mismo problema. Anotado
aquí para no repetirlo.

Las categorías **FULL** y **PARTIAL_LOWER_LOW_STALLING_MOMENTUM** sí tienen
una caída de precio real que retraceder (`r -> b`) — se construye la misma
estructura Fibonacci y el mismo modelo de ejecución ya validado
(`find_entry_executable`, orden límite real en la apertura, zona 23-25%,
TP 38.2%, stop en el cierre del pivote, time-stop 20 sesiones) que usa
V1_EXECUTABLE en producción, solo que el swing se calcula desde `r` en vez
de desde el predecesor inmediato. Esto NO hereda el sesgo del punto 2
(entrada y salida se miden desde el día del *fill*, casi siempre varios
días después de `b`, no desde `close[b]`) y usa exactamente la misma
mecánica ya validada para el resto del sistema — la comparación contra el
baseline es de tú a tú.

## Resultados (117 tickers, universo Portfolio Tracker, 2019 → hoy)

| | n | media | mediana | win% | peor | mejor |
|---|---:|---:|---:|---:|---:|---:|
| **Baseline** (V1_EXECUTABLE, método estándar) | 54 | +1.27% | +2.02% | 66.7% | -19.4% | +39.4% |
| **FULL** (nuevo, no capturado por el método estándar) | 101 | +2.42% | +2.84% | 76.2% | -30.3% | +39.4% |
| **PARTIAL_LOWER_LOW_STALLING_MOMENTUM** (nuevo) | 55 | +2.32% | +3.08% | 72.7% | -25.6% | +47.9% |
| **Los dos nuevos combinados** | 156 | +2.39% | +3.01% | 75.0% | -30.3% | +47.9% |
| **PARTIAL_FLAT_PRICE_RISING_MOMENTUM** (sin estructura Fibonacci, medido desde confirmación real) | 690 | ~0% | 0% | ~50% | — | — |

Las 156 señales nuevas están repartidas en 87 tickers distintos (máx. 6
señales en un mismo ticker) y solo 2 pares se solapan en el tiempo — no es
el mismo evento de mercado contado varias veces disfrazado de n grande.

## Lectura

- **Sí hay valor en ampliar la ventana** — al menos en esta primera pasada
  sin optimizar ningún parámetro, FULL y PARTIAL_LOWER_LOW_STALLING dan
  ~3x más señales que el método estándar (156 vs 54), con métricas
  ligeramente mejores en media/mediana/win-rate. No es una mejora
  dramática ni una prueba estadística formal (sin split dev/test, sin
  corrección por comparaciones múltiples, sin contraste de significancia)
  — es una señal de que merece la pena seguir mirando, no una validación.
- **La categoría "parcial" que el usuario pidió explorar explícitamente
  (doble suelo con momentum mejorando, sin caída de precio) no aporta
  nada** una vez corregido el sesgo de medición — ruido puro. Es un
  hallazgo negativo real, no una limitación del análisis.
- **n sigue siendo pequeño para cualquier decisión de producción**: 101 y
  55 respectivamente, muy por debajo del umbral que este proyecto se exige
  antes de promover algo (~40-150 eventos, 2+ regímenes, dev/test) — mismo
  criterio que Ranking Score, Relative Flow Lab, PCS-floor factorial, etc.

## Explícitamente fuera de alcance de esta pasada

Split dev/test, calibración de `EXTENDED_LOOKBACK_BARS`(126)/
`EXTENDED_STALL_FRACTION`(0.25) contra rendimiento, corrección por
comparaciones múltiples, extensión a máximos (divergencia bajista, cortos
— fuera del alcance long-only del proyecto), integración en
`trullas_signal_calculator.py`/`trullas_shadow_portfolio.py` — nada de
esto se ha tocado, es investigación pura en `research/`.
