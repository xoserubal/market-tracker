# Amplitud sectorial sobre componentes frente a la tendencia del propio ETF — v1 (2026-11-11)

Preregistro: `wiki/PREREGISTRO_SECTOR_BREADTH_V1.md`, revisión 2, firmado el 2026-11-11. Su SHA-256 se guardó en
`PREREGISTRO.sha256` antes de calcular nada y se comprobó sin cambios al terminar. Una sola ejecución. Sin cambios en
producción ni en el Market Tracker.

## Veredicto preregistrado: **NO SOPORTADO**

En prueba (2023-2026) y a 20 sesiones, la parte de la amplitud que no explica la tendencia del propio ETF tiene una
correlación de rangos media con el exceso futuro del ETF de **−0,025** (t −0,8, 197 fechas). Intervalo de confianza del
95 %: **−0,086 a +0,036**, entero por debajo del efecto mínimo de interés (0,05). Con estos datos se puede afirmar que
no hay un efecto útil en este periodo y estos sectores. No es un caso de falta de potencia.

| Criterio (§6) | Resultado |
|---|---|
| 1. H1 (residuo) > 0, t ≥ 2 | No: −0,025 (t −0,8) |
| 2. H2 (modelo completo mejor que el base) > 0, t ≥ 2 | No: −0,008 (t −0,3) |
| 3. Mismo signo en desarrollo | No: H1 −0,040 (t −1,8); H2 +0,023 (t +1,3) |
| 4. Exclusión de cada sector: H1 > 0 y t ≥ 1,5 en las 11 | No: negativo en 10 de 11 (Inmobiliario +0,001) |
| 5. Sensibilidad temporal | No: retardo 8 → t −0,7 y −0,3; rejillas no solapadas +0,027 / −0,019 / −0,033 / −0,075 |
| 6. 3 primeros − 3 últimos > 0 y en ≥ 3 de 4 años | No: −0,3 pp por ventana; positivo solo en 2024 y 2026 |

**Conclusión:** la evolución de la participación interna de un sector **no aporta información sobre la tendencia de su
ETF**. Es la condición que puso el asesor, y no se cumple. Se descarta como detector temprano en este diseño. No se
probarán otras definiciones sobre estos datos.

## Por qué no aporta: la amplitud repite lo que ya dice el ETF
Correlación de rangos entre el cambio de amplitud (ΔP) y los controles del ETF: con su aceleración ΔRS21 **0,79**, con
su fuerza relativa a 21 sesiones 0,53, con la de 63 sesiones −0,01. Cuando un sector "mejora por dentro", casi siempre
es porque el ETF ya está acelerando. Lo que queda una vez descontado eso no predice nada.

## Detalle

**Muestra.** 209 fechas semanales de desarrollo (2019-2022) y 202 de prueba (2023-2026), todas con ≥ 8 sectores
fiables (media en prueba 9,9). Energía solo es fiable en 132 de 411 fechas y Comunicación en 51 (cobertura de precios
por debajo del 85 %); el resto, siempre. Coeficientes congelados en desarrollo para el residuo:
0,14 × RS21 − 0,08 × RS63 + 0,72 × ΔRS21.

**Otros horizontes (prueba, H1 / H2):** 10 ses. −0,023 / −0,001 · 40 ses. +0,032 (t 1,0) / −0,028 · 60 ses.
−0,005 / +0,009. El +0,032 a 40 sesiones tiene signo contrario en desarrollo (−0,063, t −2,8): ruido.

**Umbral de cobertura del 80 % (sensibilidad):** H1 −0,013 (t −0,4), H2 −0,005. Mismo resultado.

**Referencias a 20 sesiones (IC medio desarrollo / prueba):**
| Señal | Desarrollo | Prueba |
|---|---|---|
| ΔP sin controlar | −0,087 (t −2,4) | +0,018 (t 0,4) |
| Cambio del % sobre SMA50 (secundaria) | −0,085 (t −2,2) | +0,072 (t 1,8) |
| Diferencial equiponderado − ETF (secundaria) | +0,017 | +0,026 |
| RS21 del ETF | −0,079 (t −1,7) | −0,002 |
| RS63 del ETF | −0,022 | −0,058 (t −1,4) |
| ΔRS21 del ETF | −0,058 | +0,032 |
| Azar | −0,046 (t −2,0) | +0,024 (t 1,1) |

Ninguna señal mantiene el signo entre periodos. Que el azar llegue a t −2,0 en desarrollo muestra cuánto ruido hay con
9-11 sectores por fecha: por eso el preregistro exigía t ≥ 2 en prueba **y** el mismo signo en desarrollo **y** las
demás comprobaciones. La medida secundaria del % sobre SMA50 sale +0,072 en prueba, pero −0,085 en desarrollo; no es
evidencia y no se puede promover sin un preregistro nuevo con datos nuevos.

**Lectura económica (3 primeros − 3 últimos por residuo, 0,1 % por cambio):** −0,4 pp por ventana de 20 sesiones en
desarrollo, −0,3 pp en prueba; por año en prueba −0,2 / +0,03 / −1,3 / +0,6 pp; peor con SPY bajo su SMA200 (−1,0 pp).

**Transiciones de liderazgo (descriptivo):** con la definición preregistrada solo hay 8 en 2019-2026, 5 consolidadas
(2 en desarrollo, 3 en prueba). Demasiado pocas para comparar métodos: todos cubren las mismas (50 % y 67 %). Lo único
que se ve es que las señales del ETF (RS21, ΔRS21) señalan sectores que ya habían batido a SPY en ~2-3 pp en las 20
sesiones previas, y el residuo de amplitud no (≈ 0); pero ninguno es seguido de exceso positivo (−0,3 a −0,6 pp a 20
sesiones; el azar, entre 0 y −0,5).

## Calidad de los datos
- Composición reconstruida con instantáneas anuales de Wikipedia + tabla de cambios (§2 del preregistro).
- Precios: miembros actuales (caché) + 113 símbolos que salieron del índice (descargados). Faltan ~130 empresas
  absorbidas o deslistadas sin datos gratuitos; cobertura por sector y año en `data_quality.json`.
- Verificación de identidad: 20 de 113 símbolos no superan la comparación de nombres y se tratan como sin precio. 15 son
  símbolos reutilizados por otra empresa (SE = Sea Ltd, FB = un ETF, STI = Solidion…), 2 no tienen nombre en Yahoo
  (Comerica, Tegna) y 3 son la misma empresa con otro
  nombre (VF Corp por la grafía "V.F.", CONSOL → CNX, Owens-Illinois → O-I Glass): la regla preregistrada los descarta;
  solo restan algo de cobertura.
- Símbolos ambiguos (varios candidatos por CIK): < 2 % de los miembros en todos los sectores.
- Sesgo de supervivencia: los que faltan son sobre todo empresas que salieron del índice. Con más de ellas la amplitud
  sería algo más baja y ruidosa; no hay motivo para pensar que daría información que ahora no aparece, pero el
  resultado vale para 2023-2026 y los sectores fiables, no como afirmación general.
- Potencia: el error de la media resultó ~0,031 (el preregistro estimó ~0,05 de forma conservadora con ventanas no
  solapadas). Por eso el intervalo de confianza permite un NO SOPORTADO y no solo un INCONCLUYENTE.

## Ficheros
`diag_coverage.py` → `coverage_diag.json` (diagnóstico previo) · `build_panel.py` → `_work/panel.parquet`,
`data_quality.json` · `study.py` → `results.json` (todas las cifras). `data/` (Wikipedia, sonda, precios de los que
salieron; ~20 MB) y `_work/` no deberían subirse a git.
