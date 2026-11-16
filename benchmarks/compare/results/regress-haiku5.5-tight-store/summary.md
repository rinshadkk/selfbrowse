# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 16/16 (100%) | 4.9 | 9,869 | 37,528 | 1,374 | 17 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| T1-read-text | 2/2 · 4,836 tok · 3.0 calls |
| T2-search | 2/2 · 8,965 tok · 5.0 calls |
| T3-navigate | 2/2 · 11,061 tok · 6.0 calls |
| T4-cart | 2/2 · 13,312 tok · 7.0 calls |
| T5-login | 2/2 · 9,172 tok · 5.0 calls |
| T6-paginate | 2/2 · 17,924 tok · 8.0 calls |
| T7-live-hn (live) | 2/2 · 5,248 tok · 2.0 calls |
| T8-live-wiki (live) | 2/2 · 8,436 tok · 3.0 calls |

## Failures

