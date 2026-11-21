# Flow negativo — etapa 2: resultados de la prueba confirmatoria

> **Nota de cierre (2026-11-21):** las cifras de este documento no cambian. Al cerrar se encontró que la preparación
> había omitido el embargo de la enmienda 1 §9. Con él, el veredicto sigue igual: ver `INFORME_CIERRE.md` §8.2.

2026-11-21, LAWNMOWER. Una sola ejecución válida, con la congelación de preparación v5 (`093cb385…`).
- Resultados: `data/etapa2_resultados.json` (`d512b1b5…`).
- Registro de accesos: `data/etapa2_acceso.jsonl`.
- Filas de prueba: 2 030 679 (`work/etapa2_test_rows.parquet`, `c07cef34…`).

Los tres intentos anteriores murieron por falta de memoria sin escribir ni mostrar ninguna cifra. Cada uno está anotado
en `ETAPA2_PREPARACION.md` §8 quater: las correcciones no cambian ningún cálculo y se comprobaron byte a byte con el
ensayo de desarrollo. Tras abrir la prueba no se ha cambiado ningún criterio.

## Veredicto

**NO SOPORTADO.** Ninguno de los 5 contrastes confirma (nivel 0,01 por contraste, intervalos al 99 %).
- Las dos celdas elegidas en desarrollo (+2,0 y +2,1 pp) salen **ligeramente negativas** en la prueba.
- H1 no se cumple en ninguna talla: ni el Flow negativo ordena el exceso dentro de cada celda de rentabilidad reciente,
  ni mejora la predicción de M0.
- El hallazgo de desarrollo no se reproduce fuera de muestra.

## 1. Los 5 contrastes

| # | Contraste | Resultado en la prueba | IC 99 % | Veredicto |
|---|---|---|---|---|
| 1 | H1 grandes (n 268 974, 69 meses) | D −0,13 pp; ΔIC −0,0027 | D −0,53 a +0,21; ΔIC −0,011 a +0,006 | no confirmado |
| 2 | H1 medianas (n 318 704, 69 meses) | D −0,23 pp; ΔIC +0,0021 | D −0,60 a +0,11; ΔIC −0,002 a +0,006 | no confirmado |
| 3 | H1 pequeñas (n 152 481, 45 meses) | D −0,28 pp; ΔIC +0,0033 | D −0,70 a +0,13; ΔIC −0,002 a +0,009 | no confirmado |
| 4 | Principal: grandes / ep < −30 / 20 ses. / todos | exceso −0,11 pp (t −0,22) | −1,38 a +1,20 | no confirmado |
| 5 | Anidada: la misma, solo lateral | exceso −0,16 pp (t −0,29) | −1,09 a +0,69 | no confirmado |

Detalle de las celdas:
- Celda 4: 1 851 episodios, 542 empresas, 578 días, 241 semanas. En desarrollo: 805 episodios, +2,11 pp, t 2,57.
- Celda 5: 354 episodios, 227 empresas, 126 días, 65 semanas. En desarrollo: 147 episodios, +1,97 pp, t 2,58.
- Las dos fallan las tres condiciones de §7: signo distinto al de desarrollo, |exceso| < 0,5 pp e intervalo con el 0.
- Lectura de §8 en ambas: **«descripción de la caída»**. Ninguna es reversión ni continuación bajista.
- Desenlaces desconocidos: 0 % en las dos celdas. Las cotas terminales coinciden con el principal (−0,10/−0,11 y
  −0,15/−0,16), igual que las sensibilidades de saltos.
- Micro y «sin capitalización» (solo descriptivas): D +0,19 pp y −0,20 pp. El intervalo de micro es enorme
  (−8,9 a +12,3 pp), por valores extremos.

## 2. Atribución de la celda lateral: original y estricta

Diferencia frente a días sin la señal de la misma talla, mes y celda de quintiles w1 × m1.

| Comparación | Emparejados | Diferencia | t NW | IC 99 % |
|---|---|---|---|---|
| Original, §8.3 (referencia de cualquier régimen; la que cuenta) | 354 / 354 | −0,90 pp | −1,82 | −1,74 a +0,01 |
| **Estricta** (referencia también lateral, ≥ 10 comparadores) | 339 / 354 (96 %), 116 días | −0,74 pp | −0,95 | −2,06 a +0,60 |
| Estricta sin mínimo de comparadores (sensibilidad) | 354 / 354 | −1,13 pp | −2,22 | −2,07 a −0,12 |

- Las tres apuntan al mismo lado: la señal rinde **peor**, no mejor, que días comparables sin ella.
- Ninguna de las dos versiones principales excluye el 0. Solo lo excluye la sensibilidad sin mínimo, que no decide nada.
- En la celda principal, la atribución original da −0,59 pp (IC −1,59 a +0,38).
- La señal hace nuevos mínimos de 20 sesiones en el 78-83 % de los casos, frente al 44 % de la referencia. Su percentil
  10 a 20 sesiones es −12,6/−13,1 %, frente a −9,4 %.

## 3. Rentabilidad absoluta y operabilidad (complementario, no decide)

Grandes, horizonte de 20 sesiones, entrada a la apertura de t+1, coste del 0,2 % ida y vuelta. Todos los grandes son
operables, así que la población B es idéntica a la A.

