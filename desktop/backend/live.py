"""Live mirror of the agent's browser, plus the plumbing that lets a person take over.

Selfbrowse drives Playwright's synchronous API, which only delivers events (and screencast frames)
while its own thread is inside a Playwright call. The agent thread spends most of its time waiting on
the model, so the model call is wrapped: the real call runs in a helper thread while the agent thread
"pumps" Playwright every 50 ms. That keeps frames flowing, applies the person's clicks and keystrokes,
and lets Stop interrupt a model call instead of waiting for it.

Everything here uses the public ``selfbrowse`` API plus Playwright's CDP session on the page.
"""
from __future__ import annotations

import collections
import threading
import time
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

import record
from selfbrowse.guardrails import PLACEHOLDER_NOTE

QUALITY = 60                # JPEG quality of the mirrored frames
MAX_SIDE = 1280
MAX_QUEUED_INPUTS = 500


class Stopped(BaseException):
    """Raised inside the agent thread when the person pressed Stop. A BaseException on purpose: the agent
    catches Exception around model calls and would otherwise report this as a failed model call."""


class Input(BaseModel):
    """One mouse or keyboard event from the person, in page (CSS pixel) coordinates."""

    t: Literal["move", "down", "up", "wheel", "key", "text"]
    x: float = Field(default=0, ge=0, le=20_000)
    y: float = Field(default=0, ge=0, le=20_000)
    button: Literal["left", "middle", "right"] = "left"
    dx: float = Field(default=0, ge=-5_000, le=5_000)
    dy: float = Field(default=0, ge=-5_000, le=5_000)
    key: str = Field(default="", max_length=40, pattern=r"^[A-Za-z0-9+_ -]*$")
    text: str = Field(default="", max_length=200)


class LiveView:
    """State shared between the agent thread and the web server for one run."""

    def __init__(self) -> None:
        self.stop = threading.Event()
        self.control = False                       # the person has taken over: the agent waits
        self.handoff: bool | None = None           # the person's answer to a hand-off request
        self.mode = "off"                          # review before sending: "off", "flagged" (only when something looks
                                                   # personal) or "always" (every model call)
        self.decision: Any = None                  # the answer to the call being held: "send", "redact" or "stop"
        self.inputs: collections.deque[Input] = collections.deque(maxlen=MAX_QUEUED_INPUTS)
        self.frame: dict[str, Any] | None = None   # only the latest frame is kept
        self.seq = 0
        self._page: Any = None
        self._session: Any = None

    @property
    def review(self) -> bool:                      # the older on/off switch: on means every call
        return self.mode != "off"

    @review.setter
    def review(self, on: bool) -> None:
        self.mode = "always" if on else "off"

    # ── agent thread only ──────────────────────────────────────────────────────────
    def _on_frame(self, params: dict[str, Any]) -> None:
        meta = params.get("metadata") or {}
        self.seq += 1
        self.frame = {"seq": self.seq, "jpeg": params["data"],
                      "w": meta.get("deviceWidth") or 1280, "h": meta.get("deviceHeight") or 800}
        try:                                       # without an ack Chromium stops sending frames
            self._session.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass

    def attach(self, browser: Any) -> None:
        """Mirror whichever tab the browser is on now (restarts the screencast when it changes)."""
        try:
            page = browser.page
        except Exception:
            return
        if page is self._page:
            return
        self.detach()
        try:
            session = page.context.new_cdp_session(page)
            session.on("Page.screencastFrame", self._on_frame)
            session.send("Page.startScreencast", {"format": "jpeg", "quality": QUALITY,
                                                  "maxWidth": MAX_SIDE, "maxHeight": MAX_SIDE, "everyNthFrame": 1})
            self._page, self._session = page, session
        except Exception:
            self._page, self._session = None, None

    def detach(self) -> None:
        if self._session is not None:
            try:
                self._session.send("Page.stopScreencast")
                self._session.detach()
            except Exception:
                pass
        self._page, self._session = None, None

    def _apply_inputs(self, browser: Any) -> None:
        try:
            page = browser.page
        except Exception:
            self.inputs.clear()
            return
        while self.inputs:
            e = self.inputs.popleft()
            try:
                if e.t == "move":
                    page.mouse.move(e.x, e.y)
                elif e.t == "down":
                    page.mouse.move(e.x, e.y)
                    page.mouse.down(button=e.button)
                elif e.t == "up":
                    page.mouse.move(e.x, e.y)
                    page.mouse.up(button=e.button)
                elif e.t == "wheel":
                    page.mouse.move(e.x, e.y)
                    page.mouse.wheel(e.dx, e.dy)
                elif e.t == "key" and e.key:
                    page.keyboard.press(e.key)
                elif e.t == "text" and e.text:
                    page.keyboard.insert_text(e.text)
            except Exception:
                pass                                # a click on a page that just navigated is not worth failing for

    def tick(self, browser: Any) -> None:
        """One pump: follow the active tab, apply input, and let Playwright deliver pending frames."""
        if self.stop.is_set():
            raise Stopped()
        self.attach(browser)
        self._apply_inputs(browser)
        try:
            browser.page.wait_for_timeout(50)
        except Exception:
            time.sleep(0.05)

    def wait_while(self, browser: Any, condition: Callable[[], bool]) -> None:
        while condition():
            self.tick(browser)


