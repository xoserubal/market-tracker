# Microestructura v1 — Protocolo de G2A (congelado antes de calcular, 2026-11-16)

**Qué es.** Las reglas con las que la exploración en desarrollo (2017-2021) rellenará los parámetros abiertos del
[preregistro G2](PREREGISTRO_G2.md). Se congela con su SHA-256 (`G2A_PROTOCOLO.sha256`) **antes** de calcular ninguna
variable candidata ni ningún resultado. Lo que la exploración no pueda resolver con estas reglas vuelve a ti; no se
decide sobre la marcha.

**Base.** Aprobaste el marco del preregistro G2 (§1-§12) el 2026-11-16 con 8 condiciones. Este documento las aplica.
Diferencias con el marco aprobado, todas por tus condiciones:
- H-B1 pasa a exploratoria y la corrección es Bonferroni ×3 (§1).
- Las ventanas de B1 se reducen a 30 + 10 sesiones (§5).
- La regla de elección exige estabilidad, un control de selección y un desempate por parsimonia (§4).

**Prueba cerrada.** Ninguna función de este protocolo calcula resultados con fecha de decisión posterior al
2021-10-29; el código lo comprueba y se detiene si ocurre (§9).

## 1. Hipótesis confirmatorias: 3, Bonferroni ×3

| Hipótesis | Estado | Motivo |
|---|---|---|
| H-C1 | Confirmatoria | Prioridad estratégica (acumulaciones silenciosas en valores laterales); potencia se comprueba en §6 |
| H-C2 | Confirmatoria | Ídem; si la potencia no alcanza, se aplica la regla de §6 |
| H-A1 | Confirmatoria | Universo completo; potencia suficiente (abajo) |
| H-B1 | **Exploratoria** | Potencia insuficiente, decidido antes de calcular nada (abajo) |

**H-B1, por qué exploratoria (decidido con datos de diseño, no con resultados).**
- Muestra de prueba: 100 bloques × 60 sesiones elegibles = 600 observaciones no solapadas a 10 sesiones, como máximo.
- El IC mínimo detectable con α = 0,05/3 bilateral y potencia del 80 % es (2,39 + 0,84)/√600 ≈ **0,13**, sin contar la
  dependencia dentro de cada bloque (con ella es mayor).
- H-B1 mide la información que los ticks añaden sobre la misma magnitud calculada con barras de 1 minuto. Las dos miden
  la misma distribución del volumen por precio y estarán muy correlacionadas, así que un IC incremental realista está
  muy por debajo de 0,05. Con 0,13 de mínimo detectable, un resultado negativo no informaría de nada.
- Queda exploratoria: se calcula, se informa y no entra en la corrección.

**H-A1, potencia.** ~118 fechas no solapadas a 10 sesiones en la prueba × ~480 valores. Con una desviación del IC
diario de ~0,10 (se mide en desarrollo), el error del IC medio es ~0,009 y el mínimo detectable ≈ 3,23 × 0,009 ≈
0,03, igual al mínimo de interés (§7). El cálculo se repite con la desviación medida en desarrollo y se informa.

**Nivel.** Cada hipótesis confirmatoria se contrasta con p < 0,05/m bilateral y el signo previsto, donde m es el
número final de confirmatorias (3, o 2 si se aplica la regla de §6).

## 2. Datos y ajustes

**Fuentes por magnitud.**

| Magnitud | Fuente |
|---|---|
| Apertura, máximo, mínimo, cierre, volumen y VWAP diarios | Barras diarias SIP sin ajustar (`reference/daily_ohlc_v2`) |
| Volumen por precio, VWAP intradía, eficiencia del recorrido | Barras de 1 minuto del nivel A, solo sesión regular 9:30-16:00 ET |
| Ticks (exploratorio) | Piloto B1 v2 |
| Sector | GICS de la instantánea anual de Wikipedia vigente en t (la misma reconstrucción que `sector_breadth_v1`) |
| Benchmarks | SPY y los 11 ETF sectoriales SPDR, barras diarias SIP + sus dividendos |

