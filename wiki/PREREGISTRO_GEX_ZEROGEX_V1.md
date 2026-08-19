# Preregistro — Piloto ZeroGEX / calibración DIY de SPX gamma flip (v1)

**Fecha de congelación: 2026-08-19, antes de contratar el trial de ZeroGEX
y antes de ver ningún dato en vivo del proveedor.**

Origen: `duration.html` necesitaría saber el posicionamiento de gamma de los
dealers para calibrar la fuerza de la tesis de estrés de duración. Piloto
DIY previo (`research/gex_monitor_pilot/`, 2026-08-18) implementó el cálculo
(Black-Scholes sobre OI de `^SPX` vía yfinance) pero no encontró ninguna
fuente gratuita verificablemente en vivo contra la que contrastarlo — no se
integró. Se identificó ZeroGEX (`api.zerogex.io`) como proveedor de pago con
API documentada (OpenAPI 3.1, campos `spot`/`as_of`/`age_seconds`/
`gamma_flip`/`call_wall`/`put_wall`/`max_pain` en `GET /api/v1/levels/{symbol}`).
Revisado por un asesor externo (plan de 3 fases); este documento congela las
definiciones que el plan del asesor dejaba sin fijar, antes de ejecutar nada.

**Objetivo de v1: decidir si ZeroGEX sirve como fuente temporal de verdad
para calibrar el cálculo DIY, y si el DIY calibrado puede sustituirlo. No es
un test de generación de alfa — es una validación de instrumentación.**

---

## 0. Correcciones sobre el plan del asesor, incorporadas aquí

1. **Choque de calendario Fase 1 (7 días trial) vs Fase 2 (10-20 sesiones +
   idealmente VIX expiry/monthly OpEx).** El trial no alcanza. Si Fase 1
   pasa, se contrata Fase 2 con **tope duro de 2 meses de pago ($58)**,
   decidido explícitamente con el usuario 2026-08-19 — sin renovación
   automática pasado ese tope sin volver a preguntar. Objetivo de fechas:
   cruzar el monthly OpEx (~2026-09-18, 3er viernes) y el VIX expiry
   (~2026-09-16, miércoles previo).
2. **Estados de régimen con umbrales exactos, fijados aquí antes de mirar
   datos** (el plan del asesor los nombraba sin definir la banda de
   "transition" — ver sección 3).
3. **Cadencia de Fase 2 explícita.** El OI de opciones que alimenta tanto
   nuestro DIY como (presumiblemente) ZeroGEX se actualiza a nivel de sesión,
   no intradía — muestrear cada 15-30 min en Fase 2 solo repetiría el mismo
   OI con un spot distinto. Fase 2 usa **1 snapshot/día, cerca del cierre
   (15:50-16:00 ET)**, no la cadencia de Fase 1.
4. **`regime_agreement_rate` se calcula sobre el mismo spot de mercado real
   para DIY y ZeroGEX** (nunca el spot que reporta cada proveedor) — aísla
   la comparación a la diferencia real de `gamma_flip`, sin que la
   clasificación de régimen quede contaminada por qué spot usa cada fuente.
5. **Cadencia de re-validación si se cancela la suscripción**: cada 6 meses,
   1 semana de resuscripción, mismo protocolo de Fase 2 en miniatura.
6. **Alcance ampliado a SPX + QQQ** (decidido 2026-08-19, "ya puestos" — coste
   marginal de una llamada extra por ciclo). Cada símbolo se evalúa y falla/pasa
   Fase 1 y Fase 2 **de forma independiente** — que uno falle no descarta el otro.
7. **Automatización vía GitHub Actions, no tarea local de Windows** (decidido
   2026-08-19, tras plantear inicialmente Task Scheduler local). A diferencia
   de la rama IBKR descartada (necesita TWS/Gateway con sesión persistente,
   inviable en un runner efímero), ZeroGEX es una llamada HTTPS simple con
   API key — sin obstáculo técnico para correr en la nube, igual que el resto
   de integraciones del pipeline (Form4API, Koncorde, etc.). Workflow propio
   (`.github/workflows/gex-zerogex-fase1.yml`), separado de `market-update.yml`,
   con su propio cron — se borra (workflow + secret `ZEROGEX_API_KEY`) al
   terminar el piloto.

---

## 1. Fase 1 — Provider quality (durante el trial de 7 días)

**Símbolos: SPX y QQQ**, evaluados de forma independiente (ver 0.6).

**Endpoint:** `GET /api/v1/levels/{symbol}` (`Authorization: Bearer <ZEROGEX_API_KEY>`),
una llamada por símbolo por ciclo. Cruce opcional con `GET /api/gex/summary?symbol={symbol}`
como verificación interna de consistencia (misma fuente, dos rutas).

