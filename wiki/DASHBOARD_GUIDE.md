# Market Tracker — Guía del Dashboard

## Flujo de decisión general

El sistema funciona en tres capas que se preguntan en orden:

```
1. ¿En qué entorno estamos?  →  MacroScore
2. ¿Dónde va el dinero?      →  Rotación
3. ¿Hay tensión acumulada?   →  Confluencia
```

Portfolio es el resultado histórico de aplicar este proceso sistemáticamente.

---

## Pestaña 1 — Resumen

**Es el panel de control diario.** No requiere entrar a ninguna otra pestaña si todo está en orden.

### Tarjetas superiores

| Tarjeta | Qué indica |
|---|---|
| `MacroScore` | Número de 0 a 100. Verde ≥70, amarillo 40-70, rojo <40 |
| `Régimen` | Etiqueta del momento: Bull Pleno / Bull Maduro / Transición / Bear |
| `COMPRA / ACUMULAR` | Cuántos activos tienen señal activa ahora mismo |
| `Rot. Temprana` | Señales de rotación que están arrancando (llegan antes que el precio) |

### Flags de alerta

Se muestran en rojo cuando están activos. Son señales de precaución que anulan o reducen la convicción de las señales de rotación:

| Flag | Qué significa |
|---|---|
| `Credit Complacency` | El crédito está demasiado tranquilo → sobreextensión del mercado |
| `Inflation Overlay` | La inflación distorsiona las señales → ser más cauto |
| `Term Premium Extreme` | Curva de tipos en posición extrema → mercado de bonos bajo estrés |
| `Emergency Mode` | Deterioro sistémico detectado → modo defensivo, reducir exposición |

### Gráficos mini

- **MacroScore 5 años** — contexto histórico rápido: ¿dónde estamos vs. el pasado?
- **Señales actuales** — grid con todos los activos ordenados por score.
- **Heatmap mini** — qué sectores han tenido calor en las últimas 52 semanas.
- **Portfolio mini** — la estrategia ganadora vs. SPY (curva de equity).

### Cuándo usarlo

Cada mañana antes de operar. Si MacroScore está en verde, régimen Bull y sin flags activos → contexto favorable. Si hay flags activos o el score baja de 55 → revisar las pestañas detalladas.

---

## Pestaña 2 — MacroScore

**Responde: ¿está el entorno macro a favor o en contra?**

### Gráfico principal — MacroScore con régimen

- Línea azul de 0 a 100 sobre toda la historia disponible.
- Bandas de color de fondo = régimen en cada período (verde=Bull Pleno, azul=Bull Maduro, amarillo=Transición, rojo=Bear).
- Líneas punteadas horizontales en 70, 55 y 40 = umbrales de régimen.
- Rangeslider abajo para hacer zoom en períodos concretos.

> **Clave:** mirar la dirección del score, no solo el nivel. Un 60 bajando es peor que un 55 subiendo.

### Gráfico de componentes (stacked area)

El MacroScore se construye sumando 5 indicadores:

| Componente | Máx. pts | Qué mide |
|---|---|---|
| HY Spread | 25 | Salud del crédito corporativo. Spread alto = miedo = quita puntos |
| Net Liquidity | 25 | Liquidez neta de la Fed (reservas − RRP − TGA). Más liquidez = más puntos |
| Volatilidad | 20 | VIX / condiciones de volatilidad. Calma = puntos, pánico = resta |
| CFNAI | 15 | Actividad económica real (Fed Chicago). Positivo = crecimiento |
| Curva de Tipos | 15 | Pendiente de la curva. Invertida = puntos negativos |

> **Clave:** si el score baja bruscamente, identificar qué componente lo provoca. Caída por volatilidad = corrección táctica. Caída por HY Spread + Net Liquidity = deterioro sistémico → actuar diferente en cada caso.

---

## Pestaña 3 — Rotación

**Responde: ¿en qué activos/sectores está entrando dinero ahora?**

### Heatmap 52 semanas

- Filas = activos (sectores ETF, materias primas, BTC, emergentes).
- Columnas = semanas, de más antigua (izquierda) a más reciente (derecha).
- Color: rojo=score 0, verde=score 10, gris=neutro (5).

> **Clave:** leer de derecha a izquierda. Un activo que pasa de rojo/gris a azul/verde en las últimas semanas = rotación entrante. Un activo verde muchas semanas = tendencia madura, mayor riesgo de estar llegando tarde.

### Señales actuales (grid de tarjetas)

Cada activo muestra:

| Elemento | Descripción |
|---|---|
| Score 0–10 | Momentum relativo vs. el universo de activos |
| `COMPRA` | Score ≥7. Señal fuerte, posición completa |
| `ACUMULAR` | Score 5–6. Construir posición progresivamente |
| `VIGILAR` | Score 3–4. En radar, no entrar aún |
| `IGNORAR` | Score <3. Sin señal |
| `⚡ ROT.TEMP` | Rotación temprana: el activo empieza a girar antes de que el precio lo confirme. Entradas de mayor calidad |
| Cluster | Categoría del activo (defensivo, cíclico, commodity, crypto...) |

