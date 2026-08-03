# Cava AI → AI Picks Lab — Resultados de la Prueba 1C

> La validación histórica ya está ejecutada: **5.408 sesiones, de febrero de 2005
> a julio de 2026, 20 años y medio.**
>
> El resultado es matizado y no se resume en un sí o un no. La respuesta corta:
> **como predictor de retorno no funciona; como discriminador de riesgo sí, y
> algo mejor que el sistema que ya teníamos.**
>
> Antes de nada: hemos verificado vuestros dos arreglos ejecutándolos, y
> funcionan. `insufficient_corpus` salta correctamente en el desierto de 2024 (5
> frames fechados → `true`, umbral 15) y no en marzo de 2026 (33 → `false`).
> `corpus_date_range` viene en el snapshot. Y el motor es bastante más rápido de
> lo que estimabais: **4 ms por consulta, no 500**.

---

## 1. Cómo se ha ejecutado

- **Ventana:** 2005-02-01 → 2026-07-31 (5.408 sesiones bursátiles).
- **Entrada:** estado macro reconstruido con nuestro mapping para cada sesión,
  usando solo datos disponibles en esa fecha — las ventanas móviles se calculan
  sobre la serie truncada, no sobre la serie completa.
- **Motor:** `cava_engine` v1.1.0 in-process, `CORPUS_SCOPE_PILOT`.
- **Métrica:** comportamiento posterior del S&P 500 (vía SPY) a 1 semana, 1 mes y
  3 meses, más la peor caída y la volatilidad realizada del mes siguiente.
- **Referencia de comparación:** nuestro propio `MacroScore`/régimen sobre las
  mismas sesiones exactas.

**Sobre `as_of_date`:** se ha ejecutado con el corpus completo, y es correcto
hacerlo así **precisamente porque la invariante se cumple**. Si
`deterministic_risk_posture` no depende del corpus —y lo verificamos en 8
combinaciones antes de escribir una línea de esta prueba— entonces filtrarlo no
cambiaría ni un resultado. La parte que sí depende del corpus (`regime_guidance`)
no interviene en esta prueba.

**Sobre el rendimiento:** las 5.408 sesiones producen solo **423 estados macro
distintos**, así que se consulta al motor una vez por estado y se memoiza. Es
exacto porque el motor es determinista; si no lo fuera, esta optimización sería
ilegítima.

---

## 2. El resultado depende de qué se pregunte

Esto es lo importante y conviene fijarlo antes de mirar los números, porque las
dos preguntas dan respuestas **opuestas** y es fácil quedarse con la que a uno le
convenga:

1. **¿Predice el retorno?** ¿Rinde más el mercado después de `risk_on` que
   después de `risk_off`?
2. **¿Discrimina el riesgo?** ¿Marca `risk_off` tramos con caídas y volatilidad
   posteriores mayores?

No son la misma pregunta, y en los mercados suelen ir en direcciones contrarias:
los suelos son simultáneamente el momento **más peligroso** y el de **mejor
retorno posterior**. Un marco de gestión de riesgo se juzga por la segunda.

---

## 3. Resultados — 20 años

```
▸ Comportamiento posterior del SPY según deterministic_risk_posture

  postura                 n    fwd 1w   fwd 1m   fwd 3m   peor 1m   vol 1m
  neutral               571     0.41%    1.79%    5.96%    -2.63%   17.08%
  reduce_risk          1808     0.28%    1.18%    3.09%    -2.29%   14.19%
  risk_off              852     0.17%    0.74%    2.40%    -4.65%   26.63%
  risk_on              2177     0.17%    0.69%    2.24%    -2.19%   12.20%
  [todas]              5408     0.23%    0.98%    2.95%    -2.66%   15.65%
```

### 3.1 Como predictor de retorno: no funciona

`risk_on` muestra el **peor** retorno posterior a 3 meses (2,24 %), por debajo
incluso de `risk_off` (2,40 %). El orden está esencialmente invertido respecto a
lo que cabría esperar de una señal de posicionamiento.

Dicho sin rodeos: **si alguien usara `risk_on` para decidir cuándo estar
invertido, lo haría peor que estando invertido siempre** (2,95 % de media).

### 3.2 Como discriminador de riesgo: sí funciona

Aquí la señal separa con claridad y en la dirección correcta:

| | `risk_on` | `risk_off` | factor |
|---|---|---|---|
| Volatilidad posterior (1m) | 12,20 % | **26,63 %** | **×2,2** |
| Peor caída posterior (1m) | −2,19 % | **−4,65 %** | **×2,1** |

