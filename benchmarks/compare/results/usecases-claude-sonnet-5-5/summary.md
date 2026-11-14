# Benchmark: model `claude-sonnet-5-5`, 1 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 6/6 (100%) | 2.8 | 27,311 | 81,833 | 13,888 | 22 |
| selfbrowse | 5/6 (83%) | 7.2 | 22,474 | 47,313 | 1,254 | 22 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| U1-github (live) | 1/1 · 20,434 tok · 2.0 calls | 1/1 · 11,062 tok · 4.0 calls |
| U2-pypi (live) | 1/1 · 24,765 tok · 3.0 calls | 1/1 · 17,752 tok · 8.0 calls |
| U3-wikipedia (live) | 1/1 · 32,623 tok · 3.0 calls | 1/1 · 14,638 tok · 5.0 calls |
| U4-books (live) | 1/1 · 39,990 tok · 4.0 calls | 0/1 · 59,965 tok · 15.0 calls |
| U5-pydocs (live) | 1/1 · 26,914 tok · 3.0 calls | 1/1 · 26,466 tok · 9.0 calls |
| T7-live-hn (live) | 1/1 · 19,138 tok · 2.0 calls | 1/1 · 4,963 tok · 2.0 calls |

## Failures

- rep1 U4-books selfbrowse: stopped after 15 steps without finishing
