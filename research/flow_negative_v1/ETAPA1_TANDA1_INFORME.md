# Etapa 1, tanda 1 — Flow negativo, desarrollo 2018-2020 (2026-11-20)

Preregistro firmado: `wiki/PREREGISTRO_FLOW_NEGATIVO_V3.md`. Código: `s4_etapa1.py --tanda 1`. Agregados:
`data/etapa1_tanda1_tables.json` (tablas y cruces) y `data/etapa1_tanda1_selection.json` (candidatas, elección,
M0/M1). Congelación (desbloquea la tanda 2): `data/etapa1_tanda1_frozen.json`.

Solo señales de 2018-01-02 a 2020-12-31, de todas las tallas: 832 884 días utilizables, 311 135 con Flow < 0.
Ningún día de prueba (los resultados a 40 sesiones de las señales de diciembre de 2020 llegan a marzo de 2021).
Es caracterización en desarrollo: nada de esto es un veredicto ni una regla operativa.

## 1. Celda elegida para la etapa 2

De 72 candidatas (grandes, medianas y «sin capitalización» × umbral −10/−20/−30 × plazo 20/40 × régimen), **una**
cumple todos los criterios del §5:

| Talla | Episodio | Plazo | Régimen | n | Semanas | Exceso medio diario | t (NW) | Mitades | Desconocido |
|---|---|---|---|---|---|---|---|---|---|
| Grande | Flow < −30 | 20 | todos | 739 | 96 | **+2,05 pp** | 2,70 | +1,37 / +2,89 | 0 % |

- Intervalo bootstrap 95 % (bloques de 60): +0,90 a +3,36 pp; con bloques de 20 y 120 tampoco incluye el 0.
- Igual con las cotas terminales (+2,10 / +2,04) y en la población B (+2,05, t 2,7).
- Cautela: de 72 candidatas se esperaría 1-2 con |t| ≥ 2,5 por azar. Por eso pasa a la prueba (2021-2026) una sola
  vez con Bonferroni: H1 en 3 tallas + esta celda + las que elija la tanda 2 (como mucho 7 contrastes, nivel
  ≥ 0,05/7).
- Rozaron el corte y no entraron: «sin capitalización» −20/40/bajista (t 2,78, solo 23 semanas) y grande −20/40/bajista
  (t 2,51, 29 semanas). Todas las cercanas son grandes caídas en el bajista de 2020: una sola crisis.
- Quedan 3 plazas para pequeñas y micro en la tanda 2.

## 2. M0/M1 congelados (grandes y medianas)

Efecto del tercio de R (resto del Flow) sobre el exceso a 20 sesiones, descontada la celda 5 × 5 de retornos:

| Talla | n | R bajo | R medio | R alto |
|---|---|---|---|---|
| Grande | 91 605 | +0,29 pp | −0,07 | −0,14 |
| Mediana | 112 370 | −0,01 | −0,14 | +0,13 |

Diferencias pequeñas y de signo opuesto entre tallas. Es lo que se contrastará en H1 con los datos de prueba.

## 3. Lectura descriptiva (población A, exceso frente a la talla a 20 sesiones, pp)

| Talla | Z0 [−5,0) | Z2 [−15,−10) | Z4 [−30,−20) | Z5 < −30 | ep −10 | ep −20 | ep −30 |
|---|---|---|---|---|---|---|---|
| Grande | −0,03 | +0,22 | +0,72 | +1,52 | −0,10 | +0,89 | **+2,05** |
| Mediana | −0,14 | +0,17 | +0,52 | +2,27 | +0,07 | +0,31 | −0,67 |
| Pequeña* | −0,46 | −0,14 | +0,86 | −1,33 | +0,55 | +0,16 | +0,42 |
| Micro* | −3,40 | −3,25 | −2,51 | −2,97 | −7,62 | −3,35 | −3,01 |
| Sin capitalización | −0,24 | −0,25 | +1,77 | +3,19 | −0,17 | +0,97 | +2,05 |

\* Sin los días con evento corporativo en el plazo (ver §4).

- En grandes, el exceso crece con la profundidad del Flow (de ≈0 a +1,5/+2 pp): patrón de rebote en caídas extremas.
- En micro todo es negativo, pero con intervalos anchísimos (n 250-4 000, la mitad no operable).
- Cuanto más bajo el Flow, más «nuevos mínimos» después (56 % en Z0 → 90 % en episodios −30 en grandes) y peor
  percentil 10 (−8,7 % → −19,8 %): aunque la media rebote, la cola izquierda empeora.
- Flow ≥ 0 queda algo por debajo de la media de su talla en todas (−0,26 a −0,59 pp).

## 4. Problema de datos encontrado (afecta a la tanda 2)

Dos contrasplits de 2020 no aplicados en la serie (CHK 1:200 en abril; HPR 1:50 en octubre, marcados
`E2_split_incoherente`) dan retornos de +21 600 % y +7 680 % a 20 sesiones. Hay 1 171 días con evento en el plazo
(0,14 %), todos en pequeñas y micro con precio < 3 $ (fuera de la población B).
- No afectan a la elección de esta tanda: el máximo retorno a 20 sesiones es 0,85 en grandes, 1,78 en medianas y 2,23
  en «sin capitalización».
- Sí contaminan las tablas A de pequeñas y micro: por ejemplo, micro Z5 da +38 pp con los errores y −3,0 pp sin ellos.
  La media de la talla de esos días también queda contaminada, así que el exceso de las demás pequeñas/micro de esos
  días también.
- El preregistro dice que un evento en (t, t+40] «se marca y se trata en el resultado», pero no fija cómo. **Decisión
  pendiente antes de la tanda 2:** propongo tratar como resultado desconocido los días cuyo plazo contiene un split
  incoherente o un salto sin explicar (fuera de la media de talla y del exceso), y publicar la versión con ellos aparte.

## 5. Decisiones de implementación (no fijadas literalmente en el preregistro)

- Ruta de precios: la misma clave por fecha que el panel v4; antes de 2018, la primera clave del panel.
- Percentil propio: ≥ 120 días con Flow completo en las 252 sesiones; si no, sin dato.
- Liquidez (quintiles) y rotación (tercios) dentro de talla y día.
- Elección de celdas con población A, exceso frente a la talla y episodios.
- Exceso de la población B frente a la media de toda la talla (población A).
- «Cambio de ticker» sin sucesor enlazado en el panel = valor desconocido (cotas 0 y último cierre).
