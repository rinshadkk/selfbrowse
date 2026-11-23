// My info: forms of personal details. Each field says who may see its value. By default only this computer does:
// the model is given a placeholder like <secret:SHIPPING_CITY> and Selfbrowse types the real value itself.
const V = { sel: null, timer: null, saved: null };

// A label that starts with "!" is a protected field: masked, kept only on this computer, shown only after you confirm.
const TEMPLATES = {
  'Shipping address': ['Full name', 'Phone', 'Street address', 'City', 'State', 'ZIP'],
  'Contact': ['Email', 'Phone'],
  'Insurance card': ['Member ID', 'Group number', 'Plan name', 'Date of birth'],
  'Website login': ['Website', 'Username', '!Password'],
  'Sensitive details': ['!Social Security number', '!Passport number', '!Security answer'],
};
const POLICIES = [['local', 'Only me'], ['model', 'Model may see'], ['off', 'Don’t use']];
const uid = () => Math.random().toString(36).slice(2, 10);

function setSaved(text, error = false) {
  if (!V.saved) return;
  V.saved.textContent = text;
  V.saved.className = error ? 'error' : '';
}
// Says which website this form is tied to, and updates as the Website field is edited.
function updateSiteNote() {
  const form = vault.forms.find((f) => f.id === V.sel), note = V.siteNote;
  if (!form || !note || !note.isConnected) return;
  const tag = siteField(form), site = formSite(form);
  note.className = `sitebind${site ? ' on' : ''}`;
  note.replaceChildren(...(site ? ['Typed only on ', h('strong', {}, site), ' and its subdomains. Never on any other site.']
    : tag && tag.value.trim() ? ['That does not look like a website address, so these values can be typed on any site.']
    : tag ? ['Add the website above to limit where these values are typed.']
    : ['Not tied to a website, so these values can be typed on any site. Add a field named Website to tie them to one.']));
}
function persist() {
  updateSiteNote();
  clearTimeout(V.timer);
  setSaved('Saving…');
  V.timer = setTimeout(async () => {
    try {
      ensureNames();
      await window.selfbrowse.saveMyInfo(vault);
      setSaved('Saved on this computer, encrypted.');
      if (typeof refreshUseInfo === 'function') refreshUseInfo();
    } catch (err) { setSaved(err.message, true); }
  }, 400);
}

function addForm(name, labels) {
  const form = { id: uid(), name, fields: labels.map((label) => label.startsWith('!') ? { id: uid(), label: label.slice(1), value: '', policy: 'local', kind: 'secret' } : { id: uid(), label, value: '', policy: 'local' }) };
  vault.forms.push(form);
  ensureNames();
  V.sel = form.id;
  persist();
  renderVault();
}

function renderFormList() {
  const list = $('formList');
  list.replaceChildren(...vault.forms.map((f) => h('button', { class: 'listbtn', type: 'button', 'aria-current': String(f.id === V.sel), onclick: () => { V.sel = f.id; renderVault(); } },
    f.name || 'Untitled form', h('small', {}, `${f.fields.length} field${f.fields.length === 1 ? '' : 's'}`))));
}

const hiders = new Set();
function fieldRow(form, f) {
  const small = h('small', {}, f.secret ? `<secret:${f.secret}>` : 'Name a field to use it');
  const label = h('input', { type: 'text', value: f.label, placeholder: 'Label, for example City', 'aria-label': 'Field label', maxlength: '60' });
  label.addEventListener('input', () => { f.label = label.value; persist(); });
  label.addEventListener('change', () => { ensureNames(); small.textContent = f.secret ? `<secret:${f.secret}>` : 'Name a field to use it'; persist(); });
  const err = h('div', { class: 'err', hidden: true }, 'This looks like a card number. Selfbrowse does not store those; it asks you each time.');
  const prot = f.kind === 'secret';
  const value = h('input', { type: prot ? 'password' : 'text', value: f.value, placeholder: 'Value', 'aria-label': `Value for ${f.label || 'field'}`, autocomplete: prot ? 'new-password' : 'off', spellcheck: 'false', maxlength: '500' });
  value.addEventListener('input', () => {
    if (looksLikeCard(value.value)) { value.value = ''; f.value = ''; err.hidden = false; } else { err.hidden = true; f.value = value.value; }
    ensureNames(); small.textContent = f.secret ? `<secret:${f.secret}>` : small.textContent;
    persist();
  });
  const showBtn = h('button', { class: 'btn small', type: 'button', 'aria-label': `Show ${f.label || 'value'}` }, 'Show');
  let hideTimer = null;
  const hide = () => { clearTimeout(hideTimer); value.type = 'password'; showBtn.textContent = 'Show'; };
  showBtn.addEventListener('click', async () => {
    if (value.type === 'text') { hide(); return; }
    let r;
    try { r = await window.selfbrowse.confirmIdentity(`show ${f.label || 'a saved value'}`); } catch (err) { toast(err.message); return; }
    if (!r.ok) return;
    value.type = 'text'; showBtn.textContent = 'Hide';
    hideTimer = setTimeout(hide, 15000);                       // it covers itself again
  });
  hiders.add(hide);
  const seg = prot ? h('div', { class: 'locked' }, h('span', { class: 'lockicon', 'aria-hidden': 'true' }), 'Only me. Never sent to the model.', showBtn) : h('div', { class: 'seg', role: 'group', 'aria-label': `Who may see ${f.label || 'this field'}` },
    POLICIES.map(([id, text]) => h('button', { type: 'button', class: id, 'aria-pressed': String(f.policy === id), onclick: (e) => {
      f.policy = id;
      for (const b of seg.children) b.setAttribute('aria-pressed', String(b === e.currentTarget));
      persist();
    } }, text)));
  const del = h('button', { class: 'btn quiet small', type: 'button', 'aria-label': `Remove ${f.label || 'field'}`, title: 'Remove field' }, '×');
  del.addEventListener('click', () => { form.fields = form.fields.filter((x) => x !== f); persist(); renderVault(); });
  return h('div', { class: 'fieldrow' }, h('div', { class: 'nm' }, label, small), value, seg, del, err);
}

