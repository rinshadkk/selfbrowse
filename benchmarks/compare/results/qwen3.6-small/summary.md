# Benchmark: model `qwen3.6-bench`, 1 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 6/6 (100%) | 4.2 | 39,490 | 21,692 | 11,620 | 52 |
| selfbrowse-json | 6/6 (100%) | 7.7 | 9,990 | 8,180 | 828 | 30 |
| selfbrowse-native | 6/6 (100%) | 6.3 | 9,040 | 9,697 | 1,009 | 15 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse-json | selfbrowse-native |
|---|---|---|---|
| T1-read-text | 1/1 · 25,018 tok · 3.0 calls | 1/1 · 4,251 tok · 4.0 calls | 1/1 · 5,037 tok · 4.0 calls |
| T2-search | 1/1 · 25,201 tok · 3.0 calls | 1/1 · 20,815 tok · 14.0 calls | 1/1 · 10,085 tok · 7.0 calls |
| T3-navigate | 1/1 · 36,839 tok · 4.0 calls | 1/1 · 8,223 tok · 7.0 calls | 1/1 · 9,855 tok · 7.0 calls |
| T4-cart | 1/1 · 36,758 tok · 4.0 calls | 1/1 · 6,674 tok · 6.0 calls | 1/1 · 8,007 tok · 6.0 calls |
| T5-login | 1/1 · 25,091 tok · 3.0 calls | 1/1 · 6,538 tok · 6.0 calls | 1/1 · 8,067 tok · 6.0 calls |
| T6-paginate | 1/1 · 88,036 tok · 8.0 calls | 1/1 · 13,441 tok · 9.0 calls | 1/1 · 13,192 tok · 8.0 calls |

## Failures