| | Principal (todos) | Lateral |
|---|---|---|
| Episodios | 1 851 | 354 |
| Absoluta bruta: media / mediana | +3,09 % / +2,78 % | +1,35 % / +1,00 % |
| Absoluta bruta: media diaria (IC 99 %) | +1,03 % (−0,61 a +2,69) | +1,02 % (+0,07 a +1,91) |
| Absoluta neta: media / media diaria | +2,89 % / +0,83 % | +1,15 % / +0,82 % |
| Exceso frente a la talla, bruto: media / media diaria | +0,81 / −0,11 pp | +0,22 / −0,16 pp |
| Exceso neto: media diaria | −0,31 pp | −0,36 pp |
| Frente al SPY (media) | +0,51 pp | +0,10 pp |
| Episodios positivos: absoluto bruto / neto | 59,8 % / 59,2 % | 52,8 % / 52,0 % |
| Episodios positivos: exceso bruto / neto | 52,2 % / 51,3 % | 51,7 % / 51,1 % |
| Excursión adversa máxima: media / mediana | −8,6 % / −6,4 % | −8,5 % / −6,9 % |
| Excursión adversa: p10 / ≤ −10 % / ≤ −20 % | −19,3 % / 33 % / 9 % | −18,1 % / 34 % / 8 % |
| Excursión favorable: media / mediana | +12,0 % / +9,7 % | +11,5 % / +9,4 % |

- Lo positivo es la rentabilidad absoluta, y casi todo es la subida general de las grandes en 2021-2026: frente a su
  talla, el exceso diario es ≈ 0 o negativo, y el acierto ronda el 51-52 %.
  - La media por episodio (+3,1 %) es mayor que la diaria (+1,0 %): la primera da más peso a los días con muchos
    episodios a la vez. La decisión preregistrada usa la media diaria para que esos días no dominen.
- Un exceso relativo positivo no demostraría por sí solo una reversión alcista rentable. Aquí ni siquiera hay exceso
  relativo.
- **Recorrido:** un tercio de los episodios llega a ir un 10 % en contra antes de las 20 sesiones, y casi uno de cada
  diez, un 20 %.

## 4. Periodo común limpio (desde el 2-mar-2023) y otros subperiodos

Ninguno decide nada.

| | Antes del 2-mar-2023 | **Desde el 2-mar-2023** | Sin el solape del propio desarrollo |
|---|---|---|---|
| H1 grandes: D / ΔIC | −0,21 pp / +0,0008 | **−0,08 pp (−0,51 a +0,33) / −0,0048 (−0,014 a +0,004)** | −0,09 pp / −0,0021 |
| H1 medianas: D / ΔIC | −0,43 pp / +0,0022 | **−0,11 pp (−0,42 a +0,24) / +0,0019 (−0,004 a +0,007)** | −0,14 pp / +0,0022 |
| Celda principal | −0,46 pp (n 702, 189 días) | **+0,06 pp (n 1 149, 389 días; IC −1,87 a +1,91)** | −0,13 pp |
| Celda lateral | −0,49 pp (n 51, 26 días) * | **−0,07 pp (n 303, 100 días; IC −1,45 a +1,29)** | −0,16 pp |
| Absoluta bruta diaria, celda principal | — | +1,15 % (IC −0,81 a +3,14) | — |
| Absoluta bruta diaria, celda lateral | — | +1,45 % (IC −0,37 a +3,25) | — |

\* Con 26 días y bloques de 60, el bootstrap no tiene variación y el intervalo sale de anchura cero. No es informativo.

- Ningún veredicto cambia de un subperiodo a otro: todo ≈ 0 y no confirmado.
- En el periodo común limpio, el exceso de la celda principal es prácticamente cero (+0,06 pp).

## 5. Sensibilidades

Todas salen «no confirmado», salvo una excepción en H1:
- Población B, celdas diarias, talla retrospectiva, cotas terminales, plazos de 5/10/40 sesiones y sin solape.
- **Excepción:** H1 pequeñas a 40 sesiones da ΔIC +0,0061 (IC +0,0009 a +0,011) con D ≈ 0, es decir, «evidencia
  parcial». Es una de unas 30 sensibilidades de H1, en un plazo que no es el preregistrado, y no decide nada.
- Celdas, otros plazos:
  - principal: 5 ses. −0,19 pp; 10 ses. +0,07; 40 ses. +0,05;
  - lateral: 5 ses. +0,16; 10 ses. **+0,96 pp (IC +0,21 a +1,63)**; 40 ses. +0,70.
  - El +0,96 a 10 sesiones es un plazo no seleccionado, con 126 días y sin corrección propia. No decide nada, y a 20 y
    40 sesiones desaparece.
- Entrada al cierre de t+1: −0,07 pp en la principal y −0,15 en la lateral.
- Costes ×2 y ×3 (exceso neto): −0,51/−0,71 pp en la principal y −0,56/−0,76 en la lateral.

## 6. Qué significa

- El Flow negativo no aporta información sobre el exceso futuro más allá de la rentabilidad reciente, en ninguna talla.
- Las celdas de episodio < −30 que parecían rebotar en 2018-2020 no rebotan frente a su talla en 2021-2026.
- Lo que queda es la descripción: tras un hundimiento del Flow, la acción suele marcar nuevos mínimos y tiene una cola
  izquierda más pesada que días comparables. Sube en términos absolutos lo que sube el mercado.
- No se cambia nada en producción. Para volver a estudiar el Flow negativo haría falta un preregistro nuevo; no se debe
  reinterpretar esta prueba.