function hideAllSecrets() { for (const fn of hiders) fn(); hiders.clear(); }
function renderVault() {
  if (typeof $ !== 'function' || !$('vaultMain')) return;
  hideAllSecrets();
  if (!vault.forms.some((f) => f.id === V.sel)) V.sel = vault.forms[0] ? vault.forms[0].id : null;
  renderFormList();
  const main = $('vaultMain');
  const form = vault.forms.find((f) => f.id === V.sel);
  if (!form) {
    main.replaceChildren(h('h1', {}, 'My info'),
      h('p', { class: 'lead' }, 'Save your details once, and Selfbrowse can fill forms for you. By default the model never sees the values, only the name of the field.'),
      h('div', { class: 'btns' }, Object.entries(TEMPLATES).map(([name, labels]) => h('button', { class: 'btn', type: 'button', onclick: () => addForm(name, labels) }, name))),
      h('p', { class: 'foot' }, vaultReady ? 'Start from one of these, or use New form.' : 'My info is not available right now.'));
    return;
  }
  const example = form.fields.find((f) => f.secret && f.kind !== 'secret') || null;      // never use a password as the example
  const name = h('input', { type: 'text', value: form.name, 'aria-label': 'Form name', maxlength: '60' });
  name.addEventListener('input', () => { form.name = name.value; renderFormList(); persist(); });
  const del = h('button', { class: 'btn quiet danger small', type: 'button' }, 'Delete form');
  confirmClick(del, 'Click again to delete', () => { vault.forms = vault.forms.filter((f) => f !== form); persist(); renderVault(); });
  const add = h('button', { class: 'btn', type: 'button', onclick: () => { form.fields.push({ id: uid(), label: '', value: '', policy: 'local' }); renderVault(); main.querySelector('.fieldrow:last-child input')?.focus(); } }, 'Add field');
  const addSecret = h('button', { class: 'btn', type: 'button', onclick: () => { form.fields.push({ id: uid(), label: 'Password', value: '', policy: 'local', kind: 'secret' }); ensureNames(); persist(); renderVault(); main.querySelector('.fieldrow:last-child input')?.focus(); } }, 'Add password or secret');
  V.saved = h('span', { id: 'saved' }, '');
  V.siteNote = h('p', {}, '');
  main.replaceChildren(
    h('div', { class: 'titlerow' }, name, del),
    h('p', { class: 'lead' }, 'Fill this in once. Flows use it to complete forms for you. By default the model never sees these values, only the name of the field.'),
    V.siteNote,
    h('div', { class: 'how', 'aria-label': 'How a value is used' },
      h('div', { class: 'box' }, h('small', {}, 'What the model sees'), h('code', {}, example ? `Type <secret:${example.secret}> into “${example.label}”` : 'Type <secret:NAME> into the field')),
      h('div', { class: 'arrow' }, '→'),
      h('div', { class: 'box' }, h('small', {}, 'What Selfbrowse types, on this computer'), h('code', {}, example && example.value ? example.value : 'The value you saved'))),
    h('div', { class: 'panel' }, form.fields.length ? form.fields.map((f) => fieldRow(form, f)) : h('p', { class: 'empty' }, 'No fields yet.')),
    h('div', { class: 'addrow' }, add, addSecret, V.saved),
    h('p', { class: 'foot' }, 'Encrypted with your computer’s keychain. Never uploaded, and never included when you share a flow. Passwords and secrets are masked, never shown to the model, and only revealed after you confirm it is you (Touch ID where available).'));
  updateSiteNote();
}

$('newForm').addEventListener('click', () => addForm('New form', ['']));
