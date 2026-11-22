// Which model the agent uses. A source is a built-in provider, or a custom server that speaks the OpenAI chat API.
// Keys are kept encrypted by the operating system (see main.js) and only go to the local backend with a run.
const PROVIDERS = [
  { id: 'anthropic', name: 'Anthropic', env: 'ANTHROPIC_API_KEY', models: ['claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5'] },
  { id: 'openai', name: 'OpenAI', env: 'OPENAI_API_KEY', models: ['gpt-4o-mini', 'gpt-4o'] },
  { id: 'gemini', name: 'Google Gemini', env: 'GEMINI_API_KEY', models: ['gemini-2.5-flash', 'gemini-2.5-pro'] },
  { id: 'deepseek', name: 'DeepSeek', env: 'DEEPSEEK_API_KEY', models: ['deepseek-chat'] },
  { id: 'groq', name: 'Groq', env: 'GROQ_API_KEY', models: ['llama-3.3-70b-versatile'] },
  { id: 'together', name: 'Together', env: 'TOGETHER_API_KEY', models: [] },
  { id: 'openrouter', name: 'OpenRouter', env: 'OPENROUTER_API_KEY', models: [] },
  { id: 'ollama', name: 'Ollama (this computer)', env: null, models: ['qwen2.5:14b'] },
  { id: 'lmstudio', name: 'LM Studio (this computer)', env: null, models: [] },
];
const DEFAULT_MODELS = { selected: { source: 'anthropic', model: 'claude-haiku-5-5' }, keys: {}, custom: [], last: {} };
let models = structuredClone(DEFAULT_MODELS);

async function loadModels() {
  try {
    const saved = await window.selfbrowse.loadModels();
    if (saved && saved.selected && Array.isArray(saved.custom)) models = { ...DEFAULT_MODELS, ...saved, keys: saved.keys || {}, last: saved.last || {} };
  } catch (err) { toast(`Model settings could not be opened: ${err.message}`); }
  const cur = models.selected.source.startsWith('custom:') ? sourceOf(models.selected.source) : null;
  if (cur && !cur.model) cur.model = models.selected.model;        // saved before each source remembered its model
  renderModelBtn();
}
async function persistModels() {
  try { await window.selfbrowse.saveModels(models); } catch (err) { toast(err.message); }
}

// What is installed in Ollama / LM Studio right now. null = not asked yet; { ok, models, error } once asked.
const LOCAL = { ollama: null, lmstudio: null };
async function fetchLocal(id) {
  if (!(id in LOCAL)) return null;
  try { LOCAL[id] = await call('GET', `/local-models/${id}`); } catch (err) { LOCAL[id] = { ok: false, models: [], error: err.message }; }
  return LOCAL[id];
}
const gb = (n) => (n ? ` (${(n / 1e9).toFixed(1)} GB)` : '');

const sourceOf = (id) => id.startsWith('custom:')
  ? models.custom.find((c) => `custom:${c.id}` === id)
  : PROVIDERS.find((p) => p.id === id);
// The model last used with each source, so switching back to a source brings its model name back.
const lastModel = (id) => (id.startsWith('custom:') ? (sourceOf(id) || {}).model : models.last[id]) || '';
function sourceLabel(id) { const s = sourceOf(id); return s ? s.name : 'Unknown source'; }

function renderModelBtn() {
  const { source, model } = models.selected;
  $('modelBtn').textContent = `${sourceLabel(source)} · ${model || 'choose a model'} ▾`;
  if (typeof renderLedger === 'function') renderLedger();
}

// What a run sends to the backend.
function modelRequest() {
  const { source, model } = models.selected;
  if (source.startsWith('custom:')) {
    const c = sourceOf(source);
    if (!c) throw new Error('Choose a model first.');
    return { model, custom: { base_url: c.baseUrl, api: c.api || 'openai', json_mode: !!c.json && c.api !== 'anthropic' }, api_key: c.key || '' };
  }
  return { model: `${source}:${model}`, api_key: models.keys[source] || '' };
}

