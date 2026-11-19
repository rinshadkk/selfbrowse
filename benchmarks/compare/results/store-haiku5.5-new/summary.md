# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 16/16 (100%) | 3.2 | 27,630 | 71,517 | 11,757 | 23 |
| selfbrowse | 16/16 (100%) | 4.9 | 10,273 | 38,837 | 1,462 | 16 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 12,180 tok · 2.0 calls | 2/2 · 5,110 tok · 3.0 calls |
| T2-search | 2/2 · 22,692 tok · 3.0 calls | 2/2 · 9,360 tok · 5.0 calls |
| T3-navigate | 2/2 · 33,068 tok · 4.0 calls | 2/2 · 11,615 tok · 6.0 calls |
| T4-cart | 2/2 · 38,237 tok · 4.5 calls | 2/2 · 13,926 tok · 7.0 calls |
| T5-login | 2/2 · 22,589 tok · 3.0 calls | 2/2 · 9,614 tok · 5.0 calls |
| T6-paginate | 2/2 · 34,056 tok · 4.0 calls | 2/2 · 15,272 tok · 7.0 calls |
| T7-live-hn (live) | 2/2 · 19,210 tok · 2.0 calls | 2/2 · 10,486 tok · 3.0 calls |
| T8-live-wiki (live) | 2/2 · 39,006 tok · 3.5 calls | 2/2 · 6,800 tok · 3.0 calls |

## Failures

