// Tests de scripts/ibkr_option_chain.js sin TWS: utilidades puras + el flujo
// completo contra un API simulado (EventEmitter que emite los mismos eventos que
// @stoqey/ib). No prueba el protocolo de red (eso es de la librería) sino la
// orquestación: qué se pide, cómo se ensamblan los ticks y cómo se clasifican
// los errores. Uso: node scripts/test_ibkr_option_chain.js
const EventEmitter = require('events');
const lib = require('@stoqey/ib');
const m = require('./ibkr_option_chain.js');
const { EventName } = lib;

let pass = 0, fail = 0;
const ok = (c, msg) => { if (c) pass++; else { fail++; console.log('  ✗', msg); } };
const eq = (a, b, msg) => ok(JSON.stringify(a) === JSON.stringify(b), `${msg}: got ${JSON.stringify(a)} expected ${JSON.stringify(b)}`);

// ── puras ────────────────────────────────────────────────────────────────────
const et = m.etNow(new Date('2026-10-23T20:30:00Z'));       // octubre = EDT (-04:00)
eq(et.date, '2026-10-23', 'etNow fecha'); eq(et.iso, '2026-10-23T16:30:00-04:00', 'etNow iso EDT'); eq(et.minutes, 16 * 60 + 30, 'etNow minutos');
eq(m.etNow(new Date('2026-12-15T20:30:00Z')).iso, '2026-12-15T15:30:00-05:00', 'etNow iso EST');
eq(m.etNow(new Date('2026-10-24T02:00:00Z')).date, '2026-10-23', 'etNow: tras medianoche UTC sigue siendo el día ET anterior');

const exps = ['20261030', '20261120', '20261218', '20270115', '20270618'];
eq(m.pickExpiry(exps, '2026-10-22', { dte: 30, tol: 20 }), { expiry: '20261120', dte: 29 }, 'pickExpiry ~30d');
eq(m.pickExpiry(exps, '2026-10-22', { dte: 90, tol: 35 }), { expiry: '20270115', dte: 85 }, 'pickExpiry ~90d');
eq(m.pickExpiry(['20261023'], '2026-10-22', { dte: 1, tol: 5 }), { expiry: '20261023', dte: 1 }, 'pickExpiry 1d');
eq(m.pickExpiry(['20260101'], '2026-10-22', { dte: 30, tol: 20 }), null, 'pickExpiry vencido/fuera de tolerancia');
eq(m.strikesAround([10, 11, 12, 13, 14], 12.4, 1), [11, 12, 13], 'strikesAround centro');
eq(m.strikesAround([10, 11, 12], 9, 1), [10, 11], 'strikesAround extremo');
eq(m.strikesAround([], 9, 1), [], 'strikesAround vacío');

const strikes = Array.from({ length: 40 }, (_, i) => i + 5);          // 5..44
const plan = m.planContracts(18.41, strikes, exps, '2026-10-22');
ok(plan.putExpiry.expiry === '20270115' && plan.callExpiry.expiry === '20261120', 'plan: vencimientos');
ok(plan.contracts.length > 20 && plan.contracts.length <= 70, `plan: nº de contratos razonable (${plan.contracts.length}, límite de líneas de IBKR ~100)`);
ok(plan.contracts.filter(c => c.right === 'C' && c.expiry === '20270115').length === 1, 'plan: una sola call ATM en el vencimiento largo');
ok(plan.contracts.filter(c => c.right === 'P' && c.expiry === '20261120').length === 0, 'plan: sin puts en el vencimiento corto');
ok(plan.contracts.some(c => c.right === 'P' && c.strike === 16) && plan.contracts.some(c => c.right === 'P' && c.strike === 11), 'plan: strikes de put 85%/60%');
ok(plan.contracts.some(c => c.right === 'C' && c.strike === 24) && plan.contracts.some(c => c.right === 'C' && c.strike === 36), 'plan: strikes de call 130%/200%');
eq(new Set(plan.contracts.map(c => `${c.expiry}${c.right}${c.strike}`)).size, plan.contracts.length, 'plan: sin duplicados');