**Cadencia:** cada 20 minutos durante RTH (09:30-16:00 ET), días de mercado
reales dentro de la ventana del trial. Automatizado vía GitHub Actions
(`.github/workflows/gex-zerogex-fase1.yml`, cron `*/20 13-20 * * 1-5` UTC —
el script se auto-limita a RTH real en hora ET, el cron solo necesita cubrir
la ventana con margen) — corre en la nube, no depende de que el PC del
usuario esté encendido (ver 0.7).

**Cross-check de spot:** `^GSPC` (SPX) / `QQQ` (QQQ) intradía vía yfinance,
barra más cercana al `as_of` del proveedor (tolerancia de emparejamiento: ±2 min).

**Métricas por snapshot:**
- `spot_diff_bps = |spot_provider − spot_market| / spot_market × 10000`
- `is_stale = age_seconds > 180`

**Criterio de fallo — evaluado por símbolo. Descartar ese símbolo de
inmediato si CUALQUIERA se cumple, en cualquier sesión:**
- `p90(spot_diff_bps)` de la sesión `> 10 bps`
- `>20%` de los snapshots del trial con `is_stale=true`
- `as_of` no avanza entre snapshots consecutivos durante RTH (dato
  congelado/cacheado — el mismo síntoma que descartó el dashboard gratuito
  de FlashAlpha)

Si **ambos** símbolos fallan → cancelar el trial entero, documentar el
hallazgo (mismo tratamiento que `research/gex_monitor_pilot/HALLAZGOS.md`),
no gastar el presupuesto de Fase 2. Si solo uno falla, se sigue a Fase 2
únicamente con el símbolo que pasó.

---

## 2. Fase 2 — Calibración DIY (solo si Fase 1 pasa, por símbolo)

**Símbolos:** SPX y QQQ, cada uno calibrado y evaluado por separado — nunca
se pooolean sus métricas (2.2) en una sola cifra.

**Cálculo DIY:** se reutiliza literalmente `research/gex_monitor_pilot/gex_pilot.py`
(import directo, no reimplementación), llamado con `--ticker ^SPX` y
`--ticker QQQ` respectivamente — la metodología no se modifica a mitad de la
calibración, para no mover la meta.

**Cadencia:** 1 snapshot/día por símbolo, 15:50-16:00 ET (ver punto 0.3).

**Duración objetivo:** mínimo 10 sesiones, hasta 20 si el calendario de pago
lo permite, cubriendo si es posible VIX expiry (~2026-09-16) y monthly OpEx
(~2026-09-18).

**Spot de referencia único para clasificar régimen:** cierre de `^GSPC`
(SPX) / `QQQ` (QQQ) de esa sesión (yfinance), usado tanto para DIY como para
ZeroGEX de ese símbolo.

### 2.1 Estados de régimen (frozen)

```
distance_to_flip_pct = (market_spot − gamma_flip) / market_spot × 100   (con signo)

positive_gamma:  distance_to_flip_pct >= +0.5%
negative_gamma:  distance_to_flip_pct <= -0.5%
transition:      -0.5% < distance_to_flip_pct < +0.5%
uncertain:        gamma_flip ausente, spot ausente, o snapshot marcado
                   is_stale=true en cualquiera de las dos fuentes ese día
```

Banda de 0.5% elegida por orden de magnitud del propio piloto DIY (el flip
calculado el 2026-08-18 quedó a ~0.1% de una fuente externa; el spot cruzó
esa zona en movimientos de ~0.5-1% en 3 sesiones) — no calibrada contra
rendimiento, es una banda de "cerca del borde, régimen inestable".

### 2.2 Métricas (definiciones exactas)

- `median_abs_flip_diff` = mediana(`|DIY_flip − ZeroGEX_flip|`) en puntos,
  sobre sesiones con dato válido en ambas fuentes.
- `p90_abs_flip_diff` = percentil 90 de lo mismo.
- `regime_agreement_rate` = % de sesiones con `bucket(DIY) == bucket(ZeroGEX)`
  (usando el spot de mercado único, sección 2.1), sobre sesiones donde
  ninguna de las dos fuentes es `uncertain`.
- `near_flip_agreement` = de las sesiones donde AL MENOS una fuente clasifica
  `transition`, % en que la otra fuente no cae en el lado opuesto claro
  (`positive_gamma` vs `negative_gamma`) — separa desacuerdos de borde
  (esperables, banda estrecha) de desacuerdos de régimen real.
