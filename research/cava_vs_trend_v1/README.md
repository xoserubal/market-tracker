# Cava `risk_off` frente a VIX + tendencia del SPY (v1)

Preregistro: `wiki/PREREGISTRO_CAVA_VS_TENDENCIA_V1.md` (huella en `PREREGISTRO.sha256`, guardada antes de calcular).
Ejecución única. Script: `run.py` → `results.json`. Reutiliza las posturas de `research/cava_vs_vix_v1`.

## Resultado formal: INCONCLUYENTE por falta de casos
Solo **10 de los 848 días `risk_off` (1,2 %)** ocurren con el VIX tranquilo **y** el SPY por encima de su SMA200.
- Son 3 episodios, todos en 2020-2026.
- En ellos, H1 = −1,39, con un IC enorme (−7,3 a +1,7).
- En 2005-2012 y 2013-2019 no hay ningún caso.

## Lo que sí dice
**1. En la práctica, `risk_off` ≈ «VIX alto o SPY por debajo de su SMA200».** El 98,8 % de los avisos de Cava
coincide con alguna de esas dos reglas simples. La conclusión de la prueba anterior («Cava ve riesgo que el VIX no
ve») se explica casi entera por la tendencia del SPY.

**2. Las otras dos definiciones de tendencia dejan más días sin cubrir, y Cava añade caída en ellas:**

| Regla de tendencia | Días de Cava sin cubrir | Diferencia de caída (H1) | IC 95 % |
|---|---|---|---|
| T15: SPY en el 15,7 % más bajo de distancia a su SMA200 | 93 | −1,53 | −2,76 a −0,29 |
| DD10: SPY ≥ 10 % por debajo de su máximo de 252 sesiones | 125 | −1,61 | −3,04 a −0,21 |
| Régimen sin desfase (con T, la regla primaria) | | −0,43 | |

Estas sensibilidades no deciden la clasificación.

**3. Dentro de los días en que avisa «VIX o tendencia» (24 % del tiempo), Cava separa los malos de los que rebotan**
(tabla descriptiva preregistrada):

| | Días | Peor caída del mes siguiente | Volatilidad 21 días | Retorno a 63 sesiones |
|---|---|---|---|---|
| VIX o tendencia, **con** `risk_off` | 838 | −5,0 | 27,3 % | +2,4 |
| VIX o tendencia, **sin** `risk_off` | 467 | −3,5 | 23,3 % | +4,9 |
| Ninguna regla | 4 101 | −2,2 | 12,4 % | +2,8 |

## Lectura
- **Cava casi nunca avisa cuando el VIX y la tendencia están tranquilos.** Como alarma independiente, añade muy poco.
- **Su valor posible está en ser más selectiva.** Con alrededor de un tercio menos de días activos que «VIX o
  tendencia», se queda con los tramos de más caída y deja fuera los que rebotan (+4,9 a 3 meses).
- Eso es un hallazgo descriptivo, no confirmado. Ponerlo a prueba como hipótesis principal exigiría un preregistro
  nuevo y, sobre todo, datos nuevos: esta muestra ya está muy usada.
- **Uso práctico razonable:** como regla de riesgo, «VIX alto o SPY < SMA200» da casi la misma cobertura sin
  depender del motor. Cava sirve para afinar dentro de esos días: no añadir riesgo con `risk_off`; con VIX o tendencia
  pero sin `risk_off`, no vender.
