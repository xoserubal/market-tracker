// Tests de los reintentos de la descarga Flex (ibkr_flex_sync.js), sin red real
// salvo un servidor local que no responde (para el límite de espera HTTP).
//   node scripts/test_ibkr_flex_retry.js
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ibkr-retry-'));
process.env.IBKR_PRIVATE_DIR = tmp;   // antes del require: nunca toca private/ibkr real
process.env.IBKR_FLEX_TOKEN = 'tok';
process.env.IBKR_FLEX_QUERY_ID = 'q';
const lib = require('./ibkr_flex_sync.js');

let pass = 0, fail = 0;
function check(name, cond, extra = '') {
  if (cond) { pass++; } else { fail++; console.log('FAIL ' + name + (extra ? ' — ' + extra : '')); }
}

const SEND_OK = ref => `<FlexStatementResponse><Status>Success</Status><ReferenceCode>${ref}</ReferenceCode><Url>https://x/GetStatement</Url></FlexStatementResponse>`;
const IN_PROGRESS = '<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress.</ErrorMessage></FlexStatementResponse>';
const BAD_TOKEN = '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1015</ErrorCode><ErrorMessage>Token is invalid.</ErrorMessage></FlexStatementResponse>';
const REPORT = `<FlexQueryResponse queryName="t" type="AF"><FlexStatements count="1">
<FlexStatement accountId="U1234567" fromDate="20261001" toDate="20261002" whenGenerated="20261003;083015">
<AccountInformation accountId="U1234567" currency="EUR" />
<EquitySummaryInBase><EquitySummaryByReportDateInBase accountId="U1234567" reportDate="20261002" cash="1" stock="9" total="10" /></EquitySummaryInBase>
<CashReport><CashReportCurrency accountId="U1234567" currency="BASE_SUMMARY" endingCash="1" /></CashReport>
<OpenPositions><OpenPosition accountId="U1234567" currency="USD" fxRateToBase="0.9" assetCategory="STK" symbol="NVDA" conid="1" reportDate="20261002" position="2" markPrice="10" levelOfDetail="SUMMARY" /></OpenPositions>
<Trades><Trade accountId="U1234567" currency="USD" assetCategory="STK" symbol="NVDA" conid="1" tradeID="7" tradeDate="20260930" dateTime="20260930;100000" buySell="BUY" quantity="2" tradePrice="9" /></Trades>
</FlexStatement></FlexStatements></FlexQueryResponse>`;

// Simulador: `script(sendN, pollN)` decide la respuesta de cada llamada; el reloj es falso.
function fakeService(script) {
  const st = { sends: 0, polls: {}, waited: 0, calls: 0 };
  const get = async url => {
    st.calls++;
    if (url.includes('SendRequest')) { st.sends++; return script.send ? script.send(st.sends) : SEND_OK('R' + st.sends); }
    const ref = /q=([^&]+)/.exec(url)[1];
    st.polls[ref] = (st.polls[ref] || 0) + 1;
    return script.poll(ref, st.polls[ref]);
  };
  const wait = async ms => { st.waited += ms; };
  return { st, deps: { get, wait } };
}
const quiet = () => {};

