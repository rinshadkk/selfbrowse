"""
Stop and review what is about to be sent to the model.

Masking (``RedactPII``, ``PresidioRedact``) hides personal data from the page text. This is a different
tool: a *gate*. Before each model call it can show you the exact request, and let you send it, send it with
the flagged text masked, or stop the run.

Modes (``BrowseAgent(review_payload=...)``):

* ``"always"``        every model call stops for review, whatever was found. The only mode that cannot miss
                      anything, because it does not depend on a detector.
* ``"when_flagged"``  stops only when something looks personal. ``True`` means this mode.
* ``None`` / ``False`` no review (the default).

What "looks personal" means: emails, phone numbers, US SSNs, card numbers (Luhn-checked) and any of your
``sensitive`` values, always. Names, IBANs, passports and similar too, when Microsoft Presidio and a spaCy model
are installed (``pip install 'selfbrowse[presidio]'``); without them those are not found. Screenshots are not
scanned. If a detector misses something, ``"always"`` is the mode that still stops.

A decision to send, or to mask, is remembered for that exact text for the rest of the run, so one email in the
task does not stop every call.
"""
from __future__ import annotations

import copy
import hashlib
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from selfbrowse.guardrails import _CARD, _EMAIL, _PHONE, _SSN, _luhn, PresidioRedact, _LABELS
from selfbrowse.llm.base import LLMError

MODES = ("always", "when_flagged")
MIN_SECRET = 3            # shorter saved values would match everywhere


class ReviewStopped(LLMError):
    """The person (or the lack of one) did not approve sending the request, so the run stops."""


@dataclass
class Flag:
    kind: str             # "email", "phone", "ssn", "card", "secret", or a Presidio label such as "person"
    label: str            # for a person: "email address"
    text: str             # exactly the text that looks personal
    role: str             # whose message it is in ("user")
    index: int            # position in ``messages``


@dataclass
class PayloadReview:
    """What a reviewer sees: the exact request, and what looks personal in it."""
    n: int                                                  # which model call of the run this is
    mode: str
    system: str
    messages: list[dict[str, Any]]                          # exactly what would be sent
    tools: list[str]
    flags: list[Flag] = field(default_factory=list)
    images: int = 0                                         # screenshots attached; these are not scanned

    @property
    def text(self) -> str:
        """The text of the messages the model would read, flattened."""
        return "\n\n".join(f"[{m['role']}]\n{_flatten(m.get('content'))}" for m in self.messages)


