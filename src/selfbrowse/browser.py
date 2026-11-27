"""
A thin synchronous browser wrapper (Playwright, or Patchright for stealth).

Its main job is the page *snapshot*: a short numbered list of what a person could click or
type into right now, e.g. ``#7 link "Add to cart" →/cart``. That list is what the model
reads instead of a screenshot or a raw DOM, which is where most of the token saving comes from.
"""
from __future__ import annotations

import base64
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# ── the in-page scripts ─────────────────────────────────────────────────────────────
# Shared helper, prepended to every script below: collect elements through open shadow roots
# and find what is really on top at a point (also through shadow roots).
_JS_HELPERS = r"""
const deepFromPoint = (x, y) => {
  let t = document.elementFromPoint(x, y);
  for (let i = 0; i < 8 && t && t.shadowRoot; i++) {
    const inner = t.shadowRoot.elementFromPoint(x, y);
    if (!inner || inner === t) break;
    t = inner;
  }
  return t;
};
"""

# Leaf elements with a little text, inside an absolutely or fixed positioned panel, near a point: what a dropdown or
# menu that was just opened looks like when it carries no ARIA roles at all.
_FLOATING_NEAR_JS = r"""
const floatingNear = (near, skip, cap) => {
  const out = [];
  const floating = (el) => {
    for (let p = el; p && p !== document.body; p = p.parentElement) {
      const pos = getComputedStyle(p).position;
      if (pos === 'absolute' || pos === 'fixed') return true;
    }
    return false;
  };
  let n = 0;
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    if (out.length >= cap || ++n > 6000) break;
    if (skip.has(el) || el.children.length) continue;
    const t = (el.innerText || '').trim();
    if (!t || t.length > 60) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (Math.abs(r.top + r.height / 2 - near[1]) > 360 || Math.abs(r.left + r.width / 2 - near[0]) > 420) continue;
    if (el.closest('a,button,h1,h2,h3,label,input,select,textarea,[role="button"],[role="link"]')) continue;
    if (!floating(el)) continue;
    out.push(el);
  }
  return out;
};
"""

# A shortened label ("In a Dark, Dark ...") is often the start of the element's own title attribute.
_UNTRUNCATE_JS = r"""
const untruncate = (t, el) => {
  if (!/(\.\.\.|\u2026)$/.test(t)) return '';
  const head = t.replace(/(\.\.\.|\u2026)$/, '').trim();
  const holder = el.closest && el.closest('[title]');
  const title = holder ? holder.getAttribute('title').replace(/\s+/g, ' ').trim() : '';
  return head && title.length > head.length && title.startsWith(head) ? title : '';
};
"""

# Runs in every page before its own scripts. A page that listens for drop or dragstart tells us which elements
# take part in drag and drop, even when they are plain <div>s with no markup. (Frameworks that listen on the
# page root instead are invisible to this; draggable="true" and ondrop="" attributes are read from the page.)
_DND_WATCH_JS = r"""
(() => {
  if (window.__sb) return;
  const sb = window.__sb = { drop: [], drag: [] };
  const add = (list, el) => { if (el && el.nodeType === 1 && list.length < 300 && !list.includes(el)) list.push(el); };
  const orig = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, ...rest) {
    try {
      if (type === 'drop' || type === 'dragover') add(sb.drop, this);
      else if (type === 'dragstart') add(sb.drag, this);
    } catch (e) {}
    return orig.call(this, type, ...rest);
  };
})();
"""

# The browser's name and brand details, as a page sees them (only on a secure page).
_IDENTITY_JS = r"""
async () => {
  const d = navigator.userAgentData;
  if (!d) return [navigator.userAgent, null];
  const more = await d.getHighEntropyValues(['architecture', 'bitness', 'model', 'platformVersion', 'fullVersionList', 'wow64']);
  return [navigator.userAgent, { brands: d.brands, fullVersionList: more.fullVersionList, platform: d.platform, mobile: d.mobile,
    platformVersion: more.platformVersion, architecture: more.architecture, model: more.model, bitness: more.bitness, wow64: more.wow64 }];
}
"""

# Remember what is on screen now, so what appears after the next click (a dropdown's choices, whatever markup
# it uses) can be told apart from the rest of the page.
_MARK_VISIBLE_JS = r"""
() => {
  const before = new WeakSet();
  let n = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (++n > 6000) break;
    const r = el.getBoundingClientRect();
    if (r.width >= 2 && r.height >= 2 && getComputedStyle(el).display !== 'none') before.add(el);
  }
  window.__sbBefore = before;
  return n;
}
"""

# The choices of the dropdown that is open on the page (custom widgets: role=option / menuitem, list items in a
# listbox or menu, and the popup an aria-expanded control points at). With `want`, pick the one whose text matches,
# scroll it into view and say where it is; otherwise list them.
_POPUP_OPTIONS_JS = "([want, near]) => {" + _JS_HELPERS + _FLOATING_NEAR_JS + r"""
  const norm = s => String(s).replace(/\s+/g, ' ').trim();
  const ROLES = '[role="option"],[role="menuitem"],[role="menuitemradio"],[role="menuitemcheckbox"],[role="treeitem"]';
  const popups = new Set();
  for (const el of document.querySelectorAll('[role="listbox"],[role="menu"],[role="tree"]')) popups.add(el);
  for (const host of document.querySelectorAll('[aria-expanded="true"]')) {
    for (const id of (host.getAttribute('aria-controls') || host.getAttribute('aria-owns') || '').split(/\s+/).filter(Boolean)) {
      const pop = host.getRootNode().getElementById ? host.getRootNode().getElementById(id) : document.getElementById(id);
      if (pop) popups.add(pop);
    }
  }
  const cands = new Set();
  for (const el of document.querySelectorAll(ROLES)) cands.add(el);
  const before = window.__sbBefore;                 // set just before the dropdown was opened: whatever is new is a choice
  if (before) {
    let n = 0;
    for (const el of document.querySelectorAll('body *')) {
      if (++n > 6000) break;
      if (before.has(el) || el.children.length) continue;
      const r = el.getBoundingClientRect();
      if (r.width >= 2 && r.height >= 2) cands.add(el);
    }
  }
  for (const pop of popups) {
    const inner = pop.querySelectorAll(ROLES + ',li');
    if (inner.length) inner.forEach(e => cands.add(e));
    else Array.from(pop.children).forEach(e => cands.add(e));
  }
  if (!before && near) for (const k of floatingNear(near, cands, 40)) cands.add(k);   // already open, no ARIA
  const vh = window.innerHeight, vw = window.innerWidth;
  const seen = new Set(), found = [];
  for (const el of cands) {
    const text = norm(el.innerText || el.textContent || el.getAttribute('aria-label') || '').slice(0, 60);
    if (!text || seen.has(el)) continue;
    seen.add(el);
    let r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    found.push({ el, text, selected: el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-checked') === 'true' });
  }
  const label = f => f.text + (f.selected ? ' (selected)' : '');
  if (want === null) return { options: found.map(label) };
  const w = norm(want).toLowerCase();
  let hit = found.filter(f => f.text.toLowerCase() === w);
  if (hit.length !== 1) hit = hit.length ? hit : found.filter(f => w && f.text.toLowerCase().includes(w));
  if (hit.length !== 1) {
    return { error: hit.length ? 'more than one option matches' : 'no option matches', options: found.map(label) };
  }
  const el = hit[0].el;
  el.scrollIntoView({ block: 'nearest' });
  const r = el.getBoundingClientRect();
  const cx = Math.round(Math.min(Math.max(r.left + r.width / 2, 0), vw - 1));
  const cy = Math.round(Math.min(Math.max(r.top + r.height / 2, 0), vh - 1));
  const top = deepFromPoint(cx, cy);
  if (top && !(el.contains(top) || top.contains(el))) return { error: 'that option is hidden behind something else', options: found.map(label) };
  return { chosen: hit[0].text, cx, cy };
}
"""

