import json

import pytest

from selfbrowse import Agent, Browser
from selfbrowse import trace as tr
from tests.conftest import ScriptedLLM

pytestmark = pytest.mark.browser
DONE = ("done", {"success": True, "answer": "ok"})


def run(shop_url, tmp_path, script, **kw):
    llm = ScriptedLLM(script)
    with Browser() as b:
        b.goto(shop_url)
        agent = Agent("buy a thing", llm=llm, browser=b, home=tmp_path, **kw)
        res = agent.run()
    return agent, res, llm


def events(agent):
    return tr.load(agent.trace_path)


def test_trace_records_exact_request_and_whole_run(shop_url, tmp_path):
    agent, res, llm = run(shop_url, tmp_path, [("read", {}), DONE], trace=True)
    evs = events(agent)
    kinds = [e["type"] for e in evs]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert kinds.count("llm_request") == 2 and kinds.count("llm_response") == 2
    req = next(e for e in evs if e["type"] == "llm_request")
    sent = json.dumps(req["messages"])
    assert "Add to cart" in sent and "buy a thing" in sent            # what the model actually saw
    assert req["tokens_est"]["system"] > 0 and req["tools"]
    end = evs[-1]
    assert end["success"] is True and end["tokens_total"] == 220
    assert agent.trace_path.parent == tmp_path / "traces"


def test_content_false_stores_hashes_only(shop_url, tmp_path):
    agent, _, _ = run(shop_url, tmp_path, [DONE], trace=True, trace_content=False)
    text = agent.trace_path.read_text()
    assert "Add to cart" not in text and "buy a thing" not in text
    assert "sha256" in text


def test_redact_hook_scrubs_trace(shop_url, tmp_path):
    agent, _, _ = run(shop_url, tmp_path, [DONE], trace=True, redact_trace=lambda s: s.replace("Add to cart", "[x]"))
    text = agent.trace_path.read_text()
    assert "Add to cart" not in text and "[x]" in text


def test_secret_value_never_in_trace(shop_url, tmp_path):
    snap_b = Browser().start()
    snap_b.goto(shop_url)
    pw = next(int(l.split()[0][1:]) for l in snap_b.snapshot().text.splitlines() if "Password" in l)
    snap_b.close()
    agent, res, _ = run(shop_url, tmp_path, [("type", {"ref": pw, "text": "<secret:pw>"}), DONE],
                        trace=True, sensitive={"pw": "hunter2-xyz"})
    assert res.success and "hunter2-xyz" not in agent.trace_path.read_text()


def test_show_prompts_prints_requests(shop_url, tmp_path, capsys):
    run(shop_url, tmp_path, [DONE], show_prompts=True)
    err = capsys.readouterr().err
    assert "model call 1" in err and "Add to cart" in err and "[system]" in err


def test_on_llm_request_callback(shop_url, tmp_path):
    seen = []
    run(shop_url, tmp_path, [DONE], on_llm_request=lambda **kw: seen.append(kw["n"]))
    assert seen == [1]


def test_no_tracing_by_default(shop_url, tmp_path):
    agent, _, _ = run(shop_url, tmp_path, [DONE])
    assert agent.trace_path is None and not (tmp_path / "traces").exists()


def test_guardrail_and_handoff_events_in_trace(shop_url, tmp_path):
    from selfbrowse.guardrails import AllowedDomains
    agent, _, _ = run(shop_url, tmp_path, [("goto", {"url": "https://evil.example"}), DONE],
                      trace=True, guardrails=[AllowedDomains(["127.0.0.1"])])
    g = [e for e in events(agent) if e["type"] == "guardrail"]
    assert g and g[0]["decision"] == "block"


def test_render_list_and_find(shop_url, tmp_path):
    agent, _, _ = run(shop_url, tmp_path, [("read", {}), DONE], trace=True)
    out = tr.render(events(agent))
    assert "MODEL → call 1" in out and "ACTION  read" in out and "END" in out
    rows = tr.summarize_dir(tmp_path / "traces")
    assert rows[0]["task"] == "buy a thing" and rows[0]["success"] is True and rows[0]["calls"] == 2
    assert tr.find(tmp_path / "traces", "latest") == agent.trace_path
    assert tr.find(tmp_path / "traces", agent.tracer.run_id[:12]) == agent.trace_path


