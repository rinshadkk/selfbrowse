// History: a summary of each finished run, kept on this computer by the backend.
const H = { items: [], selected: null };

function keepHistory() { return $('keepHistory').checked; }
try { $('keepHistory').checked = localStorage.getItem('sb.history') !== 'off'; } catch (_) { /* default on */ }
$('keepHistory').addEventListener('change', () => { try { localStorage.setItem('sb.history', keepHistory() ? 'on' : 'off'); } catch (_) { /* fine */ } });

function when(iso) {
  const d = new Date(iso), now = new Date();
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return `Today ${time}`;
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return `Yesterday ${time}`;
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' })} ${time}`;
}
const dur = (s) => (s < 90 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`);
const outcome = (r) => (r.stopped ? ['Stopped', ''] : r.success ? ['Done', 'ok'] : ['Not finished', 'bad']);

async function loadHistory() {
  try { H.items = await call('GET', '/history'); } catch (err) { toast(err.message); return; }
  if (!H.items.some((i) => i.id === H.selected)) H.selected = H.items.length ? H.items[0].id : null;
  renderHistory();
}

function renderHistory() {
  $('histList').replaceChildren(...H.items.map((r) => {
    const [label, cls] = outcome(r);
    return h('button', { class: 'hitem', type: 'button', 'aria-current': r.id === H.selected ? 'true' : 'false', onclick: () => { H.selected = r.id; renderHistory(); } },
      h('b', {}, r.kind === 'flow' ? `Flow: ${r.flow}` : r.prompt || '(no task)'),
      h('small', {}, h('span', { class: `hdot ${cls}` }), h('span', {}, label), h('span', {}, '·'), h('span', {}, when(r.started))));
  }));
  $('histClear').hidden = !H.items.length;
  if (!H.selected) {
    $('histMain').replaceChildren(h('h1', {}, 'No runs yet'),
      h('p', { class: 'lead' }, 'Runs you start appear here, so you can look back at what the browser did, reuse a task, or see what it cost.'));
    return;
  }
  showHistory(H.selected);
}

async function showHistory(id) {
  let r;
  try { r = await call('GET', `/history/${id}`); } catch (err) { toast(err.message); return; }
  if (H.selected !== id) return;                               // the person clicked another run meanwhile
  const [label, cls] = outcome(r);
  const tokens = r.input_tokens + r.output_tokens;
  const stat = (v, l) => h('div', {}, h('b', {}, v), h('span', {}, l));
  const body = [
    h('div', { class: 'titlerow' }, h('h1', {}, r.kind === 'flow' ? `Flow: ${r.flow}` : 'Run')),
    h('p', { class: 'muted' }, `${when(r.started)}${r.model ? ` · ${r.model}` : ''}`),
    h('p', {}, h('span', { class: `chip ${cls === 'ok' ? 'local' : 'plain'}` }, label), r.kind === 'flow' ? h('span', { class: 'chip plain' }, 'Replayed without a model') : null),
    r.prompt ? h('p', {}, h('b', {}, 'Task: '), r.prompt) : null,
    h('div', { class: 'hstats' }, stat(String(r.steps.length), 'steps'), stat(dur(r.seconds), 'took'),
      stat(fmt(tokens), 'tokens'), r.kind === 'flow' && !r.calls ? null : stat(String(r.calls), 'model calls')),
    r.answer ? [h('h3', {}, 'Answer'), h('div', { class: 'hanswer' }, restoreSecrets(r.answer))] : null,
    r.error && !r.stopped ? [h('h3', {}, 'What went wrong'), h('div', { class: 'hanswer err' }, r.error)] : null,
    h('div', { class: 'btns' },
      r.kind === 'run' && r.prompt ? h('button', { class: 'btn primary', type: 'button', onclick: () => { $('prompt').value = r.prompt; go('run'); $('prompt').focus(); } }, 'Run again') : null,
      r.kind === 'flow' ? h('button', { class: 'btn', type: 'button', onclick: () => go('flows') }, 'Open Flows') : null,
      h('button', { class: 'btn danger', type: 'button', id: 'histDelete' }, 'Delete')),
    r.steps.length ? [h('h3', {}, `Steps (${r.steps.length})`),
      h('ol', { class: 'hsteps' }, r.steps.map((s) => h('li', {}, s.tool, s.result ? h('small', {}, s.result) : null, s.url ? h('small', {}, s.url) : null)))] : null,
  ];
  $('histMain').replaceChildren(...body.flat(2).filter(Boolean));
  confirmClick($('histDelete'), 'Click again to delete', async () => {
    try { await call('DELETE', `/history/${id}`); } catch (err) { toast(err.message); return; }
    H.selected = null; loadHistory();
  });
}

confirmClick($('histClear'), 'Click again to clear all', async () => {
  try { await call('DELETE', '/history'); } catch (err) { toast(err.message); return; }
  H.selected = null; loadHistory();
});