**Splits (sin información futura).** Para las variables con fecha t, los precios y volúmenes de cada día d ≤ t se
ajustan con los splits de ex_date en (d, t]: precio ÷ factor, volumen × factor. Solo entran splits con ex_date ≤ t.
- Cualquier salto diario mayor de ×2 o ÷2 sin un split que lo explique invalida las observaciones cuya ventana de
  variables o de resultado lo contenga.
- Ese invalidar se cuenta y se informa; no se corrige a mano.

**Rentabilidad de resultado.** De la apertura de t+1 al cierre de t+h:

    R = (C_{t+h} · S + D) / O_{t+1} − 1

- S = producto de los factores de split con ex_date en (t+1, t+h].
- D = suma de dividendos en efectivo con ex_date en (t+1, t+h], expresados en acciones de t+1. No se reinvierten.
- La misma fórmula se aplica al SPY y a los ETF sectoriales.

**Salidas de cotización dentro del horizonte.** Se clasifican con las acciones corporativas de Alpaca:

| Tipo | Liquidación |
|---|---|
| Fusión en efectivo | Precio de la operación; el resto del horizonte rinde 0 |
| Fusión en acciones | Se sigue al comprador con el ratio de canje |
| Fusión mixta | Efectivo + acciones del comprador |
| Quiebra o baja sin valor | −30 % desde el último cierre (sensibilidad 0 % y −100 %) |
| Sin acción corporativa identificable | Último cierre, rentabilidad 0 después. Se marca y se informa el número; sensibilidad −30 % |

El tipo se fija con datos posteriores a t por necesidad: es el resultado, no una variable.

**Observaciones censuradas.**
- **Fin de los datos:** ninguna. Desarrollo termina en 2021-10-29 y su horizonte cae en el embargo; la prueba termina
  en 2026-09-14 y su horizonte llega a 2026-11-09, antes del final de los datos (2026-11-13).
- **Faltan barras:** si faltan barras diarias necesarias para el resultado sin que haya salida, la observación se
  excluye y se cuenta. Si supera el 1 % de una población, se informa antes de seguir.

**Historia mínima.** Una observación con fecha t necesita, sin huecos de identidad:
- 252 sesiones diarias previas;
- 140 sesiones de barras de 1 minuto previas.

No se usan ventanas parciales.

## 3. Variables (fórmulas definitivas; parámetros abiertos: L, k, θ en C; w y variante en A)

Notación:
- `pct_N(x_d)` = percentil de x_d entre sus N valores previos del mismo valor, de d−N a d−1 (0-1).
- ATR = ATR de Wilder de 14 sesiones con máximo, mínimo y cierre diarios ajustados.

**Por sesión d:**
- `RV_d = V_d / mediana(V_{d−120..d−1})`.
- `DESP_d` (desplazamiento), en dos variantes:
  - diaria: `|ln(C_d / C_{d−1})| / mediana(|ln(C/C₋₁)|)_{d−120..d−1}`;
  - intradía: `ER_d / mediana(ER)_{d−120..d−1}`, con `ER_d = |c_último − o_primero| / Σ_minutos |c_m − c_{m−1}|`, la
    eficiencia del recorrido en la sesión regular.
- `AWD_d = ln RV_d − ln(DESP_d + 0,05)`: actividad sin desplazamiento. El 0,05 evita el logaritmo de 0 en días sin
  movimiento.
- **Sesión anómala:** `pct_120(AWD_d) ≥ θ`.

**Volumen por precio (1 minuto).**
- Cada minuto asigna su volumen a su VWAP.
- Rejilla fija por valor en logaritmo del precio ajustado, con celdas de 0,25 %.
- Sobre una ventana de W sesiones:
  - `POC` = precio de la celda con más volumen;
  - `VA70` = celdas mínimas alrededor del POC (ampliando hacia el lado con más volumen) que suman el 70 %;
  - `VAW_W` = anchura de VA70 / (máximo − mínimo de la ventana).

**Familia C.** Ventana de lateralidad = L sesiones.

