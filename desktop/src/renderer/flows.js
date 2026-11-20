// Flows: runs you saved. Replaying one uses no model. Sharing shows exactly what goes in the file.
let flowList = [];

function ago(iso) {
  const t = Date.parse(iso);
  if (!t) return '';
  const d = Math.floor((Date.now() - t) / 86400000);
  return d <= 0 ? 'saved today' : d === 1 ? 'saved yesterday' : d < 14 ? `saved ${d} days ago` : `saved ${Math.floor(d / 7)} weeks ago`;
}

async function loadFlows() {
  try { flowList = await call('GET', '/flows'); } catch (err) { toast(err.message); flowList = []; }
  renderFlows();
}

function renderFlows() {
  const cards = flowList.map((f) => {
    const owners = [...new Set(f.secrets.map((s) => secretOwner(s) || `“${s}”`))];
    const required = Object.values(f.params).filter((p) => p.required).length;
    const meta = [h('span', { class: 'chip sent' }, '0 tokens to replay'),
      ...owners.map((o) => h('span', { class: 'chip local' }, `Uses: ${o}`)),
      required ? h('span', { class: 'chip plain' }, `Asks for ${required} value${required > 1 ? 's' : ''}`) : null,
      !owners.length && !required ? h('span', { class: 'chip plain' }, 'No personal info') : null];
    const del = h('button', { class: 'btn quiet danger', type: 'button' }, 'Delete');
    confirmClick(del, 'Click to delete', async () => { try { await call('DELETE', `/flows/${f.id}`); loadFlows(); } catch (err) { toast(err.message); } });
    return h('div', { class: 'card' },
      h('h3', {}, f.name),
      h('div', { class: 'muted' }, [f.domains.join(', '), `${f.steps} steps`, ago(f.created)].filter(Boolean).join(' · ')),
      h('div', { class: 'meta' }, meta),
      h('div', { class: 'btns' }, h('button', { class: 'btn primary', type: 'button', onclick: () => runFlow(f) }, 'Run'),
        h('button', { class: 'btn', type: 'button', onclick: () => shareFlow(f) }, 'Share…'), del));
  });
  cards.push(h('div', { class: 'card new' }, h('div', {}, h('b', {}, flowList.length ? 'Turn any run into a flow' : 'No flows yet'),
    h('div', {}, 'After a run succeeds, choose “Save as flow”.'))));
  $('cards').replaceChildren(...cards);
}

// ---- replay ----
function runFlow(f) {
  const have = localValues();
  const missing = f.secrets.filter((s) => !(s in have));
  const inputs = Object.entries(f.params).map(([name, p]) => {
    const input = h('input', { type: 'text', placeholder: p.default != null ? String(p.default) : p.required ? 'Required' : '', maxlength: '500', autocomplete: 'off', 'data-name': name });
    return { name, p, input, el: h('label', { class: 'field' }, p.label + (p.required ? ' (required)' : ''), input) };
  });
  const msg = h('p', { class: 'note' }, '');
  const start = async () => {
    const params = {};
    for (const x of inputs) {
      if (x.input.value) params[x.name] = x.input.value;
      else if (x.p.required) { msg.textContent = `Fill in “${x.p.label}” first.`; return; }
    }
    try {
      const { id } = await post(`/flows/${f.id}/run`, { params, sensitive: have, headed: false, history: keepHistory(), ...browserOptions() });
      closeSheet();
      beginRun(id, f.name);
    } catch (err) { msg.textContent = err.message; }
  };
  if (!missing.length && !inputs.length) { start(); return; }
  const go_ = h('button', { class: 'btn primary', type: 'button', onclick: start }, 'Run flow');
  if (missing.length) go_.disabled = true;
  openSheet(h('div', { class: 'head' }, h('div', {}, h('h2', { id: 'sheetTitle' }, `Run “${f.name}”`), h('p', { class: 'muted' }, 'Replays the saved steps. No model is used.'))),
    missing.length ? h('div', { class: 'warnbox' }, h('b', {}, 'This flow needs info you have not saved yet.'),
      h('p', { class: 'note' }, `Add ${missing.map((m) => `“${m}”`).join(', ')} in My info, set to “Only me”. The field names must match.`)) : null,
    ...inputs.map((x) => x.el), msg,
    h('div', { class: 'sharerow' }, go_, h('button', { class: 'btn', type: 'button', onclick: closeSheet }, 'Cancel')));
}

// ---- share ----
async function shareFlow(f) {
  let r;
  try { r = await post(`/flows/${f.id}/share-check`, { sensitive: allValues() }); } catch (err) { toast(err.message); return; }
  const row = (cls, mark, title, ...rest) => h('div', { class: 'check' }, h('span', { class: `ic ${cls}` }, mark), h('div', {}, h('b', {}, title), ...rest));
  const placeholders = [...r.secrets.map((s) => `<secret:${s}>`), ...Object.entries(r.params).map(([k, label]) => `{{${k}}}  ${label}`)];
  const checks = [
    row('yes', '✓', `The ${r.steps.length} step${r.steps.length === 1 ? '' : 's'}`, h('div', { class: 'muted' }, r.domains.length ? `Runs only on ${r.domains.join(', ')}.` : ''), h('div', { class: 'codebox' }, r.steps.map((s, i) => `${i + 1}. ${s}`).join('\n'))),
    placeholders.length
      ? row('yes', '✓', `${placeholders.length} placeholder${placeholders.length === 1 ? '' : 's'} instead of your info`, h('div', { class: 'muted' }, 'Whoever opens it fills in their own details.'), h('div', { class: 'codebox' }, placeholders.join('\n')))
      : row('yes', '✓', 'No personal info in this flow'),
    row('no', '×', 'Not included', h('div', { class: 'muted' }, 'Your saved values, cookies, saved logins, your card, and the history of this run.')),
    r.replaced.length
      ? row('warn', '!', `${r.replaced.length} stray personal value${r.replaced.length === 1 ? '' : 's'} found and replaced`,
        h('div', { class: 'muted' }, 'We searched every step, the name and the description for your saved info, emails, phone numbers and card numbers. These were typed in directly, so they were taken out of the file:'),
        h('div', { class: 'codebox' }, r.replaced.map((x) => `${x.where}   “${x.was}”   →   ${x.now}`).join('\n')))
      : row('yes', '✓', 'No stray personal values found', h('div', { class: 'muted' }, 'We searched every step, the name and the description for your saved info, emails, phone numbers and card numbers.')),
    row('yes', '?', 'What the person receiving it needs', h('div', { class: 'muted' }, r.secrets.length
      ? `Fields in My info named ${r.secrets.map((s) => `“${s}”`).join(', ')}, set to “Only me”.` : 'Nothing. It runs as it is.')),
  ];
  const save = h('button', { class: 'btn primary', type: 'button' }, 'Save as file');
  save.addEventListener('click', async () => {
    try {
      const path = await window.selfbrowse.saveFile(`${f.name}.json`, JSON.stringify(r.flow, null, 2));
      if (path) { closeSheet(); toast('Saved the file. Check it before you send it.'); }
    } catch (err) { toast(err.message); }
  });
  openSheet(h('div', { class: 'head' }, h('div', {}, h('h2', { id: 'sheetTitle' }, `Share “${f.name}”`), h('p', { class: 'muted' }, 'Checked just now. Here is everything that goes in the file.')),
    h('button', { class: 'btn quiet', type: 'button', 'aria-label': 'Close', onclick: closeSheet }, 'Close')),
    ...checks, h('div', { class: 'sharerow' }, save),
    h('p', { class: 'foot' }, 'The file is saved where you choose. Nothing is uploaded.'));
}
