// ── IBKR Flex Web Service — sincronización de la cartera real (SOLO LOCAL) ──
//
// Descarga un informe Flex (Activity Flex Query) de Interactive Brokers y lo
// guarda en private/ibkr/ — carpeta en .gitignore. El repo es PÚBLICO
// (GitHub Pages), así que estos datos NO se commitean nunca ni corren en
// GitHub Actions: posiciones, NAV, operaciones y número de cuenta solo viven
// en esta máquina (y en el Dropbox privado del usuario). Decisión tomada con
// el usuario 2026-10-03, ver CLAUDE.md "IBKR Flex — cartera real".
//
// Flujo del Flex Web Service v3 (documentación IBKR):
//   1. SendRequest?t=TOKEN&q=QUERY_ID&v=3  → ReferenceCode (+ Url de GetStatement)
//   2. GetStatement?t=TOKEN&q=REFERENCE&v=3 → el informe XML. Mientras se
//      genera devuelve ErrorCode 1019 ("Statement generation in progress") —
//      se reintenta con espera. Límite: 1 req/s y 10 req/min por token (1018).
//
// Parser genérico: el informe Flex es XML de elementos con atributos. Se
// guardan TODOS los atributos de cada elemento tal cual vienen (sin asumir
// qué campos marcó el usuario en la query), agrupados por sección. Solo la
// capa "latest" (lo que pinta el dashboard) lee nombres de campo concretos.
//
// Uso:
//   node scripts/ibkr_flex_sync.js              → sincroniza (necesita .env)
//   node scripts/ibkr_flex_sync.js --from-file informe.xml   → procesa un XML guardado
//   node scripts/ibkr_flex_sync.js --report     → resumen de lo almacenado
//
// Variables (.env): IBKR_FLEX_TOKEN, IBKR_FLEX_QUERY_ID

const fs   = require('fs');
const path = require('path');

const ROOT        = path.join(__dirname, '..');
// IBKR_PRIVATE_DIR solo para tests (redirige la escritura a un dir temporal).
const PRIVATE_DIR = process.env.IBKR_PRIVATE_DIR || path.join(ROOT, 'private', 'ibkr');
const RAW_DIR     = path.join(PRIVATE_DIR, 'raw');
const FILES = {
  latest:    path.join(PRIVATE_DIR, 'ibkr_latest.json'),
  positions: path.join(PRIVATE_DIR, 'ibkr_positions_daily.jsonl'),
  nav:       path.join(PRIVATE_DIR, 'ibkr_nav_daily.jsonl'),
  trades:    path.join(PRIVATE_DIR, 'ibkr_trades.jsonl'),
  state:     path.join(PRIVATE_DIR, 'ibkr_sync_state.json'),
};

const SEND_REQUEST_URL = 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest';
const GET_STATEMENT_URL = 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement';
const USER_AGENT = 'market-tracker/1.0 (personal portfolio sync)';
// Un informe de 365 días tarda en generarse bastante más de 1 min (la primera
// prueba real, 2026-10-03, seguía en 1019 tras ~70 s). 20 × 15 s ≈ 5 min, a
// 4 req/min — bien por debajo del límite de 10 req/min por token.
const POLL_MAX_ATTEMPTS = 20;
const POLL_WAIT_MS = 15000;

// ── Utilidades ──────────────────────────────────────────────────────────────
const sleep = ms => new Promise(r => setTimeout(r, ms));

function decodeEntities(s) {
  return s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (m, e) => {
    const k = e.toLowerCase();
    if (k === 'amp') return '&';
    if (k === 'lt') return '<';
    if (k === 'gt') return '>';
    if (k === 'quot') return '"';
    if (k === 'apos') return "'";
    if (k.startsWith('#x')) return String.fromCodePoint(parseInt(k.slice(2), 16));
    if (k.startsWith('#')) return String.fromCodePoint(parseInt(k.slice(1), 10));
    return m;
  });
}

// Valores numéricos → Number; el resto, string. Fechas se dejan como string
// (se normalizan aparte solo donde hace falta, ver normDate).
function coerce(v) {
  if (v === '') return null;
  if (/^-?\d+(\.\d+)?(E-?\d+)?$/i.test(v)) return Number(v);
  return v;
}

function parseAttrs(s) {
  const out = {};
  const re = /([A-Za-z_][\w.\-]*)\s*=\s*"([^"]*)"/g;
  let m;
  while ((m = re.exec(s))) out[m[1]] = coerce(decodeEntities(m[2]));
  return out;
}

