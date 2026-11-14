# Benchmark: model `claude-sonnet-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 15/16 (94%) | 4.8 | 9,281 | 23,045 | 1,334 | 14 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| T1-read-text | 2/2 · 4,664 tok · 3.0 calls |
| T2-search | 2/2 · 8,686 tok · 5.0 calls |
| T3-navigate | 2/2 · 10,612 tok · 6.0 calls |
| T4-cart | 2/2 · 11,730 tok · 6.5 calls |
| T5-login | 2/2 · 6,686 tok · 4.0 calls |
| T6-paginate | 1/2 · 16,462 tok · 7.5 calls |
| T7-live-hn (live) | 2/2 · 5,165 tok · 2.0 calls |
| T8-live-wiki (live) | 2/2 · 10,247 tok · 4.0 calls |

## Failures

- rep1 T6-paginate selfbrowse: wrong answer: 'SKU ZX-4471 does not exist in the parts list. The list has 4 pages covering ZX-4'
