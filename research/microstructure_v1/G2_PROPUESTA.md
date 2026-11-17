# Microestructura v1 — Propuesta para G2 (borrador, sin aprobar)

**No es un preregistro.** Es la propuesta de qué preregistrar. Las fórmulas exactas, los parámetros, la dirección
del efecto y los umbrales se fijan en el preregistro de G2, después de la exploración en el periodo de desarrollo
y antes de abrir la prueba. Nada de lo que hay aquí se ha calculado sobre datos futuros.

## 1. Principios heredados del proyecto (no negociables)

- **Referencia principal = factores convencionales**, no Flow Score: momentum 5 y 20 sesiones, fuerza relativa frente
  al mercado y al sector, volumen relativo, extensión respecto a la SMA20 en ATR y azar emparejado. Lo que se mide
  es la información **incremental** sobre esos factores. Ojo: a 5-20 sesiones la fuerza relativa a 3 meses ya tiene
  un efecto propio de reversión (−0,4/−0,6 pp; `research/extension_sma20_atr_v1`, `research/early_flow7_validation_v1`).
- **Ejecución**: la señal se conoce tras el cierre más el retraso de datos y el cálculo. Se compra a la apertura de
  la sesión siguiente. Costes: 0,2 % ida y vuelta para el S&P 500 y 0,5 % para el tercil menos líquido (a fijar).
- **Inferencia por fecha**: IC transversal por fecha (Fama-MacBeth), errores con Newey-West hasta el horizonte, y
  observaciones no solapadas en la prueba principal. El n efectivo se declara aparte del n nominal.
- **Partición propuesta (fechas de decisión):** desarrollo 2017-01-03 → 2021-10-29; embargo de 40 sesiones;
  prueba 2022-01-03 → 2026-09-14. Después de 2026-11, la captura prospectiva queda como confirmación independiente.
- **Familia de contrastes pequeña**: 4 hipótesis principales en total y Bonferroni ×4. Todo lo demás es exploratorio.
- Un resultado negativo bien contrastado se publica y cierra la hipótesis.

## 2. Familias e hipótesis principales (4)

### Familia A — Barras de 1 minuto sobre el universo completo (S&P 500 a fecha + EE. UU. del proyecto)

**H-A1.** Un índice intradía de **actividad sin desplazamiento** aporta información incremental sobre la referencia
a 10 sesiones (secundario: 5). El índice combina volumen relativo frente a amplitud del rango intradía, posición del
cierre en el rango del día y desviación del cierre respecto al VWAP, siempre frente a la propia historia del valor.
Dirección prevista: **positiva** cuando el volumen anómalo no mueve el precio a la baja (absorción).
- Contraste: IC incremental (residuo frente a la referencia), Fama-MacBeth, prueba 2022-2026, 10 sesiones.

### Familia B — Ticks sobre la muestra B1 (200 bloques × 100 sesiones, congelada)

**H-B1.** Variables que **solo existen en ticks** añaden información sobre las mismas variables calculadas con
barras de 1 minuto. Candidatas: cambio en la cuota de volumen fuera de mercado (código `D`), desequilibrio de
compra y venta por la regla del tick ponderado por volumen, y cambio en la distribución de tamaños de los lotes
redondos (excluidos los odd lots).
- Potencia: con unas 1 200 observaciones no solapadas a 10 sesiones, el IC mínimo detectable es ≈ 0,08 con una
  sola prueba y ≈ 0,10 con Bonferroni ×4 (80 % de potencia). Es grande para este tipo de señal. **Si G2 no puede
  justificar un efecto de ese tamaño, H-B1 debe declararse exploratoria** y la ampliación de B1 se decide después.

### Familia C — Acumulaciones silenciosas (prioridad estratégica, sin privilegio metodológico)

Población elegible en cada fecha de decisión (solo con información hasta esa fecha):
- **lateral**: rango de máximo a mínimo de los últimos L cierres ≤ k × ATR o ≤ X %, con L ∈ {40, 120} a fijar;
- **sin momentum**: fuerza relativa a 63 sesiones ≤ 0 frente al SPY, sin máximos de 52 semanas recientes y por
  debajo de cualquier umbral de Flow/Early Flow, para no solapar con lo que ya detecta el sistema.

Variables de anomalía (barras de 1 minuto, nivel A): concentración del volumen por franjas de precio dentro del
rango (aproximada con barras; se declara como aproximación), actividad sin desplazamiento persistente (fracción de
sesiones anómalas en 10 y 20 sesiones), y cambios en el reparto intradía (última hora, subastas).

**H-C1.** Dentro de la población lateral, el tercil superior de anomalía persistente tiene **mayor exceso de
rentabilidad a 40 sesiones** (secundario: 20) que **controles laterales emparejados sin anomalía**. El
emparejamiento usa la misma fecha, sector, tercil de liquidez, anchura del rango y duración de la lateralidad.

**H-C2.** El mismo grupo tiene **mayor probabilidad de ruptura alcista**: cierre por encima del máximo del rango en
las 40 sesiones siguientes, sin volver dentro en las 5 posteriores. Se compara con los mismos controles.

Lo que H-C1/H-C2 **no** permiten concluir: que hubiera compras institucionales. Una ruptura posterior no prueba la
causa. Se informa la asociación, no el mecanismo.

Aspectos que G2 debe resolver antes de congelar:
- **Cuántos episodios laterales independientes hay**: se cuentan por episodio (inicio-fin de la lateralidad), no
  por valor y día. Sin ese número no hay cálculo de potencia, y requiere barras diarias (ya descargadas, sin coste).
- Si el n efectivo de C sale pequeño, **reducir a una sola hipótesis** (H-C1) antes de abrir la prueba.
- La formación de suelos (fenómeno A del encargo) queda **exploratoria** en esta ronda: misma infraestructura,
  población «tras caída ≥ X %», sin contraste confirmatorio hasta tener una hipótesis concreta.

## 3. Horizontes

5/10 sesiones como principales para A y B. 20/40 sesiones como principales para C (las acumulaciones largas no se
evalúan a 5 días). Las cuatro se calculan siempre. La que decide cada hipótesis queda fijada arriba y en el
preregistro.

## 4. Controles contra fugas de información

- Toda variable en t usa datos ≤ t. Las ventanas de lateralidad y de persistencia terminan en t.
- La población elegible, los terciles y los emparejamientos se calculan con datos ≤ t, nunca con el periodo completo.
- No se filtra por «sigue cotizando después». Las salidas por deslistado se registran con su último precio.
- El burn-in de los bloques B1 no aporta observaciones elegibles.
- Identidad: asof = última fecha observada y corte por épocas (ver README §4).
- Los splits se aplican en la capa de variables (los trades se guardan sin ajustar).

## 5. Lo que G2 necesita para empezar (decisiones pendientes)

1. Descarga del nivel A (barras de 1 minuto, unas 160 000 peticiones, 14-20 h, ≤ 36 GB). Es imprescindible para A y C.
2. Descarga del piloto B1 (unas 115 000 peticiones, unas 15 h, unos 11 GB) y de la submuestra de quotes (< 1 h).
3. Fuente de fechas de resultados (o aceptar el análisis por eventos como «desconocido», ver README §9).
4. Aprobar la partición desarrollo/prueba propuesta y los costes de transacción.
