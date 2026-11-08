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

# ── the in-page script that builds the snapshot ─────────────────────────────────────

_SNAPSHOT_JS = r"""
(maxEls) => {
  const SEL = [
    'a[href]', 'button', 'input:not([type="hidden"])', 'textarea', 'select', 'summary',
    '[role="button"]', '[role="link"]', '[role="textbox"]', '[role="checkbox"]', '[role="radio"]',
    '[role="combobox"]', '[role="option"]', '[role="menuitem"]', '[role="tab"]', '[role="switch"]',
    '[role="slider"]', '[contenteditable=""]', '[contenteditable="true"]', 'h1', 'h2', 'h3',
  ];
  const seen = new Set(), els = [];
  for (const sel of SEL) for (const el of document.querySelectorAll(sel)) {
    if (!seen.has(el)) { seen.add(el); els.push(el); }
  }
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
    const top = document.elementFromPoint(cx, cy);            // skip anything covered by a modal/overlay
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
    const text = (el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('placeholder')
      || el.innerText || el.value || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    let value = '';
    if ((tag === 'input' || tag === 'textarea') && type !== 'password' && el.value) value = String(el.value).slice(0, 30);
    let href = '';
    if (tag === 'a') {
      try {
        const u = new URL(el.href, location.href);
        href = (u.origin === location.origin ? u.pathname + u.search : '').slice(0, 50);
      } catch (e) {}
    }
    items.push({ role, text, type, value, href, cx, cy, y: r.top, x: r.left,
                 checked: (type === 'checkbox' || type === 'radio') ? !!el.checked : null,
                 focused: document.activeElement === el });
  }
  items.sort((a, b) => (Math.abs(a.y - b.y) > 10 ? a.y - b.y : a.x - b.x));
  const total = items.length;
  const doc = document.documentElement;
  const sh = Math.max(doc.scrollHeight, 1);
  return {
    items: items.slice(0, maxEls), total,
    top: Math.round(100 * window.scrollY / sh),
    bottom: Math.min(100, Math.round(100 * (window.scrollY + vh) / sh)),
  };
}
"""

_VISIBLE_TEXT_JS = r"""
(maxChars) => {
  const vh = window.innerHeight, vw = window.innerWidth;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const out = []; let last = null, len = 0;
  while (walker.nextNode()) {
    const n = walker.currentNode, t = n.nodeValue.replace(/\s+/g, ' ').trim();
    if (!t) continue;
    const p = n.parentElement;
    if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName)) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
    const st = getComputedStyle(p);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    out.push(p === last ? ' ' + t : '\n' + t); last = p; len += t.length + 1;
    if (len > maxChars) break;
  }
  return out.join('').trim().slice(0, maxChars);
}
"""


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
    ) -> None:
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

        self._context.on("page", self._on_new_page)    # follow links that open a new tab
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
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
        """Numbered list of what is clickable or typeable in the current viewport."""
        page = self.page
        data = self._eval(_SNAPSHOT_JS, self.max_elements)
        page = self.page
        items = data["items"]
        self._elements = []
        lines = [f'[{self.title[:80]!r} | {page.url}]',
                 f'[viewport shows {data["top"]}–{data["bottom"]}% of the page]']
        for ref, el in enumerate(items, 1):
            el = dict(el, ref=ref)
            self._elements.append(el)
            extras = []
            if el.get("focused"):
                extras.append("focused")
            if el.get("value"):
                extras.append(f'value="{el["value"]}"')
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
        hidden = data["total"] - len(items)
        if hidden > 0:
            lines.append(f"[+{hidden} more elements in view not shown]")
        if not items:
            lines.append("[no interactive elements found — try screenshot, scroll or wait]")
        return Snapshot("\n".join(lines), list(self._elements), page.url, self.title)

    def visible_text(self, max_chars: int = 3000) -> str:
        """The text currently on screen (not just the clickable parts)."""
        return self._eval(_VISIBLE_TEXT_JS, max_chars)

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
        self.page.keyboard.press(key)
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