_SNAPSHOT_JS = "(arg) => { const maxEls = typeof arg === 'number' ? arg : arg.max; const near = typeof arg === 'object' && arg ? arg.near : null;" + _UNTRUNCATE_JS + _JS_HELPERS + _FLOATING_NEAR_JS + r"""
  const SEL = [
    'a[href]', 'button', 'input:not([type="hidden"])', 'textarea', 'select', 'summary',
    '[role="button"]', '[role="link"]', '[role="textbox"]', '[role="checkbox"]', '[role="radio"]',
    '[role="combobox"]', '[role="option"]', '[role="menuitem"]', '[role="tab"]', '[role="switch"]',
    '[role="slider"]', '[role="menuitemradio"]', '[role="menuitemcheckbox"]', '[role="treeitem"]',
    '[contenteditable=""]', '[contenteditable="true"]', 'h1', 'h2', 'h3',
    '[draggable="true"]', '[ondragstart]', '[ondrop]', '[ondragover]',
  ];
  const sb = window.__sb || { drop: [], drag: [] };
  const seen = new Set(), els = [];
  const collect = (root) => {
    root.querySelectorAll('[data-sb-file]').forEach(e => e.removeAttribute('data-sb-file'));
    for (const sel of SEL) for (const el of root.querySelectorAll(sel)) {
      if (!seen.has(el)) { seen.add(el); els.push(el); }
    }
    for (const host of root.querySelectorAll('*')) if (host.shadowRoot) collect(host.shadowRoot);
  };
  collect(document);
  sb.drop = sb.drop.filter(e => e.isConnected);
  sb.drag = sb.drag.filter(e => e.isConnected);
  for (const el of sb.drop.concat(sb.drag)) if (!seen.has(el)) { seen.add(el); els.push(el); }
  // the choices of an open custom dropdown belong in the list too (the popup an aria-expanded control points at)
  const popupItems = new Set();
  for (const host of Array.from(els)) {
    if (host.getAttribute('aria-expanded') !== 'true') continue;
    for (const id of (host.getAttribute('aria-controls') || host.getAttribute('aria-owns') || '').split(/\s+/).filter(Boolean)) {
      const pop = host.getRootNode().getElementById ? host.getRootNode().getElementById(id) : document.getElementById(id);
      if (!pop) continue;
      const inner = pop.querySelectorAll('[role="option"],[role="menuitem"],[role="treeitem"],li');
      const kids = inner.length ? Array.from(inner) : Array.from(pop.children);
      for (const k of kids.slice(0, 30)) { popupItems.add(k); if (!seen.has(k)) { seen.add(k); els.push(k); } }
    }
  }
  if (near) for (const k of floatingNear(near, seen, 12)) { popupItems.add(k); seen.add(k); els.push(k); }
  const vh = window.innerHeight, vw = window.innerWidth;
  const items = [];
  let fileSeq = 0;
  for (const el of els) {
    if (el.disabled) continue;
    const isFile = el.tagName === 'INPUT' && (el.getAttribute('type') || '').toLowerCase() === 'file';
    let r = el.getBoundingClientRect();
    let st = getComputedStyle(el);
    const shown = r.width >= 2 && r.height >= 2 && st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
    if (isFile && !shown) {                         // file inputs are usually hidden behind a styled button: use their label
      const anchor = el.closest('label') || el.parentElement;
      if (!anchor) continue;
      r = anchor.getBoundingClientRect();
      st = getComputedStyle(anchor);
      if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none') continue;
    }
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
    if (!isFile && (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0')) continue;
    const cx = Math.round(Math.min(Math.max(r.left + r.width / 2, 0), vw - 1));
    const cy = Math.round(Math.min(Math.max(r.top + r.height / 2, 0), vh - 1));
    const top = deepFromPoint(cx, cy);                        // skip anything covered by a modal/overlay
    if (!isFile && top && !(el.contains(top) || top.contains(el))) continue;

    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const draggable = el.getAttribute('draggable') === 'true' || el.hasAttribute('ondragstart') || sb.drag.includes(el);
    const dropTarget = el.hasAttribute('ondrop') || el.hasAttribute('ondragover') || sb.drop.includes(el);
    let role = el.getAttribute('role');
    if (!role) {
      if (isFile) role = 'file';
      else if (popupItems.has(el)) role = 'option';
      else if (tag === 'a') role = 'link';
      else if (tag === 'button' || tag === 'summary') role = 'button';
      else if (tag === 'select') role = 'combobox';
      else if (tag === 'textarea') role = 'textbox';
      else if (/^h[1-3]$/.test(tag)) role = 'heading';
      else if (tag === 'input') role = ['checkbox', 'radio'].includes(type) ? type
        : ['submit', 'button', 'reset', 'image'].includes(type) ? 'button' : 'textbox';
      else if (el.isContentEditable) role = 'textbox';
      else if (draggable) role = 'draggable';
      else if (dropTarget) role = 'dropzone';
      else role = 'textbox';
    }
    const isField = tag === 'input' || tag === 'select' || tag === 'textarea';
    const labelled = isField && el.labels && el.labels[0] ? el.labels[0].innerText : '';
    let text = (el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('placeholder')
      || labelled || (tag === 'select' ? el.getAttribute('name') : (el.innerText || el.value)) || el.textContent
      || el.getAttribute('title') || '')
      .replace(/\s+/g, ' ').trim();
    if (isFile && !text) text = ((el.closest('label') || el.parentElement || {}).innerText || el.getAttribute('name') || '').replace(/\s+/g, ' ').trim();
    text = (untruncate(text, el) || text).slice(0, 80);
    let value = '';
    let options;
    if (tag === 'select') {
      const o = el.selectedOptions && el.selectedOptions[0];
      value = o ? o.text.replace(/\s+/g, ' ').trim().slice(0, 30) : '';
      options = Array.from(el.options).map(x => x.text.replace(/\s+/g, ' ').trim().slice(0, 25));
    } else if ((tag === 'input' || tag === 'textarea') && type !== 'password' && el.value) value = String(el.value).slice(0, 30);
    let href = '';
    if (tag === 'a') {
      try {
        const u = new URL(el.href, location.href);
        href = (u.origin === location.origin ? u.pathname + u.search : '').slice(0, 50);
      } catch (e) {}
    }
    let fileId = null;
    if (isFile) { fileId = ++fileSeq; el.setAttribute('data-sb-file', String(fileId)); }
    const exp = el.getAttribute('aria-expanded');
    items.push({ role, text, type, value, href, cx, cy, y: r.top, x: r.left, options,
                 checked: (type === 'checkbox' || type === 'radio') ? !!el.checked : null,
                 focused: document.activeElement === el,
                 file: isFile, fileId, accept: isFile ? (el.getAttribute('accept') || '').slice(0, 30) : '',
                 multiple: isFile && el.multiple, drag: draggable, drop: dropTarget,
                 expanded: exp === 'true' ? true : exp === 'false' ? false : null,
                 selected: el.getAttribute('aria-selected') === 'true' });
  }
  items.sort((a, b) => (Math.abs(a.y - b.y) > 10 ? a.y - b.y : a.x - b.x));
  const total = items.length;
  const doc = document.documentElement;
  const sh = Math.max(doc.scrollHeight, 1);
  return {
    items: items.slice(0, maxEls), total, vw, vh,
    top: Math.round(100 * window.scrollY / sh),
    bottom: Math.min(100, Math.round(100 * (window.scrollY + vh) / sh)),
  };
}
"""

