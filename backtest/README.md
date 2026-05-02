# Market Tracker v2 — Backtest

Pipeline de datos históricos para validar empíricamente el protocolo
de flujos de capital del Market Tracker v2.

## Estructura

```
backtest/
├── data/
│   ├── raw/                  # Descargas brutas por serie
│   ├── processed/            # Datasets consolidados y alineados
│   │   ├── prices_weekly.parquet
│   │   ├── macro_daily.parquet
│   │   └── macro_weekly.parquet
│   ├── manifest.json         # Metadata de la última descarga
│   └── fetch.log             # Log de la última ejecución (con --log-file)
├── src/
│   ├── fetchers/
│   │   ├── yahoo.py          # Descarga Yahoo Finance (activos, VIX, DXY)
│   │   └── fred.py           # Descarga FRED (macro series)
│   ├── processors/
│   │   └── alignment.py      # Alineación temporal y cálculo de NetLiq
│   └── main.py               # Orquestador del pipeline
├── config/
│   └── series.yaml           # Lista y configuración de todas las series
├── .env.example              # Plantilla de variables de entorno
├── requirements.txt
└── README.md
```

## Configuración del entorno

### 1. Crear entorno virtual

```bash
cd backtest
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar la API key de FRED

FRED requiere una clave de API gratuita:

1. Regístrate en https://fred.stlouisfed.org/docs/api/api_key.html
2. Copia `.env.example` como `.env`:
   ```bash
   cp .env.example .env
   ```
3. Edita `.env` y reemplaza `your_key_here` con tu clave:
   ```
   FRED_API_KEY=abc123def456...
   ```

## Ejecución

```bash
# Desde el directorio backtest/
python src/main.py

# Con log a fichero:
python src/main.py --log-file
```

El pipeline descarga ~24 series (20 activos + 4 índices + 9 FRED),
procesa los datos y genera los 3 archivos en `data/processed/`.

**Primera ejecución:** ~5-15 minutos (dependiendo de la conexión).
**Actualizaciones posteriores:** re-ejecutar `main.py` sobrescribe los datos.

## Outputs generados

| Archivo | Descripción | Columnas |
|---------|-------------|----------|
| `prices_weekly.parquet` | Cierres semanales (viernes) de los 20 activos + VIX + DXY | 24 columnas, índice = viernes |
| `macro_daily.parquet` | Series FRED diarias con ffill ≤5 días | 6 columnas (HY, curva, T5YIE, DFII10, TermPremium, RRPONTSYD) |
| `macro_weekly.parquet` | WALCL, WTREGEN, CFNAI, RRPONTSYD + NetLiq calculado | 5 columnas, índice = viernes |

### Net Liquidity

```
NetLiq = WALCL - RRPONTSYD - WTREGEN  (en USD millions)
```

Para obtener USD billions: `macro_w["NetLiq"] / 1000`

## Verificación rápida

```python
import pandas as pd

prices = pd.read_parquet('data/processed/prices_weekly.parquet')
macro_d = pd.read_parquet('data/processed/macro_daily.parquet')
macro_w = pd.read_parquet('data/processed/macro_weekly.parquet')

print(f"Precios semanales: {prices.shape}, rango {prices.index.min()} a {prices.index.max()}")
print(f"Columnas: {list(prices.columns)}")
print(f"NaN por activo:\n{prices.isna().sum()}")

