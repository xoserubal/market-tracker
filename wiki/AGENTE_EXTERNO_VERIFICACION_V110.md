# Cava AI → AI Picks Lab — Verificación de la entrega v1.1.0

> Hemos ejecutado el paquete contra nuestro mapping y nuestros datos históricos
> reales. **Las dos pruebas que decidían la viabilidad del proyecto pasan.**
>
> Este documento recoge: qué hemos verificado y cómo, **dos fallos que hemos
> encontrado**, tres detalles menores, y una corrección importante de un dato que
> os dimos mal en la Ronda 5.

---

## 1. Lo que hemos verificado ejecutando el motor

No es revisión de código: hemos cargado `cava_engine` in-process, le hemos
enviado estados macro reconstruidos de fechas históricas reales, y hemos mirado
la salida.

### 1.1 Test de invariancia de `deterministic_risk_posture` — ✅ PASA

El que os anunciamos en la nota pre-desarrollo. Mismo estado de mercado (abril de
2025), ocho combinaciones distintas de `as_of_date` × `corpus_scope`:

| `as_of_date` | scope | frames en corpus | `deterministic_risk_posture` |
|---|---|---|---|
| 2024-08-15 | baseline | 15 | `reduce_risk` |
| 2024-08-15 | pilot | 15 | `reduce_risk` |
| 2025-04-08 | baseline | 17 | `reduce_risk` |
| 2025-04-08 | pilot | 17 | `reduce_risk` |
| 2026-08-15 | baseline | 77 | `reduce_risk` |
| 2026-08-15 | pilot | **112** | `reduce_risk` |
| `None` | baseline | 77 | `reduce_risk` |
| `None` | pilot | 112 | `reduce_risk` |

**Idéntico en las ocho, con el corpus variando de 15 a 112 frames.** La
invariante se cumple, así que la Prueba 1C (validación histórica estructural) es
viable. Era el desbloqueo del que dependía todo.

### 1.2 Prueba de falsación — ✅ PASA

Estado real del 8 de abril de 2025 (SPY −18,8 %, VIX 52,3, HY 457 pb tras
ampliarse 141 en un mes), con corpus completo:

```
Enviado : capitulation / below_ma / extreme / critical / extreme_fear
Devuelto: deterministic_risk_posture = "reduce_risk"
          L1 = negative · L2 = mixed · L3 = negative
          regla aplicada: L1_L3_aligned_bearish
```

Nuestra traducción convierte un estrés obvio en un diagnóstico de estrés. Era
justo lo que esta prueba tenía que descartar.

### 1.3 `as_of_date` — ✅ funciona

Filtra correctamente (77 → 15 frames al retroceder a 2024-08) y conserva los 12
frames sin fecha, como acordamos.

---

## 2. Dos fallos encontrados

### 2.1 [IMPORTANTE] `insufficient_corpus` no puede dispararse casi nunca

En `core.py`:

```python
DEFAULT_TOP_K = 5
supporting = [x for x in all_scored[:top_k] if x[0] > 0]   # ≤ 5 por construcción
...
"minimum_required": 5
insufficient = supporting_count < 5
```

`supporting_frames_count` está **acotado por `top_k`, que vale 5**, y el umbral
mínimo es exactamente 5. El flag solo salta si menos de 5 frames puntúan por
encima de cero — que es una cuestión de *scoring*, no de densidad del corpus.

Comprobado en el peor escenario posible, `as_of_date = 2024-10-01`:

```
frames disponibles : 17  (de los cuales 12 son los legacy sin fecha
                          → solo 5 frames fechados reales)
corpus_health      : {"insufficient_corpus": false, "supporting_frames_count": 5,
                      "minimum_required": 5, "warning": null}
```

**Reporta corpus sano en pleno desierto de datos.** Es exactamente el falso
positivo que pedíamos evitar en P6.b: "preferimos que nos diga 'con estos datos
no puedo opinar' a que emita un régimen apoyado en 3 vídeos sueltos".

