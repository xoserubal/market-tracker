# Cava AI → AI Picks Lab — Ronda 4: rediseño de la validación

> **Continuación de `AGENTE_EXTERNO_RONDA3.md`.** Vuestra respuesta cerró P1–P5.
> Al preparar el backtest hemos medido nuestra propia ventana histórica y hemos
> encontrado un problema serio **en nuestro plan de validación**, no en vuestro
> sistema: íbamos a probar el agente exactamente donde menos puede aportar.
>
> Este documento explica el hallazgo, propone una validación distinta, y añade
> dos preguntas que se derivan de ella.

---

## 1. Lo que queda cerrado de la Ronda 3

| Pregunta | Respuesta | Estado |
|---|---|---|
| P1 Separar estructural/táctico | **El TipBank no está conectado al motor** — no hay nada que desactivar | ✅ Se disuelve |
| P2 Guía por categoría | Nuevo bloque `regime_guidance` | ✅ Aceptado, es justo lo que necesitábamos |
| P3 Activos canónicos | 137 entradas, lista recibida | ✅ Confirma el ~2-5 % de solapamiento |
| P4 Régimen global o por activo | **Global** → 1 query al día | ✅ Simplifica mucho |
| P5 Conocimiento estructural | Distribuido, no 20 reglas | ✅ Respuesta honesta y útil |

Sobre el `asset_canonical_map.json`: con la lista del documento nos vale de
momento. Si lo incluís en el paquete pip, mejor aún — así queda versionado junto
al motor.

Agradecemos especialmente la respuesta a **P5**. "Un método de razonamiento
calibrado sobre 112 días de mercado" es una descripción honesta, y es justo lo que
nos permite diseñar bien la validación. De hecho es lo que ha destapado el
problema siguiente.

---

## 2. El problema: nuestra ventana de backtest no tiene régimen que leer

Habíamos propuesto validar sobre nuestros 76 payloads históricos (mayo–agosto
2026). Hemos medido qué régimen macro hubo en esa ventana:

```
Ventana de backtest (76 días, may–ago 2026)
  Bull Maduro : 62 días
  Bull Pleno  : 14 días
  MacroScore  : 65 → 100
  Transiciones de régimen: 2
```

**Todo el periodo es alcista.** No hubo ni una sola sesión en `Transición`,
`Risk-OFF` ni `Capitulación`.

El problema es evidente al ponerlo al lado de lo que sabemos del sistema: el valor
de Cava está en las reglas de estrés y de cambio de régimen — VIX > 30 cambia el
playbook, spreads de crédito ampliándose, capitulación, el módulo
`risk_management_invalidaciones`, las 231 invalidaciones. **En nuestra ventana no
se dispararía ninguna de ellas.** Estaríamos midiendo un marco de gestión de
riesgo en un periodo sin riesgo.

El resultado más probable sería "Cava dice risk-on, nuestro MacroScore dice
risk-on, no hay diferencia medible" — lo cual no informa de nada. Y sería peor si
saliera un número aparentemente bueno, porque nos daría confianza injustificada.

### La buena noticia: hay ventana mejor

Tenemos histórico propio de MacroScore y régimen **desde 2005** (semanal). En la
ventana que cubre vuestro corpus:

```
Ventana del corpus Cava (2024-04-12 → 2026-07-17, 119 lecturas semanales)
  Transición  : 68
  Risk-OFF    : 31      ← 31 semanas de estrés real
  Bull Maduro : 20
  MacroScore  : 26,7 → 75,0
```

Frente a las 2 transiciones de nuestra ventana original, aquí hay **variedad
genuina de régimen, incluyendo 31 semanas de Risk-OFF**. Es donde el marco de Cava
debería demostrar que sirve.

---

## 3. La validación rediseñada: dos pruebas separadas

### Prueba 1A — La lectura de régimen, aislada *(la que importa)*

- **Ventana:** 2024-04 → 2026-07 (119 lecturas semanales, todo vuestro corpus).
- **Entrada:** reconstruimos el estado macro en cada fecha (VIX, spreads de
  crédito, curva, liquidez, precio vs medias) desde nuestros datos históricos, y
  lo traducimos a vuestro vocabulario controlado.
- **Salida:** `regime_guidance` + `risk_posture` con `as_of_date` en esa fecha.
- **Evaluación:** ¿anticipa `risk_posture` el comportamiento posterior del mercado
  mejor que nuestro `MacroScore`? Comparación directa contra el índice, sin pasar
  por candidatos.

**Esta prueba no necesita nuestros 128 candidatos ni el mapeo de categorías.** Y
eso responde directamente a vuestro apunte del final de la Ronda 3: aquí no hay
paso intermedio de interpretación que pueda contaminar el resultado. Si la lectura
de régimen de Cava es mejor que la nuestra, se verá limpiamente; si no, también.

### Prueba 1B — El circuito completo *(comprobación de fontanería)*

- **Ventana:** los 76 días de mayo–agosto 2026.
- **Qué valida:** que el mapping funciona, que las categorías se traducen a
  nuestros temas, que el cableado produce picks coherentes.
- **Qué NO valida:** rentabilidad. Con régimen constante y alcista, el resultado
  no es informativo y así lo trataremos.

Dicho de otro modo: **1A decide si el agente entra en producción; 1B solo
comprueba que el enchufe funciona.**

---

## 4. Preguntas nuevas

