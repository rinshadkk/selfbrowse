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
        self.review = False                        # hold every model call until the person approves it
        self.decision: bool | None = None          # the answer to the call being held
        self.inputs: collections.deque[Input] = collections.deque(maxlen=MAX_QUEUED_INPUTS)
        self.frame: dict[str, Any] | None = None   # only the latest frame is kept
        self.seq = 0
        self._page: Any = None
        self._session: Any = None

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


class MirrorLLM:
    """Wraps the real model: keeps the browser pumped during a call, records what was sent, and can hold
    a call until the person approves it."""

    def __init__(self, inner: Any, live: LiveView, get_browser: Callable[[], Any],
                 on_pause: Callable[[bool], None] | None = None,
                 emit: Callable[[dict[str, Any]], None] | None = None,
                 secrets: dict[str, str] | None = None, presidio: bool = False) -> None:
        self._presidio = presidio
        self._inner, self._live, self._get_browser, self._on_pause = inner, live, get_browser, on_pause
        self._emit = emit or (lambda e: None)
        self._secrets = secrets or {}
        self._table: dict[str, dict[str, Any]] = {}
        self._n = 0
        self.model = getattr(inner, "model", "?")

    def __getattr__(self, name: str) -> Any:        # anything else the agent asks of the model
        return getattr(self._inner, name)

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
        self._emit({"type": "call", "idx": idx, "holding": live.review, **payload})
        if live.review:                             # nothing leaves this computer until the person says so
            live.decision = None
            live.wait_while(browser, lambda: live.review and live.decision is None)
            if live.review and live.decision is False:
                raise Stopped()
            self._emit({"type": "call_sent", "idx": idx})
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