**Fix sugerido:** el flag debería medirse contra el tamaño del corpus disponible
en esa fecha, no contra la selección top-k. Toda la información ya está en
`corpus_meta`:

```python
dated = (baseline_frames_used + incremental_frames_used
         - undated_frames_included)
insufficient = dated < MIN_DATED_FRAMES     # p. ej. 15
```

Con eso, la fecha de arriba daría `dated = 5` y saltaría correctamente.

No es urgente para nosotros —podemos calcularlo por nuestro lado desde
`corpus_meta`— pero como el flag existe y lo vamos a registrar en cada decisión,
preferimos que signifique lo que aparenta.

### 2.2 [A CONFIRMAR] ¿Es `risk_off` alcanzable en la práctica?

La cascada de `deterministic_risk_posture`:

```python
if l1_sig == "negative":
    if l2_sig == "negative":  det_posture = "risk_off"
    else:                     det_posture = "reduce_risk"
```

`risk_off` exige **L2 unánimemente negativo**. En abril de 2025 —el mayor
drawdown en dos décadas— L2 salió `mixed` y el resultado fue `reduce_risk`.

El motivo está en nuestro lado y es interesante: enviamos
`volatility_state = extreme` (L2 negativo) pero también
`liquidity_state = favorable`, porque la liquidez neta **estaba realmente
expandiéndose** (+201 mil M a 4 semanas, +405 mil M a 8). Un módulo L2 negativo y
otro positivo → `mixed` → nunca `risk_off`.

**La pregunta es conceptual, y es vuestra, no nuestra:** en la lectura de Cava,
¿una expansión de liquidez durante un crash debe leerse como señal positiva que
atenúa el riesgo, o como *síntoma* del estrés (el banco central inyectando
precisamente porque hay pánico) y por tanto no debería puntuar como positiva?

Si es lo segundo, el ajuste va en nuestro mapping y lo hacemos nosotros. Si es lo
primero, entonces `risk_off` probablemente sea un estado casi inalcanzable —
porque los bancos centrales suelen expandir liquidez justo en las crisis— y
conviene saberlo antes de construir lógica encima.

Lo preguntamos porque ya nos hemos comido un caso así este mes en nuestro propio
código: una rama inalcanzable porque dos umbrales se tocaban sin dejar hueco. La
detectó un test, no una revisión.

---

## 3. Tres detalles menores

**3.1 El ejemplo del README no ejecuta.** Muestra:

```python
corpus = load_corpus("/path/to/corpus", as_of_date="2026-05-15")
result = query_tree(corpus, estado_macro)
```

Pero la firma real es `load_corpus(corpus_scope, as_of_date)` → devuelve una
**tupla de 4** `(tree, index, timeline, corpus_meta)`, y `query_tree(tree, index,
timeline, market_state, top_k, corpus_meta)` toma cuatro posicionales. La llamada
correcta es:

```python
tree, index, timeline, meta = load_corpus(CORPUS_SCOPE_PILOT, as_of_date="2026-05-15")
res = query_tree(tree, index, timeline, estado_macro, corpus_meta=meta)
```

**3.2 `corpus_scope` por defecto excluye todo el corpus denso.** El valor por
defecto es `baseline`, y los 35 frames incrementales solo se cargan con
`CORPUS_SCOPE_PILOT`. Es decir: **por defecto se pierde toda la ventana de 2026**,
que es justo donde está la densidad y donde vive la Alternativa 2. Merece un
aviso destacado en el README, porque es fácil ejecutar sin darse cuenta con 77
frames en vez de 112.

**3.3 `corpus_snapshot` no está.** En la Ronda 4 describisteis un bloque con
`corpus_date_range`, `tips_after_filter`, etc. Lo entregado es `corpus_meta` con
los recuentos, que nos vale para casi todo, pero **falta el rango de fechas** del
corpus efectivamente usado. Nos gustaría tenerlo para registrarlo junto a cada
decisión — es lo que permitirá, dentro de seis meses, saber con qué conocimiento
se tomó una decisión concreta.

---

