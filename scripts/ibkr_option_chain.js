// ── Cadena de opciones en tiempo real vía TWS / IB Gateway (API de sockets) ──
//
// Complemento del snapshot diario de inverse_etf_options_snapshot.py (que se
// toma tras el cierre y trae spreads exagerados): al pulsar el botón de
// inversos.html, server.js llama a fetchLiveChain(), que pide a TWS solo los
// contratos que necesita el recomendador (no la cadena entera), y devuelve una
// fila con EXACTAMENTE el esquema de inverse_etf_options_chains.jsonl para que
// scripts/inverse_etf_recommendations.py --live-chain la consuma sin cambios.
//
// SOLO LOCAL: necesita TWS o IB Gateway abierto con la API de sockets activada
// (Configure > Global Configuration > API > Settings > "Enable ActiveX and
// Socket Clients", 127.0.0.1 en Trusted IPs). Nunca corre en GitHub Actions.
// Los datos de mercado en tiempo real tienen licencia personal: se guardan
// solo en private/ibkr/live_chains/ (gitignorado), nunca en docs/data.
//
// Tipo de datos: pide reqMarketDataType(3). Con suscripción de opciones (OPRA)
// IBKR devuelve tiempo real; sin ella, retrasados 15 min; fuera de horario,
// congelados. Cada contrato informa de cuál recibió (evento marketDataType) y
// el resultado lo declara en `data_type` — nunca se presenta retrasado como vivo.
//
// Códigos de error propios (err.code): NO_TWS, CONNECT_TIMEOUT, NO_UNDERLYING,
// NO_OPTIONS, NO_DATA, NOT_INSTALLED.

const PUT_EXPIRY = { dte: 90, tol: 35 };
const CALL_EXPIRY = { dte: 30, tol: 20 };
// Mismos perfiles de moneyness que el recomendador (PUT_SPREADS / CALL_SPREADS).
const PUT_MONEYNESS = [0.60, 0.65, 0.70, 0.85, 0.90, 1.00];
const CALL_MONEYNESS = [1.20, 1.30, 1.50, 1.80, 2.00, 2.50];
const NEIGHBORS = 1;                       // ±1 strike alrededor del más cercano a cada objetivo
const DEFAULT_PORTS = [7496, 7497, 4001, 4002];   // TWS live, TWS paper, Gateway live, Gateway paper
const INFO_CODES = new Set([2100, 2101, 2102, 2103, 2104, 2105, 2106, 2107, 2108, 2109, 2110, 2119, 2137, 2158]);
const SUBSCRIPTION_CODES = new Set([354, 10089, 10090, 10091, 10167, 10168, 10197]);

const ibError = (code, message) => Object.assign(new Error(message), { code });

// ── Utilidades puras (probadas en scripts/test_ibkr_option_chain.js) ─────────
const pad = n => String(n).padStart(2, '0');

// Fecha/hora en Nueva York con su offset (la usa también el recomendador para
// saber si la cadena se tomó fuera de horario).
function etNow(now = new Date()) {
  const f = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  });
  const p = Object.fromEntries(f.formatToParts(now).map(x => [x.type, x.value]));
  const asUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
  const offMin = Math.round((asUtc - Math.floor(now.getTime() / 1000) * 1000) / 60000);
  const sign = offMin < 0 ? '-' : '+';
  const a = Math.abs(offMin);
  const date = `${p.year}-${p.month}-${p.day}`;
  return { date, minutes: +p.hour * 60 + +p.minute, weekday: new Date(Date.UTC(+p.year, +p.month - 1, +p.day)).getUTCDay(),
           iso: `${date}T${p.hour}:${p.minute}:${p.second}${sign}${pad(Math.floor(a / 60))}:${pad(a % 60)}` };
}

const isoDate = yyyymmdd => `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`;
function dteBetween(todayIso, yyyymmdd) {
  return Math.round((Date.parse(isoDate(yyyymmdd) + 'T00:00:00Z') - Date.parse(todayIso + 'T00:00:00Z')) / 86400000);
}

// Vencimiento más cercano al objetivo dentro de la tolerancia (expirations: 'YYYYMMDD').
function pickExpiry(expirations, todayIso, target) {
  let best = null;
  for (const e of expirations) {
    const dte = dteBetween(todayIso, e);
    if (dte <= 0 || Math.abs(dte - target.dte) > target.tol) continue;
    if (!best || Math.abs(dte - target.dte) < Math.abs(best.dte - target.dte)) best = { expiry: e, dte };
  }
  return best;
}

