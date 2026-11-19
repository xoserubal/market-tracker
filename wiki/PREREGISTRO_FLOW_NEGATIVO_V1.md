# Preregistro — Flow Score negativo: caracterización y valor incremental (v1)

**Estado: BORRADOR SIN FIRMAR.** No se ha descargado ni calculado nada. Antes de ejecutar hay que resolver los
puntos [DECIDIR] (§9), firmar y congelar con SHA-256, como en los estudios anteriores.
Diagnóstico de datos: `wiki/DIAGNOSTICO_FLOW_NEGATIVO_V1.md`.

## 0. Pregunta y alcance

¿Qué pasa después de cada nivel negativo del Flow Score? Hay tres respuestas posibles para cada nivel y tamaño:
- **Reversión (oportunidad):** rinde por encima del universo después, y no solo por haber caído antes.
- **Continuación (peligro):** rinde por debajo, o con más nuevos mínimos y peor cola izquierda que valores con la
  misma caída previa.
- **Descripción:** ni lo uno ni lo otro, o el efecto se explica por completo con la caída previa del precio.

No se busca una estrategia de compra. No se modifica producción. Ningún umbral se ajusta después de ver
resultados: las franjas, plazos y segmentos de este documento son los únicos que se miden.

## 1. Etapas

| Etapa | Qué hace | Datos que mira | Decide algo |
|---|---|---|---|
| 0 — Construcción | Universos, precios, Flow, capitalización; puertas de calidad | Ningún rendimiento posterior | Solo si los datos valen |
| 1 — Caracterización | Curva completa del Flow negativo y lo que pasa después | **Solo periodo de desarrollo** | Nada; elige como mucho 4 hipótesis para la etapa 2 |
| 2 — Valor incremental | Confirma las hipótesis una sola vez | **Periodo de prueba**, una vez | El veredicto final |

Hacer la caracterización solo en el periodo de desarrollo permite usarla para elegir qué confirmar sin
contaminar la prueba. Tras la etapa 2 se publica también la caracterización del periodo completo, solo como
descripción. [DECIDIR-1]

## 2. Universos

| Universo | Composición en cada fecha | Señales | Desarrollo | Prueba |
|---|---|---|---|---|
| **L** — grandes | S&P 500 | 2016-01-04 → fin | 2016-2020 | 2021 → fin |
| **M** — medianas | S&P 400 | 2016-01-04 → fin | 2016-2020 | 2021 → fin |
| **S** — pequeñas | S&P 600 | 2020-01-02 → fin | 2020-2022 | 2023 → fin |
| **P** — propio | Portfolio Tracker (Flow capturado en vivo) | 2026-08-20 → fin | — | — (solo descriptivo) |

- «Fin» = última fecha de señal con 40 sesiones de datos después; se fija al congelar los datos.
- Un valor cuenta en un universo solo los días en que pertenece al índice (cambios de Wikipedia contrastados
  con instantáneas). Tras salir del índice, sus días ya no generan señales, pero sus precios sí se usan para
  medir el resultado de señales previas.
- Precios: Alpaca, barras diarias SIP, una sola fuente para L, M y S. Identidad por `asof` y épocas
  (`research/microstructure_v1/micro/identity.py`); splits validados contra el precio. Datos fuera del repo.

## 3. Etapa 0 — puertas de calidad (sin mirar resultados)

Se publican todas antes de la etapa 1. Si una falla, se corrige o se para; no se sigue «con lo que hay».

1. **Composición:** coincidencia anual con las instantáneas de Wikipedia ≥ 95 % en cada índice.
2. **Cobertura de precios:** ≥ 95 % de los días-miembro de cada índice y año con precio. Se publica por año,
   motivo de salida (adquisición, quiebra, cambio de índice) y sector.
3. **Paridad del Flow:** Flow con Alpaca frente al mismo cálculo con Yahoo en ≥ 200 valores comunes:
   diferencia absoluta mediana ≤ 0,5 y p90 ≤ 2 puntos.
4. **Paridad con producción:** la réplica Python coincide con `computeFlowScore` (`shared/flow-score.js`) en
   una muestra de ≥ 2 000 filas (diferencia máxima ≤ 0,01).
5. **Capitalización:** cobertura de la SEC por universo y año. Los segmentos de capitalización y rotación solo
   se analizan en los universos-año con cobertura ≥ 80 %; si no, se marcan como no evaluables.
6. **Final de serie:** % de señales cuya serie termina antes del plazo, por motivo.

## 4. Definiciones

