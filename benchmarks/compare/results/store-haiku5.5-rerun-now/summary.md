# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 16/16 (100%) | 4.9 | 10,336 | 40,781 | 1,462 | 16 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| T1-read-text | 2/2 · 5,102 tok · 3.0 calls |
| T2-search | 2/2 · 9,400 tok · 5.0 calls |
| T3-navigate | 2/2 · 11,573 tok · 6.0 calls |
| T4-cart | 2/2 · 13,942 tok · 7.0 calls |
| T5-login | 2/2 · 10,803 tok · 5.5 calls |
| T6-paginate | 2/2 · 14,120 tok · 6.5 calls |
| T7-live-hn (live) | 2/2 · 10,640 tok · 3.0 calls |
| T8-live-wiki (live) | 2/2 · 7,108 tok · 3.0 calls |

## Failures

