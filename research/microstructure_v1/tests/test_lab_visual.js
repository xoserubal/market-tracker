// Prueba visual del laboratorio con Edge sin ventana (local; se salta si no hay puppeteer-core o Edge).
//   PUPPETEER_DIR=<carpeta con node_modules/puppeteer-core> node tests/test_lab_visual.js [puerto] [carpeta_capturas]
// Requiere el servidor del laboratorio en marcha con datos de NVDA 2026-11-12 descargados.
'use strict';
const path = require('path');
const fs = require('fs');
let puppeteer;
try { puppeteer = require('puppeteer-core'); } catch (_) {
  try { puppeteer = require(path.join(process.env.PUPPETEER_DIR || '', 'node_modules', 'puppeteer-core')); } catch (_2) { puppeteer = null; }
}
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
if (!puppeteer || !fs.existsSync(EDGE)) { console.log('SKIP: falta puppeteer-core o Edge'); process.exit(0); }
const port = process.argv[2] || '8765';
const outDir = process.argv[3] || '.';
const assert = require('assert');

(async () => {
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ['--no-first-run', '--disable-gpu'],
    userDataDir: path.join(outDir, 'edge-profile-' + Date.now()) });
  const errors = [];
  try {
    const page = await browser.newPage();
    page.on('pageerror', (e) => errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    await page.setViewport({ width: 1500, height: 1250 });
    await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'networkidle0' });
    const setv = (id, v) => page.$eval('#' + id, (el, v) => { el.value = v; }, v);
    await setv('symbol', 'NVDA'); await setv('day', '2026-11-12'); await setv('start', '09:30'); await setv('end', '12:00');
    await page.select('#tf', '60');
    await page.click('#load');
    await page.waitForFunction(() => document.getElementById('quality').textContent.includes('clasificado'), { timeout: 240000 });
    const q = await page.$eval('#quality', (el) => el.textContent);
    assert.ok(q.includes('método'), 'faltan las insignias de calidad');
    // el lienzo tiene contenido dibujado (píxeles no blancos)
    const ink = await page.$eval('#fp', (c) => {
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let k = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i] < 240 || d[i + 1] < 240 || d[i + 2] < 240) k++;
      return k / (d.length / 4);
    });
    assert.ok(ink > 0.05, 'el footprint parece vacío: ' + ink);
    await page.screenshot({ path: path.join(outDir, 'lab_nvda_60m.png') });
    // clic en la primera vela -> detalle con tabla de niveles
    const box = await page.$eval('#fp', (c) => { const r = c.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width }; });
    await page.mouse.click(box.x + 64 + 30, box.y + 200);
    await page.waitForFunction(() => document.querySelectorAll('#detail table tr').length > 3, { timeout: 10000 });
    // 5 minutos y modo ciego con cursor a las 10:00: ningún dato posterior
    await page.select('#tf', '5'); await page.$eval('#blind', (el) => { el.checked = true; }); await setv('cursor', '10:00:00');
    await page.click('#load');
    await page.waitForFunction(() => document.getElementById('quality').textContent.includes('modo ciego'), { timeout: 240000 });
    const blindTxt = await page.$eval('#quality', (el) => el.textContent);
    const m = blindTxt.match(/datos hasta (\d\d:\d\d:\d\d)/);
    assert.ok(m && m[1] < '10:00:00', 'el modo ciego muestra datos posteriores al cursor: ' + (m && m[1]));
    await page.screenshot({ path: path.join(outDir, 'lab_nvda_5m_blind.png') });
    // avanzar una vela con ▶
    await page.click('#fwd');
    await page.waitForFunction(() => document.getElementById('cursor').value === '10:05:00', { timeout: 5000 });
    assert.deepStrictEqual(errors, [], 'errores en la página: ' + errors.join(' | '));
    console.log('OK prueba visual del laboratorio');
  } finally { await browser.close(); }
})().catch((e) => { console.error('FALLO', e); process.exit(1); });
