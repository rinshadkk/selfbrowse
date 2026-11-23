"""Local backend for the Selfbrowse desktop app.

Electron starts this process, reads the ``READY <port>`` line it prints, and talks to it over
127.0.0.1. Every request must carry the one-time token Electron put in ``SB_DESKTOP_TOKEN``.
It only uses the public ``selfbrowse`` API; nothing in the library is modified.
"""
from __future__ import annotations

import argparse
import importlib.util
import asyncio
import json
import os
import queue
import re
import secrets
import subprocess
import shutil
import socket
import time
import signal
import sys
import threading
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Literal

import uvicorn
from datetime import datetime, timezone
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from live import Input, LiveView, MirrorLLM, Stopped
from selfbrowse import Browser, BrowseAgent
from selfbrowse.llm import make_llm
from selfbrowse.guardrails import Budget, ConfirmRisky, Guardrail, PresidioRedact, RedactPII, build_guards
from selfbrowse.handoff import HandoffRequest
from selfbrowse.flow import FlowError, FlowRunner, describe_step, load_flow, save_flow, validate_flow

import addons
import atexit
import record


@dataclass
class Session:
    """What outlives one turn of a run: the browser, the model's record, the vault and what was said. A follow-up
    continues in this same browser and run instead of starting a new one."""
    req: Any
    browser: Any
    llm: Any
    vault: Any = None
    turns: list[dict[str, str]] = field(default_factory=list)       # {"task", "answer"} for each finished turn
    idle_since: float | None = None
    cmds: "queue.Queue[Any]" = field(default_factory=queue.Queue)   # follow-ups (a string) or None (close), for the run's own thread
    ended: threading.Event = field(default_factory=threading.Event) # set when that thread has closed the browser and finished


@dataclass
class Run:
    id: str
    prompt: str
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    live: LiveView = field(default_factory=LiveView)
    flow_path: Path | None = None
    started: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)      # for the history: kind, model, flow name, whether to keep it
    session: Session | None = None

    @property
    def stop(self) -> threading.Event:
        return self.live.stop

    def emit(self, event: dict[str, Any]) -> None:
        if len(self.events) < MAX_EVENTS or event.get("type") == "done":
            self.events.append(event)


class BrowserOptions(BaseModel):
    profile: bool = True                 # keep cookies and logins between runs, in a folder in the app's data
    chrome: bool = True                  # use the Chrome installed on this computer, if there is one
    stealth: bool = False                # Patchright: hides common automation tells (needs selfbrowse[stealth])


class CustomSource(BaseModel):
    """Any server that speaks the OpenAI chat API: a company gateway, vLLM, LiteLLM, a cloud endpoint."""
    base_url: str = Field(max_length=300, pattern=r"^https?://[^\s]+$")
    api: Literal["openai", "anthropic"] = "openai"   # which API the server speaks: /v1/chat/completions or /v1/messages
    json_mode: bool = False              # force JSON actions, for models without reliable tool calling


_DOMAIN = r"^[A-Za-z0-9*.-]{1,253}$"


class GuardSettings(BaseModel):
    """Every guardrail the library offers, as the person set them under Guardrails. Off or empty means not applied."""
    safe_urls: bool = True               # only http(s) pages: no file:, chrome:, data:, javascript:
    allow: list[str] = Field(default_factory=list, max_length=100)    # only these sites (and their subdomains)
    block: list[str] = Field(default_factory=list, max_length=100)    # never these sites
    confirm_risky: bool = False          # ask before Buy, Pay, Delete, Send, Sign out, uploads and risky dialogs
    risky_words: list[str] | None = Field(default=None, max_length=200)   # words that make a click "risky"; None = the library's list
    watch_injection: bool = False        # warn the model about instruction-like page text, ask before acting on it
    redact: list[Literal["email", "phone", "ssn", "card"]] = Field(default_factory=list)    # mask these in page text
    restore: bool = True                 # type masked values back where the model needs them (else mask for good)
    page_presidio: bool = False          # also mask names and more in page text with Presidio
    max_tokens: int | None = Field(default=None, ge=1_000, le=50_000_000)
    max_seconds: int | None = Field(default=None, ge=10, le=86_400)
    max_usd: float | None = Field(default=None, gt=0, le=10_000)
    price_in: float | None = Field(default=None, ge=0, le=10_000)     # USD per million input tokens, for max_usd
    price_out: float | None = Field(default=None, ge=0, le=10_000)

    @field_validator("allow", "block")
    @classmethod
    def _check_domains(cls, v: list[str]) -> list[str]:
        out = []
        for d in v:
            d = d.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
            if not d:
                continue
            if not re.fullmatch(_DOMAIN, d):
                raise ValueError(f"{d!r} is not a site name")
            out.append(d)
        return out

    @field_validator("risky_words")
    @classmethod
    def _check_words(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out: list[str] = []
        for w in v:
            w = " ".join(w.strip().lower().split())
            if not w:
                continue
            if len(w) > 40:
                raise ValueError("a word to ask about is too long")
            if w not in out:
                out.append(w)
        return out

    @model_validator(mode="after")
    def _usd_needs_price(self) -> "GuardSettings":
        if self.max_usd and (self.price_in is None or self.price_out is None):
            raise ValueError("a dollar limit needs the model's prices")
        return self

    def build(self) -> list[Guardrail]:
        guards = build_guards(allow=self.allow, block=self.block, confirm_risky=self.confirm_risky,
                              redact_pii=bool(self.redact), watch_injection=self.watch_injection,
                              max_tokens=self.max_tokens, max_seconds=self.max_seconds,
                              presidio=self.page_presidio, restore=self.restore)
        for g in guards:
            if isinstance(g, PresidioRedact) and not record.presidio_in_python():
                g._analyzer = addons.RemoteAnalyzer()          # the packaged app: ask the downloaded add-on
            if isinstance(g, RedactPII):
                g.kinds = tuple(k for k in RedactPII.ALL if k in self.redact)
            if isinstance(g, ConfirmRisky) and self.risky_words is not None:
                # whole words, so "pay" does not match "payment"; an empty list means only uploads and dialogs ask
                g.pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in self.risky_words) + r")\b", re.I) if self.risky_words else re.compile(r"(?!x)x")
        if self.max_usd and self.price_in is not None and self.price_out is not None:
            guards.append(Budget(max_usd=self.max_usd, price=(self.price_in, self.price_out)))
        return guards


