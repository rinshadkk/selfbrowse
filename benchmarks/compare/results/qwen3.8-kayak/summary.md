# Benchmark: model `qwen3.8-bench`, 1 runs per task, max 30 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 0/1 (0%) | 17.0 | 244,571 | 154,778 | 11,355 | 900 |
| selfbrowse | 0/1 (0%) | 30.0 | 88,275 | 78,907 | 1,121 | 341 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| K1-kayak (live) | 0/1 · 244,571 tok · 17.0 calls | 0/1 · 88,275 tok · 30.0 calls |

## Failures

- rep1 K1-kayak selfbrowse: stopped after 30 steps without finishing
- rep1 K1-kayak browser-use: timeout after 900s
