# Preregistro — ¿Cava `risk_off` aporta algo además del VIX y la tendencia del SPY? (v1)

**Escrito y firmado el 2026-11-11** («vale» del usuario a hacer la comparación), antes de calcular nada con las
definiciones nuevas. La huella está en `research/cava_vs_trend_v1/PREREGISTRO.sha256`.

Es una continuación de `wiki/PREREGISTRO_CAVA_VS_VIX_V1.md` (resultado: CAVA APORTA sobre el VIX). Se reutilizan las
mismas posturas diarias, del mismo motor y con el régimen corregido por desfase. También los mismos resultados del mes
siguiente (MDD21, VOL21, R63), la misma muestra (2005-02-01 a 2026-08-12) y la misma regla de VIX V.

## Hipótesis a descartar
Lo que Cava añade sobre el VIX podría venir solo del estado del precio del SPY, algo que una regla simple ya daría.

## Definiciones
- **T (primaria):** el cierre del SPY en t está por debajo de su SMA200 (con datos hasta t).
- **T15 (sensibilidad):** la distancia del SPY a su SMA200 está en el 15,7 % más bajo de la muestra (misma frecuencia
  que Cava). Como en V, el umbral se elige solo para igualar la frecuencia.
- **DD10 (sensibilidad):** el SPY está al menos un 10 % por debajo de su máximo de 252 sesiones.
- **C** = `risk_off` y **V** = la regla de VIX, igual que antes.

## Hipótesis
- **H1 (primaria):** en los días en que ni V ni T avisan, el MDD21 medio es peor con C = 1 que con C = 0.
  - Se mide la diferencia (C = 1 − C = 0) dentro de V = 0 y T = 0.
- **Descriptivo:**
  - la tabla de C frente a «V o T» (activas / inactivas);
  - el porcentaje de días `risk_off` que no cubre ni V ni T;
  - VOL21 y R63 en esas mismas casillas.

## Inferencia
Bootstrap por bloques circulares de 63 sesiones, 5 000 repeticiones, semilla fija. Subperiodos: 2005-2012, 2013-2019
y 2020-2026.

## Clasificación
**Efecto mínimo de interés (EMI):** −1 punto de MDD21.

- **CAVA APORTA MÁS ALLÁ DE VIX Y TENDENCIA**, si se cumple todo:
  1. H1 ≤ −1 y el límite superior del IC 95 % < 0;
  2. H1 negativa en al menos 2 de los 3 subperiodos;
  3. el mismo signo con T15 en lugar de T, con DD10 en lugar de T y con el régimen sin desfase.
- **CAVA NO APORTA MÁS ALLÁ DE VIX Y TENDENCIA:** el límite inferior del IC 95 % de H1 es > −1.
- **INCONCLUYENTE:** el resto, o menos de 3 episodios separados con C = 1, V = 0, T = 0.

No se probarán otras reglas de tendencia.
