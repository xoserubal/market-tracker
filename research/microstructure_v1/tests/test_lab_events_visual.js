// Prueba visual de la parte de eventos del laboratorio (E1), con Edge sin ventana. Local; se salta sin puppeteer-core/Edge.
//   PUPPETEER_DIR=<carpeta con node_modules/puppeteer-core> node tests/test_lab_events_visual.js <puerto> <carpeta_capturas> <día> <episodio>
// Requiere el servidor del laboratorio en marcha y el registro de eventos con ese episodio ya escaneado y desglosado.
'use strict';
const path = require('path');
const fs = require('fs');
let puppeteer;
try { puppeteer = require('puppeteer-core'); } catch (_) {
  try { puppeteer = require(path.join(process.env.PUPPETEER_DIR || '', 'node_modules', 'puppeteer-core')); } catch (_2) { puppeteer = null; }
}
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
if (!puppeteer || !fs.existsSync(EDGE)) { console.log('SKIP: falta puppeteer-core o Edge'); process.exit(0); }
const [port = '8765', outDir = '.', day = '2026-11-10', ep = '0c4dfdb850128661'] = process.argv.slice(2);
const assert = require('assert');

(async () => {
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ['--no-first-run', '--disable-gpu'],
    userDataDir: path.join(outDir, 'edge-profile-' + Date.now()) });
  const errors = [];
  let n = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); n++; };
  try {
    const page = await browser.newPage();
    page.on('pageerror', (e) => errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    await page.setViewport({ width: 1500, height: 1500 });
    // 1) enlace directo a un episodio histórico: campos, modo ciego por defecto y cursor en el instante detectable
    await page.goto(`http://127.0.0.1:${port}/?day=${day}&episode=${ep}`, { waitUntil: 'networkidle0' });
    await page.waitForFunction(() => document.querySelector('#alerts table'), { timeout: 60000 });
    const st = await page.evaluate(() => ({ sym: document.querySelector('#symbol').value, day: document.querySelector('#day').value,
      blind: document.querySelector('#blind').checked, cursor: document.querySelector('#cursor').value, tf: document.querySelector('#tf').value,
      url: location.search, eps: document.querySelectorAll('#events tr').length, al: document.querySelectorAll('#alerts tr').length }));
    ok(st.day === day && st.sym.length > 0, 'campos del episodio');
    ok(st.blind && /^\d\d:\d\d:\d\d$/.test(st.cursor), 'modo ciego por defecto con cursor');
    ok(st.tf === '1' && st.url.includes('episode=' + ep), 'vela de 1 min y enlace sincronizado');
    ok(st.eps >= 2 && st.al >= 2, 'panel de acontecimientos y tabla de alertas');
    // 2) gráfico de precio y volumen dibujado y sin datos posteriores al cursor
    const pv = await page.evaluate(() => { const c = document.querySelector('#pv'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      let ink = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) ink++; return ink; });
    ok(pv > 2000, 'gráfico de precio y volumen dibujado');
    const bars = await page.evaluate(async () => {
      const p = new URLSearchParams(location.search);
      const r = await fetch(`/api/bars?symbol=${p.get('symbol')}&day=${p.get('day')}&blind=1&cursor=${p.get('cursor')}`).then((x) => x.json());
      return { n: r.bars.length, last: r.bars.length ? r.bars[r.bars.length - 1].t : 0, cursor: r.cursor };
    });
    ok(bars.n > 0 && bars.last + 60000 <= Date.parse(bars.cursor), 'modo ciego: ninguna barra posterior al cursor');
    // 3) datos y versiones
    const prov = await page.$eval('#prov', (e) => e.textContent);
    ok(/Línea base/.test(prov) && /catálogo cat-v0/.test(prov), 'panel de datos y versiones');
    // 4) perfil de volumen bajo demanda
    await page.click('#profbtn');
    await page.waitForFunction(() => /POC/.test(document.querySelector('#profile').textContent) || /sin trades/.test(document.querySelector('#profile').textContent), { timeout: 60000 });
    ok(/POC/.test(await page.$eval('#profile', (e) => e.textContent)), 'perfil de volumen calculado');
    await page.screenshot({ path: path.join(outDir, 'lab_events_episode.png'), fullPage: false });
    // 5) bloqueo del periodo reservado
    await page.goto(`http://127.0.0.1:${port}/?symbol=NVDA&day=2024-01-02&tf=1`, { waitUntil: 'networkidle0' });
    await page.waitForFunction(() => /periodo reservado/.test(document.querySelector('#banner').textContent) || /periodo reservado/.test(document.querySelector('#quality').textContent), { timeout: 30000 });
    ok(true, 'fecha del periodo reservado bloqueada');
    ok(errors.length === 0, 'sin errores de página: ' + errors.join(' | '));
    console.log(`OK ${n} comprobaciones visuales de eventos`);
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exit(1); });