// Strike más cercano a `price` y n vecinos a cada lado (strikes ordenados).
function strikesAround(sorted, price, n = NEIGHBORS) {
  if (!sorted.length) return [];
  let idx = 0;
  for (let i = 1; i < sorted.length; i++) if (Math.abs(sorted[i] - price) < Math.abs(sorted[idx] - price)) idx = i;
  return sorted.slice(Math.max(0, idx - n), idx + n + 1);
}

// Contratos a pedir: puts de los perfiles (+ call y put ATM para el carry
// implícito) en el vencimiento de ~90d y calls de los perfiles en el de ~30d.
function planContracts(spot, strikes, expirations, todayIso) {
  const sorted = [...new Set(strikes)].sort((a, b) => a - b);
  const pe = pickExpiry(expirations, todayIso, PUT_EXPIRY);
  const ce = pickExpiry(expirations, todayIso, CALL_EXPIRY);
  const out = new Map();
  const add = (right, e, k) => out.set(`${e.expiry}|${right}|${k}`, { right, expiry: e.expiry, dte: e.dte, strike: k });
  if (pe) {
    PUT_MONEYNESS.forEach(m => strikesAround(sorted, spot * m).forEach(k => add('P', pe, k)));
    strikesAround(sorted, spot, 0).forEach(k => { add('P', pe, k); add('C', pe, k); });
  }
  if (ce) CALL_MONEYNESS.forEach(m => strikesAround(sorted, spot * m).forEach(k => add('C', ce, k)));
  return { contracts: [...out.values()], putExpiry: pe, callExpiry: ce };
}

const num = v => (typeof v === 'number' && isFinite(v) && v >= 0) ? v : null;

// Ticks acumulados por contrato -> fila del esquema de inverse_etf_options_chains.jsonl.
function assembleChainRow({ ticker, spot, now = new Date(), planned, quotes, dataTypes }) {
  const et = etNow(now);
  const byExpiry = new Map();
  planned.forEach(c => {
    const q = quotes.get(c.key) || {};
    const bid = num(q.bid), ask = num(q.ask);
    if (bid == null && ask == null && num(q.last) == null) return;       // sin ninguna cotización
    if (!byExpiry.has(c.expiry)) byExpiry.set(c.expiry, { expiry: isoDate(c.expiry), dte: c.dte, contracts: [] });
    byExpiry.get(c.expiry).contracts.push({
      strike: c.strike, cp: c.right, bid, ask,
      iv: (q.iv != null && q.iv > 0) ? +q.iv.toFixed(4) : null,
      oi: q.oi != null ? Math.round(q.oi) : null, vol: q.vol != null ? Math.round(q.vol) : null,
    });
  });
  const expiries = [...byExpiry.values()].sort((a, b) => a.dte - b.dte);
  expiries.forEach(e => e.contracts.sort((a, b) => a.cp.localeCompare(b.cp) || a.strike - b.strike));
  const types = [...new Set(dataTypes)];
  const dataType = !types.length ? 'unknown' : types.every(t => t === 1) ? 'live' : types.includes(3) ? 'delayed' : 'frozen';
  return { date: et.date, ticker, spot, collected_at: et.iso, source: 'ibkr_tws', data_type: dataType, expiries };
}

// ── Cliente TWS ───────────────────────────────────────────────────────────────
function loadLib() {
  try { return require('@stoqey/ib'); }
  catch (e) { throw ibError('NOT_INSTALLED', 'Falta la dependencia @stoqey/ib: ejecuta "npm install" en la raíz del proyecto.'); }
}

