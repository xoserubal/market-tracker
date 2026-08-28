// Relative Flow Lab v2 — ratio_registry
// Metadata central: cada ratio declara la pregunta que responde (type),
// su cluster narrativo (para Cluster View, secundaria) y su interpretación
// direccional (signalDirection + positiveMeaning/negativeMeaning).
// Principio: un ratio sin pregunta explícita es ruido.
//
// type: risk_appetite | anticipation | rotation | regions | sector_snapshot
// signalDirection: higher_is_risk_on | higher_is_risk_off | higher_is_bullish | higher_is_bearish | contextual
//   - higher_is_risk_on/off solo se usa en risk_appetite (alimenta el conteo del monitor).
//   - contextual = no tiene lectura risk-on/off inequívoca; se muestra pero no cuenta en el agregado.
//   - En el resto de bloques, higher_is_bullish/contextual son puramente descriptivos (no alimentan ningún agregado).
//
// context_ratio_id (RFL v2 — arquitectura de información, 2026-08-28): id opcional de
// OTRO ratio del registry cuyo estado se muestra como "Market Context" junto a este —
// resuelve el problema de leer un ratio de detalle intra-sectorial (ej. XLE/BZ=F,
// anticipation) sin haber visto antes el flujo agregado del sector vs mercado (ej.
// XLE/SPY, sector_snapshot). Solo se asigna entre ratios YA existentes en el registry —
// nunca se inventa un ratio nuevo solo para servir de contexto (ver
// smh_igv más abajo, deliberadamente sin asignar). Default: ausente = sin contexto.
//
// alsoShowIn (mismo cambio): array opcional de `type`s adicionales en los que esta fila
// se muestra TAMBIÉN (además de su `type` real, que no cambia) — visualización cruzada
// de un dato ya calculado una vez, no una segunda entrada de registry. No participa en
// ningún agregado del type "prestado" (Risk Appetite Monitor, Cluster Coherence View,
// Most Extreme Relative Moves siguen contando la fila una sola vez, por su `type` real) —
// solo el QuestionBlock del type prestado la añade a su tabla, marcada visualmente. Nace
// de un caso concreto: xlk_spy es `type:"rotation"` (reclasificado 2026-08-11), pero varios
// ratios de esa misma sección (smh_igv, xlk_xlf) necesitarían "Technology vs Market" como
// contexto — sin poder usar xlk_spy (viviría en la misma sección, circular) ni crear un
// ratio nuevo (fuera de alcance). alsoShowIn:["sector_snapshot"] en xlk_spy resuelve el
// caso sin ninguna de las dos cosas.
(function (global) {

  const RATIO_TYPES = {
    risk_appetite: {
      label: "Risk Appetite Monitor",
      question: "Is the market favoring risk-taking or safety?",
    },
    anticipation: {
      label: "Anticipation / Internal Conviction",
      question: "Within a theme, is the market anticipating improvement or deterioration before the underlying asset confirms it?",
    },
    rotation: {
      label: "Rotation Between Blocks",
      question: "Between major risk blocks, where is capital rotating?",
    },
    regions: {
      label: "Regions / EM Leadership",
      question: "Which regions are leading or lagging capital flows?",
    },
    sector_snapshot: {
      label: "Sector Relative Snapshot",
      question: "Which sectors are beating the broad market?",
    },
  };

  const RATIO_REGISTRY = [
    // ── RISK APPETITE ──────────────────────────────────────────────────────
    { id: "hyg_spy", label: "Credit vs Equities", pair: ["HYG", "SPY"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "higher_is_risk_on",
      primaryQuestion: "Is high-yield credit confirming the equity market's risk appetite?",
      positiveMeaning: "HYG outperforming SPY suggests credit investors are buying into risk alongside equities — broad risk-on confirmation.",
      negativeMeaning: "SPY outperforming HYG suggests credit is lagging equities — an early warning of stress beneath the surface.",
      primaryUse: "regime_confirmation", actionability: "high", enabled: true },

    { id: "xlu_xly", label: "Utilities vs Discretionary", pair: ["XLU", "XLY"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "higher_is_risk_off",
      primaryQuestion: "Is the market rotating into defensives (utilities) or staying in cyclicals (discretionary)?",
      positiveMeaning: "XLU outperforming XLY signals defensive positioning — a risk-off warning.",
      negativeMeaning: "XLY outperforming XLU signals cyclical strength — risk-on.",
      primaryUse: "regime_confirmation", actionability: "high", enabled: true },

    { id: "splv_mtum", label: "Low Vol vs Momentum", pair: ["SPLV", "MTUM"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "higher_is_risk_off",
      primaryQuestion: "Is the market seeking safety (low volatility) or chasing momentum (risk)?",
      positiveMeaning: "SPLV outperforming MTUM signals a flight to safety — risk-off.",
      negativeMeaning: "MTUM outperforming SPLV signals risk appetite and momentum chasing — risk-on.",
      primaryUse: "regime_confirmation", actionability: "high", enabled: true },

    { id: "xly_xlp", label: "Discretionary vs Staples", pair: ["XLY", "XLP"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "higher_is_risk_on",
      primaryQuestion: "Is the consumer favoring discretionary spending (cyclical) or staying defensive (staples)?",
      positiveMeaning: "XLY outperforming XLP suggests confident, risk-on consumer positioning.",
      negativeMeaning: "XLP outperforming XLY suggests defensive rotation and consumer caution.",
      primaryUse: "regime_confirmation", actionability: "medium", enabled: true },

    { id: "copper_gold", label: "Copper vs Gold", pair: ["HG=F", "GC=F"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "higher_is_risk_on",
      primaryQuestion: "Is the market pricing in economic growth (copper) or safety (gold)?",
      positiveMeaning: "Copper outperforming Gold suggests the market expects stronger growth — risk-on.",
      negativeMeaning: "Gold outperforming Copper suggests growth concerns and a preference for safety.",
      primaryUse: "regime_confirmation", actionability: "high", enabled: true },

    { id: "iwm_spy", label: "Small Caps vs S&P 500", pair: ["IWM", "SPY"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "higher_is_risk_on",
      primaryQuestion: "Is market breadth expanding (small caps) or narrowing (mega caps)?",
      positiveMeaning: "IWM outperforming SPY signals broad participation — a healthier, more sustainable risk-on move.",
      negativeMeaning: "SPY outperforming IWM signals concentration in large caps — narrower, more fragile leadership.",
      primaryUse: "regime_confirmation", actionability: "medium", enabled: true },

    { id: "qqq_rsp", label: "Nasdaq vs Equal Weight", pair: ["QQQ", "RSP"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "contextual",
      primaryQuestion: "Is leadership concentrated in mega-cap growth, or broad across the market?",
      positiveMeaning: "QQQ outperforming RSP signals concentration in mega-cap growth/tech — can reflect strong risk appetite OR defensive crowding into a handful of quality growth names. Direction is context-dependent, not counted in the aggregate.",
      negativeMeaning: "RSP outperforming QQQ signals broader participation and rotation away from mega-cap concentration.",
      primaryUse: "breadth_context", actionability: "medium", enabled: true },

    { id: "tlt_spy", label: "Bonds vs Market", pair: ["TLT", "SPY"],
      type: "risk_appetite", cluster: "SECTOR ROTATION", signalDirection: "higher_is_risk_off",
      // Reasignado 2026-08-11 (Fase 1 de código de wiki/RFL_CLUSTER_REASSIGNMENT_TABLE.md):
      // termómetro directo de refugio en duración, mismo nivel que HYG/SPY o XLU/XLY — no
      // encajaba en sector_snapshot por omisión, no por diseño. countedInMonitor:false porque
      // no hay evidencia para alterar el denominador /6 del Risk Appetite Monitor ya en
      // producción — mismo tratamiento (se muestra, no cuenta) que QQQ/RSP, pero vía un flag
      // explícito en vez de signalDirection:"contextual" (aquí la lectura sí es inequívoca).
      countedInMonitor: false,
      primaryQuestion: "Is long-duration Treasury debt beating equities?",
      positiveMeaning: "TLT outperforming SPY indicates money leaving equities for fixed income — risk-off.",
      negativeMeaning: "SPY outperforming TLT indicates money leaving bonds for equities — risk-on.",
      primaryUse: "regime_confirmation", actionability: "medium-low", enabled: true },

    // Fase 2 (2026-08-11, wiki/RFL_CLUSTER_REASSIGNMENT_TABLE.md): ratios nuevos de
    // verdad, no reasignaciones — sí cuentan en el agregado del monitor (denominador
    // pasa de /6 a /8), a diferencia de TLT/SPY arriba (que preserva un umbral ya
    // calibrado). Verificados contra Yahoo en vivo el 2026-08-11 antes de integrarlos.
    { id: "hyg_lqd", label: "High Yield vs Investment Grade", pair: ["HYG", "LQD"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "higher_is_risk_on",
      primaryQuestion: "Within corporate credit, is the market reaching for yield (high-yield) or staying in quality (investment-grade)?",
      positiveMeaning: "HYG outperforming LQD suggests credit investors are reaching for yield in lower-quality debt — risk-on within the credit complex, often ahead of equities.",
      negativeMeaning: "LQD outperforming HYG suggests a flight to quality within credit — a risk-off warning that can show up before it's visible in equities.",
      primaryUse: "regime_confirmation", actionability: "high", enabled: true },

    { id: "vvix_vix", label: "Vol-of-Vol vs Volatility", pair: ["^VVIX", "^VIX"],
      type: "risk_appetite", cluster: "RISK APPETITE", signalDirection: "higher_is_risk_off",
      primaryQuestion: "Is the options market pricing rising uncertainty about future volatility itself, ahead of a spike in realized volatility?",
      positiveMeaning: "VVIX outperforming VIX suggests the options market is bidding up uncertainty about future volatility — often an early tail-risk warning before VIX itself spikes.",
      negativeMeaning: "VIX outperforming VVIX suggests volatility concerns are already reflected in spot vol, without an incremental vol-of-vol warning.",
      primaryUse: "regime_confirmation", actionability: "medium", enabled: true },

    // ── ANTICIPATION / INTERNAL CONVICTION ──────────────────────────────────
    { id: "xle_brent", label: "Energy Equities vs Brent", pair: ["XLE", "BZ=F"],
      type: "anticipation", cluster: "ENERGY", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are energy equities discounting stronger fundamentals than crude oil itself?",
      positiveMeaning: "Energy equities outperform Brent; the equity market may be anticipating stronger future energy fundamentals.",
      negativeMeaning: "Brent outperforms energy equities; the equity market may doubt the sustainability of the crude move.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true, context_ratio_id: "xle_spy" },

    { id: "gdx_gld", label: "Gold Miners vs Gold", pair: ["GDX", "GLD"],
      type: "anticipation", cluster: "METALS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are gold miners leading gold itself, suggesting early accumulation?",
      positiveMeaning: "GDX outperforming GLD suggests early accumulation in miners ahead of the metal — a leading signal.",
      negativeMeaning: "GLD outperforming GDX suggests miners are lagging the metal — a bearish divergence.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true, context_ratio_id: "gld_spy" },

    { id: "gdxj_gdx", label: "Junior Miners vs Senior Miners", pair: ["GDXJ", "GDX"],
      type: "anticipation", cluster: "METALS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is speculative appetite rotating into higher-beta junior miners ahead of the senior producers?",
      positiveMeaning: "GDXJ outperforming GDX suggests risk appetite is moving into higher-beta juniors — often an early-cycle, speculative confirmation within the gold complex.",
      negativeMeaning: "GDX outperforming GDXJ suggests a flight to quality within miners — juniors lagging, a more cautious complex.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true },

    { id: "kre_xlf", label: "Regional Banks vs Large Banks", pair: ["KRE", "XLF"],
      type: "anticipation", cluster: "FINANCIALS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is local/regional credit conviction leading large-bank strength?",
      positiveMeaning: "KRE outperforming XLF suggests stronger conviction in local credit conditions — usually reflects broader confidence in the credit cycle.",
      negativeMeaning: "XLF outperforming KRE suggests flight to quality within financials — caution around regional credit exposure.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true, context_ratio_id: "xlf_spy" },

    { id: "xop_xle", label: "E&P vs Integrated Energy", pair: ["XOP", "XLE"],
      type: "anticipation", cluster: "ENERGY", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is speculative upstream exposure leading integrated energy majors?",
      positiveMeaning: "XOP outperforming XLE suggests speculative, high-beta upstream exposure is leading — risk appetite within energy.",
      negativeMeaning: "XLE outperforming XOP suggests rotation to quality/integrated majors within the energy complex.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true, context_ratio_id: "xle_spy" },

    { id: "silver_gold", label: "Silver vs Gold", pair: ["SI=F", "GC=F"],
      type: "anticipation", cluster: "METALS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is industrial/speculative demand for silver leading gold's safe-haven bid?",
      positiveMeaning: "Silver outperforming Gold suggests industrial/speculative appetite for metals is leading — a risk-on read within the metals complex.",
      negativeMeaning: "Gold outperforming Silver suggests a pure safe-haven bid, without industrial/speculative confirmation.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true },

    { id: "ura_urnm", label: "Broad Nuclear vs Uranium Miners", pair: ["URA", "URNM"],
      type: "anticipation", cluster: "URANIUM", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is capital rotating into the broader, more diversified nuclear complex vs pure uranium miners?",
      positiveMeaning: "URA outperforming URNM suggests flow into the broader nuclear complex — more defensive within the theme.",
      negativeMeaning: "URNM outperforming URA suggests flow into higher-beta, pure-play uranium miners — speculative conviction.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true },

    { id: "hcc_btu", label: "Warrior Met vs Peabody", pair: ["HCC", "BTU"],
      type: "anticipation", cluster: "COAL", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are higher-quality/met-coal equities outperforming broad coal exposure?",
      positiveMeaning: "HCC outperforming BTU suggests stronger preference for metallurgical/quality coal exposure over diversified coal.",
      negativeMeaning: "BTU outperforming HCC suggests broader/diversified coal exposure is leading.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true },

    { id: "amr_btu", label: "Alpha Met vs Peabody", pair: ["AMR", "BTU"],
      type: "anticipation", cluster: "COAL", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are met-coal pure plays outperforming diversified coal exposure?",
      positiveMeaning: "AMR outperforming BTU suggests stronger internal leadership from met coal.",
      negativeMeaning: "BTU outperforming AMR suggests broader coal is leading or met-coal leadership is weakening.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true },

    { id: "ccj_urnm", label: "Cameco vs Uranium Miners", pair: ["CCJ", "URNM"],
      type: "anticipation", cluster: "URANIUM", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is the uranium bellwether outperforming the broader uranium miners basket?",
      positiveMeaning: "CCJ outperforming URNM suggests leadership is concentrated in the quality/liquid uranium bellwether.",
      negativeMeaning: "URNM outperforming CCJ suggests broader uranium miner participation beyond the main leader.",
      primaryUse: "theme_confirmation", actionability: "medium", enabled: true },

    { id: "btc_gold", label: "Bitcoin vs Gold", pair: ["BTC-USD", "GC=F"],
      type: "anticipation", cluster: "CRYPTO", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is speculative/risk capital preferring Bitcoin over gold as a store of value?",
      positiveMeaning: "BTC-USD outperforming Gold suggests risk-on speculative capital is favoring Bitcoin over the traditional safe haven.",
      negativeMeaning: "Gold outperforming BTC-USD suggests a preference for the traditional safe haven over speculative digital assets.",
      primaryUse: "theme_confirmation", actionability: "low", enabled: true },

    // ── ROTATION BETWEEN BLOCKS ──────────────────────────────────────────────
    { id: "xlb_xle", label: "Materials vs Energy", pair: ["XLB", "XLE"],
      type: "rotation", cluster: "ENERGY", signalDirection: "contextual",
      primaryQuestion: "Is capital rotating from energy into materials, or the reverse?",
      positiveMeaning: "XLB outperforming XLE suggests capital rotating into materials at the expense of energy.",
      negativeMeaning: "XLE outperforming XLB suggests energy is leading the broader materials/commodity complex.",
      primaryUse: "capital_rotation", actionability: "medium", enabled: true },

    { id: "xlk_xlf", label: "Technology vs Financials", pair: ["XLK", "XLF"],
      type: "rotation", cluster: "SECTOR ROTATION", signalDirection: "contextual",
      primaryQuestion: "Is capital rotating between growth/technology and financials/value?",
      positiveMeaning: "XLK outperforming XLF suggests rotation into growth/technology.",
      negativeMeaning: "XLF outperforming XLK suggests rotation into financials/value.",
      // context_ratio_id: xlf_spy, no xlk_spy — xlk_spy es type:"rotation" (misma sección
      // que este ratio), sería circular. XLF/SPY sí vive en sector_snapshot y Financials
      // es una de las dos patas de este ratio (ver nota al pie del registry).
      primaryUse: "capital_rotation", actionability: "medium", enabled: true, context_ratio_id: "xlf_spy" },

    { id: "iwd_iwf", label: "Value vs Growth", pair: ["IWD", "IWF"],
      type: "rotation", cluster: "STYLE / FACTOR", signalDirection: "contextual",
      primaryQuestion: "Is capital rotating between value and growth styles?",
      positiveMeaning: "IWD outperforming IWF suggests rotation into value.",
      negativeMeaning: "IWF outperforming IWD suggests rotation into growth.",
      primaryUse: "capital_rotation", actionability: "medium", enabled: true },

    { id: "ijs_ijt", label: "Small Cap Value vs Growth", pair: ["IJS", "IJT"],
      // Fase 2 (2026-08-11): mismo cluster que IWD/IWF, versión small-cap del mismo
      // eje value/growth — verificado contra Yahoo en vivo antes de integrarlo.
      type: "rotation", cluster: "STYLE / FACTOR", signalDirection: "contextual",
      primaryQuestion: "Within small caps, is capital rotating between value and growth styles?",
      positiveMeaning: "IJS outperforming IJT suggests rotation into small-cap value.",
      negativeMeaning: "IJT outperforming IJS suggests rotation into small-cap growth.",
      primaryUse: "capital_rotation", actionability: "medium", enabled: true },

    { id: "smh_igv", label: "Semiconductors vs Software", pair: ["SMH", "IGV"],
      type: "rotation", cluster: "SECTOR ROTATION", signalDirection: "contextual",
      primaryQuestion: "Within technology, is capital rotating into hardware/semis or software?",
      positiveMeaning: "SMH outperforming IGV suggests rotation into semiconductors/hardware within tech.",
      negativeMeaning: "IGV outperforming SMH suggests rotation into software within tech.",
      // context_ratio_id deliberadamente ausente: no hay hoy ningún ratio "Technology vs
      // Market" en sector_snapshot (xlk_spy vive en rotation, misma sección — sería
      // circular; XLC/SPY es Comunicación, no encaja semánticamente con semis/software).
      // No se inventa un ratio nuevo solo para esto en Fase 1 — ver nota al pie del registry.
      primaryUse: "capital_rotation", actionability: "medium", enabled: true },

    { id: "xle_xlk", label: "Energy vs Technology", pair: ["XLE", "XLK"],
      type: "rotation", cluster: "SECTOR ROTATION", signalDirection: "contextual",
      primaryQuestion: "Is capital rotating between energy/value cyclicals and technology/growth?",
      positiveMeaning: "XLE outperforming XLK suggests rotation into energy/value cyclicals.",
      negativeMeaning: "XLK outperforming XLE suggests rotation into technology/growth.",
      primaryUse: "capital_rotation", actionability: "medium", enabled: true },

    { id: "hcc_xme", label: "Warrior Met vs Metals Miners", pair: ["HCC", "XME"],
      type: "rotation", cluster: "COAL", signalDirection: "contextual",
      primaryQuestion: "Is coal leadership outperforming broad metals & mining?",
      positiveMeaning: "HCC outperforming XME suggests coal-specific leadership versus the broader mining/materials complex.",
      negativeMeaning: "XME outperforming HCC suggests coal is lagging broader metals/mining.",
      primaryUse: "capital_rotation", actionability: "medium-low", enabled: true },

    { id: "amr_xme", label: "Alpha Met vs Metals Miners", pair: ["AMR", "XME"],
      type: "rotation", cluster: "COAL", signalDirection: "contextual",
      primaryQuestion: "Is met-coal leadership outperforming broad metals & mining?",
      positiveMeaning: "AMR outperforming XME suggests met coal is leading the broader mining/materials complex.",
      negativeMeaning: "XME outperforming AMR suggests met coal is lagging broader mining/materials.",
      primaryUse: "capital_rotation", actionability: "medium-low", enabled: true },

    { id: "xlk_spy", label: "Technology vs Market", pair: ["XLK", "SPY"],
      type: "rotation", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      // Reasignado 2026-08-11 (Fase 1 de código, wiki/RFL_CLUSTER_REASSIGNMENT_TABLE.md):
      // "promoción visual (ya existe, no se duplica)" — pasa de sector_snapshot (bloque
      // secundario) a rotation, único display en el bloque Rotation Between Blocks.
      primaryQuestion: "Is technology beating the broad market?",
      positiveMeaning: "XLK outperforming SPY indicates flow into growth/tech.",
      negativeMeaning: "SPY outperforming XLK indicates rotation out of tech.",
      // alsoShowIn (2026-08-28): se muestra TAMBIÉN en la tabla de Sector Relative
      // Snapshot (marcado visualmente como cruzado desde Rotation) — sirve de
      // "Technology vs Market" a los ratios de esa sección que lo necesitan como
      // contexto (ver smh_igv/xlk_xlf) sin duplicar la entrada ni cambiar su `type`
      // real. No participa en ningún agregado de sector_snapshot (Cluster View,
      // conteos) — solo aparece en su tabla.
      primaryUse: "capital_rotation", actionability: "medium", enabled: true, alsoShowIn: ["sector_snapshot"] },

    // ── REGIONS / EM LEADERSHIP ───────────────────────────────────────────────
    { id: "eem_urth", label: "Emerging Markets vs World", pair: ["EEM", "URTH"],
      type: "regions", cluster: "REGIONS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is capital favoring emerging markets over developed/global equities?",
      positiveMeaning: "EEM outperforming URTH suggests risk appetite for emerging markets.",
      negativeMeaning: "URTH outperforming EEM suggests a preference for developed markets — EM risk aversion.",
      primaryUse: "regional_leadership", actionability: "medium", enabled: true },

    { id: "ewz_eem", label: "Brazil vs EM", pair: ["EWZ", "EEM"],
      type: "regions", cluster: "REGIONS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is Brazil leading or lagging the broader EM complex?",
      positiveMeaning: "EWZ outperforming EEM suggests capital concentrating in Brazil within EM.",
      negativeMeaning: "EEM outperforming EWZ suggests Brazil is lagging the broader EM complex.",
      primaryUse: "regional_leadership", actionability: "medium", enabled: true },

    { id: "argt_eem", label: "Argentina vs EM", pair: ["ARGT", "EEM"],
      type: "regions", cluster: "REGIONS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is Argentina leading or lagging the broader EM complex?",
      positiveMeaning: "ARGT outperforming EEM suggests relative outperformance and idiosyncratic strength in Argentina.",
      negativeMeaning: "EEM outperforming ARGT suggests Argentina is lagging the broader EM complex.",
      primaryUse: "regional_leadership", actionability: "medium-low", enabled: true },

    { id: "ewj_eem", label: "Japan vs EM", pair: ["EWJ", "EEM"],
      type: "regions", cluster: "REGIONS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is capital rotating toward developed-Asia quality (Japan) or emerging markets?",
      positiveMeaning: "EWJ outperforming EEM suggests rotation toward developed-Asia quality.",
      negativeMeaning: "EEM outperforming EWJ suggests capital favoring emerging markets over Japan.",
      primaryUse: "regional_leadership", actionability: "medium", enabled: true },

    // Fase 2 (2026-08-11): sub-cat "fx_estructural" — señales FX/macro estructurales sin
    // eje región-vs-región limpio, agrupadas aquí por ser el bucket más cercano de los 5
    // de la taxonomía (decisión cerrada en wiki/RFL_CLUSTER_REASSIGNMENT_TABLE.md).
    // signalDirection:"contextual" en ambas — el propio proyecto ya trata USDJPY como
    // direccionalmente ambiguo en duration.html (yields↑+TLT↓+USDJPY↓ puede ser
    // repatriación limpia, o DXY↑+USDJPY↑ puede ser un shock de yields/dólar genérico
    // que no confirma la tesis Japón); el mismo criterio se aplica aquí por consistencia.
    { id: "usdjpy_nikkei", label: "USDJPY vs Nikkei", pair: ["JPY=X", "^N225"],
      type: "regions", cluster: "REGIONS", signalDirection: "contextual",
      primaryQuestion: "Is yen weakness moving together with Nikkei strength (the carry-trade-on pattern), or are they decoupling?",
      positiveMeaning: "USDJPY (yen weakness) rising faster than the Nikkei suggests the yen-carry relationship may be decoupling — a divergence worth cross-checking against the Duration Stress Monitor's BOJ/Treasury supply thesis.",
      negativeMeaning: "Nikkei strength keeping pace with or outrunning yen weakness suggests the carry-trade-on relationship (weak yen, strong Nikkei) remains intact.",
      primaryUse: "regional_leadership", actionability: "medium", enabled: true },

    { id: "dxy_gld", label: "Dollar Index vs Gold", pair: ["DX-Y.NYB", "GC=F"],
      type: "regions", cluster: "REGIONS", signalDirection: "contextual",
      primaryQuestion: "Is the dollar strengthening against gold structurally, or is gold's safe-haven bid outpacing dollar strength?",
      positiveMeaning: "The Dollar Index outperforming Gold suggests dollar strength is dominant — often reflects real-rate-driven dollar demand rather than a broad flight to safety.",
      negativeMeaning: "Gold outperforming the Dollar Index suggests a safe-haven or inflation-hedge bid strong enough to overcome dollar strength.",
      primaryUse: "regional_leadership", actionability: "medium", enabled: true },

    // ── SECTOR RELATIVE SNAPSHOT (secundario) ────────────────────────────────
    { id: "xlf_spy", label: "Financials vs Market", pair: ["XLF", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are financials beating the broad market?",
      positiveMeaning: "XLF outperforming SPY indicates an active credit cycle.",
      negativeMeaning: "SPY outperforming XLF indicates money leaving financials.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xlv_spy", label: "Healthcare vs Market", pair: ["XLV", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is healthcare beating the broad market?",
      positiveMeaning: "XLV outperforming SPY indicates defensive rotation toward healthcare.",
      negativeMeaning: "SPY outperforming XLV indicates money leaving healthcare.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xly_spy", label: "Discretionary vs Market", pair: ["XLY", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is discretionary beating the broad market?",
      positiveMeaning: "XLY outperforming SPY indicates risk appetite / consumer strength.",
      negativeMeaning: "SPY outperforming XLY indicates consumer caution.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xlp_spy", label: "Staples vs Market", pair: ["XLP", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are staples beating the broad market?",
      positiveMeaning: "XLP outperforming SPY indicates defensive rotation.",
      negativeMeaning: "SPY outperforming XLP indicates money leaving staples toward risk.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xle_spy", label: "Energy vs Market", pair: ["XLE", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is energy beating the broad market?",
      positiveMeaning: "XLE outperforming SPY indicates flow into energy/inflation exposure.",
      negativeMeaning: "SPY outperforming XLE indicates money leaving energy.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xli_spy", label: "Industrials vs Market", pair: ["XLI", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are industrials beating the broad market?",
      positiveMeaning: "XLI outperforming SPY indicates a bet on the economic cycle.",
      negativeMeaning: "SPY outperforming XLI indicates money leaving industrials.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xlb_spy", label: "Materials vs Market", pair: ["XLB", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are materials beating the broad market?",
      positiveMeaning: "XLB outperforming SPY indicates flow into commodities/materials.",
      negativeMeaning: "SPY outperforming XLB indicates money leaving materials.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xlre_spy", label: "Real Estate vs Market", pair: ["XLRE", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is real estate beating the broad market?",
      positiveMeaning: "XLRE outperforming SPY indicates yield appetite / sensitivity to falling rates.",
      negativeMeaning: "SPY outperforming XLRE indicates pressure from high rates.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xlc_spy", label: "Communication vs Market", pair: ["XLC", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is communication services beating the broad market?",
      positiveMeaning: "XLC outperforming SPY indicates flow into media/telecom/internet.",
      negativeMeaning: "SPY outperforming XLC indicates money leaving communication services.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "xlu_spy", label: "Utilities vs Market", pair: ["XLU", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are utilities beating the broad market?",
      positiveMeaning: "XLU outperforming SPY indicates defensive rotation (yield, low beta).",
      negativeMeaning: "SPY outperforming XLU indicates money leaving utilities toward risk.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "gld_spy", label: "Gold vs Market", pair: ["GLD", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is gold beating equities?",
      positiveMeaning: "GLD outperforming SPY indicates the market seeking safe-haven/hedge exposure.",
      negativeMeaning: "SPY outperforming GLD indicates risk appetite — gold not attracting flow.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "bil_spy", label: "Cash vs Market", pair: ["BIL", "SPY"],
      type: "sector_snapshot", cluster: "SECTOR ROTATION", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is T-Bill cash beating equities?",
      positiveMeaning: "BIL outperforming SPY indicates money moving to cash/liquidity — extreme defensiveness.",
      negativeMeaning: "SPY outperforming BIL indicates money leaving cash for risk.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },

    { id: "urnm_urth", label: "Uranium Miners vs World", pair: ["URNM", "URTH"],
      type: "sector_snapshot", cluster: "URANIUM", signalDirection: "higher_is_bullish",
      primaryQuestion: "Is uranium outperforming global equities?",
      positiveMeaning: "Uranium miners outperforming world equities suggests theme-level leadership.",
      negativeMeaning: "Uranium miners lagging world equities suggests the uranium theme is not attracting relative capital.",
      primaryUse: "sector_snapshot", actionability: "medium", enabled: true },

    { id: "xme_spy", label: "Metals Miners vs Market", pair: ["XME", "SPY"],
      type: "sector_snapshot", cluster: "MATERIALS", signalDirection: "higher_is_bullish",
      primaryQuestion: "Are metals & mining equities outperforming the broad US market?",
      positiveMeaning: "XME outperforming SPY suggests metals/mining leadership versus broad equities.",
      negativeMeaning: "XME lagging SPY suggests metals/mining are not leading the market.",
      primaryUse: "sector_snapshot", actionability: "medium-low", enabled: true },
  ];

  global.RATIO_TYPES = RATIO_TYPES;
  global.RATIO_REGISTRY = RATIO_REGISTRY;

})(window);