**Población elegible en t:** las cinco condiciones, todas con datos ≤ t.
1. Miembro del S&P 500 en t.
2. `RANGO_L = (max C − min C)_{t−L+1..t} / ATR_t ≤ k`.
3. Fuerza relativa a 63 sesiones frente al SPY ≤ 0.
4. Ningún cierre de las últimas 20 sesiones es máximo de 252 sesiones.
5. Flow Score < 4 y Early Flow < 7, reconstruidos con `shared/flow-score.js` como en `macd_combo_filters_v1`.

**Componentes de la anomalía**, cada uno expresado como su percentil frente a sus 120 valores previos del mismo valor:
1. `C1 = 1 − VAW_L` (volumen concentrado dentro del rango).
2. `C2 = media de pct_120(AWD_d)` en d = t−9..t, variante diaria.
3. `C3 = fracción de sesiones anómalas` en t−19..t.
4. `C4 = posición del POC_10 en el rango − posición del POC_L en el rango`, con posición = (POC − mín)/(máx − mín) del
   rango de L sesiones. Positivo = la concentración migra hacia arriba.

**Índice:** `AI_t = (pct(C1) + pct(C2) + pct(C3) + pct(C4)) / 4`, con igual peso, fijado.

**Grupo «con anomalía»:** AI_t ≥ el percentil 66,7 de AI en la población elegible de desarrollo (umbral fijo,
calculado sin resultados).

**Episodios.**
- Racha máxima de fechas elegibles de un valor, permitiendo huecos de hasta 5 sesiones.
- Evento tratado: primera fecha del episodio en que AI entra en el grupo con anomalía. Una observación por episodio.
- Duración de la lateralidad en t: sesiones consecutivas elegibles hasta t.

**Controles de H-C1/H-C2.**
- Candidatos: misma fecha t, elegibles, AI en el tercio inferior de la población de desarrollo, mismo tercil de
  liquidez (mediana de V·VWAP de las 60 sesiones previas, terciles transversales del día).
- Si hay candidatos del mismo sector, solo esos; si no, cualquier sector y se marca.
- Se eligen hasta 3 por distancia de Mahalanobis en (RANGO_L, duración, ln liquidez).
- Se informa el porcentaje de tratados con sector relajado y con menos de 3 controles. Los tratados sin control no
  entran y se cuentan.

**H-C1.**

    Δ = media sobre episodios de [Ex_tratado − media(Ex_controles)]

- Ex = R − R_SPY − costes, a 40 sesiones.
- Secundario: 20 sesiones.

**H-C2.**
- Ruptura = algún cierre de t+1..t+40 por encima del máximo de cierres del rango de L sesiones en t, sin volver dentro
  del rango en las 5 sesiones siguientes.
- Efecto = P(ruptura | tratado) − media de P(ruptura | controles).

**Familia A** (universo completo de miembros del S&P 500 con historia mínima).
- Variable: `A_t = media de pct_120(AWD_d)` en d = t−w+1..t, variante diaria o intradía.
- Variable incremental: residuo de la regresión transversal (por fecha, sobre rangos) de A_t frente a:
  - momentum 5 y 20;
  - fuerza relativa a 63 frente al SPY y a su ETF sectorial;
  - RV_t;
  - (C_t − SMA20)/ATR.
- **H-A1:** IC de Spearman por fecha entre el residuo y Ex a 10 sesiones. Media de Fama-MacBeth en fechas no solapadas
  (cada 10 sesiones desde la primera fecha del periodo; los otros 9 desfases se informan). Dirección prevista: positiva.

**Familia B (exploratoria).** Las mismas magnitudes con ticks en los días de B1, con las ventanas de §5.

## 4. Rejillas y regla de elección (solo desarrollo)

**Rejillas, cerradas.**

| Familia | Parámetros | Combinaciones |
|---|---|---|
| C | L ∈ {40, 120} · k ∈ {q20, q35, q50} · θ ∈ {0,80; 0,90} | 12 |
| A | w ∈ {1, 5, 10} · variante ∈ {diaria, intradía} | 6 |

Los tres k son los percentiles 20, 35 y 50 de RANGO_L, uno por cada L. Se calculan sobre todas las observaciones
valor-día de desarrollo que cumplen las condiciones 1, 3, 4 y 5 de la población, sin mirar resultados.

