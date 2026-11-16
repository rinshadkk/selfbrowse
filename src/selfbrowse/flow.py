"""
Flows: a whole run saved as a file and replayed with no model at all.

A *flow* is what an agent run did, in order: open this page, click that button, type a value, read the
result. :class:`FlowRecorder` builds one while a run goes on (``BrowseAgent(..., save_flow="x.json")`` or
``selfbrowse "task" --save-flow x.json``) and :class:`FlowRunner` plays it back (``selfbrowse flow run x.json``).
Running a flow calls no model, so it costs nothing, takes a few seconds, and does the same thing every time.

Design rules, so a flow file is safe to keep and to pass on:

* **Values that change are parameters.** Whatever was typed or chosen is stored as ``{{name}}`` with the
  recorded value as its default, so ``--param from=BLR`` reruns it for another airport.
* **Secrets are names, never values.** ``<secret:PASSWORD>`` stays a placeholder in the file and is filled
  from ``$SELFBROWSE_SECRET_PASSWORD`` at run time. A value that was masked for the model (``<EMAIL_1>``)
  becomes a parameter with no default, so personal data is never written to the file.
* **Elements are found again by what they are called**, not by a number: role, visible label, and which of
  several identical ones. If the page no longer matches, the run stops and says which step failed.
* **A flow stays on the sites it was recorded on.** Its ``domains`` are enforced on every step, and a click
  on something like Buy or Delete asks a person first, exactly as in a normal run.
* **The file is checked before anything runs**: known step kinds only, bounded size, http(s) URLs only.

A flow reads what is on screen; it cannot summarise. Its output is the text of the last ``read`` step, or
the visible text of the final page if there was none.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from selfbrowse.guardrails import Action, AllowedDomains, Block, ConfirmRisky, Guards, SafeUrls
from selfbrowse.handoff import Handler, HandoffRequest

FORMAT_VERSION = 1
MAX_FILE_BYTES = 1_000_000
MAX_STEPS = 300
MAX_TEXT = 2000
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_SECRET_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_SECRET_RE = re.compile(r"<secret:([A-Za-z0-9_]+)>")
_MASKED_RE = re.compile(r"<[A-Z][A-Z_]*_\d+>")          # a masked personal value such as <EMAIL_1>
_PARAM_RE = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")

# What each kind of step needs. "target" is {"role", "text", "nth", "of"}.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "goto": ("url",), "click": ("target",), "type": ("target", "text"), "select": ("target", "option"),
    "press": ("key",), "scroll": (), "back": (), "wait": (), "switch_tab": ("index",), "close_tab": (),
    "read": (), "find": ("text",), "pause": ("reason",),
}
_OPTIONAL = {"submit", "direction", "seconds", "full", "nth"}


class FlowError(ValueError):
    """The flow file is not valid, or a parameter or secret it needs is missing."""


# ── file format ────────────────────────────────────────────────────────────────────

def validate_flow(data: Any) -> dict[str, Any]:
    """Check a flow before using it. Returns it unchanged, or raises :class:`FlowError` saying what is wrong."""
    if not isinstance(data, dict) or data.get("selfbrowse_flow") != FORMAT_VERSION:
        raise FlowError(f"not a selfbrowse flow (expected selfbrowse_flow: {FORMAT_VERSION})")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise FlowError("the flow has no steps")
    if len(steps) > MAX_STEPS:
        raise FlowError(f"the flow has {len(steps)} steps; the limit is {MAX_STEPS}")
    domains = data.get("domains", [])
    if not isinstance(domains, list) or not all(isinstance(d, str) and d for d in domains):
        raise FlowError("domains must be a list of site names")
    params = data.get("params", {})
    if not isinstance(params, dict) or not all(_NAME_RE.match(str(k)) and isinstance(v, dict) for k, v in params.items()):
        raise FlowError("params must map lowercase names to objects")
    secrets = data.get("secrets", [])
    if not isinstance(secrets, list) or not all(isinstance(s, str) and _SECRET_NAME_RE.match(s) for s in secrets):
        raise FlowError("secrets must be a list of names")
    for n, step in enumerate(steps, 1):
        where = f"step {n}"
        if not isinstance(step, dict) or step.get("do") not in _REQUIRED:
            raise FlowError(f"{where}: unknown step kind {step.get('do') if isinstance(step, dict) else step!r}")
        kind = step["do"]
        extra = set(step) - {"do"} - set(_REQUIRED[kind]) - _OPTIONAL
        if extra:
            raise FlowError(f"{where}: unexpected field(s) {', '.join(sorted(extra))}")
        for key in _REQUIRED[kind]:
            if key not in step:
                raise FlowError(f"{where}: {kind} needs {key}")
        for key in ("url", "text", "option", "key", "reason"):
            if key in step and (not isinstance(step[key], str) or len(step[key]) > MAX_TEXT):
                raise FlowError(f"{where}: {key} must be text of at most {MAX_TEXT} characters")
        if "target" in step:
            t = step["target"]
            if not (isinstance(t, dict) and isinstance(t.get("role"), str) and isinstance(t.get("text", ""), str)
                    and isinstance(t.get("nth", 0), int) and isinstance(t.get("of", 1), int)):
                raise FlowError(f"{where}: target needs a role and a label")
        if kind == "goto" and urlparse(step["url"]).scheme not in ("http", "https"):
            raise FlowError(f"{where}: only http(s) addresses are allowed")
        for key in ("text", "option", "url"):
            for name in _PARAM_RE.findall(step.get(key, "")):
                if name not in params:
                    raise FlowError(f"{where}: {{{{{name}}}}} is not a declared parameter")
        for name in _SECRET_RE.findall(step.get("text", "")):
            if name not in secrets:
                raise FlowError(f"{where}: <secret:{name}> is not listed under secrets")
    if any(s["do"] == "goto" for s in steps) and not domains:
        raise FlowError("a flow that opens pages must list its domains")
    return data


def load_flow(path: "str | Path") -> dict[str, Any]:
    p = Path(path).expanduser()
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            raise FlowError(f"{p.name} is larger than {MAX_FILE_BYTES // 1000} KB; not a normal flow")
        data = json.loads(p.read_text())
    except OSError as exc:
        raise FlowError(f"cannot read {p}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise FlowError(f"{p.name} is not valid JSON: {exc}") from exc
    return validate_flow(data)


def save_flow(flow: dict[str, Any], path: "str | Path") -> Path:
    validate_flow(flow)
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(flow, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


# ── recording ──────────────────────────────────────────────────────────────────────

def _host(url: str) -> str:
    """The site name guardrails compare against (no port, no leading www)."""
    return (urlparse(url).hostname or "").removeprefix("www.")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:24]
    return s if s and s[0].isalpha() else ("value" if not s else "v_" + s)[:30]


class FlowRecorder:
    """Collects the actions of one run. The agent feeds it every action that worked."""

    def __init__(self, task: str, start_url: str = "") -> None:
        self.task = task
        self._rows: list[tuple[dict[str, Any], str, str]] = []      # (step, url before, url after)
        self.params: dict[str, dict[str, Any]] = {}
        self.secrets: set[str] = set()
        self.hosts: set[str] = set()
        if start_url.startswith("http"):
            self._rows.append(({"do": "goto", "url": start_url}, "", start_url))
            self.hosts.add(_host(start_url))

    def _param(self, target: dict[str, Any] | None, label: str, value: str, masked: bool) -> str:
        base = _slug((target or {}).get("text", "") or label)
        name, n = base, 2
        while name in self.params:
            name, n = f"{base}_{n}", n + 1
        spec: dict[str, Any] = {"label": ((target or {}).get("text") or label)[:60]}
        if masked:
            spec["required"] = True                    # a personal value: never written to the file
        else:
            spec["default"] = value
        self.params[name] = spec
        return "{{" + name + "}}"

    def add(self, tool: str, args: dict[str, Any], *, url_before: str, url_after: str,
            target: dict[str, Any] | None = None) -> None:
        """Note one action that succeeded. Unrecordable tools (remember, done, ...) are ignored."""
        for u in (url_before, url_after):
            if u.startswith("http"):
                self.hosts.add(_host(u))
        if tool == "back":                                       # going back means the last click was a detour
            if self._rows and self._rows[-1][1] == url_after and self._rows[-1][2] != self._rows[-1][1]:
                self._rows.pop()
                return
            step: dict[str, Any] = {"do": "back"}
        elif tool == "goto":
            step = {"do": "goto", "url": str(args.get("url", ""))}
            if "://" not in step["url"]:
                step["url"] = "https://" + step["url"]
            self.hosts.add(_host(step["url"]))
        elif tool == "click" and target:
            step = {"do": "click", "target": target}
        elif tool == "type" and target:
            text = str(args.get("text", ""))
            if _SECRET_RE.search(text):
                self.secrets.update(_SECRET_RE.findall(text))
            elif _MASKED_RE.search(text):
                text = self._param(target, "value", text, masked=True)
            else:
                text = self._param(target, "value", text, masked=False)
            step = {"do": "type", "target": target, "text": text}
            if args.get("submit"):
                step["submit"] = True
        elif tool == "select" and target:
            step = {"do": "select", "target": target, "option": self._param(target, "choice", str(args.get("option", "")), masked=False)}
        elif tool == "press":
            step = {"do": "press", "key": str(args.get("key", ""))}
        elif tool == "scroll":
            step = {"do": "scroll", "direction": "up" if args.get("direction") == "up" else "down"}
        elif tool == "wait":
            step = {"do": "wait", "seconds": float(args.get("seconds", 2))}
        elif tool == "switch_tab":
            step = {"do": "switch_tab", "index": int(args.get("index", 0))}
        elif tool == "close_tab":
            step = {"do": "close_tab"}
            if args.get("index") is not None:
                step["index"] = int(args["index"])
        elif tool == "find":
            step = {"do": "find", "text": str(args.get("text", ""))[:200]}
            if int(args.get("nth", 1) or 1) > 1:
                step["nth"] = int(args["nth"])
        elif tool == "read":
            step = {"do": "read"}
            if args.get("full"):
                step["full"] = True
        elif tool == "ask_human":
            step = {"do": "pause", "reason": str(args.get("reason", "a person is needed"))[:300]}
        else:
            return
        self._rows.append((step, url_before, url_after))

    def build(self, *, name: str = "", description: str = "") -> dict[str, Any]:
        from selfbrowse import __version__
        steps = [s for s, _, _ in self._rows]
        last_read = max((i for i, s in enumerate(steps) if s["do"] == "read"), default=None)
        steps = [s for i, s in enumerate(steps) if s["do"] != "read" or i == last_read]   # only the last read is the output
        used = {n for s in steps for key in ("text", "option") for n in _PARAM_RE.findall(s.get(key, ""))}
        flow: dict[str, Any] = {
            "selfbrowse_flow": FORMAT_VERSION,
            "name": name or _slug(self.task) or "flow",
            "description": description or self.task,
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "selfbrowse": __version__,
            "domains": sorted(h for h in self.hosts if h),
            "params": {k: v for k, v in self.params.items() if k in used},
            "secrets": sorted(self.secrets),
            "steps": steps,
        }
        return validate_flow(flow)


# ── running ────────────────────────────────────────────────────────────────────────

@dataclass
class FlowResult:
    success: bool
    output: str = ""
    steps_run: int = 0
    total_steps: int = 0
    error: str | None = None
    failed_step: int | None = None          # 1-based number of the step that stopped the run
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def describe_step(step: dict[str, Any], params: "dict[str, str] | None" = None) -> str:
    """One line for a person: ``click button "Search"``."""
    kind = step["do"]
    t = step.get("target")
    label = f' {t["role"]} "{t["text"]}"' if t else ""
    extra = ""
    if kind == "type":
        shown = _SECRET_RE.sub("<secret>", step["text"])
        extra = f' "{_fill(shown, params or {}, keep=True)}"' + (" + Enter" if step.get("submit") else "")
    elif kind == "select":
        extra = f' "{_fill(step["option"], params or {}, keep=True)}"'
    elif kind == "goto":
        extra = f" {step['url']}"
    elif kind in ("press",):
        extra = f" {step['key']}"
    elif kind == "find":
        extra = f' "{step["text"]}"'
    elif kind == "pause":
        extra = f" ({step['reason']})"
    return f"{kind}{label}{extra}"


def _fill(text: str, params: dict[str, str], keep: bool = False) -> str:
    return _PARAM_RE.sub(lambda m: params.get(m.group(1), m.group(0) if keep else ""), text)


class FlowRunner:
    """Plays a flow in a browser. No model is involved.

    Args:
        flow: a loaded flow (see :func:`load_flow`).
        browser: a started :class:`selfbrowse.Browser`.
        params: values for the flow's parameters; the rest use their recorded defaults.
        secrets: ``{"NAME": "value"}`` for the flow's secrets.
        guardrails: extra guardrails. The flow's own domains, http(s)-only and risky-click approval always apply.
        handler: how to ask a person (a risky click, or a ``pause`` step). Without one, those steps stop the run.
        on_step: called with ``(number, total, description)`` before each step.
    """

    def __init__(self, flow: dict[str, Any], browser: Any, *, params: dict[str, str] | None = None,
                 secrets: dict[str, str] | None = None, guardrails: list[Any] | None = None,
                 handler: Handler | None = None, on_step: Callable[[int, int, str], None] | None = None,
                 find_attempts: int = 4) -> None:
        self.flow = validate_flow(flow)
        self.browser = browser
        self.handler = handler
        self.on_step = on_step
        self.find_attempts = max(1, find_attempts)
        self.params = self._resolve_params(params or {})
        self.secrets = dict(secrets or {})
        missing = [s for s in self.flow.get("secrets", []) if s not in self.secrets]
        if missing:
            raise FlowError("this flow needs secret(s) " + ", ".join(missing) +
                            "; set " + " and ".join(f"$SELFBROWSE_SECRET_{m}" for m in missing))
        base = [SafeUrls(), ConfirmRisky()]
        if self.flow.get("domains"):
            base.insert(1, AllowedDomains(self.flow["domains"]))
        self.guards = Guards(base + list(guardrails or []))

    def _resolve_params(self, given: dict[str, str]) -> dict[str, str]:
        spec = self.flow.get("params", {})
        unknown = [k for k in given if k not in spec]
        if unknown:
            raise FlowError(f"unknown parameter(s): {', '.join(unknown)}. This flow has: {', '.join(spec) or 'none'}")
        out: dict[str, str] = {}
        for name, s in spec.items():
            if name in given:
                out[name] = str(given[name])
            elif "default" in s:
                out[name] = str(s["default"])
            else:
                raise FlowError(f"parameter {name!r} has no default; pass --param {name}=VALUE")
        return out

    def run(self) -> FlowResult:
        steps = self.flow["steps"]
        started = time.monotonic()
        result = FlowResult(False, total_steps=len(steps))
        output = ""
        try:
            for n, step in enumerate(steps, 1):
                if self.on_step:
                    self.on_step(n, len(steps), describe_step(step, self.params))
                result.failed_step = n
                text = self._do(step)
                if step["do"] == "read":
                    output = text
                if (hit := self.guards.url(self.browser.url)) and self.browser.url not in ("about:blank", ""):
                    raise _Stop(f"landed on {self.browser.url}, which {hit[0].name} does not allow: {hit[1].reason}")
                result.steps_run = n
            result.failed_step = None
            result.success = True
            result.output = output or self.guards.page(self.browser.visible_text(3000), self.browser.url)
        except _Stop as exc:
            result.error = f"step {result.failed_step} ({describe_step(steps[result.failed_step - 1], self.params)}): {exc}"
        except Exception as exc:                      # a browser failure is a failed step, not a crash
            msg = (str(exc).splitlines() or [type(exc).__name__])[0][:200]
            result.error = f"step {result.failed_step} ({describe_step(steps[(result.failed_step or 1) - 1], self.params)}): {msg}"
        result.seconds = round(time.monotonic() - started, 2)
        return result

    # ── one step ───────────────────────────────────────────────────────────────
    def _do(self, step: dict[str, Any]) -> str:
        b, kind = self.browser, step["do"]
        if kind == "goto":
            url = _fill(step["url"], self.params)
            if hit := self.guards.url(url):
                raise _Stop(f"{hit[0].name}: {hit[1].reason}")
            return f"opened {b.goto(url)}"
        if kind in ("click", "type", "select"):
            ref, t = self._find(step["target"])
            text = _fill(step.get("text", ""), self.params)
            act = Action(kind, {"ref": ref}, b.url, role=t["role"], text=t.get("text", ""))
            self._approve(act)
            if kind == "click":
                return b.click_ref(ref)
            if kind == "select":
                return b.select_ref(ref, _fill(step["option"], self.params))
            text = _SECRET_RE.sub(lambda m: self.secrets[m.group(1)], text)
            b.click_ref(ref)
            b.type_text(text, clear=True)
            if step.get("submit"):
                b.press("Enter")
            return "typed"
        if kind == "press":
            return b.press(step["key"])
        if kind == "scroll":
            return b.scroll(step.get("direction", "down"))
        if kind == "back":
            return b.back()
        if kind == "wait":
            return b.wait(step.get("seconds", 2))
        if kind == "switch_tab":
            return b.switch_tab(step["index"])
        if kind == "close_tab":
            return b.close_tab(step.get("index"))
        if kind == "find":
            return b.find_text(_fill(step["text"], self.params), int(step.get("nth", 1)))
        if kind == "read":
            return self.guards.page(b.visible_text(12000, whole=True) if step.get("full") else b.visible_text(), b.url)
        if kind == "pause":
            self._ask("model", step["reason"])
            return "continued"
        raise _Stop(f"unknown step {kind}")

    def _find(self, target: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        for attempt in range(self.find_attempts):
            ref = self.browser.find_ref(target["role"], target.get("text", ""), target.get("nth", 0), target.get("of", 1))
            if ref is not None:
                return ref, target
            if attempt + 1 < self.find_attempts:
                self.browser.wait(0.8)                 # the page may still be loading
        label = f'{target["role"]} "{target.get("text", "")}"'
        raise _Stop(f"could not find {label} on {self.browser.url}; the site may have changed. Record the flow again")

    def _approve(self, act: Action) -> None:
        hit = self.guards.action(act)
        if not hit:
            return
        g, d = hit
        if isinstance(d, Block):
            raise _Stop(f"blocked by {g.name}: {d.reason}")
        self._ask("confirm", d.reason)

    def _ask(self, kind: str, reason: str) -> None:
        if self.handler is None:
            raise _Stop(f"{reason}, and no person is available to approve it. Run with --headed")
        self.browser.bring_to_front()
        if not self.handler(HandoffRequest(kind, reason, self.browser.url)):
            raise _Stop("the person did not approve")


class _Stop(Exception):
    """A step that cannot or must not go on; the message says why."""


def run_flow(flow: "str | Path | dict[str, Any]", *, params: dict[str, str] | None = None,
             secrets: dict[str, str] | None = None, browser: Any = None, headless: bool = True,
             **kwargs: Any) -> FlowResult:
    """Load (if given a path) and run a flow. Opens and closes a browser unless you pass one."""
    data = load_flow(flow) if isinstance(flow, (str, Path)) else flow
    own = browser is None
    if own:
        from selfbrowse.browser import Browser
        browser = Browser(headless=headless)
    try:
        if own:
            browser.start()
        return FlowRunner(data, browser, params=params, secrets=secrets, **kwargs).run()
    finally:
        if own:
            browser.close()
