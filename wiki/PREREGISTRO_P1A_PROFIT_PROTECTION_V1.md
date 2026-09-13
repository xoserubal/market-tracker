# Preregistro — P1A: `PROFIT_PROTECTION_V1`

**Fecha de firma:** 2026-09-13
**Autor:** usuario + Claude (implementación de §3 de la Hoja de ruta consolidada)
**Fuente:** `Hoja de ruta consolidada — Auditoría de carteras IA`, v1.2 (FINAL —
arquitectura congelada), firmada 2026-08-30, §3 + §1.1 + §2 + §13.
Documento externo, no commiteado en el repo (por diseño). Este preregistro
reproduce literalmente los apartados relevantes.

> Cláusula de congelación de arquitectura (§14): con la firma de la v1.2 se
> cerró la fase de diseño del programa completo. Este preregistro no reabre
> esa discusión — solo instancia P1A tal como quedó fijado.

---

## 0. Motivación por qué se construye ahora, no cuando dispare el contador

`p1_readiness_monitor.py` cuenta cierres reales en `ai_picks.json` hacia el
umbral de §3 (≥40 cierres/≥30 eventos) **independientemente de si existe
código shadow que lo evalúe**. Si P1A no se construyera hasta que ese
contador avise, el aviso llegaría a un log vacío — y desde ahí habría que
esperar otros 3-6 meses para tener muestra real de los brazos. La hoja de
ruta ya lo decía en §1: *"P1A, P1B y P1C corren en paralelo (todas shadow,
ninguna toca producción)"* — desde la firma (2026-08-30), no desde que se
cumpla el umbral. Este preregistro se firma con **2 semanas de retraso**
respecto a esa fecha; se ejecuta backfill retroactivo sobre las filas de P0
ya existentes para no perder esas 2 semanas.

---

## 1. Hipótesis (§0/§3, literal)

Un trailing stop de protección de ganancias, superpuesto al suelo de PCS
(solo puede **adelantar** la salida, nunca sustituir al control), mejora el
retorno del libro sin dañar el mandato de acompañamiento de flujo.

---

## 2. Ámbito (§3, literal)

Shadow sobre `HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS, EARLY_ROTATION,
MACRO_THEMATIC_BENEFICIARIES, CAVA_MACRO`. `MIRROR_ESPEJO` excluida (ya
tiene su propio mecanismo y es su propio experimento, P6).

Importado de `p1_readiness_monitor.P1A_P1C_SCOPE` en
`p1a_profit_protection_v1_shadow.py` — mismo ámbito exacto que P1C y que el
contador que decide cuándo hay "primera lectura".

---

## 3. Los dos brazos (§3, literal — especificación ATR corregida en ronda 4/V1.2)

- **Brazo FIXED (baseline candidato):** armado al alcanzar **+10%** no
  realizado desde entrada (MFE, sobre cierres); una vez armado, EXIT shadow
  si el cierre cae **≥8%** desde el máximo de cierre de la tenencia.
  *Declaración de sesgo (literal de §3): estos parámetros salen de una
  parrilla mirada in-sample en la auditoría de 2026-08-30 (H3). Congelados,
  no se reoptimizan con los datos de este experimento.*
- **Brazo ATR (challenger):** todo en unidades de precio absoluto:
  - *Armado:* MFE en precio ≥ 2.5·ATR(14)_entry — ATR congelado el día de
    entrada (nunca recalculado más tarde).
  - *Trailing:* ratchet monótono. En cada nuevo `running_high`, se captura
    `ATR_high` (el ATR14 de ESE día) y se calcula `candidato = running_high
    − 2.0·ATR_high`; `Stop_t = max(Stop_{t-1}, candidato)`. El stop puede
    subir con cada nuevo máximo; **nunca baja**, aunque el ATR se expanda
    en una caída posterior (esta es la corrección de V1.1→V1.2: un ATR
    móvil recalculado cada día aflojaría el stop justo cuando debe
    proteger).

Ninguno de los dos brazos toca `ai_picks.json` ni cierra nada real.

---

## 4. ATR de entrada — fuente de datos (decisión de implementación)

El ATR congelado en la fecha de entrada (`atr_entry`) se calcula con un
fetch dedicado a yfinance (`scripts/p1_entry_snapshot.py`, compartido con
P1C y P1B), no leyendo el `ATR` del primer día capturado por P0. Motivo: P0
solo empezó a capturar el 2026-08-30 — para posiciones abiertas **antes**
de esa fecha (p. ej. TMO, entrada 2026-07-25), el primer valor de P0 sería
el ATR de agosto, no el de la entrada real. El fetch dedicado calcula el
ATR14 exactamente al cierre de `entry_date`, sin este sesgo, para cualquier
posición sin importar cuándo entró.

