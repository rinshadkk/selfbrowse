# Benchmark: model `claude-haiku-5-5`, 3 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 9/9 (100%) | 5.0 | 9,698 | 38,559 | 1,472 | 18 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| W1-dropdowns | 3/3 · 16,700 tok · 8.0 calls |
| W2-drag | 3/3 · 7,318 tok · 4.0 calls |
| W3-upload | 3/3 · 5,076 tok · 3.0 calls |

## Failures