### Combinación con MacroScore

| MacroScore | Señal rotación | Acción |
|---|---|---|
| ≥70 (Bull Pleno) | COMPRA | Máxima convicción — posición completa |
| 55–70 (Bull Maduro) | ACUMULAR | Construir posición parcial, esperar confirmación |
| 40–55 (Transición) | Cualquiera | Posición reducida, stops ajustados |
| <40 (Bear) | Cualquiera | Las señales de rotación no son fiables — no operar o solo hedges |

---

## Pestaña 4 — Portfolio

**Responde: ¿qué hace el sistema si se aplica mecánicamente? ¿merece la pena vs. comprar y mantener SPY?**

### Tarjetas superiores

Métricas de la mejor estrategia vs. SPY benchmark (período 2005–2026).

### Gráfico de equity (escala logarítmica, base 100)

- Cada línea = una estrategia backtestada desde 2005.
- Línea gris punteada = SPY buy & hold (benchmark de referencia).
- Escala log para que los períodos iniciales sean comparables con los recientes.

Estrategias actuales:

| Estrategia | CAGR | Sharpe | Max Drawdown | Nº trades (21 años) |
|---|---|---|---|---|
| `rot_temprana_pure` | 10.0% | 0.60 | −56.6% | 19 |
| `full_system` | 9.3% | 0.57 | −40.9% | — |
| SPY benchmark | 8.5% | 0.57 | −55.2% | — |

> **Clave:** el sistema no bate al SPY de forma espectacular en retorno, pero sí en perfil de riesgo en períodos de stress. `full_system` tiene un drawdown notablemente menor que SPY en crisis. Usar para calibrar expectativas, no para operar diariamente.

### Gráfico de métricas comparativas

CAGR, Sharpe y Max Drawdown por estrategia agrupados en barras — comparación visual rápida.

---

## Pestaña 5 — Confluencia

**Responde: ¿hay tensión acumulada suficiente para que algo se rompa?**

Esta pestaña es la **alarma temprana de giro de mercado**. El Confluence Score mide cuántas señales de deterioro coinciden simultáneamente.

### Gráfico Confluence Score

- Score de 0 a ~100.
- Históricamente, valores >25–30 han precedido correcciones relevantes.
- Tiene rangeslider para navegar la historia.

### Gráfico Macro vs. Sector tension

- Línea roja = tensión macro (HY spread acelerando, liquidez contrayéndose, volatilidad subiendo).
- Línea amarilla = tensión sectorial (cíclicos cayendo, defensivos subiendo, divergencias internas en SPY).
- Cuando ambas suben juntas = máxima alerta.

### Alertas recientes

Lista de eventos donde el sistema detectó confluencia suficiente. Cada alerta incluye:
- `dominant_component` — qué está dominando la señal de riesgo.
- `alert_type` — TACTICAL (corrección a corto) vs. STRUCTURAL (giro de ciclo).
- Componentes individuales A (macro) y B (sectorial) desglosados.

> **Referencia:** la última alerta fue el 13 de febrero 2026 con score 31, dominada por `defensive_strength` + `cyclical_deteri` — combinación clásica de giro bajista.

---

## Flujo de decisión semanal integrado

```
Cada lunes (revisión semanal):
│
├─ [Resumen] ¿MacroScore y régimen sin cambios relevantes?
│     │
│     ├─ Sí → ¿Hay señales ROT.TEMP nuevas esta semana?
│     │         └─ Sí → evaluar entrada (ver tabla combinación arriba)
│     │         └─ No → mantener posiciones
│     │
│     └─ No (score se movió >5 pts) → ir a MacroScore
│           └─ ¿Qué componente cambió?
│                 ├─ Solo Vol → corrección táctica, no cambiar posiciones
│                 └─ HY + Liquidity → ir a Confluencia
│
├─ [Confluencia] Si MacroScore bajó de 55:
│     ├─ Score >25 + alerta reciente → reducir exposición a cíclicos
│     └─ Score <20 → probablemente ruido, mantener
│
└─ Para nuevas entradas:
      Condición mínima: MacroScore ≥55 + señal COMPRA o ACUMULAR + sin flags activos
      Condición óptima: MacroScore ≥70 + ROT.TEMP + Confluencia baja + sin flags
```

---

## Señales de alerta que requieren acción inmediata

Cualquiera de estas condiciones requiere revisar el dashboard ese mismo día (no esperar al lunes):

1. Flag `Emergency Mode` activado.
2. MacroScore cae más de 10 puntos en una semana.
3. Confluence Score supera 30.
4. Régimen cambia a `Bear` o `Risk-OFF`.
5. Flags `Credit Complacency` + `Term Premium Extreme` activos simultáneamente.