class RunRequest(BrowserOptions):
    prompt: str = Field(max_length=10_000)
    model: str = Field(default="anthropic:claude-haiku-5-5", max_length=100, pattern=r"^[A-Za-z0-9_.:/@+-]+$")
    headed: bool = False                 # the live view is the browser window; this opens a separate one too
    max_steps: int = Field(default=40, ge=1, le=100)
    custom: CustomSource | None = None   # when set, "model" is just the model's name on this server
    api_key: str = Field(default="", max_length=500)   # overrides the provider's environment variable
    history: bool = True                 # keep a summary of this run under History
    presidio: bool = False               # also look for personal data with Microsoft Presidio
    review: bool = False                 # hold each model call until the person approves it (same as review_mode always)
    review_mode: Literal["off", "flagged", "always"] = "off"    # off, only when something looks personal, or every call
    guards: GuardSettings = Field(default_factory=GuardSettings)
    sensitive: dict[str, str] = Field(default_factory=dict)      # values from My info; typed locally, never sent
    labels: dict[str, str] = Field(default_factory=dict)         # what each is, "Form > Field"; given to the model only on request

    @field_validator("labels")
    @classmethod
    def _check_labels(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 100 or any(not re.fullmatch(r"[A-Za-z0-9_]{1,64}", k) or len(x) > 120 for k, x in v.items()):
            raise ValueError("bad labels")
        return v

    @field_validator("sensitive")
    @classmethod
    def _check_sensitive(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 100 or any(not re.fullmatch(r"[A-Za-z0-9_]{1,64}", k) or len(x) > 500 for k, x in v.items()):
            raise ValueError("bad sensitive values")
        return v


MAX_EVENTS = 2_000          # per run: a runaway loop cannot grow memory without bound
MAX_RUNS_KEPT = 20          # finished runs we keep so a late reader can still get the answer


def data_dir() -> Path:
    """Where flows live. Electron passes its per-user folder; the default is for running the backend alone."""
    d = Path(os.environ.get("SB_DESKTOP_DATA") or Path.home() / ".selfbrowse-desktop")
    d.mkdir(parents=True, exist_ok=True)
    return d


def installed_chrome() -> bool:
    """Is Google Chrome installed here? Playwright can drive it with channel="chrome"."""
    if sys.platform == "darwin":
        return Path("/Applications/Google Chrome.app").exists() or (Path.home() / "Applications/Google Chrome.app").exists()
    if sys.platform.startswith("win"):
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        return any(r and (Path(r) / "Google/Chrome/Application/chrome.exe").exists() for r in roots)
    return any(shutil.which(n) for n in ("google-chrome", "google-chrome-stable"))


FROZEN = bool(getattr(sys, "frozen", False))    # the packaged app: no pip, so optional packages cannot be added


def stealth_installed() -> bool:
    return importlib.util.find_spec("patchright") is not None


def profile_dir() -> Path:
    return data_dir() / "browser-profile"


def free_profile(d: Path) -> None:
    """Chrome refuses a profile that another Chrome has open. A Chrome left behind by an earlier run (the app was
    closed or crashed mid-run) holds it forever, so every later run fails. Close it, but only if it is ours: its
    command line must name this profile folder. A lock whose process is gone is just removed."""
    lock = d / "SingletonLock"
    if not lock.is_symlink():
        return
    try:
        pid = int(os.readlink(lock).rsplit("-", 1)[1])
    except (OSError, ValueError, IndexError):
        pid = 0
    alive = False
    if pid > 0:
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            pass
        except PermissionError:
            raise RuntimeError("The browser profile is open in a program this app cannot close.")
    if alive:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
        if str(d) not in cmd:
            raise RuntimeError("The browser profile is in use by another browser. Close it and try again.")
        for sig, wait in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 2.0)):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                break
            end = time.time() + wait
            while time.time() < end:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                continue
            break
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            (d / name).unlink()
        except FileNotFoundError:
            pass


def make_browser(o: BrowserOptions, headed: bool = False) -> Browser:
    """The browser for a run, set up so it looks less like automation: a real profile, the real Chrome."""
    kw: dict[str, Any] = {"headless": not headed}
    if o.profile:
        free_profile(profile_dir())
        kw["user_data_dir"] = profile_dir()
    if o.chrome and installed_chrome():
        kw["channel"] = "chrome"
    if o.stealth:
        kw["stealth"] = True
    return Browser(**kw)


def check_browser_options(o: BrowserOptions) -> None:
    if o.stealth and FROZEN:
        raise HTTPException(status_code=400, detail="Stealth mode is not included in the packaged app.")
    if o.stealth and not stealth_installed():
        raise HTTPException(status_code=400, detail="Stealth mode needs one more package. In the desktop folder run: "
                            "backend/.venv/bin/pip install 'patchright' and then 'backend/.venv/bin/patchright install chromium'.")


def build_llm(req: "RunRequest") -> Any:
    if req.custom and req.custom.api == "anthropic":
        from selfbrowse.llm.anthropic import AnthropicLLM
        base = req.custom.base_url.rstrip("/")
        base = base[:-3] if base.endswith("/v1") else base                # the Anthropic client adds /v1 itself
        return AnthropicLLM(req.model, api_key=req.api_key or "not-needed", base_url=base)
    if req.custom:
        from selfbrowse.llm.openai_compat import OpenAICompatLLM
        return OpenAICompatLLM(req.model, api_key=req.api_key or None, base_url=req.custom.base_url,
                               require_key=False, json_mode=req.custom.json_mode)
    return make_llm(req.model, **({"api_key": req.api_key} if req.api_key else {}))


def check_presidio(req: "RunRequest") -> None:
    if not (req.presidio or getattr(getattr(req, "guards", None), "page_presidio", False)):
        return
    if not record.presidio_available():
        raise HTTPException(status_code=400, detail=(
            "Presidio is not installed. Open the Run screen, press the ⋯ menu and choose Install next to Presidio." if FROZEN else
            "Presidio is not installed. Turn it on in the app and press Install, or run backend/.venv/bin/pip install "
            "presidio-analyzer and then backend/.venv/bin/python -m spacy download en_core_web_sm."))
    if not record.presidio_in_python():                    # start the add-on now, so a broken one stops the run here
        try:
            addons.SIDECAR.ensure()
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


# ── history: a summary of each finished run, kept on this computer ─────────────────────────────────
SHARED_MARK = "\n\nMy details you may use:"
SAVED_MARK = "\n\nMy saved details"      # the app appends My info the person allowed the model to see; not kept
_HISTORY_ID = re.compile(r"^[0-9a-f]{12}$")
MAX_HISTORY = 500


