# Benchmark: model `claude-opus-5-5`, 1 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 0/1 (0%) | 0.0 | 0 | 0 | nan | 61 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| S4-flight-cok (live) | 0/1 · 0 tok · 0.0 calls |

## Failures

- rep1 S4-flight-cok selfbrowse: model call failed: Error code: 429 - Rate limit exceeded: new-account-rpm/anthropic/claude-opus-5.5-20260921. Rate limit reached: new accounts are limited to 20 requests per minute for this model. Please retry shortly.
