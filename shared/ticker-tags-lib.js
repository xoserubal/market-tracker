/*
 * ticker-tags-lib.js — taxonomía de etiquetas del Portfolio Tracker (línea A).
 *
 * Fuente única de esquema, validación y consultas. La usan server.js (vía ticker-tags-store.js),
 * el script de siembra y portfolio.html (navegador). UMD: global `TickerTags` o module.exports.
 *
 * AISLAMIENTO: ningún motor de inversión (PCS, Flow, Sol, carteras) lee este módulo ni sus ficheros.
 * Lo garantizan scripts/test_tags_invariance.py y el workflow tags-isolation.yml.
 *
 * Modelo (wiki/DISENO_PORTFOLIO_TAGS_DEFINITIVO.md v2):
 *   · issuers      — empresa/emisor económico. Las etiquetas económicas se asignan AL EMISOR.
 *   · instruments  — instrumento cotizado (ticker). Apunta a UN emisor (sin cadenas ni ciclos).
 *   · tags         — vocabulario `dimension:slug`, con `parent` opcional.
 *   · assignments  — (dentro del emisor) etiqueta + relación/intensidad/nav_primary + fuente/confianza/revisión.
 *
 * La fuente de verdad es el registro de eventos (ticker_tags_events.jsonl); ticker_tags.json es el estado
 * materializado y debe cumplir  replay(eventos) == estado.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TickerTags = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const SCHEMA_VERSION = 1;

  const ENUM = {
    source: ['assistant', 'derived_universe', 'derived_section', 'yahoo', 'manual'],
    confidence: ['high', 'medium', 'low'],
    review: ['pending', 'confirmed', 'rejected'],
    relation: ['direct', 'indirect', 'narrative'],
    intensity: ['high', 'low'],
    role: ['operating_company', 'fund', 'leveraged_product', 'index'],
    identity: ['verified', 'provisional', 'disputed'],
  };

  const DEFAULT_DIMENSIONS = {
    industry:     { label: 'Industria',             hierarchical: true,  exposure: false },
    commodity:    { label: 'Materia prima',         hierarchical: true,  exposure: true },
    theme:        { label: 'Temática',              hierarchical: true,  exposure: true },
    geo_exposure: { label: 'Exposición geográfica', hierarchical: true,  exposure: true },
    stage:        { label: 'Etapa',                 hierarchical: false, exposure: false, single: true },
    asset_class:  { label: 'Clase de activo',       hierarchical: false, exposure: false, single: true },
    macro_driver: { label: 'Driver macro',          hierarchical: false, exposure: true, reserved: true },
  };

  // Fuentes de identidad que cuentan como "independientes" de Yahoo para marcar `verified`.
  const STRONG_IDENTITY_TYPES = ['exchange', 'company', 'regulator'];

  class TagError extends Error {
    constructor(code, message, details) {
      super(message);
      this.name = 'TagError';
      this.code = code;            // validation | not_found | stale_revision | unknown_op
      this.details = details || null;
    }
  }
  const fail = (msg, details) => { throw new TagError('validation', msg, details); };

  // ── utilidades ────────────────────────────────────────────────────────────
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const isStr = (v) => typeof v === 'string' && v.length > 0;
  const isDate = (v) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && !isNaN(Date.parse(v + 'T00:00:00Z'));
  const TAG_RE = /^[a-z_]+:[a-z0-9_]+$/;
  const TICKER_RE = /^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$/;
  const dimOf = (tag) => tag.split(':')[0];

  function dayBefore(iso) {
    const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - 1);
    return d.toISOString().slice(0, 10);
  }

  function emptyState() {
    return {
      schema_version: SCHEMA_VERSION, revision: 0,
      dimensions: clone(DEFAULT_DIMENSIONS), tags: {},
      issuers: {}, instruments: {},
      counters: { issuer: 0, instrument: 0, assignment: 0 },
    };
  }

  const nextId = (state, kind, prefix, width) =>
    prefix + String(++state.counters[kind]).padStart(width, '0');

  // ── identidad de instrumentos: periodos de uso de un ticker ───────────────
  // Intervalo inclusivo [from, to]; from=null → -∞ ; to=null → +∞ (solo el ticker vigente).
  function tickerUses(inst) {
    const uses = [{ ticker: inst.ticker, from: inst.ticker_from || null, to: null }];
    for (const h of inst.ticker_history || []) uses.push({ ticker: h.ticker, from: h.from || null, to: h.to });
    return uses;
  }
  const overlaps = (a, b) => {
    const aFrom = a.from || '0000-00-00', bFrom = b.from || '0000-00-00';
    const aTo = a.to || '9999-99-99', bTo = b.to || '9999-99-99';
    return aFrom <= bTo && bFrom <= aTo;
  };

  function checkTickerUses(state, inst, selfId) {
    const mine = tickerUses(inst);
    for (const h of inst.ticker_history || []) {
      if (!TICKER_RE.test(h.ticker)) fail('ticker histórico inválido', { ticker: h.ticker });
      if (!isDate(h.to)) fail('cada ticker histórico necesita fecha `to`', { ticker: h.ticker });
      if (h.from != null && !isDate(h.from)) fail('fecha `from` inválida en histórico', { ticker: h.ticker });
      if (h.from && h.from > h.to) fail('histórico con from > to', { ticker: h.ticker });
    }
    for (let i = 0; i < mine.length; i++)
      for (let j = i + 1; j < mine.length; j++)
        if (mine[i].ticker === mine[j].ticker && overlaps(mine[i], mine[j]))
          fail('el mismo ticker aparece dos veces en periodos solapados dentro del instrumento', { ticker: mine[i].ticker });
    for (const [id, other] of Object.entries(state.instruments)) {
      if (id === selfId) continue;
      for (const a of mine) for (const b of tickerUses(other))
        if (a.ticker === b.ticker && overlaps(a, b))
          fail(`el ticker ${a.ticker} ya lo usa ${id} en un periodo solapado`, { ticker: a.ticker, other: id });
    }
  }

  // ── reglas de una asignación ──────────────────────────────────────────────
  const activeOf = (issuer) => issuer.assignments.filter(a => !a.removed_at);
  const livingOf = (issuer) => activeOf(issuer).filter(a => a.review_status !== 'rejected');

  function checkAssignmentShape(state, a) {
    if (!TAG_RE.test(a.tag)) fail('etiqueta con formato inválido', { tag: a.tag });
    const tag = state.tags[a.tag];
    if (!tag) fail('la etiqueta no existe en el vocabulario', { tag: a.tag });
    const dim = state.dimensions[dimOf(a.tag)];
    if (!dim) fail('dimensión desconocida', { tag: a.tag });
    if (dim.reserved) fail('dimensión reservada: aún no admite asignaciones', { tag: a.tag });
    if (!ENUM.source.includes(a.source)) fail('source inválida', { source: a.source });
    if (!ENUM.confidence.includes(a.confidence)) fail('confidence inválida', { confidence: a.confidence });
    if (!ENUM.review.includes(a.review_status)) fail('review_status inválido', { review_status: a.review_status });
    if (a.effective_from != null && !isDate(a.effective_from)) fail('effective_from inválida');
    if (a.effective_to != null && !isDate(a.effective_to)) fail('effective_to inválida');
    if (a.effective_from && a.effective_to && a.effective_from > a.effective_to) fail('effective_from posterior a effective_to');
    if (typeof a.note !== 'string' || a.note.length > 300) fail('note debe ser texto de hasta 300 caracteres');
    if (dim.exposure) {
      if (!ENUM.relation.includes(a.relation)) fail('esta dimensión exige `relation` (direct|indirect|narrative)', { tag: a.tag });
      if (a.relation === 'narrative') { if (a.intensity != null) fail('una relación narrative no lleva intensidad'); }
      else if (!ENUM.intensity.includes(a.intensity)) fail('direct/indirect exigen `intensity` (high|low)');
      if (a.nav_primary && a.relation === 'narrative') fail('una asignación narrative no puede ser nav_primary');
    } else {
      if (a.relation != null || a.intensity != null) fail('relation/intensity solo existen en dimensiones de exposición', { tag: a.tag });
      if (a.nav_primary) fail('nav_primary solo existe en dimensiones de exposición', { tag: a.tag });
    }
  }

  // Reglas entre asignaciones de un mismo emisor.
  function checkIssuerRules(state, issuer, issuerId) {
    const live = livingOf(issuer);
    const seen = new Set();
    for (const a of activeOf(issuer)) {
      if (seen.has(a.tag)) fail('etiqueta duplicada en el emisor', { issuer: issuerId, tag: a.tag });
      seen.add(a.tag);
    }
    const byDim = {};
    for (const a of live) (byDim[dimOf(a.tag)] = byDim[dimOf(a.tag)] || []).push(a);
    for (const [d, list] of Object.entries(byDim)) {
      const dim = state.dimensions[d];
      if (dim.single && list.length > 1) fail(`la dimensión ${d} admite una sola asignación activa`, { issuer: issuerId });
      const navs = list.filter(a => a.nav_primary);
      if (navs.length > 1) fail(`más de una etiqueta principal en ${d}`, { issuer: issuerId });
      if (navs.length === 1 && navs[0].relation === 'indirect' && list.some(a => a.relation === 'direct'))
        fail('nav_primary sobre vínculo indirecto solo se permite si no hay ninguno directo en la dimensión', { issuer: issuerId, dimension: d });
    }
    for (const a of activeOf(issuer).filter(x => x.review_status === 'rejected' && x.nav_primary))
      fail('una asignación rechazada no puede ser nav_primary', { issuer: issuerId, tag: a.tag });
  }

  // ── operaciones (reducer). Validan ANTES de mutar. Mutan `state` in situ. ──
  const OPS = {};

  OPS.create_tag = (state, args) => {
    if (!TAG_RE.test(args.tag || '')) fail('tag debe tener formato dimension:slug (minúsculas, dígitos y _)');
    const dim = state.dimensions[dimOf(args.tag)];
    if (!dim) fail('dimensión desconocida', { dimension: dimOf(args.tag) });
    if (state.tags[args.tag]) fail('la etiqueta ya existe', { tag: args.tag });
    if (!isStr(args.label) || args.label.length > 80) fail('label obligatorio (≤ 80 caracteres)');
    if (args.parent != null) {
      if (!dim.hierarchical) fail('esta dimensión no es jerárquica');
      const p = state.tags[args.parent];
      if (!p) fail('parent inexistente', { parent: args.parent });
      if (dimOf(args.parent) !== dimOf(args.tag)) fail('parent de otra dimensión');
    }
    const t = { label: args.label, parent: args.parent || null, status: 'active' };
    if (args.context) t.context = clone(args.context);
    state.tags[args.tag] = t;
    return { id: args.tag, after: clone(t) };
  };

  OPS.retire_tag = (state, args) => {
    const t = state.tags[args.tag];
    if (!t) throw new TagError('not_found', 'etiqueta inexistente');
    const before = clone(t); t.status = 'retired';
    return { before, after: clone(t) };
  };

  OPS.create_issuer = (state, args) => {
    if (!isStr(args.legal_name) || args.legal_name.length > 160) fail('legal_name obligatorio (≤ 160)');
    const status = args.identity_status || 'provisional';
    if (!ENUM.identity.includes(status)) fail('identity_status inválido');
    if (status === 'verified') fail('un emisor nuevo no puede nacer verified: usa set_identity con fuentes');
    const sources = args.identity_sources || [];
    if (!Array.isArray(sources) || sources.some(s => !isStr(s.type) || !isStr(s.ref))) fail('identity_sources inválido');
    const aliases = args.aliases || [];
    if (!Array.isArray(aliases) || aliases.some(a => !isStr(a))) fail('aliases inválido');
    const id = nextId(state, 'issuer', 'iss_', 4);
    state.issuers[id] = { legal_name: args.legal_name, aliases: clone(aliases), identity_status: status,
      identity_sources: clone(sources), notes: args.notes || '', assignments: [] };
    return { id, after: clone(state.issuers[id]) };
  };

  OPS.set_identity = (state, args) => {
    const is = state.issuers[args.issuer_id];
    if (!is) throw new TagError('not_found', 'emisor inexistente');
    const before = { legal_name: is.legal_name, identity_status: is.identity_status, identity_sources: clone(is.identity_sources) };
    const status = args.identity_status;
    if (!ENUM.identity.includes(status)) fail('identity_status inválido');
    const sources = args.identity_sources != null ? args.identity_sources : is.identity_sources;
    if (!Array.isArray(sources) || sources.some(s => !isStr(s.type) || !isStr(s.ref))) fail('identity_sources inválido');
    if (status === 'verified') {
      const types = new Set(sources.map(s => s.type));
      if (types.size < 2 || !STRONG_IDENTITY_TYPES.some(t => types.has(t)))
        fail('verified exige ≥ 2 fuentes de tipo distinto y al menos una de bolsa, empresa o regulador (Yahoo solo no basta)');
    }
    if (args.legal_name != null) { if (!isStr(args.legal_name)) fail('legal_name inválido'); is.legal_name = args.legal_name; }
    is.identity_status = status; is.identity_sources = clone(sources);
    return { before, after: { legal_name: is.legal_name, identity_status: is.identity_status, identity_sources: clone(is.identity_sources) } };
  };

  OPS.create_instrument = (state, args) => {
    const ticker = String(args.ticker || '').toUpperCase();
    if (!TICKER_RE.test(ticker)) fail('ticker inválido', { ticker });
    if (!state.issuers[args.issuer_id]) fail('el emisor no existe', { issuer_id: args.issuer_id });
    const role = args.role || 'operating_company';
    if (!ENUM.role.includes(role)) fail('role inválido');
    const leveraged = !!args.leveraged;
    if (role === 'leveraged_product' && !leveraged) fail('un producto apalancado debe llevar leveraged=true');
    if (args.ticker_from != null && !isDate(args.ticker_from)) fail('ticker_from inválida');
    const inst = { ticker, ticker_from: args.ticker_from || null, issuer_id: args.issuer_id, role, leveraged, ticker_history: [] };
    checkTickerUses(state, inst, null);
    const id = nextId(state, 'instrument', 'ins_', 4);
    state.instruments[id] = inst;
    return { id, after: clone(inst) };
  };

  OPS.change_ticker = (state, args) => {
    const inst = state.instruments[args.instrument_id];
    if (!inst) throw new TagError('not_found', 'instrumento inexistente');
    const nt = String(args.new_ticker || '').toUpperCase();
    if (!TICKER_RE.test(nt)) fail('new_ticker inválido');
    if (nt === inst.ticker) fail('el ticker nuevo es el actual');
    if (!isDate(args.effective_date)) fail('effective_date (YYYY-MM-DD) obligatoria');
    if (inst.ticker_from && args.effective_date <= inst.ticker_from) fail('effective_date debe ser posterior al inicio del ticker actual');
    const next = clone(inst);
    next.ticker_history.push({ ticker: inst.ticker, from: inst.ticker_from || null, to: dayBefore(args.effective_date), reason: args.reason || '' });
    next.ticker = nt; next.ticker_from = args.effective_date;
    checkTickerUses(state, next, args.instrument_id);
    const before = clone(inst);
    state.instruments[args.instrument_id] = next;
    return { before, after: clone(next) };
  };

  function findAssignment(state, issuerId, aid) {
    const is = state.issuers[issuerId];
    if (!is) throw new TagError('not_found', 'emisor inexistente');
    const a = is.assignments.find(x => x.aid === aid);
    if (!a) throw new TagError('not_found', 'asignación inexistente');
    return { is, a };
  }

  OPS.assign = (state, args, ts) => {
    const is = state.issuers[args.issuer_id];
    if (!is) throw new TagError('not_found', 'emisor inexistente');
    const tag = state.tags[args.tag];
    if (tag && tag.status !== 'active') fail('la etiqueta está retirada', { tag: args.tag });
    const review = args.review_status || 'pending';
    const a = {
      aid: null, tag: args.tag,
      relation: args.relation == null ? null : args.relation,
      intensity: args.intensity == null ? null : args.intensity,
      nav_primary: !!args.nav_primary,
      source: args.source || 'manual', confidence: args.confidence || 'medium', review_status: review,
      effective_from: args.effective_from || null, effective_to: args.effective_to || null,
      recorded_at: ts, reviewed_at: review === 'pending' ? null : ts, removed_at: null,
      note: args.note || '',
    };
    checkAssignmentShape(state, a);
    const trial = clone(is); a.aid = nextId({ counters: { assignment: state.counters.assignment } }, 'assignment', 'a_', 5);
    trial.assignments.push(a);
    checkIssuerRules(state, trial, args.issuer_id);
    a.aid = nextId(state, 'assignment', 'a_', 5);
    is.assignments.push(a);
    return { id: a.aid, after: clone(a) };
  };

  const EDITABLE = ['relation', 'intensity', 'confidence', 'effective_from', 'effective_to', 'note'];
  OPS.update_assignment = (state, args) => {
    const { is, a } = findAssignment(state, args.issuer_id, args.aid);
    if (a.removed_at) fail('la asignación está retirada');
    const ch = args.changes || {};
    const bad = Object.keys(ch).filter(k => !EDITABLE.includes(k));
    if (bad.length || !Object.keys(ch).length) fail('changes inválido: campos editables = ' + EDITABLE.join(', '), { bad });
    const next = { ...a, ...ch };
    if ('relation' in ch && ch.relation === 'narrative' && !('intensity' in ch)) next.intensity = null;
    checkAssignmentShape(state, next);
    const trial = clone(is); trial.assignments = trial.assignments.map(x => x.aid === a.aid ? next : x);
    checkIssuerRules(state, trial, args.issuer_id);
    const before = clone(a); Object.assign(a, next);
    return { before, after: clone(a) };
  };

  OPS.set_nav_primary = (state, args) => {
    const { is, a } = findAssignment(state, args.issuer_id, args.aid);
    if (a.removed_at || a.review_status === 'rejected') fail('solo una asignación viva puede ser principal');
    const dim = state.dimensions[dimOf(a.tag)];
    if (!dim.exposure) fail('nav_primary no existe en esta dimensión');
    const trial = clone(is);
    const same = trial.assignments.filter(x => !x.removed_at && dimOf(x.tag) === dimOf(a.tag));
    const before = same.map(x => ({ aid: x.aid, nav_primary: x.nav_primary }));
    same.forEach(x => { x.nav_primary = (x.aid === a.aid) && args.value !== false; });
    checkAssignmentShape(state, trial.assignments.find(x => x.aid === a.aid));
    checkIssuerRules(state, trial, args.issuer_id);
    is.assignments = trial.assignments;
    return { before, after: same.map(x => ({ aid: x.aid, nav_primary: x.nav_primary })) };
  };

  OPS.review = (state, args, ts) => {
    const { a } = findAssignment(state, args.issuer_id, args.aid);
    if (a.removed_at) fail('la asignación está retirada');
    if (!ENUM.review.includes(args.review_status)) fail('review_status inválido');
    const before = { review_status: a.review_status, reviewed_at: a.reviewed_at, nav_primary: a.nav_primary };
    a.review_status = args.review_status;
    a.reviewed_at = args.review_status === 'pending' ? null : ts;
    if (args.review_status === 'rejected') a.nav_primary = false;
    return { before, after: { review_status: a.review_status, reviewed_at: a.reviewed_at, nav_primary: a.nav_primary } };
  };

  OPS.retire_assignment = (state, args, ts) => {
    const { a } = findAssignment(state, args.issuer_id, args.aid);
    if (a.removed_at) fail('la asignación ya está retirada');
    const before = { removed_at: a.removed_at, nav_primary: a.nav_primary };
    a.removed_at = ts; a.nav_primary = false;
    return { before, after: { removed_at: a.removed_at, nav_primary: a.nav_primary } };
  };

  const OP_NAMES = Object.keys(OPS);

  /** Aplica una operación sobre `state` (mutándolo). Lanza TagError sin haber mutado si no es válida. */
  function applyOp(state, op, args, ts) {
    if (!OPS[op]) throw new TagError('unknown_op', 'operación desconocida: ' + op);
    if (!args || typeof args !== 'object') fail('args obligatorio');
    if (!isStr(ts)) fail('ts obligatorio');
    return OPS[op](state, args, ts) || {};
  }

  /** Aplica un evento ya registrado (replay). */
  function applyEvent(state, ev) {
    applyOp(state, ev.op, ev.args, ev.ts);
    state.revision = ev.seq;
    return state;
  }

  function replay(events, uptoTs) {
    const st = emptyState();
    for (const ev of events) {
      if (uptoTs && ev.ts > uptoTs) break;
      applyEvent(st, ev);
    }
    return st;
  }

  // Estado en el que el sistema SABÍA lo que sabía al final del día `isoDate` (point-in-time real).
  const stateAt = (events, isoDate) => replay(events, isoDate + 'T23:59:59.999Z');

  /** Invariantes globales; devuelve lista de problemas (vacía = ok). */
  function validateState(state) {
    const problems = [];
    const guard = (fn) => { try { fn(); } catch (e) { if (e instanceof TagError) problems.push(e.message + (e.details ? ' ' + JSON.stringify(e.details) : '')); else throw e; } };
    if (state.schema_version !== SCHEMA_VERSION) problems.push('schema_version inesperada');
    for (const [id, inst] of Object.entries(state.instruments)) {
      guard(() => { if (!state.issuers[inst.issuer_id]) fail('instrumento con emisor inexistente', { id }); });
      guard(() => checkTickerUses(state, inst, id));
      guard(() => { if (!ENUM.role.includes(inst.role)) fail('role inválido', { id }); });
    }
    for (const [id, is] of Object.entries(state.issuers)) {
      guard(() => { if (!ENUM.identity.includes(is.identity_status)) fail('identity_status inválido', { id }); });
      for (const a of is.assignments) guard(() => checkAssignmentShape(state, a));
      guard(() => checkIssuerRules(state, is, id));
    }
    for (const [t, tag] of Object.entries(state.tags)) {
      guard(() => { if (tag.parent && !state.tags[tag.parent]) fail('parent inexistente', { tag: t }); });
      guard(() => { if (!state.dimensions[dimOf(t)]) fail('dimensión inexistente', { tag: t }); });
    }
    const maxId = (obj, re) => Math.max(0, ...Object.keys(obj).map(k => +(k.match(re) || [0, 0])[1]));
    if (state.counters.issuer < maxId(state.issuers, /^iss_(\d+)$/)) problems.push('contador de emisores por debajo de un id existente');
    if (state.counters.instrument < maxId(state.instruments, /^ins_(\d+)$/)) problems.push('contador de instrumentos por debajo de un id existente');
    return problems;
  }

  // ── consultas ─────────────────────────────────────────────────────────────
  const tagLabel = (state, tag) => (state.tags[tag] || {}).label || tag;
  function tagPath(state, tag) {
    const out = []; let t = tag; const guardN = 8;
    for (let i = 0; t && i < guardN; i++) { out.unshift(tagLabel(state, t)); t = (state.tags[t] || {}).parent; }
    return out;
  }
  function ancestors(state, tag) {
    const out = []; let t = tag;
    for (let i = 0; t && i < 8; i++) { out.push(t); t = (state.tags[t] || {}).parent; }
    return out;
  }

  /** Resuelve un ticker a su instrumento. Con `asOf` (YYYY-MM-DD) tiene en cuenta tickers históricos y reutilizados. */
  function resolveInstrument(state, ticker, asOf) {
    const T = String(ticker || '').toUpperCase();
    for (const [id, inst] of Object.entries(state.instruments)) {
      for (const u of tickerUses(inst)) {
        if (u.ticker !== T) continue;
        if (!asOf) { if (u.to === null) return { id, inst }; continue; }
        if ((u.from || '0000-00-00') <= asOf && asOf <= (u.to || '9999-99-99')) return { id, inst };
      }
    }
    return null;
  }

  const MARKETS = [
    ['.TO', 'Canadá (TSX)'], ['.V', 'Canadá (TSX-V)'], ['.AX', 'Australia (ASX)'], ['.XA', 'Australia (Cboe AU)'],
    ['.L', 'Reino Unido'], ['.DE', 'Alemania (Xetra)'], ['.HM', 'Alemania (Hamburgo)'], ['.F', 'Alemania (Fráncfort)'],
    ['.AS', 'Países Bajos'], ['.MI', 'Italia'], ['.MC', 'España'], ['.ST', 'Suecia'], ['.PA', 'Francia'], ['.NZ', 'Nueva Zelanda'],
  ];
  /** Mercado de cotización derivado del sufijo (no se guarda). */
  function listingMarket(ticker) {
    const T = String(ticker || '').toUpperCase();
    if (T.startsWith('^')) return 'Índices';
    for (const [suf, label] of MARKETS) if (T.endsWith(suf)) return label;
    return 'EE. UU.';
  }

  function view(state, ticker) {
    const r = resolveInstrument(state, ticker);
    if (!r) return null;
    const issuer = state.issuers[r.inst.issuer_id];
    return { instrumentId: r.id, instrument: r.inst, issuerId: r.inst.issuer_id, issuer, assignments: activeOf(issuer) };
  }

  const ROLE_LABEL = { operating_company: 'empresa', fund: 'fondo', leveraged_product: 'apalancado', index: 'índice' };

  function emptyCounts() { return { instruments: 0, companies: 0, funds: 0, leveraged: 0, indexes: 0 }; }
  function countRows(rows) {
    const c = emptyCounts(); const issuers = new Set();
    for (const r of rows) {
      c.instruments++;
      if (r.role === 'operating_company') issuers.add(r.issuerId);
      else if (r.role === 'fund') c.funds++;
      else if (r.role === 'leveraged_product') c.leveraged++;
      else if (r.role === 'index') c.indexes++;
    }
    c.companies = issuers.size;
    return c;
  }
  /** "9 instrumentos · 8 empresas · 1 fondo" — solo recuentos descriptivos, sin porcentajes. */
  function countsLabel(c) {
    const plural = (n, s, p) => `${n} ${n === 1 ? s : p}`;
    const parts = [plural(c.instruments, 'instrumento', 'instrumentos'), plural(c.companies, 'empresa', 'empresas')];
    if (c.funds) parts.push(plural(c.funds, 'fondo', 'fondos'));
    if (c.leveraged) parts.push(plural(c.leveraged, 'apalancado', 'apalancados'));
    if (c.indexes) parts.push(plural(c.indexes, 'índice', 'índices'));
    return parts.join(' · ');
  }

  /**
   * Filtro y agrupación para la UI.
   *   tickers   — lista de tickers del Portfolio (los que existan en `state`; el resto cae en "sin clasificar").
   *   dimension — 'industry'|'commodity'|'theme'|'geo_exposure'|'stage'|'asset_class'|'listing_market'
   *   opts      — { level:'leaf'|'parent', onlyConfirmed, showNarrative, onePerInstrument,
   *                 tagFilters:{dim:[tags]}, search }
   * Un instrumento puede aparecer en varios grupos (misma fila lógica, marcada `alsoIn`), pero los totales
   * globales cuentan instrumentos únicos.
   */
  function groupTickers(state, tickers, dimension, opts) {
    const o = Object.assign({ level: 'leaf', onlyConfirmed: false, showNarrative: false, onePerInstrument: false, tagFilters: {}, search: '' }, opts || {});
    const q = (o.search || '').trim().toLowerCase();
    const qualifies = (a) => !a.removed_at && a.review_status !== 'rejected'
      && (!o.onlyConfirmed || a.review_status === 'confirmed')
      && (o.showNarrative || a.relation !== 'narrative');

    // 1) instrumentos visibles (búsqueda + filtros por etiqueta)
    const rows = [];
    for (const ticker of tickers) {
      const v = view(state, ticker);
      const base = v ? { ticker, instrumentId: v.instrumentId, issuerId: v.issuerId, role: v.instrument.role, name: v.issuer.legal_name, assignments: v.assignments, classified: true }
                     : { ticker, instrumentId: null, issuerId: 'ticker:' + ticker, role: 'operating_company', name: '', assignments: [], classified: false };
      if (q && !(ticker.toLowerCase().includes(q) || base.name.toLowerCase().includes(q))) continue;
      let ok = true;
      for (const [d, tags] of Object.entries(o.tagFilters || {})) {
        if (!tags || !tags.length) continue;
        const hit = base.assignments.some(a => dimOf(a.tag) === d && qualifies(a) && ancestors(state, a.tag).some(t => tags.includes(t)));
        if (!hit) { ok = false; break; }
      }
      if (ok) rows.push(base);
    }

    // 2) clave(s) de grupo por instrumento
    const groups = new Map(); const unclassified = [];
    const place = (key, label, path, row, assignment) => {
      if (!groups.has(key)) groups.set(key, { key, label, path, rows: [] });
      groups.get(key).rows.push(Object.assign({}, row, { assignment: assignment || null }));
    };
    for (const row of rows) {
      if (dimension === 'listing_market') { const m = listingMarket(row.ticker); place('mkt:' + m, m, [m], row); continue; }
      let mine = row.assignments.filter(a => dimOf(a.tag) === dimension && qualifies(a));
      if (o.onePerInstrument) {
        const prim = mine.find(a => a.nav_primary);
        mine = prim ? [prim] : [];
        if (!prim && row.assignments.some(a => dimOf(a.tag) === dimension && qualifies(a)))
          { place('none:principal', 'Sin etiqueta principal', ['Sin etiqueta principal'], row); continue; }
      }
      if (!mine.length) { unclassified.push(row); continue; }
      const seen = new Set();
      for (const a of mine) {
        let tag = a.tag;
        if (o.level === 'parent') { const p = (state.tags[tag] || {}).parent; if (p) tag = p; }
        if (seen.has(tag)) continue; seen.add(tag);
        place('tag:' + tag, tagLabel(state, tag), tagPath(state, tag), row, a);
      }
    }

    // 3) marcas "también en…"
    const out = [...groups.values()];
    const where = new Map();
    for (const g of out) for (const r of g.rows) (where.get(r.ticker) || where.set(r.ticker, []).get(r.ticker)).push(g.label);
    for (const g of out) {
      g.rows.sort((a, b) => a.ticker.localeCompare(b.ticker));
      g.rows.forEach(r => { r.alsoIn = (where.get(r.ticker) || []).filter(l => l !== g.label); });
      g.counts = countRows(g.rows);
    }
    out.sort((a, b) => a.path.join('›').localeCompare(b.path.join('›'), 'es'));
    const unique = new Set(rows.map(r => r.ticker));
    return {
      groups: out,
      unclassified: { rows: unclassified.sort((a, b) => a.ticker.localeCompare(b.ticker)), counts: countRows(unclassified) },
      totals: { instruments: unique.size, issuers: new Set(rows.map(r => r.issuerId)).size },
    };
  }

  /** Nº de instrumentos distintos que verían el cálculo de "empresas" (útil para tests). */
  const uniqueTickers = (grouped) => new Set([].concat(...grouped.groups.map(g => g.rows.map(r => r.ticker))).concat(grouped.unclassified.rows.map(r => r.ticker)));

  return {
    SCHEMA_VERSION, ENUM, DEFAULT_DIMENSIONS, OP_NAMES, TagError,
    emptyState, applyOp, applyEvent, replay, stateAt, validateState, clone,
    resolveInstrument, view, listingMarket, tagLabel, tagPath, ancestors,
    groupTickers, countRows, countsLabel, uniqueTickers, ROLE_LABEL, dimOf,
  };
});