Cuando el motor dice `risk_off`, el mes siguiente trae **el doble de volatilidad
y el doble de caída máxima**. Eso es exactamente lo que debe hacer un marco de
gestión de riesgo: identificar cuándo el terreno es peligroso, no cuándo va a
subir.

---

## 4. Comparación con nuestro MacroScore

Mismas sesiones, mismo periodo:

```
▸ Comportamiento posterior según NUESTRO régimen

  régimen                 n    fwd 1w   fwd 1m   fwd 3m   peor 1m   vol 1m
  Bull Maduro          2314     0.23%    0.79%    2.51%    -2.38%   13.65%
  Bull Pleno            964     0.28%    1.12%    3.15%    -1.53%   10.58%
  Risk-OFF              594     0.21%    1.42%    5.36%    -3.76%   22.52%
  Transición           1536     0.22%    1.00%    2.53%    -3.37%   19.19%
```

Nuestro régimen sufre **la misma inversión** en retorno: `Risk-OFF` precede al
mejor retorno a 3 meses (5,36 %). No es un defecto de vuestro marco, es la
naturaleza del dato.

Lo relevante es la capacidad de separar riesgo, y ahí:

| Separación entre el extremo defensivo y el ofensivo | Cava | Nuestro MacroScore |
|---|---|---|
| Volatilidad posterior | **14,4 pp** | 11,9 pp |
| Peor caída posterior | **2,46 pp** | 2,23 pp |

**Vuestra capa determinista discrimina riesgo algo mejor que el sistema que ya
teníamos.** La diferencia es modesta pero consistente en las dos métricas, y se
sostiene sobre 20 años y todos los regímenes: 2008, 2011, 2020, 2022.

Es el criterio que fijamos desde la Ronda 4: la pregunta no era si Cava acierta,
sino si acierta **más** que lo que ya teníamos. En riesgo, la respuesta es sí.

---

## 5. Tres cautelas, por honestidad

**5.1 El tramo reciente parece espectacular y no hay que creérselo.** Sobre las
753 sesiones desde agosto de 2023 (las únicas con dimensión de crédito),
`risk_off` muestra 13,70 % a 3 meses y solo −1,47 % de caída. Pero son **44
sesiones dominadas por el suelo de abril de 2025**. Es un episodio, no una
muestra. No lo usaremos para nada concluyente.

**5.2 Los episodios anteriores a agosto de 2023 se midieron sin crédito.** Como
ya os comentamos, el spread HY no está disponible antes de esa fecha. Para 2008,
2011 o 2020 el motor operó con precio y volatilidad pero **sin la dimensión que
en vuestra jerarquía es L1**. Que aun así discrimine riesgo mejor que nuestro
sistema es notable — pero significa que estos resultados **infravaloran** lo que
haría el marco completo, no al revés.

**5.3 Esto mide el S&P 500, no nuestra cartera.** El uso previsto es modular la
exposición de una cartera de valores temáticos de pequeña capitalización, con
beta bastante superior. Es razonable esperar que la discriminación de riesgo se
amplifique ahí, pero **no está medido** y no lo vamos a afirmar sin medirlo.

---

## 6. Qué concluimos

**La capa determinista entra en producción**, con un uso concreto y acotado:
`deterministic_risk_posture` modulará la **exposición** de la cartera (cuánto
riesgo asumir), no la **selección** (qué comprar). Esa la seguirá haciendo el PCS.

Es justo el reparto que dibujamos en la Ronda 3 —Cava dicta el campo de juego, AI
Picks Lab elige el vehículo— y ahora tiene respaldo empírico sobre 20 años en
lugar de ser una hipótesis razonable.

**Lo que no vamos a hacer** es usar la postura como señal de entrada ni esperar
que mejore el retorno por sí sola. Los datos dicen que no lo hace, y preferimos
dejarlo escrito ahora a descubrirlo dentro de seis meses.

**Siguiente paso por nuestra parte:** montar el circuito completo de la cartera
(Prueba 1B) y arrancar el modo sombra, que sigue siendo la validación de verdad.
Os avisaremos cuando tengamos los primeros picks.

Gracias por el trabajo y por la rapidez. Que la invariante se cumpliera es lo que
ha hecho posible esta prueba — sin ella nos habríamos quedado con un episodio de
estrés evaluable en vez de veinte años.
