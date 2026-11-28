# Giro de sectores deprimidos v2 — contrastes históricos (bloques A y A′)

Preregistro firmado el 2026-11-28: `wiki/PREREGISTRO_GIRO_SECTORES_REZAGADOS_V2.md` (huellas en `freeze.json`).
Script: `historical.js`, subido antes de ejecutarlo (commit `325f6ed5`) y ejecutado **una sola vez** (`--final`) el
2026-11-28. Resultado completo: `historical_results.json`. Antes se probó con precios simulados (`--placebo`), sin ver
ningún resultado real.

**Estatus:** A es exploratorio y A′ es una generalización. Ninguno confirma nada. El único bloque confirmatorio es el
registro prospectivo C (desde 2026-W48).

## Convenciones de ejecución (interpretaciones del texto, fijadas antes de ejecutar)

- **Resultado completo en el histórico:** la entrada y las 40 sesiones posteriores tienen que caer dentro del bloque
  (≤ 2026-08-28). Así la ventana excluida no entra ni en las señales ni en los resultados. Con eso quedan fuera 1
  evento de sector y 4 de industria.
- **Momentum a 21 sesiones (H2):** retorno propio del ETF, para distinguirlo de la fuerza relativa a 63.
- **Exclusión de un ETF:** se quitan sus eventos; la media del nivel con la que se calcula el exceso no cambia.
- **B1:** las extracciones al azar son de ETFs del mismo nivel evaluables esa semana.
- **B0:** evaluable con al menos 10 semanas con D∧G y D sin G a la vez.

## Resultado

Exceso neto a 40 sesiones frente a la media del nivel. IC 95 % por bootstrap de trimestres (10 000 remuestras).

| Estimando | Eventos | Trimestres | Estimación | IC 95 % | Veredicto | Robustez |
|---|---|---|---|---|---|---|
| **A, 11 sectores** (E_sect) | 147 | 73 | **+0,64 pp** | −0,44 a +1,75 | **INCONCLUYENTE** | NO ROBUSTA |
| **A′, 18 industrias** | 405 | 85 | **−0,44 pp** | −1,14 a +0,26 | **DESFAVORABLE** | NO ROBUSTA |
| **E_amp = 0,5·A + 0,5·A′** | 552 | 95 | **+0,10 pp** | −0,56 a +0,77 | **DESFAVORABLE** | NO ROBUSTA |

- **No sensible a la dependencia temporal:** con bloques de semestre y de año, el veredicto es el mismo en los tres.
  Las ventanas que entran en el trimestre siguiente y se solapan con otro evento son el 20 % (sectores), el 37 %
  (industrias) y el 42 % (juntos).
- **Robustez de A:**
  - con coste triple, +0,44;
  - sin los 5 mejores eventos, −0,06 (no pasa);
  - las 11 exclusiones de un ETF siguen positivas (+0,44 a +0,88).
  - **La media positiva depende de pocos eventos:** XLE en 2020-2022 (+19 a +28 pp), XLF en marzo de 2009 (+25 pp) y
    XLB en dic-2025.
  - Acierto: 53 %. Caída intermedia mediana: −2,7 %; peor caso: −31 %.
- **Robustez de A′:** negativa con coste triple (−0,84, IC −1,54 a −0,15) y en las 18 exclusiones.
  - Sin IBB/IHI/XHS, −0,67.
  - Acierto: 49 %.
- **E_amp, sensibilidades:**
  - regla anterior: −0,32;
  - mismo peso por evento: +0,21;
  - sin IBB/IHI/XHS: −0,02.
- **Horizontes secundarios:**
  - A: +0,52 a 20 sesiones y +0,28 a 60;
  - A′: −0,12 y −0,74;
  - todos con el IC incluyendo el 0.

### Comparadores (informan, no deciden)

| | A, sectores | A′, industrias |
|---|---|---|
| B0: D∧G − D sin G (efectos fijos de semana) | +0,39 (−0,77 a +1,63), 117 semanas | +0,31 (−0,51 a +1,15), 274 semanas |
| B0′: emparejamiento | +0,13 (−1,16 a +1,45), 107 de 147 | +0,19 (−0,76 a +1,13), 361 de 405 |
| B1: percentil frente al azar | 95,5 | 27,8 |
| B2: D∧G − momentum (tercio superior por fuerza relativa 63) | **+1,35 (+0,21 a +2,48)** | −0,20 (−1,11 a +0,71) |
| B3: D∧G − G sin D | +1,39 (−0,54 a +3,72), 57 semanas | −0,63 (−2,42 a +1,27), 132 semanas |

- **B0 no es positivo en ningún nivel.** Una eventual ventaja de los sectores deprimidos que giran **no puede
  atribuirse específicamente al giro**. Esperar a G no aporta frente a estar solo deprimido.
- En los sectores, lo que bate a D∧G es sobre todo el mal resultado del momentum: el tercio con más fuerza relativa
  rinde −0,72 pp esas mismas semanas. Es reversión, no un mérito del giro.

### H2 histórico: solo descriptivo (Cycle simplificado, §7.6)

β de concordancia con la siguiente posición, con controles de profundidad, fuerza relativa, momentum y año:

| Muestra | Concordantes / no | Evaluable | β | IC 95 % |
|---|---|---|---|---|
| Sectores, tabla Cycle | 28 / 102 | no | −2,27 pp | −6,22 a +1,65 |
| Sectores, Cycle + XLRE | 29 / 113 | no | −0,99 pp | −4,95 a +2,89 |
| Industrias A′, tabla del libro | 88 / 317 | sí | +1,53 pp | −0,90 a +4,01 |
| Industrias sin IBB/IHI/XHS | 55 / 291 | sí | +3,05 pp | −0,67 a +6,80 |
| Sectores + industrias, 50/50 | 117 / 430 | sí | +0,77 pp | −1,60 a +3,35 |

- **Sectores:** no hay señal de que el Cycle simplificado ayude, aunque hay pocos concordantes.
- **Industrias:** los concordantes rinden más (+2,2 pp frente a −0,5 en medias brutas), pero el IC incluye el 0 y no
  es confirmación.
- La concordancia casi no se correlaciona con los controles (|r| < 0,1).
- **Ojo:** el H2 confirmatorio usa la Cycle real, no esta versión simplificada.

### Etapas inspiradas en Pring (solo reparto, §8)

| Etapa | Sectores | Industrias |
|---|---|---|
| IV (bonos bajistas, acciones y materias primas alcistas) | 60 | 138 |
| II | 23 | 81 |
| III | 19 | 60 |
| I | 14 | 36 |
| sin etapa | 24 | 60 |
| VI | 5 | 20 |
| V | 2 | 10 |

## Lectura

- **En el histórico no hay ventaja económicamente relevante.** En los sectores la estimación es positiva pero pequeña,
  depende de pocos eventos de energía y finanzas y no se atribuye al giro. En las industrias es negativa.
- **DESFAVORABLE** significa que no hay evidencia de un efecto de +1 pp o más, no que no exista ningún efecto.
- **Nada cambia en el registro prospectivo C:** sigue siendo el único contraste confirmatorio, con las reglas firmadas.
- **Pendiente:**
  - Europa (bloque B, secundario y descriptivo): sin ejecutar. El v2 no fija la lista de los 19 ETFs ni su índice de
    referencia, así que hace falta decidirlo antes de mirar.
