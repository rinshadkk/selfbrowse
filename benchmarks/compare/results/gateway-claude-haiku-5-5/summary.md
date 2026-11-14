# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 16/16 (100%) | 3.2 | 27,033 | 75,857 | 11,703 | 27 |
| selfbrowse | 16/16 (100%) | 4.9 | 9,416 | 38,343 | 1,256 | 23 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 12,182 tok · 2.0 calls | 2/2 · 4,471 tok · 3.0 calls |
| T2-search | 2/2 · 22,598 tok · 3.0 calls | 2/2 · 8,346 tok · 5.0 calls |
| T3-navigate | 2/2 · 32,873 tok · 4.0 calls | 2/2 · 10,349 tok · 6.0 calls |
| T4-cart | 2/2 · 32,934 tok · 4.0 calls | 2/2 · 11,334 tok · 6.5 calls |
| T5-login | 2/2 · 22,580 tok · 3.0 calls | 2/2 · 8,390 tok · 5.0 calls |
| T6-paginate | 2/2 · 33,959 tok · 4.0 calls | 2/2 · 15,078 tok · 7.5 calls |
| T7-live-hn (live) | 2/2 · 19,150 tok · 2.0 calls | 2/2 · 7,394 tok · 2.5 calls |
| T8-live-wiki (live) | 2/2 · 39,986 tok · 3.5 calls | 2/2 · 9,966 tok · 4.0 calls |

## Failures

