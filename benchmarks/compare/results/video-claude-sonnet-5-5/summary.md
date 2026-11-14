# Benchmark: model `claude-sonnet-5-5`, 1 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 8/8 (100%) | 3.1 | 25,717 | 81,008 | 11,649 | 21 |
| selfbrowse | 8/8 (100%) | 4.9 | 9,116 | 22,695 | 1,256 | 14 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 1/1 · 12,111 tok · 2.0 calls | 1/1 · 4,426 tok · 3.0 calls |
| T2-search | 1/1 · 22,490 tok · 3.0 calls | 1/1 · 8,300 tok · 5.0 calls |
| T3-navigate | 1/1 · 32,597 tok · 4.0 calls | 1/1 · 10,200 tok · 6.0 calls |
| T4-cart | 1/1 · 32,613 tok · 4.0 calls | 1/1 · 12,357 tok · 7.0 calls |
| T5-login | 1/1 · 22,398 tok · 3.0 calls | 1/1 · 6,473 tok · 4.0 calls |
| T6-paginate | 1/1 · 33,763 tok · 4.0 calls | 1/1 · 16,299 tok · 8.0 calls |
| T7-live-hn (live) | 1/1 · 19,125 tok · 2.0 calls | 1/1 · 4,948 tok · 2.0 calls |
| T8-live-wiki (live) | 1/1 · 30,639 tok · 3.0 calls | 1/1 · 9,922 tok · 4.0 calls |

## Failures

