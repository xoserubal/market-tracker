# Cava AI → AI Picks Lab — Ronda 3: reenfoque del rol del agente

> **Continuación de `AGENTE_EXTERNO_RONDA2.md`.** Vuestras respuestas cerraron
> arquitectura, `as_of_date`, corpus append-only y M1–M4. Con esa información en
> la mano hemos hecho una comprobación sobre nuestro universo real que **cambia el
> planteamiento de la integración** — a mejor, y simplificándola.
>
> Este documento es corto: una reformulación del rol del agente y cinco preguntas
> que se derivan de ella.

---

## 1. El hallazgo: nuestro universo y el de Cava casi no se tocan

Hemos cruzado nuestros 128 candidatos actuales con los activos canónicos que
maneja el árbol (SPX, NDX, BTC, GOLD, OIL, VIX, HYG, DXY, UST10Y, NVDA, sectores
SPDR…). El resultado:

```
Solapamiento: 3 de 128 candidatos  (NVDA, QQQ, MSTR)  →  2,3 %
```

Composición real de nuestro universo:

| Bloque | Ejemplos |
|---|---|
| Utilities y financieras argentinas | PAM, CEPU, TGS, SUPV, BBAR, GGAL |
| Petróleo canadiense | CVE, SU, WCP.TO, DPM.TO |
| Mineras de plata y oro | 10 tickers |
| Microcaps del TSX Venture (`.V`) | 9 tickers |
| Cotizadas fuera de EE. UU. | Suecia, Reino Unido, Australia, España, Francia, Nueva Zelanda, Alemania |
| Farmacéuticas y salud grandes | TMO, MRK, LLY, ABBV, UNH, JNJ, VRTX |

*(Nota: el 2,3 % está calculado con una lista aproximada de activos canónicos por
nuestra parte. Ver pregunta **P3** — con vuestro `asset_canonical_map.json` real
podemos dar la cifra exacta, pero el orden de magnitud no va a cambiar.)*

**Consecuencia directa:** Cava no ha hablado nunca de SEDANA.ST, MLX.AX ni III.L,
y nunca lo hará. Los tips a nivel de activo concreto son inaplicables a ~98 % de
nuestro universo. En cambio, el **marco estructural** — cómo leer el régimen, qué
características favorecer o evitar en ese régimen, cuándo cambia el playbook —
aplica al 100 %.

---

## 2. El reenfoque: motor de decisión, no banco de tips

Lo que queremos del agente es **su método de razonamiento, no sus llamadas
concretas sobre activos**.

| | Rol descartado | Rol que queremos |
|---|---|---|
| Pregunta que responde | "¿Qué opina Cava de NVDA?" | "Dado este estado de mercado, ¿qué tipo de activo hay que favorecer y cuál evitar?" |
| Aplicable a | 3 de 128 candidatos | 128 de 128 |
| Se apoya en | TipBank (804 tips, específicos y perecederos) | DecisionFrames + módulos + reglas estructurales |
| Envejece | Rápido | Lento (es metodología) |

En este esquema, el reparto de trabajo queda mucho más limpio:

```
Cava AI   →  lee el régimen y dicta el campo de juego
             (qué favorecer, qué evitar, qué nivel de riesgo tolerar)

AI Picks  →  aplica ese campo de juego a sus 128 candidatos
Lab          usando PCS / rot_score / Koncorde para elegir el vehículo concreto
```

Es exactamente la filosofía que ya rige nuestro sistema (`MacroScore` = permiso de
riesgo → `PCS` = vehículo). El agente entraría a **mejorar la primera capa**, que
es donde creemos que aporta más y donde su conocimiento es genuinamente
transferible.

**Efecto secundario positivo:** buena parte del problema de sesgo de anticipación
de la Ronda 2 se disuelve. Si no usamos tips específicos, los 141 tips sin fecha
dejan de ser un riesgo, y el conocimiento estructural es intrínsecamente
atemporal. `as_of_date` **sigue siendo necesario** (un DecisionFrame de julio
también contiene una lectura de mercado concreta), pero el montaje deja de ser
frágil.

---

## 3. Preguntas

### P1. [BLOQUEANTE] ¿Se puede separar la capa estructural de la táctica?

Necesitamos poder ejecutar el motor **usando los DecisionFrames y los módulos,
pero sin que los tips específicos de activo arrastren la decisión**.

- **P1.a** ¿Existe o se puede añadir un parámetro tipo `use_tipbank=False`, o una
  ponderación entre ambas fuentes?
- **P1.b** Dentro del propio TipBank, ¿hay forma de distinguir tips
  *estructurales* ("si el VIX supera 30 el playbook cambia") de tips *tácticos*
  ("me gusta NVDA en este nivel")? Los primeros nos interesan mucho; los segundos
  no. Si existe un campo de tipo, horizonte o categoría que permita filtrarlos,
  sería mejor que apagar el TipBank entero.
- **P1.c** **Al desactivar los tips, ¿se degrada el motor?** Es decir: ¿el
  `confidence` se hunde, dejan de activarse módulos, o el árbol sigue funcionando
  con normalidad apoyándose solo en los frames? Necesitamos saber si es un modo de
  uso soportado o una amputación.

### P2. [BLOQUEANTE] ¿El motor emite guía a nivel de categoría, no solo de activo?

