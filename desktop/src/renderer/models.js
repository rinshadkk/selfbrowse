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
const DEFAULT_MODELS = { selected: { source: 'anthropic', model: 'claude-haiku-5-5' }, keys: {}, custom: [] };
let models = structuredClone(DEFAULT_MODELS);

async function loadModels() {
  try {
    const saved = await window.selfbrowse.loadModels();
    if (saved && saved.selected && Array.isArray(saved.custom)) models = { ...DEFAULT_MODELS, ...saved, keys: saved.keys || {} };
  } catch (err) { toast(`Model settings could not be opened: ${err.message}`); }
  renderModelBtn();
}
async function persistModels() {
  try { await window.selfbrowse.saveModels(models); } catch (err) { toast(err.message); }
}

const sourceOf = (id) => id.startsWith('custom:')
  ? models.custom.find((c) => `custom:${c.id}` === id)
  : PROVIDERS.find((p) => p.id === id);
function sourceLabel(id) { const s = sourceOf(id); return s ? s.name : 'Unknown source'; }

function renderModelBtn() {
  const { source, model } = models.selected;
  $('modelBtn').textContent = `${sourceLabel(source)} · ${model || 'choose a model'}`;
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

function openModelSheet() {
  let source = models.selected.source;
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
    model = h('input', { list: 'modelList', spellcheck: 'false', autocomplete: 'off', placeholder: custom ? 'The model name on that server' : 'Model name',
      value: models.selected.source === source ? models.selected.model : (prov && prov.models[0]) || '' });
    if (prov && prov.models.length) datalist = h('datalist', { id: 'modelList' }, prov.models.map((m) => h('option', { value: m })));
    rows.push(field('Model', model), datalist);
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
          Object.assign(existing, { name: n, baseUrl: u, json: json.checked, api: apiSel.value });
          if (key.value) existing.key = key.value.trim();
        } else {
          const c = { id: Math.random().toString(36).slice(2, 10), name: n, baseUrl: u, json: json.checked, api: apiSel.value, key: key.value.trim() };
          models.custom.push(c);
          id = `custom:${c.id}`;
        }
      } else if (key && key.value.trim()) models.keys[source] = key.value.trim();
      models.selected = { source: id, model: m };
      persistModels(); renderModelBtn(); closeSheet();
    } }, 'Use this model'));
    body.replaceChildren(...rows.filter(Boolean), h('div', { class: 'sharerow' }, ...btns));
  }
  draw();
  openSheet(h('div', { class: 'head' }, h('div', {}, h('h2', { id: 'sheetTitle' }, 'Model'),
    h('p', { class: 'muted' }, 'Choose who answers for the browser agent. Pick a provider, or add your own server.'))), body);
}
$('modelBtn').addEventListener('click', openModelSheet);
