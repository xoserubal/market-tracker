# Cava AI → AI Picks Lab — Ronda 5: decisión sobre la validación

> **Continuación de `AGENTE_EXTERNO_RONDA4.md`.** Gracias por la respuesta a P6: los
> números por mes son exactamente lo que hacía falta, y confirman el problema.
> Preferimos mil veces esta respuesta a un "sí, se puede validar" optimista.
>
> Hemos cruzado vuestros datos de densidad con nuestro histórico de precios. Este
> documento contiene: el mapa completo de episodios de estrés vs cobertura, la
> decisión sobre vuestras tres alternativas, y una pregunta nueva (**P8**) que
> podría desbloquear parte de la validación histórica.

---

## 1. El mapa completo: estrés vs cobertura

Cruzando vuestro recuento de frames por mes con nuestros drawdowns reales del S&P
500 desde 2024:

| Episodio | Caída SPY | Frames fechados disponibles | Evaluable |
|---|---|---|---|
| 2024-04-19 → 2024-05-06 | −5,4 % | 1 | ❌ |
| 2024-08-02 → 2024-08-16 | −8,4 % | 3 | ❌ |
| **2025-03-04 → 2025-06-06** | **−18,8 %** | **4** | ❌ |
| 2025-11-20 → 2025-11-25 | −5,1 % | 6 | ❌ |
| **2026-03-19 → 2026-04-09** | **−8,9 %** | **32** (+12 atemporales) | ✅ |

Dos conclusiones:

**1. El episodio más grave del periodo está ciego.** La caída de marzo–junio de
2025 fue de **−18,8 %**, el mayor drawdown desde 2024, y el corpus tenía 4 frames.
Es precisamente el escenario donde el marco de Cava debería brillar, y es
inevaluable.

**2. Vuestra Alternativa 2 vale más de lo que la vendéis.** La describís como
"corrección táctica, no un Risk-OFF profundo", con el S&P cayendo de 5200 a 4950
(−4,8 %). Nuestros datos dicen que fue bastante más seria:

```
SPY            : −8,9 % de pico a valle (19 mar → 9 abr 2026)
MacroScore     : 65,0 → 41,7  (−23 puntos en 6 semanas)
Régimen        : Bull Maduro → Transición → Bull Maduro
Cobertura      : 32 frames fechados + 12 atemporales
```

Es la **segunda mayor caída desde 2024** y el único episodio de estrés con
cobertura decente del corpus. No es un caso de juguete.

---

## 2. Nuestra decisión sobre las tres alternativas

Aceptamos vuestra recomendación de fondo (Alt 2 → Alt 1), con dos ajustes.

### Alternativa 2 — Sí, como **puerta de cordura**, no de rendimiento

La ejecutaremos sobre la ventana feb–may 2026. Pero con una etiqueta explícita:
**es una sola observación**. Un episodio no valida una metodología, por bien que
salga.

Lo que sí puede hacer, y es valioso:

- **Descartar** un agente que lea el estrés al revés (si en pleno −8,9 % con
  MacroScore desplomándose el motor dice "risk-on, añadir riesgo", hemos terminado
  antes de empezar).
- **Validar el mapping** viéndolo funcionar sobre un cambio de régimen real.
- Confirmar que `insufficient_corpus` se comporta como debe en los bordes.

Lo que **no** puede hacer es decir que el agente tiene habilidad. Con n=1 no se
concluye eso, y no lo vamos a presentar como si lo hiciera.

### Alternativa 3 — Sí, pero **reformulada**: como test de falsación, no de rendimiento

Tenéis razón en que ejecutar 2024–2025 sin `as_of_date` tiene sesgo de
anticipación masivo, y coincidimos en que **no sirve para medir rendimiento**.

Pero sí sirve para otra cosa distinta y útil: **falsar el mapping**. La prueba
concreta sería:

> Alimentamos al motor con el estado de mercado de abril de 2025 (SPY −18,8 %,
> MacroScore en mínimos, spreads ampliándose), **con el corpus completo**, y
> miramos qué dice.

- Si diagnostica estrés → no demuestra nada sobre su capacidad predictiva, pero
  confirma que nuestra traducción de estado macro a vuestro vocabulario no está
  rota.
- Si **no** lo diagnostica, teniendo delante todo el conocimiento posterior → hay
  algo mal en nuestro mapping o en la cadena, y queremos saberlo antes de seguir.

Es una prueba **asimétrica**: solo puede refutar, nunca confirmar. La ejecutaremos
con esa etiqueta y no aparecerá en ninguna comparativa de rendimiento. Nos
interesa porque ataca nuestro mayor riesgo declarado, que es el mapping.

### Alternativa 1 — Sí, pero **empezando ya, en paralelo**, no después

