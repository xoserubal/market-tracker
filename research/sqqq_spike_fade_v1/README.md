# SQQQ spike-fade v1 — ¿qué definición de «giro» sirve? (2026-11-17)

Script: `backtest.py` (preregistro en el docstring). SQQQ/QQQ 2010-2026, dev hasta 2018, test desde 2019,
entrada a la apertura siguiente, cooldown 10 sesiones. Mide el precio de SQQQ, no opciones.

| Regla | n dev/test | r21 mediana | baja a 21 | r63 mediana | P(sube ≥30% en 21) |
|---|---|---|---|---|---|
| Todos los días | 2012/1980 | −5 / −8 | 72/70% | −16 / −20 | 5/10% |
| Solo extendido | 44/45 | −10 / −9 | 70/70% | −22 / −25 | 5/25% |
| Producción (ext + giro 1 día + QQQ ≥ +2,5% semanal) | 0/3 | — / +10 | —/33% | — / −16 | —/67% |
| Ext + giro 1 día, sin QQQ | 16/22 | −12 / −12 | 81/67% | −23 / −24 | 0/24% |
| Ext + giro 2 sesiones | 4/5 | −10 / −4 | 100/60% | | 0/60% |
| Ext + histograma < 0 | 2/5 | | | | |
| Ext + cierre < mínimo 3 sesiones | 6/9 | −10 / 0 | 67/50% | | 0/38% |

Lectura:
- La regla de producción casi nunca dispara (3 veces en 16 años: ene-22, may-22 —dos rebotes falsos del bajista— y
  ago-24). El filtro «QQQ +2,5% en la semana» rara vez coincide con SQQQ extendido.
- El decay manda: SQQQ baja a 21 sesiones el 70% de los días cualesquiera y a 63 el 81-83%.
- Exigir el giro de 1 día (sin QQQ) mejora poco a 21 sesiones frente a «solo extendido» (−12 vs −9/−10) e igual a 63.
- Giros más estrictos dan menos eventos y no mejoran (con n = 4-9, no se puede afirmar nada).
- La cola sigue ahí en test: 24-25% de probabilidad de +30% en 21 sesiones tras un spike (2022).
Descriptivo y post-hoc respecto a la regla actual; n efectivo menor que el nominal (episodios agrupados).
