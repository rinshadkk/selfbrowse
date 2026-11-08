"""
Optional OpenTelemetry export (``pip install 'selfbrowse[otel]'``).

Turns trace events into spans::

    selfbrowse.run
    ├─ chat <model>        gen_ai.* attributes, token usage
    ├─ tool <name>
    └─ span events: guardrail decisions, hand-offs

By default spans carry sizes, timings and metadata only. Pass ``content=True`` to also attach the
task and prompt text, which may include page content.

Point it at any OTLP/HTTP receiver, including one on your own machine
(Jaeger, Grafana Tempo, Arize Phoenix...): ``http://localhost:4318``.
"""
from __future__ import annotations

import json
from typing import Any


class OtelSink:
    def __init__(self, endpoint: str | None = None, *, exporter: Any = None, content: bool = False,
                 service_name: str = "selfbrowse") -> None:
        try:
            from opentelemetry import trace as otrace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
        except ImportError as exc:
            raise ImportError("OpenTelemetry export needs: pip install 'selfbrowse[otel]'") from exc

        if exporter is None:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            url = endpoint or "http://localhost:4318"
            exporter = OTLPSpanExporter(endpoint=url if url.rstrip("/").endswith("/v1/traces") else url.rstrip("/") + "/v1/traces")
            processor = BatchSpanProcessor(exporter)
        else:
            processor = SimpleSpanProcessor(exporter)
        self._otrace = otrace
        self._provider = TracerProvider(resource=Resource.create({"service.name": service_name}))   # private: no global state
        self._provider.add_span_processor(processor)
        self._tracer = self._provider.get_tracer("selfbrowse")
        self.content = content
        self._run: Any = None
        self._llm: Any = None
        self._tool: Any = None

    def _ctx(self) -> Any:
        return self._otrace.set_span_in_context(self._run) if self._run is not None else None

    def handle(self, ev: dict[str, Any]) -> None:
        k = ev["type"]
        if k == "run_start":
            self._run = self._tracer.start_span("selfbrowse.run")
            self._run.set_attribute("gen_ai.request.model", str(ev.get("model", "")))
            if self.content:
                self._run.set_attribute("selfbrowse.task", str(ev.get("task", "")))
        elif k == "llm_request":
            self._llm = self._tracer.start_span(f"chat {ev.get('model', '')}", context=self._ctx())
            s, t = self._llm, ev["tokens_est"]
            s.set_attribute("gen_ai.operation.name", "chat")
            s.set_attribute("gen_ai.request.model", str(ev.get("model", "")))
            s.set_attribute("selfbrowse.est_tokens.system", t["system"])
            s.set_attribute("selfbrowse.est_tokens.tools", t["tools"])
            s.set_attribute("selfbrowse.est_tokens.messages", t["messages"])
            if self.content:
                s.set_attribute("selfbrowse.request", json.dumps(ev["messages"], ensure_ascii=False)[:32000])
        elif k in ("llm_response", "llm_error") and self._llm is not None:
            s = self._llm
            if k == "llm_response":
                u = ev["usage"]
                s.set_attribute("gen_ai.usage.input_tokens", u["input"] + u["cache_read"] + u["cache_write"])
                s.set_attribute("gen_ai.usage.output_tokens", u["output"])
                s.set_attribute("selfbrowse.cache_read_tokens", u["cache_read"])
                s.set_attribute("gen_ai.response.finish_reasons", [str(ev.get("stop_reason"))])
            else:
                s.set_attribute("error.type", "llm_error")
                s.set_attribute("error.message", ev["error"])
            s.end()
            self._llm = None
        elif k == "tool_call":
            self._tool = self._tracer.start_span(f"tool {ev['tool']}", context=self._ctx())
            self._tool.set_attribute("selfbrowse.tool", ev["tool"])
            if self.content:
                self._tool.set_attribute("selfbrowse.args", json.dumps(ev.get("args"), ensure_ascii=False)[:2000])
        elif k == "tool_result" and self._tool is not None:
            if str(ev.get("result", "")).startswith("Error:"):
                self._tool.set_attribute("error.type", "tool_error")
            self._tool.end()
            self._tool = None
        elif k in ("guardrail", "handoff", "replay") and self._run is not None:
            self._run.add_event(k, {a: str(v)[:300] for a, v in ev.items() if a in ("guardrail", "decision", "reason", "kind", "resumed", "tool")})
        elif k == "run_end" and self._run is not None:
            self._run.set_attribute("selfbrowse.success", bool(ev.get("success")))
            self._run.set_attribute("selfbrowse.steps", int(ev.get("steps") or 0))
            if ev.get("error"):
                self._run.set_attribute("error.message", str(ev["error"])[:300])
            for s in (self._llm, self._tool):
                if s is not None:
                    s.end()
            self._llm = self._tool = None
            self._run.end()
            self._run = None
            self._provider.force_flush()

    def close(self) -> None:
        try:
            self._provider.shutdown()
        except Exception:
            pass
