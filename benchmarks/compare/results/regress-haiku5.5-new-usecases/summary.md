# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 12/12 (100%) | 4.4 | 13,532 | 44,963 | 1,403 | 19 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| U1-github (live) | 2/2 · 10,578 tok · 3.5 calls |
| U2-pypi (live) | 2/2 · 6,778 tok · 3.0 calls |
| U3-wikipedia (live) | 2/2 · 14,130 tok · 4.0 calls |
| U4-books (live) | 2/2 · 22,292 tok · 7.0 calls |
| U5-pydocs (live) | 2/2 · 19,618 tok · 6.5 calls |
| T7-live-hn (live) | 2/2 · 7,797 tok · 2.5 calls |

## Failures

