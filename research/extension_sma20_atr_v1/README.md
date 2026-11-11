# Extensión sobre la SMA20 en ATR — S&P 500 + Nasdaq 100 (v1)

Preregistro firmado el 2026-11-11: `wiki/PREREGISTRO_EXTENSION_SMA20_ATR_V1.md` (huella en `PREREGISTRO.sha256`).
Se ejecutó una sola vez.
- **Datos:** 519 símbolos de yfinance (2015 a 2026-11-10); 152 622 pares valor-semana en la prueba.
- **Scripts:** `fetch_prices.py` y `analyze.py` → `results.json`.

## Resultado: INCONCLUYENTE (sin efecto útil demostrado)
Exceso del decil más extendido (D10) a 20 sesiones frente a la media del universo, en bruto:

| | Desarrollo 2016-2020 | Prueba 2021-2026 |
|---|---|---|
| D10 | −0,30 (t −1,9) | **−0,11** (t −0,5; IC 95 % −0,61 a +0,38) |
| IC de X sin controlar | −0,033 (t −2,6) | −0,007 (t −0,6) |
| IC del residuo frente a RS63 | −0,027 (t −2,3) | **0,000** (t 0,0) |

**Criterios:**
- se cumplen tres: mismo signo en desarrollo, D10 por debajo de D1-D9 y negativo en 3 de 4 subperiodos;
- fallan cuatro:
  - el efecto no llega a −0,5;
  - el residuo frente a RS63 es nulo en la prueba;
  - D10 sale positivo (+0,17) sin el 1 % de peores eventos;
  - con datos no solapados solo es negativo en 2 de 4 rejillas.

El IC llega a −0,61, así que no puede descartarse un efecto de −0,5. Pero el punto central es −0,11 y en la prueba no
hay nada que no explique ya la fuerza relativa.

**Deciles (prueba):** de D1 a D10 van de +0,10 a −0,11, sin escalera. En desarrollo sí había escalera (de +0,49 a
−0,30). La extensión y RS63 correlacionan 0,43 en rango.

**Descriptivo (prueba):**
- X > 2 (22 706 casos): −0,39 (t −1,2);
- X > 3 (7 314 casos): −0,61 (t −1,5).

## Sensibilidades
| | D10 prueba | Residuo prueba |
|---|---|---|
| 5 sesiones | −0,02 | −0,006 |
| 10 sesiones | −0,05 | −0,002 |
| SPY por encima de su SMA200 | +0,04 | |
| SPY por debajo de su SMA200 | −0,78 (t −1,4) | |
| Neutral por sector | −0,04 | |

## Lectura
- **En grandes empresas de EE.UU., estar extendido sobre la SMA20 no anticipa un peor resultado en 2021-2026** de forma
  que sirva de filtro.
- **El efecto de 2016-2020 se diluye.** Lo poco que queda es la misma reversión de corto plazo que ya mide la fuerza
  relativa a 3 meses.
- **Las extensiones extremas (X > 3) y los mercados bajistas** apuntan en la dirección esperada, pero sin
  significación. Son descriptivos y no se promueven.
- **No se cambia el PCS ni `extension_risk`.**
- **Límites:**
  - componentes actuales (sesgo de supervivencia);
  - universo de grandes empresas, no el universo propio (small caps, TSX-V), donde el comportamiento podría ser
    distinto.