_VISIBLE_TEXT_JS = _UNTRUNCATE_JS + r"""
(arg) => {
  const maxChars = typeof arg === 'number' ? arg : arg.max, whole = typeof arg === 'object' && !!arg.whole;
  const vh = window.innerHeight, vw = window.innerWidth;
  const out = []; let last = null, len = 0;
  const visit = (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      if (len > maxChars) return;
      const n = walker.currentNode;
      if (n.nodeType === 1) { if (n.shadowRoot) visit(n.shadowRoot); continue; }
      let t = n.nodeValue.replace(/\s+/g, ' ').trim();
      if (!t) continue;
      const p = n.parentElement || (n.parentNode && n.parentNode.host);
      if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName)) continue;
      const range = document.createRange(); range.selectNodeContents(n);
      const r = range.getBoundingClientRect();
      if (r.width < 1 || r.height < 1 || r.right < 0 || r.left > vw) continue;
      if (!whole && (r.bottom < 0 || r.top > vh)) continue;
      const full = untruncate(t, p);
      if (full) t = full;
      const st = getComputedStyle(p);
      if (st.visibility === 'hidden' || st.display === 'none') continue;
      out.push(p === last ? ' ' + t : '\n' + t); last = p; len += t.length + 1;
    }
  };
  if (document.body) visit(document.body);
  return out.join('').trim().slice(0, maxChars);
}
"""

# Pick an option of the native <select> under (x, y) by its visible text or value.
_SELECT_JS = "([x, y, want]) => {" + _JS_HELPERS + r"""
  let el = deepFromPoint(x, y);
  el = el && (el.tagName === 'SELECT' ? el : el.closest && el.closest('select'));
  if (!el) return { error: 'no dropdown at that spot' };
  const norm = s => String(s).replace(/\s+/g, ' ').trim().toLowerCase();
  const w = norm(want);
  const opts = Array.from(el.options).filter(o => !o.disabled);
  let hit = opts.filter(o => norm(o.text) === w || norm(o.value) === w);
  if (hit.length !== 1) hit = hit.length ? hit : opts.filter(o => w && norm(o.text).includes(w));
  if (hit.length !== 1) {
    return { error: hit.length ? 'more than one option matches' : 'no option matches',
             options: opts.map(o => o.text.replace(/\s+/g, ' ').trim()) };
  }
  hit[0].selected = true;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { chosen: hit[0].text.replace(/\s+/g, ' ').trim() };
}
"""

# Find visible text (case-insensitive), through shadow roots. skip < 0 counts only; otherwise it
# scrolls the match numbered `skip` into view.
_FIND_JS = r"""
([needle, skip]) => {
  // Match against the page's text as a reader sees it, not one text node at a time: a label such as
  // "First appeared" is often split by inline markup (<span>&nbsp;</span>, <b>, <a>) into several nodes.
  const norm = s => String(s).replace(/\s+/g, ' ').trim().toLowerCase();
  const n = norm(needle);
  let buf = '';
  const starts = [], nodes = [];                       // where each node's text begins in buf
  const blockOf = new Map();
  const block = (el) => {
    if (blockOf.has(el)) return blockOf.get(el);
    let b = el;
    while (b && b.parentElement && /^(inline|contents)$/.test(getComputedStyle(b).display)) b = b.parentElement;
    blockOf.set(el, b);
    return b;
  };
  let lastBlock = null;
  const visit = (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.nodeType === 1) { if (node.shadowRoot) visit(node.shadowRoot); continue; }
      const p = node.parentElement || (node.parentNode && node.parentNode.host);
      if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName)) continue;
      if (!p.getClientRects().length || getComputedStyle(p).visibility === 'hidden') { lastBlock = null; continue; }
      let t = node.nodeValue.replace(/\s+/g, ' ');
      if (!t) continue;
      const b = block(p);
      if (b !== lastBlock && buf && !buf.endsWith('\n')) buf += '\n';   // a block boundary ends a phrase
      if (buf.endsWith(' ') && t.startsWith(' ')) t = t.slice(1);
      if (!t) continue;
      starts.push(buf.length); nodes.push(node);
      buf += t;
      lastBlock = b;
    }
  };
  if (document.body && n) visit(document.body);
  const low = buf.toLowerCase();
  const found = [];
  if (n) for (let i = low.indexOf(n); i >= 0; i = low.indexOf(n, i + n.length)) found.push(i);
  if (skip < 0 || skip >= found.length) return { count: found.length };
  const at = found[skip];
  let k = starts.length - 1;
  while (k > 0 && starts[k] > at) k--;
  const node = nodes[k], p = node.parentElement || node.parentNode.host;
  p.scrollIntoView({ block: 'center', inline: 'nearest' });
  return { count: found.length, snippet: buf.slice(Math.max(0, at - 50), at + n.length + 70).replace(/\n+/g, ' ').replace(/ +/g, ' ').trim() };
}
"""


_KEY_ALIASES = {
    "down": "ArrowDown", "up": "ArrowUp", "left": "ArrowLeft", "right": "ArrowRight",
    "arrowdown": "ArrowDown", "arrowup": "ArrowUp", "arrowleft": "ArrowLeft", "arrowright": "ArrowRight",
    "return": "Enter", "enter": "Enter", "esc": "Escape", "escape": "Escape", "tab": "Tab",
    "space": " ", "spacebar": " ", "backspace": "Backspace", "delete": "Delete", "del": "Delete",
    "pageup": "PageUp", "pagedown": "PageDown", "page up": "PageUp", "page down": "PageDown",
    "home": "Home", "end": "End",
    "ctrl": "Control", "control": "Control", "cmd": "Meta", "command": "Meta", "meta": "Meta",
    "option": "Alt", "alt": "Alt", "shift": "Shift",
}


