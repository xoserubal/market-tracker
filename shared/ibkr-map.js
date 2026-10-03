// ── Mapeo de símbolos IBKR → ticker de Portfolio Tracker (Yahoo) ───────────
// Compartido entre portfolio.html (panel "Cartera real") y
// scripts/ibkr_decision_journal.js (diario de operaciones). Dual export
// navegador (<script src>) / Node (module.exports), mismo patrón que
// shared/flow-score.js. Antes vivía duplicado dentro de portfolio.html.
//
// IBKR da el símbolo "limpio" (BTCC.B, FXPOl en LSE, "QXO   270115C…" para
// una opción OCC) y Yahoo añade sufijo de bolsa y usa guion en clases
// (BTCC-B.TO). Orden de intentos: (1) símbolo tal cual, (2) + sufijo de la
// bolsa de listado, (3) coincidencia única por base — válida solo si UN
// ticker del tracker comparte base (evita enlazar mal cuando hay ambigüedad).

const IBKR_EXCHANGE_SUFFIX = {
  AEB:'.AS', IBIS:'.DE', IBIS2:'.DE', FWB:'.DE', FWB2:'.DE', GETTEX:'.DE', LSE:'.L', LSEETF:'.L',
  SBF:'.PA', BM:'.MC', BVME:'.MI', SFB:'.ST', TSE:'.TO', VENTURE:'.V', ASX:'.AX', EBS:'.SW',
  CSE:'.CO', OSE:'.OL', SEHK:'.HK',
  // CDE (Montreal) y EUREX son bolsas de OPCIONES: el sufijo sale de la bolsa
  // del contrato, que aquí coincide con el país del subyacente.
  CDE:'.TO', EUREX:'.DE',
};
const IBKR_KNOWN_SUFFIXES = new Set(Object.values(IBKR_EXCHANGE_SUFFIX));

// Base de un ticker Yahoo para comparar: sin sufijo de bolsa y con punto en
// vez de guion en clases de acción (BTCC-B.TO → BTCC.B).
function ibkrYahooBase(t) {
  const s = String(t || '').replace(/^\^/, '');   // índices Yahoo (^XSP) ↔ símbolo IBKR (XSP)
  const i = s.lastIndexOf('.');
  const noSuffix = (i > 0 && IBKR_KNOWN_SUFFIXES.has(s.slice(i))) ? s.slice(0, i) : s;
  return noSuffix.replace(/-/g, '.');
}

// Subyacente de una fila de posición (underlying_symbol) o de una operación
// (solo trae `symbol`; en opciones OCC el subyacente es el primer token).
function ibkrUnderlying(row) {
  const raw = String(row.underlying_symbol || row.symbol || '').trim();
  return raw.split(/\s+/)[0];
}

function ibkrTrackerTicker(row, trackerTickers) {
  const base = ibkrUnderlying(row);
  if (!base) return null;
  const suf = IBKR_EXCHANGE_SUFFIX[row.listing_exchange || row.exchange] || '';
  const cands = [];
  [base, base.replace('.', '-')].forEach(b => { cands.push(b); if (suf) cands.push(b + suf); });
  const direct = cands.find(t => trackerTickers.has(t));
  if (direct) return direct;
  // Variantes del símbolo base: las operaciones de OPCIONES sobre una acción con
  // clase (BTCC.B) traen solo 'BTCC' (el OCC no lleva la clase), y las acciones de
  // Londres llevan una 'l' minúscula final en IBKR (FXPOl, TLWl).
  const variants = [base];
  if (/[A-Z]l$/.test(base)) variants.push(base.slice(0, -1));
  for (const v of variants) {
    const wanted = v.toUpperCase();
    const exact = [...trackerTickers].filter(t => ibkrYahooBase(t).toUpperCase() === wanted);
    if (exact.length === 1) return exact[0];
    if (exact.length > 1) return null;                       // ambiguo: no se adivina
    const withClass = [...trackerTickers].filter(t => ibkrYahooBase(t).toUpperCase().startsWith(wanted + '.'));
    if (withClass.length === 1) return withClass[0];
  }
  return null;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { IBKR_EXCHANGE_SUFFIX, ibkrYahooBase, ibkrUnderlying, ibkrTrackerTicker };
}