def test_otel_spans(shop_url, tmp_path):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from selfbrowse.otel import OtelSink
    from selfbrowse.trace import Tracer

    exporter = InMemorySpanExporter()
    tracer = Tracer(None, sinks=[OtelSink(exporter=exporter)])
    run(shop_url, tmp_path, [("read", {}), DONE], trace=tracer)
    spans = {s.name: s for s in exporter.get_finished_spans()}
    names = list(spans)
    assert "selfbrowse.run" in names and any(n.startswith("chat ") for n in names) and "tool read" in names
    chat = next(s for n, s in spans.items() if n.startswith("chat "))
    assert chat.attributes["gen_ai.usage.input_tokens"] == 100 and chat.attributes["gen_ai.usage.output_tokens"] == 10
    run_span = spans["selfbrowse.run"]
    assert run_span.attributes["selfbrowse.success"] is True
    assert "selfbrowse.task" not in run_span.attributes                 # content is opt-in
    assert chat.parent.span_id == run_span.context.span_id


def test_sink_failure_never_breaks_a_run(shop_url, tmp_path):
    class Boom:
        def handle(self, ev):
            raise RuntimeError("sink down")

        def close(self):
            raise RuntimeError("sink down")

    from selfbrowse.trace import Tracer
    _, res, _ = run(shop_url, tmp_path, [DONE], trace=Tracer(None, sinks=[Boom()]))
    assert res.success


def _otel_run(shop_url, tmp_path, content):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from selfbrowse.otel import OtelSink
    from selfbrowse.trace import Tracer

    exporter = InMemorySpanExporter()
    run(shop_url, tmp_path, [("read", {}), DONE], trace=Tracer(None, sinks=[OtelSink(exporter=exporter, content=content)]))
    return [s for s in exporter.get_finished_spans() if s.name.startswith("chat ")]


def test_otel_content_carries_request_and_response(shop_url, tmp_path):
    import json
    chats = _otel_run(shop_url, tmp_path, content=True)
    assert len(chats) == 2
    first, second = chats
    system = json.loads(first.attributes["gen_ai.system_instructions"])
    assert system[0]["type"] == "text" and "web browser" in system[0]["content"]
    # request: the task and page list as a user message
    msgs = json.loads(first.attributes["gen_ai.input.messages"])
    assert msgs[0]["role"] == "user" and "Add to cart" in msgs[0]["parts"][0]["content"]
    # response: the chosen tool call
    out = json.loads(first.attributes["gen_ai.output.messages"])
    assert out[0]["role"] == "assistant" and out[0]["finish_reason"] == "tool_use"
    assert out[0]["parts"][0] == {"type": "tool_call", "name": "read", "arguments": {}}
    # the second call sees the first call's reply and the tool's result
    msgs2 = json.loads(second.attributes["gen_ai.input.messages"])
    kinds = [p["type"] for m in msgs2 for p in m["parts"]]
    assert "tool_call" in kinds and "tool_call_response" in kinds
    assert list(first.attributes["selfbrowse.tools"])[:2] == ["goto", "click"]


def test_otel_without_content_has_no_text(shop_url, tmp_path):
    for span in _otel_run(shop_url, tmp_path, content=False):
        for key in ("gen_ai.system_instructions", "gen_ai.input.messages", "gen_ai.output.messages"):
            assert key not in span.attributes
        assert "Add to cart" not in repr(dict(span.attributes))     # no page text leaks through any attribute


def test_otel_long_conversations_stay_valid_json():
    import json
    from selfbrowse.otel import _as_json, _clip, _parts
    long_text = "x" * 50_000
    assert len(_clip(long_text)) < 8100 and _clip("short") == "short"
    msgs = [{"role": "user", "parts": _parts([{"type": "text", "text": long_text}])} for _ in range(40)]
    data = json.loads(_as_json(msgs))                                # still parses
    assert len(json.dumps(data)) < 140_000
    assert data[0] == msgs[0] and data[-1] == msgs[-1] and "omitted" in data[1]["parts"][0]["content"]
