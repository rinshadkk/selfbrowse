# Benchmark: model `claude-haiku-5-5`, 3 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 3/3 (100%) | 3.3 | 41,894 | 111,351 | 10,014 | 34 |
| fastbrowse | 3/3 (100%) | 0.0 | 0 | 0 | nan | 18 |
| selfbrowse | 3/3 (100%) | 7.7 | 20,838 | 61,474 | 1,366 | 32 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | fastbrowse | selfbrowse |
|---|---|---|---|
| K2-flights (live) | 3/3 · 41,894 tok · 3.3 calls | 3/3 · 0 tok · 0.0 calls | 3/3 · 20,838 tok · 7.7 calls |

## Failures