def _flatten(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for b in content or []:
        if not isinstance(b, dict):
            parts.append(str(b))
        elif b.get("type") == "text":
            parts.append(str(b.get("text", "")))
        elif b.get("type") == "tool_use":
            parts.append(f"{b.get('name')} {b.get('input')}")
        elif b.get("type") == "tool_result":
            parts.append(_flatten(b.get("content")))
        elif b.get("type") == "image":
            parts.append("[a screenshot is attached]")
    return "\n".join(p for p in parts if p)


def _texts(content: Any):
    """Every piece of text the model reads in one message, as (container, key) pairs that can be rewritten."""
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                yield b, "text"
            elif b.get("type") == "tool_result":
                inner = b.get("content")
                if isinstance(inner, str):
                    yield b, "content"
                else:
                    yield from _texts(inner)


def _images(content: Any) -> int:
    n = 0
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "image":
                    n += 1
                elif b.get("type") == "tool_result":
                    n += _images(b.get("content"))
    return n


class Detector:
    """Finds text that looks personal. Built-in checks always; Presidio when it is installed."""

    def __init__(self, secrets: dict[str, str] | None = None, *, presidio: Any = "auto") -> None:
        self.secrets = {k: v for k, v in (secrets or {}).items() if len(str(v)) >= MIN_SECRET}
        self._presidio: Any = None
        self.presidio_active = False
        if presidio:
            try:
                p = presidio if isinstance(presidio, PresidioRedact) else PresidioRedact(restore=False)
                p._engine()                                  # raises if the package or the model is missing
                self._presidio, self.presidio_active = p, True
            except Exception:                                # not installed: the built-in checks still run
                if presidio is True:
                    raise
        self._cache: dict[str, list[tuple[str, str, str]]] = {}

    def scan(self, text: str) -> list[tuple[str, str, str]]:
        """``(kind, label, text)`` for each hit. Cached by content, so an unchanged page is not rescanned."""
        key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
        if key in self._cache:
            return self._cache[key]
        found: dict[tuple[str, str], tuple[str, str, str]] = {}
        for name, value in self.secrets.items():
            if str(value) in text:
                found[("secret", str(value))] = ("secret", name, str(value))
        for m in _CARD.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and _luhn(digits):
                found.setdefault(("card", m.group(0)), ("card", "card number", m.group(0)))
        for m in _SSN.finditer(text):
            found.setdefault(("ssn", m.group(0)), ("ssn", "social security number", m.group(0)))
        for m in _PHONE.finditer(text):
            if not any(m.group(0) in k[1] for k in found if k[0] in ("card", "ssn", "secret")):
                found.setdefault(("phone", m.group(0)), ("phone", "phone number", m.group(0)))
        for m in _EMAIL.finditer(text):
            found.setdefault(("email", m.group(0)), ("email", "email address", m.group(0)))
        if self._presidio is not None and text.strip():
            p = self._presidio
            for r in p._engine().analyze(text=text, language=p.language, entities=p.entities, score_threshold=p.threshold):
                span = text[r.start:r.end]
                if any(span in k[1] or k[1] in span for k in found):          # a built-in check already has it
                    continue
                kind = _LABELS.get(r.entity_type, r.entity_type.lower())
                found.setdefault((kind, span), (kind, kind, span))
        out = list(found.values())
        if len(self._cache) > 2000:
            self._cache.clear()
        self._cache[key] = out
        return out


Reviewer = Callable[[PayloadReview], Any]


def terminal_review(review: PayloadReview) -> str:
    """Ask in the terminal: ``s`` send, ``r`` send with the flagged text masked, ``q`` stop. Without a terminal,
    stops: a request nobody can approve is not sent."""
    if not sys.stdin or not sys.stdin.isatty():
        return "stop"
    err = sys.stderr
    err.write("\a\n┌─ Selfbrowse: about to send to the model ──────────────\n")
    err.write(f"│ call {review.n}, {len(review.messages)} message(s), mode {review.mode}\n")
    if review.flags:
        err.write("│ looks personal:\n")
        for f in review.flags[:12]:
            shown = f.text if len(f.text) <= 60 else f.text[:57] + "..."
            err.write(f"│   {f.label}: {shown}\n")
        if len(review.flags) > 12:
            err.write(f"│   ... and {len(review.flags) - 12} more\n")
    else:
        err.write("│ nothing in it looked personal to the checks that ran\n")
    if review.images:
        err.write(f"│ {review.images} screenshot(s) attached (not scanned)\n")
    err.write("│ [s] send   [r] send with the flagged text masked   [q] stop the run   [v] view it all\n└─ ")
    err.flush()
    while True:
        try:
            answer = sys.stdin.readline().strip().lower()
        except (OSError, ValueError):
            return "stop"
        if answer in ("s", "send", "y", "yes"):
            return "send"
        if answer in ("r", "redact", "mask"):
            return "redact"
        if answer in ("q", "quit", "n", "no", ""):
            return "stop"
        if answer in ("v", "view"):
            err.write(review.text + "\n└─ ")
            err.flush()


class ReviewLLM:
    """Wraps a model so each request can be reviewed before it is sent. Raises :class:`ReviewStopped` to end the run."""

    def __init__(self, inner: Any, *, mode: str, on_review: Reviewer | None = None,
                 secrets: dict[str, str] | None = None, presidio: Any = "auto",
                 trace: Callable[..., None] | None = None) -> None:
        if mode not in MODES:
            raise ValueError(f"review_payload must be one of {MODES}, True, or off (got {mode!r})")
        self.inner, self.mode = inner, mode
        self.on_review = on_review or terminal_review
        self.detector = Detector(secrets, presidio=presidio)
        self._trace = trace or (lambda *a, **k: None)
        self._decided: dict[tuple[str, str], str] = {}        # (kind, text) -> "send" | "redact", for this run
        self._n = 0
        self.model = getattr(inner, "model", "?")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _flags(self, messages: list[dict[str, Any]]) -> list[Flag]:
        out: list[Flag] = []
        for i, m in enumerate(messages):
            if m.get("role") != "user":                       # the model's own words are not what leaves
                continue
            content = m.get("content")
            for holder, key in ([(m, "content")] if isinstance(content, str) else list(_texts(content))):
                for kind, label, text in self.detector.scan(str(holder[key])):
                    out.append(Flag(kind, label, text, "user", i))
        return out

    @staticmethod
    def _mask(messages: list[dict[str, Any]], flags: list[Flag]) -> None:
        """Replace each flagged text, in place, with ``[kind]``, longest first so a part never survives."""
        for f in sorted(flags, key=lambda f: -len(f.text)):
            m = messages[f.index]
            content = m.get("content")
            for holder, key in ([(m, "content")] if isinstance(content, str) else list(_texts(content))):
                holder[key] = str(holder[key]).replace(f.text, f"[{f.kind}]")

    def complete(self, *, system: list[dict], messages: list[dict], tools: list[dict], max_tokens: int = 2048):
        self._n += 1
        flags = self._flags(messages)
        sticky = [f for f in flags if (f.kind, f.text) in self._decided]
        new = [f for f in flags if (f.kind, f.text) not in self._decided]
        ask = self.mode == "always" or bool(new)
        send_messages = messages
        redact: list[Flag] = [f for f in sticky if self._decided[(f.kind, f.text)] == "redact"]
        if ask:
            shown = flags if self.mode == "always" else new
            review = PayloadReview(
                n=self._n, mode=self.mode, system="\n".join(str(b.get("text", "")) for b in system),
                messages=copy.deepcopy(messages), tools=[t.get("name", "?") for t in tools], flags=list(shown),
                images=sum(_images(m.get("content")) for m in messages if m.get("role") == "user"))
            try:
                answer = self.on_review(review)
            except Exception as exc:
                self._trace("review", n=self._n, mode=self.mode, flags=len(shown), decision="stop", error=str(exc)[:200])
                raise ReviewStopped(f"stopped: the review of the request failed ({type(exc).__name__}), so it was not sent") from exc
            decision = _decision(answer)
            self._trace("review", n=self._n, mode=self.mode, flags=len(shown), decision=decision)
            if decision == "stop":
                raise ReviewStopped("stopped: you did not approve sending the request to the model")
            if self.mode == "when_flagged":
                for f in new:
                    self._decided[(f.kind, f.text)] = decision
            if decision == "redact":
                redact += [f for f in shown if f not in redact]
        if redact:
            send_messages = copy.deepcopy(messages)
            self._mask(send_messages, redact)
        return self.inner.complete(system=system, messages=send_messages, tools=tools, max_tokens=max_tokens)


def _decision(answer: Any) -> str:
    if answer is True:
        return "send"
    if isinstance(answer, str):
        a = answer.strip().lower()
        if a in ("send", "s", "yes", "y", "ok"):
            return "send"
        if a in ("redact", "r", "mask"):
            return "redact"
    return "stop"                                             # False, None, anything unclear: do not send