const planned = [{ key: 'a', expiry: '20261120', dte: 29, right: 'C', strike: 24 }, { key: 'b', expiry: '20261120', dte: 29, right: 'C', strike: 22 },
                 { key: 'c', expiry: '20270115', dte: 85, right: 'P', strike: 16 }, { key: 'd', expiry: '20270115', dte: 85, right: 'P', strike: 11 }];
const quotes = new Map([['a', { bid: 1.0, ask: 1.4, iv: 1.39, oi: 1503, vol: 6 }], ['b', { bid: -1, ask: -1, last: 1.5 }], ['c', { bid: 1.14, ask: 3.85, iv: 1.09 }], ['d', {}]]);
const row = m.assembleChainRow({ ticker: 'UVXY', spot: 18.41, now: new Date('2026-10-23T15:00:00Z'), planned, quotes, dataTypes: [3, 3, 1] });
eq(row.expiries.map(e => [e.expiry, e.dte, e.contracts.length]), [['2026-11-20', 29, 2], ['2027-01-15', 85, 1]], 'assemble: agrupa por vencimiento y descarta contratos sin cotización');
eq(row.data_type, 'delayed', 'assemble: cualquier retrasado => delayed');
eq(m.assembleChainRow({ ticker: 'X', spot: 1, planned, quotes, dataTypes: [1, 1] }).data_type, 'live', 'assemble: todo tipo 1 => live');
eq(m.assembleChainRow({ ticker: 'X', spot: 1, planned, quotes, dataTypes: [2, 4] }).data_type, 'frozen', 'assemble: 2/4 => frozen');
eq(row.expiries[0].contracts[1], { strike: 24, cp: 'C', bid: 1, ask: 1.4, iv: 1.39, oi: 1503, vol: 6 }, 'assemble: esquema idéntico al de inverse_etf_options_chains.jsonl');
eq(row.expiries[0].contracts[0].bid, null, 'assemble: bid -1 => null');

// ── flujo contra TWS simulado ────────────────────────────────────────────────
function fakeApiFactory(cfg) {
  return () => {
    const api = new EventEmitter();
    api.sent = { mktData: [], cancelled: [], dataType: null };
    api.connect = () => setTimeout(() => api.emit(EventName.nextValidId, 100), 5);
    api.disconnect = () => { api.disconnected = true; };
    api.reqMarketDataType = t => { api.sent.dataType = t; };
    api.reqContractDetails = id => setTimeout(() => {
      if (cfg.noUnderlying) { api.emit(EventName.error, new Error('No security definition'), 200, id); api.emit(EventName.contractDetailsEnd, id); return; }
      api.emit(EventName.contractDetails, id, { contract: { conId: 777 } }); api.emit(EventName.contractDetailsEnd, id);
    }, 5);
    api.reqSecDefOptParams = id => setTimeout(() => {
      api.emit(EventName.securityDefinitionOptionParameter, id, 'SMART', 777, 'UVXY1', '100', ['20261120', '20270115'], [3, 4]);   // clase ajustada: debe ignorarse
      api.emit(EventName.securityDefinitionOptionParameter, id, 'SMART', 777, 'UVXY', '100', exps, strikes);
      api.emit(EventName.securityDefinitionOptionParameterEnd, id);
    }, 5);
    api.reqMktData = (id, contract, generic) => {
      api.sent.mktData.push({ id, contract, generic });
      setTimeout(() => {
        api.emit(EventName.marketDataType, id, cfg.dataType || 1);
        if (contract.secType === 'STK') { if (!cfg.noSpot) api.emit(EventName.tickPrice, id, 4, 18.4); return; }
        const k = contract.strike, call = contract.right === 'C';
        if (cfg.noOptionQuotes) return;
        api.emit(EventName.tickPrice, id, 1, +(k * 0.05).toFixed(2)); api.emit(EventName.tickPrice, id, 2, +(k * 0.06).toFixed(2));
        api.emit(EventName.tickSize, id, call ? 27 : 28, 100 + k);
        api.emit(EventName.tickOptionComputation, id, 13, undefined, 0.9 + k / 100);
      }, 5);
    };
    api.cancelMktData = id => api.sent.cancelled.push(id);
    cfg.last = api;
    return api;
  };
}

