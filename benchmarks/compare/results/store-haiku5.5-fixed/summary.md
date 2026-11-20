# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 16/16 (100%) | 4.8 | 9,851 | 39,129 | 1,462 | 17 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| T1-read-text | 2/2 · 5,096 tok · 3.0 calls |
| T2-search | 2/2 · 9,449 tok · 5.0 calls |
| T3-navigate | 2/2 · 11,568 tok · 6.0 calls |
| T4-cart | 2/2 · 13,856 tok · 7.0 calls |
| T5-login | 2/2 · 8,458 tok · 4.5 calls |
| T6-paginate | 2/2 · 15,362 tok · 7.0 calls |
| T7-live-hn (live) | 2/2 · 7,938 tok · 2.5 calls |
| T8-live-wiki (live) | 2/2 · 7,081 tok · 3.0 calls |

## Failures