### P6. [BLOQUEANTE] Densidad de frames por fecha

Esta es la mayor amenaza para la Prueba 1A. Vuestros propios números:

| Corpus | Frames | Ventana | Densidad |
|---|---|---|---|
| Baseline (V6.5) | 77 | 2024-04 → 2026-05 (25 meses) | **~3 / mes** |
| Incremental (V6.6-dev) | 35 | 2026-06 → 2026-07 (1,5 meses) | **~23 / mes** |

La densidad del incremental es **ocho veces** la del baseline. Consecuencia: con
`as_of_date = 2024-08-15` (plena ventana de Risk-OFF, justo donde queremos
probar), el motor dispondría quizá de 10–15 frames en total.

- **P6.a** ¿Nos pasáis el **recuento de frames por mes** en todo el corpus? Con
  eso sabemos qué tramos de la Prueba 1A son evaluables y cuáles no.
- **P6.b** ¿Hay un **mínimo de frames por debajo del cual la votación ponderada
  deja de ser significativa**? Si el motor puede señalarlo (un `confidence` bajo,
  o un flag tipo `insufficient_corpus`), mucho mejor: preferimos que nos diga "con
  estos datos no puedo opinar" a que emita un régimen apoyado en 3 frames.
- **P6.c** ¿Los 31 tramos de Risk-OFF de 2024 y finales de 2025 están **cubiertos
  por frames**, o el corpus se concentra en los periodos más recientes? Si esos
  tramos están vacíos, la Prueba 1A no se puede hacer tal cual y habría que
  replantearla.

### P7. [AJUSTE] Cobertura de módulos frente a nuestro universo

Cruzando la fuerza de vuestros módulos (por *reasoning steps*) con la composición
real de nuestro universo:

| Nuestro tema | Candidatos | Módulo Cava correspondiente | Steps | Cobertura |
|---|---|---|---|---|
| `silver_gold_miners` | 20 | `degradacion_monetaria` | 46 | 🟢 Fuerte |
| `oil_gas` | 15 | `energia_petroleo` | 38 | 🟢 Fuerte |
| `us_tech_ai` | 9 | `ia_tecnologia_productividad` | — | 🟡 Media |
| `argentina` | 11 | `dolar_dxy` / EM | — | 🟡 Indirecta |
| `healthcare_largecap` + `healthcare_special` | 21 | *ninguno* | — | 🔴 Nula |
| `cannabis` | 7 | *ninguno* | — | 🔴 Nula |

Además, los dos módulos que más nos servirían para rotación temática —
`sector_rotation` (9 steps) y `relative_strength` (3 steps) — son de los más
delgados del corpus.

- **P7.a** ¿Es correcta esta lectura? ¿Hay cobertura de salud o de temas
  defensivos que no estemos viendo?
- **P7.b** Para los temas sin módulo (salud, cannabis ≈ 28 de 128 candidatos),
  ¿qué debería devolver `regime_guidance` — quedan fuera de `favor`/`avoid`, o
  caen en `equity_general`? **Preferimos que el agente diga explícitamente "sobre
  esto no opino" a que los meta en un cajón genérico.** Un "no tengo criterio
  aquí" honesto es más útil que una clasificación inventada, y además nos permite
  medir por separado el rendimiento en los temas que sí cubre.

---

## 5. Corrección por nuestra parte

En la Ronda 3 dijimos "21 subtemas". Al preparar el puente de categorías hemos
comprobado que **`subtheme` está vacío en 54 de 128 candidatos (42 %)** — no es un
campo fiable para mapear.

Los campos sólidos son:

- **`theme`** — poblado en el **100 %** de los candidatos. Valores actuales:
  `silver_gold_miners` (20), `healthcare_largecap` (15), `oil_gas` (15),
  `argentina` (11), `us_tech_ai` (9), `us_cyclical` (9), `cannabis` (7),
  `healthcare_special` (6), `europa` (6), `china_em` (6), y algunos más.
- **`cluster`** — poblado en el 98 %: `Commodities` (19), `Salud_Largecap` (14),
  `Value/Cyclical` (13), `Growth` (13), `Argentina` (11), `Europa` (8),
  `Canada_Energy` (8), `Cannabis` (7), `Mineras_Juniors` (7)…

**El puente de categorías se hará contra `theme` y `cluster`, no contra
`subtheme`.** Lo mencionamos porque afecta a la tabla de correspondencias que
propusisteis en P2.b.

---

## 6. Resumen — qué necesitamos ahora

Se mantiene todo lo de rondas anteriores (`as_of_date`, motor empaquetado, corpus
versionado, `regime_guidance`), y se añade:

1. **P6.a** — recuento de frames por mes.
2. **P6.b** — mínimo viable de frames, e idealmente un flag de corpus insuficiente.
3. **P6.c** — confirmación de si los tramos de Risk-OFF de 2024 y finales de 2025
   tienen cobertura.

**P6 es ahora el punto crítico del proyecto.** Si el corpus está concentrado en
los meses recientes y los periodos de estrés están vacíos, la Prueba 1A no se
puede ejecutar — y sin ella no tenemos forma honesta de validar el agente antes de
ponerlo a operar. En ese caso habría que hablar de alternativas (validación hacia
adelante con dinero simulado durante varios meses, esperando a que llegue un
periodo de estrés real).

Preferimos saberlo ahora.
