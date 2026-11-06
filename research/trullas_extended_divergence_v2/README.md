# Divergencia ampliada de Trullás, v2 (2026-11-06)

Corrige `trullas_extended_divergence_v1` (2026-09-23), que buscaba la entrada desde el día siguiente al
mínimo (b+1) cuando el mínimo solo se sabe confirmado al cierre de b+5: las entradas de b+1..b+5 no eran
operables y, por construcción del fractal, eran precisamente las sesiones en que el precio ya subía. Aquí la
orden límite empieza en b+6. Añade la ventana de 12 meses además de la de 6. Misma mecánica que producción
(zona 23-25%, objetivo 38,2%, stop en el mínimo, 20 sesiones), 118 valores de Portfolio Tracker, 2019 →
2026-09-18, coste 1 pp ida y vuelta. Script: `backtest.py` (`--save` → `summary.json`, `trades.json`).

## Resultado

| Señal | n | Media | Con coste | Mediana | Aciertos | Media sin las 5 mejores |
|---|---:|---:|---:|---:|---:|---:|
| Estricta (pares consecutivos) | 39 | +0,67% | −0,33% | +1,64% | 53,8% | −1,98% |
| Ampliada 6 meses (añadidas) | 117 | +0,29% | −0,71% | +1,30% | 53,0% | −0,97% |
| Ampliada 12 meses (añadidas) | 110 | +0,03% | −0,97% | +1,14% | 51,8% | −1,18% |
| Estricta + 6 meses | 156 | +0,38% | −0,62% | +1,32% | 53,2% | −0,76% |
| Estricta + 12 meses | 149 | +0,20% | −0,80% | +1,30% | 52,3% | −0,84% |

- **El resultado prometedor de v1 era el sesgo.** v1: FULL n=101, +2,42%, 76% aciertos. v2, misma
  categoría: n=76, −0,12%, 53%.
- Ampliar la ventana triplica o cuadruplica las operaciones, pero todas las versiones quedan en torno a cero
  antes de costes y negativas después. 12 meses no mejora a 6 (la referencia elegida está a 3,3 meses en
  mediana: el mínimo más bajo de un año suele ser reciente).
- Perfil común: mediana positiva (+1,3%) y ~53% de aciertos, pero media ≈ 0: muchas ganancias pequeñas al
  tocar el objetivo y pérdidas grandes cuando el precio abre por debajo del stop (peor −30%).
- 2025-2026 (n≈18-28) sale algo mejor en algunas versiones, pero sin las 5 mejores operaciones vuelve a ser
  negativo: ruido con estas muestras.
- **La señal no anticipa subidas.** Comprar al confirmarse y aguantar 20 sesiones: estricta (626 señales)
  mediana 0,00%, ampliada 6 meses (1.109) +0,53%, 12 meses (822) −0,02%, frente a +0,33% de comprar cualquier
  día del universo.

Conclusión: ni la divergencia ampliada a 6 o 12 meses ni la estricta muestran ventaja con esta mecánica. La
pregunta abierta sigue siendo la de `trullas_no_pullback_v1`: si el método original mide el Fibonacci desde el
máximo intermedio y no entre los dos mínimos.
