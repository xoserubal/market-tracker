# Cava AI → AI Picks Lab — Ronda 2: decisiones técnicas y requisitos nuevos

> **Continuación de `AGENTE_EXTERNO_INTEGRACION.md`.** Vuestras respuestas
> resolvieron todo lo bloqueante del primer cuestionario. Este documento recoge:
> (1) lo que queda cerrado, (2) una decisión de arquitectura que os afecta,
> (3) **tres requisitos nuevos bloqueantes** que surgieron al revisar el plan,
> y (4) lo que arreglamos nosotros de nuestro lado.
>
> El requisito **R1 (`as_of_date`)** es el más importante del documento. Sin él,
> la fase de validación no se puede hacer de forma honesta.

---

## 1. Lo que queda cerrado

| Pregunta | Respuesta | Estado |
|---|---|---|
| B1 Horizonte | Swing (días–semanas) | ✅ Encaja directo |
| B2 Universo | ~128 candidatos con PCS | ✅ Máxima comparabilidad |
| B3 Salidas | Agente decide + red mecánica | ✅ Acordado |
| B6 Dirección | Solo largo | ✅ Sin cambios en la medición |
| C2 Datos que faltan | Nada bloqueante | ✅ Confirmado por nuestra parte |
| A2 Estado | Stateless, AI Picks Lab es fuente de verdad | ✅ Acordado |
| A4 Determinismo | Motor 100% determinista | ✅ **Esto abre posibilidades, ver §3** |

Un apunte sobre **A4**: que el motor de decisión sea determinista y no un LLM
cambia la naturaleza del proyecto a mejor. Nuestro sistema de *quality score*
existe para detectar alucinaciones de modelos generativos; con un árbol
determinista eso deja de aplicar. A cambio, gana algo mucho más valioso:
**se puede validar contra el pasado antes de ponerlo a operar**. De ahí el
requisito R1.

---

## 2. Decisión de arquitectura: in-process, no HTTP

Proponíais exponer el Decision Tree como wrapper HTTP (FastAPI). **Preferimos
evitar HTTP e invocar el árbol como dependencia Python en el mismo proceso**, por
un motivo concreto:

> Nuestro pipeline corre en **GitHub Actions** (infraestructura de GitHub, no una
> máquina nuestra). No puede alcanzar un FastAPI que corra en vuestra red local.
> Con HTTP habría que desplegarlo en un cloud público: coste recurrente,
> autenticación, disponibilidad 24/7 y un punto de fallo más — para algo que
> tarda 500 ms y no necesita estado.

**Ventajas adicionales del in-process:**

- El backtest histórico pasa a ser un bucle sobre una función, no 76 llamadas de red.
- Sin secretos ni credenciales que rotar.
- La versión exacta que produjo cada decisión queda registrada en nuestro
  `requirements.txt`, es decir, en git.

**Lo que necesitamos de vosotros:** que `query_decision_tree_v1.py` + el corpus se
empaqueten como algo instalable con `pip`, con **versiones etiquetadas**
(`v1.1`, `v1.2`…). Puede ser un repo privado de GitHub — `pip install
git+https://github.com/vuestra-org/cava-ai@v1.1` funciona perfectamente con un
token de acceso. No hace falta publicar en PyPI ni abrir el código al público.

**Fijaremos la versión de forma deliberada.** No instalaremos desde la rama
principal. Cuando publiquéis una versión nueva nos avisáis y decidimos cuándo
adoptarla, registrando la fecha del cambio. No es desconfianza: es que si el
agente cambia en mitad de un periodo de medición sin que lo sepamos, los datos de
rendimiento de ese periodo dejan de significar nada. Ya segmentamos rendimiento
por modelo en nuestros registros; haremos lo mismo por versión del agente.

---

## 3. Requisitos nuevos [BLOQUEANTES]

### R1. `as_of_date` — evitar sesgo de anticipación en la validación

**Este es el punto crítico del documento.**

Vuestro paso 3 propuesto ("dry-run con datos históricos") es exactamente lo que
queremos hacer — y lo queremos hacer **primero**, no tercero, porque es lo único
que puede decirnos si el agente aporta valor antes de invertir en el cableado.
Tenemos **76 payloads históricos guardados** (mayo–agosto 2026) con su estructura
completa: candidatos, contexto macro, posiciones abiertas y exposición temática.

**El problema:** si ejecutamos el payload del 15 de mayo contra el corpus de hoy,
el corpus contiene los análisis que Cava publicó en junio y julio — es decir,
**posteriores a la fecha de la decisión**. El agente estaría decidiendo sobre el
15 de mayo con conocimiento del futuro. Los resultados saldrían excelentes y
serían completamente inválidos.

