# Benchmark: model `claude-haiku-5-5`, 1 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 0/1 (0%) | 8.0 | 85,496 | 233,125 | 10,015 | 70 |
| selfbrowse | 0/1 (0%) | 37.0 | 183,478 | 349,537 | 1,328 | 173 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| K1-kayak (live) | 0/1 · 85,496 tok · 8.0 calls | 0/1 · 183,478 tok · 37.0 calls |

## Failures

- rep1 K1-kayak selfbrowse: wrong answer: 'I could not find the cheapest COK to ORD fare for Dec 26, 2026 for 4 people. Kay'
- rep1 K1-kayak browser-use: wrong answer: 'I could not find the cheapest one-way fare from COK to ORD on Dec 26, 2026 for 4'
