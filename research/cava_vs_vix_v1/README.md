# Cava `risk_off` frente al VIX — SPY 2005-2026 (v1)

Preregistro firmado el 2026-11-11: `wiki/PREREGISTRO_CAVA_VS_VIX_V1.md` (huella en `PREREGISTRO.sha256`). Se ejecutó
una sola vez.
- **Datos y motor:** motor `cava-decision-engine` v1.1.0 (commit `e9a7140`); MacroScore con desfase de publicación;
  5 416 días (2005-02-01 a 2026-08-12).
- **Script:** `run.py` → `results.json`. Las posturas diarias están en `_work/` (no se versiona).

## Resultado: CAVA APORTA (los 4 criterios se cumplen)
- **`risk_off`** está activo el 15,7 % de los días.
- **Regla de VIX con la misma frecuencia:** el VIX está en o por encima del percentil 86 de sus 5 años anteriores
  (15,8 % de los días).
- **Coincidencia entre las dos reglas:** 87,7 % de los días.

Caída máxima del SPY en las 21 sesiones siguientes (MDD21), según qué regla esté activa:

| | Días | MDD21 | Vol. 21d | Retorno 63d |
|---|---|---|---|---|
| Ninguna activa | 4 231 | −2,22 | 12,6 % | +2,81 |
| Solo el VIX | 337 | −3,53 | 25,1 % | +5,94 |
| **Solo Cava** | 332 | **−3,95** | 22,0 % | +2,74 |
| Las dos | 516 | −5,65 | 30,6 % | +2,26 |

- **H1:** cuando el VIX no avisa, Cava añade **−1,73 puntos** de caída (IC 95 % −2,95 a −0,58; 22 episodios separados).
  Es negativo en los tres subperiodos (2005-2012 −1,18, 2013-2019 −1,17, 2020-2026 −1,97).
- **H2:** en los días en que las reglas discrepan, «solo Cava» cae más que «solo VIX» (−0,41), pero con un **IC muy
  ancho (−2,33 a +1,95)**. Cava no es claramente mejor que el VIX cuando discrepan. Lo que sí está claro es que no lo
  repite.

## Sensibilidades
- **Régimen sin desfase:** H1 −1,60.
- **VIX ≥ 25 fijo:** H1 −2,31 (IC −3,48 a −1,03).
- **Solo desde 2023-08** (con crédito, muestra corta): H1 −1,01, con solo 25 días de «solo Cava».
- **Volatilidad a 21 días:** H1 +9,4 puntos (IC 6,7 a 11,9).
- **Retorno a 63 días:** H1 −0,08.

## Lectura
- **Cava detecta riesgo que el VIX no ve.** Lo más probable es que venga del estado del precio y la tendencia del SPY
  (distancia a máximos, SMA200), no de la volatilidad. No se ha comprobado: queda como hipótesis.
- **Reducir riesgo cuando solo avisa Cava sale casi gratis:** el retorno a 3 meses de esos días (+2,74) es igual al de
  los días tranquilos (+2,81).
- **En cambio, cuando solo avisa el VIX, el retorno posterior es mejor (+5,94):** los picos de VIX rebotan, así que
  reducir riesgo ahí cuesta retorno.
- **Para modular la exposición, el orden más razonable es:**
  - `risk_off` de Cava: reducir o no añadir riesgo;
  - VIX alto en solitario: no vender.
- **Límites:**
  - no se compara con una regla simple de tendencia del SPY, que podría explicar lo mismo;
  - antes de 2023-08 no hay crédito;
  - las ventanas de 21 días se solapan (tenido en cuenta con el bootstrap por bloques);
  - los umbrales de `cava_mapping` se diseñaron con conocimiento de este mismo histórico.