def _mask_text(text: str, tokens: dict[str, str]) -> str:
    for match in sorted(tokens, key=len, reverse=True):          # longest first, so a part of a value never survives
        text = text.replace(match, tokens[match])
    return text


def _mask_content(content: Any, tokens: dict[str, str]) -> Any:
    if isinstance(content, str):
        return _mask_text(content, tokens)
    out = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            b = {**b, "text": _mask_text(str(b.get("text", "")), tokens)}
        elif isinstance(b, dict) and b.get("type") == "tool_result":
            b = {**b, "content": _mask_content(b.get("content"), tokens)}
        out.append(b)
    return out


def _decision(value: Any) -> str:
    if value is True:
        return "send"
    return value if value in ("send", "redact") else "stop"


class MirrorLLM:
    """Wraps the real model: keeps the browser pumped during a call, records what was sent, and can hold
    a call until the person approves it. Modes: off, "flagged" (hold only when something in the request looks
    personal), "always". The person can send it, send it with the flagged text masked, or stop the run."""

    def __init__(self, inner: Any, live: LiveView, get_browser: Callable[[], Any],
                 on_pause: Callable[[bool], None] | None = None,
                 emit: Callable[[dict[str, Any]], None] | None = None,
                 secrets: dict[str, str] | None = None, presidio: bool = False) -> None:
        self._presidio = presidio
        self._inner, self._live, self._get_browser, self._on_pause = inner, live, get_browser, on_pause
        self._emit = emit or (lambda e: None)
        self._secrets = secrets or {}
        self._table: dict[str, dict[str, Any]] = {}
        self._decided: dict[tuple[str, str], str] = {}      # (kind, text) -> "send" | "redact", kept for the run
        self.get_vault: Callable[[], Any] = lambda: None    # the agent's own vault, so a masked value can be put back
        self._n = 0
        self.model = getattr(inner, "model", "?")

    def __getattr__(self, name: str) -> Any:        # anything else the agent asks of the model
        return getattr(self._inner, name)

    def _tokens(self, to_mask: list[dict[str, str]], payload: dict[str, Any]) -> dict[str, str]:
        """What to put in place of each flagged text. Reversible whenever the agent has a vault: the library's own
        placeholders (<EMAIL_1>) are typed back for the model on the right site and restored in the answer. One of the
        person's saved values becomes its <secret:NAME>. Without a vault it is a one-way [removed: ...]."""
        vault = self.get_vault()
        task = self._table.get(payload["ids"][1], {}).get("text", "") if len(payload["ids"]) > 1 else ""
        try:
            url = self._get_browser().url
        except Exception:
            url = ""
        out: dict[str, str] = {}
        for f in to_mask:
            if f["kind"] == "value":
                out[f["match"]] = f"<secret:{f['name']}>"
            elif vault is None:
                out[f["match"]] = f"[removed: {f['name']}]"
            else:
                kind = f["name"] if f["kind"] == "pii" else f["kind"]
                given = f["match"] in task                       # written by the person in the task, not seen on a page
                out[f["match"]] = vault.mint(kind, f["match"], "" if given else url, anywhere=given)
        return out

    def _flags(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        seen, out = set(), []
        for mid in payload["ids"]:
            for f in self._table.get(mid, {}).get("flags", []):
                key = (f["kind"], f["match"])
                if key not in seen:
                    seen.add(key)
                    out.append(f)
        return out

    def complete(self, **kwargs: Any) -> Any:
        browser, live = self._get_browser(), self._live
        if live.control:                            # the person is driving: wait here, before spending tokens
            if self._on_pause:
                self._on_pause(True)
            live.wait_while(browser, lambda: live.control)
            if self._on_pause:
                self._on_pause(False)
        self._n += 1
        idx = self._n
        payload = record.build(kwargs, self._table, self._secrets, self._presidio)
        flags = self._flags(payload)
        key = lambda f: (f["kind"], f["match"])
        new = [f for f in flags if key(f) not in self._decided]
        to_mask = [f for f in flags if self._decided.get(key(f)) == "redact"]
        mode = live.mode
        hold = mode == "always" or (mode == "flagged" and bool(new))
        shown = flags if mode == "always" else new
        self._emit({"type": "call", "idx": idx, "holding": hold, "mode": mode if hold else "off",
                    "reason": shown if hold else [], **payload})
        if hold:                                    # nothing leaves this computer until the person says so
            live.decision = None
            live.wait_while(browser, lambda: live.mode != "off" and live.decision is None)
            answer = _decision(live.decision) if live.decision is not None else "send"   # review switched off: send
            if answer == "stop":
                raise Stopped()
            if mode == "flagged":
                for f in new:
                    self._decided[key(f)] = answer
            if answer == "redact":
                to_mask = to_mask + [f for f in shown if f not in to_mask]
            self._emit({"type": "call_sent", "idx": idx})
        if to_mask:                                 # what is sent is the masked request, so that is what is recorded
            kwargs = dict(kwargs)
            tokens = self._tokens(to_mask, payload)
            note = "" if any(t.startswith("<secret:") for t in tokens.values()) and len(tokens) == 1 else PLACEHOLDER_NOTE
            msgs = [{**m, "content": _mask_content(m.get("content"), tokens)} if m.get("role") == "user" else m
                    for m in kwargs.get("messages", [])]
            first = next((i for i, m in enumerate(msgs) if m.get("role") == "user"), None)
            if note and first is not None and self.get_vault() is not None and isinstance(msgs[first].get("content"), str) \
                    and "placeholders like" not in msgs[first]["content"]:
                msgs[first] = {**msgs[first], "content": msgs[first]["content"] + "\n" + note}   # tell the model how to use them
            kwargs["messages"] = msgs
            masked = record.build(kwargs, self._table, self._secrets, False)
            self._emit({"type": "call_masked", "idx": idx, "ids": masked["ids"], "new": masked["new"], "count": len(to_mask)})
        box: dict[str, Any] = {}

        def call() -> None:
            try:
                box["result"] = self._inner.complete(**kwargs)
            except BaseException as exc:            # re-raised in the agent thread below
                box["error"] = exc

        started = time.monotonic()
        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        while worker.is_alive():
            live.tick(browser)
        if "error" in box:
            raise box["error"]
        result = box["result"]
        self._emit({"type": "call_done", "idx": idx, "ms": int((time.monotonic() - started) * 1000),
                    "usage": record.usage_of(result), "reply": record.reply_text(result)})
        return result