print(f"\nMacro diario: {macro_d.shape}")
print(f"Macro semanal (incl. NetLiq): {macro_w.shape}")
print(f"NetLiq últimas 5 semanas (Mtons USD):\n{macro_w['NetLiq'].tail()}")
```

## Known methodological limitations

### HY Spread (BAMLH0A0HYM2) — indisponibilidad historica y proxy fallido

**Situacion:** La serie BAMLH0A0HYM2 (ICE BofA US High Yield Index OAS) esta disponible
en FRED solo desde 2023-04-18 (ventana rolling de 3 anos, impuesta por licencia de ICE Data).

**Investigacion empirica realizada:**

1. **Truncacion FRED:** los metadatos de FRED confirman: *"Starting in April 2026, this series
   will only include 3 years of observations"*. La serie fue incorporada a FRED en junio 2023
   ya con ventana rolling — nunca existio el historico completo en FRED.

2. **ALFRED sin vintages pre-2023:** se verifico via API con fechas vintage de 2020-01-01 hasta
   2026-04-14. Los vintages anteriores a abril 2023 devuelven error 400 ("series does not exist
   in ALFRED"). Los vintages posteriores devuelven siempre `first=2023-04-18`. ALFRED no tiene
   datos pre-2023 de esta serie.

3. **Proxy NFCICREDIT rechazado:** se probaron tres modelos para usar NFCICREDIT (Chicago Fed
   Credit Subindex) como proxy del HY spread pre-2023. Los tres fallaron:

   | Modelo | Spot-checks pasados | Problema |
   |--------|---------------------|---------|
   | Lineal: HY = a + b*NFCI | 2/5 | Falla en regimen normal 2011/2015 |
   | Log-lineal 3A: log(HY) = a + b*NFCI | 1/5 | Explota a 17,000 bps en 2008 |
   | Cuadratico asimetrico 3B | 1/5 | Va negativo (-42 bps) en 2008 |

   **Causa raiz:** el periodo solapante (2023-2026) tiene spreads estructuralmente mas bajos
   que los periodos historicos para el mismo nivel de NFCICREDIT. La relacion no es estable
   en el tiempo. Ningun modelo parametrico calibrado sobre ese ventana puede extrapolarse.
   Ver `data/calibration_report_failed.json` para parametros completos y spot-checks.

**Implicaciones para el backtest:**

El MacroScore tiene un componente de HY Spread de peso 25 puntos (sobre base 100).
Para el periodo 2005-2023-04-17, este componente es **NaN**.

Se definen dos modos de backtest (a implementar en Entrega 4):

- **Modo B — backtest reducido (PRINCIPAL para 2005-2022):** MacroScore sobre base 75 pts,
  sin componente HY. Los otros 4 indicadores conservan sus pesos originales.
  Umbrales de regimen reescalados:

  | Regimen      | Umbral original (/100) | Umbral Modo B (/75) |
  |--------------|------------------------|---------------------|
  | Bull Pleno   | >= 75                  | >= 60               |
  | Bull Maduro  | 55-74                  | 45-59               |
  | Transicion   | 35-54                  | 30-44               |
  | Risk-OFF     | 20-34                  | 15-29               |
  | Capitulacion | < 20                   | < 15                |

- **Modo A — backtest completo (COMPLEMENTARIO para 2023+):** MacroScore completo con
  BAMLH0A0HYM2 real. Umbrales originales sobre base 100.

La comparacion de ambos modos en el periodo 2023+ permite cuantificar el aporte del
componente HY al poder predictivo del modelo.

---

## Limitaciones conocidas

### 1. Revisiones en CFNAI (look-ahead bias menor)
El CFNAI se descarga con la serie actual, que incluye revisiones retroactivas.
Para un backtest completamente honesto, deberían usarse datos "vintage" (como se
conocían en cada momento) disponibles en la base ALFRED de FRED. En una iteración
futura se puede migrar si se considera relevante. El sesgo introducido es menor
porque CFNAI tiene peso 15/100 en el MacroScore.

### 2. Series con inicio posterior a 2005
Algunas series no tienen datos desde 2005:

| Serie | Inicio real | Impacto |
|-------|-------------|---------|
| ^VIX9D | ~2011-01-03 | VolScore usa solo VIX nivel pre-2011 |
| ^VIX3M | ~2007-12-04 | Ídem |
| BTC-USD | ~2014-09-17 | Señales BTC-USD ausentes pre-2014 |
| XLRE | ~2015-10-08 | Sin datos sectoriales pre-2015 |
| THREEFYTP10 | Variable | Term Premium Extreme flag ausente en ciertos periodos |

Los NaN están presentes en los datos: el consumidor (Entrega 2) decide el fallback.

### 3. Futuros continuos (GC=F, SI=F, BZ=F)
Los contratos de futuros en Yahoo Finance son el contrato front-month, no una
serie continua ajustada por roll. Los precios históricos pueden tener saltos en
los cambios de contrato. Para backtest de largo plazo, los ETFs (GLD, SLV, USO)
serían más limpios pero no son los tickers usados en el sistema.

### 4. Idempotencia
La estrategia actual es re-descargar todo en cada ejecución (sobreescritura
limpia). Optimización futura: descarga incremental desde la última fecha en raw/.

---

## Known limitations — RotationScore validation (Entrega 3)

### Intraday timing gap en validaciones cruzadas contra la app

La validacion cruzada del RotationScore contra snapshots de la app productiva tiene una
limitacion estructural cuando la snapshot se toma **intraday** (tipicamente 12:25 PM ET):
el backtest usa el **cierre del dia** (4 PM ET), mientras la app usa el precio en el momento
de ejecucion.

**Resultado empirico (checkpoint 2026-04-17, 12:25 PM ET):**
- 12/19 tickers: match exacto en score, senal y fit
- 7/19 tickers: divergencia por intraday timing (ver tabla)

| Ticker  | Delta score | Criterio que flipea            | Margen EOD vs umbral |
|---------|-------------|-------------------------------|----------------------|
| XLI     | +2          | RS13w EOD=2.091% (umbral >2.0%) | +0.09%              |
| TLT     | +1          | trend: close=87.07 vs SMA200=86.67 | +$0.40 (0.46%)  |
| XLF     | +1          | trend: close=52.43 vs SMA200=52.29 | +$0.14 (0.27%)  |
| IWM     | +1          | CMF20=0.0080 (umbral >0)        | +0.008              |
| BZ=F    | +1          | CMF o OBV en frontera intraday  | —                    |
| GC=F    | 0 (fit)     | DXY ret_63d EOD=-1.23% (fit=True); intraday DXY >= 99.32 (fit=False) | +1.23% |
| BTC-USD | -1          | noext: ratio EOD=2.54 vs umbral <1.5; BTC 12:25 PM ~$74k | +$2.6k  |

Estos 7 divergencias estan marcados como `xfail` en `tests/test_rotation_vs_app.py` con
razon especifica por ticker. **No son bugs del codigo.**

**Guia practica para umbrales criticos:** si un criterio binario tiene un valor
dentro del **2% del umbral** en el EOD, es susceptible de flipear con diferencias
de timing. Esto afecta tipicamente al 30-40% de los tickers en snapshots intraday,
y al ~5% en snapshots post-cierre.

**Recomendacion para validaciones futuras:** tomar snapshots de la app los **viernes
despues de las 4 PM ET** (o fin de semana). Los precios intraday ya no cambian y la
tasa de match deberia ser 95-100%. Las snapshots intraday solo son utiles para
validar el comportamiento en tiempo real, no para comparar contra el backtest EOD.

---

## Known limitations — crisis detection in pre-2023 period

### HY Spread ausente: infravaloracion del estres en crisis severas

El HY Spread (peso 25/100) no esta disponible antes de 2023-04-18 por restriccion de
licencia ICE (ver seccion "HY Spread — indisponibilidad historica" mas arriba).

El **Modo B** del backtest reescala el MacroScore sobre 75 pts (4 componentes en lugar
de 5). Esto infravalora sistematicamente el estres en crisis severas donde el HY spread
se dispara por encima de 600 bps (0 pts).

**Ejemplo cuantificado — marzo 2020:**

| Semana | Score Modo B (sin HY) | Score hipotetico con HY (>1000 bps) | Regimen Modo B | Regimen hipotetico |
|--------|----------------------|-------------------------------------|----------------|--------------------|
| 2020-03-06 | 31.67 / 100 | ~23.75 / 100 | Bull Maduro | Capitulacion |
| 2020-03-13 | 40.00 / 100 | ~30.00 / 100 | Bull Maduro | Risk-OFF |
| 2020-03-20 | 53.33 / 100 | ~40.00 / 100 | Transicion | Transicion |

Con HY real (>600 bps = 0 pts), el score absoluto seria 5-7 pts menor y el MacroScore
escalado caeria ~6-9 puntos adicionales. El sistema habria detectado Capitulacion o
Risk-OFF en lugar de Bull Maduro durante las semanas mas agudas.

**Implicaciones practicas para Entregas 3-4:**

- La calibracion de umbrales de regimen en Modo B debera evaluarse empiricamente en
  Entrega 4 una vez se tenga la distribucion historica completa del backtest de rendimiento.
  No se recalibran a priori.
- Las metricas de precision/recall del detector de regimen en periodo pre-2023 deben
  interpretarse con esta limitacion estructural explicita.
- En crisis pre-2023, el campo `reliability` registra 0.75 (75 pts de 100 disponibles),
  lo que permite filtrar automaticamente el subconjunto afectado.

### NetLiq Delta13w en crisis intervencionistas: limitacion interpretativa

En marzo 2020, el indicador NetLiq Delta13w alcanzo su maximo (**25/25 pts**, delta >+500B)
**simultaneamente** al colapso del mercado. Esto ocurrio porque la Fed anuncio QE
ilimitado el 23 de marzo: la expansion del balance de la Fed se refleja inmediatamente en
WALCL, y el delta de 13 semanas cruza el umbral >500B cuando se compara con el nivel
pre-crisis.

**El indicador funciona correctamente segun su definicion**: mide si la liquidez del sistema
esta expandiendose, lo cual era cierto. Pero **no distingue entre liquidez organica de
expansion economica y liquidez de emergencia por intervencion**.

Consecuencia observada: en la tabla de regimenes, el score de marzo 2020 reboto de 31
a 53 puntos en dos semanas no porque el estres hubiera desaparecido, sino porque NetLiq
compenso aritmeticamente la caida del VolScore.

**Relevancia para Entrega 5 (detector de confluencia temprana):**

Los deltas cortos de NetLiq (Delta2w, Delta4w almacenados en `macro_history.parquet`)
pueden tener mejor resolucion discriminante en crisis que el Delta13w, porque:
- El Delta2w/4w captura la velocidad de expansion del QE, no solo su magnitud acumulada
- Un Delta13w positivo + Delta2w negativo puede indicar que la intervencion esta
  perdiendo velocidad (patron distinto al ciclo organico normal)
- Esta observacion queda pendiente de verificacion empirica en Entrega 5

---

## Actualización del pipeline

Re-ejecutar `python src/main.py` descarga datos frescos hasta hoy y sobrescribe
todos los archivos procesados. El `manifest.json` registra la fecha y hora de
la última ejecución.

Para programar actualizaciones semanales automáticas (ej. cada domingo):
- **Windows:** Programador de tareas → acción: `python C:\...\backtest\src\main.py`
- **Mac/Linux:** cron → `0 8 * * 0 cd /path/to/backtest && python src/main.py`
