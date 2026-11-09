"""The agent loop."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable

from selfbrowse import _about
from selfbrowse.guardrails import Action, Block, Confirm, Guardrail, Guards, RunState, SafeUrls
from selfbrowse.knowledge import SiteKnowledge, domain_of
from selfbrowse.llm import LLM, LLMError, make_llm
from selfbrowse.handoff import Handler, HandoffRequest, detect_block, terminal_handler
from selfbrowse.prompts import HUMAN_RULE, OLD_PAGE, PAGE_SEP, SYSTEM
from selfbrowse.tools import build_tools, extract_text_tool_call, looks_like_junk, normalize_args
from selfbrowse.trace import Tracer, TracingLLM
from selfbrowse.types import RunResult, Step, Usage

_SECRET_RE = re.compile(r"<secret:([A-Za-z0-9_\-]+)>")
_NOT_LEARNED = ("Error:", "Blocked", "The person declined")
_NUDGE = "Reply with exactly one tool call (tools: {tools}). To finish, call done with your answer."
_CUT_OFF = ("Your reply was cut off before you chose an action. Think in one or two short sentences, "
            "then call exactly one tool (tools: {tools}).")
MAX_NUDGES = 3
MAX_ERROR_STREAK = 6


class BrowseAgent:
    """
    Args:
        task: what to do, in plain language.
        llm: ``"provider:model"`` string or any object implementing :class:`selfbrowse.llm.LLM`.
        browser: an existing :class:`selfbrowse.Browser`; one is created (headless) if omitted.
        max_steps: hard cap on tool calls.
        learn: read and write per-site knowledge (replay known flows, remember facts).
        vision: let the model request screenshots (off by default; costs tokens).
        handoff: what to do when only a person can continue (CAPTCHA, login, 2FA...).
            ``"auto"`` (default): ask in the terminal if the browser window is visible, otherwise
            stop with a clear error; ``False``: never; or your own ``callable(HandoffRequest) -> bool``
            (return True once the person is done). Needs ``Browser(headless=False)`` / ``--headed``.
        max_handoffs: stop after this many hand-offs in one run.
        guardrails: list of :mod:`selfbrowse.guardrails` objects (domain limits, confirm-risky,
            PII redaction, budgets, your own). ``SafeUrls`` (http/https only) is always added unless
            ``safe_urls=False``.
        trace: record the run as JSON lines. ``True`` → ``<home>/traces``; or a folder path; or a
            :class:`selfbrowse.trace.Tracer`. See ``selfbrowse trace show latest``.
        show_prompts: print every model request (what is actually sent) to stderr.
        trace_content: ``False`` stores sizes and hashes instead of prompt text.
        redact_trace: ``callable(str) -> str`` applied to all text written to the trace.
        on_llm_request: ``callable(system=, messages=, tools=, n=)`` called before every model call.
        otel: OTLP endpoint (e.g. ``"http://localhost:4318"``) to export spans; needs ``selfbrowse[otel]``.
        otel_content: also attach task/prompt text to spans (off by default).
        max_output_tokens: cap on each model reply. Reasoning models that think at length may need more;
            a reply that hits the cap is answered with a request to be brief.
        page_text: send up to this many characters of on-screen text with every page list (0 = off).
            Fewer ``read`` calls, more tokens per step.
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
        page_text: int = 0,
        max_output_tokens: int = 2048,
        sensitive: dict[str, str] | None = None,
        handoff: "str | bool | Handler" = "auto",
        max_handoffs: int = 3,
        guardrails: "list[Guardrail] | None" = None,
        safe_urls: bool = True,
        trace: "bool | str | Path | Tracer" = False,
        show_prompts: bool = False,
        trace_content: bool = True,
        redact_trace: "Callable[[str], str] | None" = None,
        on_llm_request: "Callable[..., None] | None" = None,
        otel: "str | None" = None,
        otel_content: bool = False,
        home: str | Path | None = None,
        on_step: Callable[[Step], None] | None = None,
    ) -> None:
        import os

        self.task = task
        self._raw_llm = make_llm(llm)
        self.llm = self._raw_llm
        self._own_browser = browser is None
        self.browser = browser
        self.max_steps = max_steps
        self.vision = vision
        self.page_text = max(0, int(page_text))
        self.max_output_tokens = max(256, int(max_output_tokens))
        self.sensitive = dict(sensitive or {})
        self.on_step = on_step
        home_dir = Path(home or os.environ.get(f"{_about.ENV_PREFIX}HOME") or Path.home() / _about.HOME_DIRNAME).expanduser()
        self.knowledge = SiteKnowledge(home_dir / "sites") if learn else None
        self._handoff_opt = handoff
        self.max_handoffs = max_handoffs
        self._handler: Handler | None = None
        self._handoffs = 0
        self._stop: str | None = None
        self.tools = build_tools(vision=vision)
        user_guards = list(guardrails or [])
        if safe_urls and not any(isinstance(g, SafeUrls) for g in user_guards):
            user_guards.insert(0, SafeUrls())
        self.guards = Guards(user_guards)
        self._trace_opt, self._show_prompts = trace, show_prompts
        self._trace_content, self._redact_trace = trace_content, redact_trace
        self._on_llm_request = on_llm_request
        self._otel, self._otel_content = otel, otel_content
        self._traces_dir = home_dir / "traces"
        self.tracer: Tracer | None = None

    # ── public ─────────────────────────────────────────────────────────────────
    def run(self) -> RunResult:
        if self.browser is None:
            from selfbrowse.browser import Browser
            self.browser = Browser()
        self.browser.start()
        self._handler = self._resolve_handler()
        self.tools = build_tools(vision=self.vision, human=self._handler is not None)
        self._system_text = SYSTEM + (HUMAN_RULE if self._handler else "")
        self._handoffs, self._stop = 0, None
        self._setup_trace()
        self._trace("run_start", task=self.task, model=getattr(self._raw_llm, "model", "?"),
                    headed=not getattr(self.browser, "headless", True), handoff=self._handler is not None,
                    guardrails=[g.name for g in self.guards.items])
        result: RunResult | None = None
        try:
            result = self._loop()
            return result
        except BaseException as exc:
            self._trace("run_end", success=False, error=f"{type(exc).__name__}: {exc}"[:300])
            raise
        finally:
            if result is not None:
                u = result.usage
                self._trace("run_end", success=result.success, steps=result.steps, error=result.error,
                            tokens_total=u.total_input + u.output_tokens, calls=u.calls)
            if self.tracer:
                self.tracer.close()
            if self._own_browser:
                self.browser.close()

    @property
    def trace_path(self) -> Path | None:
        """Where this run's trace was written (after ``run()``), if tracing to a file."""
        return self.tracer.path if self.tracer else None

    def _setup_trace(self) -> None:
        opt = self._trace_opt
        want = bool(opt) or self._show_prompts or self._otel or self._on_llm_request
        self.llm, self.tracer = self._raw_llm, None
        if not want:
            return
        if isinstance(opt, Tracer):
            self.tracer = opt
        else:
            directory = None
            if opt:
                directory = self._traces_dir if opt is True else Path(opt)
            sinks = []
            if self._otel:
                from selfbrowse.otel import OtelSink
                sinks.append(OtelSink(self._otel, content=self._otel_content))
            self.tracer = Tracer(directory, content=self._trace_content, redact=self._redact_trace,
                                 show_prompts=self._show_prompts, sinks=sinks)
        self.llm = TracingLLM(self._raw_llm, self.tracer, self._on_llm_request)

    def _trace(self, type: str, **data: Any) -> None:
        if self.tracer:
            self.tracer.event(type, **data)

    # ── internals ──────────────────────────────────────────────────────────────
    def _loop(self) -> RunResult:
        usage = Usage()
        history: list[Step] = []
        messages: list[dict[str, Any]] = [{"role": "user", "content": f"Task: {self.task}"}]
        system = [{"text": self._system_text, "cache": True}]
        recent: list[tuple[str, str, str]] = []
        replayed: set[str] = set()
        success, output, error = False, "", None
        first = True
        t0 = time.monotonic()
        nudges = 0
        err_streak = 0
        scroll_log: list[str] = []                           # scroll directions since the last non-scroll action
        click_log: list[tuple[str, str, str]] = []           # (url, role, label) of recent clicks
        names = [t["name"] for t in self.tools]

        if (hit := self.guards.url(self.browser.url)) and self.browser.url not in ("about:blank", ""):
            self._trace("guardrail", guardrail=hit[0].name, decision="block", reason=hit[1].reason)
            return RunResult(False, "", 0, usage, history, f"guardrail {hit[0].name}: {hit[1].reason} (start page {self.browser.url})")

        for _ in range(self.max_steps):
            # Known flow for this page? Run it without asking the model.
            self._maybe_replay(history, replayed)

            if first:
                state = self._state()
                messages[0]["content"] = f"Task: {self.task}{PAGE_SEP}{state}"
                first = False
                if self._stop:
                    error = self._stop
                    break

            self._trim_old_pages(messages)
            try:
                resp = self.llm.complete(system=system, messages=messages, tools=self.tools, max_tokens=self.max_output_tokens)
            except LLMError as exc:
                error = str(exc)
                break
            except Exception as exc:                       # network, rate limit, bad key...
                error = f"model call failed: {exc}"
                break
            usage.add(resp.usage)
            if (hit := self.guards.step(RunState(len(history), usage, time.monotonic() - t0))):
                self._trace("guardrail", guardrail=hit[0].name, decision="stop", reason=hit[1].reason)
                error = f"guardrail {hit[0].name}: {hit[1].reason}"
                break
            content = self._repair(resp.content, len(history))
            messages.append({"role": "assistant", "content": content or [{"type": "text", "text": "(no output)"}]})

            calls = [b for b in content if b["type"] == "tool_use"]
            if not calls:
                text = " ".join(b.get("text", "") for b in content if b["type"] == "text").strip()
                # A plain-text reply is only a real answer if the model has acted and is not imitating the transcript.
                if history and text and resp.stop_reason == "end_turn" and not looks_like_junk(text):
                    success, output = True, text
                    break
                nudges += 1
                if nudges > MAX_NUDGES:
                    error = ("the model's replies kept running past the output limit (raise --max-output-tokens or use a model "
                             "that does not think at length)" if resp.stop_reason == "max_tokens"
                             else "the model never produced a valid action")
                    break
                cut = resp.stop_reason == "max_tokens"
                self._trace("nudge", text=text[:200], cut_off=cut)
                messages.append({"role": "user", "content": (_CUT_OFF if cut else _NUDGE).format(tools=", ".join(names))})
                continue
            nudges = 0                                       # the limit is for consecutive misses

            results: list[dict[str, Any]] = []
            finished = False
            acted = False
            for call in calls:
                name, args = call["name"], call.get("input") or {}
                args, bad = self._validate(name, args)
                if name == "done" and not bad:
                    success, output = bool(args.get("success")), str(args.get("answer", ""))
                    history.append(self._step(history, name, args, output))
                    finished = True
                    break
                if acted:                                  # one page-changing action per turn
                    results.append(self._result(call["id"], "Skipped: one action per turn. Page unchanged; decide again."))
                    continue
                url_before = self.browser.url
                clicked = self._click_key(url_before, args) if name == "click" and not bad else None
                blocked = bad if bad is not None else self._pre_action(name, args)
                if blocked is not None:
                    text, changed = blocked, False
                    self._trace("tool_call", tool=name, args=args, blocked=True)
                    self._trace("tool_result", result=text, seconds=0)
                else:
                    self._trace("tool_call", tool=name, args=args)
                    started = time.perf_counter()
                    text, changed = self._execute(name, args)
                    if changed and name != "ask_human":
                        text = self._post_url_check(text)
                    self._trace("tool_result", result=text.split(PAGE_SEP)[0][:500], seconds=round(time.perf_counter() - started, 3))
                acted = acted or changed
                step = self._step(history, name, args, text, url_before)
                history.append(step)
                if not text.startswith(_NOT_LEARNED):      # failed or blocked actions teach nothing
                    self._learn(url_before, name, args)
                suffix = ""
                if name == "scroll":
                    scroll_log.append(str(args.get("direction", "down")))
                else:
                    scroll_log.clear()                           # reading or acting ends the circle
                if clicked and not text.startswith(_NOT_LEARNED):
                    if clicked in click_log[-6:]:
                        suffix = (f'\n[You already clicked "{clicked[2][:40]}" on this page a moment ago. If that did not '
                                  "do what you expected, call read or try a different control.]")
                    click_log.append(clicked)
                if changed or name in ("wait", "scroll", "back"):
                    sig = (name, repr(sorted(args.items())), self.browser.url)
                    recent.append(sig)
                    if name == "scroll" and len(scroll_log) >= 4 and all(a != b for a, b in zip(scroll_log[-4:], scroll_log[-3:])):
                        suffix = ("\n[You are scrolling up and down in circles. Call read to see the text here, or find to jump "
                                  "to a word, then act.]")
                    elif name == "scroll" and sum(1 for r in recent[-4:] if r[0] == "scroll") >= 3:
                        suffix = "\n[You have scrolled several times without reading. Call read.]"
                    elif len(recent) >= 3 and len(set(recent[-3:])) == 1:
                        suffix = "\n[You repeated this action 3 times with no progress. Try something different.]"
                    text = f"{text}{suffix}{PAGE_SEP}{self._state()}"
                if text.startswith("Error:"):
                    err_streak += 1
                    if err_streak == 3:
                        text += "\n[3 failed actions in a row. Use only refs from the latest page list and the exact argument names.]"
                    if err_streak >= MAX_ERROR_STREAK:
                        self._stop = "the model keeps producing invalid or failing actions"
                else:
                    err_streak = 0
                results.append(self._result(call["id"], text))
            if finished:
                break
            messages.append({"role": "user", "content": results})
            if self._stop:
                error = self._stop
                break
        else:
            error = f"stopped after {self.max_steps} steps without finishing"

        if self.knowledge:
            self.knowledge.commit(success, self.task)
        return RunResult(success=success, output=output, steps=len(history), usage=usage, history=history, error=error)

    def _click_key(self, url: str, args: dict[str, Any]) -> tuple[str, str, str] | None:
        try:
            d = self.browser.describe_ref(int(args.get("ref", 0)))
        except (TypeError, ValueError):
            return None
        return (url, d["role"], d["text"]) if d and d["text"] else None

    def _state(self) -> str:
        prefix = ""
        snap = self.browser.snapshot()
        reason = self._detect_block(snap)
        while reason and not self._stop:                  # re-check: the person may not have got past it
            prefix = self._hand_off("challenge", reason) + "\n"
            snap = self.browser.snapshot()
            reason = self._detect_block(snap)
        text = snap.text
        if self.page_text:                                 # optional: facts on screen without a separate read call
            on_screen = self.browser.visible_text(self.page_text)
            if on_screen:
                text += "\n[text on screen]\n" + on_screen
        text = self.guards.page(text, self.browser.url)
        if self.knowledge:
            memo = self.knowledge.get_memo(self.browser.url)
            if memo:
                text += "\n[Notes for this site: " + "; ".join(memo) + "]"
        return prefix + text

    def _detect_block(self, snap: Any) -> str | None:
        if self._stop:
            return None
        try:
            page_text = self.browser.visible_text(1500)
        except Exception:
            page_text = ""
        return detect_block(snap.title, page_text, len(snap.elements))

    def _resolve_handler(self) -> Handler | None:
        opt = self._handoff_opt
        if callable(opt):
            return opt
        if opt is False:
            return None
        return terminal_handler if not getattr(self.browser, "headless", True) else None

    def _hand_off(self, kind: str, reason: str) -> str:
        """Pause for a person. Returns a note for the model; sets self._stop if the run cannot go on."""
        url = self.browser.url
        self._trace("handoff", kind=kind, reason=reason, url=url, resumed=None)
        if self._handler is None:
            if kind == "challenge":
                self._stop = f"blocked: {reason} at {url}. Re-run with --headed so you can complete it yourself."
            else:
                self._stop = f"needs a person ({reason}) at {url}, but hand-off is unavailable. Re-run with --headed."
            return "[blocked: a person is needed but hand-off is unavailable]"
        if self._handoffs >= self.max_handoffs:
            self._stop = f"stopped after {self.max_handoffs} hand-offs without getting past: {reason}"
            return "[too many hand-offs]"
        self._handoffs += 1
        self.browser.bring_to_front()
        try:
            resumed = bool(self._handler(HandoffRequest(kind, reason, url)))
        except Exception as exc:
            resumed = False
            reason = f"{reason} (hand-off failed: {exc})"
        self._trace("handoff", kind=kind, reason=reason, url=url, resumed=resumed)
        if not resumed:
            self._stop = f"stopped: the person did not continue after: {reason}"
            return "[the person did not continue]"
        return "[The person handled it. Continue from the page below.]"

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
        """Keep only the newest page list; older ones are dead weight (refs have changed)."""
        def has_live_page(msg: dict[str, Any]) -> bool:
            if msg["role"] != "user":
                return False
            if isinstance(msg["content"], str):
                return PAGE_SEP in msg["content"] and not msg["content"].endswith(OLD_PAGE)
            return any(
                part.get("type") == "text" and PAGE_SEP in part["text"] and not part["text"].endswith(OLD_PAGE)
                for block in msg["content"] if block.get("type") == "tool_result" for part in block["content"]
            )

        live = [i for i, m in enumerate(messages) if has_live_page(m)]
        keep = live[-1] if live else len(messages)
        for msg in messages[:keep]:
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

    # ── guardrails ─────────────────────────────────────────────────────────────
    def _validate(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        spec = next((t for t in self.tools if t["name"] == name), None)
        if spec is None:
            return args, f"Error: unknown tool {name!r}. Tools: {', '.join(t['name'] for t in self.tools)}."
        return normalize_args(spec, args)

    def _repair(self, content: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
        """If the model wrote a tool call as text, turn it into a real one."""
        if any(b["type"] == "tool_use" for b in content):
            return content
        text = " ".join(b.get("text", "") for b in content if b["type"] == "text")
        found = extract_text_tool_call(text, self.tools)
        if not found:
            return content
        name, args = found
        self._trace("repair", tool=name, args=args)
        return [{"type": "tool_use", "id": f"repaired-{n}", "name": name, "input": args}]

    def _make_action(self, name: str, a: dict[str, Any]) -> Action:
        act = Action(name, dict(a), self.browser.url)
        if name == "goto":
            raw = str(a.get("url", ""))
            act.target_url = raw if "://" in raw or raw.startswith(("about:", "data:", "javascript:")) else "https://" + raw
        elif name in ("click", "type", "hover", "select"):
            try:
                d = self.browser.describe_ref(int(a.get("ref", 0)))
            except (TypeError, ValueError):
                d = None
            if d:
                act.role, act.text = d["role"], d["text"]
        return act

    def _pre_action(self, name: str, a: dict[str, Any]) -> str | None:
        """Run guardrails before an action. Returns a message for the model if it must not run."""
        if not self.guards.items:
            return None
        act = self._make_action(name, a)
        if name == "goto" and (hit := self.guards.url(act.target_url)):
            g, d = hit
            self._trace("guardrail", guardrail=g.name, decision="block", reason=d.reason)
            return f"Blocked by guardrail {g.name}: {d.reason}. Choose another approach."
        hit = self.guards.action(act)
        if not hit:
            return None
        g, d = hit
        if isinstance(d, Block):
            self._trace("guardrail", guardrail=g.name, decision="block", reason=d.reason)
            return f"Blocked by guardrail {g.name}: {d.reason}. Choose another approach."
        # Confirm: ask a person
        self._trace("guardrail", guardrail=g.name, decision="confirm", reason=d.reason)
        if self._handler is None:
            return f"Blocked by guardrail {g.name}: {d.reason}, and no person is available to approve it. Choose another approach."
        self.browser.bring_to_front()
        try:
            ok = bool(self._handler(HandoffRequest("confirm", d.reason, act.url)))
        except Exception:
            ok = False
        self._trace("handoff", kind="confirm", reason=d.reason, url=act.url, resumed=ok)
        return None if ok else "The person declined this action. Choose another approach."

    def _post_url_check(self, text: str) -> str:
        """After an action, make sure the browser did not land somewhere the guardrails forbid."""
        hit = self.guards.url(self.browser.url)
        if not hit or self.browser.url in ("about:blank", ""):
            return text
        g, d = hit
        self._trace("guardrail", guardrail=g.name, decision="block", reason=f"{d.reason} (landed on {self.browser.url})")
        try:
            self.browser.back()
            if self.guards.url(self.browser.url):
                self.browser.page.goto("about:blank")
        except Exception:
            try:
                self.browser.page.goto("about:blank")
            except Exception:
                pass
        return f"Blocked by guardrail {g.name}: {d.reason}. Went back to the previous page."

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
            if name == "select":
                return b.select_ref(int(a["ref"]), str(a["option"])), True
            if name == "find":
                return self.guards.page(b.find_text(str(a["text"]), int(a.get("nth", 1))), b.url), True
            if name == "switch_tab":
                return b.switch_tab(int(a["index"])), True
            if name == "close_tab":
                return b.close_tab(int(a["index"]) if a.get("index") is not None else None), True
            if name == "press":
                return b.press(str(a["key"])), True
            if name == "scroll":
                return b.scroll(str(a.get("direction", "down"))) + " (call read to see the text now on screen)", True
            if name == "back":
                return b.back(), True
            if name == "wait":
                return b.wait(float(a.get("seconds", 2))), True
            if name == "read":
                return "Visible text:\n" + self.guards.page(b.visible_text(), b.url), False
            if name == "ask_human":
                note = self._hand_off("model", str(a.get("reason", "the agent needs your help")))
                return note, True
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
                    act = Action("click", {"ref": ref}, before, role=s.get("role", ""), text=s.get("text", ""))
                    if self.guards.action(act):            # replay never asks anyone: leave it to the model
                        return
                    text = self.browser.click_ref(ref)
                elif s["tool"] == "press":
                    text = self.browser.press(s["key"])
                else:
                    continue
            except Exception:
                self.knowledge.record_miss(before)
                return
            history.append(self._step(history, s["tool"], {k: v for k, v in s.items() if k != "tool"}, text, before, True))
            self._trace("replay", tool=s["tool"], args={k: v for k, v in s.items() if k != "tool"}, url=before)
            if self.guards.url(self.browser.url):
                self._post_url_check("")
                return
            if domain_of(self.browser.url) != domain_of(before):
                return
