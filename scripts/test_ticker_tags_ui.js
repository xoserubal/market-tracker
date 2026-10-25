#!/usr/bin/env node
/*
 * test_ticker_tags_ui.js — F6: la interfaz de etiquetas en un navegador real (Edge/Chrome headless).
 *   node scripts/test_ticker_tags_ui.js
 *   Requiere puppeteer-core (opcional: sin él la prueba se OMITE con aviso) y un Edge/Chrome instalado
 *   (EDGE_PATH para indicarlo). Usa tags_test_server.js en un puerto efímero con datos temporales: no toca
 *   el servidor real, ni git, ni portfolio.json (se comprueba el hash antes y después).
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const net = require('net');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { createApp } = require('./tags_test_server');

const ROOT = path.resolve(__dirname, '..');
let puppeteer;
try { puppeteer = require('puppeteer-core'); } catch (_) { try { puppeteer = require(path.join(process.env.PUPPETEER_DIR || '', 'node_modules', 'puppeteer-core')); } catch (_2) { puppeteer = null; } }
const EDGES = [process.env.EDGE_PATH, 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe'].filter(Boolean);
const exe = EDGES.find(p => fs.existsSync(p));
if (!puppeteer || !exe) {
  console.log(`OMITIDA: ${!puppeteer ? 'falta puppeteer-core' : 'no se encontró Edge/Chrome'} (esta prueba es opcional; la cubren las pruebas de librería, almacén y HTTP)`);
  process.exit(0);
}

const results = [];
const check = (name, ok, detail) => results.push({ name, ok: !!ok, detail: ok ? '' : String(detail || '') });
const sha = (f) => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });

async function run() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tags-ui-'));
  const data = path.join(tmp, 'docs', 'data'); fs.mkdirSync(data, { recursive: true });
  for (const f of ['ticker_tags.json', 'ticker_tags_events.jsonl']) fs.copyFileSync(path.join(ROOT, 'docs', 'data', f), path.join(data, f));
  const portHash = sha(path.join(ROOT, 'portfolio.json'));
  const evCount = () => fs.readFileSync(path.join(data, 'ticker_tags_events.jsonl'), 'utf8').split('\n').filter(Boolean).length;

  const rwApp = createApp({ dataDir: data, repoRoot: tmp, writer: 'LAWNMOWER', hostname: 'LAWNMOWER' });
  const roApp = createApp({ dataDir: data, repoRoot: tmp, writer: '', hostname: 'LAWNMOWER' });
  const rw = await new Promise(r => { const s = rwApp.app.listen(0, '127.0.0.1', () => r(s)); });
  const ro = await new Promise(r => { const s = roApp.app.listen(0, '127.0.0.1', () => r(s)); });

  const dbgPort = await freePort();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-prof-'));
  const proc = spawn(exe, ['--headless=new', `--remote-debugging-port=${dbgPort}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', '--disable-gpu', 'about:blank'], { stdio: 'ignore', detached: false });
  let browser;
  for (let i = 0; i < 60 && !browser; i++) { try { browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${dbgPort}` }); } catch (_) { await sleep(500); } }
  if (!browser) { check('arrancar el navegador headless', false, 'no se pudo conectar'); proc.kill(); return; }

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1500, height: 1000 });
    const pageErrors = [];
    page.on('pageerror', e => pageErrors.push(String(e.message || e)));
    page.on('dialog', d => d.dismiss().catch(() => {}));
    const open = async (srv) => { await page.goto(`http://127.0.0.1:${srv.address().port}/portfolio.html`, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => document.querySelectorAll('.sec-table').length > 5 && document.body.innerText.includes('Agrupar por'), { timeout: 60000, polling: 500 }); };
    const txt = () => page.evaluate(() => document.body.innerText);
    const count = (sel) => page.evaluate((s) => document.querySelectorAll(s).length, sel);
    const select = async (value) => { await page.evaluate((v) => { const sel = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.value === 'sections')); const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(sel, v); sel.dispatchEvent(new Event('change', { bubbles: true })); }, value); await sleep(400); };

    // ── vista actual intacta ─────────────────────────────────────────────
    await open(rw);
    const secTables = await count('.sec-table');
    const t0 = await txt();
    check('F6 vista por defecto «Secciones»: las 13 secciones y su tabla siguen ahí', secTables === 13 && t0.includes('CARTERA') && t0.includes('CANNABIS') && t0.includes('+ posición'), `tablas ${secTables}`);
    check('F6 la barra de etiquetas aparece con la función de edición habilitada', t0.includes('Agrupar por') && t0.includes('＋ etiqueta') && !t0.includes('solo lectura'));
    const hdrs0 = await page.evaluate(() => [...document.querySelectorAll('.sec-table thead tr')][0].innerText);
    check('F6 las columnas de la tabla no cambian (Ticker … Notas)', ['ticker', 'precio', 'rsi', 'estado', 'macd', 'flow', 'notas'].every(c => hdrs0.toLowerCase().includes(c)), hdrs0.slice(0, 200));
    const rows0 = await count('.sec-table tbody tr');

    // ── agrupar por temática ────────────────────────────────────────────
    await select('theme');
    const t1 = await txt();
    check('F6 «Temática»: aparecen grupos con recuentos descriptivos', /CANNABIS/i.test(t1) && /\d+ instrumentos? · \d+ empresas?/.test(t1), t1.slice(0, 300));
    check('F6 …sin porcentajes ni «x de y» en las cabeceras', !/\d+ ?% /.test((await page.evaluate(() => [...document.querySelectorAll('div')].filter(d => /instrumentos? ·/.test(d.innerText) && d.children.length < 4).map(d => d.innerText).join(' | '))).slice(0, 4000)));
    check('F6 …sin botones de sección (+ posición / renombrar / borrar) en los grupos', !t1.includes('+ posición'));
    check('F6 …y el grupo «Sin clasificar (en esta vista)» existe', /SIN CLASIFICAR/i.test(t1));
    const groupHdr = await page.evaluate(() => [...document.querySelectorAll('span')].filter(s => /CANNABIS/i.test(s.innerText) && s.innerText.length < 60).map(s => s.parentElement.innerText).slice(0, 2));
    check('F6 la cabecera del grupo Cannabis muestra «N instrumentos · M empresas»', groupHdr.some(h => /\d+ instrumentos · \d+ empresas/.test(h)), JSON.stringify(groupHdr));
    const rowsTheme = await count('.sec-table tbody tr');
    check('F6 vista por grupos reutiliza la misma tabla (filas de datos presentes)', rowsTheme > 100, `${rowsTheme} filas vs ${rows0} en secciones`);
    check('F6 «↻ también en…» aparece para tickers en varios grupos', (await txt()).includes('también en'));

    // ── búsqueda, filtros y plegado ─────────────────────────────────────
    await page.type('input[placeholder^="Buscar ticker"]', 'NVDA'); await sleep(400);
    const tN = await txt();
    check('F6 búsqueda «NVDA»: solo grupos que contienen NVDA', (tN.match(/NVDA/g) || []).length >= 1 && !tN.includes('GGAL'), '');
    await page.evaluate(() => { const i = document.querySelector('input[placeholder^="Buscar ticker"]'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(i, ''); i.dispatchEvent(new Event('input', { bubbles: true })); }); await sleep(300);
    await page.evaluate(() => { const sel = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.textContent.startsWith('+ Filtrar'))); const opt = [...sel.options].find(o => o.value === 'commodity:gold'); const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(sel, opt.value); sel.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(400);
    const tF = await txt();
    check('F6 filtro por etiqueta (oro): aparece el chip y se reducen los grupos', tF.includes('Materia prima: Metales preciosos › Oro') && (await count('.sec-table')) < 30, `${await count('.sec-table')} tablas`);
    await page.evaluate(() => [...document.querySelectorAll('button')].find(b => b.innerText.includes('limpiar filtros')).click()); await sleep(300);
    const before = await count('.sec-table');
    await page.evaluate(() => [...document.querySelectorAll('button')].find(b => b.innerText.includes('▾ ocultar')).click()); await sleep(300);
    check('F6 plegar un grupo oculta su tabla', (await count('.sec-table')) === before - 1, `${before} → ${await count('.sec-table')}`);

    // ── edición: confirmar una asignación desde el modal 🏷 ─────────────
    await select('commodity');
    const evBefore = evCount();
    await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => x.innerText.startsWith('🏷') && x.title.startsWith('Clasificación')); b.click(); }); await sleep(600);
    const modalTxt = await txt();
    check('F6 el botón 🏷 abre el modal de clasificación con identidad y fuentes', modalTxt.includes('Clasificación ·') && /sin verificar|verificada/.test(modalTxt) && modalTxt.includes('YAHOO (REFERENCIA)'));
    const pend = await page.evaluate(() => { const b = [...document.querySelectorAll('.modal button')].find(x => x.title === 'Confirmar'); if (!b) return false; b.click(); return true; });
    await sleep(900);
    check('F6 confirmar una asignación escribe UN evento en el registro', pend && evCount() === evBefore + 1, `${evBefore} → ${evCount()}`);
    const last = fs.readFileSync(path.join(data, 'ticker_tags_events.jsonl'), 'utf8').trim().split('\n').pop();
    check('F6 …es un evento `review` con antes/después', JSON.parse(last).op === 'review' && JSON.parse(last).before.review_status === 'pending' && JSON.parse(last).after.review_status === 'confirmed', last.slice(0, 160));
    check('F6 …y la interfaz lo refleja (la asignación pasa a «confirmada»)', (await txt()).includes('confirmada'));
    await page.evaluate(() => document.querySelector('.modal button').click()); await sleep(300);   // ✕

    // ── editar posición desde un grupo: abre la fila correcta y no ensucia el item ──
    const ticker = await page.evaluate(() => { const b = [...document.querySelectorAll('.sec-table tbody tr')].find(r => r.querySelector('button[title="Clasificación (etiquetas del Portfolio)"]')); const t = b.querySelector('span[style*="font-weight: 700"]').innerText; b.querySelector('button[title="Clasificación (etiquetas del Portfolio)"]').nextElementSibling.click(); return t; }); await sleep(500);
    check('F6 «✎» desde un grupo abre el editor de la posición correcta', (await txt()).includes(ticker), ticker);
    await page.keyboard.press('Escape'); await page.evaluate(() => { const b = [...document.querySelectorAll('.modal button')].find(x => /cancelar|✕/i.test(x.innerText)); if (b) b.click(); }); await sleep(300);

    // ── modo solo lectura ────────────────────────────────────────────────
    await open(ro);
    const tR = await txt();
    check('F6 sin escritor: la barra avisa «solo lectura» y no ofrece publicar ni crear', tR.includes('solo lectura') && !tR.includes('＋ etiqueta') && !tR.includes('Publicar'));
    await select('industry');
    check('F6 sin escritor: la navegación por grupos funciona igual', /MINER/i.test(await txt()) && (await count('.sec-table')) > 10);
    await page.evaluate(() => [...document.querySelectorAll('button')].find(x => x.innerText.startsWith('🏷')).click()); await sleep(500);
    const mR = await txt();
    check('F6 sin escritor: el modal explica por qué y no permite editar ni añadir', mR.includes('Edición deshabilitada') && !mR.includes('Añadir (queda confirmada)'));
    check('F6 sin escritor: ningún botón de acción está habilitado', await page.evaluate(() => [...document.querySelectorAll('.modal button[title="Confirmar"],.modal button[title="Rechazar (no volverá a proponerse)"]')].every(b => b.disabled)));

    // ── invariancia ──────────────────────────────────────────────────────
    check('F6 portfolio.json byte a byte igual tras navegar, agrupar, filtrar y editar etiquetas', sha(path.join(ROOT, 'portfolio.json')) === portHash);
    check('F6 sin excepciones de JavaScript en la página', pageErrors.length === 0, pageErrors.slice(0, 3).join(' | '));
    await page.close();
  } finally {
    try { await browser.disconnect(); } catch (_) { /* ya cerrado */ }
    proc.kill();
    rw.close(); ro.close();
    await sleep(500);
    for (const d of [tmp, profile]) { try { fs.rmSync(d, { recursive: true, force: true }); } catch (_) { /* perfil en uso en Windows */ } }
  }
}

run().catch(e => check('excepción', false, e.stack)).finally(() => {
  const bad = results.filter(r => !r.ok);
  for (const r of results) console.log((r.ok ? '  ok   ' : '  FAIL ') + r.name + (r.detail ? '\n         ' + r.detail : ''));
  console.log(`\n${results.length - bad.length}/${results.length} passed`);
  process.exit(bad.length ? 1 : 0);
});
