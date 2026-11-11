# Preregistro — confluencia sectorial: régimen + Flujos & Rotación + flow change de RFL (v1, borrador)

**FIRMADO el 2026-11-11 por el usuario («dale» a las cuatro condiciones de §8). Congelado desde ese momento.** No se ha calculado ninguna rentabilidad futura. El diagnóstico de §2 solo cuenta
condiciones con datos hasta cada fecha de decisión. Alcance: investigación en `research/sector_confluence_v1/`. No se
toca el Market Tracker, el pipeline ni ninguna cartera.

## 0. Pregunta
La intuición del usuario: un sector es oportunidad cuando coinciden tres cosas:
- el régimen o momento de ciclo lo favorece;
- Flujos & Rotación da señal de compra sobre su ETF;
- el flow change de Relative Flow Lab (RFL) es positivo.

La matriz de coherencia de RFL (Fase 5a) ya muestra esa coincidencia, pero nunca se ha medido contra rentabilidades.

Se prueban dos versiones que solo se diferencian en la pata rápida:
- **A (aceleración):** las patas lenta y media coinciden **y** el flow change es positivo.
- **B (retroceso):** las patas lenta y media coinciden **y** el flow change es negativo, es decir, un retroceso
  corto dentro de una tendencia confirmada.

B se incluye porque lo más repetido en el proyecto es la reversión a corto plazo:
- las caídas fuertes del flow change rebotan a 21 sesiones;
- la fuerza relativa a 3 meses positiva rinde peor a 1-4 semanas;
- el filtro Top 3 Flow In/Out acierta al revés a 1 semana.

Lo que ya se sabe:
- rot_score sobre ETFs con 20 años de datos no ordena el rendimiento futuro;
- el score de RFL frente al alfa tiene una correlación de prácticamente cero;
- la pata RFL de la matriz sale invertida a 1 semana.

## 1. Datos
| Pieza | Fuente | Estado |
|---|---|---|
| rot_score, régimen, fit y señal semanales, modo A, 2005-2026 | `backtest/data/processed/rotation_history.parquet` | Existe. Hay que recalcular el régimen con desfase de publicación (§3) |
| MacroScore y sus componentes | `backtest/data/processed/macro_history.parquet`, `macro_weekly.parquet` | Existe |
| Precios diarios de los 11 ETFs SPDR y SPY | `backtest/data/processed/prices_daily.parquet` | Llega hasta el 2026-04-19. Hay que actualizarlo hasta el 2026-11 con Yahoo (12 símbolos) |

Universo: los 11 ETFs sectoriales SPDR (XLK, XLC, XLY, XLF, XLI, XLB, XLE, XLV, XLRE, XLP, XLU). XLC entra desde
2018-06 y XLRE desde 2015-10. No se usan QQQ, IWM, materias primas ni BTC: el estudio es de rotación sectorial.

## 2. Diagnóstico de viabilidad (hecho, sin rentabilidades)
Con el régimen tal como está guardado (aún sin el desfase de §3), en fechas semanales:

| | Fechas | Lenta (L) | Media (F) | L y F | A | B |
|---|---|---|---|---|---|---|
| Desarrollo 2006-2015 | 521 | 837 | 867 | 589 | 303 | 286 |
| Prueba 2016-2026 | 568 | 952 | 1 105 | 685 | 348 | 337 |

Las cifras son pares sector-semana. Un sector suele seguir cumpliendo varias semanas seguidas, así que el número de
eventos independientes es mucho menor (§5).

Correlaciones de Spearman en las fechas de decisión:
- flow change frente al alfa a 3 meses: 0,01;
- flow change frente a rot_score: 0,02;
- alfa a 3 meses frente a rot_score: 0,66.

Lectura: la pata rápida sí aporta información distinta, pero las patas lenta y media repiten en buena parte lo mismo
(momentum relativo).

## 3. Definiciones (fijadas antes de ver rentabilidades)
**Fecha de decisión:** el último día bursátil de cada semana (t). Se usan solo datos hasta el cierre de t.

**Desfase de publicación (obligatorio):** se recalcula el MacroScore y el régimen con histéresis usando para cada
serie solo lo publicado en t:
- WALCL, WTREGEN y RRP: dato de la semana anterior;
- CFNAI: el último mes publicado (unas 3-4 semanas después del cierre del mes);
- series de mercado (VIX, curva, HY, breakeven): dato de t.

No hay histórico de revisiones de CFNAI: se usa el último valor revisado y se declara como limitación. También se
recalculan `fit` y la señal de Flujos & Rotación con ese régimen. El régimen guardado sin desfase solo se usa como
sensibilidad.

**Patas:**
- **L (lenta: régimen y ciclo).** El sector está entre los líderes efectivos del régimen (`fit=True`) **y** su alfa
  de ciclo es positivo: 0,7 × retorno a 63 sesiones del ratio ETF/SPY + 0,3 × retorno a 21 sesiones. Es la misma
  fórmula que el Cycle Tracker, aplicada al propio ETF, como en la matriz de RFL.
- **F (media: Flujos & Rotación).** Señal ACUMULAR, ACUMULAR* o COMPRA (modo A).
- **Flow change (rápida).** Retorno a 5 sesiones del ratio ETF/SPY menos el de las 5 sesiones anteriores, en puntos.
  Es exactamente el de `shared/relative-lib.js`.

**Señales:**
- **A:** L y F y flow change > 0.
- **B:** L y F y flow change < 0.

