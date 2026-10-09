# Trullás: ¿importa cómo se define la divergencia de volumen (T3)? (2026-10-09)

Retrospectivo pedido por el usuario. Mismo universo y caché que `trullas_divergence_backtest_v1` (118 tickers,
2019→hoy), **sin look-ahead** (primera apertura accionable = `b + PIVOT_WINDOW + 1`), misma salida
(stop pivote / TP 38.2% / time-stop 20). `backtest.py` lo reproduce.

Métodos de volumen: **A** (producción) vela exacta del pivote · **B1** máximo en [p-2, p+2] · **B2** máximo
en el tramo de caída hacia el pivote. T3 = divergencia RSI + volumen; T2 = RSI sin volumen; T1 = solo MACD.

## Resultado
- **A y B coinciden en el tier el 88% (B1) y 82% (B2) de las veces.** Definir el volumen de otra manera
  cambia poco la clasificación.
- **Más confirmación NO da mejor resultado** (626 pares con divergencia MACD, retorno a +21 sesiones desde la
  primera apertura accionable, sin modelo de entrada):

| | T1 (solo MACD) | T2 | T3 |
|---|---|---|---|
| A | n=351 +3.62% win 54% | n=133 +2.21% | n=142 +1.73% win 47% |
| B1 | idem | n=132 +3.06% | n=143 +0.95% win 49% |
| B2 | idem | n=160 +2.93% | n=115 +0.62% win 50% |

  T3 queda 1.5 a 2.8 pp por debajo del resto con los tres métodos; el T1 es el mejor. Errores estándar de
  1.2 a 2.2 pp: ninguna diferencia es estadísticamente sólida, pero el signo es contrario al método.
- **Operaciones ejecutables** (n=4 a 22 por celda, inconclusas): T3 estricto n=4 (A/B1) o 6 (B2); flexible
  T3 n=8 a 11. Ningún método destaca.

## Cautelas
Pares consecutivos comparten pivotes y los retornos a 21 sesiones se solapan: los errores estándar están
subestimados. Un solo régimen largo (2019→hoy, mayoritariamente alcista). Sin split dev/test ni corrección por
comparaciones múltiples: descriptivo, no para promover nada.

## Conclusión
No hay evidencia de que el volumen (en ninguna de las 3 definiciones) mejore la señal; los tiers T2/T3 no se
sostienen como indicador de calidad con estos datos. El prospectivo (`vol_div_peak` en el histórico) no se
justifica por ahora. Sin cambios en producción.
