// Shared helpers. Everything the page shows is built with textContent / DOM nodes, never innerHTML:
// page text and model replies are untrusted.
const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
  return el;
}

const fmt = (n) => Number(n || 0).toLocaleString();
function toast(text) {
  const t = $('toast');
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 3500);
}

// ---- the backend ----
let api = null;
const auth = () => ({ Authorization: `Bearer ${api.token}` });
async function call(method, path, body) {
  const res = await fetch(`${api.baseUrl}${path}`, {
    method, headers: { ...auth(), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (_) { /* no body */ }
  if (!res.ok) {
    const d = data && data.detail;
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? 'That value is not allowed.' : `HTTP ${res.status}`);
  }
  return data;
}
const post = (p, b) => call('POST', p, b === undefined ? {} : b);

// Server-sent events over fetch, so the token goes in a header and never in a URL.
async function readSSE(path, onEvent, signal) {
  const res = await fetch(`${api.baseUrl}${path}`, { headers: auth(), signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    const batch = [];
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const line = buf.slice(0, i);
      buf = buf.slice(i + 2);
      if (line.startsWith('data: ')) batch.push(JSON.parse(line.slice(6)));
    }
    if (batch.length && onEvent(batch) === 'stop') return;
  }
}

// ---- My info (kept encrypted by the operating system; see main.js) ----
let vault = { forms: [] };
let vaultReady = false;

const secretWord = (s) => String(s).toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 30) || 'FIELD';

// Every field gets a stable secret name like SHIPPING_CITY. Names are made once and kept, so a saved flow
// that mentions <secret:SHIPPING_CITY> keeps working when the person renames the label.
function ensureNames() {
  const taken = new Set(vault.forms.flatMap((f) => f.fields.map((x) => x.secret).filter(Boolean)));
  for (const form of vault.forms) {
    for (const f of form.fields) {
      if (f.secret || !String(f.label || '').trim()) continue;
      const base = `${secretWord(form.name)}_${secretWord(f.label)}`.slice(0, 60);
      let name = base;
      for (let n = 2; taken.has(name); n++) name = `${base}_${n}`;
      f.secret = name;
      taken.add(name);
    }
  }
}

// The values a run may type for the model without the model ever seeing them.
function localValues() {
  const out = {};
  for (const form of vault.forms) for (const f of form.fields) if (f.policy === 'local' && f.value && f.secret) out[f.secret] = f.value;
  return out;
}
// Fields the person allowed the model to see: they go into the task text.
function sharedNote() {
  const rows = [];
  for (const form of vault.forms) for (const f of form.fields) if (f.policy === 'model' && f.kind !== 'secret' && f.value) rows.push(`${f.label}: ${f.value}`);
  return rows.length ? `\n\nMy details you may use:\n${rows.join('\n')}` : '';
}
// What each placeholder is, for the run to hand the model only when it asks (labels, never values).
function savedLabels() {
  const out = {};
  for (const form of vault.forms) for (const f of form.fields) if (f.policy === 'local' && f.value && f.secret) out[f.secret] = `${form.name} › ${f.label}`;
  return out;
}
function allValues() {                                  // for scanning shared files: every saved value, whatever its setting
  const out = {};
  for (const form of vault.forms) for (const f of form.fields) if (f.value && f.secret) out[f.secret] = f.value;
  return out;
}
const isPasswordName = (name) => vault.forms.some((form) => form.fields.some((f) => f.secret === name && f.kind === 'secret'));
function describeSecret(name) {                         // "Shipping address › City"
  for (const form of vault.forms) for (const f of form.fields) if (f.secret === name) return `${form.name} › ${f.label}`;
  return null;
}
const secretOwner = (name) => { for (const form of vault.forms) if (form.fields.some((f) => f.secret === name)) return form.name; return null; };

// ---- navigation ----
function go(id) {
  if (typeof hideAllSecrets === 'function') hideAllSecrets();         // leaving My info covers any shown password
  for (const s of document.querySelectorAll('.screen')) s.classList.toggle('on', s.id === id);
  for (const b of document.querySelectorAll('.rail button[data-go]')) {
    if (b.dataset.go === id) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  }
  if (id === 'flows' && typeof loadFlows === 'function') loadFlows();
  if (id === 'run' && typeof refreshSuggestions === 'function') refreshSuggestions();
  if (id === 'history' && typeof loadHistory === 'function') loadHistory();
  if (id === 'vault' && typeof renderVault === 'function') renderVault();
}
document.querySelector('.rail').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-go]');
  if (b) go(b.dataset.go);
});

// ---- dialogs (a side sheet) ----
let sheetOpener = null;
function openSheet(...content) {
  sheetOpener = document.activeElement;
  $('sheet').replaceChildren(...content.filter((c) => c != null && c !== false));
  $('sheetwrap').hidden = false;
  const first = $('sheet').querySelector('input,button');
  if (first) first.focus();
}
function closeSheet() {
  $('sheetwrap').hidden = true;
  $('sheet').classList.remove('wide');
  $('sheet').replaceChildren();
  if (sheetOpener && sheetOpener.focus) sheetOpener.focus();
}
$('sheetwrap').addEventListener('click', (e) => { if (e.target.id === 'sheetwrap') closeSheet(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('sheetwrap').hidden) closeSheet(); });

// Luhn check: used to keep card numbers out of My info and out of shared files.
function looksLikeCard(text) {
  const digits = String(text).replace(/[\s-]/g, '');
  if (!/^\d{13,19}$/.test(digits)) return false;
  let sum = 0, flip = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = +digits[i];
    if (flip) { d *= 2; if (d > 9) d -= 9; }
    sum += d; flip = !flip;
  }
  return sum % 10 === 0;
}

async function boot() {
  api = await window.selfbrowse.backend();
  try {
    vault = await window.selfbrowse.loadMyInfo();
    if (!vault || !Array.isArray(vault.forms)) vault = { forms: [] };
    ensureNames();
    vaultReady = true;
  } catch (err) {
    vault = { forms: [] };
    toast(`My info could not be opened: ${err.message}`);
  }
  if (typeof onBoot === 'function') onBoot();
}

// A destructive button asks twice: the first click arms it for a few seconds.
function confirmClick(btn, armedText, action) {
  const text = btn.textContent;
  let armed = null;
  btn.addEventListener('click', () => {
    if (armed) { clearTimeout(armed); armed = null; btn.textContent = text; action(); return; }
    btn.textContent = armedText;
    armed = setTimeout(() => { armed = null; btn.textContent = text; }, 3500);
  });
}
