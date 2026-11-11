# Flow Continuación y Flow Reversión con las reglas de `SCREENER_SHADOW` (v1)

Preregistro: `wiki/PREREGISTRO_FLOW_CONT_REV_V1.md`, firmado el 2026-11-11 (v3) y congelado (SHA-256 `29752cd9…`,
`PREREGISTRO.sha256`). Contraste ejecutado **una sola vez** el 2026-11-11; `study.py` comprueba el hash antes de
calcular. Producción y carteras sin tocar.

## Veredicto (versión B decide: sesiones, entrada a la apertura siguiente, salidas a la apertura siguiente)

| Filtro | U1 prueba, exceso B | IC 97,5 % (Bonferroni) | Veredicto |
|---|---|---|---|
| Flow Continuación | −0,16 pp por operación (t −1,13; 9.731 eventos) | −0,48 a +0,16 | **NO SOPORTADO** |
| Flow Reversión | +0,16 pp (t +0,97; 12.027 eventos) | −0,21 a +0,52 | **INCONCLUYENTE** |

No se cumple ninguno de los seis criterios de VALIDADO para ninguno de los dos filtros.
- **Continuación:** el intervalo entero queda por debajo del mínimo de interés (+0,5 pp).
- **Reversión:** su intervalo llega a +0,52 por solo 0,02, así que no se puede descartar formalmente. Pero el
  resto de pruebas van en contra:
  - desarrollo −0,02;
  - acierto 47,5 % frente al 48,6 % del universo;
  - sin el 1 % de mejores operaciones, −0,38;
  - U2 −0,16.

## Detalle (exceso medio por operación frente al universo en las mismas velas y con las mismas reglas, pp)

| | U1 desarrollo B | U1 prueba B | U1 prueba A | U1 prueba A +1 sesión | U2 B | U2 A |
|---|---|---|---|---|---|---|
| Continuación | −0,23 (t −2,1) | −0,16 | −0,11 | −0,01 | −0,04 | +0,26 |
| Reversión | −0,02 | +0,16 | +0,09 | +0,01 | −0,16 | −0,03 |

- **Acierto (B, U1 prueba):** Continuación 47,3 % frente a 48,1 % del universo; Reversión 47,5 % frente a 48,6 %.
- **Retorno neto mediano (B, U1 prueba):** Continuación −0,32 %, Reversión +0,01 %. La media positiva sale de una
  minoría de operaciones grandes; sin el 1 % mejor, el exceso pasa a −0,48 y −0,38.
- **Sin *stops*:**
  - Continuación es negativa a 5, 10 y 20 sesiones en las dos muestras de U1.
  - Reversión a 20 sesiones da +0,41 en prueba (t 1,6) pero −0,10 en la versión A. No es robusta.
- **Por régimen (SPY frente a su SMA200):** ninguna celda significativa en la prueba. Continuación es peor con
  SPY por debajo de su SMA200 (desarrollo −0,60 en B y −0,70 en A, t −1,7 y −2,2).
- **Salidas (B, U1 prueba):** 60-65 % por tiempo, 31-36 % por *hard stop* y solo 4 % por *trailing*. El *trailing*
  casi nunca llega a activarse en 14 días.
- **Solapes:** 60-80 operaciones abiertas a la vez de media en U1; 10-22 en U2. La versión sin solapes da lo mismo
  (Continuación −0,14, Reversión +0,16).
- Newey-West con retardo 20 no cambia nada.
- **Operaciones excluidas** por seguir abiertas al final de los datos: 0-13 por celda.

## Qué se puede decir
- Con reglas y fechas idénticas, las entradas de Continuación y Reversión no rinden mejor que entrar en cualquier
  valor del universo. Tampoco en desarrollo ni en tus tickers (U2).
- Lo que se veía en AI Picks Lab (Continuación +0,3 % frente a −2,6 % del azar en un mes) no se sostiene con 10
  años de datos. Encaja con el ruido de un periodo corto y con que la mejor operación de los dos filtros era la misma
  (TDOC).
- **Sobre la ejecución realista (B frente a A):** la diferencia entre ejecución literal y realista es pequeña
  (≤ 0,1 pp en U1). El veredicto no depende de esa elección.

## Limitaciones
- U1 son componentes actuales del S&P 500 / Nasdaq 100, con sesgo de supervivencia.
- U2 es una lista elegida a mano.
- Los *stops* se evalúan al cierre; no son órdenes intradía (§3 del preregistro).
- U1 tiene 517 valores con datos, no los 514 que dice el preregistro. Es la misma lista
  (`macd_combo_filters_v1/sectors.json`, 518 entradas, una sin datos); el 514 del texto era un error de recuento.

## Reproducibilidad (condición previa, §4)
Se cumplió antes del contraste:
- **Lógica:** la regla de producción reproduce el registro (187 de 187 y 352 de 352).
- **Koncorde:** el de producción coincide con la reconstrucción en 300 de 300 casos.
- **Flow, RSI y MACD:** coinciden entre el 96 y el 100 % con dato limpio.
- **Diferencias explicadas:** todas vienen del retraso del dato en vivo antes del 2026-11-10.

**Hallazgo en producción, sin corregir:** 17 de las 255 posiciones de `SCREENER_SHADOW` entran con un cierre anterior
a la captura de la señal, y otras 46 el mismo día de la captura.

## Ficheros
- `features.py` / `prep_compact.py`: entradas y candidatos sin mirar al futuro. `prep_compact.py` procesa valor a
  valor por falta de memoria y reproduce `features.py` (idéntico en U2).
- `repro.py`, `diag_repro.py`, `repro_clean.py`, `_konc_window_test.py`, `_input_parity.py`, `parity.py`:
  reproducibilidad.
- `study.py`: contraste. `--selftest` compara el simulador A con `screener_shadow_portfolio.simulate()`: 3.000 de
  3.000 casos iguales.
- `results.json`: todas las cifras.
- `_work/`: intermedios, regenerables y fuera de git.