Esto no es una hipótesis teórica: es el error clásico que invalida la mayoría de
backtests mal hechos, y aquí es especialmente fácil de cometer porque el corpus
crece hacia adelante de forma natural.

**Lo que necesitamos:** que el motor acepte un parámetro `as_of_date` que:

1. **Descarte todo DecisionFrame con fecha posterior** a `as_of_date`.
2. **Descarte igualmente los tips** del TipBank posteriores a esa fecha.
3. **Calcule el `recency_bonus` relativo a `as_of_date`**, no a la fecha actual
   (mencionáis ≤30 días = +2, ≤90 días = +1 — esos umbrales deben medirse desde
   `as_of_date`).
4. **Informe en la respuesta qué subconjunto de corpus usó**: número de frames
   considerados y rango de fechas. Esto nos permite *verificar* que el filtro
   funcionó, en vez de confiar en que funcionó.

Vosotros mismos indicáis que el `recency_bonus` ya se calcula sobre las fechas de
los frames, así que la información de fecha ya está — se trata de hacerla
parametrizable.

Sin `as_of_date` la validación histórica no se puede hacer de forma honesta, y sin
validación estaríamos cableando a ciegas.

---

### R2. Separar motor y corpus — tienen ritmos de actualización distintos

Al revisar el empaquetado detectamos algo que conviene decidir explícitamente:

| Componente | Qué es | Cadencia de cambio |
|---|---|---|
| **Motor** | `query_decision_tree_v1.py`, lógica del árbol | Rara (versiones puntuales) |
| **Corpus** | DecisionFrames + TipBank extraídos de los vídeos | **Potencialmente diaria** |

Cava publica análisis a diario. Si congelamos el corpus junto con el motor, en dos
meses el agente estará razonando con la visión de mercado de hace dos meses — deja
de ser el sistema que tiene valor.

**Lo que proponemos:**

- **Motor**: versión fijada, se actualiza de forma deliberada (§2).
- **Corpus**: artefacto **versionado y fechado**, independiente del motor, con un
  camino de actualización más frecuente.

**Preguntas:**

- **R2.a** ¿Con qué frecuencia querríais que actualizásemos el corpus:
  diaria, semanal, o bajo demanda cuando publiquéis un lote?
- **R2.b** ¿Cómo lo distribuís? ¿Un artefacto descargable con fecha (ej.
  `corpus_2026-08-15.json`), un endpoint del que tirar, un repo aparte?
- **R2.c** ¿El corpus es *append-only* (solo se añaden frames nuevos) o se
  reescriben/corrigen frames antiguos? *Si se reescriben, `as_of_date` no basta
  para reproducir una decisión pasada: necesitaríamos también versionar el corpus
  entero, no solo filtrar por fecha.*

---

### R3. Identificadores de versión en cada respuesta

Para poder atribuir rendimiento correctamente, cada respuesta del agente debe
incluir:

```json
{
  "agent_version":  "1.1-patched",
  "corpus_version": "2026-08-15",
  "corpus_as_of":   "2026-08-15",
  "corpus_frames_used": 124,
  "corpus_date_range": ["2025-11-02", "2026-08-15"]
}
```

Los guardaremos en cada pick registrado. Así, si dentro de tres meses el
rendimiento cambia, podremos distinguir "el mercado cambió" de "el agente cambió".

---

## 4. El contrato del mapping — dónde vive el riesgo real

El árbol es determinista, pero **la traducción de nuestro payload a vuestro
vocabulario controlado no lo es**: decidir que `rsi_14: 78` + `extension_risk:
"extreme"` equivale a `price_state: "overextended"` son umbrales que alguien
elige. Ahí es donde se colará el error, no en el árbol.

Tenemos un precedente propio y caro: durante meses arrastramos un indicador
duplicado en JavaScript y Python que divergió en silencio; un criterio que
creíamos activo llevaba tiempo sin puntuar para ningún activo, y nadie lo vio
porque no había una única fuente de verdad ni tests.

**Por eso proponemos que el mapping viva en nuestro repositorio**, como código
revisable y con tests unitarios, en vez de oculto dentro del wrapper. No es
desconfianza en vuestro criterio — es que necesitamos poder auditarlo cuando una
decisión salga rara, y poder testear los casos límite.

**Lo que necesitamos de vosotros para escribirlo:**

- **M1.** La **lista completa de enums** de cada dimensión del vocabulario
  controlado (`price_state`, `trend_state`, `volatility_state`, `credit_state`,
  `sentiment_state`, `narrative_state`, `liquidity_state`): valores posibles y qué
  significa cada uno.
