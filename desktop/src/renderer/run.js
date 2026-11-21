// The Run screen: steps on the left, the live browser in the middle, what was sent to the model on the right.
const R = {
  id: null, running: false, flowName: null,
  items: [],            // one per model call (or per replayed step): { call, step }
  table: {},            // every message sent so far, by id; calls refer to messages by id
  selected: -1, follow: true,
  control: false, frameSize: { w: 1280, h: 800 },
  stream: null, frames: null, canSaveFlow: false, doneEvent: null,
};

// ---- small readers over a call ----
const callRefs = (c) => [...new Set(c.ids.flatMap((id) => R.table[id].refs))];
function callFlags(c) {
  const seen = new Map();
  for (const id of c.ids) for (const f of R.table[id].flags) seen.set(`${f.kind}\0${f.match}`, f);
  return [...seen.values()];
}
const callTokens = (c) => (c.usage ? c.usage.input + c.usage.cache_read + c.usage.cache_write + c.usage.output : 0);
const calls = () => R.items.map((i) => i.call).filter(Boolean);

// ---- prices (optional, kept in this browser only) ----
function loadPrices() { try { return JSON.parse(localStorage.getItem('sb.prices') || '{}'); } catch (_) { return {}; } }
function savePrices() {
  try { localStorage.setItem('sb.prices', JSON.stringify({ in: $('priceIn').value, out: $('priceOut').value })); } catch (_) { /* fine */ }
  renderUsage(); renderLedger();
}
function estimate(inTok, outTok) {
  const p = loadPrices(), pin = parseFloat(p.in), pout = parseFloat(p.out);
  if (!(pin >= 0) || !(pout >= 0) || p.in === '' || p.out === '') return null;
  return (inTok * pin + outTok * pout) / 1e6;
}
const money = (v) => (v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`);

// ---- text with placeholders and flagged values marked ----
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function richText(text, flags) {
  const values = allValues();
  const pats = ['<secret:[A-Za-z0-9_]+>', ...flags.map((f) => esc(f.match)).sort((a, b) => b.length - a.length)];
  const re = new RegExp(pats.join('|'), 'g');
  const out = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[0].startsWith('<secret:')) {
      const real = isPasswordName(m[0].slice(8, -1)) ? null : values[m[0].slice(8, -1)];   // a saved password is never shown here
      out.push(h('span', { class: 'ph' }, m[0], real ? h('s', {}, real) : null));
    } else out.push(h('span', { class: 'flag' }, m[0]));
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
const body = (m) => [...richText(m.text, m.flags || []), m.cut ? h('div', { class: 'cut' }, '… cut here for display; the model received it in full.') : null];

// ---- timeline ----
function stepTitle(step) {
  const first = String(step.result || '').split('\n')[0].trim();
  if (!first) return step.tool;                       // a replayed step: the tool field already holds the description
  const text = first.replace(/<secret:([A-Za-z0-9_]+)>/g, (_, n) => describeSecret(n) || n);
  return text.length > 90 ? `${text.slice(0, 89)}\u2026` : text;
}
function renderTimeline() {
  $('stepsEmpty').hidden = R.items.length > 0;
  const list = R.items.map((it, i) => {
    const c = it.call;
    const chips = [];
    if (c && c.usage) chips.push(h('span', { class: 'chip sent' }, `${fmt(callTokens(c))} tokens`));
    else if (c) chips.push(h('span', { class: 'chip plain' }, c.holding ? 'Waiting for your OK' : 'Waiting for the model'));
    else chips.push(h('span', { class: 'chip sent' }, '0 tokens'));
    if (c) {
      const kept = callRefs(c).length, flags = callFlags(c).length;
      if (kept) chips.push(h('span', { class: 'chip local' }, `${kept} kept private`));
      if (flags) chips.push(h('span', { class: 'chip sent' }, `${flags} looks personal`));
      if (c.masked) chips.push(h('span', { class: 'chip local' }, `${c.masked} replaced before sending`));
    }
    const title = it.step ? stepTitle(it.step) : 'Thinking…';
    return h('button', { class: `step${it.step ? '' : ' waiting'}`, type: 'button', 'aria-pressed': String(i === R.selected), onclick: () => { R.selected = i; R.follow = i === R.items.length - 1; render(); } },
      h('span', { class: 'n' }, String(i + 1)),
      h('span', {}, h('div', { class: 't' }, title), it.step && it.step.url ? h('div', { class: 'u' }, it.step.url) : null, h('div', { class: 'm' }, chips)));
  });
  const withMarks = [];
  list.forEach((el, i) => {
    if (R.turnMarks && R.turnMarks[i] != null) withMarks.push(h('div', { class: 'turnmark' }, h('b', {}, 'Follow-up'), h('span', {}, R.turnMarks[i])));
    withMarks.push(el);
  });
  if (R.turnMarks && R.turnMarks[list.length] != null) withMarks.push(h('div', { class: 'turnmark' }, h('b', {}, 'Follow-up'), h('span', {}, R.turnMarks[list.length])));
  $('steps').replaceChildren(...withMarks);
  if (R.follow) $('steps').lastElementChild?.scrollIntoView({ block: 'nearest' });
}

// ---- inspector ----
function block(cls, label, ...kids) { return h('div', { class: `blk ${cls}` }, h('b', {}, label), ...kids); }
function fold(label, ...kids) { return h('details', { class: 'blk' }, h('summary', {}, label), ...kids); }

function renderPayload(c) {
  const msgs = c.ids.map((id) => R.table[id]);
  const [sys, ...rest] = msgs;
  const firstUser = rest.findIndex((m) => m.role === 'user');
  let lastUser = -1;
  rest.forEach((m, i) => { if (m.role === 'user') lastUser = i; });
  const out = [fold('Instructions (same every call)', ...body(sys))];
  const earlier = [];
  rest.forEach((m, i) => {
    if (i === firstUser && i === lastUser) out.push(block('page', 'Task and page, as the model sees them', ...body(m)));
    else if (i === firstUser) out.push(block('task', 'Your task and this run’s rules', ...body(m)));
    else if (i === lastUser) out.push(block('page', 'Page as the model sees it', ...body(m)));
    else earlier.push(block(m.role === 'assistant' ? 'reply' : 'task', m.role === 'assistant' ? 'Model’s earlier reply' : 'Earlier page', ...body(m)));
  });
  if (earlier.length) out.splice(out.length - 1, 0, fold(`Earlier in this conversation (${earlier.length} messages)`, ...earlier));
  out.push(c.reply != null ? block('reply', 'Model’s reply', c.reply) : block('reply', 'Model’s reply', c.holding ? 'Not sent yet.' : 'Waiting for the model…'));
  return out;
}

const KIND = { value: 'A value from My info', email: 'Looks like an email address', phone: 'Looks like a phone number', card: 'Looks like a card number' };
function renderKept(c) {
  const refs = callRefs(c), flags = callFlags(c);
  const parts = [h('p', { class: 'muted' }, 'Values that stayed on this computer. The model got a placeholder, and Selfbrowse typed the real value.')];
  if (refs.length) {
    parts.push(h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'What'), h('th', {}, 'Model saw'), h('th', {}, 'Why'))),
      h('tbody', {}, refs.map((r) => h('tr', {}, h('td', {}, describeSecret(r) || r), h('td', {}, h('span', { class: 'ph' }, `<secret:${r}>`)),
        h('td', { class: 'muted' }, describeSecret(r) ? 'Matches My info' : 'Named in a saved flow'))))));
  } else parts.push(h('p', { class: 'muted' }, vault.forms.length ? 'Nothing from My info was needed for this call.' : 'My info is empty, so nothing was swapped for a placeholder.'));
  if (flags.length) {
    parts.push(h('div', { class: 'keptsec' }),
      h('div', { class: 'warnbox' }, h('h4', {}, 'These looked personal and were sent'),
        h('p', { class: 'foot' }, 'Selfbrowse only hides values from My info. Anything else on a page goes to the model as it appears.'),
        h('table', {}, h('tbody', {}, flags.map((f) => h('tr', {}, h('td', {}, h('span', { class: 'flag' }, f.match)), h('td', { class: 'muted' }, f.kind === 'value' ? `${KIND.value}: ${describeSecret(f.name) || f.name}` : KIND[f.kind])))))));
  }
  return parts;
}

function renderUsage() {
  const done = calls().filter((c) => c.usage);
  const sum = (k) => done.reduce((a, c) => a + c.usage[k], 0);
  const inAll = sum('input') + sum('cache_read') + sum('cache_write'), out = sum('output');
  $('uIn').textContent = fmt(inAll);
  $('uOut').textContent = fmt(out);
  const cost = estimate(inAll, out);
  $('uCost').textContent = cost == null ? '–' : money(cost);
  const fresh = sum('input') + sum('cache_write'), cached = sum('cache_read');
  const seg = (cls, n) => { const i = h('i', { class: cls }); i.style.width = `${inAll ? (n / inAll) * 100 : 0}%`; return i; };
  $('uStack').replaceChildren(seg('new', fresh), seg('cache', cached));
  $('uLegend').replaceChildren(h('span', {}, h('span', { class: 'chip ink' }, fmt(fresh)), ' new'),
    h('span', {}, h('span', { class: 'chip sent' }, fmt(cached)), ' reused from the provider’s cache'));
  const max = Math.max(1, ...done.map((c) => c.usage.input + c.usage.cache_read + c.usage.cache_write));
  $('callRows').replaceChildren(...done.map((c) => {
    const tot = c.usage.input + c.usage.cache_read + c.usage.cache_write;
    const stack = h('div', { class: 'stack' }, h('i', { class: 'new' }), h('i', { class: 'cache' }));
    stack.children[0].style.width = `${((c.usage.input + c.usage.cache_write) / max) * 100}%`;
    stack.children[1].style.width = `${(c.usage.cache_read / max) * 100}%`;
    return h('div', { class: 'callrow' }, h('span', { class: 'muted' }, `Call ${c.idx}`), stack, h('span', { class: 'right' }, fmt(tot)));
  }));
}

function renderInspector() {
  const it = R.items[R.selected];
  const c = it && it.call;
  const tag = $('callTag');
  tag.className = 'tag';
  $('keptCount').textContent = c ? callRefs(c).length : 0;
  if (!it) {
    tag.textContent = 'Outbound';
    $('callMeta').textContent = '';
    $('callSub').textContent = 'Nothing has been sent yet.';
    $('payload').replaceChildren(h('p', { class: 'muted' }, 'When a run starts, each message to the model appears here exactly as it was sent.'));
    $('keptBody').replaceChildren();
    return;
  }
  if (!c) {
    tag.textContent = `Step ${R.selected + 1}`;
    $('callMeta').textContent = '0 tokens';
    $('callSub').textContent = 'Replayed from a saved flow. No model was called, so nothing was sent.';
    $('payload').replaceChildren(h('p', { class: 'muted' }, 'This step ran from the recorded flow.'));
    $('keptBody').replaceChildren();
    return;
  }
  tag.textContent = `${c.holding ? 'Held' : 'Outbound'} · call ${c.idx}`;
  if (c.holding) tag.classList.add('holding');
  $('callMeta').textContent = c.usage ? `${fmt(c.usage.input + c.usage.cache_read + c.usage.cache_write)} in · ${fmt(c.usage.output)} out · ${(c.ms / 1000).toFixed(1)} s` : '';
  const kept = callRefs(c).length, flags = callFlags(c).length;
  $('callSub').textContent = c.holding ? 'Not sent. Approve it or stop the run.'
    : `${kept ? `${kept} value${kept > 1 ? 's' : ''} did not leave this computer. ` : ''}${flags ? `${flags} item${flags > 1 ? 's' : ''} that look personal ${flags > 1 ? 'were' : 'was'} sent.` : kept ? '' : 'Nothing private was on this page.'}`.trim();
  $('payload').replaceChildren(...renderPayload(c));
  $('keptBody').replaceChildren(...renderKept(c));
}

function renderLedger() {
  const cs = calls(), done = cs.filter((c) => c.usage);
  const inAll = done.reduce((a, c) => a + c.usage.input + c.usage.cache_read + c.usage.cache_write, 0);
  const out = done.reduce((a, c) => a + c.usage.output, 0);
  const noModel = R.flowName && cs.length === 0 && !R.flowModel;
  $('lCalls').textContent = noModel ? 'No model used' : `${cs.length} call${cs.length === 1 ? '' : 's'}`;
  $('lProvider').textContent = noModel ? '' : `to ${sourceLabel(models.selected.source)}`;
  $('lIn').textContent = fmt(inAll);
  $('lOut').textContent = fmt(out);
  const cost = estimate(inAll, out);
  $('lCost').textContent = cost == null || !done.length ? '' : `≈ ${money(cost)}`;
  const kept = new Set(cs.flatMap(callRefs)).size;
  $('lKept').textContent = `${kept} value${kept === 1 ? '' : 's'}`;
  const flagged = new Set(cs.filter((c) => !c.holding).flatMap((c) => callFlags(c).map((f) => f.match))).size;     // a held call has not been sent
  $('lFlagWrap').hidden = flagged === 0;
  $('lFlags').textContent = `${flagged} item${flagged === 1 ? '' : 's'}`;
}

function syncMaskButton() {
  const n = R.replace ? R.replace.size : 0;
  $('maskCall').textContent = n ? `Send with ${n} replaced` : 'Nothing ticked to replace';
  $('maskCall').disabled = n === 0;
}
function renderBanner() {
  const it = R.items[R.items.length - 1];
  const c = it && it.call;
  const show = !!(R.running && c && c.holding);
  $('banner').hidden = !show;
  if (!show) return;
  const flags = c.reason || [];
  const flagged = c.mode === 'flagged';
  $('bannerTitle').textContent = flagged ? 'Something in this request looks personal.' : 'Waiting for your OK.';
  $('bannerText').textContent = flagged
    ? 'It is shown on the right with the parts highlighted. Nothing has left this computer yet.'
    : 'The next model call is shown on the right. Nothing has left this computer yet.';
  // each flagged item is a choice: ticked ones are replaced, the others go as they are (a form label such as "Suff."
  // can be taken for a name, so you decide)
  R.replace = new Set(flags.map((f) => f.match));
  $('bannerFlags').replaceChildren(...flags.slice(0, 12).map((f) => {
    const short = f.match.length > 40 ? `${f.match.slice(0, 39)}\u2026` : f.match;
    const b = h('button', { class: 'flagchip', type: 'button', 'aria-pressed': 'true', title: `${f.name}. Click to replace it or leave it.` }, h('i', { 'aria-hidden': 'true' }, '\u2713'), short);
    b.addEventListener('click', () => {
      const on = b.getAttribute('aria-pressed') !== 'true';
      b.setAttribute('aria-pressed', String(on));
      b.firstChild.textContent = on ? '\u2713' : '';
      if (on) R.replace.add(f.match); else R.replace.delete(f.match);
      syncMaskButton();
    });
    return b;
  }), ...(flags.length > 12 ? [h('span', { class: 'muted' }, ` and ${flags.length - 12} more`)] : []));
  $('maskCall').hidden = flags.length === 0;
  syncMaskButton();
  $('sendCall').textContent = flagged ? 'Send as is' : 'Send this call';
}
function render() { renderTimeline(); renderInspector(); renderUsage(); renderLedger(); renderBanner(); renderHead(); }

// ---- tabs ----
for (const t of document.querySelectorAll('.tabs button')) {
  t.addEventListener('click', () => {
    for (const x of document.querySelectorAll('.tabs button')) x.setAttribute('aria-selected', String(x === t));
    for (const p of document.querySelectorAll('.tabpane')) p.classList.toggle('on', p.id === `tab-${t.dataset.tab}`);
  });
}
$('reveal').addEventListener('change', (e) => $('payload').classList.toggle('reveal', e.target.checked));
$('priceIn').addEventListener('input', savePrices);
$('priceOut').addEventListener('input', savePrices);
{ const p = loadPrices(); $('priceIn').value = p.in || ''; $('priceOut').value = p.out || ''; }

// ---- status area ----
function setStatus(title, text, { error = false, answer = '' } = {}) {
  $('status').classList.toggle('error', error);
  $('statusTitle').textContent = title;
  $('statusText').textContent = text;
  $('answerText').textContent = answer;
  $('answerText').hidden = !answer;
}
const setState = (st) => { $('run').dataset.state = st; };
function setRunning(on) {
  R.running = on;
  if (on) setState('running');
  $('follow').disabled = on;
  $('follow').placeholder = on ? 'Working… you can follow up when it finishes' : 'Follow up on this run…';
  $('followForm').classList.toggle('busy', on);
  $('control').disabled = !on;
  if (!on) setControl(false, false);
  renderBanner();
  renderHead();
}

// The bar above a run: what it is, and whether it is working, waiting for you, or finished.
function renderHead() {
  $('runTitle').textContent = R.title || 'Run';
  $('runTitle').title = R.title || '';
  const e = R.doneEvent;
  let cls = 'run', text = 'Running';
  if (e) {
    if (e.error === 'Stopped by you.') [cls, text] = ['', 'Stopped'];
    else if (e.success) [cls, text] = ['ok', `Done · ${R.durationText || `${e.steps} steps`}`];
    else if (e.error && !e.output) [cls, text] = ['bad', 'Could not finish'];
    else [cls, text] = ['wait', 'Not confirmed'];
  } else {
    const held = R.items.some((i) => i.call && i.call.holding);
    if (held) [cls, text] = ['wait', 'Waiting for your OK'];
    else if (R.control) [cls, text] = ['wait', 'You are driving'];
    else if (!$('handoff').hidden) [cls, text] = ['wait', 'Paused · waiting for you'];
  }
  const pill = $('runPill');
  pill.className = `statuspill ${cls}`;
  pill.textContent = text;
  $('runModel').textContent = R.flowName && !R.flowModel ? 'No model' : `${sourceLabel(models.selected.source)} · ${models.selected.model}`;
}

// ---- live view: frames in, clicks and keys out ----
function setControl(on, tell = true) {
  R.control = on;
  $('control').textContent = on ? 'Hand back to the agent' : 'Take control';
  $('frame').classList.toggle('driving', on);
  $('liveChip').textContent = on ? 'You are in control' : 'Live';
  $('liveChip').className = on ? 'chip sent' : 'chip local';
  if (on) $('frame').focus();
  if (tell && R.id) post(`/runs/${R.id}/control`, { on }).catch(() => {});
}
let pending = [];
let flushTimer = null;
function send(ev) {
  if (!R.control || !R.id) return;
  pending.push(ev);
  if (!flushTimer) flushTimer = setTimeout(flush, 25);
}
async function flush() {
  flushTimer = null;
  const batch = pending.splice(0, 50);               // the backend accepts at most 50 events per call
  if (pending.length) flushTimer = setTimeout(flush, 25);
  if (batch.length) { try { await post(`/runs/${R.id}/input`, batch); } catch (_) { /* the run ended */ } }
}
function point(e) {
  const r = $('frame').getBoundingClientRect();
  return { x: Math.max(0, ((e.clientX - r.left) / r.width) * R.frameSize.w), y: Math.max(0, ((e.clientY - r.top) / r.height) * R.frameSize.h) };
}
const BUTTONS = ['left', 'middle', 'right'];
const frameEl = $('frame');
frameEl.addEventListener('pointerdown', (e) => { if (!R.control) return; e.preventDefault(); frameEl.focus(); send({ t: 'down', ...point(e), button: BUTTONS[e.button] || 'left' }); });
frameEl.addEventListener('pointerup', (e) => { if (R.control) send({ t: 'up', ...point(e), button: BUTTONS[e.button] || 'left' }); });
let lastMove = 0;
frameEl.addEventListener('pointermove', (e) => { const n = Date.now(); if (R.control && n - lastMove > 40) { lastMove = n; send({ t: 'move', ...point(e) }); } });
frameEl.addEventListener('contextmenu', (e) => e.preventDefault());
frameEl.addEventListener('wheel', (e) => { if (!R.control) return; e.preventDefault(); send({ t: 'wheel', ...point(e), dx: Math.max(-5000, Math.min(5000, e.deltaX)), dy: Math.max(-5000, Math.min(5000, e.deltaY)) }); }, { passive: false });
frameEl.addEventListener('keydown', (e) => {
  if (!R.control) return;
  e.preventDefault();
  const mod = e.ctrlKey || e.metaKey || e.altKey;
  if (e.key.length === 1 && !mod) return send({ t: 'text', text: e.key });
  const parts = [];
  if (e.ctrlKey) parts.push('Control');
  if (e.metaKey) parts.push('Meta');
  if (e.altKey) parts.push('Alt');
  if (e.shiftKey && e.key.length > 1) parts.push('Shift');
  parts.push(e.key === ' ' ? 'Space' : e.key);
  send({ t: 'key', key: parts.join('+') });
});
$('control').addEventListener('click', () => setControl(!R.control));
function answerHandoff(resume) {
  $('handoff').hidden = true;
  setControl(false, false);
  post(`/runs/${R.id}/handoff`, { resume }).catch(() => {});
}
$('handoffGo').addEventListener('click', () => answerHandoff(true));
$('handoffNo').addEventListener('click', () => answerHandoff(false));

// ---- approval of a held call ----
$('sendCall').addEventListener('click', () => { $('banner').hidden = true; post(`/runs/${R.id}/call`, { send: true }).catch((e) => toast(e.message)); });
$('maskCall').addEventListener('click', () => { $('banner').hidden = true; post(`/runs/${R.id}/call`, { send: true, mask: true, replace: [...(R.replace || [])] }).catch((e) => toast(e.message)); });
$('refuseCall').addEventListener('click', () => { $('banner').hidden = true; post(`/runs/${R.id}/call`, { send: false }).catch((e) => toast(e.message)); });

// ---- events from the run ----
function onEvent(e) {
  if (e.type === 'call') {
    Object.assign(R.table, e.new);
    R.items.push({ call: { idx: e.idx, ids: e.ids, holding: e.holding, mode: e.mode, reason: e.reason || [], masked: 0, usage: null, reply: null, ms: 0, tools: e.tools }, step: null });
    if (R.follow) R.selected = R.items.length - 1;
  } else if (e.type === 'turn') {
    R.turnMarks = R.turnMarks || {};
    R.turnMarks[R.items.length] = e.prompt;
  } else if (e.type === 'call_masked') {
    Object.assign(R.table, e.new);
    const c = calls().find((x) => x.idx === e.idx);
    if (c) { c.ids = e.ids; c.masked = e.count; }
  } else if (e.type === 'call_sent') {
    const c = calls().find((x) => x.idx === e.idx);
    if (c) c.holding = false;
  } else if (e.type === 'call_done') {
    const c = calls().find((x) => x.idx === e.idx);
    if (c) Object.assign(c, { usage: e.usage, reply: e.reply, ms: e.ms });
  } else if (e.type === 'step') {
    const open = [...R.items].reverse().find((i) => i.call && !i.step);
    if (open) open.step = e;
    else { R.items.push({ call: null, step: e }); if (R.follow) R.selected = R.items.length - 1; }
    $('liveUrl').textContent = e.url || (e.tool.startsWith('goto ') ? e.tool.slice(5) : $('liveUrl').textContent.startsWith('Starting') ? 'Browser' : $('liveUrl').textContent);
    setStatus(R.flowName ? `Replaying “${R.flowName}”` : 'Working…', e.total ? `Step ${e.number} of ${e.total}.` : `Step ${e.number}: ${stepTitle(e)}`);
  } else if (e.type === 'handoff') {
    $('handoffReason').textContent = e.reason;
    $('handoff').hidden = false;
    setControl(true, false);                         // the backend already gave you the browser
  } else if (e.type === 'control') {
    if (!e.on) $('handoff').hidden = true;
    setControl(e.on, false);
  } else if (e.type === 'paused') {
    if (e.paused) setStatus('Paused for you', 'Press “Hand back to the agent” to continue. No tokens are used while you drive.');
  } else if (e.type === 'done') {
    finish(e);
  }
  render();
}

function finish(e) {
  R.doneEvent = e;
  R.rawAnswer = e.output || '';                       // as the model wrote it: this is what a follow-up may send
  setRunning(false);
  $('liveChip').textContent = 'Finished';
  $('liveChip').className = 'chip plain';
  $('handoff').hidden = true;
  R.canSaveFlow = !!e.can_save_flow;
  const secs = (Date.now() - (R.startedAt || Date.now())) / 1000;
  R.durationText = secs < 90 ? `${Math.round(secs)} s` : `${Math.round(secs / 60)} min`;
  setState('done');
  $('afterRun').hidden = false;
  $('saveFlow').hidden = !R.canSaveFlow;
  $('copyAnswer').hidden = !e.output;
  $('runAgain').hidden = false;
  $('followForm').hidden = !!R.flowName;
  const stat = (v, l) => h('div', {}, h('span', {}, l), h('b', {}, v));
  $('resultStats').replaceChildren(stat(String(e.steps || 0), 'Steps'), stat(R.durationText, 'Time'),
    stat(fmt(e.tokens || 0), 'Tokens'), stat(R.flowName && !e.model_calls ? 'None' : String(e.model_calls != null ? e.model_calls : calls().length), 'Model calls'));
  $('resultStats').hidden = false;
  const used = e.model_calls ? `${fmt(e.tokens)} tokens in ${e.model_calls} model call${e.model_calls === 1 ? '' : 's'}` : R.flowName ? 'no model used' : `${fmt(e.tokens)} tokens`;
  const extra = [e.repaired ? `A model finished the task after step ${e.repaired_at} failed.` : '', e.summarized ? 'The model wrote the summary.' : '', e.warning || ''].filter(Boolean).join(' ');
  if (e.error && !e.output) setStatus(e.error === 'Stopped by you.' ? 'Stopped' : 'The run could not finish', e.error, { error: e.error !== 'Stopped by you.' });
  else setStatus(e.success ? 'Done' : 'Finished without a confirmed answer', `${e.steps} steps, ${used}.${extra ? ` ${extra}` : ''}`, { answer: restoreSecrets(e.output) });
}

async function beginRun(id, flowName, flowModel, title) {
  Object.assign(R, { id, items: [], table: {}, selected: -1, follow: true, flowName: flowName || null, flowModel: !!flowModel, doneEvent: null, canSaveFlow: false,
    title: flowName ? `Flow: ${flowName}` : String(title || '').split('\n')[0].slice(0, 160), task: title || '', startedAt: Date.now(), durationText: '', eventCount: 0, turnMarks: {} });
  $('reviewHead').value = $('review').value;
  $('followForm').hidden = !!flowName; $('resultStats').hidden = true; $('live').classList.remove('shown'); $('showBrowser').textContent = 'Show browser';
  if (R.stream) R.stream.abort();
  if (R.frames) R.frames.abort();
  $('afterRun').hidden = true;
  $('handoff').hidden = true;
  $('live').hidden = false;
  $('frame').removeAttribute('src');
  $('liveUrl').textContent = 'Starting the browser…';
  setStatus(flowName ? `Replaying “${flowName}”` : 'Starting…', flowName ? (flowModel ? 'Replaying without a model. One is used only for the summary, or if a step fails.' : 'No model is used, so this costs no tokens.') : 'Opening a browser and sending the first request.');
  setRunning(true);
  go('run');
  render();
  openStreams(id, 0);
}

// Read the live view and the events of a run. A follow-up reads on from where the last stream ended.
function openStreams(id, after) {
  if (R.stream) R.stream.abort();
  if (R.frames) R.frames.abort();
  R.stream = new AbortController();
  R.frames = new AbortController();
  readSSE(`/runs/${id}/frames`, (batch) => {
    const last = batch[batch.length - 1];             // only the newest frame matters; skip any we fell behind on
    R.frameSize = { w: last.w, h: last.h };
    $('frame').src = `data:image/jpeg;base64,${last.jpeg}`;
  }, R.frames.signal).catch(() => {});
  readSSE(`/runs/${id}/events?after=${after}`, (batch) => {
    for (const e of batch) { R.eventCount += 1; onEvent(e); if (e.type === 'done') return 'stop'; }
  }, R.stream.signal).then(() => { if (R.running) { finish({ error: 'The backend closed the connection before the run finished.', steps: 0, tokens: 0 }); render(); } })
    .catch(() => { if (R.running) { finish({ error: 'Lost connection to the backend.', steps: 0, tokens: 0 }); render(); } });
}

// A follow-up carries on in the same run and browser. If that browser has gone, it starts a new run with the context instead.
async function continueRun(text) {
  if (R.running || !R.id) return;
  try {
    await post(`/runs/${R.id}/followup`, { prompt: text });
  } catch (err) {
    toast('That browser was closed, so this started a new run with the earlier result as context.');
    startRun(`${R.task}\n\nWhat you found last time:\n${String(R.rawAnswer || '').slice(0, 3000) || '(nothing recorded)'}\n\nNow: ${text}`, text);
    return;
  }
  Object.assign(R, { doneEvent: null, canSaveFlow: false, startedAt: Date.now(), durationText: '' });
  $('resultStats').hidden = true; $('afterRun').hidden = true; $('handoff').hidden = true;
  $('live').hidden = false; $('live').classList.remove('shown'); $('showBrowser').textContent = 'Show browser';
  setStatus('Working…', 'Following up in the same browser.');
  setRunning(true);
  render();
  openStreams(R.id, R.eventCount);
}

// ---- browser options: profile, installed Chrome, stealth ----
const BOPT = { profile: 'optProfile', chrome: 'optChrome', stealth: 'optStealth' };
function browserOptions() { return { profile: $('optProfile').checked, chrome: $('optChrome').checked && !$('optChrome').disabled, stealth: $('optStealth').checked }; }
{
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('sb.browser') || '{}'); } catch (_) { /* fine */ }
  for (const [k, id] of Object.entries(BOPT)) if (k in saved) $(id).checked = !!saved[k];
  for (const id of Object.values(BOPT)) $(id).addEventListener('change', () => { try { localStorage.setItem('sb.browser', JSON.stringify(browserOptions())); } catch (_) { /* fine */ } });
}
async function refreshBrowserInfo() {
  try {
    const i = await call('GET', '/browser-info');
    $('optChrome').disabled = !i.chrome;
    $('chromeNote').textContent = i.chrome ? 'A real Chrome looks less like automation than the bundled browser.' : 'Chrome was not found on this computer, so the bundled browser is used.';
    $('stealthNote').textContent = i.stealth ? 'Hides common automation tells (Patchright).' : 'Needs one more package. If you turn it on, the next run tells you the install command.';
    $('profileSize').textContent = i.profile_bytes ? `${(i.profile_bytes / 1048576).toFixed(1)} MB saved` : 'Nothing saved yet';
  } catch (_) { /* the backend is not ready yet */ }
}
$('browserOpts').addEventListener('toggle', () => { if ($('browserOpts').open) refreshBrowserInfo(); });
document.addEventListener('click', (e) => {
  if (!e.target.closest('#browserOpts')) $('browserOpts').open = false;
  if (!e.target.closest('#moreOpts')) $('moreOpts').open = false;
});
{
  const btn = $('clearData');
  const text = btn.textContent;
  let armed = null;
  btn.addEventListener('click', async () => {
    if (!armed) { btn.textContent = 'Click again: signs you out of every site'; armed = setTimeout(() => { armed = null; btn.textContent = text; }, 4000); return; }
    clearTimeout(armed); armed = null; btn.textContent = text;
    try { await post('/browser-data/clear'); toast('Browser data cleared.'); refreshBrowserInfo(); } catch (err) { toast(err.message); }
  });
}

// ---- starting, stopping, saving ----
async function startRun(prompt, title) {
  const useInfo = $('useInfo').checked && !$('useInfo').disabled;
  setRunning(true);
  try {
    const { id } = await post('/runs', {
      prompt: prompt + (useInfo ? sharedNote() : ''), ...modelRequest(), review_mode: $('review').value,
      sensitive: useInfo ? localValues() : {}, labels: useInfo ? savedLabels() : {}, presidio: $('presidio').checked, history: keepHistory(), ...browserOptions(),
    });
    beginRun(id, null, false, title || prompt);
  } catch (err) {
    setRunning(false);
    setState('idle');
    toast(err.message);
  }
}
$('form').addEventListener('submit', (ev) => {
  ev.preventDefault();
  const prompt = $('prompt').value.trim();
  if (!prompt) { toast('Describe what the browser should do first.'); $('prompt').focus(); return; }
  startRun(prompt);
});
$('prompt').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !R.running) $('form').requestSubmit(); });
$('stopBtn').addEventListener('click', () => stopRun());
function stopRun() {
  setStatus('Stopping…', 'Stopping now.');
  post(`/runs/${R.id}/stop`).catch(() => {});
}
$('saveFlow').addEventListener('click', async () => {
  let draft;
  try { draft = await call('GET', `/runs/${R.id}/flow`); } catch (err) { toast(err.message); return; }
  openFlowEditor({
    runId: R.id, flow: draft.flow, lines: draft.lines, name: $('prompt').value.trim().slice(0, 60), description: draft.flow.description,
    onSave: async (body) => {
      await post(`/runs/${R.id}/save-flow`, body);
      R.canSaveFlow = false; $('saveFlow').hidden = true; closeSheet(); toast('Saved. Find it under Flows.');
    },
  });
});

// "Use My info" needs something saved
function refreshUseInfo() {
  const any = Object.keys(localValues()).length > 0 || sharedNote() !== '';
  $('useInfo').disabled = !any;
  $('useInfoLabel').classList.toggle('off', !any);
  $('useInfoLabel').title = any ? '' : 'Nothing is saved in My info yet.';
}

// Presidio is optional: the Install button downloads it into the backend's Python, then the checkbox works.
let presidioTimer = null;
function showPresidio(i) {
  const ready = i.state === 'done', busy = i.state === 'running';
  $('presidio').disabled = !ready;
  if (!ready) $('presidio').checked = false;
  $('presidioInstall').hidden = ready || busy;
  $('presidioInstall').textContent = i.state === 'error' ? 'Try again' : 'Install';
  $('presidioNote').textContent = ready ? '' : busy ? 'Installing, about 1 minute. It downloads from PyPI and spaCy.'
    : i.state === 'error' ? `Install failed: ${i.error}` : 'Not installed. Downloads about 30 MB once.';
}
async function pollPresidio() {
  try {
    const i = await call('GET', '/presidio/install');
    showPresidio(i);
    if (i.state === 'running') presidioTimer = setTimeout(pollPresidio, 2000);
  } catch (_) { /* backend not ready */ }
}
$('presidioInstall').addEventListener('click', async () => {
  try { showPresidio(await post('/presidio/install')); clearTimeout(presidioTimer); pollPresidio(); } catch (err) { toast(err.message); }
});

// ---- after a run: run again, a new run, copy, follow up ----
function copyText(text) {
  const t = h('textarea', { 'aria-hidden': 'true', class: 'sr' });
  t.value = text;
  document.body.append(t);
  t.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (_) { /* fall through */ }
  t.remove();
  return ok;
}
function newRun() {
  if (R.running) return;
  if (R.id && !R.flowName) post(`/runs/${R.id}/close`).catch(() => {});      // let go of the browser kept for follow-ups
  if (R.stream) R.stream.abort();
  if (R.frames) R.frames.abort();
  R.doneEvent = null;
  setState('idle');
  $('prompt').value = '';
  go('run');
  $('prompt').focus();
  refreshSuggestions();
}
$('newRun').addEventListener('click', newRun);
$('runAgain').addEventListener('click', () => {
  if (R.running) return;
  if (R.flowName && R.lastFlow) { runFlow(R.lastFlow); return; }
  if (!R.task) return;
  startRun(R.task);
});
$('copyAnswer').addEventListener('click', () => toast(copyText($('answerText').textContent) ? 'Copied.' : 'Could not copy.'));
$('showBrowser').addEventListener('click', () => {
  const on = $('live').classList.toggle('shown');
  $('showBrowser').textContent = on ? 'Hide browser' : 'Show browser';
});
$('followForm').addEventListener('submit', (ev) => {
  ev.preventDefault();
  const text = $('follow').value.trim();
  if (!text || R.running) return;
  $('follow').value = '';
  continueRun(text);
});
// the Run icon, or Cmd+N, starts a fresh run once one has finished
document.querySelector('.rail').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-go=run]');
  if (b && $('run').classList.contains('on') && !R.running && $('run').dataset.state === 'done') newRun();
}, true);
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'n') { e.preventDefault(); newRun(); }
});
// approve each call: the same setting on the idle screen and in the run bar
try { const saved = localStorage.getItem('sb.reviewmode'); if (['off', 'flagged', 'always'].includes(saved)) { $('review').value = saved; $('reviewHead').value = saved; } } catch (_) { /* default off */ }
function setReviewMode(mode) {
  $('review').value = mode;
  $('reviewHead').value = mode;
  try { localStorage.setItem('sb.reviewmode', mode); } catch (_) { /* fine */ }
  if (R.running) post(`/runs/${R.id}/review`, { mode }).catch(() => {});
}
$('review').addEventListener('change', (e) => setReviewMode(e.target.value));
$('reviewHead').addEventListener('change', (e) => setReviewMode(e.target.value));

// ---- what to try: your recent runs and flows, or examples ----
const EXAMPLES = [
  { title: 'Compare flight prices', sub: 'Cheapest nonstop Chicago → Kochi next month', prompt: 'Find the cheapest nonstop flight from Chicago to Kochi next month' },
  { title: 'Look up a price', sub: 'Find what a product costs on a store’s site', prompt: 'Find the price of ' },
  { title: 'Summarize a page', sub: 'Read a page and give me the key points', prompt: 'Open this page and summarize the key points: ' },
];
async function refreshSuggestions() {
  let runs = [], flows = [];
  try { [runs, flows] = await Promise.all([call('GET', '/history'), call('GET', '/flows')]); } catch (_) { /* the backend is not ready yet */ }
  const cards = [];
  const seen = new Set();
  for (const r of runs) {
    if (cards.length >= 2) break;
    if (r.kind !== 'run' || !r.prompt || seen.has(r.prompt)) continue;
    seen.add(r.prompt);
    cards.push({ title: r.prompt.length > 48 ? `${r.prompt.slice(0, 47)}…` : r.prompt, sub: `Run again · ${r.success ? 'finished' : r.stopped ? 'stopped' : 'not finished'}`, act: () => { $('prompt').value = r.prompt; $('prompt').focus(); } });
  }
  for (const f of flows.slice(0, 2)) cards.push({ title: f.name, sub: 'Run a saved flow · no model needed', act: () => runFlow(f) });
  for (const ex of EXAMPLES) { if (cards.length >= 4) break; cards.push({ title: ex.title, sub: ex.sub, act: () => { $('prompt').value = ex.prompt; $('prompt').focus(); } }); }
  $('suggestions').replaceChildren(...cards.slice(0, 4).map((c) => h('button', { class: 'suggest', type: 'button', onclick: c.act }, h('b', {}, c.title), h('span', {}, c.sub))));
}

function onBoot() { refreshSuggestions(); loadModels(); pollPresidio(); refreshUseInfo(); render(); if (typeof renderVault === 'function') renderVault(); }
boot();

// ---- show My info values in the answer: your choice, remembered ----
try { $('showSecrets').checked = localStorage.getItem('sb.showsecrets') !== 'off'; } catch (_) { /* default on */ }
$('showSecrets').addEventListener('change', (e) => {
  try { localStorage.setItem('sb.showsecrets', e.target.checked ? 'on' : 'off'); } catch (_) { /* fine */ }
  if (R.doneEvent && R.rawAnswer) { $('answerText').textContent = restoreSecrets(R.rawAnswer); }
  if (typeof showHistory === 'function' && H && H.selected && $('history').classList.contains('on')) showHistory(H.selected);
});
