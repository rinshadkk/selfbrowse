# Benchmark: model `claude-haiku-5-5`, 1 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 1/1 (100%) | 5.0 | 75,856 | 159,831 | 10,013 | 42 |
| fastbrowse | 1/1 (100%) | 0.0 | 0 | 0 | nan | 44 |
| selfbrowse | 0/1 (0%) | 50.0 | 312,248 | 566,350 | 1,326 | 221 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | fastbrowse | selfbrowse |
|---|---|---|---|
| K2-flights (live) | 1/1 · 75,856 tok · 5.0 calls | 1/1 · 0 tok · 0.0 calls | 0/1 · 312,248 tok · 50.0 calls |

## Failures

- rep1 K2-flights selfbrowse: stopped after 50 steps without finishing
