// Review a recorded flow before it is saved: skip or reorder steps, edit what a step types, and turn typed
// values into inputs that are asked for each time the flow runs.
const PARAM_RE = /\{\{([a-z][a-z0-9_]*)\}\}/g;
const VALUE_KEY = { goto: 'url', type: 'text', select: 'option', find: 'text' };   // the field a person may edit
const KIND_WORD = { goto: 'Open page', click: 'Click', type: 'Type', select: 'Choose', find: 'Look for', press: 'Press key', scroll: 'Scroll',
  back: 'Go back', wait: 'Wait', switch_tab: 'Switch tab', close_tab: 'Close tab', read: 'Read page', pause: 'Hand over' };

const paramSlug = (label) => (String(label).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^[^a-z]+/, '') || 'input').slice(0, 30);
const refsIn = (text) => [...String(text || '').matchAll(PARAM_RE)].map((m) => m[1]);

function openFlowEditor({ flow, lines, name, description, saveLabel, onSave, runId }) {
  const params = JSON.parse(JSON.stringify(flow.params || {}));
  const rows = flow.steps.map((step, i) => ({ step: JSON.parse(JSON.stringify(step)), line: lines[i], skip: false }));
  const nameIn = h('input', { type: 'text', maxlength: '80', value: name });
  const descIn = h('input', { type: 'text', maxlength: '500', value: description || '' });
  const msg = h('p', { class: 'note' });
  const paramsBox = h('div', { class: 'params' });
  const stepsBox = h('ol', { class: 'steps-edit' });
  const save = h('button', { class: 'btn primary', type: 'button' }, saveLabel || 'Save flow');
  const suggestBox = h('div', { class: 'suggest' });

  // Ask the chosen model which typed values should be inputs. The person reads exactly what is sent first,
  // and every suggestion is accepted or dismissed one by one; nothing is applied on its own.
  const askBody = () => ({ prompt: '', ...modelRequest(), presidio: $('presidio').checked, sensitive: allValues(),
    steps: live().map((r) => r.step) });
  function suggestIdle() {
    suggestBox.replaceChildren(runId ? h('div', { class: 'btns' },
      h('button', { class: 'btn small', type: 'button', onclick: suggestPreview }, 'Suggest inputs with a model'),
      h('span', { class: 'foot' }, 'You will see exactly what is sent before it goes.')) : '');
  }
  async function suggestPreview() {
    let req, pre;
    try { req = askBody(); pre = await post(`/runs/${runId}/suggest-inputs/preview`, req); } catch (err) { toast(err.message); return; }
    const where = sourceLabel(models.selected.source);
    suggestBox.replaceChildren(h('div', { class: 'consent' },
      h('p', {}, h('b', {}, `This will be sent to ${where}.`), ' Step wording and typed values only, no page contents.'),
      pre.hidden.length ? h('p', { class: 'foot' }, `Hidden before sending: ${pre.hidden.join(', ')}.`) : h('p', { class: 'foot' }, 'Nothing in it looked personal.'),
      h('pre', { class: 'payload-pre' }, pre.text),
      h('div', { class: 'btns' },
        h('button', { class: 'btn primary small', type: 'button', onclick: () => suggestSend(req) }, 'Send'),
        h('button', { class: 'btn small', type: 'button', onclick: suggestIdle }, 'Cancel'))));
  }
  async function suggestSend(req) {
    suggestBox.replaceChildren(h('p', { class: 'muted' }, 'Asking the model…'));
    const sent = live().map((r) => r);                         // step numbers in the answer refer to this list
    let res;
    try { res = await post(`/runs/${runId}/suggest-inputs`, req); } catch (err) { toast(err.message); suggestIdle(); return; }
    const todo = res.suggestions.filter((x) => {            // the server already checked; this is a second look
      const r = sent[x.step - 1], k = r && VALUE_KEY[r.step.do];
      return k && k !== 'url' && r.step.do !== 'find' && typeof r.step[k] === 'string' && r.step[k] && !/\{\{|<secret:/.test(r.step[k]);
    });
    if (!todo.length) { suggestBox.replaceChildren(h('p', { class: 'muted' }, 'The model found no values that need to be inputs.'), h('div', { class: 'btns' }, h('button', { class: 'btn small', type: 'button', onclick: suggestIdle }, 'Done'))); return; }
    const drawList = () => {
      suggestBox.replaceChildren(
        h('p', {}, h('b', {}, 'Suggested inputs'), ' Nothing changes until you accept.'),
        ...todo.map((x) => {
          const row = sent[x.step - 1], key = VALUE_KEY[row.step.do];
          const label = h('input', { type: 'text', value: x.label, maxlength: '60', 'aria-label': 'Input label' });
          return h('div', { class: 'sugg' },
            h('div', { class: 'sline' }, h('b', {}, `Step ${x.step}`), h('span', { class: 'muted' }, ` ${KIND_WORD[row.step.do]} “${row.step[key]}”`)),
            x.reason ? h('p', { class: 'foot' }, x.reason) : null,
            h('div', { class: 'btns' }, label,
              h('button', { class: 'btn small primary', type: 'button', onclick: () => { makeInput(row, label.value.trim() || x.label); todo.splice(todo.indexOf(x), 1); todo.length ? drawList() : suggestIdle(); } }, 'Accept'),
              h('button', { class: 'btn small', type: 'button', onclick: () => { todo.splice(todo.indexOf(x), 1); todo.length ? drawList() : suggestIdle(); } }, 'Dismiss')));
        }),
        h('div', { class: 'btns' }, h('button', { class: 'btn small', type: 'button', onclick: suggestIdle }, 'Close')));
    };
    drawList();
  }

  const live = () => rows.filter((r) => !r.skip);
  const used = () => new Set(live().flatMap((r) => { const k = VALUE_KEY[r.step.do]; return k ? refsIn(r.step[k]) : []; }));

  function makeInput(row, given) {
    const key = VALUE_KEY[row.step.do];
    const label = given || (row.step.target && row.step.target.text) || KIND_WORD[row.step.do] || 'Input';
    let name = paramSlug(label);
    for (let n = 2; params[name]; n++) name = `${paramSlug(label)}_${n}`;
    params[name] = { label, default: row.step[key] };
    row.step[key] = `{{${name}}}`;
    draw();
  }
  function makeFixed(name) {                                   // put the default back into the steps and drop the input
    const value = params[name].default == null ? '' : String(params[name].default);
    for (const r of rows) {
      const k = VALUE_KEY[r.step.do];
      if (k) r.step[k] = r.step[k].split(`{{${name}}}`).join(value);
    }
    delete params[name];
    draw();
  }
  const move = (i, d) => { const j = i + d; if (j < 0 || j >= rows.length) return; [rows[i], rows[j]] = [rows[j], rows[i]]; draw(); };

  function drawParams() {
    const inUse = used();
    const names = Object.keys(params);
    paramsBox.replaceChildren(
      h('h3', {}, 'Inputs'),
      h('p', { class: 'muted' }, names.length
        ? 'Asked for each time the flow runs. The default is what it uses if you leave it blank.'
        : 'None yet. Use “Make this an input” on a step that types or chooses a value, like a city or a date.'),
      ...names.map((n) => {
        const p = params[n];
        const label = h('input', { type: 'text', value: p.label || n, maxlength: '60', 'aria-label': 'Label' });
        label.addEventListener('input', () => { p.label = label.value; });
        const def = h('input', { type: 'text', value: p.default == null ? '' : String(p.default), 'aria-label': 'Default value', placeholder: 'No default' });
        def.addEventListener('input', () => { if (def.value === '') delete p.default; else p.default = def.value; });
        const req = h('input', { type: 'checkbox' });
        req.checked = !!p.required;
        req.addEventListener('change', () => { p.required = req.checked; if (req.checked) { delete p.default; def.value = ''; } });
        return h('div', { class: 'prow' },
          h('div', { class: 'pname' }, h('code', {}, `{{${n}}}`), inUse.has(n) ? null : h('span', { class: 'foot' }, ' not used, will be dropped')),
          h('label', { class: 'field' }, 'Label', label),
          h('label', { class: 'field' }, 'Default', def),
          h('label', { class: 'switch' }, req, 'Always ask'),
          h('button', { class: 'btn small', type: 'button', onclick: () => makeFixed(n) }, 'Make fixed'));
      }));
  }

  function drawSteps() {
    stepsBox.replaceChildren(...rows.map((row, i) => {
      const st = row.step, key = VALUE_KEY[st.do];
      const target = st.target ? `${st.target.role} “${st.target.text}”` : '';
      const input = key ? h('input', { type: 'text', value: st[key], spellcheck: 'false', 'aria-label': `${KIND_WORD[st.do]} value`, disabled: row.skip || null }) : null;
      if (input) input.addEventListener('input', () => { st[key] = input.value; drawParamsLater(); });
      const isSecret = key && /<secret:/.test(st[key]);
      const refs = key ? refsIn(st[key]) : [];
      const can = key && !isSecret && !refs.length && st[key].trim() !== '' && st.do !== 'find' && st.do !== 'goto';    // a whole page address cannot be an input
      return h('li', { class: `srow${row.skip ? ' skipped' : ''}` },
        h('div', { class: 'sline' },
          h('b', {}, KIND_WORD[st.do] || st.do), target ? h('span', { class: 'muted' }, ` ${target}`) : null,
          refs.map((r) => h('span', { class: 'chip local' }, params[r] ? params[r].label || r : `{{${r}}}`)),
          isSecret ? h('span', { class: 'chip local' }, 'from My info') : null),
        input,
        h('div', { class: 'srow-btns' },
          can ? h('button', { class: 'btn small', type: 'button', disabled: row.skip || null, onclick: () => makeInput(row) }, 'Make this an input') : null,
          h('button', { class: 'btn small', type: 'button', 'aria-label': 'Move up', disabled: i === 0 || null, onclick: () => move(i, -1) }, '↑'),
          h('button', { class: 'btn small', type: 'button', 'aria-label': 'Move down', disabled: i === rows.length - 1 || null, onclick: () => move(i, 1) }, '↓'),
          h('button', { class: 'btn small', type: 'button', onclick: () => { row.skip = !row.skip; draw(); } }, row.skip ? 'Keep step' : 'Skip step')));
    }));
  }
  let later = null;
  const drawParamsLater = () => { clearTimeout(later); later = setTimeout(drawParams, 300); };
  function draw() { drawParams(); drawSteps(); save.disabled = live().length === 0; }

  save.addEventListener('click', async () => {
    if (!nameIn.value.trim()) { msg.textContent = 'Give the flow a name.'; return; }
    const inUse = used(), outParams = {};
    for (const [n, p] of Object.entries(params)) {
      if (!inUse.has(n)) continue;
      const spec = { label: (p.label || n).trim() || n };
      if (p.required) spec.required = true; else if (p.default != null) spec.default = String(p.default);
      outParams[n] = spec;
    }
    save.disabled = true;
    try {
      await onSave({ name: nameIn.value.trim(), description: descIn.value.trim(), edited: { params: outParams, steps: live().map((r) => r.step) } });
    } catch (err) { msg.textContent = err.message; save.disabled = false; }
  });

  $('sheet').classList.add('wide');
  openSheet(
    h('div', { class: 'head' }, h('div', {}, h('h2', { id: 'sheetTitle' }, 'Review before saving'),
      h('p', { class: 'muted' }, 'A flow replays these steps without a model. Check each step, skip the ones you do not need, and turn values that change from run to run into inputs.'))),
    h('label', { class: 'field' }, 'Name', nameIn), h('label', { class: 'field' }, 'Description', descIn),
    suggestBox, paramsBox, h('h3', {}, `Steps (${rows.length})`), stepsBox, msg,
    h('div', { class: 'sharerow' }, save, h('button', { class: 'btn', type: 'button', onclick: closeSheet }, 'Cancel')));
  suggestIdle();
  draw();
}