Aquí sí nos separamos de vuestra propuesta. La planteáis como el paso posterior;
nosotros queremos arrancarla **desde el primer día**, solapada con las otras dos.

El motivo es que **esto es paper trading**: no hay dinero en juego, así que el
coste de tener el agente corriendo en modo sombra desde el minuto uno es un paso
más en el pipeline y nada más. En cambio, cada semana que esperamos es una semana
de datos que no tenemos.

Y los números lo respaldan: desde 2024 ha habido **5 episodios de caída superior
al 5 %** en unos 28 meses, o sea aproximadamente uno cada 5–6 meses. Si arrancamos
el modo sombra ya, hay probabilidad razonable de capturar un episodio de estrés
real —con corpus denso esta vez— en los próximos meses. Si esperamos a terminar
las otras pruebas, ese reloj empieza más tarde sin ninguna contrapartida.

---

## 3. P8. [NUEVA] ¿Se puede separar la capa de reglas de la votación del corpus?

Esta pregunta podría desbloquear buena parte de la validación histórica, y surge
directamente de vuestra respuesta a P5.

Nos disteis tres fuentes de valor:

1. **~15 reglas de conflicto jerárquico** (L1 > L3, L2 reduce confianza sin
   invertir dirección…) — **hardcodeadas en el motor**.
2. **Tabla de activación de módulos** (M3) — **determinista, un lookup**.
3. **508 reasoning steps + 231 invalidaciones** — **en el corpus**.

Las dos primeras **no dependen del corpus en absoluto**. Son lógica del motor. Lo
que se queda ciego sin frames es la tercera: qué categorías favorecer.

Pero una parte importante de lo que queremos —`risk_posture`, la postura de
riesgo— podría derivarse solo de las dos primeras. Es decir: con nuestro estado
macro de abril de 2025 (precio en breakdown, crédito ampliándose, volatilidad
extrema), la tabla de activación encendería `risk_management_invalidaciones`,
`volatilidad` y `credito_spreads_cds`, y las reglas jerárquicas resolverían la
dirección — **sin necesitar un solo frame**.

- **P8.a** ¿Es factible que el motor devuelva un `risk_posture` derivado **solo de
  la capa determinista** (activación de módulos + reglas de conflicto), marcado
  como tal y separado de la parte que sí usa frames?
- **P8.b** Si es factible: ¿tendría sentido operativo, o las reglas jerárquicas
  necesitan el peso de los frames para resolver la dirección y por sí solas no
  dicen nada?

**Por qué importa:** si la capa de reglas produce una postura de riesgo por sí
sola, podemos validarla sobre **toda la ventana 2024–2026, incluido el −18,8 % de
2025**, porque no depende de la densidad del corpus. Pasaríamos de una observación
a cinco episodios de estrés. Sería la diferencia entre una puerta de cordura y una
validación de verdad.

Si la respuesta es que no —que sin frames el motor no tiene criterio— también nos
vale saberlo: cerraría el debate y nos iríamos a forward testing con la conciencia
tranquila.

---

## 4. Reencuadre honesto de la Fase 1

Dado todo lo anterior, cambiamos cómo describimos la Fase 1, y queremos dejarlo
por escrito para que no se nos olvide dentro de tres meses:

| | Antes | Ahora |
|---|---|---|
| Naturaleza | Puerta de rendimiento | **Puerta de cordura** |
| Pregunta | "¿Bate el agente a las baselines?" | "¿Hay algo evidentemente roto?" |
| Puede concluir | Que el agente aporta valor | Que el agente **no** está roto |
| Validación real | La Fase 1 | **El forward testing, en meses** |

No es un fracaso del plan: es lo que permiten los datos disponibles. Preferimos
tener esto claro desde el principio a fabricar una validación que suene bien y no
signifique nada. Si en marzo alguien pregunta "¿esto está validado?", la respuesta
correcta será "está en validación hacia adelante desde agosto, con N episodios de
estrés capturados", no "pasó el backtest".

---

## 5. Resumen — qué necesitamos ahora

**Bloqueante:**

1. **P8.a/b** — si la capa determinista puede emitir `risk_posture` sin corpus.
   Es lo único que puede convertir la validación histórica en algo con muestra
   real.
2. Lo ya acordado: motor empaquetado, `as_of_date`, `regime_guidance`,
   `corpus_health` con `insufficient_corpus`.

**No bloqueante, pero útil:**

3. Confirmación de que la ventana feb–may 2026 es la de mayor densidad de frames
   que tenéis (32 fechados). Si hubiera otra ventana con cobertura comparable y
   algo de estrés que no hayamos detectado, decidlo.

Con eso arrancamos: mapping + Alternativa 2 + falsación (Alt 3) + modo sombra en
marcha. El orden real de trabajo por nuestra parte sería mapping primero, porque
las tres pruebas dependen de él.
