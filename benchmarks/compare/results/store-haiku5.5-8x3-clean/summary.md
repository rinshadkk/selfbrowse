# Benchmark: model `claude-haiku-5-5`, 3 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 24/24 (100%) | 3.2 | 26,686 | 64,863 | 11,724 | 27 |
| selfbrowse | 24/24 (100%) | 4.8 | 10,014 | 38,752 | 1,462 | 25 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 3/3 · 12,199 tok · 2.0 calls | 3/3 · 5,106 tok · 3.0 calls |
| T2-search | 3/3 · 22,704 tok · 3.0 calls | 3/3 · 9,415 tok · 5.0 calls |
| T3-navigate | 3/3 · 33,006 tok · 4.0 calls | 3/3 · 11,582 tok · 6.0 calls |
| T4-cart | 3/3 · 32,921 tok · 4.0 calls | 3/3 · 13,145 tok · 6.7 calls |
| T5-login | 3/3 · 22,544 tok · 3.0 calls | 3/3 · 9,469 tok · 5.0 calls |
| T6-paginate | 3/3 · 34,038 tok · 4.0 calls | 3/3 · 15,483 tok · 7.0 calls |
| T7-live-hn (live) | 3/3 · 19,334 tok · 2.0 calls | 3/3 · 8,842 tok · 2.7 calls |
| T8-live-wiki (live) | 3/3 · 36,744 tok · 3.3 calls | 3/3 · 7,072 tok · 3.0 calls |

## Failures

