// Tests del parser/persistencia de ibkr_flex_sync.js sobre un informe Flex
// sintético con la estructura real de IBKR (Activity Flex Query, XML). Sin
// framework — mismo estilo que los test_*.py del proyecto.
//   node scripts/test_ibkr_flex_parser.js
const fs = require('fs');
const os = require('os');
const path = require('path');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ibkr-test-'));
process.env.IBKR_PRIVATE_DIR = tmp;   // antes del require: nunca toca private/ibkr real
const lib = require('./ibkr_flex_sync.js');

let pass = 0, fail = 0;
function check(name, cond, extra = '') {
  if (cond) { pass++; } else { fail++; console.log('FAIL ' + name + (extra ? ' — ' + extra : '')); }
}

const XML = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse queryName="market-tracker" type="AF">
<FlexStatements count="1">
<FlexStatement accountId="U1234567" fromDate="20251003" toDate="20261002" period="Last365CalendarDays" whenGenerated="20261003;083015">
<AccountInformation accountId="U1234567" acctAlias="" currency="EUR" name="Test" accountType="Individual" />
<EquitySummaryInBase>
<EquitySummaryByReportDateInBase accountId="U1234567" currency="EUR" reportDate="20260930" cash="1000.5" stock="9000" options="0" total="10000.5" />
<EquitySummaryByReportDateInBase accountId="U1234567" currency="EUR" reportDate="20261001" cash="1000.5" stock="9100" options="0" total="10100.5" />
<EquitySummaryByReportDateInBase accountId="U1234567" currency="EUR" reportDate="20261002" cash="500.5" stock="9800" options="0" total="10300.5" />
</EquitySummaryInBase>
<CashReport>
<CashReportCurrency accountId="U1234567" currency="BASE_SUMMARY" endingCash="500.5" endingSettledCash="500.5" />
<CashReportCurrency accountId="U1234567" currency="USD" endingCash="580" endingSettledCash="580" />
</CashReport>
<OpenPositions>
<OpenPosition accountId="U1234567" currency="USD" fxRateToBase="0.86" assetCategory="STK" symbol="NVDA" description="NVIDIA CORP" conid="4815747" isin="US67066G1040" listingExchange="NASDAQ" reportDate="20261002" position="20" markPrice="180.5" positionValue="3610" costBasisPrice="150.25" costBasisMoney="3005" percentOfNAV="30.1" fifoPnlUnrealized="605" side="Long" levelOfDetail="SUMMARY" />
<OpenPosition accountId="U1234567" currency="USD" fxRateToBase="0.86" assetCategory="STK" symbol="NVDA" description="NVIDIA CORP" conid="4815747" reportDate="20261002" position="20" markPrice="180.5" levelOfDetail="LOT" />
<OpenPosition accountId="U1234567" currency="EUR" fxRateToBase="1" assetCategory="STK" symbol="ASM" description="ASM INTERNATIONAL NV &amp; CO &gt; test" conid="12345" listingExchange="AEB" reportDate="20261002" position="5" markPrice="900" positionValue="4500" costBasisPrice="1000" costBasisMoney="5000" percentOfNAV="43.7" fifoPnlUnrealized="-500" side="Long" levelOfDetail="SUMMARY" />
</OpenPositions>
<Trades>
<Trade accountId="U1234567" currency="USD" fxRateToBase="0.86" assetCategory="STK" symbol="NVDA" description="NVIDIA CORP" conid="4815747" tradeID="111" tradeDate="20260915" dateTime="20260915;153012" buySell="BUY" quantity="20" tradePrice="150.25" proceeds="-3005" ibCommission="-1" netCash="-3006" fifoPnlRealized="0" openCloseIndicator="O" orderType="LMT" exchange="NASDAQ" />
<Trade accountId="U1234567" currency="EUR" fxRateToBase="1" assetCategory="STK" symbol="SAP" description="SAP SE" conid="999" tradeID="112" tradeDate="20260920" dateTime="20260920;101500" buySell="SELL" quantity="-10" tradePrice="210" proceeds="2100" ibCommission="-3" netCash="2097" fifoPnlRealized="150.75" openCloseIndicator="C" orderType="MKT" exchange="IBIS" />
</Trades>
</FlexStatement>
</FlexStatements>
</FlexQueryResponse>`;

// ── utilidades
check('normDate yyyyMMdd', lib.normDate('20261002') === '2026-10-02');
check('normDate datetime', lib.normDate('20260915;153012') === '2026-09-15');
check('normDate iso', lib.normDate('2026-10-02') === '2026-10-02');
check('normDate MM/dd/yyyy', lib.normDate('10/02/2026') === '2026-10-02');
check('maskAccount', lib.maskAccount('U1234567') === 'U***567');

// ── respuestas del servicio
const ok = lib.parseServiceResponse('<FlexStatementResponse timestamp="x"><Status>Success</Status><ReferenceCode>987654</ReferenceCode><Url>https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement</Url></FlexStatementResponse>');
check('send ok status', ok.status === 'Success' && ok.referenceCode === '987654' && ok.url.endsWith('GetStatement'));
const err = lib.parseServiceResponse('<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress. Please try again shortly.</ErrorMessage></FlexStatementResponse>');
check('send 1019', err.errorCode === '1019' && /in progress/.test(err.errorMessage));

// ── parser
const st = lib.parseFlexStatement(XML);
check('1 statement', st.length === 1);
check('attrs statement', st[0].attrs.accountId === 'U1234567' && st[0].attrs.toDate === 20261002);
check('sección autocerrada', st[0].sections.AccountInformation?._self?.[0]?.currency === 'EUR');
check('open positions (incl. lote)', st[0].sections.OpenPositions.OpenPosition.length === 3);
check('entidades + ">" en atributo', st[0].sections.OpenPositions.OpenPosition[2].description === 'ASM INTERNATIONAL NV & CO > test');

// ── extracción + persistencia
const r1 = lib.processXml(XML, { syncedAt: '2026-10-03T08:30:00Z', log: () => {} });
const L = r1.latest;
check('lote excluido → 2 posiciones', L.positions.length === 2, `got ${L.positions.length}`);
check('fecha posiciones', L.positions_date === '2026-10-02');
check('cuenta enmascarada en latest', L.accounts[0].account === 'U***567' && !JSON.stringify(L).includes('U1234567'));
check('base currency', L.accounts[0].base_currency === 'EUR');
check('NAV último', L.nav.date === '2026-10-02' && L.nav.total === 10300.5);
check('NAV histórico', L.nav_history_days === 3);
check('cash base', L.base_cash.ending_cash === 500.5);
const nv = L.positions.find(p => p.symbol === 'NVDA');
check('posición NVDA', nv.quantity === 20 && nv.cost_basis_price === 150.25 && nv.unrealized_pnl === 605);
check('P&L no realizado en base', Math.abs(L.unrealized_pnl_base - (605 * 0.86 - 500)) < 0.01, `got ${L.unrealized_pnl_base}`);
check('sin warnings con query completa', L.warnings.length === 0, JSON.stringify(L.warnings));

const trades = fs.readFileSync(lib.FILES.trades, 'utf8').trim().split('\n').map(JSON.parse);
check('2 operaciones', trades.length === 2);
check('operación SAP', trades.find(t => t.trade_id === 112)?.realized_pnl === 150.75 && trades.find(t => t.trade_id === 112).date === '2026-09-20');

// ── idempotencia: re-procesar el mismo informe no duplica
const r2 = lib.processXml(XML, { syncedAt: '2026-10-03T20:30:00Z', log: () => {} });
check('dedup posiciones', r2.counts.positions.added === 0 && r2.counts.positions.total === 2);
check('dedup NAV', r2.counts.nav.added === 0 && r2.counts.nav.total === 3);
check('dedup trades', r2.counts.trades.added === 0 && r2.counts.trades.total === 2);

// ── query incompleta → aviso explícito, no fallo silencioso
const partial = XML.replace(/<Trades>[\s\S]*?<\/Trades>/, '').replace(/<CashReport>[\s\S]*?<\/CashReport>/, '');
const r3 = lib.extractRows(lib.parseFlexStatement(partial), 'x');
check('warning secciones ausentes', r3.warnings.length === 1 && /Trades/.test(r3.warnings[0]) && /Cash Report/.test(r3.warnings[0]));

// ── mapeo símbolo IBKR → ticker del tracker (shared/ibkr-map.js)
const { ibkrTrackerTicker } = require('../shared/ibkr-map.js');
const tk = new Set(['BTCC-B.TO', 'FXPO.L', 'TLW.L', 'TNZ.TO', 'REG.V', 'QXO', 'A.TO', 'A', 'ASM.AS']);
const mapCase = (name, row, expected) => check('map ' + name, ibkrTrackerTicker(row, tk) === expected, `got ${ibkrTrackerTicker(row, tk)}`);
mapCase('opción OCC sobre clase (BTCC→BTCC-B.TO)', { symbol: 'BTCC  261218C00020000', exchange: 'CDE' }, 'BTCC-B.TO');
mapCase('LSE con l minúscula', { symbol: 'FXPOl' }, 'FXPO.L');
mapCase('LSE TLWl', { symbol: 'TLWl' }, 'TLW.L');
mapCase('opción OCC normal', { symbol: 'QXO   270115C00013000' }, 'QXO');
mapCase('acción con bolsa', { symbol: 'TNZ', listing_exchange: 'TSE' }, 'TNZ.TO');
mapCase('AEB → .AS', { symbol: 'ASM', listing_exchange: 'AEB' }, 'ASM.AS');
mapCase('desconocido', { symbol: 'XYZ' }, null);
mapCase('exacto gana sobre prefijo (A vs A.TO)', { symbol: 'A' }, 'A');
mapCase('subyacente de posición con clase', { underlying_symbol: 'BTCC.B', listing_exchange: 'TSE', symbol: 'BTCC.B' }, 'BTCC-B.TO');
tk.add('^XSP');
mapCase('índice Yahoo con ^ (XSP → ^XSP)', { symbol: 'XSP   261113P00760000', exchange: 'CBOE' }, '^XSP');
tk.add('A.V');   // ahora hay dos tickers con base 'A' además del exacto 'A': el exacto sigue ganando…
mapCase('exacto sigue ganando con más candidatos', { symbol: 'A' }, 'A');
tk.delete('A');  // …pero sin el exacto, dos candidatos (A.TO, A.V) → ambiguo → no se adivina
mapCase('ambiguo → null', { symbol: 'A' }, null);

// ── sesgo inferido (diario de decisiones)
const { inferBias } = require('./ibkr_decision_journal.js');
check('bias comprar acción', inferBias({ asset_class: 'STK', side: 'BUY' }) === 1);
check('bias vender acción (corto)', inferBias({ asset_class: 'STK', side: 'SELL' }) === -1);
check('bias comprar call', inferBias({ asset_class: 'OPT', side: 'BUY', put_call: 'C' }) === 1);
check('bias vender call', inferBias({ asset_class: 'OPT', side: 'SELL', put_call: 'C' }) === -1);
check('bias comprar put', inferBias({ asset_class: 'OPT', side: 'BUY', put_call: 'P' }) === -1);
check('bias vender put (alcista)', inferBias({ asset_class: 'OPT', side: 'SELL', put_call: 'P' }) === 1);
check('bias sin put_call → null', inferBias({ asset_class: 'OPT', side: 'BUY', put_call: null }) === null);

// ── nunca escribió en private/ibkr real
check('dir temporal usado', lib.FILES.latest.startsWith(tmp));

fs.rmSync(tmp, { recursive: true, force: true });
console.log(`\n${pass} ok, ${fail} fallos`);
process.exit(fail ? 1 : 0);
