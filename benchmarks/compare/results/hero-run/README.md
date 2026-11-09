# Website hero run

The example run on the website is this recording, not a mock-up.

- Model: `qwen3.6-bench` (qwen3.6 via Ollama on the same machine, native tool calls, temperature 0)
- Site: the benchmark's local demo store (`../../store.py`)
- Guardrails: SafeUrls, AllowedDomains(127.0.0.1), ConfirmRisky, RedactPII, Budget(100k tokens); none were triggered
- Result: success, "Glass Kettle - $24.99", added to the cart
- 16 model calls, 35,667 tokens (as reported by Ollama), 41.2 seconds wall time, including model load on the first call

Replay the summary with:

    python -c "from selfbrowse import trace as tr; print(tr.render(tr.load('trace.jsonl')))"

Record a new one with `python record.py <trace-folder>` from `benchmarks/compare`.
