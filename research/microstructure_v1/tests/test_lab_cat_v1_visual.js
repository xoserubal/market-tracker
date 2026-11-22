// Prueba visual del laboratorio con cat-v1 (Edge sin ventana). Local; se salta sin puppeteer-core/Edge.
//   PUPPETEER_DIR=<carpeta con node_modules/puppeteer-core> node tests/test_lab_cat_v1_visual.js <puerto> <validation_cases.json> <carpeta_capturas>
// Requiere el servidor del laboratorio en marcha. Las capturas contienen datos de mercado: no van al repositorio.
'use strict';
const path = require('path');
const fs = require('fs');
let puppeteer;
try { puppeteer = require('puppeteer-core'); } catch (_) {
  try { puppeteer = require(path.join(process.env.PUPPETEER_DIR || '', 'node_modules', 'puppeteer-core')); } catch (_2) { puppeteer = null; }
}
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
if (!puppeteer || !fs.existsSync(EDGE)) { console.log('SKIP: falta puppeteer-core o Edge'); process.exit(0); }
const [port = '8766', casesFile, outDir = '.'] = process.argv.slice(2);
const cases = JSON.parse(fs.readFileSync(casesFile, 'utf8').replace(/\bNaN\b/g, 'null')).cases;

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  // CDP_URL=http://127.0.0.1:<puerto>: Edge lanzado a mano con --remote-debugging-port (en este equipo, launch() falla)
  const browser = process.env.CDP_URL ? await puppeteer.connect({ browserURL: process.env.CDP_URL, defaultViewport: null, protocolTimeout: 600000 })
    : await puppeteer.launch({ executablePath: EDGE, headless: true, args: ['--no-first-run', '--disable-gpu'],
      userDataDir: path.join(outDir, 'edge-profile-' + Date.now()) });
  const report = [];
  try {
    for (let i = 0; i < cases.length; i++) {
      const c = cases[i];
      const page = await browser.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(String(e)));
      // se ignora el ruido de las extensiones integradas de Edge (no es del laboratorio)
      const noise = /chrome-extension:|runtime\.lastError|^Failed to load resource: net::ERR_FAILED$/;
      page.on('console', (m) => { if (m.type() === 'error' && !noise.test(m.text())) errors.push(m.text()); });
      await page.setViewport({ width: 1600, height: 1400 });
      const url = c.lab_url.replace(/127\.0\.0\.1:\d+/, '127.0.0.1:' + port);
      await page.goto(url, { waitUntil: 'networkidle0', timeout: 180000 });
      await page.waitForFunction(() => document.querySelector('#valorday table') || /calcul|Sin medidas|sin datos/i.test(document.querySelector('#valorday').textContent), { timeout: 180000 });
      // solo los episodios de este valor (un día de estrés tiene miles de episodios en todo el mercado)
      await page.evaluate(() => { const c = document.querySelector('#evall'); if (c.checked) { c.checked = false; c.dispatchEvent(new Event('change')); } });
      await page.waitForFunction(() => document.querySelectorAll('#events tr').length < 200, { timeout: 120000 });
      await new Promise((r) => setTimeout(r, 1500));
      const st = await page.evaluate(() => ({
        evmeta: document.querySelector('#evmeta').textContent,
        catalog: document.querySelector('#evcat').value,
        alertsRows: document.querySelectorAll('#alerts table tr').length - 1,
        valordayRows: document.querySelectorAll('#valorday table tr').length - 1,
        vdmeta: document.querySelector('#vdmeta').textContent,
        pvBlank: (() => { const cv = document.querySelector('#pv'); const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let n = 0; for (let k = 3; k < d.length; k += 4) if (d[k]) n++; return n; })(),
      }));
      const rowEl = await page.$('section.evrow');
      const f1 = path.join(outDir, `case${String(i + 1).padStart(2, '0')}_events.png`);
      await rowEl.screenshot({ path: f1 });
      const vdEl = await page.$('#valorday');
      const f2 = path.join(outDir, `case${String(i + 1).padStart(2, '0')}_valorday.png`);
      await vdEl.screenshot({ path: f2 });
      report.push({ case: c.case, symbol: c.symbol, day: c.day, ...st, errors, shots: [f1, f2] });
      console.log(JSON.stringify(report[report.length - 1]));
      await page.close();
    }
  } finally { if (process.env.CDP_URL) browser.disconnect(); else await browser.close(); }
  fs.writeFileSync(path.join(outDir, 'visual_report.json'), JSON.stringify(report, null, 1));
  const bad = report.filter((r) => r.errors.length || r.catalog !== 'cat-v1' || r.pvBlank < 1000);
  console.log(bad.length ? `FALLOS: ${bad.length}` : `OK: ${report.length} casos`);
  process.exit(bad.length ? 1 : 0);
})();
