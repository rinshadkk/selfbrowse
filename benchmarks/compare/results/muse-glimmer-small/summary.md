# Benchmark: model `muse-glimmer-bench`, 1 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 3/6 (50%) | 3.5 | 36,075 | 18,070 | 11,620 | 250 |
| selfbrowse-json | 5/6 (83%) | 6.3 | 9,440 | 6,668 | 2,924 | 64 |
| selfbrowse-native | 6/6 (100%) | 5.5 | 7,563 | 8,786 | 1,009 | 75 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse-json | selfbrowse-native |
|---|---|---|---|
| T1-read-text | 0/1 · 34,776 tok · 3.0 calls | 1/1 · 2,967 tok · 3.0 calls | 1/1 · 3,573 tok · 3.0 calls |
| T2-search | 0/1 · 46,964 tok · 4.0 calls | 1/1 · 18,396 tok · 7.0 calls | 1/1 · 8,277 tok · 6.0 calls |
| T3-navigate | 1/1 · 36,892 tok · 4.0 calls | 1/1 · 9,139 tok · 7.0 calls | 1/1 · 8,065 tok · 6.0 calls |
| T4-cart | 1/1 · 36,864 tok · 4.0 calls | 0/1 · 11,309 tok · 9.0 calls | 1/1 · 6,412 tok · 5.0 calls |
| T5-login | 1/1 · 25,189 tok · 3.0 calls | 1/1 · 5,336 tok · 5.0 calls | 1/1 · 8,054 tok · 6.0 calls |
| T6-paginate | 0/1 · 35,763 tok · 3.0 calls | 1/1 · 9,492 tok · 7.0 calls | 1/1 · 10,999 tok · 7.0 calls |

## Failures

- rep1 T1-read-text browser-use: timeout after 300s
- rep1 T2-search browser-use: timeout after 300s
- rep1 T4-cart selfbrowse-json: wrong answer: 'Desk Lamp added to cart (3 units). Task complete.'
- rep1 T6-paginate browser-use: timeout after 300s
