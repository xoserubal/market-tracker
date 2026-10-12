#!/usr/bin/env node
// ── Aviso Telegram: ETFs inversos (UVXY/SQQQ/GLL/BOIL) ──────────────────────
//
// Clasifica cada ETF con shared/inverse-etf-lib.js (misma fuente que la página
// inversos.html) y avisa por Telegram cuando el estado SUBE de nivel:
//   calma → spike        "spike detectado, vigilar"
//   calma/spike → fading "ventana de venta de prima"
// No avisa al bajar de nivel ni mientras el estado se mantiene (dedup por
// transición, estado en docs/data/inverse_etf_alert_state.json). Si hay datos
// de opciones recientes (inverse_etf_options_summary.jsonl) se adjuntan IV, IV/RV,
// skew y spread al mensaje. Solo observación: no es señal de compra/venta.
// Fallo visible: si hay algo que avisar y faltan TELEGRAM_BOT_TOKEN /
// TELEGRAM_CHAT_ID, sale con código 1 (mismo criterio que check_koncorde_alerts).
//
// CLI: node scripts/inverse_etf_alert.js [--dry-run]

const fs = require('fs');
const path = require('path');
const { buildQuoteData } = require('../shared/quote-lib.js');
const { invDistAtr, INVERSE_ETFS, INV_STATE_META, classifyInverseEtf, summarizeOptions } = require('../shared/inverse-etf-lib.js');

try { require('dotenv').config(); } catch (e) { /* dotenv opcional en CI */ }

const DATA = path.join(__dirname, '..', 'docs', 'data');
const STATE = path.join(DATA, 'inverse_etf_alert_state.json');
const OPTIONS = path.join(DATA, 'inverse_etf_options_summary.jsonl');
const DRY = process.argv.includes('--dry-run');

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE, 'utf8')); } catch (e) { return {}; }
}

function latestOptionsByTicker() {
  const out = {};
  if (!fs.existsSync(OPTIONS)) return out;
  fs.readFileSync(OPTIONS, 'utf8').split('\n').filter(Boolean).forEach(l => {
    try { const r = JSON.parse(l); if (!out[r.ticker] || r.date >= out[r.ticker].date) out[r.ticker] = r; } catch (e) { /* línea corrupta */ }
  });
  return out;
}

async function sendTelegram(text) {
  const token = process.env.TELEGRAM_BOT_TOKEN, chat = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chat) return false;
  const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chat, text, parse_mode: 'HTML' }),
  });
  if (!r.ok) console.log('Telegram error', r.status, (await r.text()).slice(0, 200));
  return r.ok;
}

const pct = v => v == null ? '—' : (v >= 0 ? '+' : '') + v + '%';

(async () => {
  const unders = [...new Set(INVERSE_ETFS.map(e => e.under))];
  const quotes = {}, underQuotes = {};
  await Promise.all([
    ...INVERSE_ETFS.map(async e => { try { quotes[e.ticker] = await buildQuoteData(e.ticker); } catch (err) { console.log(`${e.ticker}: error ${err.message}`); } }),
    ...unders.map(async s => { try { underQuotes[s] = await buildQuoteData(s); } catch (err) { console.log(`${s}: error ${err.message}`); } }),
  ]);
  const opts = latestOptionsByTicker();

  const state = loadState();
  const today = new Date().toISOString().slice(0, 10);
  const alerts = [];
  INVERSE_ETFS.forEach(e => {
    const q = quotes[e.ticker], u = underQuotes[e.under];
    const c = classifyInverseEtf(e, q, u);
    const meta = INV_STATE_META[c.state];
    const prev = state[e.ticker] ? state[e.ticker].state : null;
    const prevRank = prev && INV_STATE_META[prev] ? INV_STATE_META[prev].rank : -1;
    console.log(`${e.ticker}: ${c.state} (ext=${c.extended} giro=${c.rolling} enfría=${c.cooling} nivel=${c.levelOk}) prev=${prev}`);
    // no_data no actualiza el estado: un fallo de red no debe "resetear" y re-avisar después
    if (c.state === 'no_data') return;
    if (meta.rank >= 1 && meta.rank > prevRank) alerts.push({ e, q, u, c, meta, o: summarizeOptions(opts[e.ticker]) });
    state[e.ticker] = { state: c.state, last_checked: today, last_alert: (meta.rank >= 1 && meta.rank > prevRank) ? today : (state[e.ticker] && state[e.ticker].last_alert) || null };
  });

  if (alerts.length) {
    const blocks = alerts.map(({ e, q, u, c, meta, o }) => {
      const icon = c.state === 'fading' ? '🟢' : '🟠';
      let t = `${icon} <b>${e.ticker}</b> — ${meta.label}\n`;
      t += `${q.price} · dist SMA20 ${invDistAtr(q) ?? '—'} ATR · 1D ${pct(q.d1)} · 1M ${pct(q.m1)}\n`;
      t += `${e.under} ${u ? u.price : '—'} (1S ${u ? pct(u.w1) : '—'})\n`;
      t += `Condiciones: ${c.checks.map(k => (k.v == null ? '?' : k.v ? '✓' : '✗') + ' ' + k.label).join(' · ')}\n`;
      t += `<i>${meta.desc}</i>`;
      if (e.strategy) t += '\n<b>Estructura:</b> put/put spread a 2-3 meses + call spread vendido o call ~30d rodando (no naked a 3m).';
      if (o) {
        t += `\nOpciones (${o.date}, ${o.expiry}): IV ${(o.atmIv * 100).toFixed(0)}%` +
          (o.ivRv != null ? ` · IV/RV20 ${o.ivRv.toFixed(2)}${o.rich ? ' (prima rica)' : ''}` : '') +
          (o.skew != null ? ` · skew call-put ${(o.skew * 100).toFixed(0)}pp` : '') +
          (o.spread != null ? ` · spread ${(o.spread * 100).toFixed(0)}%${o.illiquid ? ' ⚠️ ilíquido' : ''}` : '');
        if (o.term && o.term.ratio != null) t += `\nPlazos: IV 3m/1m ${o.term.ratio.toFixed(2)} ${o.term.inverted ? '(invertida: put 3m más barata por unidad de vol)' : '(normal)'}`;
      } else t += '\nOpciones: sin snapshot todavía.';
      return t;
    });
    const msg = `📉 <b>ETFs inversos</b>\n\n${blocks.join('\n\n')}\n\n<i>Solo observación. Revisa la cadena y el riesgo de cola antes de operar.</i>`;
    console.log(msg);
    if (!DRY) {
      const ok = await sendTelegram(msg);
      if (!ok) { console.log('No se pudo enviar el aviso (¿faltan TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID?)'); process.exit(1); }
    }
  }
  if (!DRY) fs.writeFileSync(STATE, JSON.stringify(state, null, 1) + '\n');
  else console.log('[dry-run] estado no escrito');
})();
