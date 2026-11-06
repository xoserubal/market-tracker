# Trullás: dejar correr la subida (2026-11-06)

Pregunta del usuario: en vez de cerrar en el objetivo del 38,2% (≈1-3% sobre la entrada), ¿dejar correr?
Entrada idéntica a producción y sin sesgo (orden límite en la zona 23-25% desde b+6); una sola posición
abierta por valor. Menú de salidas fijado de antemano (`backtest.py`), todas con el stop inicial en el
mínimo. 118 valores, 2019 → 2026-09-18, coste 1 pp ida y vuelta.

## Resultado (estricta + ampliada a 6 meses, ~153 operaciones)

| Salida | Media | Con coste | Mediana | Aciertos | Sin las 5 mejores | Sesiones |
|---|---:|---:|---:|---:|---:|---:|
| Producción: objetivo 38,2% | +0,28% | −0,72% | +1,29% | 52,6% | −0,89% | 3,6 |
| Objetivo 100% (volver al mínimo anterior) | +2,38% | +1,38% | −3,11% | 34,6% | +0,29% | 9,8 |
| Objetivo 161,8% | +2,37% | +1,37% | −3,99% | 24,3% | −1,07% | 15,2 |
| Salir al cruce bajista del MACD | +4,66% | +3,66% | −2,37% | 34,0% | −0,20% | 10,0 |
| Stop dinámico 2×ATR | +2,56% | +1,56% | −3,11% | 30,7% | −1,00% | 11,8 |
| Aguantar 60 sesiones | +3,25% | +2,25% | −4,50% | 17,9% | −2,85% | 21,3 |
| *Referencia: comprar cualquier día, 60 sesiones* | *+7,59%* | *+6,59%* | *+1,43%* | *52,5%* | — | 60 |

Solo con la estricta (39 operaciones) dejar correr empeora todo: el stop está ~1,8% por debajo de la entrada y
salta en 28-35 de las 39; las medias quedan entre +1,2% y −2,8% y los aciertos bajan al 8-28%.

- Dejar correr sube la media pero hunde la mediana y los aciertos: perfil de lotería (pérdidas pequeñas
  frecuentes, ganancias enormes raras).
- La media sale casi entera de tres operaciones: ASTS abr-2024 (+380% con salida por MACD), ASPI jun-2023
  (+214%) y BBAR oct-2025 (+59%). Sin las 5 mejores, todas las variantes quedan en torno a cero o negativas.
- Comprar cualquier día del mismo universo y aguantar 60 sesiones rinde más en media y mucho más en mediana:
  el universo (muchas small caps, 2019-2026 alcista) sube solo. Lo ganado al dejar correr es la deriva del
  mercado más un par de golpes de suerte, no la señal.
- Primera pasada con un fallo propio corregido: dos señales seguidas del mismo valor abrían dos posiciones a la
  vez (ASTS contado dos veces); ahora una sola posición por valor. Afecta poco (156 → 154 en producción).

Conclusión: dejar correr no rescata a Trullás. Coherente con `trullas_no_pullback_v1` y
`trullas_extended_divergence_v2`: con la medición actual del Fibonacci la señal no tiene ventaja con ninguna
salida probada.
