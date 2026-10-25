# Incidencia: tickers sin proxy representativo — el componente B del PCS usa la media del tema

**Estado:** abierta. Solo diagnóstico. **No se implementa ninguna fórmula nueva del PCS** y no se toca nada en la corrección de la línea B.
**Fecha de apertura:** 2026-10-25.
**Origen:** revisión de TK (Teekay) durante la línea B. Afecta a muchos más tickers que TK.

## El problema

El componente B del PCS («flujo del tema», techo 24) sale de dos fuentes distintas, según haya o no proxy:

1. **Proxy propio.** Si `theme_proxy` está en `rotation_signals.json` (22 ETFs y futuros: XLE, XLK, GC=F, BZ=F…), B sale del `rot_score` de ese proxy.
2. **Media del tema.** Si no (proxy vacío, o un proxy que no está en esas 22 señales como GDX, SIL, COPX, URA, XAR, GGAL…), B sale del retorno medio a 13 semanas de los *otros tickers del mismo `theme`*.

El segundo camino mezcla dos cosas que deberían ser independientes: `theme` sirve para **clasificar y medir concentración**, pero también decide **qué compañeros alimentan B**. Corregir bien la clasificación de un ticker (objetivo) cambia a la vez su B (efecto de modelado), y cuando el tema no representa el driver bursátil del ticker, el componente B no mide lo que dice medir.

## Evidencia (universo corregido de la rama `fix/universe-integrity-b`, datos del 2026-10-24)

- **71 de 147 tickers (48 %) usan la media del tema.** 35 por proxy vacío, 36 por un proxy que no está entre las 22 señales (GGAL 11, GDX 5, SIL 5, XAR 3, COPX 3, URA 3, MSOS 2, KWEB 2, FXI 1, GDXJ 1).
- De los 66 elegibles que lo usan, **5 cambian de tramo de selección según ese efecto** (comparando con un B neutro de 10):

| Ticker | PCS | PCS con B neutro | Tramo que depende de la media del tema |
|---|---|---|---|
| GTE | 78,5 | 70,5 | CFL (75) |
| TK | 71,2 | 63,2 | ER (68) |
| YAL.AX | 70,0 | 62,0 | ER (68) |
| WHC.AX | 68,5 | 60,5 | ER (68) y MTB (62) |
| VGZ | 57,5 | **63,5** | MTB (62) — aquí la media del tema **resta** |

El efecto no es un sesgo a favor: puede subir o bajar el PCS de forma arbitraria respecto a la neutralidad.

## Caso TK

TK es `oil_gas / tankers` sin proxy (decisión: XLE no representa fletes). Su B = 18 sale de lo que hacen las petroleras, no de los fletes. Aun así, **el PCS de TK no depende solo de eso**: su componente C está en el máximo (23) y su retorno a 13 semanas es +28,5 % (`rot_score` 7). Con B neutro quedaría en 63,2, por encima del suelo de 62. Lo que cambia es el tramo: con la media del tema sube de MTB a ER.

**¿Puede seleccionarse automáticamente con 71,2?** (comprobado)

| Vía | ¿Puede elegir TK? |
|---|---|
| HIGH_CONVICTION (85) y CFL (78) | No: 71,2 no alcanza el umbral. |
| EARLY_ROTATION (70 / entrada 68) y MTB (65 / 62) | Entra en el conjunto de candidatos que ve la IA. **La selección la decide la IA con HARD_RULES**, no el PCS solo. Además, la regla «todo candidato con PCS ≥ 62 no elegido debe estar en `watch` o `rejected`» obliga a razonar sobre TK. |
| CAVA_MACRO (mecánica, solo PCS) | Podría entrar **solo si queda hueco**: hoy tiene 10 de 10 posiciones y postura neutral sin temas favorecidos. Competiría por PCS con el resto. |
| RANKING_SHADOW_EXPERIMENTAL (mecánica) | No: exige `ranking_score_eligible` y en el `ai_candidates.json` publicado los 149 candidatos lo tienen en `false` (faltan los cuatro campos delta; el checkout de CI es `fetch-depth: 1`). Esto es independiente de la corrección y conviene revisarlo aparte: **hoy esa cartera no puede elegir nada en el pipeline**. |
| Carteras de señal técnica (Mirror, Cruce Rojo, Trullás, Screener, MACD) | No usan el PCS para elegir. |

Además, lo que la IA ve de TK incluye `component_B = 18` y `flags` con `theme_avg_strong` (en la posición 2 de una lista recortada a 5), pero **no hay forma de saber qué significa** ni de distinguirlo de un B basado en un proxy propio.

## Protecciones posibles sin cambiar la fórmula (para decidir, no implementadas)

Ninguna cambia el cálculo del PCS ni quita la clasificación económica de TK; son transparencia y avisos.

1. **Procedencia explícita de B** — campo `component_B_basis` ∈ {`own_proxy`, `theme_average`, `no_theme_data`}. Es información que el cálculo ya conoce (hoy solo se deduce de las `flags`); se añadiría a `ai_candidates.json` y al payload de la IA. Coste bajo.
2. **Tramo dependiente del fallback** — dos campos derivados: `pcs_neutral_b` (el PCS con B = 10) y un indicador `selection_tier_depends_on_b_fallback` cuando `pcs` y `pcs_neutral_b` caen a distinto lado de un umbral. No decide nada; marca los 5 casos de arriba. Coste bajo.
3. **Texto de guía a la IA** (soft, sin penalización de calidad, como el resto de guías de observación): «si `component_B_basis = theme_average`, B refleja a los compañeros del tema, no el driver propio del ticker; no lo cites como evidencia específica». Coste bajo.
4. **Marca en el dashboard** (AI Picks Lab): icono junto al PCS cuando B no es de proxy propio. Coste bajo.
5. **Objetivo futuro (otra decisión, otra incidencia de diseño):** separar `theme` (clasificación y concentración) de la **fuente del componente B** (`b_source` explícito por ticker: proxy concreto, media de un grupo definido a mano, o neutral). Esto sí cambiaría PCS, por lo que exigiría preregistro y simulación como la línea B.

## Qué debe responder la auditoría

1. Para cada uno de los 71 tickers: ¿existe un proxy representativo entre las 22 señales de rotación o entre ETFs que se puedan añadir? ¿Cuántos se resolverían ampliando el conjunto de señales (p. ej. GDX/SIL/COPX/URA)?
2. ¿La media del tema es una aproximación razonable para su grupo (p. ej. mineras de plata entre sí) o arbitraria (petroleros de fletes con petroleras)?
3. ¿Cuánto del PCS que lee la IA viene de B por esta vía, y ha condicionado alguna selección real? Medirlo con los payloads y `model_tests` históricos.
4. ¿Qué umbral de «tramo dependiente del fallback» es útil sin generar ruido?

## Alcance

Diagnóstico y simulación con datos congelados. **Sin cambios en `pcs_calculator.py`, `ai_shared.py` ni en reglas de selección** hasta que se apruebe. No mezclar con la línea A ni con la incidencia de concentración (`wiki/INCIDENCIA_CONCENTRACION_TEMATICA.md`).