def _model_label(req: "RunRequest") -> str:
    if req.custom:
        return f"{urlparse(req.custom.base_url).netloc} · {req.model}"
    return req.model.replace(":", " · ", 1)


def history_dir() -> Path:
    d = data_dir() / "history"
    d.mkdir(exist_ok=True)
    return d


def remember(run: Run) -> None:
    """Write what the person would want to look back on: the task, the outcome, the steps and the cost. Not the
    pages or what was sent to the model; that was shown live and is not kept."""
    if not run.meta.get("keep", True):
        return
    try:
        done = next((e for e in reversed(run.events) if e.get("type") == "done"), {})
        steps = [{"n": e["number"], "tool": str(e.get("tool", ""))[:200],
                  "result": str(e.get("result", "")).split("\n")[0][:200],
                  "url": (lambda u: f"{u.scheme}://{u.netloc}{u.path[:80]}" if u.netloc else "")(urlparse(str(e.get("url", ""))))}
                 for e in run.events if e.get("type") == "step"][:150]
        used = [e["usage"] for e in run.events if e.get("type") == "call_done" and e.get("usage")]
        rec = {"id": run.id, "kind": run.meta.get("kind", "run"), "flow": run.meta.get("flow", ""),
               "prompt": run.prompt[:2000], "model": run.meta.get("model", ""),
               "started": datetime.fromtimestamp(run.started, timezone.utc).isoformat(timespec="seconds"),
               "seconds": round(time.time() - run.started, 1),
               "success": bool(done.get("success")), "stopped": done.get("error") == "Stopped by you.",
               "answer": str(done.get("output", ""))[:4000], "error": str(done.get("error") or "")[:500],
               "calls": len(used), "input_tokens": sum(u.get("input", 0) + u.get("cache_read", 0) + u.get("cache_write", 0) for u in used),
               "output_tokens": sum(u.get("output", 0) for u in used), "steps": steps}
        (history_dir() / f"{run.id}.json").write_text(json.dumps(rec, ensure_ascii=False))
        files = sorted(history_dir().glob("*.json"), key=lambda p: p.stat().st_mtime)
        for old in files[:-MAX_HISTORY]:
            old.unlink(missing_ok=True)
    except Exception:
        pass                                            # history is a convenience; it must never break a run


RUNS: dict[str, Run] = {}
_TOKEN = os.environ.get("SB_DESKTOP_TOKEN") or secrets.token_urlsafe(24)
_RUN_LOCK = threading.Lock()


def _auth(authorization: str = Header(default="")) -> None:
    """Header only: a token in a URL would end up in logs and history."""
    given = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(given.encode(), _TOKEN.encode()):
        raise HTTPException(status_code=401, detail="bad token")


