# Benchmark: model `claude-opus-5-5`, 1 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 0/1 (0%) | 61.0 | 578,841 | 0 | 10,014 | 565 |
| selfbrowse | 1/1 (100%) | 4.0 | 8,806 | 19,120 | 1,326 | 20 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| K2-flights (live) | 0/1 · 578,841 tok · 61.0 calls | 1/1 · 8,806 tok · 4.0 calls |

## Failures

- rep1 K2-flights browser-use: LLM call timed out after 90 seconds. Keep your thinking and output short.
