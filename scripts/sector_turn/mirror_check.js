'use strict';
// Segunda copia del registro de giros sectoriales (preregistro v2 §10): actualiza el clon local del repositorio
// privado (private/sector_turn_registry) y lo verifica a fondo contra las huellas publicadas en GitHub.
// Lo lanza una tarea semanal de Windows (MicroSectorTurnMirror) en LAWNMOWER. Avisa por Telegram si algo falla;
// si todo va bien, no avisa (solo deja constancia en mirror_check.log).
//   node scripts/sector_turn/mirror_check.js
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env'), quiet: true });

const REPO = path.join(__dirname, '..', '..');
const MIRROR = path.join(REPO, 'private', 'sector_turn_registry');
const LOG = path.join(MIRROR, '..', 'sector_turn_mirror_check.log');
const ANCHORS_URL = 'https://raw.githubusercontent.com/xoserubal/market-tracker/master/docs/data/sector_turn_anchors.jsonl';

const log = msg => { const l = `${new Date().toISOString()} ${msg}`; console.log(l); fs.appendFileSync(LOG, l + '\n'); };

(async () => {
  process.env.SECTOR_TURN_PRIVATE_DIR = MIRROR;
  const tmp = path.join(os.tmpdir(), `sector_turn_anchors_${process.pid}.jsonl`);
  process.env.SECTOR_TURN_ANCHORS = tmp;
  const R = require('./registry');
  try {
    const st = execFileSync('git', ['-C', MIRROR, 'status', '--porcelain'], { encoding: 'utf8' }).trim();
    if (st) throw new Error(`la copia local tiene cambios sin subir (no se toca): ${st.slice(0, 200)}`);
    execFileSync('git', ['-C', MIRROR, 'pull', '-q', '--ff-only'], { stdio: 'pipe' });
    const r = await fetch(ANCHORS_URL + `?t=${Date.now()}`);
    if (!r.ok) throw new Error(`no se pudieron descargar las huellas publicadas (HTTP ${r.status})`);
    fs.writeFileSync(tmp, await r.text());
    const v = R.verify({ deep: true, requireAnchors: true });
    if (!v.ok) throw new Error('la copia no supera la verificación: ' + JSON.stringify(v.problems).slice(0, 600));
    log(`OK: ${v.n} registros, último ${v.last?.week} ${v.last?.hash?.slice(0, 12)}; avisos: ${v.warnings.map(w => w.kind).join(',') || 'ninguno'}`);
  } catch (e) {
    log('FALLO: ' + (e.stderr?.toString() || e.message));
    const token = process.env.TELEGRAM_BOT_TOKEN, chat = process.env.TELEGRAM_CHAT_ID;
    if (token && chat) await fetch(`https://api.telegram.org/bot${token}/sendMessage`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chat, text: `⚠️ Copia local del registro de giros sectoriales (LAWNMOWER): ${e.message}`.slice(0, 1500) }) }).catch(() => {});
    process.exitCode = 1;
  } finally { fs.rmSync(tmp, { force: true }); }
})();
