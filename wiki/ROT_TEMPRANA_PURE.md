# Rot Temprana Pure — Walkthrough Operativo

## Qué es esta estrategia

Detecta activos que están ganando fuerza técnica **antes de que el consenso los reconozca** como líderes del ciclo. No requiere que estén en fase con el régimen macro actual — los busca fuera de fase pero con momentum técnico creciente.

Es la estrategia con mayor alpha validado del sistema: **+7.3% en 13 semanas** desde la señal (mediana +6.3%, t-stat 2.77). Las señales COMPRA convencionales no tienen alpha estadístico significativo.

---

## Universo de activos

**Sectores (11):** XLK, XLC, XLY, XLF, XLI, XLB, XLE, XLV, XLRE, XLP, XLU  
**Índices (3):** QQQ, IWM, EEM  
**Renta fija:** TLT  
**Materias primas (3):** GC=F (oro), SI=F (plata), BZ=F (petróleo)  
**Crypto:** BTC-USD

---

## Cuándo mirar el sistema

**Solo los viernes.** El sistema actualiza señales semanalmente. No hay nada que hacer entre semana salvo monitorizar el stop-loss manualmente.

---

## Paso 1 — Revisar el régimen macro

En la página principal del dashboard, ver el **MacroScore y Régimen**:

| Régimen | Qué hacer |
|---|---|
| Bull Pleno / Bull Maduro | Operar con normalidad — buscar ROT.TEMPRANA |
| Transición | Operar con cautela — posiciones reducidas |
| Risk-OFF / Capitulación | **Modo defensivo** — ver sección final |

Si el régimen es favorable, continuar al paso 2.

---

## Paso 2 — Buscar señales ROT.TEMPRANA

En la pestaña **Rotación**, buscar el badge `⚡ ROT.TEMP` en cualquier activo.

**Si no hay ninguno → no hacer nada.** El capital sin invertir se aparca en SPY.

### Cómo genera el sistema la señal ROT.TEMPRANA

Las tres condiciones deben cumplirse simultáneamente (el sistema las valida automáticamente):

**1. Score técnico ≥ 8/10 durante 3 semanas consecutivas**

El score (0-10) mide:

| Bloque | Pts | Indicadores |
|---|---|---|
| Momentum relativo | 4 | Retorno 13 sem vs SPY >2% · Retorno 4 sem vs SPY >1% · Precio > SMA200 |
| Flujo de dinero | 3 | CMF(20) > 0 · OBV > SMA50(OBV) · Volumen 4 sem / 12 sem > 1.10 |
| Técnico | 3 | MACD histogram > 0 · RSI(14) entre 40-70 · Precio > SMA20 y no sobreextendido |

**2. Confirmación de cluster** — al menos otro activo del mismo grupo también cumple la condición 1:

| Cluster | Activos |
|---|---|
| Growth | XLK, XLC, XLY, QQQ, BTC-USD |
| Value/Cíclico | XLF, XLI, XLB, XLE |
| Defensivo | XLP, XLU, XLV, XLRE |
| Commodities | GC=F, SI=F, BZ=F |
| Small/EM | IWM, EEM |
| Duration | TLT (solo — nunca activa el cluster) |

**3. Mercado no en pánico** — SPY > SMA200 o la liquidez neta creció >$300B en 13 semanas.

---

## Paso 3 — Entrada (BUY)

Cuando aparece ROT.TEMPRANA:

1. **Entrar ese viernes** (o el lunes siguiente como máximo)
2. **Sizing:** dividir el capital disponible entre el número de señales nuevas — equal weight
3. El capital que no se invierte se mantiene en **SPY**

> Ejemplo: tienes $100k en SPY y aparecen 2 señales ROT.TEMPRANA → $50k en cada activo, vendes $100k de SPY.

---

## Paso 4 — Gestión de posiciones abiertas

Cada viernes revisar las posiciones y cerrar si se cumple alguna condición:

| Condición de salida | Acción |
|---|---|
| Precio cayó **−15%** desde la entrada | Cerrar — stop loss duro |
| Han pasado **26 semanas** desde la entrada | Cerrar — tiempo máximo de holding |
| La señal cambia a **ACUMULAR\*** (emergencia) | Cerrar |
| El régimen entra en **Risk-OFF o Capitulación** | Cerrar todas las posiciones no defensivas |

Si no se cumple ninguna condición → **no tocar la posición.**

---

## Paso 5 — Modo Risk-OFF (si ocurre)

Si el MacroScore entra en Risk-OFF o Capitulación:

1. Cerrar todas las posiciones de rot temprana
2. Rotar a la cesta defensiva: **TLT, XLU, XLP, GC=F** (equal weight)
3. Esperar a que el régimen se normalice antes de volver a buscar ROT.TEMPRANA

> Nota: el sistema detecta Risk-OFF con retraso histórico (~350 días en 2008, no detectó el COVID por la recuperación en V). Cuando llega la señal, la protección es real (+20% alpha en 13 semanas) pero hay que asumir que llega tarde.

---

## Lo que se ignora en esta estrategia

- Señales **COMPRA, ACUMULAR, VIGILAR** → sin alpha estadístico
- Noticias, earnings, sentimiento → el sistema ya los filtra vía score técnico
- Rebalanceo de posiciones abiertas → una vez dentro, no se ajusta el tamaño hasta la salida
- Régimen macro como filtro de entrada → ROT.TEMPRANA ignora el régimen (es su ventaja)

---

## Rendimiento histórico (2005–2026)

| Métrica | Rot Temprana Pure | SPY |
|---|---|---|
| CAGR | 9.95% | 8.51% |
| Sharpe | 0.60 | 0.57 |
| Max Drawdown | −56.6% | −55.2% |
| Nº de operaciones (21 años) | ~19 | — |
| Lead time vs señal COMPRA | +21 semanas de antelación | — |

El número de trades es muy bajo (~1 por año) — es una estrategia de **paciencia**, no de actividad.

---

## Resumen operativo

```
CADA VIERNES:

1. ¿Régimen = Risk-OFF?
   → Sí: rotar a defensivos (TLT, XLU, XLP, GC=F)
   → No: continuar

2. ¿Hay señal ROT.TEMPRANA nueva?
   → Sí: entrar con equal weight del capital disponible
   → No: no hacer nada

3. ¿Alguna posición abierta cumple condición de salida?
   (-15% || 26 semanas || ACUMULAR* || Risk-OFF)
   → Sí: cerrar esa posición, aparcar en SPY
   → No: mantener sin tocar

Capital sin invertir → siempre en SPY como posición por defecto.
```
