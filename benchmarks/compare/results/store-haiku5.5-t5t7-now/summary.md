# Benchmark: model `claude-haiku-5-5`, 5 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 10/10 (100%) | 4.0 | 9,759 | 34,149 | 1,462 | 14 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| T5-login | 5/5 · 9,910 tok · 5.2 calls |
| T7-live-hn (live) | 5/5 · 9,608 tok · 2.8 calls |

## Failures