// Flex usa yyyyMMdd por defecto, o yyyy-MM-dd si se configura así; los
// datetimes llevan ";HHmmss" o ",HH:mm:ss". Devuelve YYYY-MM-DD o null.
function normDate(v) {
  if (v == null) return null;
  const s = String(v);
  let m = s.match(/^(\d{4})-?(\d{2})-?(\d{2})/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/); // MM/dd/yyyy
  if (m) return `${m[3]}-${m[1]}-${m[2]}`;
  return null;
}

function maskAccount(id) {
  if (!id) return null;
  const s = String(id);
  return s.length <= 4 ? '***' : s.slice(0, 1) + '***' + s.slice(-3);
}

// ── Respuesta de SendRequest / GetStatement en error ─────────────────────────
function parseServiceResponse(xml) {
  const tag = t => { const m = xml.match(new RegExp(`<${t}>([\\s\\S]*?)</${t}>`)); return m ? decodeEntities(m[1].trim()) : null; };
  return {
    status: tag('Status'),
    referenceCode: tag('ReferenceCode'),
    url: tag('Url'),
    errorCode: tag('ErrorCode'),
    errorMessage: tag('ErrorMessage'),
  };
}

// ── Parser genérico del informe Flex ────────────────────────────────────────
// Estructura: FlexQueryResponse > FlexStatements > FlexStatement(+attrs) >
//   <Sección/> autocerrada (ej. AccountInformation) o
//   <Sección> <Item .../> ... </Sección> (ej. OpenPositions > OpenPosition).
// Cada sección se guarda como { ChildTag: [attrs, ...] }; una sección
// autocerrada se guarda como { _self: [attrs] }. Elementos más profundos
// (ej. Lot dentro de OpenPositions a nivel lote) se agrupan igual por tag.
function parseFlexStatement(xml) {
  const statements = [];
  // Los atributos entrecomillados pueden contener '>' (XML lo permite sin
  // escapar) — el grupo de atributos salta cadenas "..." completas.
  const tagRe = /<(\/?)([A-Za-z_][\w.\-]*)((?:\s+(?:[^>"]|"[^"]*")*?)?)\s*(\/?)>/g;
  const stack = [];
  let cur = null;          // FlexStatement actual
  let section = null;      // { name, data }
  let m;
  while ((m = tagRe.exec(xml))) {
    const [, closing, name, attrStr, selfClose] = m;
    if (name.startsWith('?') || name.startsWith('!')) continue;
    if (closing) {
      stack.pop();
      if (name === 'FlexStatement') { if (cur) statements.push(cur); cur = null; }
      else if (section && name === section.name && stack.length === section.depth) section = null;
      continue;
    }
    const attrs = parseAttrs(attrStr || '');
    if (name === 'FlexStatement') {
      cur = { attrs, sections: {} };
      if (!selfClose) stack.push(name); else { statements.push(cur); cur = null; }
      continue;
    }
    if (cur && stack[stack.length - 1] === 'FlexStatement') {
      // Hijo directo de FlexStatement = sección
      if (selfClose) {
        (cur.sections[name] = cur.sections[name] || {})._self = [attrs];
      } else {
        cur.sections[name] = cur.sections[name] || {};
        if (Object.keys(attrs).length) cur.sections[name]._self = [attrs];
        section = { name, depth: stack.length, data: cur.sections[name] };
        stack.push(name);
      }
      continue;
    }
    if (cur && section) {
      (section.data[name] = section.data[name] || []).push(attrs);
    }
    if (!selfClose) stack.push(name);
  }
  return statements;
}

// ── Llamadas al servicio ────────────────────────────────────────────────────
async function httpGet(url) {
  const r = await fetch(url, { headers: { 'User-Agent': USER_AGENT } });
  const text = await r.text();
  if (!r.ok) throw new Error(`HTTP ${r.status} en ${url.split('?')[0]}`);
  return text;
}

async function downloadFlexReport(token, queryId, log = console.log) {
  const sendXml = await httpGet(`${SEND_REQUEST_URL}?t=${encodeURIComponent(token)}&q=${encodeURIComponent(queryId)}&v=3`);
  const send = parseServiceResponse(sendXml);
  if (send.status !== 'Success' || !send.referenceCode) {
    throw new Error(`SendRequest falló: ${send.errorCode || '?'} ${send.errorMessage || sendXml.slice(0, 200)}`);
  }
  const baseUrl = send.url || GET_STATEMENT_URL;
  await sleep(3000);
  for (let attempt = 1; attempt <= POLL_MAX_ATTEMPTS; attempt++) {
    const xml = await httpGet(`${baseUrl}?t=${encodeURIComponent(token)}&q=${encodeURIComponent(send.referenceCode)}&v=3`);
    if (xml.includes('<FlexQueryResponse')) return xml;
    const resp = parseServiceResponse(xml);
    if (resp.errorCode === '1019' || resp.errorCode === '1018') {
      log(`  informe aún generándose (${resp.errorCode}), reintento ${attempt}/${POLL_MAX_ATTEMPTS}…`);
      await sleep(POLL_WAIT_MS);
      continue;
    }
    throw new Error(`GetStatement falló: ${resp.errorCode || '?'} ${resp.errorMessage || xml.slice(0, 200)}`);
  }
  throw new Error('GetStatement: el informe no estuvo listo tras varios reintentos');
}

// ── Persistencia ────────────────────────────────────────────────────────────
function readJsonl(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => {
    try { return JSON.parse(l); } catch (e) { return null; }
  }).filter(Boolean);
}

// Añade filas nuevas por clave (dedup). Si la clave ya existe, se SUSTITUYE
// por la versión nueva (una re-sincronización del mismo día trae el dato
// más reciente/corregido de IBKR).
function upsertJsonl(file, rows, keyFn) {
  const existing = readJsonl(file);
  const byKey = new Map(existing.map(r => [keyFn(r), r]));
  let added = 0, updated = 0;
  rows.forEach(r => {
    const k = keyFn(r);
    if (byKey.has(k)) updated++; else added++;
    byKey.set(k, r);
  });
  const all = [...byKey.values()];
  fs.writeFileSync(file, all.map(r => JSON.stringify(r)).join('\n') + (all.length ? '\n' : ''));
  return { added, updated, total: all.length };
}

const firstOf = (sec, tag) => (sec && sec[tag] && sec[tag][0]) || null;
const listOf  = (sec, tag) => (sec && sec[tag]) || [];

// Del informe parseado → filas normalizadas por tipo. Los campos que se
// exponen con nombre propio son los nombres estándar de IBKR; si el usuario
// no los marcó en la query, quedan null — y se avisa en `warnings`.
function extractRows(statements, syncedAt) {
  const positions = [], nav = [], trades = [], cash = [], accounts = [];
  const warnings = [];
  statements.forEach(st => {
    const acct = st.attrs.accountId;
    const acctM = maskAccount(acct);
    const toDate = normDate(st.attrs.toDate) || normDate(st.attrs.whenGenerated);
    const S = st.sections;
    const info = firstOf(S.AccountInformation, '_self');
    accounts.push({
      account: acctM,
      base_currency: info?.currency ?? null,
      from_date: normDate(st.attrs.fromDate),
      to_date: toDate,
      when_generated: st.attrs.whenGenerated ?? null,
      sections: Object.keys(S),
    });

    listOf(S.OpenPositions, 'OpenPosition').forEach(p => {
      // A nivel "Summary" cada posición es una fila; si la query se configuró
      // a nivel lote, IBKR mezcla filas SUMMARY y LOT (levelOfDetail).
      if (p.levelOfDetail && String(p.levelOfDetail).toUpperCase() === 'LOT') return;
      positions.push({
        date: normDate(p.reportDate) || toDate,
        account: acctM,
        symbol: p.symbol ?? null,
        description: p.description ?? null,
        asset_class: p.assetCategory ?? null,
        currency: p.currency ?? null,
        fx_to_base: p.fxRateToBase ?? null,
        quantity: p.position ?? null,
        mark_price: p.markPrice ?? null,
        position_value: p.positionValue ?? null,
        cost_basis_price: p.costBasisPrice ?? null,
        cost_basis_money: p.costBasisMoney ?? null,
        unrealized_pnl: p.fifoPnlUnrealized ?? null,
        pct_of_nav: p.percentOfNAV ?? null,
        side: p.side ?? null,
        conid: p.conid ?? null,
        isin: p.isin ?? null,
        listing_exchange: p.listingExchange ?? null,
        multiplier: p.multiplier ?? null,
        put_call: p.putCall ?? null,
        strike: p.strike ?? null,
        expiry: normDate(p.expiry),
        underlying_symbol: p.underlyingSymbol ?? null,
        synced_at: syncedAt,
      });
    });

    listOf(S.EquitySummaryInBase, 'EquitySummaryByReportDateInBase').forEach(e => {
      nav.push({
        date: normDate(e.reportDate),
        account: acctM,
        total: e.total ?? null,
        cash: e.cash ?? null,
        stock: e.stock ?? null,
        options: e.options ?? null,
        funds: e.funds ?? null,
        bonds: e.bonds ?? null,
        commodities: e.commodities ?? null,
        crypto: e.crypto ?? null,
        dividend_accruals: e.dividendAccruals ?? null,
        interest_accruals: e.interestAccruals ?? null,
        synced_at: syncedAt,
      });
    });

    listOf(S.Trades, 'Trade').forEach(t => {
      trades.push({
        trade_id: t.tradeID ?? t.transactionID ?? null,
        account: acctM,
        date: normDate(t.tradeDate) || normDate(t.dateTime),
        date_time: t.dateTime ?? null,
        symbol: t.symbol ?? null,
        description: t.description ?? null,
        asset_class: t.assetCategory ?? null,
        currency: t.currency ?? null,
        fx_to_base: t.fxRateToBase ?? null,
        side: t.buySell ?? null,
        quantity: t.quantity ?? null,
        price: t.tradePrice ?? null,
        proceeds: t.proceeds ?? null,
        commission: t.ibCommission ?? null,
        net_cash: t.netCash ?? null,
        realized_pnl: t.fifoPnlRealized ?? null,
        open_close: t.openCloseIndicator ?? null,
        order_type: t.orderType ?? null,
        exchange: t.exchange ?? null,
        conid: t.conid ?? null,
        put_call: t.putCall ?? null,
        strike: t.strike ?? null,
        expiry: normDate(t.expiry),
        synced_at: syncedAt,
      });
    });

    listOf(S.CashReport, 'CashReportCurrency').forEach(c => {
      cash.push({ account: acctM, currency: c.currency ?? null, ending_cash: c.endingCash ?? null, ending_settled_cash: c.endingSettledCash ?? null });
    });

    const missing = [];
    if (!S.OpenPositions) missing.push('Open Positions');
    if (!S.EquitySummaryInBase) missing.push('Net Asset Value (NAV) in Base');
    if (!S.Trades) missing.push('Trades');
    if (!S.CashReport) missing.push('Cash Report');
    if (missing.length) warnings.push(`La Flex Query no incluye: ${missing.join(', ')} — añádelas en Client Portal para tener la vista completa.`);
  });
  return { positions, nav, trades, cash, accounts, warnings };
}

function buildLatest(extracted, syncedAt) {
  const { positions, nav, cash, accounts, warnings } = extracted;
  const lastDate = positions.reduce((d, p) => (p.date && (!d || p.date > d) ? p.date : d), null);
  const currentPositions = positions.filter(p => p.date === lastDate);
  const navSorted = [...nav].filter(n => n.date).sort((a, b) => a.date.localeCompare(b.date));
  const lastNav = navSorted[navSorted.length - 1] || null;
  const baseCash = cash.find(c => c.currency === 'BASE_SUMMARY') || null;
  const unreal = currentPositions.reduce((s, p) => s + (typeof p.unrealized_pnl === 'number' ? p.unrealized_pnl * (p.fx_to_base ?? 1) : 0), 0);
  return {
    synced_at: syncedAt,
    accounts,
    positions_date: lastDate,
    positions: currentPositions,
    nav: lastNav,
    nav_history_days: navSorted.length,
    base_cash: baseCash,
    unrealized_pnl_base: currentPositions.length ? Math.round(unreal * 100) / 100 : null,
    warnings,
  };
}

// ── Proceso completo ────────────────────────────────────────────────────────
function processXml(xml, { syncedAt = new Date().toISOString(), log = console.log } = {}) {
  const statements = parseFlexStatement(xml);
  if (!statements.length) throw new Error('El XML no contiene ningún FlexStatement');
  const ex = extractRows(statements, syncedAt);
  fs.mkdirSync(PRIVATE_DIR, { recursive: true });
  const rp = upsertJsonl(FILES.positions, ex.positions, r => `${r.date}|${r.account}|${r.conid ?? r.symbol}`);
  const rn = upsertJsonl(FILES.nav, ex.nav.filter(r => r.date), r => `${r.date}|${r.account}`);
  const rt = upsertJsonl(FILES.trades, ex.trades, r => r.trade_id != null ? `${r.account}|${r.trade_id}` : `${r.account}|${r.date_time}|${r.symbol}|${r.quantity}|${r.price}`);
  const latest = buildLatest(ex, syncedAt);
  fs.writeFileSync(FILES.latest, JSON.stringify(latest, null, 2));
  log(`  posiciones: ${ex.positions.length} (${rp.added} nuevas) · NAV: ${ex.nav.length} días (${rn.added} nuevos) · operaciones: ${ex.trades.length} (${rt.added} nuevas)`);
  ex.warnings.forEach(w => log('  ⚠ ' + w));
  return { latest, counts: { positions: rp, nav: rn, trades: rt } };
}

function readState() {
  try { return JSON.parse(fs.readFileSync(FILES.state, 'utf8')); } catch (e) { return {}; }
}
function writeState(s) {
  fs.mkdirSync(PRIVATE_DIR, { recursive: true });
  fs.writeFileSync(FILES.state, JSON.stringify(s, null, 2));
}

function isConfigured() {
  return !!(process.env.IBKR_FLEX_TOKEN && process.env.IBKR_FLEX_QUERY_ID);
}

let syncInFlight = null;
async function syncIbkr({ log = console.log } = {}) {
  if (syncInFlight) return syncInFlight;   // nunca dos sincronizaciones a la vez (límite por token)
  syncInFlight = (async () => {
    const state = readState();
    const startedAt = new Date().toISOString();
    try {
      if (!isConfigured()) throw new Error('Faltan IBKR_FLEX_TOKEN / IBKR_FLEX_QUERY_ID en .env');
      log('[ibkr] solicitando informe Flex…');
      const xml = await downloadFlexReport(process.env.IBKR_FLEX_TOKEN, process.env.IBKR_FLEX_QUERY_ID, log);
      fs.mkdirSync(RAW_DIR, { recursive: true });
      const stamp = startedAt.slice(0, 16).replace(/[:T]/g, '-');
      fs.writeFileSync(path.join(RAW_DIR, `flex_${stamp}.xml`), xml);
      const res = processXml(xml, { syncedAt: startedAt, log });
      // Diario de decisiones (operaciones × señales): derivado, no debe tumbar la
      // sincronización si falla (p. ej. aún no hay screener_signal_log).
      try { require('./ibkr_decision_journal.js').writeJournal(); log('  diario de decisiones actualizado'); }
      catch (e) { log('  ⚠ diario de decisiones no actualizado: ' + e.message); }
      writeState({ ...state, last_success: startedAt, last_attempt: startedAt, last_error: null });
      return { ok: true, ...res };
    } catch (e) {
      writeState({ ...state, last_attempt: startedAt, last_error: e.message });
      log('[ibkr] error: ' + e.message);
      return { ok: false, error: e.message };
    } finally {
      syncInFlight = null;
    }
  })();
  return syncInFlight;
}

function readLatest() {
  const state = readState();
  let latest = null;
  try { latest = JSON.parse(fs.readFileSync(FILES.latest, 'utf8')); } catch (e) { /* sin datos todavía */ }
  return { configured: isConfigured(), state, latest };
}

function report() {
  const { configured, state, latest } = readLatest();
  console.log('Configurado (.env):', configured);
  console.log('Estado:', JSON.stringify(state));
  if (!latest) { console.log('Sin datos sincronizados todavía.'); return; }
  console.log(`Cuentas: ${latest.accounts.map(a => `${a.account} (${a.base_currency}, ${a.from_date}→${a.to_date})`).join(', ')}`);
  console.log(`Posiciones a ${latest.positions_date}: ${latest.positions.length}`);
  latest.positions.forEach(p => console.log(`  ${String(p.symbol).padEnd(10)} ${String(p.quantity).padStart(10)} @ ${p.mark_price} ${p.currency}  P&L no real.: ${p.unrealized_pnl}`));
  if (latest.nav) console.log(`NAV ${latest.nav.date}: ${latest.nav.total} (histórico: ${latest.nav_history_days} días)`);
  console.log(`Operaciones almacenadas: ${readJsonl(FILES.trades).length}`);
  latest.warnings.forEach(w => console.log('⚠ ' + w));
}

module.exports = { syncIbkr, readLatest, processXml, parseFlexStatement, parseServiceResponse, extractRows, buildLatest, normDate, maskAccount, isConfigured, FILES };

if (require.main === module) {
  require('dotenv').config({ path: path.join(ROOT, '.env') });
  const args = process.argv.slice(2);
  if (args.includes('--report')) { report(); }
  else if (args.includes('--from-file')) {
    const f = args[args.indexOf('--from-file') + 1];
    if (!f) { console.error('Uso: --from-file informe.xml'); process.exit(1); }
    processXml(fs.readFileSync(f, 'utf8'));
  } else {
    syncIbkr().then(r => process.exit(r.ok ? 0 : 1));
  }
}
