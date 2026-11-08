"""
Run traces: a JSON-lines record of everything that happened, including exactly what was sent to
the model.

One file per run (``~/.selfbrowse/traces/<run-id>.jsonl``). Event types::

    run_start  llm_request  llm_response  llm_error  tool_call  tool_result
    replay     guardrail    handoff       run_end

Prompt text is stored by default. It can contain page content, so use ``content=False`` to store
only sizes and hashes, or pass ``redact=`` to scrub strings before they are written.
Secrets passed with ``sensitive=`` never appear: the model only ever sees ``<secret:NAME>``.

Tracing must never break a run: any error in a sink or the file is swallowed.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Callable, Protocol

_encoder: Any = False


def estimate_tokens(text: str) -> int:
    """Token count: exact-ish with tiktoken if installed, else characters / 4."""
    global _encoder
    if _encoder is False:
        try:
            import tiktoken
            _encoder = tiktoken.get_encoding("o200k_base")
        except Exception:
            _encoder = None
    if _encoder is not None:
        try:
            return len(_encoder.encode(text, disallowed_special=()))
        except Exception:
            pass
    return max(1, len(text) // 4) if text else 0


class Sink(Protocol):
    def handle(self, event: dict[str, Any]) -> None: ...
    def close(self) -> None: ...


def _digest(text: str) -> dict[str, Any]:
    return {"chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()[:16]}


class Tracer:
    def __init__(
        self,
        directory: "str | Path | None" = None,
        *,
        content: bool = True,
        redact: Callable[[str], str] | None = None,
        show_prompts: bool = False,
        sinks: "list[Sink] | None" = None,
        stream: Any = None,
    ) -> None:
        self.directory = Path(directory).expanduser() if directory else None
        self.content = content
        self.redact = redact
        self.show_prompts = show_prompts
        self.sinks = list(sinks or [])
        self.stream = stream or sys.stderr
        self.run_id = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        self.path: Path | None = self.directory / f"{self.run_id}.jsonl" if self.directory else None
        self._seq = 0
        self._shown_static = False
        self._file = None

    # ── writing ────────────────────────────────────────────────────────────────
    # Fields that can hold page text, typed text or URLs: redacted, or hashed when content=False.
    _SENSITIVE = ("task", "result", "args", "reason", "url")

    def _obj(self, value: Any) -> Any:
        """Strings and JSON-able values, passed through redaction/hashing as configured."""
        if value is None or (self.content and not self.redact):
            return value
        return self._text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str))

    def event(self, type: str, **data: Any) -> None:
        for key in self._SENSITIVE:
            if key in data:
                data[key] = self._obj(data[key])
        self._seq += 1
        ev = {"seq": self._seq, "ts": round(time.time(), 3), "run_id": self.run_id, "type": type, **data}
        try:
            if self.path is not None:
                if self._file is None:
                    self.directory.mkdir(parents=True, exist_ok=True)   # type: ignore[union-attr]
                    self._file = open(self.path, "a", encoding="utf-8")
                self._file.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
                self._file.flush()
        except Exception:
            pass
        for sink in self.sinks:
            try:
                sink.handle(ev)
            except Exception:
                pass

    def close(self) -> None:
        try:
            if self._file:
                self._file.close()
        except Exception:
            pass
        self._file = None
        for sink in self.sinks:
            try:
                sink.close()
            except Exception:
                pass

    # ── describing a model request ─────────────────────────────────────────────
    def _text(self, text: str) -> Any:
        if self.redact:
            try:
                text = self.redact(text)
            except Exception:
                text = "[redaction failed]"
        return text if self.content else _digest(text)

    def describe_request(self, system: list[dict], messages: list[dict], tools: list[dict]) -> dict[str, Any]:
        sys_text = "\n\n".join(b.get("text", "") for b in system)
        tools_json = json.dumps(tools, ensure_ascii=False)
        msgs: list[dict[str, Any]] = []
        msg_tokens = 0
        for m in messages:
            blocks = [{"type": "text", "text": m["content"]}] if isinstance(m["content"], str) else m["content"]
            out: list[dict[str, Any]] = []
            for b in blocks:
                t = b.get("type")
                if t == "text":
                    msg_tokens += estimate_tokens(b["text"])
                    out.append({"type": "text", "text": self._text(b["text"])})
                elif t == "tool_use":
                    args = json.dumps(b.get("input", {}), ensure_ascii=False)
                    msg_tokens += estimate_tokens(args)
                    out.append({"type": "tool_use", "name": b.get("name"), "input": self._obj(b.get("input"))})
                elif t == "tool_result":
                    parts = []
                    for p in b.get("content") or []:
                        if p.get("type") == "text":
                            msg_tokens += estimate_tokens(p["text"])
                            parts.append({"type": "text", "text": self._text(p["text"])})
                        else:
                            parts.append({"type": p.get("type", "?"), "note": "omitted"})
                    out.append({"type": "tool_result", "content": parts})
                else:
                    out.append({"type": t or "?", "note": "omitted"})
            msgs.append({"role": m["role"], "content": out})
        return {
            "tokens_est": {"system": estimate_tokens(sys_text), "tools": estimate_tokens(tools_json), "messages": msg_tokens},
            "system": self._text(sys_text),
            "tools": [t["name"] for t in tools],
            "messages": msgs,
        }

    def print_request(self, n: int, req: dict[str, Any]) -> None:
        """--show-prompts: a readable view of one model call."""
        w = self.stream.write
        t = req["tokens_est"]
        w(f"\n── model call {n} ── system {t['system']}t · tools {t['tools']}t · messages {t['messages']}t "
          f"(≈{sum(t.values())} in) ──\n")
        if not self._shown_static:
            w(f"[system]\n{req['system'] if self.content else '(hidden)'}\n[tools] {', '.join(req['tools'])}\n")
            self._shown_static = True
        for m in req["messages"]:
            for b in m["content"]:
                if b["type"] == "text":
                    w(f"[{m['role']}]\n{b['text'] if self.content else '(hidden)'}\n")
                elif b["type"] == "tool_use":
                    w(f"[assistant → {b['name']}] {json.dumps(b.get('input'), ensure_ascii=False)}\n")
                elif b["type"] == "tool_result":
                    for p in b["content"]:
                        w(f"[tool result]\n{p.get('text', p.get('note', '')) if self.content else '(hidden)'}\n")
        self.stream.flush()


class TracingLLM:
    """Wraps any LLM; records each request and response, and calls ``on_request`` first."""

    def __init__(self, inner: Any, tracer: Tracer, on_request: Callable[..., None] | None = None) -> None:
        self.inner, self.tracer, self.on_request = inner, tracer, on_request
        self.model = getattr(inner, "model", "unknown")
        self._n = 0

    def complete(self, *, system: list[dict], messages: list[dict], tools: list[dict], max_tokens: int = 2048):
        self._n += 1
        req = self.tracer.describe_request(system, messages, tools)
        self.tracer.event("llm_request", n=self._n, model=self.model, **req)
        if self.tracer.show_prompts:
            self.tracer.print_request(self._n, req)
        if self.on_request:
            try:
                self.on_request(system=system, messages=messages, tools=tools, n=self._n)
            except Exception:
                pass
        start = time.perf_counter()
        try:
            resp = self.inner.complete(system=system, messages=messages, tools=tools, max_tokens=max_tokens)
        except Exception as exc:
            self.tracer.event("llm_error", n=self._n, error=str(exc)[:500], seconds=round(time.perf_counter() - start, 3))
            raise
        u = resp.usage
        self.tracer.event(
            "llm_response", n=self._n, seconds=round(time.perf_counter() - start, 3), stop_reason=resp.stop_reason,
            usage={"input": u.input_tokens, "output": u.output_tokens, "cache_read": u.cache_read_tokens,
                   "cache_write": u.cache_write_tokens},
            content=[{"type": b["type"], **({"text": self.tracer._text(b["text"])} if b["type"] == "text" else
                                            {"name": b.get("name"), "input": self.tracer._obj(b.get("input"))})} for b in resp.content],
        )
        return resp


# ── reading traces back (CLI) ──────────────────────────────────────────────────────

def load(path: "str | Path") -> list[dict[str, Any]]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def find(directory: "str | Path", run_id: str) -> Path | None:
    d = Path(directory).expanduser()
    files = sorted(d.glob("*.jsonl")) if d.exists() else []
    if run_id == "latest":
        return files[-1] if files else None
    hits = [f for f in files if f.stem == run_id or f.stem.startswith(run_id)]
    return hits[-1] if hits else None


def summarize_dir(directory: "str | Path") -> list[dict[str, Any]]:
    rows = []
    d = Path(directory).expanduser()
    for f in sorted(d.glob("*.jsonl")) if d.exists() else []:
        evs = load(f)
        start = next((e for e in evs if e["type"] == "run_start"), {})
        end = next((e for e in reversed(evs) if e["type"] == "run_end"), {})
        rows.append({"id": f.stem, "task": start.get("task", "?"), "success": end.get("success"),
                     "steps": end.get("steps"), "calls": sum(1 for e in evs if e["type"] == "llm_request"),
                     "tokens": end.get("tokens_total")})
    return rows


def render(evs: list[dict[str, Any]], full: bool = False) -> str:
    """Human-readable timeline of a run."""
    if not evs:
        return "(empty trace)"
    t0 = evs[0]["ts"]
    lines = []
    for e in evs:
        at = f"+{e['ts'] - t0:6.1f}s"
        k = e["type"]
        if k == "run_start":
            lines.append(f"{at}  RUN     {e.get('task', '')!r} model={e.get('model')} guardrails={e.get('guardrails')}")
        elif k == "llm_request":
            t = e["tokens_est"]
            lines.append(f"{at}  MODEL → call {e['n']}: system {t['system']}t, tools {t['tools']}t, messages {t['messages']}t")
            if full:
                lines.append("          " + json.dumps(e["messages"], ensure_ascii=False)[:4000])
        elif k == "llm_response":
            u = e["usage"]
            acts = ", ".join(b.get("name") or b["type"] for b in e["content"])
            lines.append(f"{at}  MODEL ← {e['seconds']}s in={u['input']} out={u['output']} cache={u['cache_read']} → {acts}")
        elif k == "llm_error":
            lines.append(f"{at}  MODEL ✗ {e['error']}")
        elif k == "tool_call":
            lines.append(f"{at}  ACTION  {e['tool']} {json.dumps(e.get('args'), ensure_ascii=False)}")
        elif k == "tool_result":
            lines.append(f"{at}  RESULT  {e.get('seconds', 0)}s {str(e.get('result', ''))[:120]!r}")
        elif k == "replay":
            lines.append(f"{at}  REPLAY  {e.get('tool')} {json.dumps(e.get('args'), ensure_ascii=False)} (no model call)")
        elif k == "guardrail":
            lines.append(f"{at}  GUARD   {e.get('guardrail')}: {e.get('decision')} — {e.get('reason')}")
        elif k == "handoff":
            lines.append(f"{at}  HANDOFF {e.get('kind')}: {e.get('reason')} → {'resumed' if e.get('resumed') else 'stopped'}")
        elif k == "run_end":
            lines.append(f"{at}  END     success={e.get('success')} steps={e.get('steps')} tokens={e.get('tokens_total')} "
                         f"error={e.get('error')!r}")
    return "\n".join(lines)