## 4. Corrección de un dato que os dimos mal

En la Ronda 5 escribimos que la Prueba 1C nos daría "cinco episodios de estrés".
**Era incorrecto y queremos corregirlo antes de que nadie construya expectativas
sobre ese número.**

Al reconstruir el estado histórico descubrimos primero un error nuestro: lo
estábamos haciendo en cadencia semanal, y el cierre semanal borra las caídas que
se recuperan dentro de la semana. Reconstruido en diario, el recuento real sobre
2024-2026 es:

```
647 sesiones · 35 en estado de estrés (5 %) · 3 episodios distintos

  2024-08-05 → 2024-08-07   2 sesiones   (VIX 38,6 — carry del yen)
  2025-03-10 → 2025-05-07  31 sesiones   (VIX 52,3 — el grande)
  2026-03-27 → 2026-03-30   2 sesiones   (VIX 30,6)
```

Son **3 episodios, no 5**, y uno concentra el 89 % de las sesiones. Sigue siendo
mejor que el único episodio evaluable con corpus denso, pero no es la muestra que
insinuamos.

### La contrapartida: la Prueba 1C no tiene por qué limitarse a vuestro corpus

Y aquí está lo bueno, que se deriva directamente de que la invariante del punto
1.1 se cumpla: **si `deterministic_risk_posture` no depende del corpus, entonces
la ventana del corpus (2024-04 en adelante) no lo limita.**

Nuestras series de SPY y VIX llegan a 2004. Sesiones con VIX > 30 por año:

```
2008: 79 (máx 81)   2011: 75 (máx 48)   2020: 80 (máx 83)   2022: 48
2009: 111           2010: 23 (máx 46)   2015: 4  (máx 41)   2018: 5
2021: 6             2024: 1  (máx 39)   2025: 12 (máx 52)   2026: 2
```

**Doce regímenes de estrés en veinte años**, y de naturaleza distinta: crisis de
crédito, pandemia, shock de tipos, geopolítica. Eso sí es una muestra.

**Con una limitación que hay que decir:** el spread HY solo está disponible desde
agosto de 2023 (verificado contra FRED, no es carencia de nuestro almacén). Los
episodios anteriores se evaluarían **sin la dimensión de crédito**, que en
vuestra jerarquía es L1. Según vuestro M4 eso degrada con elegancia —el módulo
simplemente no se activa— pero significa que para 2008 o 2020 estaríamos midiendo
vuestro marco con precio y volatilidad, no con crédito.

Nos parece un intercambio que vale la pena: doce episodios parcialmente medidos
informan más que tres bien medidos, sobre todo cuando el peso de esos tres está
en uno solo.

---

## 5. Estado de nuestro lado

- **Mapping direcciones A y B**: escritos, **98 tests pasando**.
- **Contrato de categorías actualizado a 15.** Detectamos `defense_aerospace`
  **al verificar el paquete, no porque nos avisarais** — y lo detectamos porque
  nuestro validador lanza excepción ante una categoría desconocida en vez de
  ignorarla. Es exactamente el fallo silencioso que queríamos evitar al pediros
  la lista cerrada, funcionando como se diseñó. Gracias por resolver
  `defense_space`.
- **Reconstructor de estado histórico**: funcionando en diario desde 2004.

**Siguen pendientes `uranium_nuclear` y `energy_storage`.** Mencionáis un
documento de "Respuestas Operativas" que las resuelve, pero no nos ha llegado —
solo tenemos el paquete. Mientras tanto quedan sin opinión y se operan solo con
PCS.

---

## 6. Qué necesitamos

1. **2.2** — la lectura conceptual sobre liquidez expansiva en crisis. Es la
   única que puede cambiar nuestro mapping.
2. **`uranium_nuclear` y `energy_storage`** — reenviadnos ese documento.
3. **2.1** — el fix de `insufficient_corpus`, cuando podáis. No nos bloquea.

Nada de esto impide que arranquemos: con lo entregado ya podemos ejecutar la
Prueba 1C y la de falsación. Empezamos con eso.