**Estadístico por año.** Para cada combinación y año de desarrollo y (2017-2021):
- C: Δ_y a 40 sesiones;
- A: IC medio del año.

**Puertas.** Todas deben cumplirse; si una combinación falla una, queda fuera.
1. **Muestra:** C ≥ 20 episodios tratados por año; A ≥ 20 fechas no solapadas por año.
2. **Estabilidad:** el signo previsto en ≥ 4 de los 5 años y en las dos mitades (2017-2019 y 2020-2021).
3. **No es un pico aislado:** al menos la mitad de sus vecinas en la rejilla (las que cambian un solo parámetro) tienen
   el mismo signo en desarrollo agrupado.
4. **Control de la selección (reality check):**
   - Se permutan los valores de la variable entre los valores elegibles de la misma fecha, 200 veces.
   - En cada permutación se recalcula el criterio de todas las combinaciones de la familia y se guarda el máximo.
   - La combinación elegida debe superar el percentil 95 de esos máximos (p de selección ≤ 0,05).
   - Esto descuenta haber probado 12 (o 6) variantes.

**Criterio.** Mediana de los estadísticos anuales, robusta a un año extremo.

**Desempate por parsimonia (regla del 1-ES).**
- ES = error estándar del estimador agrupado de desarrollo de la mejor combinación, con errores agrupados por mes.
- Entre las que pasan las puertas, son candidatas las que tienen criterio ≥ el mejor − 1 ES.
- Entre las candidatas se elige por este orden fijo, de menos a más selectiva:
  - C: k mayor → θ menor → L mayor;
  - A: w mayor → diaria antes que intradía.
- Motivo: la regla menos selectiva usa más observaciones y tiene menos grados de libertad implícitos.

**Si ninguna combinación pasa las puertas,** la hipótesis no va a la prueba. Queda como resultado negativo de
desarrollo y se te informa; no se relajan las puertas.

**Informe.** Se publican las 12 y las 6 combinaciones con sus estadísticos anuales, el resultado de cada puerta y el
reality check, no solo la elegida.

## 5. Ventanas de B1 (resuelve la discrepancia de historia previa)

- Cada bloque B1 tiene 40 sesiones de historia de ticks antes de la primera fecha elegible.
- Con la normalización de 120 sesiones y la persistencia de 20 del nivel A, una variable de ticks necesitaría 140
  sesiones de historia. Incluso con 40 de normalización + 20 de persistencia harían falta 60.
- **Solución, fijada antes de calcular y sin cambiar el muestreo:** en B1 las variables de ticks usan normalización de
  30 sesiones y persistencia de 10. 30 + 10 = 40 = la historia disponible, así que la primera fecha elegible ya tiene
  la ventana completa.
- Para comparar ticks frente a barras (H-B1, exploratoria), la versión con barras de 1 minuto se recalcula sobre los
  mismos días y con las mismas ventanas 30 + 10. Las variables del nivel A siguen con 120 + 20.
- No se usan datos de fuera del bloque ni se alarga ningún bloque.

## 6. Potencia de C y número final de hipótesis (antes de congelar el preregistro)

**Proyección de la muestra de prueba.**
- Con la combinación elegida se cuentan los episodios tratados de desarrollo por año.
- Se proyectan a la prueba: episodios/año × 4,7 años, menos la proporción de exclusiones.
- No se calcula nada sobre la prueba.

**Mínimo detectable de H-C1.** `MDE = (z_{α/2} + 0,84) · sd_Δ / √n_proyectado`.
- sd_Δ = desviación de las diferencias por episodio en desarrollo.
- α = 0,05/3.
- Se aplica un factor de 1,25 por la dependencia entre episodios del mismo periodo.

**Regla.**

| MDE | Decisión |
|---|---|
| ≤ 0,5 pp | H-C1 y H-C2 confirmatorias (m = 3) |
| 0,5-1,0 pp | Solo H-C1 confirmatoria; H-C2 exploratoria (m = 2) |
| > 1,0 pp | Se te consulta antes de congelar: la prueba no podría detectar el efecto mínimo útil |

**H-C2** usa el mismo n. Su efecto mínimo es +5 puntos porcentuales de probabilidad de ruptura.