def normalize_key(key: str) -> str:
    """Accept the names models actually use ("Down", "Return", "ctrl+a") and give Playwright its own."""
    key = (key or "").strip()
    if len(key) > 1 and "+" in key.strip("+"):
        return "+".join(normalize_key(part) for part in key.split("+"))
    return _KEY_ALIASES.get(key.lower(), key)


# Names Playwright accepts for BrowserContext.grant_permissions.
PERMISSIONS = frozenset({
    "geolocation", "notifications", "camera", "microphone", "clipboard-read", "clipboard-write",
    "midi", "midi-sysex", "payment-handler", "background-sync", "accelerometer", "gyroscope",
    "magnetometer", "ambient-light-sensor", "accessibility-events", "storage-access",
})
DIALOG_POLICIES = ("auto", "accept", "dismiss")


def dialog_note(dialogs: "list[dict[str, Any]]") -> str:
    """One line per JavaScript dialog, for the model."""
    lines = []
    for d in dialogs:
        why = " (a guardrail stopped it being accepted)" if d.get("vetoed") else ""
        lines.append(f'\n[A {d["type"]} dialog appeared: "{d["message"]}". It was {d["action"]}{why}.]')
    return "".join(lines)


class BrowserError(RuntimeError):
    pass


@dataclass
class Snapshot:
    text: str                                   # what the model reads
    elements: list[dict[str, Any]] = field(default_factory=list)
    url: str = ""
    title: str = ""