(async () => {
  const { POLL_MAX_ATTEMPTS: P, POLL_WAIT_MS: W, FRESH_REQUESTS: F } = lib;

  // 1) la primera referencia se atasca; la segunda sale → 2 peticiones, 1 informe
  {
    const { st, deps } = fakeService({ poll: (ref, n) => ref === 'R1' ? IN_PROGRESS : (n >= 2 ? REPORT : IN_PROGRESS) });
    const xml = await lib.downloadFlexReport('tok', 'q', quiet, deps);
    check('atasco → informe de la 2.ª petición', xml === REPORT);
    check('atasco → 2 SendRequest', st.sends === 2, `sends ${st.sends}`);
    check('atasco → R1 sondeado exactamente P veces', st.polls.R1 === P, `polls ${st.polls.R1}`);
  }

  // 2) las tres se atascan → error acotado: F peticiones × P sondeos, espera total exacta
  {
    const { st, deps } = fakeService({ poll: () => IN_PROGRESS });
    let err = null;
    try { await lib.downloadFlexReport('tok', 'q', quiet, deps); } catch (e) { err = e; }
    check('todas atascadas → lanza error', err && /no estuvo listo/.test(err.message));
    check('todas atascadas → F SendRequest', st.sends === F, `sends ${st.sends}`);
    check('todas atascadas → F×P sondeos', Object.values(st.polls).reduce((a, b) => a + b, 0) === F * P);
    const expected = F * (3000 + P * W) + (F - 1) * 10000;
    check('todas atascadas → espera total acotada', st.waited === expected, `${st.waited} vs ${expected}`);
  }

  // 3) error no recuperable (token inválido) → no pide informes nuevos
  {
    const { st, deps } = fakeService({ send: () => BAD_TOKEN, poll: () => REPORT });
    let err = null;
    try { await lib.downloadFlexReport('tok', 'q', quiet, deps); } catch (e) { err = e; }
    check('token inválido → error 1015', err && /1015/.test(err.message));
    check('token inválido → una sola petición', st.sends === 1 && st.waited === 0);
  }

  // 4) timeout HTTP → se pide un informe nuevo (y la 2.ª sale)
  {
    let first = true;
    const { st, deps } = fakeService({ poll: () => REPORT });
    const get0 = deps.get;
    deps.get = async url => {
      if (first && url.includes('GetStatement')) { first = false; const e = new Error('sin respuesta'); e.retryable = true; throw e; }
      return get0(url);
    };
    const xml = await lib.downloadFlexReport('tok', 'q', quiet, deps);
    check('timeout → recupera con petición nueva', xml === REPORT && st.sends === 2);
  }

  // 5) el límite HTTP es efectivo: un servidor que no responde corta en ~timeout
  {
    const srv = http.createServer(() => { /* nunca responde */ });
    await new Promise(r => srv.listen(0, '127.0.0.1', r));
    const url = `http://127.0.0.1:${srv.address().port}/GetStatement?q=1`;
    const t0 = Date.now();
    let err = null;
    try { await lib.httpGet(url, 300); } catch (e) { err = e; }
    const dt = Date.now() - t0;
    check('httpGet colgado → error retryable', err && err.retryable === true && /sin respuesta/.test(err.message), err && err.message);
    check('httpGet colgado → corta cerca del límite', dt >= 250 && dt < 3000, `${dt} ms`);
    srv.closeAllConnections(); srv.close();
    check('timeout por defecto definido', lib.HTTP_TIMEOUT_MS > 0 && lib.HTTP_TIMEOUT_MS <= 60000);
  }

  // 6) syncIbkr con todo fallando → ok:false, estado con error, nada escrito
  {
    const download = async () => { throw new Error('GetStatement: el informe no estuvo listo tras varios reintentos'); };
    const r = await lib.syncIbkr({ log: quiet, download });
    const state = JSON.parse(fs.readFileSync(lib.FILES.state, 'utf8'));
    check('fallo total → ok:false', r.ok === false && /no estuvo listo/.test(r.error));
    check('fallo total → last_error guardado', /no estuvo listo/.test(state.last_error) && !state.last_success);
    check('fallo total → sin ficheros de cartera', !fs.existsSync(lib.FILES.positions) && !fs.existsSync(lib.FILES.trades) && !fs.existsSync(lib.FILES.latest));
    // el cerrojo se libera: una sincronización posterior vuelve a ejecutarse
    let called = 0;
    await lib.syncIbkr({ log: quiet, download: async () => { called++; throw new Error('x'); } });
    check('fallo total → cerrojo liberado', called === 1);
  }

  // 7) proceso: `node ibkr_flex_sync.js` termina con código 1 si la sincronización falla
  {
    const { spawnSync } = require('child_process');
    const res = spawnSync(process.execPath, [path.join(__dirname, 'ibkr_flex_sync.js')], {
      env: { ...process.env, IBKR_FLEX_TOKEN: '', IBKR_FLEX_QUERY_ID: '', IBKR_PRIVATE_DIR: tmp, DOTENV_CONFIG_PATH: path.join(tmp, 'none.env') },
      cwd: tmp, timeout: 20000, encoding: 'utf8',
    });
    // Si el .env real tiene credenciales, dotenv no las pisa (variables ya definidas, aunque vacías).
    check('proceso sale con código 1 y no se cuelga', res.status === 1, `status ${res.status} ${res.error || ''}`);
  }

  // 8) reintentos + sincronización repetida no duplican la cartera
  {
    for (const f of ['positions', 'nav', 'trades', 'latest']) fs.rmSync(lib.FILES[f], { force: true });
    let k = 0;
    const flaky = async (token, q, log) => {
      const { deps } = fakeService({ poll: (ref) => ref === 'R1' ? IN_PROGRESS : REPORT });
      k++;
      return lib.downloadFlexReport(token, q, log, deps);
    };
    const r1 = await lib.syncIbkr({ log: quiet, download: flaky });
    const r2 = await lib.syncIbkr({ log: quiet, download: flaky });
    const lines = f => fs.readFileSync(lib.FILES[f], 'utf8').trim().split('\n').length;
    check('reintento → sincronización ok', r1.ok && r2.ok && k === 2);
    check('reintento → 1 posición, 1 NAV, 1 operación', lines('positions') === 1 && lines('nav') === 1 && lines('trades') === 1,
      `${lines('positions')}/${lines('nav')}/${lines('trades')}`);
    check('reintento → 2.ª sincronización no añade filas', r2.counts.positions.added === 0 && r2.counts.trades.added === 0 && r2.counts.nav.added === 0);
  }

  check('dir temporal usado', lib.FILES.latest.startsWith(tmp));
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\n${pass} ok, ${fail} fallos`);
  process.exit(fail ? 1 : 0);
})();