app = FastAPI(title="Selfbrowse desktop backend", docs_url=None, redoc_url=None, openapi_url=None)
# A web page that tricks the browser into resolving its own name to 127.0.0.1 (DNS rebinding) sends
# that name in Host, so refuse anything that is not a loopback name.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
# The window loads from file://, whose Origin is "null". Only that origin may read responses, and the
# token is still required on every call.
app.add_middleware(CORSMiddleware, allow_origins=["null"], allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"])


class HoldsValues(Guardrail):
    """Changes nothing on a page. Its presence gives the agent a vault, so a value masked at review time becomes a
    placeholder like <EMAIL_1> that is typed back for the model on the right site and restored in the answer."""
    reversible = True


def _work(run: Run, req: RunRequest) -> None:
    """The first turn of a run: open the browser and the model's record, then do the task."""
    try:
        browser = make_browser(req, req.headed)
        run.live.mode = req.review_mode if req.review_mode != "off" else ("always" if req.review else "off")
        llm = MirrorLLM(build_llm(req), run.live, lambda: browser,
                        on_pause=lambda paused: run.emit({"type": "paused", "paused": paused}),
                        emit=run.emit, secrets=req.sensitive, presidio=req.presidio)
        tmp = data_dir() / "tmp"
        tmp.mkdir(exist_ok=True)
        run.flow_path = tmp / f"{run.id}.json"
        run.session = Session(req=req, browser=browser, llm=llm)
    except Exception as exc:                           # a bad key, a missing model, a browser that will not start
        run.emit({"type": "done", "success": False, "output": "", "steps": 0, "tokens": 0,
                  "error": f"{type(exc).__name__}: {exc}"[:500]})
        remember(run)
        run.finished = True
        _RUN_LOCK.release()
        return
    s = run.session
    try:
        _execute(run, req.prompt, first=True)
        # The browser stays open for a follow-up. Playwright belongs to the thread that started it, so every later turn
        # (and closing the browser) happens here, in this same thread.
        while True:
            try:
                cmd = s.cmds.get(timeout=1)
            except queue.Empty:
                if s.idle_since is not None and time.time() - s.idle_since > IDLE_SECONDS:
                    break
                continue
            if cmd is None:
                break
            _execute(run, _followup_task(run, s, cmd), first=False)
    finally:
        run.session = None
        try:
            s.browser.close()
        except Exception:
            pass
        s.ended.set()


def _followup_task(run: Run, s: Session, prompt: str) -> str:
    try:
        url = s.browser.url
    except Exception:
        url = "(unknown)"
    first = s.turns[0] if s.turns else {"task": run.prompt, "answer": ""}
    last = s.turns[-1] if s.turns else first
    return (f"This continues an earlier task in the same browser.\nEarlier task: {first['task'][:1500]}\n"
            f"Your last answer: {last['answer'][:3000] or '(none)'}\nThe browser is on {url}.\n\n"
            f"The person now says: {prompt}")


def _execute(run: Run, task: str, *, first: bool) -> None:
    """One turn: the first task, or a follow-up in the same browser. Releases the run lock when it ends."""
    s = run.session
    assert s is not None
    req = s.req
    s.idle_since = None

    def on_step(step: Any) -> None:
        run.emit({"type": "step", "number": step.number, "tool": step.tool, "input": step.input,
                  "result": step.result, "url": step.url, "cached": step.from_cache})
        if run.stop.is_set():
            raise Stopped()

    def hand_off(request: HandoffRequest) -> bool:
        """The agent needs the person (bot check, login, approval): hand over the live view and wait."""
        run.live.handoff, run.live.control = None, True
        run.emit({"type": "handoff", "kind": request.kind, "reason": request.reason, "url": request.url})
        run.live.wait_while(s.browser, lambda: run.live.handoff is None)
        run.live.control = False
        run.emit({"type": "control", "on": False})
        return bool(run.live.handoff)

    answer = ""
    try:
        if not first:
            run.live.stop.clear()
        agent = BrowseAgent(task, llm=s.llm, browser=s.browser, max_steps=req.max_steps,
                            on_step=on_step, handoff=hand_off, sensitive=req.sensitive, sensitive_hints=req.labels or None,
                            save_flow=run.flow_path if first else None,        # a follow-up starts mid-way: not a replayable flow
                            safe_urls=req.guards.safe_urls,
                            guardrails=([HoldsValues()] if run.live.mode != "off" else []) + req.guards.build())
        v = agent.guards.vault
        if v is not None:                                # one vault for the whole run, so <EMAIL_1> means the same later
            if s.vault is None:
                s.vault = v
            else:
                agent.guards.vault = s.vault
                for g in agent.guards.items:
                    if getattr(g, "reversible", False):
                        g.vault = s.vault
        s.llm.get_vault = lambda: s.vault
        r = agent.run()
        answer = r.output or ""
        run.emit({"type": "done", "success": r.success, "output": r.output, "steps": r.steps,
                  "tokens": r.usage.total_input + r.usage.output_tokens, "error": r.error,
                  "can_save_flow": bool(first and r.success and run.flow_path and run.flow_path.exists())})
    except Stopped:
        run.emit({"type": "done", "success": False, "output": "", "steps": len(run.events), "tokens": 0,
                  "error": "Stopped by you."})
    except Exception as exc:                           # a bad key, a missing model, a crash: show it, don't die
        run.emit({"type": "done", "success": False, "output": "", "steps": 0, "tokens": 0,
                  "error": f"{type(exc).__name__}: {exc}"[:500]})
    finally:
        s.turns.append({"task": task, "answer": answer})
        s.idle_since = time.time()
        remember(run)
        run.finished = True
        _RUN_LOCK.release()


def close_session(run: Run) -> None:
    """Ask the run's own thread to close its browser, and wait for it, so the profile is free when this returns."""
    s = run.session
    if s is not None and not s.ended.is_set():
        s.cmds.put(None)
        s.ended.wait(20)
    run.session = None


def close_idle_sessions(max_age: float | None = None) -> int:
    """Close the browsers of runs that are not doing anything (all of them, or only those idle for ``max_age`` seconds)."""
    n = 0
    for run in list(RUNS.values()):
        s = run.session
        if s is not None and run.finished and (max_age is None or (s.idle_since and time.time() - s.idle_since > max_age)):
            close_session(run)
            n += 1
    return n


IDLE_SECONDS = 600          # an answered run keeps its browser this long for a follow-up


class FollowUp(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


@app.post("/runs/{run_id}/followup", dependencies=[Depends(_auth)])
def follow_up(run_id: str, req: FollowUp) -> dict[str, Any]:
    """Carry on in the same run: same browser, on the page it ended on, with what was said before."""
    run = _get_run(run_id)
    s = run.session
    if s is None or not run.finished or s.ended.is_set():
        raise HTTPException(status_code=409, detail="This run can no longer take a follow-up (it is still working, or its browser was closed).")
    if not _RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A run is already in progress. Stop it or wait for it to finish.")
    start = len(run.events)
    run.finished = False
    run.emit({"type": "turn", "n": len(s.turns) + 1, "prompt": req.prompt})
    s.cmds.put(req.prompt)
    return {"after": start}


@app.post("/runs/{run_id}/close", dependencies=[Depends(_auth)])
def close_run(run_id: str) -> dict[str, bool]:
    run = _get_run(run_id)
    if run.session is not None and run.finished:
        close_session(run)
    return {"closed": run.session is None}


@app.post("/sessions/close", dependencies=[Depends(_auth)])
def close_all_sessions() -> dict[str, int]:
    """Before the app quits: close every browser a finished run is keeping for a follow-up."""
    return {"closed": close_idle_sessions()}


@app.get("/history", dependencies=[Depends(_auth)])
def list_history() -> list[dict[str, Any]]:
    out = []
    for p in sorted(history_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            r = json.loads(p.read_text())
            out.append({k: r[k] for k in ("id", "kind", "flow", "prompt", "model", "started", "seconds", "success", "stopped",
                                          "calls", "input_tokens", "output_tokens")} | {"steps": len(r.get("steps", []))})
        except Exception:
            continue
    return out


@app.get("/history/{item_id}", dependencies=[Depends(_auth)])
def get_history(item_id: str) -> dict[str, Any]:
    p = history_dir() / f"{item_id}.json"
    if not _HISTORY_ID.fullmatch(item_id) or not p.is_file():
        raise HTTPException(status_code=404, detail="no such run")
    return json.loads(p.read_text())


@app.delete("/history/{item_id}", dependencies=[Depends(_auth)])
def delete_history(item_id: str) -> dict[str, bool]:
    if not _HISTORY_ID.fullmatch(item_id):
        raise HTTPException(status_code=404, detail="no such run")
    (history_dir() / f"{item_id}.json").unlink(missing_ok=True)
    return {"deleted": True}


@app.delete("/history", dependencies=[Depends(_auth)])
def clear_history() -> dict[str, int]:
    n = 0
    for p in history_dir().glob("*.json"):
        p.unlink(missing_ok=True)
        n += 1
    return {"deleted": n}


@app.get("/health", dependencies=[Depends(_auth)])
def health() -> dict[str, str]:
    return {"status": "ok"}


atexit.register(addons.SIDECAR.stop)             # the downloaded Presidio program quits with the backend
PRESIDIO_JOB: dict[str, Any] = {"state": "idle", "error": ""}       # idle | running | done | error
_PRESIDIO_STEPS = [["-m", "pip", "install", "--disable-pip-version-check", "presidio-analyzer"],
                   ["-m", "spacy", "download", record.PRESIDIO_MODEL]]


def _install_presidio() -> None:
    try:
        for step in _PRESIDIO_STEPS:
            r = subprocess.run([sys.executable, *step], capture_output=True, text=True, timeout=1800)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1][:300] if (r.stderr or r.stdout).strip() else "install failed")
        importlib.invalidate_caches()
        PRESIDIO_JOB.update(state="done" if record.presidio_available() else "error",
                            error="" if record.presidio_available() else "Installed, but Presidio still cannot be loaded. Restart the app.")
    except Exception as exc:
        PRESIDIO_JOB.update(state="error", error=str(exc)[:300])


class PresidioInstall(BaseModel):
    consent: bool = False        # the person agreed to the download in the app


@app.post("/presidio/install", dependencies=[Depends(_auth)])
def presidio_install(body: PresidioInstall | None = None) -> dict[str, Any]:
    """Make Presidio available. From source: pip install into this Python. Packaged: download the add-on program."""
    if record.presidio_available():
        return presidio_status()
    if FROZEN:
        if not (body and body.consent):
            raise HTTPException(status_code=400, detail="Downloading the add-on needs the person's OK. Use the Install button in the app.")
        try:
            return addons.start_install()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    if PRESIDIO_JOB["state"] == "running":
        raise HTTPException(status_code=409, detail="Presidio is already being installed.")
    PRESIDIO_JOB.update(state="running", error="")
    threading.Thread(target=_install_presidio, daemon=True).start()
    return dict(PRESIDIO_JOB)


@app.get("/presidio/install", dependencies=[Depends(_auth)])
def presidio_status() -> dict[str, Any]:
    if FROZEN:
        return addons.status()
    return {"state": "done" if record.presidio_available() else PRESIDIO_JOB["state"], "error": PRESIDIO_JOB["error"]}


@app.delete("/presidio/install", dependencies=[Depends(_auth)])
def presidio_remove() -> dict[str, Any]:
    """Stop a download in progress, or delete the installed add-on to free its disk space."""
    if not FROZEN:
        raise HTTPException(status_code=400, detail="Presidio is installed in Python here. Remove it with pip uninstall.")
    if addons.JOB["state"] == "running":
        addons.cancel()
    else:
        addons.remove()
    return addons.status()


# ── models installed on this computer ──────────────────────────────────────────────────────────
def _local_base(kind: str) -> str:
    """Where Ollama or LM Studio listens. OLLAMA_HOST may move Ollama, but only to this computer."""
    default = {"ollama": "http://127.0.0.1:11434", "lmstudio": "http://127.0.0.1:1234"}[kind]
    host = os.environ.get("OLLAMA_HOST", "") if kind == "ollama" else ""
    if host:
        url = host if "://" in host else f"http://{host}"
        if (urlparse(url).hostname or "") in ("127.0.0.1", "localhost", "::1"):
            return url.rstrip("/")
    return default


@app.get("/local-models/{kind}", dependencies=[Depends(_auth)])
def local_models(kind: Literal["ollama", "lmstudio"]) -> dict[str, Any]:
    """What is installed in Ollama or LM Studio right now, so the person picks a model instead of typing its name."""
    import urllib.request
    base = _local_base(kind)
    label = "Ollama" if kind == "ollama" else "LM Studio"
    try:
        with urllib.request.urlopen(f"{base}/api/tags" if kind == "ollama" else f"{base}/v1/models", timeout=2) as res:
            data = json.loads(res.read(2_000_000))
    except Exception:
        return {"ok": False, "models": [], "error": f"{label} is not running at {base}. Start it, then refresh."}
    if kind == "ollama":
        items = [{"name": m["name"], "size": m.get("size", 0)} for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
    else:
        items = [{"name": m["id"], "size": 0} for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
    return {"ok": True, "models": sorted(items, key=lambda m: m["name"])[:200], "error": ""}


@app.get("/browser-info", dependencies=[Depends(_auth)])
def browser_info() -> dict[str, Any]:
    p = profile_dir()
    size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
    return {"chrome": installed_chrome(), "stealth": stealth_installed(), "presidio": record.presidio_available(),
            "profile_bytes": size, "packaged": FROZEN}


@app.post("/browser-data/clear", dependencies=[Depends(_auth)])
def clear_browser_data() -> dict[str, bool]:
    """Forget every login and cookie the agent's browser has kept. Only when no run is using the profile."""
    if not _RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A run is in progress. Stop it first.")
    close_idle_sessions()                              # its browser holds the profile open
    try:
        p = profile_dir().resolve()
        if p.exists() and p.parent == data_dir().resolve():     # only ever the one folder we made
            shutil.rmtree(p)
    finally:
        _RUN_LOCK.release()
    return {"cleared": True}


@app.post("/runs", dependencies=[Depends(_auth)])
def start_run(req: RunRequest) -> dict[str, str]:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Type a prompt first.")
    check_browser_options(req)
    check_presidio(req)
    if not _RUN_LOCK.acquire(blocking=False):          # one run at a time: each one drives a real browser
        raise HTTPException(status_code=409, detail="A run is already in progress. Stop it or wait for it to finish.")
    close_idle_sessions()                              # an answered run's browser may still hold the profile
    run = Run(id=uuid.uuid4().hex[:12], prompt=req.prompt.split(SHARED_MARK)[0].split(SAVED_MARK)[0].strip())
    run.meta = {"kind": "run", "model": _model_label(req), "keep": req.history}
    for old in [r for r in RUNS.values() if r.finished][:-MAX_RUNS_KEPT]:
        close_session(old)
        RUNS.pop(old.id, None)
    RUNS[run.id] = run
    threading.Thread(target=_work, args=(run, req), daemon=True).start()
    return {"id": run.id}


@app.post("/runs/{run_id}/stop", dependencies=[Depends(_auth)])
def stop_run(run_id: str) -> dict[str, bool]:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="no such run")
    run.stop.set()
    return {"stopping": not run.finished}


def _get_run(run_id: str) -> Run:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="no such run")
    return run


class ControlRequest(BaseModel):
    on: bool


class HandoffAnswer(BaseModel):
    resume: bool


@app.post("/runs/{run_id}/control", dependencies=[Depends(_auth)])
def control(run_id: str, req: ControlRequest) -> dict[str, bool]:
    """Take over the browser (the agent pauses before its next model call) or hand it back."""
    run = _get_run(run_id)
    if run.finished:
        raise HTTPException(status_code=409, detail="This run has finished.")
    run.live.control = req.on
    run.emit({"type": "control", "on": req.on})
    return {"on": req.on}


@app.post("/runs/{run_id}/input", dependencies=[Depends(_auth)])
def send_input(run_id: str, events: list[Input]) -> dict[str, int]:
    run = _get_run(run_id)
    if not run.live.control:
        raise HTTPException(status_code=409, detail="Take control first.")
    if len(events) > 50:
        raise HTTPException(status_code=422, detail="Too many events in one call.")
    run.live.inputs.extend(events)
    return {"queued": len(events)}


@app.post("/runs/{run_id}/handoff", dependencies=[Depends(_auth)])
def answer_handoff(run_id: str, req: HandoffAnswer) -> dict[str, bool]:
    _get_run(run_id).live.handoff = req.resume
    return {"resume": req.resume}


class ReviewRequest(BaseModel):
    on: bool | None = None                              # the older switch: on means every call
    mode: Literal["off", "flagged", "always"] | None = None


class CallAnswer(BaseModel):
    send: bool
    mask: bool = False                                  # send, with what looks personal replaced
    replace: list[str] | None = Field(default=None, max_length=200)   # with mask: which flagged texts (None: all)


class SaveFlow(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    edited: dict[str, Any] | None = None   # the person's reviewed "params" and "steps"; the rest comes from the run


@app.post("/runs/{run_id}/review", dependencies=[Depends(_auth)])
def set_review(run_id: str, req: ReviewRequest) -> dict[str, Any]:
    """Change the review before sending while a run is going: off, only when something looks personal, or every call."""
    live = _get_run(run_id).live
    live.mode = req.mode if req.mode is not None else ("always" if req.on else "off")
    return {"mode": live.mode, "on": live.mode != "off"}


@app.post("/runs/{run_id}/call", dependencies=[Depends(_auth)])
def answer_call(run_id: str, req: CallAnswer) -> dict[str, Any]:
    """Send the held model call (as it is, or with what looks personal replaced), or refuse it (which stops the run)."""
    decision = ("redact" if req.mask else "send") if req.send else "stop"
    live = _get_run(run_id).live
    live.replace = [r[:500] for r in req.replace] if req.replace is not None else None
    live.decision = decision
    return {"send": req.send, "mask": req.mask and req.send}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "flow"


def _flow_file(flow_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{1,60}", flow_id):
        raise HTTPException(status_code=404, detail="no such flow")
    p = data_dir() / "flows" / f"{flow_id}.json"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="no such flow")
    return p


def _summary(flow_id: str, flow: dict[str, Any]) -> dict[str, Any]:
    return {"id": flow_id, "name": flow.get("name", flow_id), "description": flow.get("description", ""),
            "created": flow.get("created", ""), "steps": len(flow["steps"]), "domains": flow.get("domains", []),
            "secrets": flow.get("secrets", []),
            "params": {k: {"label": v.get("label", k), "default": v.get("default"), "required": bool(v.get("required"))}
                       for k, v in flow.get("params", {}).items()}}


# ── asking the model which typed values should be inputs ────────────────────────────────────────
class SuggestRequest(RunRequest):
    """The model to ask, how to mask, and the steps as they stand in the review sheet."""
    prompt: str = Field(default="", max_length=0)
    steps: list[dict[str, Any]] = Field(default_factory=list, max_length=300)


_SUGGEST_SYSTEM = (
    "You help turn a recorded browser run into a reusable flow. Decide which typed or chosen values would change "
    "from one run to the next (a city, a date, a search term, a name, a quantity) and which are fixed (a button label, "
    "a setting that is always the same). Answer by calling the suggest_inputs tool. Only suggest steps that type or "
    "choose text, at most one input per step, and use the step numbers you are given. Text marked [removed: ...] is "
    "personal data that was hidden from you; it is usually an input. Do not invent steps or values.")
_SUGGEST_TOOL = {
    "name": "suggest_inputs",
    "description": "The steps whose value should become an input the person fills in each time the flow runs.",
    "input_schema": {"type": "object", "properties": {"inputs": {"type": "array", "items": {
        "type": "object", "properties": {
            "step": {"type": "integer", "description": "the step number"},
            "label": {"type": "string", "description": "a short name a person would use, like Origin or Check-in date"},
            "reason": {"type": "string", "description": "why this value changes between runs, in a few words"}},
        "required": ["step", "label"]}}}, "required": ["inputs"]}}
_VALUE_KEY = {"type": "text", "select": "option"}


def _mask(text: str, req: "SuggestRequest", hidden: list[str]) -> str:
    """Hide personal data before text goes to a model. Longest matches first, so a phone number inside a longer one is safe."""
    for f in sorted(record.scan(text, req.sensitive, req.presidio), key=lambda f: -len(f["match"])):
        text = text.replace(f["match"], f"[removed: {f['name']}]")
        hidden.append(f["name"])
    return text


def _suggest_prompt(task: str, req: "SuggestRequest") -> tuple[str, list[str]]:
    hidden: list[str] = []
    lines = []
    for n, st in enumerate(req.steps, 1):
        kind = st.get("do")
        t = st.get("target") if isinstance(st.get("target"), dict) else None
        label = f' {t.get("role", "")} “{str(t.get("text", ""))[:80]}”' if t else ""
        if kind == "goto":
            u = urlparse(str(st.get("url", "")))
            lines.append(f"{n}. Open page {u.scheme}://{u.netloc}{u.path[:80]}")        # no query string: it may carry personal data
        elif kind in _VALUE_KEY and isinstance(st.get(_VALUE_KEY[kind]), str):
            value = st[_VALUE_KEY[kind]]
            shown = "(already an input)" if "{{" in value else "(from My info)" if "<secret:" in value else f"“{_mask(value[:200], req, hidden)}”"
            lines.append(f"{n}. {'Type into' if kind == 'type' else 'Choose in'}{label}: {shown}")
        else:
            lines.append(f"{n}. {str(kind).capitalize()}{label}")
    text = f"Task: {_mask(task[:500], req, hidden)}\n\nSteps:\n" + "\n".join(lines)
    return text, sorted(set(hidden))


@app.post("/runs/{run_id}/suggest-inputs/preview", dependencies=[Depends(_auth)])
def suggest_preview(run_id: str, req: SuggestRequest) -> dict[str, Any]:
    """Exactly what would be sent, so the person can read it first. Nothing leaves this computer here."""
    run = _get_run(run_id)
    check_presidio(req)
    text, hidden = _suggest_prompt(run.prompt, req)
    return {"system": _SUGGEST_SYSTEM, "text": text, "hidden": hidden}


@app.post("/runs/{run_id}/suggest-inputs", dependencies=[Depends(_auth)])
def suggest_inputs(run_id: str, req: SuggestRequest) -> dict[str, Any]:
    run = _get_run(run_id)
    check_presidio(req)
    text, _ = _suggest_prompt(run.prompt, req)
    try:
        resp = build_llm(req).complete(system=[{"text": _SUGGEST_SYSTEM}], messages=[{"role": "user", "content": text}],
                                       tools=[_SUGGEST_TOOL], max_tokens=1500)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"The model could not be reached: {str(exc)[:200]}")
    raw: Any = None
    for b in resp.content:
        if b.get("type") == "tool_use" and b.get("name") == "suggest_inputs":
            raw = b.get("input")
    if raw is None:                                                     # a model that answered in plain text
        for b in resp.content:
            if b.get("type") == "text":
                try:
                    raw = json.loads(re.search(r"\{.*\}", b.get("text", ""), re.S).group())
                except Exception:
                    pass
    out, seen = [], set()
    for item in (raw or {}).get("inputs", []) if isinstance(raw, dict) else []:
        try:
            n, label = int(item["step"]), str(item["label"]).strip()[:60]
        except (KeyError, TypeError, ValueError):
            continue
        st = req.steps[n - 1] if 1 <= n <= len(req.steps) else None
        key = _VALUE_KEY.get(st.get("do")) if st else None
        value = st.get(key) if st and key else None
        if not label or n in seen or not isinstance(value, str) or not value.strip() or "{{" in value or "<secret:" in value:
            continue                                                    # only real, literal, typed or chosen values
        seen.add(n)
        out.append({"step": n, "label": label, "reason": str(item.get("reason", ""))[:160]})
    return {"suggestions": sorted(out, key=lambda x: x["step"])}


@app.get("/runs/{run_id}/flow", dependencies=[Depends(_auth)])
def run_flow_draft(run_id: str) -> dict[str, Any]:
    """The flow a finished run recorded, for the person to review before saving."""
    run = _get_run(run_id)
    if not run.flow_path or not run.flow_path.is_file():
        raise HTTPException(status_code=409, detail="This run cannot be saved as a flow.")
    flow = load_flow(run.flow_path)
    return {"flow": flow, "lines": [describe_step(st) for st in flow["steps"]]}


@app.post("/runs/{run_id}/save-flow", dependencies=[Depends(_auth)])
def save_run_as_flow(run_id: str, req: SaveFlow) -> dict[str, Any]:
    run = _get_run(run_id)
    if not run.flow_path or not run.flow_path.is_file():
        raise HTTPException(status_code=409, detail="This run cannot be saved as a flow.")
    flow = load_flow(run.flow_path)
    flow["name"] = req.name.strip()
    if req.description is not None:
        flow["description"] = req.description.strip()
    if req.edited is not None:
        # Only the steps and the inputs can be changed here. Sites, secrets and the file format stay as recorded,
        # and the library checks the result, so a bad edit is refused with a plain reason.
        changed = {**flow, "params": req.edited.get("params", {}), "steps": req.edited.get("steps", [])}
        try:
            validate_flow(changed)
        except FlowError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        flow = changed
    flow_id = f"{_slug(req.name)}-{uuid.uuid4().hex[:6]}"
    (data_dir() / "flows").mkdir(exist_ok=True)
    save_flow(flow, data_dir() / "flows" / f"{flow_id}.json")
    return _summary(flow_id, flow)


@app.get("/flows", dependencies=[Depends(_auth)])
def list_flows() -> list[dict[str, Any]]:
    out = []
    for p in sorted((data_dir() / "flows").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if (data_dir() / "flows").exists() else []:
        try:
            out.append(_summary(p.stem, load_flow(p)))
        except Exception:                                # a hand-edited or damaged file: skip it, do not break the list
            continue
    return out


@app.delete("/flows/{flow_id}", dependencies=[Depends(_auth)])
def delete_flow(flow_id: str) -> dict[str, bool]:
    _flow_file(flow_id).unlink()
    return {"deleted": True}


class ShareCheck(BaseModel):
    sensitive: dict[str, str] = Field(default_factory=dict)


_PLACEHOLDER = re.compile(r"<secret:[A-Za-z0-9_]+>|\{\{[a-z][a-z0-9_]*\}\}")


def sanitize_flow(flow: dict[str, Any], vault: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """A copy that is safe to hand to someone else, and a list of what was replaced.

    Typed values the library already turned into parameters or secrets are left alone. This finds the ones
    it did not: a saved value from My info, or text that looks like an email, phone or card number, left
    in a step, a default, the name or the description."""
    flow = json.loads(json.dumps(flow))
    replaced: list[dict[str, str]] = []
    params, secrets_ = flow.setdefault("params", {}), set(flow.get("secrets", []))

    def hits(text: str) -> list[dict[str, str]]:
        return record.scan(_PLACEHOLDER.sub(" ", text), vault)

    def clean_text(text: str, where: str, in_step: bool) -> str:
        for f in hits(text):
            if in_step and f["kind"] == "value":
                now = f"<secret:{f['name']}>"
                secrets_.add(f["name"])
            elif in_step:
                n = 1
                while f"personal_{n}" in params:
                    n += 1
                params[f"personal_{n}"] = {"label": f["name"], "required": True}
                now = "{{" + f"personal_{n}" + "}}"
            else:
                now = "[removed]"
            text = text.replace(f["match"], now)
            replaced.append({"where": where, "was": f["match"], "now": now})
        return text

    for n, step in enumerate(flow["steps"], 1):
        for key in ("text", "option", "url", "reason"):
            if isinstance(step.get(key), str):
                step[key] = clean_text(step[key], f"step {n}", key in ("text", "option"))
    for key in ("name", "description"):
        if isinstance(flow.get(key), str):
            flow[key] = clean_text(flow[key], key, False)
    for name, spec in params.items():
        d = spec.get("default")
        if isinstance(d, str) and hits(d):
            for f in hits(d):
                replaced.append({"where": f"default of {{{{{name}}}}}", "was": f["match"], "now": "(no default)"})
            spec.pop("default", None)
            spec["required"] = True
    flow["secrets"] = sorted(secrets_)
    return validate_flow(flow), replaced


@app.post("/flows/{flow_id}/share-check", dependencies=[Depends(_auth)])
def share_check(flow_id: str, req: ShareCheck) -> dict[str, Any]:
    """Everything that would go in a shared file, after personal values are taken out."""
    flow = load_flow(_flow_file(flow_id))
    safe, replaced = sanitize_flow(flow, req.sensitive)
    return {"flow": safe, "replaced": replaced,
            "steps": [describe_step(s) for s in safe["steps"]],
            "params": {k: v.get("label", k) for k, v in safe.get("params", {}).items()},
            "secrets": safe.get("secrets", []), "domains": safe.get("domains", [])}


class FlowRun(BrowserOptions):
    params: dict[str, str] = Field(default_factory=dict)
    sensitive: dict[str, str] = Field(default_factory=dict)
    headed: bool = False
    history: bool = True
    # Optional model help. Off by default: a replay uses no model.
    summarize: bool = False              # after the last step, one call turns what the flow read into an answer
    failover: bool = False               # if a step cannot find its element, a model finishes the task from that page
    ask: str = Field(default="", max_length=500)       # the question or task for the model (default: the flow's description)
    model: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9_.:/@+-]*$")
    custom: CustomSource | None = None
    api_key: str = Field(default="", max_length=500)
    presidio: bool = False
    review: bool = False                 # hold each model call until the person approves it (same as review_mode always)
    review_mode: Literal["off", "flagged", "always"] = "off"


class MaskedLLM:
    """Hides personal data from everything that goes out, so a summary or a repair never carries it. Wraps the
    model; the record of calls sits inside it and so shows exactly what was sent."""

    def __init__(self, inner: Any, req: Any) -> None:
        self._inner, self._req = inner, req
        self.model = getattr(inner, "model", "?")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _text(self, text: str) -> str:
        return _mask(text, self._req, [])

    def _blocks(self, content: Any) -> Any:
        if isinstance(content, str):
            return self._text(content)
        out = []
        for b in content or []:
            if isinstance(b, dict) and b.get("type") == "text":
                b = {**b, "text": self._text(str(b.get("text", "")))}
            elif isinstance(b, dict) and b.get("type") == "tool_result":
                b = {**b, "content": self._blocks(b.get("content"))}
            out.append(b)
        return out

    def complete(self, **kw: Any) -> Any:
        kw["messages"] = [{**m, "content": self._blocks(m.get("content"))} for m in kw.get("messages", [])]
        return self._inner.complete(**kw)


def _work_flow(run: Run, flow: dict[str, Any], req: FlowRun) -> None:
    """Replay a saved flow. No model is called, so it costs no tokens."""
    holder: dict[str, Any] = {}

    def on_step(n: int, total: int, desc: str) -> None:
        run.emit({"type": "step", "number": n, "total": total, "tool": desc, "input": {}, "result": "",
                  "url": "", "cached": True})
        run.live.tick(holder["browser"])               # keeps the live view moving between steps
        if run.stop.is_set():
            raise Stopped()

    def hand_off(request: HandoffRequest) -> bool:
        run.live.handoff, run.live.control = None, True
        run.emit({"type": "handoff", "kind": request.kind, "reason": request.reason, "url": request.url})
        run.live.wait_while(holder["browser"], lambda: run.live.handoff is None)
        run.live.control = False
        run.emit({"type": "control", "on": False})
        return bool(run.live.handoff)

    try:
        holder["browser"] = make_browser(req, req.headed)
        holder["browser"].start()
        llm = None
        if req.summarize or req.failover:
            run.live.mode = req.review_mode if req.review_mode != "off" else ("always" if req.review else "off")
            llm = MaskedLLM(MirrorLLM(build_llm(req), run.live, lambda: holder["browser"],
                                      on_pause=lambda paused: run.emit({"type": "paused", "paused": paused}),
                                      emit=run.emit, secrets=req.sensitive, presidio=req.presidio), req)
        runner = FlowRunner(flow, holder["browser"], params=req.params, secrets=req.sensitive,
                            handler=hand_off, on_step=on_step, llm=llm, answer_with_model=req.summarize,
                            repair_with_model=req.failover, task=req.ask.strip() or None)
        r = runner.run()
        run.emit({"type": "done", "success": r.success, "output": r.output, "steps": r.steps_run, "tokens": r.tokens,
                  "error": r.error, "can_save_flow": False, "model_calls": r.model_calls,
                  "summarized": r.answered_by_model, "repaired": r.repaired_by_model, "repaired_at": r.repaired_at,
                  "warning": r.warning})
    except Stopped:
        run.emit({"type": "done", "success": False, "output": "", "steps": 0, "tokens": 0, "error": "Stopped by you."})
    except Exception as exc:
        run.emit({"type": "done", "success": False, "output": "", "steps": 0, "tokens": 0,
                  "error": f"{type(exc).__name__}: {exc}"[:500]})
    finally:
        remember(run)
        run.finished = True
        try:
            holder["browser"].close()
        except Exception:
            pass
        _RUN_LOCK.release()


@app.post("/flows/{flow_id}/run", dependencies=[Depends(_auth)])
def run_saved_flow(flow_id: str, req: FlowRun) -> dict[str, str]:
    flow = load_flow(_flow_file(flow_id))
    check_browser_options(req)
    if req.summarize or req.failover:
        if not req.model.strip():
            raise HTTPException(status_code=400, detail="Choose a model first.")
        check_presidio(req)
    if not _RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A run is already in progress. Stop it or wait for it to finish.")
    close_idle_sessions()
    run = Run(id=uuid.uuid4().hex[:12], prompt=flow.get("description", flow.get("name", "")))
    run.meta = {"kind": "flow", "flow": flow.get("name", flow_id), "keep": req.history,
                "model": _model_label(req) if (req.summarize or req.failover) else ""}
    RUNS[run.id] = run
    threading.Thread(target=_work_flow, args=(run, flow, req), daemon=True).start()
    return {"id": run.id}


@app.get("/runs/{run_id}/frames", dependencies=[Depends(_auth)])
async def frames(run_id: str) -> StreamingResponse:
    """The live view: the newest frame whenever there is one (older frames are dropped, not queued)."""
    run = _get_run(run_id)

    async def stream():
        sent = 0
        while True:
            frame = run.live.frame
            if frame and frame["seq"] != sent:
                sent = frame["seq"]
                yield f"data: {json.dumps(frame)}\n\n"
            elif run.finished:
                return
            else:
                await asyncio.sleep(0.04)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/runs/{run_id}/events", dependencies=[Depends(_auth)])
async def events(run_id: str, after: int = 0) -> StreamingResponse:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="no such run")

    async def stream():
        sent = max(0, after)                           # a follow-up reads on from where the last stream ended
        while True:
            while sent < len(run.events):
                yield f"data: {json.dumps(run.events[sent])}\n\n"
                sent += 1
            if run.finished and sent >= len(run.events):
                return
            await asyncio.sleep(0.2)

    return StreamingResponse(stream(), media_type="text/event-stream")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=0, help="0 picks a free port")
    args = p.parse_args()
    sock = socket.socket()
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]
    print(f"READY {port}", flush=True)                  # Electron waits for this line
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


if __name__ == "__main__":
    main()