Cacheado por posición en `docs/data/p1_entry_snapshot_cache.json` — un solo
fetch por posición, nunca se repite.

---

## 5. Métricas (§3, literal)

- **Trade-level (diagnóstico, implementado aquí):** expectancy, mediana,
  MFE capture ratio (retorno realizado / MFE), MAE, % de operaciones
  empeoradas vs regla real, pérdidas de cola (p10).
- **Portfolio-level (decisivo para promoción, DIFERIDO — ver §8):**
  `excess_CAGR_calendar` sobre libros shadow prospectivos
  (`PORTFOLIO_CONTROL`, `PORTFOLIO_P1A_FIXED`, `PORTFOLIO_P1A_ATR`), max
  drawdown, Sortino, exposición media, turnover.

---

## 6. Criterio de éxito (§3, literal — doble n de §1.1)

Sobre **≥40 episodios cerrados nuevos post-firma Y ≥30 eventos
independientes** (`event_id = ticker+entry_date`) en el ámbito de §2, por
brazo:

- `excess_CAGR_calendar` del libro shadow ≥ libro control + margen que
  cubra fricción estimada.
- Retorno medio trade-level ≥ regla actual + 1pp.
- ≤10% de episodios empeorados en >5pp.
- Max drawdown no peor que el control en >2pp.

**Cláusula de resultado no concluyente:** si a los 40 episodios ninguna
condición se resuelve con claridad, se acumulan otros 40 sin modificar
parámetros.

**Cláusula de potencia calendario:** si a 90 días de la firma (2026-11-28)
no se han acumulado 40 episodios cerrados nuevos, no se cambia ningún
parámetro; se publica un informe intermedio con el n alcanzado y se alarga
el plazo. Con las posiciones vivas actuales (24 en el ámbito de P0/P2), es
razonable esperar que P1A necesite 4-6 meses, no 3 — aceptado en la firma.

**Cláusula de acta (H3):** el overlay +10/8 es candidato baseline in-sample
que tocó ~13% de episodios en la auditoría original; no se cita como
estimación del alfa esperable.

---

## 7. Implementación

- `scripts/p1a_profit_protection_v1_shadow.py` — evalúa los 2 brazos cada
  día sobre las filas de P0 en ámbito, append-only, dedup por
  `(position_id, date)`. `--report` resume disparos por brazo.
- `scripts/p1_entry_snapshot.py` — helper compartido (ATR_entry).
- Salida: `docs/data/p1a_profit_protection_v1_shadow.jsonl`.
- Pipeline: Step 10i3, justo después de Step 10i2 (P2). `continue-on-error: true`.
- **No se modifica** `ai_picks_decision_state.py`, `paper_trading.py`,
  `cava_portfolio.py` ni ninguna cartera real.

---

## 8. Explícitamente diferido en esta v1

- **Libros shadow prospectivos a nivel cartera** (`PORTFOLIO_CONTROL`,
  `PORTFOLIO_P1A_FIXED`, `PORTFOLIO_P1A_ATR`) — construir un simulador de
  cartera virtual completo (sizing, slippage, tratamiento de cash, reglas
  de reentrada, todo "congelado antes de empezar") es una pieza de
  infraestructura bastante mayor que el shadow signal-level ya
  implementado. La propia hoja de ruta admite despliegue en fases
  ("control + 2 brazos P1A desde la firma; los libros de P1C/P2 en cuanto
  la infraestructura esté probada") — se construye cuando haya evidencia
  trade-level de que vale la pena, o cuando el usuario lo priorice.
  Mientras tanto, las métricas trade-level (§5) sí se pueden calcular sobre
  el log ya acumulado en cualquier momento.
- Combinación con precedencia P1A/P1C/P2 (§6.1) — pendiente de que los tres
  shadows tengan suficiente historial propio.

---

## 9. Verificado (2026-09-13)

Backfill retroactivo sobre las 15 sesiones ya capturadas por P0
(2026-08-30→2026-09-13): 197 filas, 24 posiciones. `atr_entry` obtenido con
éxito para todas las posiciones vía el fetch dedicado (TMO: 17.25;
HIMS: 2.15). Casos con disparo real hasta ahora: control (regla 13 real) 1/24;
brazo FIXED 1/24; brazo ATR 1/24 — la misma posición (`SEDANA.ST`, suelo
absoluto de PCS), consistente con lo esperado dado que ningún ticker en
ámbito ha alcanzado todavía el +10% de MFE necesario para armar ninguno de
los dos brazos de protección de ganancias.
