# Benchmark: model `claude-haiku-5-5`, 3 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 9/9 (100%) | 12.2 | 54,375 | 125,330 | 1,376 | 52 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| S1-flight-sfo (live) | 3/3 · 134,473 tok · 26.7 calls |
| S2-trending (live) | 3/3 · 6,672 tok · 3.0 calls |
| U4-books (live) | 3/3 · 21,980 tok · 7.0 calls |

## Failures

