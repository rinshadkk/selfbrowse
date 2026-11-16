# Benchmark: model `claude-haiku-5-5`, 1 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 0/1 (0%) | 49.0 | 305,919 | 512,222 | 1,328 | 210 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| K1-kayak (live) | 0/1 · 305,919 tok · 49.0 calls |

## Failures

- rep1 K1-kayak selfbrowse: wrong answer: "I could not find the cheapest COK to ORD fare for Dec 26 for 4 travelers. Kayak'"