Vuestro ejemplo de salida clasificaba activos concretos (`NVDA` →
`assets_to_favor`). Para nosotros eso sirve en 3 de 128 casos.

Lo que necesitamos es la capa de arriba: **qué tipo de activo favorecer**, en
términos que podamos mapear sobre nuestros temas y sectores. Por ejemplo:

```
"favor":  ["energía", "materias primas", "value defensivo"]
"avoid":  ["duración larga", "growth especulativo", "mercados emergentes"]
"risk_posture": "reducir exposición" | "neutral" | "añadir riesgo"
```

- **P2.a** ¿El motor ya produce algo así, o solo clasifica activos canónicos?
- **P2.b** Si solo clasifica activos: ¿hay una taxonomía de sectores/temas
  intermedia (los módulos como `energia_petroleo`, `ia_tecnologia_productividad`,
  `degradacion_monetaria` apuntan a que sí)? ¿Se puede exponer la clasificación a
  ese nivel?

*Nosotros tenemos 21 subtemas propios (mineras de plata, petróleo canadiense,
energía argentina, farmacéutica de calidad…) más un `cluster` macro. El puente
natural sería mapear vuestras categorías contra los nuestros — pero necesitamos
saber cuáles son vuestras categorías.*

### P3. [BLOQUEANTE] Lista completa de activos canónicos

Pasadnos el `asset_canonical_map.json` (o solo la lista de IDs canónicos). Con él
calculamos el solapamiento exacto y, sobre todo, sabemos qué activos **sí** puede
tratar directamente el agente — para esos pocos, la guía a nivel de activo sigue
siendo valiosa y la usaríamos.

### P4. [AJUSTE] ¿El régimen es global o por activo?

Cuando el árbol devuelve `dominant_regime`, ¿es una lectura **del mercado en
conjunto**, o depende de qué activos se hayan incluido en la query?

*Importa porque determina cómo llamamos al motor: una sola query por día con el
estado macro (barato, coherente), o una query por candidato (caro, y con riesgo de
que el "régimen" varíe según qué ticker preguntemos, lo cual sería incoherente).*

### P5. [AJUSTE] ¿Cuánto conocimiento estructural hay realmente?

De los 112 DecisionFrames, ¿cuántos codifican **reglas y playbooks reutilizables**
(tipo "VIX > 30 cambia el playbook", "cuando los spreads de crédito se amplían y
el precio no lo confirma, prevalece el precio") frente a los que son **lectura de
un momento concreto** ("el 12 de junio el mercado estaba así")?

*No es una pega: es dimensionar cuánta señal transferible hay. Si el grueso del
valor está en 20 reglas estructurales muy buenas, mejor saberlo — cambia lo que
esperamos del sistema y cómo lo medimos.*

---

## 4. Consecuencia para la medición (nuestro lado)

El reenfoque cambia qué prueba la Fase 1, y conviene dejarlo dicho antes de correr
nada:

- **Antes:** "¿elige el agente mejores tickers que nuestras baselines?"
- **Ahora:** "¿mejora la lectura de régimen de Cava la selección que ya hacemos?"

Es una pregunta distinta y con una dificultad añadida: si el resultado es malo, hay
que poder distinguir si falla **la lectura de régimen del agente** o **nuestra
traducción de esa lectura a candidatos concretos**. Lo resolvemos con una
comparación a tres bandas sobre los mismos días:

| Configuración | Qué aísla |
|---|---|
| Top-3 PCS puro | Baseline mecánica, sin capa macro |
| Nuestro `MacroScore` + PCS | Sistema actual |
| Régimen de Cava + PCS | El agente sustituyendo solo la capa macro |

Si la tercera bate a la segunda, el agente aporta valor en la capa donde decimos
que lo aporta, y queda medido de forma limpia.

---

## 5. Pendientes de la Ronda 2 (informativo)

Dos cosas que resolvemos por nuestro lado, sin acción vuestra:

1. **Universo del backtest.** Detectamos que nuestros payloads históricos
   guardados están recortados a ~21 candidatos (una preselección nuestra), no a
   los ~128 de producción. Backtestear sobre la preselección respondería a una
   pregunta sesgada por nuestro propio ranking. Lo resolvemos reconstruyendo el
   universo completo desde el historial de git (158 instantáneas diarias
   disponibles, mayo–agosto 2026).

2. **Cobertura del corpus.** Vuestro corpus llega al 2026-07-17 y nuestra ventana
   de backtest al 2026-08-01. Las últimas dos semanas correrán con un corpus de
   hasta 15 días de antigüedad. Lo tendremos en cuenta al leer los resultados y no
   interpretaremos ese tramo final como degradación real.

---

## 6. Resumen — lo que necesitamos para arrancar

Se mantiene lo de la Ronda 2 (`as_of_date`, motor empaquetado, corpus versionado),
y se añade:

1. **P1** — modo "solo estructural": desactivar o despriorizar el TipBank táctico,
   y confirmar que el motor no se degrada al hacerlo.
2. **P2** — salida a nivel de categoría/sector, no solo de activo canónico.
3. **P3** — lista de activos canónicos.

Con P1–P3 podemos escribir el mapping con el enfoque correcto. Sin ellas
escribiríamos una traducción orientada a selección de tickers que, con un
solapamiento del 2 %, no tendría recorrido.
