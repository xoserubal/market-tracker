# Stock Scanner — Acciones Individuales por Cluster

## Qué es

Módulo complementario a la estrategia rot_temprana_pure que busca **acciones individuales con alta beta, pequeña capitalización o alto apalancamiento financiero** dentro de los mismos clusters del sistema. Cuando un cluster ETF muestra ROT.TEMPRANA, el scanner identifica qué acciones concretas dentro de ese cluster tienen mayor potencial de amplificar el movimiento.

---

## Cómo funciona

El scanner reutiliza exactamente el mismo `RotationScore` del sistema principal, pero con **criterios relajados**:

| Parámetro | rot_temprana_pure | Stock Scanner |
|---|---|---|
| Score mínimo | 8/10 | 6/10 |
| Semanas consecutivas (streak) | 3 | 2 |
| Confirmación de cluster | Sí (≥2 ETFs) | No |
| Validación benchmark | Sí | No |
| Stop sugerido | −15% | −10% |
| Horizonte | 26 semanas | 8–13 semanas |

Calcula además:
- **Beta 52w** vs SPY (sobre retornos semanales)
- **Amplifier score** = beta × rot_score — ordena los candidatos por potencial de amplificación

### Señales producidas

| Señal | Condición | Acción |
|---|---|---|
| `⚡ CANDIDATO` | Cluster ETF con ROT.TEMPRANA activa + streak ≥ 2w | Entrada con máxima convicción |
| `EN_RADAR` | Streak ≥ 2w, cluster ETF sin señal todavía | Prepararse, monitorizar |
| `VIGILAR` | Score ≥ 6 pero streak < 2 | En radar, no entrar aún |
| `IGNORAR` | Score < 6 | Sin señal |

---

## Flujo operativo

### Paso 1 — Añadir o quitar acciones

Editar [backtest/config/individual_stocks.yaml](../backtest/config/individual_stocks.yaml):

```yaml
clusters:
  Growth:
    - ticker: NVDA
      note: "alta beta, líder semiconductores IA"
    - ticker: MSTR          # añadir una nueva
      note: "proxy bitcoin apalancado"

  Value/Cyclical:
    - ticker: FCX
      note: "minería cobre, alta beta, proxy ciclo global"
```

Campos por ticker:
- `ticker` — símbolo Yahoo Finance (obligatorio). Ejemplos: `NVDA`, `EWZ`, `GOLD`
- `note` — motivo de inclusión (opcional, aparece en el dashboard)

El pipeline descarga los datos automáticamente en la siguiente ejecución.

### Paso 2 — Generar los datos

```bash
cd c:\Users\Usuario\Dropbox\AI\market-tracker\backtest
python src/main_stocks.py
```

Esto:
1. Lee `config/individual_stocks.yaml`
2. Descarga datos frescos de Yahoo Finance para cada acción (omite si el archivo tiene < 12h de antigüedad)
3. Calcula RotationScore, beta y amplifier para cada acción
4. Cruza con los clusters que tienen ROT.TEMPRANA activa en `rotation_history.parquet`
5. Guarda resultado en `backtest/data/processed/stock_candidates.json`

### Paso 3 — Ver en el dashboard local

```bash
# Reiniciar el servidor si ya está corriendo
node server.js
```

Abrir `http://localhost:3000/rotacion.html` — al final de la página aparece la tabla **Acciones individuales — candidatos por cluster**.

---

## Archivos del módulo

| Archivo | Propósito |
|---|---|
| `backtest/config/individual_stocks.yaml` | Config editable por el usuario — añadir/quitar stocks aquí |
| `backtest/src/rotation/stock_scanner.py` | Motor: calcula score, beta, amplifier y señal por stock |
| `backtest/src/main_stocks.py` | Script de pipeline: descarga datos y genera el JSON |
| `backtest/data/processed/stock_candidates.json` | Output del scanner (no versionar) |
| `docs/data/stock_candidates.json` | Copia para GitHub Pages (generado por export_to_json.py) |
| `server.js` → `/api/stock-candidates` | Endpoint que sirve el JSON al dashboard local |
| `rotacion.html` → `StockCandidates` | Componente React que muestra la tabla |

---

## Automatización en GitHub Actions

El workflow `market-update.yml` ejecuta el scanner automáticamente en cada actualización (08:00 y 20:00 UTC):

```
Step 6: main_portfolio.py
Step 7: main_stocks.py        ← nuevo
Export: export_to_json.py     ← incluye export_stock_candidates()
```

Los datos llegan a `docs/data/stock_candidates.json` y quedan disponibles en el dashboard de GitHub Pages.

---

## Columnas del dashboard

| Columna | Descripción |
|---|---|
| **Ticker** | Símbolo Yahoo Finance |
| **Cluster** | Cluster al que pertenece (Growth, Value/Cyclical, etc.) |
| **Señal** | CANDIDATO / EN_RADAR / VIGILAR |
| **Score** | RotationScore 0–10 (mismo cálculo que el sistema ETF) |
| **Streak** | Semanas consecutivas con score ≥ 6 |
| **Beta 52w** | Beta vs SPY calculada sobre últimas 52 semanas. Rojo ≥ 1.8, naranja ≥ 1.3 |
| **Amplifier** | beta × score — mayor valor = mayor potencial de amplificación |
| **4w vs SPY** | Retorno 4 semanas relativo a SPY |
| **13w vs SPY** | Retorno 13 semanas relativo a SPY |
| **Nota** | Motivo de inclusión del YAML |

---

## Criterios de selección de stocks para el config

Al añadir acciones, buscar:

- **Alta beta** (> 1.3 vs SPY): amplifica el movimiento del sector
- **Pequeña/media capitalización**: mayor volatilidad, más recorrido potencial
- **Alto apalancamiento financiero**: en ciclos favorables actúa como multiplicador
- **Miners de commodities** (GOLD, NEM, SLB): leverage 2-3x al precio del subyacente
- **ETFs de países** dentro de Small/EM (EWZ, INDA): beta alta vs EEM

Evitar:
- Acciones con liquidez muy baja (volumen diario < $5M)
- Acciones sin historial suficiente (< 2 años de datos)
- Tickers que Yahoo Finance no reconoce

---

## Gestión de posiciones (quick trade)

Una vez identificado un `CANDIDATO`:

| Parámetro | Valor sugerido |
|---|---|
| Sizing | Equal weight del capital disponible para quick trades |
| Stop loss | −10% desde entrada (más ajustado que rot_temprana_pure) |
| Horizonte máximo | 8–13 semanas |
| Salida anticipada | Si el cluster ETF pierde la señal ROT.TEMPRANA |
| Salida anticipada | Si el régimen macro entra en Risk-OFF |

Estas posiciones son **independientes y complementarias** a las posiciones de rot_temprana_pure en ETFs. Gestionarlas con capital separado y sizing más pequeño dado el mayor riesgo idiosincrático.
