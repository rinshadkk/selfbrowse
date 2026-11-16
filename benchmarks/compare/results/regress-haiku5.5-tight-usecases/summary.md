# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 11/12 (92%) | 4.1 | 11,626 | 42,009 | 1,373 | 17 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| U1-github (live) | 2/2 · 9,692 tok · 3.5 calls |
| U2-pypi (live) | 1/2 · 4,889 tok · 2.5 calls |
| U3-wikipedia (live) | 2/2 · 8,277 tok · 3.0 calls |
| U4-books (live) | 2/2 · 21,938 tok · 7.0 calls |
| U5-pydocs (live) | 2/2 · 19,726 tok · 6.5 calls |
| T7-live-hn (live) | 2/2 · 5,233 tok · 2.0 calls |

## Failures

- rep1 U2-pypi selfbrowse: blocked: the site is asking to verify you are human at https://pypi.org/search/?q=httpx. Re-run with --headed so you can complete it yourself.