function openModelSheet(start) {
  let source = typeof start === 'string' ? start : models.selected.source;
  const draft = { name: '', baseUrl: '', json: false, api: 'openai' };
  const body = h('div');
  const field = (label, input, note) => h('label', { class: 'field' }, label, input, note ? h('span', { class: 'foot' }, note) : null);

  function draw() {
    const custom = source === 'custom:new' || source.startsWith('custom:');
    const existing = source.startsWith('custom:') && source !== 'custom:new' ? sourceOf(source) : null;
    const prov = custom ? null : sourceOf(source);
    const pick = h('select', { id: 'srcSel', 'aria-label': 'Source' },
      PROVIDERS.map((p) => h('option', { value: p.id }, p.name)),
      models.custom.map((c) => h('option', { value: `custom:${c.id}` }, `${c.name} (custom)`)),
      h('option', { value: 'custom:new' }, 'Add a custom source…'));
    pick.value = source;
    pick.addEventListener('change', () => { source = pick.value; draw(); });

    const rows = [field('Source', pick)];
    let name, url, model, key, json, apiSel, datalist = null;
    if (custom) {
      name = h('input', { value: existing ? existing.name : draft.name, spellcheck: 'false', autocomplete: 'off', placeholder: 'Company gateway' });
      url = h('input', { value: existing ? existing.baseUrl : draft.baseUrl, spellcheck: 'false', autocomplete: 'off', placeholder: 'https://llm.example.com/v1' });
      apiSel = h('select', { 'aria-label': 'API type' },
        h('option', { value: 'openai' }, 'OpenAI chat (/v1/chat/completions)'),
        h('option', { value: 'anthropic' }, 'Anthropic messages (/v1/messages)'));
      apiSel.value = existing ? existing.api || 'openai' : draft.api;
      apiSel.addEventListener('change', () => { if (json) json.closest('label').hidden = apiSel.value === 'anthropic'; });
      rows.push(field('Name', name), field('API type', apiSel, 'Pick the one your server speaks. If http://…/v1/models answers with type, display_name and has_more, it is Anthropic style.'), field('Base URL', url, 'Any server that speaks the OpenAI chat API: vLLM, LiteLLM, a company gateway, a cloud endpoint. Page text and screenshots are sent to this address.'));
    }
    const current = models.selected.source === source ? models.selected.model : lastModel(source) || (prov && prov.models[0]) || '';
    const local = prov && source in LOCAL ? LOCAL[source] : undefined;
    if (prov && source in LOCAL && LOCAL[source] === null) {
      const asked = source;
      fetchLocal(source).then(() => { if (source === asked && $('srcSel')) draw(); });     // fill the list in as soon as it arrives
    }
    if (local && local.ok && local.models.length) {
      const names = local.models.map((m) => m.name);
      model = h('select', { 'aria-label': 'Installed model', id: 'localModel' },
        current && !names.includes(current) ? h('option', { value: current }, `${current} (not installed)`) : null,
        local.models.map((m) => h('option', { value: m.name }, `${m.name}${gb(m.size)}`)));
      model.value = current || names[0];
      rows.push(field('Model', model, `${names.length} installed on this computer.`),
        h('div', { class: 'btns' }, h('button', { class: 'btn small', type: 'button', onclick: async () => { LOCAL[source] = null; draw(); } }, 'Refresh the list')));
    } else {
      model = h('input', { list: 'modelList', spellcheck: 'false', autocomplete: 'off', placeholder: custom ? 'The model name on that server' : 'Model name', value: current });
      if (prov && prov.models.length) datalist = h('datalist', { id: 'modelList' }, prov.models.map((m) => h('option', { value: m })));
      const note = !prov || !(source in LOCAL) ? null
        : local === null ? 'Looking for installed models…'
        : local && !local.ok ? local.error
        : local && local.ok ? 'Nothing is installed yet. Pull a model in Ollama, then refresh.' : null;
      rows.push(field('Model', model, note), datalist);
      if (local && !local.ok) rows.push(h('div', { class: 'btns' }, h('button', { class: 'btn small', type: 'button', onclick: () => { LOCAL[source] = null; draw(); } }, 'Try again')));
    }
    if (!prov || prov.env) {
      const saved = custom ? (existing && existing.key) : models.keys[source];
      key = h('input', { type: 'password', autocomplete: 'off', spellcheck: 'false',
        placeholder: saved ? 'Saved. Type to replace it.' : prov ? `Uses ${prov.env} if empty` : 'Optional' });
      rows.push(field('API key', key, 'Kept encrypted on this computer and sent only to this model’s server.'));
    }
    if (custom) {
      json = h('input', { type: 'checkbox' });
      json.checked = existing ? !!existing.json : draft.json;
      rows.push(h('label', { class: 'switch' }, json, 'Use JSON actions (for models without tool calling)'));
      rows[rows.length - 1].hidden = apiSel.value === 'anthropic';
    }

    const btns = [h('button', { class: 'btn', type: 'button', onclick: closeSheet }, 'Cancel')];
    if (existing) btns.unshift(h('button', { class: 'btn danger', type: 'button', onclick: () => {
      models.custom = models.custom.filter((c) => c !== existing);
      if (models.selected.source === source) models.selected = { ...DEFAULT_MODELS.selected };
      persistModels(); renderModelBtn(); closeSheet();
    } }, 'Delete source'));
    if (!custom && models.keys[source]) btns.unshift(h('button', { class: 'btn', type: 'button', onclick: () => {
      delete models.keys[source]; persistModels(); draw();
    } }, 'Remove saved key'));
    btns.push(h('button', { class: 'btn primary', type: 'button', onclick: () => {
      const m = model.value.trim();
      if (!m) return toast('Enter a model name.');
      if (!/^[A-Za-z0-9_.:/@+-]+$/.test(m)) return toast('The model name has characters that are not allowed.');
      let id = source;
      if (custom) {
        const n = name.value.trim(), u = url.value.trim();
        if (!n) return toast('Give the source a name.');
        if (!/^https?:\/\/\S+$/.test(u)) return toast('The base URL must start with http:// or https://');
        if (existing) {
          Object.assign(existing, { name: n, baseUrl: u, json: json.checked, api: apiSel.value, model: m });
          if (key.value) existing.key = key.value.trim();
        } else {
          const c = { id: Math.random().toString(36).slice(2, 10), name: n, baseUrl: u, json: json.checked, api: apiSel.value, model: m, key: key.value.trim() };
          models.custom.push(c);
          id = `custom:${c.id}`;
        }
      } else {
        if (key && key.value.trim()) models.keys[source] = key.value.trim();
        models.last[source] = m;
      }
      models.selected = { source: id, model: m };
      persistModels(); renderModelBtn(); closeSheet();
    } }, 'Use this model'));
    body.replaceChildren(...rows.filter(Boolean), h('div', { class: 'sharerow' }, ...btns));
  }
  draw();
  openSheet(h('div', { class: 'head' }, h('div', {}, h('h2', { id: 'sheetTitle' }, 'Model'),
    h('p', { class: 'muted' }, 'Choose who answers for the browser agent. Pick a provider, or add your own server.'))), body);
}

