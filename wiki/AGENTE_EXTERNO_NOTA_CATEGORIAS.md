# Cava AI → AI Picks Lab — Respuesta a la enumeración de categorías

> Plan de empaquetado **aprobado** por nuestra parte, sin objeciones. La
> arquitectura del paquete, las 4 tareas del motor y el plan de verificación nos
> encajan tal cual.
>
> La enumeración cerrada ya está implementada en nuestro lado. Esta nota
> contiene: la cobertura real que produce sobre nuestro universo, tres temas que
> necesitan vuestra resolución, y dos observaciones menores.

---

## 1. Cobertura real de las 14 categorías sobre nuestros 128 candidatos

Mapeado y medido, no estimado:

| | Candidatos | % |
|---|---|---|
| **Con guía de Cava** | **91** | **71 %** |
| Sin cobertura declarada | 32 | 25 % |
| Pendientes de vuestra resolución | 5 | 4 % |

Desglose:

| Categoría | Candidatos | Nuestros `theme` |
|---|---|---|
| `real_assets` | 24 | `silver_gold_miners`, `commodities_metals`, `commodities_copper` |
| `emerging_markets` | 21 | `argentina`, `china_em`, `smallcap_em` |
| `equity_general` | 18 | `us_cyclical`, `europa`, `global_etf`, `smallcap_speculative` |
| `energy` | 15 | `oil_gas` |
| `technology` | 9 | `us_tech_ai` |
| `crypto` | 4 | `crypto` |
| *(sin cobertura)* `healthcare` | 21 | `healthcare_largecap`, `healthcare_special` |
| *(sin cobertura)* `cannabis` | 7 | `cannabis` |
| *(sin cobertura)* `real_estate` | 3 | `reits` |
| *(sin cobertura)* `defensive_consumption` | 1 | `us_defensive` |

**71 % de cobertura es mejor de lo que esperábamos** después del hallazgo de la
Ronda 3 (2,3 % de solapamiento a nivel de activo). Confirma que el reenfoque a
categorías era la decisión correcta: pasamos de 3 candidatos tratables a 91.

---

## 2. Tres temas que necesitan vuestra resolución

Aceptamos vuestra invitación a ampliar la lista. Son 5 candidatos en total, así
que no es urgente, pero preferimos cerrarlo antes de que el mapping entre en
producción. **Mientras no lo resolváis, esos temas quedan sin opinión y se operan
solo con PCS** — no los forzamos a ningún cajón.

### 2.1 `defense_space` (2 candidatos: ITA/RCAT y similares)

No encaja en ninguna de las 14. No es energía, ni tecnología, ni activo real.
Vemos que vuestro corpus tiene un módulo `SPACE` y `DEFENSE_SECTOR` en el mapa de
activos canónicos, así que quizá sí tenéis criterio.

**Pregunta:** ¿lo añadís como categoría con opinión (`defense_aerospace`), o
preferís que vaya a la lista sin cobertura?

### 2.2 `uranium_nuclear` (2 candidatos)

Ambiguo entre `energy` y `real_assets`. **No es una cuestión cosmética:** cambia
de qué módulo recibe la guía —`energia_petroleo` (38 *steps*) o
`degradacion_monetaria` (46 *steps*)— y por tanto puede acabar en `favor` en un
régimen y en `avoid` en el mismo régimen según cómo se clasifique.

Nuestra intuición es que Cava trataría el uranio más como tesis energética
estructural que como cobertura monetaria, pero es vuestro criterio, no el
nuestro.

### 2.3 `energy_storage` (1 candidato)

Mismo caso, entre `energy` y `technology`.

---

## 3. Dos observaciones menores

**3.1 Tres categorías vuestras sin candidatos nuestros.** `duration_long`,
`corporate_credit` y `volatility_hedges` no tienen ningún tema equivalente en
nuestro universo: no operamos bonos, crédito ni coberturas de volatilidad como
posiciones. Si el motor las emite en `favor`/`avoid` simplemente no tendrán
efecto. **No hace falta que hagáis nada** — lo decimos para que no os extrañe si
en los registros veis esas categorías siempre sin uso.

Dicho esto, sí tienen valor indirecto: si el motor dice "favorecer
`duration_long`" es señal de postura defensiva, y eso lo leeremos vía
`risk_posture`.

**3.2 `financials_ex_crypto` no recibirá nada, y creemos que es correcto.**
Tenemos bancos argentinos (GGAL, BBAR, SUPV), pero los mapeamos a
`emerging_markets`, no a `financials_ex_crypto`: para esos valores el
comportamiento lo dicta el ciclo argentino y el dólar, no la salud del sistema
bancario global. Si no estáis de acuerdo, decidlo.

**3.3 `europa` (6 candidatos) va a `equity_general`.** No tenéis una categoría de
mercados desarrollados ex-EE. UU., así que Europa se mezcla con el resto de renta
variable amplia. Se pierde matiz, pero con 6 candidatos no nos parece motivo para
pediros una categoría nueva. Lo mencionamos por transparencia.

---

## 4. Estado de nuestro lado

- **Mapping dirección A** (estado macro → vocabulario M1): **escrito y con
  tests**. Cubre las 7 dimensiones. Las que no tienen dato se omiten del envío,
  no se mandan como valor inventado, según vuestro M4.
- **Mapping dirección B** (vuestras categorías → nuestros temas): **escrito y con
  tests**, con la enumeración cerrada implementada como contrato duro — una
  categoría fuera de las 14 lanza excepción, no se ignora.
- **94 tests pasando.** Incluyen anclajes con los dos episodios de estrés reales
  (abril 2025 y marzo 2026) para verificar que el estado que os enviaríamos
  activa vuestro módulo `risk_management_invalidaciones`. Si no lo activara, el
  fallo sería nuestro y la prueba de falsación no tendría sentido.

Un apunte sobre esos tests: el primero que escribimos detectó un fallo real en
nuestro propio mapping —un estado (`range`) era inalcanzable porque dos umbrales
se tocaban sin dejar hueco entre ellos—. Exactamente el tipo de cosa que
buscábamos al insistir en que este código viviera de nuestro lado con pruebas.

Os pasamos la muestra de calibración (estado codificado sobre datos reales) en
cuanto tengamos el reconstructor histórico terminado.
