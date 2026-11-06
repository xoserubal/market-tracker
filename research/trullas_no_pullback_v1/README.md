# Trullás sin esperar al retroceso (2026-11-06)

Pregunta del usuario: ¿y si se compra en cuanto se confirma la divergencia, sin esperar a que el precio
retroceda a la zona del 23-25%? Misma señal que producción (`evaluate_pivot_pair`); la entrada pasa a la
apertura de la primera sesión operable tras confirmarse el mínimo (b+6). Caché de precios compartida
(118 valores de Portfolio Tracker, 2019 → 2026-09-18). Script: `backtest.py` (`--save` → `summary.json`,
`trades.json`). Coste ida y vuelta 1 pp, igual que los estudios anteriores.

## Resultado

| Variante | n | Media | Con coste | Mediana | Aciertos | Media/desv |
|---|---:|---:|---:|---:|---:|---:|
| Comprar cualquier día y vender a 20 sesiones (referencia) | 201.921 | +2,79% | +1,79% | +0,33% | 50,9% | 0,035 |
| Estricta (zona 23-25%, sin look-ahead) | 39 | +0,67% | −0,33% | +1,64% | 53,8% | 0,066 |
| Sin esperar, objetivo 38,2% | 113 | +1,97% | +0,97% | +0,42% | 52,2% | 0,149 |
| Sin esperar, objetivo 61,8% | 201 | +1,20% | +0,20% | +0,97% | 51,7% | 0,103 |
| Sin esperar, salir a 20 sesiones | 608 | +2,33% | +1,33% | 0,00% | 49,5% | 0,107 |

1. **Sin esperar casi nunca hay operación con el objetivo actual.** Cuando el mínimo se confirma (5 sesiones
   de rebote), el precio ya ha superado el objetivo del 38,2% en el 81% de las señales (495 descartadas).
   Motivo: los niveles se miden sobre la distancia entre los DOS MÍNIMOS (mediana 7,4% del precio), así que la
   zona de entrada queda a ~1,8% sobre el mínimo y el objetivo a ~2,8%. El sistema es, en la práctica, «comprar
   casi en el mínimo con stop justo debajo y objetivo corto»; esperar al retroceso es lo que lo hace posible.
2. **Las que quedan (rebotes débiles) no son mejores.** Media +1,97%, pero mediana +0,42% y el 113% del
   beneficio lo aportan 5 operaciones; sin ellas, −0,27%. En 2025-2026: +0,68% (n=22).
3. **La divergencia por sí sola no anticipa subidas.** Comprar al confirmarse y aguantar 20 sesiones (608
   señales) rinde igual o peor que comprar cualquier día en el mismo universo: mediana 0,00% frente a +0,33%,
   aciertos 49,5% frente a 50,9%. Lo que pueda tener de bueno Trullás viene de la mecánica de entrada y salida,
   no de que la señal prediga el rebote.
4. **La regla estricta tampoco es concluyente.** n=39, −0,33% tras costes y −1,98% sin sus 5 mejores operaciones.
5. Por tier, más confirmación no mejora (T1 mejor que T2/T3), coherente con `trullas_vol_method_v1`.

Cautelas: varias variantes sobre las mismas señales, sin corrección por comparaciones múltiples; el corte
2019-2024 / 2025-2026 es descriptivo; operaciones del mismo valor pueden solaparse. La referencia «cualquier
día» tiene colas enormes (microcaps), por eso se comparan medianas y aciertos además de la media.

## Pregunta abierta

La implementación mide el Fibonacci entre los dos mínimos (`trullas_lib.evaluate_pivot_pair`: swing =
cierre del mínimo anterior − cierre del nuevo). Si el método original lo mide sobre el tramo bajista (desde el
máximo intermedio hasta el nuevo mínimo), las zonas y objetivos serían mucho más amplios y todo este análisis
cambia. Conviene confirmarlo con la fuente del método antes de estudiar más flexibilidades.