async function connect(lib, opts) {
  const { IBApi, EventName } = lib;
  const factory = opts.apiFactory || ((o) => new IBApi(o));
  const ports = opts.ports || (process.env.IBKR_TWS_PORT ? [+process.env.IBKR_TWS_PORT] : DEFAULT_PORTS);
  const host = opts.host || process.env.IBKR_TWS_HOST || '127.0.0.1';
  let lastTimeout = false;
  for (const port of ports) {
    for (let attempt = 0; attempt < 3; attempt++) {
      const clientId = opts.clientId || (1200 + Math.floor(Math.random() * 700));
      const api = factory({ host, port, clientId });
      const res = await new Promise(resolve => {
        let done = false;
        const finish = r => { if (!done) { done = true; clearTimeout(t); resolve(r); } };
        const t = setTimeout(() => finish({ ok: false, timeout: true }), opts.connectTimeoutMs || 6000);
        api.on(EventName.nextValidId, id => finish({ ok: true, nextId: id }));
        api.on(EventName.error, (err, code) => {
          if (code === 326) finish({ ok: false, clientIdBusy: true });                    // clientId en uso
          else if (code === -1 || /ECONNREFUSED|ECONNRESET|connect/i.test(String(err && err.message))) finish({ ok: false, refused: true });
        });
        try { api.connect(); } catch (e) { finish({ ok: false, refused: true }); }
      });
      if (res.ok) return { api, port, clientId, nextId: res.nextId };
      try { api.disconnect(); } catch (e) { /* ya cerrada */ }
      if (res.clientIdBusy) continue;
      if (res.timeout) lastTimeout = true;
      break;                                         // puerto sin respuesta -> siguiente puerto
    }
  }
  if (lastTimeout) throw ibError('CONNECT_TIMEOUT', `TWS aceptó la conexión pero no completó el acceso en ${ports.join('/')}: mira si TWS muestra un aviso «Accept incoming connection» y acéptalo (o añade 127.0.0.1 a Trusted IPs).`);
  throw ibError('NO_TWS', `No hay respuesta de TWS/Gateway en ${host} (puertos ${ports.join(', ')}). En TWS: Configure > Global Configuration > API > Settings > marca «Enable ActiveX and Socket Clients» y añade 127.0.0.1 a Trusted IPs.`);
}