class Browser:
    """
    Args:
        headless: run without a visible window.
        channel: ``"chrome"`` / ``"msedge"`` to use an installed browser. By default the bundled
            Chromium is tried first, then installed Chrome.
        executable_path: path to a specific browser binary.
        user_data_dir: keep cookies and logins between runs in this folder.
        viewport: (width, height).
        args: extra command-line flags for the browser (for example ``["--window-position=-2400,-2400"]``).
        stealth: use Patchright (``pip install selfbrowse[stealth]``) to hide common automation tells.
        record_video_dir: folder to record a video of each page (WebM, at the viewport size). The files are
            finished when the browser closes; :meth:`video_paths` lists them. Shows the page, not the window.
        cdp_url: attach to a browser that is already running and exposes the Chrome DevTools Protocol
            (``wss://...`` from a cloud provider, or ``http://localhost:9222`` for a local Chrome started
            with ``--remote-debugging-port``) instead of launching one. Selfbrowse uses the browser's
            first tab and leaves the browser running when it closes.
        cdp_headers: extra headers for the CDP connection (provider auth).
        cloud: a provider from :mod:`selfbrowse.cloud` (for example ``AgentCoreBrowser()``) that starts a
            remote browser session and returns where to connect; the session is stopped on close.
            Remote browsers cannot record video or use a profile folder, and ``viewport`` is theirs to set.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        channel: str | None = None,
        executable_path: str | None = None,
        user_data_dir: str | Path | None = None,
        viewport: tuple[int, int] = (1280, 800),
        stealth: bool = False,
        args: "list[str] | None" = None,
        screenshot_quality: int = 60,
        timeout_ms: int = 15000,
        max_elements: int = 120,
        permissions: "list[str] | None" = None,
        dialogs: str = "auto",
        record_video_dir: "str | Path | None" = None,
        cdp_url: str | None = None,
        cdp_headers: "dict[str, str] | None" = None,
        cloud: Any = None,
    ) -> None:
        if cdp_url and cloud:
            raise BrowserError("Pass either cdp_url or cloud, not both.")
        if cdp_url or cloud:
            for what, given in (("record_video_dir", record_video_dir), ("user_data_dir", user_data_dir),
                                ("executable_path", executable_path), ("channel", channel)):
                if given:
                    raise BrowserError(f"{what} does not apply to a remote browser (the provider runs it).")
        self.cdp_url = cdp_url
        self.cdp_headers = dict(cdp_headers or {})
        self.cloud = cloud
        self.live_view_url: str | None = None
        bad = [p for p in (permissions or []) if p not in PERMISSIONS]
        if bad:
            raise BrowserError(f"Unknown permission {bad[0]!r}. Choose from: {', '.join(sorted(PERMISSIONS))}.")
        if dialogs not in DIALOG_POLICIES:
            raise BrowserError(f"dialogs must be one of: {', '.join(DIALOG_POLICIES)}.")
        self.permissions = list(permissions or [])
        self.dialogs = dialogs
        self.record_video_dir = Path(record_video_dir).expanduser() if record_video_dir else None
        self._videos: list[Any] = []
        self.on_dialog: "Callable[[dict[str, Any]], bool | None] | None" = None   # may veto accepting
        self._nav_check: "Callable[[str], tuple[str, str] | None] | None" = None
        self._refused: list[tuple[str, str, str]] = []     # navigations stopped before any request was made
        self._dialog_log: list[dict[str, Any]] = []
        self.headless = headless
        self.channel = channel
        self.executable_path = executable_path
        self.user_data_dir = Path(user_data_dir).expanduser() if user_data_dir else None
        self.viewport = viewport
        self.stealth = stealth
        self.args = list(args or [])
        self.screenshot_quality = max(10, min(95, screenshot_quality))
        self.timeout_ms = timeout_ms
        self.max_elements = max_elements
        self._pw = self._browser = self._context = self._page = None
        self._elements: list[dict[str, Any]] = []
        self._click_point: tuple[str, int, int] | None = None   # (url, x, y) of the last click: where a dropdown may have opened
        self._frames: list[Any] = []                    # frames the latest snapshot read; el["frame"] indexes this

    # ── lifecycle ──────────────────────────────────────────────────────────────────
    def start(self) -> "Browser":
        if self._page is not None:
            return self
        if self.stealth:
            try:
                from patchright.sync_api import sync_playwright
            except ImportError as exc:
                raise BrowserError("stealth=True needs Patchright: pip install 'selfbrowse[stealth]'") from exc
        else:
            from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        chromium = self._pw.chromium
        if self.cdp_url or self.cloud:
            self._connect_remote(chromium)
            return self._finish_start()
        ctx_kwargs: dict[str, Any] = {"viewport": {"width": self.viewport[0], "height": self.viewport[1]}}
        if self.record_video_dir:
            self.record_video_dir.mkdir(parents=True, exist_ok=True)
            ctx_kwargs["record_video_dir"] = str(self.record_video_dir)
            ctx_kwargs["record_video_size"] = {"width": self.viewport[0], "height": self.viewport[1]}
        last: Exception | None = None
        for channel in ([self.channel] if self.channel else [None, "chrome"]):
            kwargs: dict[str, Any] = {"headless": self.headless}
            if self.args:
                kwargs["args"] = self.args
            if channel:
                kwargs["channel"] = channel
            if self.executable_path:
                kwargs["executable_path"] = self.executable_path
            try:
                if self.user_data_dir:
                    self.user_data_dir.mkdir(parents=True, exist_ok=True)
                    self._context = chromium.launch_persistent_context(str(self.user_data_dir), **kwargs, **ctx_kwargs)
                else:
                    self._browser = chromium.launch(**kwargs)
                    self._context = self._browser.new_context(**ctx_kwargs)
                break
            except Exception as exc:                    # try the next channel
                last = exc
        else:
            self._pw.stop()
            self._pw = None
            raise BrowserError(
                "Could not start a browser. Install one with `playwright install chromium`, "
                f"or install Google Chrome. Last error: {last}"
            )

        return self._finish_start()

    def _connect_remote(self, chromium: Any) -> None:
        """Attach to a CDP endpoint, starting a cloud session first if there is a provider."""
        url, headers = self.cdp_url, self.cdp_headers
        try:
            if self.cloud:
                target = self.cloud.open()
                url, headers, self.live_view_url = target.url, {**target.headers, **headers}, target.live_view_url
            self._browser = chromium.connect_over_cdp(url, headers=headers or None, timeout=30000)
        except Exception as exc:
            self.close()
            raise BrowserError(f"Could not connect to the remote browser: {exc}") from exc
        # the provider's browser comes with a context (and usually a tab); a bare one may not
        self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()

    def _finish_start(self) -> "Browser":
        if self.permissions:
            try:
                self._context.grant_permissions(self.permissions)
            except Exception as exc:
                self.close()
                raise BrowserError(f"Could not grant permissions {self.permissions}: {exc}") from exc
        self._watched: set[int] = set()
        try:                                           # learn which elements take part in drag and drop
            self._context.add_init_script(_DND_WATCH_JS)
        except Exception:
            pass
        self._identity = self._read_identity()         # before the listener: its temporary tab is not "the page"
        self._context.on("page", self._on_new_page)    # follow links that open a new tab
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        self._watch_dialogs(self._page)                # new_page() may already have fired the event above
        self._unmask_headless(self._page)
        return self

    def refuse_navigations(self, check: "Callable[[str], tuple[str, str] | None]") -> None:
        """Stop page navigations (clicks, form posts, redirects, frames) to places ``check`` refuses, before the request
        is made. ``check(url)`` returns ``(who, reason)`` to refuse. Without this a click is only judged after the page has
        loaded, by which time the site has already received the request and anything in it. Turns off Chromium's HTTP
        cache for the context, because Playwright does that while it intercepts requests."""
        self._nav_check = check
        if not getattr(self, "_routed", False):
            self._routed = True
            self._context.route("**/*", self._route)

    def _route(self, route: Any) -> None:
        try:
            req = route.request
            if self._nav_check and req.is_navigation_request() and (hit := self._nav_check(req.url)):
                self._refused.append((hit[0], hit[1], req.url))
                route.abort("blockedbyclient")
                return
        except Exception:
            pass
        try:
            route.continue_()
        except Exception:
            pass

    def take_refused(self) -> list[tuple[str, str, str]]:
        """Navigations refused since the last call, as ``(guardrail, reason, url)``."""
        out, self._refused = self._refused, []
        return out

    def video_paths(self) -> list[Path]:
        """Video files recorded so far, one per page (complete once the browser has closed)."""
        return [p for p in self._videos if p]

    def close(self) -> None:
        self._videos = []
        for page in self._open_pages() if self.record_video_dir else []:
            try:
                if page.video:
                    self._videos.append(Path(page.video.path()))
            except Exception:
                pass
        remote = bool(self.cdp_url or self.cloud)
        # a remote browser's own context is not ours to close; closing the connection is enough
        for obj in ((self._browser,) if remote else (self._context, self._browser)):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        if self.cloud:
            try:
                self.cloud.close()
            except Exception:
                pass
        self._pw = self._browser = self._context = self._page = None

    def __enter__(self) -> "Browser":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _on_new_page(self, page: Any) -> None:
        self._page = page
        page.set_default_timeout(self.timeout_ms)
        self._watch_dialogs(page)
        self._unmask_headless(page)

    def _read_identity(self) -> dict[str, Any] | None:
        """For stealth in headless mode: what to report instead of "HeadlessChrome", or None to change nothing.

        Overriding the user agent alone makes Chrome stop sending the ``sec-ch-ua`` headers and empties
        ``navigator.userAgentData``, so the brand details are read here and given back with the new name. They are
        only visible to a secure page, so a temporary tab is opened on an address that is answered locally."""
        if not (self.stealth and self.headless):
            return None
        page = None
        try:
            page = self._context.new_page()
            page.route("**/*", lambda route: route.fulfill(content_type="text/html", body=""))   # never leaves this computer
            page.goto("https://identity.selfbrowse.invalid/")
            ua, data = page.evaluate(_IDENTITY_JS)
        except Exception:
            return None                                # better to leave the name as it is than to send half of it
        finally:
            if page is not None:
                try:
                    page.close()
                    if self.record_video_dir and page.video:
                        page.video.delete()
                except Exception:
                    pass
        if "HeadlessChrome" not in ua or not data or not data.get("brands"):
            return None
        for key in ("brands", "fullVersionList"):
            seen: dict[str, dict[str, str]] = {}
            for brand in data.get(key) or []:
                name = "Chromium" if brand["brand"] == "HeadlessChrome" else brand["brand"]
                seen.setdefault(name, {"brand": name, "version": brand["version"]})
            data[key] = list(seen.values())
        return {"userAgent": ua.replace("HeadlessChrome", "Chrome"), "userAgentMetadata": data}

    def _unmask_headless(self, page: Any) -> None:
        """Headless Chrome says "HeadlessChrome" in its user agent, which is the first thing bot checks read.
        With stealth on, report plain "Chrome" instead, with the browser's own version and brand details."""
        if not self._identity:
            return
        try:
            self._context.new_cdp_session(page).send("Emulation.setUserAgentOverride", self._identity)
        except Exception:
            pass                                       # best effort: a page that cannot be patched still works

    def _watch_dialogs(self, page: Any) -> None:
        """Listen for dialogs on this page, once. A second listener would record every dialog twice."""
        if id(page) not in self._watched:
            self._watched.add(id(page))
            page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog: Any) -> None:
        """alert / confirm / prompt / beforeunload. Record it, then accept or dismiss per policy."""
        kind = dialog.type
        info: dict[str, Any] = {"type": kind, "message": (dialog.message or "")[:300]}
        if self.dialogs == "accept":
            accept = True
        elif self.dialogs == "dismiss":
            accept = False
        else:                                           # auto: harmless ones go through, choices are declined
            accept = kind in ("alert", "beforeunload")
        if accept and self.on_dialog:
            try:
                if self.on_dialog(dict(info)) is False:
                    accept = False
                    info["vetoed"] = True
            except Exception:
                accept = False
        info["action"] = "accepted" if accept else "dismissed"
        self._dialog_log.append(info)
        try:
            dialog.accept() if accept else dialog.dismiss()
        except Exception:
            pass

    def pop_dialogs(self) -> list[dict[str, Any]]:
        """Dialogs that appeared since the last call (and what was done with them)."""
        out, self._dialog_log = self._dialog_log, []
        return out

    @property
    def page(self) -> Any:
        if self._page is None:
            raise BrowserError("Browser is not started. Use `with Browser() as b:` or call .start().")
        if self._page.is_closed():                      # a popup closed itself: fall back to an open tab
            open_pages = [p for p in self._context.pages if not p.is_closed()]
            if not open_pages:
                raise BrowserError("All browser tabs are closed.")
            self._page = open_pages[-1]
        return self._page

    # ── state ──────────────────────────────────────────────────────────────────────
    @property
    def url(self) -> str:
        return self.page.url

    @property
    def title(self) -> str:
        try:
            return self.page.title()
        except Exception:
            return ""

    def snapshot(self) -> Snapshot:
        """Numbered list of what is clickable or typeable in the current viewport (frames and shadow DOM included)."""
        near = self._click_point if self._click_point and self._click_point[0] == self.page.url else None
        data = self._eval(_SNAPSHOT_JS, {"max": self.max_elements, "near": list(near[1:])} if near else self.max_elements)
        page = self.page
        items = [dict(i, frame=0, lx=i["cx"], ly=i["cy"]) for i in data["items"]]
        total = data["total"]
        self._frames = [page.main_frame]
        for frame, ox, oy, box in self._child_frames(data["vw"], data["vh"]):
            sub = self._eval_in(frame, _SNAPSHOT_JS, self.max_elements)
            if not sub:
                continue
            idx = len(self._frames)
            self._frames.append(frame)
            total += sub["total"]
            for it in sub["items"]:
                gx, gy = it["cx"] + ox, it["cy"] + oy
                inside = (box["x"] <= gx <= box["x"] + box["width"] and box["y"] <= gy <= box["y"] + box["height"]
                          and 0 <= gx < data["vw"] and 0 <= gy < data["vh"])
                if not inside:
                    total -= 1
                    continue
                items.append(dict(it, frame=idx, lx=it["cx"], ly=it["cy"], cx=round(gx), cy=round(gy),
                                  x=it["x"] + ox, y=it["y"] + oy))
        if len(self._frames) > 1:
            items.sort(key=lambda a: (a["y"] // 10, a["x"]))   # frames' elements slot into reading order
        items = items[: self.max_elements]
        self._elements = []
        lines = [f'[{self.title[:80]!r} | {page.url}]']
        tabs = self.tab_summary()
        if tabs:
            lines.append(tabs)
        lines.append(f'[viewport shows {data["top"]}–{data["bottom"]}% of the page]')
        for ref, el in enumerate(items, 1):
            el = dict(el, ref=ref)
            self._elements.append(el)
            extras = []
            if el.get("focused"):
                extras.append("focused")
            if el.get("value"):
                extras.append(f'value="{el["value"]}"')
            if el.get("options"):
                opts = el["options"]
                shown = " | ".join(opts[:12]) + (f" | …+{len(opts) - 12}" if len(opts) > 12 else "")
                extras.append(f"options: {shown}")
            if el.get("checked") is True:
                extras.append("checked")
            elif el.get("checked") is False:
                extras.append("unchecked")
            if el.get("expanded") is True:
                extras.append("open")
            elif el.get("expanded") is False:
                extras.append("closed")
            if el.get("selected"):
                extras.append("selected")
            if el.get("file"):
                if el.get("accept"):
                    extras.append(f'accepts {el["accept"]}')
                if el.get("multiple"):
                    extras.append("several files")
            if el.get("drag") and el["role"] != "draggable":
                extras.append("draggable")
            if el.get("drop") and el["role"] != "dropzone":
                extras.append("drop target")
            if el.get("type") and el["type"] not in ("text", "submit", "button", "checkbox", "radio", "file", ""):
                extras.append(f'type={el["type"]}')
            if el.get("href"):
                extras.append(f'→{el["href"]}')
            label = f'"{el["text"]}"' if el["text"] else "(no label)"
            lines.append(f'#{ref} {el["role"]} {label}' + (f' ({", ".join(extras)})' if extras else ""))
        hidden = total - len(items)
        if hidden > 0:
            lines.append(f"[+{hidden} more elements in view not shown]")
        if not items:
            lines.append("[no interactive elements found — try screenshot, scroll or wait]")
        return Snapshot("\n".join(lines), list(self._elements), page.url, self.title)

    def _child_frames(self, vw: int, vh: int, limit: int = 8) -> list[tuple[Any, float, float, dict[str, float]]]:
        """Visible iframes as (frame, content-left, content-top, box), positions relative to the main viewport."""
        found = []
        for frame in self.page.frames[1:]:
            if len(found) >= limit:
                break
            try:
                if frame.is_detached():
                    continue
                handle = frame.frame_element()
                box = handle.bounding_box()
                if not box or box["width"] < 10 or box["height"] < 10:
                    continue
                if box["x"] + box["width"] < 0 or box["y"] + box["height"] < 0 or box["x"] > vw or box["y"] > vh:
                    continue
                inset = handle.evaluate(
                    "el => { const cs = getComputedStyle(el);"
                    " return [el.clientLeft + parseFloat(cs.paddingLeft || 0), el.clientTop + parseFloat(cs.paddingTop || 0)]; }")
            except Exception:
                continue
            found.append((frame, box["x"] + inset[0], box["y"] + inset[1], box))
        return found

    def _eval_in(self, frame: Any, script: str, arg: Any) -> Any:
        """evaluate inside one frame; None if the frame is gone or still loading."""
        try:
            return frame.evaluate(script, arg)
        except Exception:
            return None

    # ── tabs ────────────────────────────────────────────────────────────────────────
    def _open_pages(self) -> list[Any]:
        return [p for p in self._context.pages if not p.is_closed()] if self._context else []

    def tab_summary(self) -> str:
        """One line naming the open tabs, or '' when there is only one."""
        pages = self._open_pages()
        if len(pages) < 2:
            return ""
        current = self.page
        parts = []
        for i, p in enumerate(pages, 1):
            try:
                title = p.title()[:30] or p.url[:30]
            except Exception:
                title = "(loading)"
            parts.append(f'{i} "{title}"' + (" (current)" if p is current else ""))
        return "[tabs: " + " · ".join(parts) + "]"

    def switch_tab(self, index: int) -> str:
        pages = self._open_pages()
        if not 1 <= index <= len(pages):
            raise BrowserError(f"No tab {index}; there are {len(pages)} open tab(s).")
        self._page = pages[index - 1]
        self.bring_to_front()
        self._settle()
        return f'switched to tab {index} "{self.title[:40]}"'

    def close_tab(self, index: int | None = None) -> str:
        pages = self._open_pages()
        if len(pages) < 2:
            raise BrowserError("That is the only open tab; it cannot be closed.")
        target = self.page if index is None else (pages[index - 1] if 1 <= index <= len(pages) else None)
        if target is None:
            raise BrowserError(f"No tab {index}; there are {len(pages)} open tab(s).")
        was_current = target is self.page
        opener = None
        try:
            opener = target.opener()
        except Exception:
            pass
        pos = pages.index(target)
        target.close()
        if was_current:
            left = self._open_pages()
            self._page = opener if opener in left else left[max(0, min(pos - 1, len(left) - 1))]
            self.bring_to_front()
            self._settle()
        return f"closed tab {pos + 1}; now on \"{self.title[:40]}\""

    def visible_text(self, max_chars: int = 3000, whole: bool = False) -> str:
        """The text currently on screen (not just the clickable parts), iframes included.

        whole=True reads the entire page, not only the part in view (still limited to max_chars)."""
        arg: Any = {"max": max_chars, "whole": True} if whole else max_chars
        text = self._eval(_VISIBLE_TEXT_JS, arg)
        if len(self.page.frames) > 1 and len(text) < max_chars:
            vw, vh = self.viewport
            for frame, _, _, _ in self._child_frames(vw, vh):
                extra = self._eval_in(frame, _VISIBLE_TEXT_JS, ({"max": max_chars - len(text), "whole": True} if whole else max_chars - len(text)))
                if extra:
                    text = (text + "\n" + extra).strip()
                if len(text) >= max_chars:
                    break
        return text[:max_chars]

    def _eval(self, script: str, arg: Any) -> Any:
        """page.evaluate that survives the page navigating underneath it."""
        last: Exception | None = None
        for _ in range(4):
            try:
                return self.page.evaluate(script, arg)
            except Exception as exc:
                msg = str(exc)
                if "context was destroyed" not in msg and "Target closed" not in msg and "navigating" not in msg:
                    raise
                last = exc
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                self.page.wait_for_timeout(500)
        raise BrowserError(f"page kept navigating: {last}")

    def describe_ref(self, ref: int) -> dict[str, str] | None:
        el = self._el(ref)
        return {"role": el["role"], "text": el["text"]} if el else None

    def resolve_ref(self, role: str, text: str) -> int | None:
        """Re-find an element by role+text on a fresh snapshot; None if missing or ambiguous."""
        self.snapshot()
        role, text = (role or "").strip().lower(), (text or "").strip().lower()
        same = [e for e in self._elements if e["role"].lower() == role]
        exact = [e for e in same if e["text"].strip().lower() == text]
        if len(exact) == 1:
            return exact[0]["ref"]
        part = [e for e in same if text and text in e["text"].lower()]
        return part[0]["ref"] if len(part) == 1 else None

    def locate_ref(self, ref: int) -> dict[str, Any] | None:
        """Describe element #ref well enough to find it again: role, text, and which of the identical ones it is."""
        el = self._el(ref)
        if el is None:
            return None
        text = el["text"].strip().lower()
        twins = [e for e in self._elements if e["role"] == el["role"] and e["text"].strip().lower() == text]
        return {"role": el["role"], "text": el["text"], "nth": twins.index(el) if el in twins else 0, "of": len(twins)}

    def find_ref(self, role: str, text: str, nth: int = 0, of: int = 1) -> int | None:
        """Re-find an element on a fresh snapshot. Uses the exact label; falls back to a unique partial match.

        When the page lists as many identical elements as were seen when recording, ``nth`` picks the same one.
        Returns None if it cannot tell which element is meant.
        """
        self.snapshot()
        role, text = (role or "").strip().lower(), (text or "").strip().lower()
        same = [e for e in self._elements if e["role"].lower() == role]
        exact = [e for e in same if e["text"].strip().lower() == text]
        if len(exact) == 1:
            return exact[0]["ref"]
        if exact and len(exact) == of and 0 <= nth < len(exact):
            return exact[nth]["ref"]
        if exact:
            return None
        part = [e for e in same if text and text in e["text"].lower()]
        return part[0]["ref"] if len(part) == 1 else None

    def _el(self, ref: int) -> dict[str, Any] | None:
        return next((e for e in self._elements if e["ref"] == ref), None)

    # ── actions ────────────────────────────────────────────────────────────────────
    def goto(self, url: str) -> str:
        if "://" not in url:
            url = "https://" + url
        self.page.goto(url, wait_until="domcontentloaded")
        self._settle()
        return self.page.url

    def click_ref(self, ref: int) -> str:
        el = self._el(ref)
        if el is None:
            raise BrowserError(f"No element #{ref} in the latest page list; refs change after every page change.")
        self.page.mouse.click(el["cx"], el["cy"])
        self._click_point = (self.page.url, el["cx"], el["cy"])     # a dropdown opened by this click lists its choices next
        self._settle()
        return f'clicked #{ref} {el["role"]} "{el["text"][:40]}"'

    def click_at(self, x: int, y: int) -> str:
        self.page.mouse.click(x, y)
        self._settle()
        return f"clicked at ({x}, {y})"

    def select_ref(self, ref: int, option: str) -> str:
        """Choose an option of the native dropdown #ref by its text or value."""
        el = self._el(ref)
        if el is None:
            raise BrowserError(f"No element #{ref} in the latest page list; refs change after every page change.")
        if not el.get("options"):
            return self._select_custom(ref, el, option)
        frame = self._frames[el.get("frame", 0)] if self._frames else self.page.main_frame
        res = self._eval_in(frame, _SELECT_JS, [el["lx"], el["ly"], option])
        if not res:
            raise BrowserError("the page changed before the option could be chosen; read the new list and try again")
        if res.get("error"):
            opts = " | ".join(res.get("options", [])[:12])
            raise BrowserError(f'{res["error"]} for "{option}". Options: {opts}')
        self._settle()
        return f'selected "{res["chosen"]}" in #{ref}'

    def _frame_of(self, el: dict[str, Any]) -> Any:
        return self._frames[el.get("frame", 0)] if self._frames else self.page.main_frame

    def _select_custom(self, ref: int, el: dict[str, Any], option: str) -> str:
        """Choose from a dropdown built from page elements: open it if it is not open, find the option, click it."""
        if el["role"] not in ("combobox", "button", "textbox", "listbox"):
            raise BrowserError(f"#{ref} is not a dropdown. Click it, then click the option you want.")
        frame = self._frame_of(el)
        dx, dy = el["cx"] - el["lx"], el["cy"] - el["ly"]        # where this frame sits on the page
        res = self._eval_in(frame, _POPUP_OPTIONS_JS, [option, [el["lx"], el["ly"]]]) or {}
        opened = False
        if "chosen" not in res and not res.get("options") and el.get("expanded") is not True:
            opened = True
            self._eval_in(frame, _MARK_VISIBLE_JS, None)            # so the choices can be told from the rest of the page
            self.page.mouse.click(el["cx"], el["cy"])              # nothing is showing: open it, then look again
            self.page.wait_for_timeout(350)
            res = self._eval_in(frame, _POPUP_OPTIONS_JS, [option, [el["lx"], el["ly"]]]) or {}
        self._eval_in(frame, "() => { window.__sbBefore = null; }", None)
        if res.get("error"):
            opts = " | ".join(res.get("options", [])[:12])
            if opts:
                where = f" Options: {opts}"
            elif opened:
                where = f" I opened #{ref} but no choices appeared: read the page and click the option by its number if it is listed."
            else:
                where = f" No options are showing: click #{ref} to open it, or type to filter."
            raise BrowserError(f'{res["error"]} for "{option}".{where}')
        if "chosen" not in res:
            raise BrowserError("the page changed before the option could be chosen; read the new list and try again")
        self.page.mouse.click(res["cx"] + dx, res["cy"] + dy)
        self._click_point = None
        self._settle()
        return f'selected "{res["chosen"]}" in #{ref}'

    def upload_ref(self, ref: int, path: str) -> str:
        """Attach a local file to the file input #ref, or to the button that opens a file picker."""
        el = self._el(ref)
        if el is None:
            raise BrowserError(f"No element #{ref} in the latest page list; refs change after every page change.")
        name = Path(path).name
        if el.get("file"):
            frame = self._frame_of(el)
            try:
                frame.locator(f'[data-sb-file="{el["fileId"]}"]').first.set_input_files(path, timeout=8000)
            except Exception as exc:
                raise BrowserError(f"could not attach {name} to #{ref}: {str(exc).splitlines()[0][:120]}") from None
        else:
            try:
                with self.page.expect_file_chooser(timeout=4000) as chooser:
                    self.page.mouse.click(el["cx"], el["cy"])
                chooser.value.set_files(path)
            except Exception:
                raise BrowserError(f'#{ref} "{el["text"][:40]}" did not open a file picker. '
                                   "Use a control with the role file, or the button that says upload or choose file.") from None
        self.page.wait_for_timeout(300)
        self._settle()
        return f'attached "{name}" to #{ref} "{el["text"][:40]}"'

    def has_drag_targets(self) -> bool:
        """Does the latest page list contain something to drag or drop onto?"""
        return any(e.get("drag") or e.get("drop") for e in self._elements)

    def drag_ref(self, ref: int, to_ref: int) -> str:
        """Press on #ref, move to #to_ref and let go (mouse events, so HTML5 and script-driven drag and drop both run)."""
        a, b = self._el(ref), self._el(to_ref)
        for r, e in ((ref, a), (to_ref, b)):
            if e is None:
                raise BrowserError(f"No element #{r} in the latest page list; refs change after every page change.")
        if ref == to_ref:
            raise BrowserError("drag needs two different elements: the one to pick up and the one to drop it on.")
        m = self.page.mouse
        m.move(a["cx"], a["cy"])
        m.down()
        m.move(a["cx"] + 8, a["cy"] + 8, steps=3)                    # a first small move starts the drag
        m.move(b["cx"], b["cy"], steps=18)
        self.page.wait_for_timeout(150)
        m.up()
        self.page.wait_for_timeout(200)
        self._settle()
        return f'dragged #{ref} "{a["text"][:30]}" onto #{to_ref} "{b["text"][:30]}"'

    def find_text(self, text: str, nth: int = 1) -> str:
        """Scroll the nth on-page match of ``text`` into view and say what is around it."""
        nth = max(1, int(nth))
        frames = [self.page.main_frame] + [f for f, *_ in self._child_frames(*self.viewport)]
        counts = [(f, (self._eval_in(f, _FIND_JS, [text, -1]) or {}).get("count", 0)) for f in frames]
        total = sum(c for _, c in counts)
        if total == 0:
            return f'"{text}" is not on this page (only text that can be seen counts; try other words or scroll).'
        if nth > total:
            return f'"{text}" appears {total} time(s); there is no match number {nth}.'
        skip = nth - 1
        for frame, count in counts:
            if skip < count:
                res = self._eval_in(frame, _FIND_JS, [text, skip]) or {}
                self.page.wait_for_timeout(250)
                more = f" Call find again with nth={nth + 1} for the next." if nth < total else ""
                return f'found "{text}" (match {nth} of {total}) and scrolled to it: "…{res.get("snippet", "")}…"{more}'
            skip -= count
        return f'"{text}" could not be scrolled to.'

    def hover_ref(self, ref: int) -> str:
        el = self._el(ref)
        if el is None:
            raise BrowserError(f"No element #{ref} in the latest page list.")
        self.page.mouse.move(el["cx"], el["cy"])
        self.page.wait_for_timeout(300)
        return f'hovered #{ref} "{el["text"][:40]}"'

    def type_text(self, text: str, *, clear: bool = False) -> str:
        page = self.page
        if clear:
            page.keyboard.press("Meta+A" if sys.platform == "darwin" else "Control+A")
            page.keyboard.press("Backspace")
        page.keyboard.type(text)
        return f"typed {len(text)} character(s)"

    def press(self, key: str) -> str:
        self.page.keyboard.press(normalize_key(key))
        self._settle()
        return f"pressed {key}"

    def scroll(self, direction: str = "down", amount: int = 600) -> str:
        self.page.mouse.wheel(0, -abs(amount) if direction == "up" else abs(amount))
        self.page.wait_for_timeout(250)
        return f"scrolled {direction} {abs(amount)}px"

    def back(self) -> str:
        resp = self.page.go_back(wait_until="domcontentloaded")
        self._settle()
        return "went back" if resp else "nothing to go back to"

    def wait(self, seconds: float) -> str:
        seconds = max(0.1, min(float(seconds), 15.0))
        self.page.wait_for_timeout(int(seconds * 1000))
        return f"waited {seconds:g}s"

    def bring_to_front(self) -> None:
        try:
            self.page.bring_to_front()
        except Exception:
            pass

    def save_screenshot(self, path: "str | Path") -> bool:
        """Save the viewport as a JPEG file. False if the page cannot be captured right now
        (closed, or blocked by an open dialog); a missing picture must never stop a run."""
        try:
            self.page.screenshot(path=str(path), type="jpeg", quality=self.screenshot_quality, timeout=5000)
            return True
        except Exception:
            return False

    def screenshot(self) -> str:
        """Base64 JPEG of the viewport."""
        raw = self.page.screenshot(type="jpeg", quality=self.screenshot_quality)
        return base64.b64encode(raw).decode()

    def _settle(self) -> None:
        """Give a click/navigation a moment to take effect without waiting on slow trackers."""
        page = self.page
        try:
            page.wait_for_load_state("domcontentloaded", timeout=2500)
        except Exception:
            pass
        page.wait_for_timeout(350)

    # ── helpers ────────────────────────────────────────────────────────────────────
    @staticmethod
    def domain_of(url: str) -> str:
        return urlparse(url).netloc.removeprefix("www.")