- `bias_stability` = serie de (`DIY_flip − ZeroGEX_flip`) con signo +
  desviación estándar; se reporta la serie completa, no solo un número —
  con n=10-20 no tiene sentido fijar un umbral rígido de "estable", se
  reporta y se interpreta a ojo junto al usuario.

### 2.3 Criterio de decisión (del asesor, aplicado con los umbrales de 2.2)

**Aplicado independientemente a SPX y a QQQ** — es perfectamente posible que
el veredicto difiera entre los dos (p. ej. DIY calibra bien en SPX pero no en
QQQ, cuya cadena de opciones es distinta en composición de OI).

- **`regime_agreement_rate >= 85%` Y `bias_stability` sin tendencia clara de
  deriva** → calibración pasa para ese símbolo. Si pasa en ambos, cancelar
  ZeroGEX del todo; si pasa solo en uno, evaluar con el usuario si vale la
  pena mantener la suscripción solo por el símbolo que no calibró. Re-validar
  cada 6 meses (1 semana de resuscripción, mismo protocolo en miniatura).
- **DIY no replica pero ZeroGEX pasó Fase 1 (fresco/fiable) para ese
  símbolo** → decisión de juicio con el usuario: mantener suscripción como
  fuente externa continua para ese símbolo, o descartarlo.
- **ZeroGEX no pasa Fase 1 para ese símbolo** → descartar ese símbolo, no
  llega a Fase 2.

---

## 3. Fase 3 — Integración (solo si Fase 2 concluye con veredicto de uso)

Campos (del plan del asesor, sin cambios): `spx_spot`, `gamma_flip`,
`distance_to_flip_pct`, `dealer_gamma_regime`, `call_wall`, `put_wall`,
`max_pain`, `source`, `as_of`, `age_seconds`, `stale_warning`,
`diy_gamma_flip`, `diy_vs_provider_diff`.

**Ubicación (decidir en el momento, no ahora):** sección nueva dentro de
`duration.html` vs página nueva dedicada — depende de si Fase 2 concluye que
hace falta mostrar ambas series (DIY + ZeroGEX en paralelo, si se mantiene
la suscripción) o solo una (si se cancela y se usa DIY en solitario).

**No se toca CLAUDE.md como "implementado" hasta que Fase 3 esté realmente
en un dashboard** — Fases 1 y 2 son investigación (`research/`), mismo
criterio que el resto de pilotos de este proyecto.

---

## 4. Presupuesto y tiempo autorizado

- Trial: 7 días, gratis.
- Fase 2: **tope duro de 2 meses de pago, $58 total**, decidido con el
  usuario 2026-08-19. Si a los 2 meses Fase 2 no ha concluido veredicto
  (datos insuficientes, API caída, etc.), se cancela y se reevalúa —
  no se renueva sin volver a preguntar.
- Re-validación futura (si DIY gana): 1 semana de resuscripción cada 6 meses.

## 5. Qué NO se hace (idéntico al plan del asesor, sin recortes)

No tocar PCS. No tocar carteras. No usar como señal BUY/SELL. No integrar
0DTE imbalance/squeeze/trap/Market Pressure Index. No usar GEX de ticker
individual hasta evaluar cobertura del universo de AI Picks Lab (sospecha
fundada de que no cubre small/microcaps, mismo patrón que Cava — sin
verificar, no se usa). No asumir que el DIY es válido si falla específicamente
cerca del flip (la zona donde el signo es más sensible al ruido).

## 6. Salidas esperadas

Todas bajo `research/gex_zerogex_pilot_v1/` (fuera de rutas productivas),
más el workflow de automatización:

- `.github/workflows/gex-zerogex-fase1.yml` — cron cada 20 min RTH, borrar
  al terminar el piloto
- `fetch_zerogex_snapshot.py` — colector Fase 1, SPX + QQQ
- `outputs/fase1_snapshots.jsonl`
- `outputs/fase1_informe.md` — veredicto de Fase 1 por símbolo (pasa / cancela)
- `run_diy_calibration.py` — colector Fase 2 (importa `gex_pilot.py`,
  cadencia 1/día EOD, SPX + QQQ)
- `outputs/fase2_calibration.jsonl`
- `outputs/fase2_informe.md` — métricas de la sección 2.2 + veredicto de
  la sección 2.3, por símbolo

## 7. Puerta dura antes de Fase 3

Tras leer `outputs/fase2_informe.md`, se decide explícitamente entre usuario
y Claude Code: (a) cancelar y usar DIY, (b) mantener suscripción como fuente
externa, o (c) descartar el módulo entero. Ninguna integración en dashboard
se implementa sin esa decisión.