async function fetchLiveChain(ticker, opts = {}) {
  const lib = opts.lib || loadLib();
  const { EventName, SecType, OptionType } = lib;
  const t0 = Date.now();
  const now = opts.now || new Date();
  const todayIso = etNow(now).date;
  const { api, port, clientId, nextId } = await connect(lib, opts);
  let reqId = nextId;
  const nextReq = () => reqId++;
  const notices = new Set();
  const errorsByReq = new Map();
  const cleanup = [];
  const shutdown = () => { cleanup.forEach(f => { try { f(); } catch (e) { /* cancelación best-effort */ } }); try { api.disconnect(); } catch (e) { /* ya cerrada */ } };

  api.on(EventName.error, (err, code, rid) => {
    if (INFO_CODES.has(code)) return;
    if (rid != null && rid >= 0) errorsByReq.set(rid, code);
    if (SUBSCRIPTION_CODES.has(code)) notices.add(`${code}: ${err && err.message}`);
  });
  const waitFor = (ms, check) => new Promise(resolve => {
    const start = Date.now();
    const iv = setInterval(() => { if (check() || Date.now() - start >= ms) { clearInterval(iv); resolve(check()); } }, 100);
  });

  try {
    api.reqMarketDataType(3);                         // tiempo real si hay suscripción; si no, retrasado/congelado
    const stock = { symbol: ticker, secType: SecType.STK, exchange: 'SMART', currency: 'USD' };

    // 1) conId del subyacente
    const cdId = nextReq();
    let conId = null, cdDone = false;
    api.on(EventName.contractDetails, (rid, d) => { if (rid === cdId && conId == null) conId = d.contract.conId; });
    api.on(EventName.contractDetailsEnd, rid => { if (rid === cdId) cdDone = true; });
    api.reqContractDetails(cdId, stock);
    await waitFor(8000, () => cdDone || conId != null);
    if (conId == null) throw ibError('NO_UNDERLYING', `IBKR no reconoce ${ticker} como acción/ETF en SMART/USD${errorsByReq.has(cdId) ? ` (error ${errorsByReq.get(cdId)})` : ''}.`);

    // 2) vencimientos y strikes (clase de opción = el propio símbolo; evita las ajustadas tipo UVXY1)
    const spId = nextReq();
    const sets = []; let spDone = false;
    api.on(EventName.securityDefinitionOptionParameter, (rid, exchange, _u, tradingClass, multiplier, expirations, strikes) => {
      if (rid === spId) sets.push({ exchange, tradingClass, multiplier, expirations, strikes: [...strikes] });
    });
    api.on(EventName.securityDefinitionOptionParameterEnd, rid => { if (rid === spId) spDone = true; });
    api.reqSecDefOptParams(spId, ticker, '', SecType.STK, conId);
    await waitFor(8000, () => spDone);
    const own = sets.filter(s => s.tradingClass === ticker);
    const chosen = (own.find(s => s.exchange === 'SMART') || own.sort((a, b) => b.expirations.length - a.expirations.length)[0]);
    if (!chosen) throw ibError('NO_OPTIONS', `${ticker}: IBKR no devuelve cadena de opciones (clase ${ticker}).`);

    // 3) subyacente: último precio (o cierre / media bid-ask)
    const quotes = new Map();       // key -> ticks
    const dataTypes = [];
    const reqKey = new Map();       // reqId -> key
    const q = k => { if (!quotes.has(k)) quotes.set(k, {}); return quotes.get(k); };
    api.on(EventName.marketDataType, (rid, type) => { if (reqKey.has(rid)) dataTypes.push(type); });
    api.on(EventName.tickPrice, (rid, field, value) => {
      const k = reqKey.get(rid); if (!k) return;
      const o = q(k), v = value >= 0 ? value : null;
      if (field === 1 || field === 66) o.bid = v; else if (field === 2 || field === 67) o.ask = v;
      else if (field === 4 || field === 68) o.last = v; else if (field === 9 || field === 75) o.close = v;
    });
    api.on(EventName.tickSize, (rid, field, value) => {
      const k = reqKey.get(rid); if (!k) return;
      const o = q(k);
      if (field === 8 || field === 74) o.vol = value;
      else if (field === 27 || field === 28 || field === 86) o.oi = value;       // OI call / put / retrasado
    });
    api.on(EventName.tickOptionComputation, (rid, field, _attr, iv) => {
      const k = reqKey.get(rid); if (!k) return;
      const o = q(k);
      if ((field === 13 || field === 83) && iv > 0 && iv < 20) o.iv = iv;        // modelo; 10/11/80/81 (bid/ask) solo si no hay modelo
      else if ([10, 11, 80, 81].includes(field) && iv > 0 && iv < 20 && o.iv == null) o.iv = iv;
    });
    const subscribe = (contract, key, generic) => {
      const id = nextReq(); reqKey.set(id, key);
      api.reqMktData(id, contract, generic, false, false);
      cleanup.push(() => api.cancelMktData(id));
      return id;
    };
    const stkKey = 'STK';
    const stkId = subscribe(stock, stkKey, '');
    await waitFor(5000, () => { const o = quotes.get(stkKey); return o && (o.last != null || o.close != null || (o.bid != null && o.ask != null)); });
    const so = quotes.get(stkKey) || {};
    const spot = so.last ?? (so.bid != null && so.ask != null ? (so.bid + so.ask) / 2 : null) ?? so.close ?? null;
    if (spot == null) throw ibError('NO_DATA', `Sin precio del subyacente ${ticker}${[...notices].length ? ' (' + [...notices][0] + ')' : ''}. ¿Mercado cerrado sin datos congelados o falta suscripción?`);
    api.cancelMktData(stkId);

    // 4) opciones a pedir y recogida
    const plan = planContracts(spot, chosen.strikes, chosen.expirations, todayIso);
    if (!plan.contracts.length) throw ibError('NO_OPTIONS', `${ticker}: no hay vencimientos cerca de 30/90 días en la cadena de IBKR.`);
    const planned = plan.contracts.map(c => ({ ...c, key: `${c.expiry}|${c.right}|${c.strike}` }));
    planned.forEach(c => {
      subscribe({ symbol: ticker, secType: SecType.OPT, exchange: 'SMART', currency: 'USD', lastTradeDateOrContractMonth: c.expiry,
                  strike: c.strike, right: c.right === 'C' ? OptionType.Call : OptionType.Put, multiplier: +chosen.multiplier || 100,
                  tradingClass: chosen.tradingClass }, c.key, '101');
    });
    const window0 = Date.now();
    const quoted = () => planned.filter(c => { const o = quotes.get(c.key); return o && (o.bid != null || o.ask != null); }).length;
    await waitFor(opts.collectMs || 9000, () => Date.now() - window0 > (opts.minCollectMs ?? 3500) && quoted() >= planned.length * 0.9);

    const row = assembleChainRow({ ticker, spot, now, planned, quotes, dataTypes });
    const nQuoted = row.expiries.reduce((s, e) => s + e.contracts.length, 0);
    if (!nQuoted) throw ibError('NO_DATA', `IBKR no devolvió cotizaciones de opciones de ${ticker}${notices.size ? ': ' + [...notices][0] : ''}. Revisa la suscripción de datos de opciones (o abre el mercado).`);
    return {
      row,
      info: { port, clientId, requested: planned.length, quoted: nQuoted, elapsed_ms: Date.now() - t0,
              notices: [...notices], put_expiry: plan.putExpiry, call_expiry: plan.callExpiry },
    };
  } finally {
    shutdown();
  }
}

module.exports = { fetchLiveChain, etNow, pickExpiry, strikesAround, planContracts, assembleChainRow, PUT_MONEYNESS, CALL_MONEYNESS };
