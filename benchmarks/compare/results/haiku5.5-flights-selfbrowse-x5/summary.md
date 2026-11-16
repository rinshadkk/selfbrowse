# Benchmark: model `claude-haiku-5-5`, 5 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 4/5 (80%) | 22.2 | 111,342 | 222,039 | 1,326 | 101 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| K2-flights (live) | 4/5 · 111,342 tok · 22.2 calls |

## Failures

- rep5 K2-flights selfbrowse: stopped after 50 steps without finishing
