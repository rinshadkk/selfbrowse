// Guardrails: every limit the library offers, set once and applied to each run. Kept in this browser's storage.
// What a run sends is built by guardSettings(); the backend validates it (see GuardSettings in server.py).
const G_DEFAULT = {
  safe_urls: true, allow: '', block: '', confirm_risky: false, watch_injection: false,
  redact: [], restore: true, page_presidio: false,
  max_steps: '40', max_tokens: '', max_seconds: '', max_usd: '',
};
let GS = { ...G_DEFAULT };
try { GS = { ...G_DEFAULT, ...JSON.parse(localStorage.getItem('sb.guards') || '{}') }; } catch (_) { /* defaults */ }
function saveGuards() { try { localStorage.setItem('sb.guards', JSON.stringify(GS)); } catch (_) { /* fine */ } renderGuardSummary(); }

const lines = (t) => String(t || '').split(/[\n,]+/).map((x) => x.trim()).filter(Boolean);
const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) && n > 0 ? n : null; };

// The `guards` and `max_steps` a run sends.
function guardSettings() {
  const p = loadPrices(), usd = num(GS.max_usd);
  if (usd && (num(p.in) === null && p.in !== '0' || num(p.out) === null && p.out !== '0')) throw new Error('A dollar limit needs your model’s prices. Enter them under Guardrails > Limits.');
  return {
    guards: {
      safe_urls: GS.safe_urls, allow: lines(GS.allow), block: lines(GS.block),
      confirm_risky: GS.confirm_risky, watch_injection: GS.watch_injection,
      redact: GS.redact, restore: GS.restore, page_presidio: GS.page_presidio,
      max_tokens: num(GS.max_tokens) && Math.round(num(GS.max_tokens)), max_seconds: num(GS.max_seconds) && Math.round(num(GS.max_seconds)),
      max_usd: usd, price_in: usd ? parseFloat(p.in) : null, price_out: usd ? parseFloat(p.out) : null,
    },
    max_steps: Math.min(100, Math.max(1, Math.round(num(GS.max_steps) || 40))),
  };
}

function activeGuards() {
  const on = [];
  if (GS.safe_urls) on.push('web pages only');
  if (lines(GS.allow).length) on.push('allowed sites');
  if (lines(GS.block).length) on.push('blocked sites');
  if (GS.confirm_risky) on.push('ask before risky actions');
  if (GS.watch_injection) on.push('watch for injected instructions');
  if (GS.redact.length || GS.page_presidio) on.push('mask personal data on pages');
  if (num(GS.max_tokens) || num(GS.max_seconds) || num(GS.max_usd)) on.push('limits');
  if ($('review').value !== 'off') on.push('review before sending');
  return on;
}
function renderGuardSummary() {
  const on = activeGuards();
  $('gSummary').textContent = on.length ? `On: ${on.join(', ')}.` : 'No guardrails are on.';
}

function switchRow(key, label, note, extra) {
  const box = h('input', { type: 'checkbox', id: `g_${key}` });
  box.checked = !!GS[key];
  box.addEventListener('change', () => { GS[key] = box.checked; saveGuards(); if (extra) extra(box.checked); });
  return [h('label', { class: 'switch' }, box, ` ${label}`), note ? h('p', { class: 'foot' }, note) : null];
}
function textRow(key, label, note, placeholder) {
  const ta = h('textarea', { id: `g_${key}`, placeholder, spellcheck: 'false', 'aria-label': label });
  ta.value = GS[key];
  ta.addEventListener('input', () => { GS[key] = ta.value; saveGuards(); });
  return h('label', { class: 'field' }, label, ta, note ? h('span', { class: 'foot' }, note) : null);
}
function numberRow(key, label, placeholder) {
  const inp = h('input', { type: 'number', id: `g_${key}`, min: '0', step: 'any', placeholder });
  inp.value = GS[key];
  inp.addEventListener('input', () => { GS[key] = inp.value; saveGuards(); });
  return h('label', { class: 'field' }, label, inp);
}
const card = (title, why, ...kids) => h('section', { class: 'gcard' }, h('h3', {}, title), why ? h('p', { class: 'why' }, why) : null, ...kids);

