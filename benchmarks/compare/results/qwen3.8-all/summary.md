# Benchmark: model `qwen3.8-bench`, 1 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 12/13 (92%) | 3.4 | 34,613 | 21,478 | 13,467 | 167 |
| selfbrowse | 12/13 (92%) | 5.7 | 11,810 | 10,348 | 1,128 | 54 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 1/1 · 13,408 tok · 2.0 calls | 1/1 · 3,858 tok · 3.0 calls |
| T2-search | 1/1 · 25,323 tok · 3.0 calls | 1/1 · 6,900 tok · 5.0 calls |
| T3-navigate | 1/1 · 36,731 tok · 4.0 calls | 1/1 · 8,351 tok · 6.0 calls |
| T4-cart | 1/1 · 36,764 tok · 4.0 calls | 1/1 · 8,285 tok · 6.0 calls |
| T5-login | 1/1 · 25,146 tok · 3.0 calls | 1/1 · 6,740 tok · 5.0 calls |
| T6-paginate | 1/1 · 37,830 tok · 4.0 calls | 1/1 · 12,997 tok · 8.0 calls |
| T7-live-hn (live) | 1/1 · 20,440 tok · 2.0 calls | 1/1 · 4,700 tok · 2.0 calls |
| T8-live-wiki (live) | 1/1 · 66,001 tok · 5.0 calls | 1/1 · 10,885 tok · 5.0 calls |
| U1-github (live) | 1/1 · 34,791 tok · 3.0 calls | 1/1 · 6,838 tok · 3.0 calls |
| U2-pypi (live) | 1/1 · 27,421 tok · 3.0 calls | 1/1 · 4,088 tok · 3.0 calls |
| U3-wikipedia (live) | 1/1 · 36,758 tok · 3.0 calls | 1/1 · 10,226 tok · 3.0 calls |
| U4-books (live) | 0/1 · 59,560 tok · 5.0 calls | 1/1 · 28,715 tok · 10.0 calls |
| U5-pydocs (live) | 1/1 · 29,799 tok · 3.0 calls | 0/1 · 40,945 tok · 15.0 calls |

## Failures

- rep1 U4-books browser-use: wrong answer: 'After checking all 2 pages of the Mystery category on books.toscrape.com (32 boo'
- rep1 U5-pydocs selfbrowse: stopped after 15 steps without finishing