// ---- quick switch: the models you have used, one click each ----
function savedModels() {
  const rows = [{ source: models.selected.source, model: models.selected.model }];
  for (const p of PROVIDERS) if (models.last[p.id]) rows.push({ source: p.id, model: models.last[p.id] });
  for (const c of models.custom) if (c.model) rows.push({ source: `custom:${c.id}`, model: c.model });
  const seen = new Set();
  return rows.filter((r) => sourceOf(r.source) && !seen.has(`${r.source}|${r.model}`) && seen.add(`${r.source}|${r.model}`));
}
function closeModelMenu() { $('modelMenu').hidden = true; $('modelBtn').setAttribute('aria-expanded', 'false'); }
function drawModelMenu() {
  const cur = models.selected;
  const rows = savedModels().map((r) => {
    const on = r.source === cur.source && r.model === cur.model;
    return h('div', { class: `mrow${on ? ' on' : ''}`, role: 'none' },
      h('button', { class: 'mpick', type: 'button', role: 'menuitemradio', 'aria-checked': String(on),
        onclick: () => { models.selected = { source: r.source, model: r.model }; persistModels(); renderModelBtn(); closeModelMenu(); } },
        h('span', { class: 'mtick', 'aria-hidden': 'true' }, on ? '✓' : ''), h('span', { class: 'mname' }, sourceLabel(r.source)), h('span', { class: 'mmodel' }, r.model)),
      h('button', { class: 'medit', type: 'button', 'aria-label': `Edit ${sourceLabel(r.source)}`, title: 'Edit', onclick: () => { closeModelMenu(); openModelSheet(r.source); } }, 'Edit'));
  });
  const have = new Set(savedModels().map((r) => `${r.source}|${r.model}`));
  const installed = [];
  for (const [id, label] of [['ollama', 'Ollama'], ['lmstudio', 'LM Studio']]) {
    const l = LOCAL[id];
    if (!l || !l.ok || !l.models.length || (models.selected.source !== id && !models.last[id])) continue;     // only for a source you use
    installed.push(h('div', { class: 'msep' }), h('div', { class: 'mhead' }, `Installed in ${label}`));
    for (const m of l.models) {
      if (have.has(`${id}|${m.name}`)) continue;
      installed.push(h('div', { class: 'mrow', role: 'none' },
        h('button', { class: 'mpick', type: 'button', role: 'menuitemradio', 'aria-checked': 'false',
          onclick: () => { models.selected = { source: id, model: m.name }; models.last[id] = m.name; persistModels(); renderModelBtn(); closeModelMenu(); } },
          h('span', { class: 'mtick', 'aria-hidden': 'true' }), h('span', { class: 'mname' }, label), h('span', { class: 'mmodel' }, `${m.name}${gb(m.size)}`))));
    }
  }
  $('modelMenu').replaceChildren(...rows, ...installed, h('div', { class: 'msep' }),
    h('button', { class: 'mact', type: 'button', role: 'menuitem', onclick: () => { closeModelMenu(); openModelSheet('custom:new'); } }, '+ Add a custom source'),
    h('button', { class: 'mact', type: 'button', role: 'menuitem', onclick: () => { closeModelMenu(); openModelSheet(); } }, 'Choose another provider or model…'));
}
$('modelBtn').addEventListener('click', () => {
  if (!$('modelMenu').hidden) { closeModelMenu(); return; }
  drawModelMenu();
  $('modelMenu').hidden = false;
  $('modelBtn').setAttribute('aria-expanded', 'true');
  Promise.all(Object.keys(LOCAL).map(fetchLocal)).then(() => { if (!$('modelMenu').hidden) drawModelMenu(); });   // refresh what is installed
});
document.addEventListener('click', (e) => { if (!e.target.closest('.menuwrap')) closeModelMenu(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModelMenu(); });