### 4.1 Señal y ejecución
- Flow_t calculado con la barra de cierre del día t (réplica de `features.py`, sin datos posteriores).
- Entrada: **apertura de t+1**. Sensibilidad: cierre de t+1.
- Plazos: **5, 10, 20 y 40 sesiones**. Retorno = cierre de t+H / entrada − 1. El plazo principal es 20.
- Si la serie termina antes de t+H (adquisición, quiebra, exclusión): se usa el último cierre disponible y la
  señal queda marcada. Sensibilidad: excluirlas. (Limitación conocida: en quiebras, el último cierre puede
  infravalorar la pérdida.)

### 4.2 Medidas para cada señal
- Retorno; exceso frente al universo (media equiponderada de todos los miembros del mismo universo con la misma
  entrada y plazo); exceso frente a SPY; exceso frente a la mediana de su sector dentro del mismo índice.
- **MFE** = máximo alto entre t+1 y t+H / entrada − 1. **MAE** = mínimo bajo / entrada − 1.
- **Nuevo mínimo** = el mínimo bajo entre t+1 y t+H queda por debajo del mínimo de las 20 sesiones hasta t.
- **Cola:** percentiles 5 y 10 del retorno; P(retorno ≤ −10 %) y P(retorno ≤ −20 %).
- Por cada celda: media, mediana, media recortada al 1 %, % positivo y las medidas anteriores.

### 4.3 Niveles de Flow (fijados ahora)
- **Absolutos:** Z0 [−5, 0) · Z1 [−10, −5) · Z2 [−15, −10) · Z3 [−20, −15) · Z4 [−30, −20) · Z5 < −30.
  Referencias: todos los días, Flow ≥ 0, y [0, 4).
- **Percentil entre valores:** posición del Flow_t frente a los demás miembros del mismo universo ese día:
  ≤ 1 % · (1, 5] · (5, 10] · (10, 25] · (25, 50].
- **Percentil propio:** posición del Flow_t frente a las 252 sesiones anteriores del mismo valor (incluida t);
  mismas franjas; requiere 252 sesiones de historia.

### 4.4 Poblaciones
- **A — Todos los días** en el estado. La inferencia agrupa por fecha (§6) porque los días seguidos del mismo
  hundimiento no son independientes.
- **B — Episodios:** para cada umbral X ∈ {−10, −20, −30}, el primer día con Flow < X tras ≥ 10 sesiones con
  Flow ≥ X. Es la población principal para todo lo que se quiera leer como «señal».

### 4.5 Segmentos
- **Tamaño:** universo (L, M, S); dentro de cada uno, tercios de capitalización en esa fecha
  (precio sin ajustar × acciones de la última presentación a la SEC con fecha ≤ t).
- **Liquidez:** quintiles de la mediana de precio × volumen de las 20 sesiones hasta t, entre los miembros del
  mismo universo ese día.
- **Rotación:** tercios de liquidez / capitalización (si hay cobertura).
- **Régimen** (SPY en t): alcista = cierre ≥ SMA200, cierre ≥ SMA50 y SMA50 ≥ SMA200; bajista = cierre < SMA200;
  lateral = el resto. Igual que el registro de señales de RFL.
- **Tipo de caída** (retornos de 21 sesiones hasta t) [DECIDIR-3]:
  - idiosincrática: valor − mediana de su sector ≤ −10 pp y SPY > −3 %;
  - general: SPY ≤ −5 % o mediana de su sector ≤ −8 %;
  - mixta: el resto.
- **Filtro de iliquidez:** se excluyen señales con precio sin ajustar < 3 $ o liquidez < 1 M$ al día;
  se publica cuántas se excluyen. [DECIDIR-4]

## 5. Etapa 1 — caracterización (solo desarrollo)

- Tablas por universo × nivel (absoluto y percentiles) × plazo, para las poblaciones A y B, con todas las medidas
  de §4.2; y los cruces con liquidez, régimen y tipo de caída.
- Una celda con menos de 100 episodios o menos de 30 semanas distintas se marca «insuficiente» y no se interpreta.
- Gráficos de la curva: exceso, MAE, nuevo mínimo y cola izquierda frente al nivel de Flow, por universo.
- **Elección para la etapa 2** (regla fijada ahora): como mucho 4 celdas
  (universo × umbral de episodio × plazo × régimen o «todos»), con |t| ≥ 2,5, ≥ 100 episodios y el mismo signo en
  las dos mitades del periodo de desarrollo; las de mayor |t|. Si ninguna cumple, la etapa 2 se limita a H1.
- La etapa 1 no produce ninguna regla operativa, aunque algo parezca claro.

