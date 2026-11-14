# Benchmark: model `claude-sonnet-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 12/12 (100%) | 5.0 | 14,323 | 33,140 | 1,333 | 15 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| U1-github (live) | 2/2 · 8,214 tok · 3.0 calls |
| U2-pypi (live) | 2/2 · 13,196 tok · 6.5 calls |
| U3-wikipedia (live) | 2/2 · 28,852 tok · 8.0 calls |
| U4-books (live) | 2/2 · 14,850 tok · 5.0 calls |
| U5-pydocs (live) | 2/2 · 15,671 tok · 5.5 calls |
| T7-live-hn (live) | 2/2 · 5,156 tok · 2.0 calls |

## Failures