**Entrada y salida:** compra a la apertura de t+1 y venta al cierre de t+H. **H = 20 sesiones** (primario); 5, 10 y 40
son secundarios.

**Objetivo:** retorno del ETF menos la media equiponderada de los sectores disponibles en la misma ventana. Mide si el
sector elegido bate a los demás, no al mercado en general. Coste: 0,1 % por operación (ida y vuelta).

**Estadístico por fecha:** media del objetivo neto de los sectores que cumplen la señal esa semana. Las fechas sin
ninguno no entran. Resumen: media sobre las fechas, con t de Newey-West de retardo 4 (las ventanas de 20 sesiones se
solapan cuatro semanas).

## 4. Referencias (mismas fechas, mismo número de sectores)
En cada fecha en la que la señal elige k sectores:
1. **L y F sin condición de flow change.** Mide lo que añade la pata rápida.
2. **Top-k por fuerza relativa a 63 sesiones.** El momentum simple.
3. **k sectores al azar** entre los disponibles (1 000 repeticiones, semilla fija).
4. **Media de todos los sectores.** Exceso 0 por construcción.

Además, **B − A** en las fechas en que existen ambas. Es el contraste directo entre aceleración y retroceso.

## 5. Muestras y potencia
- **Desarrollo:** 2006-01-01 → 2015-12-31. Sin parámetros que estimar: solo sirve para comprobar el signo.
- **Prueba:** 2016-01-01 → última fecha con 40 sesiones de futuro disponibles. Se ejecuta una sola vez.
- **No hay datos realmente nuevos.** El usuario ya ha visto los resultados de rot_score, de RFL y de la reversión de
  2016-2026, y la hipótesis B se ha formulado sabiéndolos. Un resultado favorable en la prueba vale menos que en un
  estudio ciego. Solo el seguimiento en vivo daría evidencia limpia.
- **Potencia:** en la prueba habrá unas 250-300 fechas con alguna señal, pero solo unas 70 ventanas de 20 sesiones no
  solapadas. Con una desviación típica del exceso de sector de unos 3-4 puntos a 20 sesiones, el error de la media
  ronda 0,4-0,5 puntos. **Solo se detectarán con fiabilidad efectos de 1 punto o más.**

## 6. Clasificación
**Efecto mínimo de interés (EMI):** +0,5 puntos netos por evento a 20 sesiones. Hay dos hipótesis (A y B), así que
se aplica Bonferroni con intervalos del 97,5 %.

**VALIDADO** (para A o para B, en la prueba, a 20 sesiones), si se cumple todo:
1. exceso medio neto ≥ EMI, con el límite inferior del IC 97,5 % > 0;
2. mejor que las referencias 1 y 2 (diferencia > 0 con t ≥ 2) y que el azar (por encima del percentil 97,5);
3. mismo signo en desarrollo;
4. sigue siendo positivo sin el 1 % de mejores eventos;
5. positivo en al menos 3 de los 4 subperiodos de la prueba (2016-2018, 2019-2020, 2021-2023, 2024-2026);
6. datos no solapados (una semana de cada cuatro, las 4 rejillas posibles): media > 0 en las 4.

**NO SOPORTADO:** el límite superior del IC 97,5 % queda por debajo del EMI.

**INCONCLUYENTE:** el resto. No se presenta como refutación y tampoco se promueve.

**Lectura B − A:** se informa siempre como descriptivo. Si A sale NO SOPORTADO y B VALIDADO, la conclusión es que la
confluencia funciona como contexto para comprar retrocesos, no aceleraciones.

**Sensibilidades (se informan todas, ninguna decide):**
- régimen guardado sin desfase;
- horizontes de 5, 10 y 40 sesiones;
- coste del 0,2 %;
- régimen de mercado (SPY por encima o por debajo de su SMA200);
- eventos independientes: primera semana en que el sector cumple tras ≥ 4 semanas sin cumplir.

No se probarán otros umbrales del flow change, otras definiciones de las patas ni otros universos con estos datos.

**Alcance de un VALIDADO:** pasaría a seguimiento en vivo (una cartera sombra con preregistro propio), no a producción.

## 7. Fuera de alcance
- Las fases del Cycle Tracker calculadas con su cesto completo de acciones: no hay histórico de esos cestos.
- Acciones individuales.
- Otros mercados.
- Cualquier cambio en el Market Tracker, el pipeline o las carteras.

## 8. Pendiente antes de firmar
1. Autorizar la actualización de `prices_daily` hasta el 2026-11 (Yahoo, 12 símbolos).
2. Confirmar el desfase de publicación de §3. Exige recalcular el MacroScore con `backtest/src/macro/`. Si eso no
   reproduce el régimen guardado cuando el desfase es cero, el estudio no arranca hasta encontrar la diferencia.
3. Aceptar la limitación de §5 (sin datos nuevos de verdad; solo se detectan efectos ≥ 1 punto).
4. Firmar. Desde ese momento quedan congelados definiciones, horizontes, umbrales y criterios, y la huella SHA-256 de
   este documento se guarda en `research/sector_confluence_v1/PREREGISTRO.sha256` antes de calcular nada.

## 9. Firma
- Firmado el 2026-11-11. La huella SHA-256 del documento, calculada sin esta sección 9, está en
  `research/sector_confluence_v1/PREREGISTRO.sha256`. Se guardó antes de calcular ninguna variable del estudio.