- **M2.** Para cada dimensión, **qué señales usaría Cava** para clasificarla. No
  hacen falta umbrales numéricos exactos si no existen — con la lógica cualitativa
  ("volatilidad alta = VIX por encima de su media de X sesiones y subiendo") nos
  vale para proponer una traducción que luego revisáis.
- **M3.** Los 17 módulos (L1/L2/L3) y **qué estado de mercado activa cada uno**.
- **M4.** Qué ocurre si una dimensión llega vacía o desconocida: ¿hay valor por
  defecto, se desactivan módulos, falla la query?

Nuestra propuesta de flujo: escribimos el mapping, os pasamos **el resultado
sobre datos reales** (ej. "con el payload del 1 de agosto, esto es el estado de
mercado que hemos codificado"), y vosotros confirmáis si refleja lo que Cava
diría. Una o dos iteraciones y queda calibrado.

---

## 5. Lo que arreglamos nosotros

Al revisar vuestra lista de datos necesarios (C1/C4) encontramos tres huecos en
**nuestro** lado. Todos son trabajo nuestro, no vuestro — los listamos para que
sepáis que están contemplados:

1. **`konc_d_blue_z` y `konc_d_blue_accel`**, que marcáis como imprescindibles,
   se calculan pero **no llegaban al payload**. Se añaden.
2. **Datos de posición abierta** (C4): ya enviamos `entry_price` y `entry_date`,
   pero faltan `pnl_pct` y `days_in_position`. Se calculan al vuelo.
3. **`entry_regime`** (el régimen macro en el que se abrió la posición) **no se
   guardaba en ninguna parte**. Empezamos a registrarlo. ⚠️ Las posiciones
   abiertas antes de este cambio lo tendrán a `null` — el agente debe tolerar ese
   caso sin fallar.

Sobre los datos que marcáis como "muy valiosos" (Fear & Greed y sus 7
subcomponentes, monitor de estrés de duración, los ~45 ratios de fuerza relativa,
fase del ciclo): **existen, pero viven en la capa de visualización (JavaScript),
no en el pipeline de Python**. Portarlos es trabajo real, no añadir un campo. Dado
que confirmáis que nada de eso es bloqueante, quedan fuera de la v1 y los
valoramos con datos en la mano una vez el agente esté midiendo.

---

## 6. Plan por fases

| Fase | Contenido | Necesitamos de vosotros |
|---|---|---|
| **1. Validación histórica** | Mapping + backtest sobre 76 payloads reales, contra baselines mecánicas | **R1 (`as_of_date`)**, M1–M4, motor instalable |
| **2. Huecos de datos** | Los 3 puntos de §5 | Nada |
| **3. Operativa** | Script de cartera + step del pipeline + registro de rendimiento desde el primer pick | R2 (corpus), R3 (versiones) |
| **4. Salvaguardas** | Red mecánica de salida + validación de vuestros límites (8–10 posiciones, máx 3 por tema) por nuestro lado | Nada |

**La Fase 1 es la puerta.** Si el agente no bate ahí a una baseline mecánica
simple ("comprar los 3 candidatos de mayor PCS"), preferimos saberlo antes de
construir el resto. Es la misma vara de medir que aplicamos al modelo que ya
tenemos en producción.

Una nota sobre la validación de límites en Fase 4: no es desconfianza en que el
agente respete sus propias reglas, es defensa en profundidad — la misma razón por
la que hay red mecánica de salida aunque el agente decida las salidas.

---

## 7. Sobre el tamaño de posición (B4)

Vuestra tabla de convicción → tamaño (1–8% según `confidence`) nos vale. Un apunte
de medición: **los tamaños variables no son comparables con nuestras baselines**,
que son equiponderadas.

Registraremos **los dos retornos**: equiponderado (comparable con las baselines y
con las otras carteras) y ponderado por tamaño (el rendimiento real de vuestro
método, incluyendo si acertáis dando más peso a las de alta convicción). Es barato
hacerlo desde el principio y evita una discusión irresoluble dentro de tres meses.

De hecho es una hipótesis interesante por sí sola: si el ponderado bate
sistemáticamente al equiponderado, significa que vuestro `confidence` tiene
información real más allá de la selección.

---

## 8. Resumen — lo mínimo para arrancar la Fase 1

1. **R1** — `as_of_date` en el motor (filtrado de frames y tips, `recency_bonus`
   relativo, y reporte del subconjunto usado).
2. **M1–M4** — vocabulario controlado, señales por dimensión, módulos y su
   activación, comportamiento ante datos ausentes.
3. **Motor instalable** con versión etiquetada (repo privado vale).
4. **R2.a/b/c** — decisión sobre cadencia y distribución del corpus, y si es
   *append-only*.

Con eso podemos escribir el mapping y ejecutar la validación histórica. El resto
de fases no depende de nada más por vuestra parte hasta la Fase 3.