function drawGuards() {
  const kinds = h('div', { class: 'kinds' }, [['email', 'Emails'], ['phone', 'Phone numbers'], ['ssn', 'US SSNs'], ['card', 'Card numbers']].map(([k, name]) => {
    const box = h('input', { type: 'checkbox', id: `g_kind_${k}` });
    box.checked = GS.redact.includes(k);
    box.addEventListener('change', () => { GS.redact = ['email', 'phone', 'ssn', 'card'].filter((x) => (x === k ? box.checked : GS.redact.includes(x))); saveGuards(); });
    return h('label', {}, box, name);
  }));
  const presidio = switchRow('page_presidio', 'Also find names and more with Presidio', 'Runs on this computer. Install it from the ⋯ menu on the Run screen first.');
  const review = h('select', { id: 'gReview', 'aria-label': 'Review before sending' },
    h('option', { value: 'off' }, 'Off'), h('option', { value: 'flagged' }, 'When something looks personal'), h('option', { value: 'always' }, 'Every model call'));
  review.value = $('review').value;
  review.addEventListener('change', () => { setReviewMode(review.value); renderGuardSummary(); });
  const secrets = h('input', { type: 'checkbox', id: 'gShowSecrets' });
  secrets.checked = $('showSecrets').checked;
  secrets.addEventListener('change', () => { $('showSecrets').checked = secrets.checked; $('showSecrets').dispatchEvent(new Event('change')); });
  const pIn = h('input', { type: 'number', min: '0', step: 'any', id: 'g_pin', placeholder: 'USD' });
  const pOut = h('input', { type: 'number', min: '0', step: 'any', id: 'g_pout', placeholder: 'USD' });
  const prices = loadPrices(); pIn.value = prices.in || ''; pOut.value = prices.out || '';
  const setPrice = () => { $('priceIn').value = pIn.value; $('priceOut').value = pOut.value; savePrices(); };
  pIn.addEventListener('input', setPrice); pOut.addEventListener('input', setPrice);

  $('gBody').replaceChildren(
    card('Sites', 'Where the agent may go. Each page it lands on is checked, including after a redirect.',
      switchRow('safe_urls', 'Web pages only', 'Blocks file:, chrome:, data: and javascript: addresses. Leave this on unless you are testing a local file.'),
      textRow('allow', 'Only these sites', 'One per line. A site includes its subdomains. Empty means any site.', 'example.com'),
      textRow('block', 'Never these sites', 'One per line.', 'ads.example.net')),
    card('Actions', 'What the agent must ask you about first.',
      switchRow('confirm_risky', 'Ask before risky actions', 'Buy, Pay, Delete, Send, Sign out, file uploads and dialogs that look irreversible. The run pauses and shows the browser.'),
      switchRow('watch_injection', 'Watch for instructions hidden in pages', 'Warns the model that a page is talking to it, and asks you before it navigates or acts from that page. Pattern based, so it can miss a cleverly worded attack.')),
    card('Personal data in pages', 'Masked before the model reads the page. This is separate from what you type in My info.',
      kinds, ...presidio,
      ...switchRow('restore', 'Type masked values back where needed', 'The model sees <EMAIL_1>. If it types that into a field on the same site, the real value goes in. Off masks for good.')),
    card('Limits', 'A run stops, and says why, when it reaches any of these. Empty means no limit.',
      h('div', { class: 'row' }, numberRow('max_steps', 'Most steps (1 to 100)', '40'), numberRow('max_tokens', 'Most tokens', '200000'), numberRow('max_seconds', 'Most seconds', '300')),
      h('div', { class: 'row' }, numberRow('max_usd', 'Most dollars', '1.00'),
        h('label', { class: 'field' }, 'Input price per million tokens', pIn), h('label', { class: 'field' }, 'Output price per million tokens', pOut)),
      h('p', { class: 'foot' }, 'A dollar limit needs prices, which differ by model and are not built in. Cached tokens are counted at the full input price, so the limit can hit early.')),
    card('Messages to the model', 'The same controls as on the Run screen.',
      h('label', { class: 'field' }, 'Review before sending', review),
      h('label', { class: 'switch' }, secrets, ' Show My info values in the answer')));
  renderGuardSummary();
}
$('gReset').addEventListener('click', () => { GS = { ...G_DEFAULT }; saveGuards(); drawGuards(); toast('Guardrails reset.'); });
drawGuards();
