# Benchmark: model `claude-sonnet-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 16/16 (100%) | 3.3 | 27,956 | 77,821 | 11,702 | 20 |
| selfbrowse | 15/16 (94%) | 4.8 | 9,064 | 23,114 | 1,256 | 14 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 12,113 tok · 2.0 calls | 2/2 · 4,416 tok · 3.0 calls |
| T2-search | 2/2 · 22,494 tok · 3.0 calls | 2/2 · 8,226 tok · 5.0 calls |
| T3-navigate | 2/2 · 32,600 tok · 4.0 calls | 2/2 · 10,238 tok · 6.0 calls |
| T4-cart | 2/2 · 32,605 tok · 4.0 calls | 2/2 · 11,266 tok · 6.5 calls |
| T5-login | 2/2 · 22,380 tok · 3.0 calls | 2/2 · 6,463 tok · 4.0 calls |
| T6-paginate | 2/2 · 50,120 tok · 5.5 calls | 1/2 · 16,988 tok · 8.0 calls |
| T7-live-hn (live) | 2/2 · 19,105 tok · 2.0 calls | 2/2 · 4,962 tok · 2.0 calls |
| T8-live-wiki (live) | 2/2 · 32,232 tok · 3.0 calls | 2/2 · 9,950 tok · 4.0 calls |

## Failures

- rep1 T6-paginate selfbrowse: wrong answer: "SKU ZX-4471 isn't in the list. The list has 4 pages of 10 items each, and the SK"
