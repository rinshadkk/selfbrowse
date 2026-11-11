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

_SNAPSHOT_JS = "(maxEls) => {" + _JS_HELPERS + r"""
  const SEL = [
    'a[href]', 'button', 'input:not([type="hidden"])', 'textarea', 'select', 'summary',
    '[role="button"]', '[role="link"]', '[role="textbox"]', '[role="checkbox"]', '[role="radio"]',
    '[role="combobox"]', '[role="option"]', '[role="menuitem"]', '[role="tab"]', '[role="switch"]',
    '[role="slider"]', '[contenteditable=""]', '[contenteditable="true"]', 'h1', 'h2', 'h3',
  ];
  const seen = new Set(), els = [];
  const collect = (root) => {
    for (const sel of SEL) for (const el of root.querySelectorAll(sel)) {
      if (!seen.has(el)) { seen.add(el); els.push(el); }
    }
    for (const host of root.querySelectorAll('*')) if (host.shadowRoot) collect(host.shadowRoot);
  };
  collect(document);
  const vh = window.innerHeight, vw = window.innerWidth;
  const items = [];
  for (const el of els) {
    if (el.disabled) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') continue;
    const cx = Math.round(Math.min(Math.max(r.left + r.width / 2, 0), vw - 1));
    const cy = Math.round(Math.min(Math.max(r.top + r.height / 2, 0), vh - 1));
    const top = deepFromPoint(cx, cy);                        // skip anything covered by a modal/overlay
    if (top && !(el.contains(top) || top.contains(el))) continue;

    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    let role = el.getAttribute('role');
    if (!role) {
      if (tag === 'a') role = 'link';
      else if (tag === 'button' || tag === 'summary') role = 'button';
      else if (tag === 'select') role = 'combobox';
      else if (tag === 'textarea') role = 'textbox';
      else if (/^h[1-3]$/.test(tag)) role = 'heading';
      else if (tag === 'input') role = ['checkbox', 'radio'].includes(type) ? type
        : ['submit', 'button', 'reset', 'image'].includes(type) ? 'button' : 'textbox';
      else role = 'textbox';
    }
    const isField = tag === 'input' || tag === 'select' || tag === 'textarea';
    const labelled = isField && el.labels && el.labels[0] ? el.labels[0].innerText : '';
    const text = (el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('placeholder')
      || labelled || (tag === 'select' ? el.getAttribute('name') : (el.innerText || el.value)) || el.textContent || '')
      .replace(/\s+/g, ' ').trim().slice(0, 80);
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
    items.push({ role, text, type, value, href, cx, cy, y: r.top, x: r.left, options,
                 checked: (type === 'checkbox' || type === 'radio') ? !!el.checked : null,
                 focused: document.activeElement === el });
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

_VISIBLE_TEXT_JS = r"""
(maxChars) => {
  const vh = window.innerHeight, vw = window.innerWidth;
  const out = []; let last = null, len = 0;
  const visit = (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      if (len > maxChars) return;
      const n = walker.currentNode;
      if (n.nodeType === 1) { if (n.shadowRoot) visit(n.shadowRoot); continue; }
      const t = n.nodeValue.replace(/\s+/g, ' ').trim();
      if (!t) continue;
      const p = n.parentElement || (n.parentNode && n.parentNode.host);
      if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName)) continue;
      const range = document.createRange(); range.selectNodeContents(n);
      const r = range.getBoundingClientRect();
      if (r.width < 1 || r.height < 1 || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
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
  const norm = s => String(s).replace(/\s+/g, ' ').trim().toLowerCase();
  const n = norm(needle);
  const hits = [];
  const visit = (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.nodeType === 1) { if (node.shadowRoot) visit(node.shadowRoot); continue; }
      const p = node.parentElement || (node.parentNode && node.parentNode.host);
      if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName)) continue;
      if (!norm(node.nodeValue).includes(n)) continue;
      if (!p.getClientRects().length || getComputedStyle(p).visibility === 'hidden') continue;
      hits.push(node);
    }
  };
  if (document.body && n) visit(document.body);
  if (skip < 0 || skip >= hits.length) return { count: hits.length };
  const node = hits[skip], p = node.parentElement || node.parentNode.host;
  p.scrollIntoView({ block: 'center', inline: 'nearest' });
  const t = node.nodeValue.replace(/\s+/g, ' ').trim();
  const i = Math.max(0, t.toLowerCase().indexOf(n));
  return { count: hits.length, snippet: t.slice(Math.max(0, i - 50), i + n.length + 70) };
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
        stealth: use Patchright (``pip install selfbrowse[stealth]``) to hide common automation tells.
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
        screenshot_quality: int = 60,
        timeout_ms: int = 15000,
        max_elements: int = 120,
        permissions: "list[str] | None" = None,
        dialogs: str = "auto",
    ) -> None:
        bad = [p for p in (permissions or []) if p not in PERMISSIONS]
        if bad:
            raise BrowserError(f"Unknown permission {bad[0]!r}. Choose from: {', '.join(sorted(PERMISSIONS))}.")
        if dialogs not in DIALOG_POLICIES:
            raise BrowserError(f"dialogs must be one of: {', '.join(DIALOG_POLICIES)}.")
        self.permissions = list(permissions or [])
        self.dialogs = dialogs
        self.on_dialog: "Callable[[dict[str, Any]], bool | None] | None" = None   # may veto accepting
        self._dialog_log: list[dict[str, Any]] = []
        self.headless = headless
        self.channel = channel
        self.executable_path = executable_path
        self.user_data_dir = Path(user_data_dir).expanduser() if user_data_dir else None
        self.viewport = viewport
        self.stealth = stealth
        self.screenshot_quality = max(10, min(95, screenshot_quality))
        self.timeout_ms = timeout_ms
        self.max_elements = max_elements
        self._pw = self._browser = self._context = self._page = None
        self._elements: list[dict[str, Any]] = []
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
        ctx_kwargs = {"viewport": {"width": self.viewport[0], "height": self.viewport[1]}}
        last: Exception | None = None
        for channel in ([self.channel] if self.channel else [None, "chrome"]):
            kwargs: dict[str, Any] = {"headless": self.headless}
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

        if self.permissions:
            try:
                self._context.grant_permissions(self.permissions)
            except Exception as exc:
                self.close()
                raise BrowserError(f"Could not grant permissions {self.permissions}: {exc}") from exc
        self._watched: set[int] = set()
        self._context.on("page", self._on_new_page)    # follow links that open a new tab
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        self._watch_dialogs(self._page)                # new_page() may already have fired the event above
        return self

    def close(self) -> None:
        for obj in (self._context, self._browser):
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
        self._pw = self._browser = self._context = self._page = None

    def __enter__(self) -> "Browser":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _on_new_page(self, page: Any) -> None:
        self._page = page
        page.set_default_timeout(self.timeout_ms)
        self._watch_dialogs(page)

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
        data = self._eval(_SNAPSHOT_JS, self.max_elements)
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
            if el.get("type") and el["type"] not in ("text", "submit", "button", "checkbox", "radio", ""):
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

    def visible_text(self, max_chars: int = 3000) -> str:
        """The text currently on screen (not just the clickable parts), iframes included."""
        text = self._eval(_VISIBLE_TEXT_JS, max_chars)
        if len(self.page.frames) > 1 and len(text) < max_chars:
            vw, vh = self.viewport
            for frame, _, _, _ in self._child_frames(vw, vh):
                extra = self._eval_in(frame, _VISIBLE_TEXT_JS, max_chars - len(text))
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
            raise BrowserError(f"#{ref} is not a native dropdown. Click it, then click the option you want.")
        frame = self._frames[el.get("frame", 0)] if self._frames else self.page.main_frame
        res = self._eval_in(frame, _SELECT_JS, [el["lx"], el["ly"], option])
        if not res:
            raise BrowserError("the page changed before the option could be chosen; read the new list and try again")
        if res.get("error"):
            opts = " | ".join(res.get("options", [])[:12])
            raise BrowserError(f'{res["error"]} for "{option}". Options: {opts}')
        self._settle()
        return f'selected "{res["chosen"]}" in #{ref}'

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
