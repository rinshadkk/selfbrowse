"""The agent loop."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from selfbrowse import _about
from selfbrowse.knowledge import SiteKnowledge, domain_of
from selfbrowse.llm import LLM, LLMError, make_llm
from selfbrowse.prompts import OLD_PAGE, PAGE_SEP, SYSTEM
from selfbrowse.tools import build_tools
from selfbrowse.types import RunResult, Step, Usage

_SECRET_RE = re.compile(r"<secret:([A-Za-z0-9_\-]+)>")


class Agent:
    """
    Args:
        task: what to do, in plain language.
        llm: ``"provider:model"`` string or any object implementing :class:`selfbrowse.llm.LLM`.
        browser: an existing :class:`selfbrowse.Browser`; one is created (headless) if omitted.
        max_steps: hard cap on tool calls.
        learn: read and write per-site knowledge (replay known flows, remember facts).
        vision: let the model request screenshots (off by default; costs tokens).
        sensitive: ``{"NAME": "value"}``. The model writes ``<secret:NAME>``; Selfbrowse substitutes the
            real value only when typing, so secrets never enter the model's context.
        home: data folder (default ``~/.selfbrowse``, or ``$SELFBROWSE_HOME``).
        on_step: callback receiving each :class:`selfbrowse.Step`.
    """

    def __init__(
        self,
        task: str,
        *,
        llm: "str | LLM" = "anthropic:claude-haiku-4-5",
        browser: Any = None,
        max_steps: int = 25,
        learn: bool = True,
        vision: bool = False,
        sensitive: dict[str, str] | None = None,
        home: str | Path | None = None,
        on_step: Callable[[Step], None] | None = None,
    ) -> None:
        import os

        self.task = task
        self.llm = make_llm(llm)
        self._own_browser = browser is None
        self.browser = browser
        self.max_steps = max_steps
        self.vision = vision
        self.sensitive = dict(sensitive or {})
        self.on_step = on_step
        home_dir = Path(home or os.environ.get(f"{_about.ENV_PREFIX}HOME") or Path.home() / _about.HOME_DIRNAME).expanduser()
        self.knowledge = SiteKnowledge(home_dir / "sites") if learn else None
        self.tools = build_tools(vision=vision)

    # ── public ─────────────────────────────────────────────────────────────────
    def run(self) -> RunResult:
        if self.browser is None:
            from selfbrowse.browser import Browser
            self.browser = Browser()
        self.browser.start()
        try:
            return self._loop()
        finally:
            if self._own_browser:
                self.browser.close()

    # ── internals ──────────────────────────────────────────────────────────────
    def _loop(self) -> RunResult:
        usage = Usage()
        history: list[Step] = []
        messages: list[dict[str, Any]] = [{"role": "user", "content": f"Task: {self.task}"}]
        system = [{"text": SYSTEM, "cache": True}]
        recent: list[tuple[str, str, str]] = []
        replayed: set[str] = set()
        success, output, error = False, "", None
        first = True

        for _ in range(self.max_steps):
            # Known flow for this page? Run it without asking the model.
            self._maybe_replay(history, replayed)

            if first:
                state = self._state()
                messages[0]["content"] = f"Task: {self.task}{PAGE_SEP}{state}"
                first = False

            self._trim_old_pages(messages)
            try:
                resp = self.llm.complete(system=system, messages=messages, tools=self.tools)
            except LLMError as exc:
                error = str(exc)
                break
            except Exception as exc:                       # network, rate limit, bad key...
                error = f"model call failed: {exc}"
                break
            usage.add(resp.usage)
            messages.append({"role": "assistant", "content": resp.content or [{"type": "text", "text": "(no output)"}]})

            calls = [b for b in resp.content if b["type"] == "tool_use"]
            if not calls:
                text = " ".join(b.get("text", "") for b in resp.content if b["type"] == "text").strip()
                success, output = (True, text) if resp.stop_reason == "end_turn" and text else (False, "")
                if not success:
                    error = "the model stopped without finishing"
                break

            results: list[dict[str, Any]] = []
            finished = False
            acted = False
            for call in calls:
                name, args = call["name"], call.get("input") or {}
                if name == "done":
                    success, output = bool(args.get("success")), str(args.get("answer", ""))
                    history.append(self._step(history, name, args, output))
                    finished = True
                    break
                if acted:                                  # one page-changing action per turn
                    results.append(self._result(call["id"], "Skipped: one action per turn. Page unchanged; decide again."))
                    continue
                url_before = self.browser.url
                text, changed = self._execute(name, args)
                acted = acted or changed
                step = self._step(history, name, args, text, url_before)
                history.append(step)
                if not text.startswith("Error:"):          # failed actions teach nothing
                    self._learn(url_before, name, args)
                suffix = ""
                if changed or name in ("wait", "scroll", "back"):
                    sig = (name, repr(sorted(args.items())), self.browser.url)
                    recent.append(sig)
                    if name == "scroll" and sum(1 for r in recent[-4:] if r[0] == "scroll") >= 3:
                        suffix = "\n[You have scrolled several times without reading. Call read.]"
                    elif len(recent) >= 3 and len(set(recent[-3:])) == 1:
                        suffix = "\n[You repeated this action 3 times with no progress. Try something different.]"
                    text = f"{text}{suffix}{PAGE_SEP}{self._state()}"
                results.append(self._result(call["id"], text))
            if finished:
                break
            messages.append({"role": "user", "content": results})
        else:
            error = f"stopped after {self.max_steps} steps without finishing"

        if self.knowledge:
            self.knowledge.commit(success, self.task)
        return RunResult(success=success, output=output, steps=len(history), usage=usage, history=history, error=error)

    def _state(self) -> str:
        snap = self.browser.snapshot().text
        if self.knowledge:
            memo = self.knowledge.get_memo(self.browser.url)
            if memo:
                snap += "\n[Notes for this site: " + "; ".join(memo) + "]"
        return snap

    def _step(self, history: list[Step], tool: str, args: dict, result: str, url: str = "", cached: bool = False) -> Step:
        shown = {k: ("<hidden>" if k == "text" and _SECRET_RE.search(str(v)) else v) for k, v in args.items()}
        step = Step(len(history) + 1, tool, shown, result.split(PAGE_SEP)[0][:300], url or self.browser.url, cached)
        if self.on_step:
            self.on_step(step)
        return step

    @staticmethod
    def _result(tool_use_id: str, text: str) -> dict[str, Any]:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": [{"type": "text", "text": text}]}

    @staticmethod
    def _trim_old_pages(messages: list[dict[str, Any]]) -> None:
        """Only the newest page list is useful; older ones are dead weight (refs have changed)."""
        for msg in messages[:-1]:
            if msg["role"] != "user":
                continue
            if isinstance(msg["content"], str):
                if PAGE_SEP in msg["content"]:
                    msg["content"] = msg["content"].split(PAGE_SEP)[0] + PAGE_SEP + OLD_PAGE
                continue
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    for part in block["content"]:
                        if part.get("type") == "text" and PAGE_SEP in part["text"]:
                            part["text"] = part["text"].split(PAGE_SEP)[0] + PAGE_SEP + OLD_PAGE
                        elif part.get("type") == "image":
                            part["type"], part["text"] = "text", "[older screenshot omitted]"
                            part.pop("source", None)

    def _substitute_secrets(self, text: str) -> str:
        def sub(m: re.Match) -> str:
            if m.group(1) not in self.sensitive:
                raise KeyError(m.group(1))
            return self.sensitive[m.group(1)]
        return _SECRET_RE.sub(sub, text)

    def _execute(self, name: str, a: dict[str, Any]) -> tuple[str, bool]:
        """Run one tool. Returns (message for the model, whether the page may have changed)."""
        b = self.browser
        try:
            if name == "goto":
                return f"opened {b.goto(str(a['url']))}", True
            if name == "click":
                return b.click_ref(int(a["ref"])), True
            if name == "type":
                try:
                    text = self._substitute_secrets(str(a["text"]))
                except KeyError as exc:
                    return f"Unknown secret {exc}. Available: {', '.join(self.sensitive) or 'none'}.", False
                b.click_ref(int(a["ref"]))
                b.type_text(text, clear=True)
                if a.get("submit"):
                    b.press("Enter")
                shown = _SECRET_RE.sub(lambda m: m.group(0), str(a["text"]))
                return f'typed "{shown[:60]}"' + (" and pressed Enter" if a.get("submit") else ""), True
            if name == "press":
                return b.press(str(a["key"])), True
            if name == "scroll":
                return b.scroll(str(a.get("direction", "down"))) + " (call read to see the text now on screen)", True
            if name == "back":
                return b.back(), True
            if name == "wait":
                return b.wait(float(a.get("seconds", 2))), True
            if name == "read":
                return "Visible text:\n" + b.visible_text(), False
            if name == "remember":
                if self.knowledge:
                    self.knowledge.remember(b.url, str(a.get("fact", "")))
                return "saved", False
            if name == "screenshot" and self.vision:
                return "(screenshot unavailable for this provider path)", False
            return f"Unknown tool {name!r}.", False
        except Exception as exc:                           # a failed action is feedback, not a crash
            msg = str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__
            return f"Error: {msg}", True

    def _learn(self, url_before: str, name: str, a: dict[str, Any]) -> None:
        if not self.knowledge:
            return
        if name == "click":
            desc = self.browser.describe_ref(int(a.get("ref", 0)))   # refs are still valid: no snapshot since the click
            if desc:
                self.knowledge.record(url_before, {"tool": "click", **desc})
        elif name == "press":
            self.knowledge.record(url_before, {"tool": "press", "key": str(a.get("key", ""))})
        elif name == "type":
            self.knowledge.record(url_before, {"tool": "type"})
        elif name == "back":
            self.knowledge.undo_last(self.browser.url)     # the click that left this page was a detour

    def _maybe_replay(self, history: list[Step], replayed: set[str]) -> None:
        """Replay a trusted learned flow for the current page, without calling the model."""
        if not self.knowledge or self.max_steps <= len(history):
            return
        url = self.browser.url
        if not url.startswith("http") or url in replayed:
            return
        steps = self.knowledge.get_steps(url, self.task)
        replayed.add(url)
        for s in steps:
            before = self.browser.url
            try:
                if s["tool"] == "click":
                    ref = self.browser.resolve_ref(s.get("role", ""), s.get("text", ""))
                    if ref is None:
                        raise LookupError("element not found")
                    text = self.browser.click_ref(ref)
                elif s["tool"] == "press":
                    text = self.browser.press(s["key"])
                else:
                    continue
            except Exception:
                self.knowledge.record_miss(before)
                return
            history.append(self._step(history, s["tool"], {k: v for k, v in s.items() if k != "tool"}, text, before, True))
            if domain_of(self.browser.url) != domain_of(before):
                return