## 6. Etapa 2 — valor incremental y confirmación (prueba, una sola vez)

**Separar el Flow de la caída previa.** El Flow es 2 × (0,6 × retorno 1 semana + 0,4 × retorno 1 mes) más un
resto acotado (RSI, MACD, ATR, Koncorde, distancia al máximo). Se llama **R** a ese resto, calculado exactamente
(Flow − parte de momentum). Lo que el Flow pueda añadir sobre la caída del precio está en R.

**H1 — ¿el Flow añade algo a la caída previa?** (en L, M y S por separado)
- En cada fecha se forman celdas por deciles del retorno de 5 sesiones × deciles del de 21 sesiones (dentro del
  universo). Es una comparación no lineal: no supone ninguna forma de la relación.
- Dentro de cada celda, se compara el quintil más bajo de R con el más alto. La diferencia de exceso a 20 sesiones
  se promedia entre celdas, ponderando por número de observaciones.
- Modelo comparativo: M0 = medias de exceso por celda de 5 × 21 sesiones, estimadas en desarrollo; M1 = M0 + efecto
  por quintil de R dentro de la celda, estimado en desarrollo. En prueba: correlación por rangos de cada modelo con
  el exceso real, día a día.
- **Confirmado si**, en prueba: el intervalo de la diferencia de correlación (M1 − M0) queda por encima de 0 **y**
  la diferencia entre quintiles extremos de R es ≥ 0,5 pp a 20 sesiones con el intervalo excluyendo el 0.
- Si no se confirma: lo que muestre la etapa 1 sobre el Flow negativo describe la caída ya producida, nada más.

**H2…H5 — las celdas elegidas en la etapa 1**
- Se confirma una celda si en prueba: mismo signo, |exceso| ≥ 0,5 pp e intervalo sin el 0.
- Y además, para atribuirla al Flow: frente a días sin esa señal en la misma celda de retornos 5 × 21 sesiones, la
  diferencia mantiene el signo con intervalo sin el 0. Si solo se cumple lo primero, se clasifica como «describe
  la caída previa».
- Para llamarla **oportunidad** hace falta además exceso neto > 0 tras coste de ida y vuelta: 0,2 % (L), 0,4 % (M),
  0,8 % (S). [DECIDIR-5]
- Para llamarla **peligro** basta un exceso negativo confirmado, o más nuevos mínimos / peor percentil 10 que los
  días de la misma celda de retornos, con intervalo sin el 0.

**Inferencia:** para cada celda se forma la serie diaria del exceso medio; error estándar de Newey-West con
retardo igual al plazo; además, bootstrap por bloques semanales (2 000 réplicas) como comprobación. Corrección de
Bonferroni sobre H1 (3 universos) + las celdas elegidas.

## 7. Universo propio (P)

Con el Flow tal como se capturó en vivo. Mismas tablas que la etapa 1 (franjas absolutas, episodios, plazos que
hayan madurado), en un apartado separado, sin intervalos de confianza que se lean como prueba. Sirve para ver si
tus valores se parecen a lo que dicen L/M/S, nunca para fijar nada.

## 8. Salidas

- Código y agregados en `research/flow_negative_v1/`. Precios, Flow por valor y día y capitalizaciones, fuera del
  repo (`MICRO_DATA_DIR/flow_negative_v1/`), por licencia de Alpaca.
- Informe: puertas de calidad, caracterización de desarrollo, veredicto de la etapa 2, caracterización completa,
  universo propio y limitaciones (supervivencia restante, pequeñas solo desde 2020, sesgo de calidad del S&P 600
  frente a las small caps en general).

## 9. Puntos a decidir antes de firmar

1. **[DECIDIR-1] Etapa 1 solo en desarrollo** (recomendado) o en todo el periodo con las hipótesis de la etapa 2
   fijadas ya ahora (más datos para describir, pero la etapa 2 queda limitada a H1 + celdas elegidas a ciegas).
2. **[DECIDIR-2] Fuente única Alpaca** (recomendado) o Yahoo con Alpaca solo para las desaparecidas.
3. **[DECIDIR-3] Umbrales del tipo de caída** (−10 pp frente al sector con SPY > −3 %; general si SPY ≤ −5 % o
   sector ≤ −8 %).
4. **[DECIDIR-4] Filtro de iliquidez** (3 $ y 1 M$/día).
5. **[DECIDIR-5] Costes** por tamaño (0,2 / 0,4 / 0,8 % ida y vuelta).
6. **[DECIDIR-6] Mínimo de interés** de 0,5 pp a 20 sesiones (el mismo de estudios anteriores).
