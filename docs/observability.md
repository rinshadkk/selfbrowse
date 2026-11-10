# Traces, prompts and screenshots

```bash
selfbrowse --show-prompts "task"     # prints every model request live (stderr)
selfbrowse --trace "task"            # also saves the run to ~/.selfbrowse/traces/<run-id>.jsonl
selfbrowse trace list
selfbrowse trace show latest         # timeline: model calls, tokens, actions, guardrail decisions
selfbrowse trace show latest --full  # include the full prompts
```

A trace is one JSON line per event: `run_start`, `llm_request` (the exact system text, tool names and messages sent, with token estimates per part), `llm_response` (usage, timing, the model's reply), `tool_call`, `tool_result`, `replay`, `guardrail`, `handoff`, `run_end`.

- Secrets passed with `sensitive=` never appear: the model only sees `<secret:NAME>`.
- Prompts include page text, which may hold personal data. `--trace-hashes` (Python: `trace_content=False`) stores sizes and hashes only, and `redact_trace=fn` scrubs every string before it is written. Task text, typed text, tool results, reasons and URLs are covered too.
- Tracing never breaks a run: a failing sink or unwritable folder is ignored.

From Python:

```python
agent = BrowseAgent("task", trace=True, on_llm_request=lambda system, messages, tools, n: print(n, len(messages)))
agent.run()
print(agent.trace_path)
```

## OpenTelemetry

`pip install -e '.[otel]'`, then point it at any OTLP/HTTP receiver, including one on your own machine (Jaeger, Grafana Tempo, Arize Phoenix on `http://localhost:4318`):

```bash
selfbrowse --otel http://localhost:4318 "task"
```

Each run becomes a `selfbrowse.run` span with child spans per model call (`gen_ai.*` attributes, token usage) and per tool call; guardrail decisions and hand-offs are span events. Spans carry sizes and timings only. Add `--otel-content` to attach what the model was sent and what it answered: each `chat` span gets `gen_ai.system_instructions`, `gen_ai.input.messages` and `gen_ai.output.messages` (OpenTelemetry GenAI conventions, still experimental). LLM viewers such as Phoenix, Langfuse and Opik show these as a conversation; Jaeger shows them as JSON strings under the span's Tags. Long text is shortened part by part so the JSON stays valid. These attributes contain page text, so only send them to a backend you trust. Spans go only where you point them.

## Screenshots as evidence

To keep proof of what the agent saw and did, save a picture after every step:

```bash
selfbrowse --screenshots ./evidence "Add the cheapest USB-C cable to the cart on example.com"
# [screenshots: evidence/run-20261110-093015]
```

Each run gets its own folder with `step-01.jpg`, `step-02.jpg` and so on, and an `index.html` that lists every step (tool, arguments, URL, result) next to its picture. Python: `BrowseAgent("task", screenshots="./evidence")`, then `agent.screenshots_dir`; each `Step` has a `.screenshot` file name, and a trace records a `screenshot` event per image.

- **The picture shows the page after the step ran**, including the last page when the agent calls `done`.
- **The model never gets these images.** This is separate from `--vision`, which sends pictures to the model and costs tokens.
- **They are not redacted.** A screenshot shows the page as it really is: names, emails and anything the agent typed, even a password that is hidden everywhere else. The folder is created private to your user (mode 700). Do not share or commit it without looking, and avoid `--screenshots` on pages with data you would not want stored.
- **A picture that cannot be taken** (the page just closed, or a pop-up is blocking capture) leaves a gap, marked in `index.html`; the run carries on.
- The MCP server does not save screenshots.