## 7. Costes y efectos mínimos

**Costes de ida y vuelta.**
- 0,2 % en general;
- 0,5 % en el tercil de liquidez más bajo;
- 0,02 % en el SPY y los ETF sectoriales;
- sensibilidad con todo ×2.

Se aplican igual a la estrategia y a cada benchmark: tratados, controles, carteras de referencia y SPY pagan según su
propio tercil. En H-C1 tratados y controles comparten tercil, así que en Δ los costes se compensan: Δ neto = Δ bruto.
Por eso se añade la condición de utilidad (abajo).

**Efectos mínimos útiles.**

| Contraste | Mínimo | Justificación |
|---|---|---|
| H-C1, 40 sesiones | +0,5 pp por operación | 2,5 × el coste general. ~6,3 operaciones no solapadas/año → ~+3 pp/año de exceso. Por debajo, el coste ×2 (0,4 %) y el deslizamiento se comen casi todo |
| H-C1, 20 sesiones (secundario) | +0,25 pp | El mismo exceso anual (12,6 operaciones/año × 0,25). Informativo, no decide |
| H-C2 | +5 pp de probabilidad | En una base del ~20-30 % de rupturas es un aumento relativo de ~20 %; menos no cambia la decisión de vigilar un valor |
| H-A1, 10 sesiones | IC ≥ 0,03 | Umbral de equilibrio de una cartera solo comprada en el quintil superior: exceso esperado ≈ 1,40 · IC · σ₁₀ ≈ 0,25 pp con σ₁₀ ≈ 6 %, frente a 0,2 % de coste. Por debajo no paga su rotación |

Para H-A1, σ₁₀ (dispersión transversal de Ex a 10 sesiones) se mide en desarrollo. El mínimo final es el mayor entre
0,03 y el equilibrio recalculado (coste ÷ (1,40 · σ₁₀)).

**Condición de utilidad,** solo para pasar a la captura en sombra, no para el veredicto: la hipótesis es SOPORTADA y
además el exceso neto frente al SPY del grupo tratado (C) o del quintil superior (A) es > 0 con t ≥ 2 en la prueba.

## 8. Muestra de desarrollo completa y representativa (antes de elegir)

No se elige ninguna combinación hasta comprobar en desarrollo:
1. **Nivel A completo:** unidades del plan de 2016-2021 en estado `ok`/`empty` = 100 %. Fallidas = 0.
2. **Cobertura** de valor-días miembro con barras de 1 minuto en sesión regular ≥ 98 % por año, y ≥ 95 % por sector y
   por tercil de liquidez.
3. **Empresas que salieron del índice:** cobertura ≥ 95 %. Se informa su peso en la población elegible.
4. **Integridad de referencia:**
   - barras diarias coincidentes con G1;
   - saltos sin split explicados o marcados;
   - salidas clasificadas, con el número de «sin acción identificable».
5. **Barras diarias completas** en los bloques B1 (incluido CZR) y en todos los horizontes de desarrollo.

Si alguna no se cumple, se informa y se te consulta. La exploración descriptiva puede empezar antes (poblaciones,
distribuciones de variables, potencia), pero **no** el cálculo de los criterios de elección.

## 9. Separación de resultados y protecciones

- **Resultados de la exploración:** van en un documento aparte, `G2A_RESULTADOS_DESARROLLO.md`. El preregistro
  definitivo solo contiene fórmulas, parámetros congelados, n efectivo, potencia, reglas y criterios, y remite a ese
  documento.
- **Protección en el código:** las funciones de resultado rechazan fechas de decisión > 2021-10-29 salvo con el modo
  confirmatorio. Ese modo exige que exista el preregistro definitivo congelado y que su hash coincida. No se ejecutará
  sin tu aprobación.
- **Exclusiones:** las de prueba están fijadas en `test_exclusion_audit.csv`: 628 valor-sesiones únicas de 51 valores,
  todas por resultado posterior visto. La sensibilidad de mercado de la criba de G1.5 es aparte.
- **Variables de agresor y delta:** siguen siendo exploratorias, con las variantes de G2_CAMBIOS §2.