(async () => {
  const base = { lib, ports: [1], connectTimeoutMs: 500, collectMs: 3000, minCollectMs: 50, now: new Date('2026-10-22T19:00:00Z') };
  let cfg = {};
  let r = await m.fetchLiveChain('UVXY', { ...base, apiFactory: fakeApiFactory(cfg) });
  ok(cfg.last.sent.dataType === 3, 'flujo: pide reqMarketDataType(3)');
  ok(cfg.last.disconnected === true, 'flujo: desconecta al terminar');
  ok(cfg.last.sent.mktData.every(x => x.contract.secType === 'STK' || (x.contract.tradingClass === 'UVXY' && x.generic === '101' && x.contract.lastTradeDateOrContractMonth.length === 8)), 'flujo: opciones con clase UVXY (no UVXY1), OI pedido (tick 101) y fecha YYYYMMDD');
  ok(cfg.last.sent.cancelled.length >= cfg.last.sent.mktData.length - 1, 'flujo: cancela las suscripciones de datos');
  ok(r.row.spot === 18.4 && r.row.ticker === 'UVXY' && r.row.source === 'ibkr_tws' && r.row.data_type === 'live', 'flujo: fila con spot, ticker y data_type=live');
  eq(r.row.expiries.map(e => e.dte), [29, 85], 'flujo: dos vencimientos (~30d y ~90d)');
  const c24 = r.row.expiries[0].contracts.find(c => c.strike === 24 && c.cp === 'C');
  eq([c24.bid, c24.ask, c24.oi, c24.iv], [1.2, 1.44, 124, 1.14], 'flujo: bid/ask/OI/IV de un contrato');
  ok(r.info.quoted === r.info.requested, 'flujo: todos los contratos cotizados');

  cfg = { dataType: 3 };
  r = await m.fetchLiveChain('UVXY', { ...base, apiFactory: fakeApiFactory(cfg) });
  eq(r.row.data_type, 'delayed', 'flujo: sin suscripción => data_type=delayed (nunca se presenta como vivo)');

  cfg = { noUnderlying: true };
  await m.fetchLiveChain('UVXY', { ...base, apiFactory: fakeApiFactory(cfg) }).then(() => ok(false, 'NO_UNDERLYING debía fallar'), e => eq(e.code, 'NO_UNDERLYING', 'error: subyacente desconocido'));
  ok(cfg.last.disconnected, 'error: desconecta también al fallar');

  cfg = { noSpot: true };
  await m.fetchLiveChain('UVXY', { ...base, apiFactory: fakeApiFactory(cfg) }).then(() => ok(false, 'NO_DATA debía fallar'), e => eq(e.code, 'NO_DATA', 'error: sin precio del subyacente'));

  cfg = { noOptionQuotes: true };
  await m.fetchLiveChain('UVXY', { ...base, collectMs: 400, apiFactory: fakeApiFactory(cfg) }).then(() => ok(false, 'NO_DATA debía fallar'), e => eq(e.code, 'NO_DATA', 'error: sin cotizaciones de opciones'));

  // Conexión rechazada con la librería real (no hay nada escuchando en el puerto 1)
  await m.fetchLiveChain('UVXY', { ports: [1], connectTimeoutMs: 1500 }).then(() => ok(false, 'NO_TWS debía fallar'), e => { eq(e.code, 'NO_TWS', 'error: sin TWS (conexión real rechazada)'); ok(/Enable ActiveX and Socket Clients/.test(e.message), 'error: el mensaje explica cómo activar la API'); });

  console.log(`\n${pass} ok, ${fail} fallos`);
  process.exit(fail ? 1 : 0);
})();
