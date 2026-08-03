# Cava AI → AI Picks Lab — Nota breve antes de arrancar desarrollo

> No es una ronda nueva: el diseño está cerrado y estamos de acuerdo en todo.
> Son tres puntos operativos que surgen al empezar a picar código.

---

## 1. [BLOQUEA una parte] Enumeración cerrada de categorías de `regime_guidance`

En la Ronda 3 nos disteis ejemplos de categorías (`energy`, `real_assets`,
`technology`, `emerging_markets`, `equity_general`, `defensive`,
`duration_long`) y en la Ronda 4 añadisteis `unmapped_or_no_opinion` con
`healthcare`, `cannabis`, `defensive_consumption`.

Entendemos que eran **ilustrativos**. Necesitamos la **lista cerrada y definitiva**
de identificadores que `regime_guidance` puede emitir en cualquiera de sus cuatro
bloques (`favor_categories`, `avoid_categories`, `neutral_categories`,
`unmapped_or_no_opinion`).

**Por qué es importante y no es una formalidad:** el mapping tiene dos
direcciones. La primera (nuestro estado macro → vuestro vocabulario M1) está
completamente especificada y ya la estamos escribiendo. La segunda (vuestras
categorías → nuestros `theme`/`cluster`) es un diccionario literal de cadenas de
texto. Si vosotros emitís `commodities` y nosotros esperamos `real_assets`, **la
categoría se cae en silencio**: no hay error, simplemente ese tema deja de
recibir guía y nadie se entera.

Es exactamente el tipo de fallo que ya nos costó meses en este proyecto — dos
representaciones del mismo concepto que divergen sin avisar. Con la lista cerrada
lo convertimos en un test: cualquier categoría que llegue y no esté en el
diccionario provoca un fallo ruidoso, no un silencio.

Si la lista aún no está congelada, mandadnos la que tengáis y avisad cuando
cambie; lo importante es que exista una fuente única y que sepamos cuándo se
mueve.

---

## 2. [No bloquea] Aviso de un test de aceptación sobre `deterministic_risk_posture`

Cuando recibamos `v1.1.0` vamos a comprobar automáticamente esta invariante:

```
Mismo estado de mercado + as_of_date = 2024-08-15  →  deterministic_risk_posture = X
Mismo estado de mercado + as_of_date = 2026-08-15  →  deterministic_risk_posture = X   (idéntico)
```

Es decir: si la capa determinista es de verdad independiente del corpus, cambiar
`as_of_date` **no puede alterar su salida**. Solo debería cambiar
`regime_guidance` y `corpus_health`.

Os lo decimos **antes** de que lo construyáis, no después, para que la invariante
esté presente desde el diseño. Toda la Prueba 1C (la validación histórica sobre
2024–2026, incluido el −18,8 % de 2025) se apoya en que esto se cumpla: si
`deterministic_risk_posture` variase con la densidad del corpus, esa prueba
quedaría contaminada y volveríamos a quedarnos sin validación histórica.

No esperamos problemas — por lo que describís (`_l1_direction_from_inputs` y
compañía leen solo los inputs), debería cumplirse por construcción. Es una
comprobación de que sigue cumpliéndose, no una sospecha.

---

## 3. [No bloquea] Acceso al repositorio

Mencionasteis que avisaríais con el tag `v1.1.0` y el acceso. Cuando lo tengáis,
pasadnos la URL y el método de autenticación que prefiráis para el
`pip install git+...` desde GitHub Actions (probablemente un *deploy key* o un
token de solo lectura; lo que os resulte más cómodo de revocar).

---

## 4. Por dónde vamos nosotros

Arrancamos ya, sin esperar a `v1.1.0`:

- **Mapping dirección A** (nuestro estado macro → vocabulario M1) — en marcha. No
  depende de nada vuestro, M1/M2 está completo.
- **Reconstructor de estado histórico** — tenemos serie semanal desde 2005 con
  VIX (y sus deltas a 2 y 4 semanas), spread HY con dirección, curva, liquidez
  neta e indicadores de inflación. Cubre las dimensiones de volatilidad, crédito
  y liquidez casi directamente.
- **Mapping dirección B** (vuestras categorías → nuestros temas) — a la espera
  del punto 1.

Os pasaremos la muestra de calibración en cuanto la dirección A esté escrita:
"con el estado de mercado del 1 de agosto de 2026, esto es lo que hemos
codificado" — para que confirméis si refleja lo que diría Cava, tal como
acordamos en la Ronda 2.
