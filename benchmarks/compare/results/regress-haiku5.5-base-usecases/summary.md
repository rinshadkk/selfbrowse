# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 12/12 (100%) | 4.2 | 11,999 | 41,666 | 1,333 | 20 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| U1-github (live) | 2/2 · 10,274 tok · 3.5 calls |
| U2-pypi (live) | 2/2 · 6,828 tok · 3.5 calls |
| U3-wikipedia (live) | 2/2 · 7,957 tok · 3.0 calls |
| U4-books (live) | 2/2 · 19,938 tok · 6.5 calls |
| U5-pydocs (live) | 2/2 · 19,358 tok · 6.5 calls |
| T7-live-hn (live) | 2/2 · 7,639 tok · 2.5 calls |

## Failures

