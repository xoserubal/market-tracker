# Revisión de etiquetas del Portfolio

_Generado por `scripts/seed_ticker_tags.js`. Todas las asignaciones sembradas son **propuestas** (`source: assistant`, `review_status: pending`)._

- Instrumentos: **130** · emisores: **129** · etiquetas en el vocabulario: **150**
- Asignaciones activas: pendientes **480** · confirmadas **0** · rechazadas **0**
- Identidades: 129 provisionales, 0 verificadas (Yahoo solo nunca verifica).

## Revisar primero

Tickers con confianza baja o media en alguna asignación. La columna Yahoo es solo referencia (no prueba de identidad).

| Ticker | Empresa (Yahoo) | Confianza | Industria propuesta | Sector / industria Yahoo | Nota |
|---|---|---|---|---|---|
| AAG.V | Aftermath Silver Ltd. | 🟠 media | Minería de plata | Basic Materials / Other Industrial Metals & Mining | Berenguela |
| ASPI | ASP Isotopes Inc. | 🟠 media | Químicos especializados | Basic Materials / Specialty Chemicals | isótopos médicos y HALEU |
| ASTS | AST SpaceMobile, Inc. | 🟠 media | Equipos de comunicación | Technology / Communication Equipment |  |
| AWX.V | ArcWest Exploration Inc. | 🟠 media | Minería de cobre | Basic Materials / Other Industrial Metals & Mining | Todd Creek, BC |
| BOGO.V | Borealis Mining Company Limited | 🟠 media | Minería de oro | Basic Materials / Other Industrial Metals & Mining | Nevada |
| BUR | Burford Capital Limited | 🟠 media | Financiación de litigios | Financial Services / Asset Management | pleito YPF |
| CORZ | Core Scientific, Inc. | 🟠 media | Centros de datos | Technology / Software - Infrastructure | colocación IA + minería de bitcoin |
| DMX.V | District Metals Corp. | 🟠 media | Minería polimetálica | Basic Materials / Other Industrial Metals & Mining | Viken (Suecia) |
| DPM.TO | DPM Metals Inc. | 🟠 media | Minería de oro | Basic Materials / Gold | ver §7; Vareš (BA) tras comprar Adriatic |
| EOS.AX | Electro Optic Systems Holdings Limited | 🟠 media | Aeroespacial y defensa | Industrials / Aerospace & Defense | antidrones, láser, seguimiento de satélites |
| FDR.AX | Finder Energy Holdings Limited | 🟠 media | Exploración y producción | Energy / Oil & Gas E&P | NW Shelf + UK |
| GHM.AX | Golden Horse Minerals Limited | 🟠 media | Minería de oro | Basic Materials / Gold | Western Australia |
| GLEN.L | Glencore plc | 🟠 media | Minería diversificada | Basic Materials / Other Industrial Metals & Mining | trading + minería |
| GLNG | Golar LNG Limited | 🟠 media | Infraestructura GNL | Energy / Oil & Gas Midstream | FLNG en Argentina |
| GRSL.V | GR Silver Mining Ltd. | 🔴 baja | Minería de plata | Basic Materials / Other Industrial Metals & Mining | Yahoo: «sin operaciones significativas», revisar |
| HFG.DE | HelloFresh SE | 🟠 media | Distribución alimentaria | Consumer Defensive / Grocery Stores | ingresos sobre todo en Norteamérica, revisar |
| HIMS | Hims & Hers Health, Inc. | 🟠 media | Telesalud | Healthcare / Drug Manufacturers - Specialty & Generic |  |
| KOS | Kosmos Energy Ltd. | 🟠 media | Exploración y producción | Energy / Oil & Gas E&P |  |
| MRR.XA | Northstone Resources Limited | 🟠 media | Minería de oro | — | Tlamino (sur de Serbia); símbolo → BD2 de la línea B |
| PNPN.V | Power Metallic Mines Inc. | 🔴 baja | Minería polimetálica | Basic Materials / Other Industrial Metals & Mining | revisar qué metal es el principal |
| SE | Sea Limited | 🟠 media | Comercio electrónico | Consumer Cyclical / Internet Retail | Shopee/Garena/fintech |
| SLG.V | San Lorenzo Gold Corp. | 🟠 media | Minería de oro | Basic Materials / Other Industrial Metals & Mining | Salvadora |
| SLS.TO | Solaris Resources Inc. | 🟠 media | Minería de cobre | Basic Materials / Other Precious Metals & Mining | Warintza |
| TSLA | Tesla, Inc. | 🟠 media | Automoción | Consumer Cyclical / Auto Manufacturers |  |
| TTI | TETRA Technologies, Inc. | 🟠 media | Servicios petroleros | Energy / Oil & Gas Equipment & Services | salmueras de bromo/litio |
| USAU | U.S. Gold Corp. | 🟠 media | Minería de oro | Basic Materials / Gold | CK Gold, Wyoming |
| VFF | Village Farms International, Inc. | 🟠 media | Agricultura | Consumer Defensive / Farm Products | invernaderos + cannabis |

## Casos donde Yahoo y la propuesta difieren mucho

Yahoo describe el sector contable; la propuesta describe la exposición económica. Estos casos son los esperables:

| Ticker | Yahoo | Propuesta (exposición principal) |
|---|---|---|
| MSTR | Technology / Software - Application | Bitcoin, Estados Unidos |
| VFF | Consumer Defensive / Farm Products | Cannabis, Canadá |
| ASTS | Technology / Communication Equipment | Espacio, Estados Unidos |
| GLEN.L | Basic Materials / Other Industrial Metals & Mining | Cobre, Global |
| AFM.V | Basic Materials / Other Industrial Metals & Mining | Estaño, R. D. del Congo |
| COIN | Financial Services / Financial Data & Stock Exchanges | Criptoactivos, Estados Unidos |
| CORZ | Technology / Software - Infrastructure | Infraestructura IA, Estados Unidos |
| HFG.DE | Consumer Defensive / Grocery Stores | Norteamérica |
| SE | Consumer Cyclical / Internet Retail | Asia-Pacífico |

## Grupos que nacen pequeños

- Cromo (`commodity:chrome`): SLP.L
- Cobalto (`commodity:cobalt`): GLEN.L
- Mineral de hierro (`commodity:iron_ore`): FXPO.L
- GNL (`commodity:lng`): GLNG, KOS
- Manganeso (`commodity:manganese`): AAG.V
- Níquel (`commodity:nickel`): GLEN.L, PNPN.V
- Platinoides (`commodity:pgm`): PNPN.V, SLP.L
- Estaño (`commodity:tin`): AFM.V, MLX.AX
- Vanadio (`commodity:vanadium`): DMX.V
- Software IA (`theme:ai_software`): PLTR
- Criptoactivos (`theme:crypto`): COIN
- Drones (`theme:drones`): EOS.AX, RCAT
- Electrificación (`theme:electrification`): EOSE
- Vehículo eléctrico (`theme:ev`): TSLA
- GLP-1 y obesidad (`theme:glp1_obesity`): LLY
- Ecosistema Elon Musk (`theme:musk_ecosystem`): TSLA
- Robótica (`theme:robotics`): ISRG
- Espacio (`theme:space`): ASTS, EOS.AX

## Cómo revisar

Abre `portfolio.html`, agrupa por la dimensión que quieras y confirma o rechaza las asignaciones desde el botón 🏷 de cada fila. Las confirmadas, rechazadas o editadas a mano **no se vuelven a tocar** al re-sembrar.
