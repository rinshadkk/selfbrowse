# Benchmark: model `claude-haiku-5-5`, 1 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 0/1 (0%) | 2.0 | 2,933 | 15,421 | 1,328 | 13 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| K1-kayak (live) | 0/1 · 2,933 tok · 2.0 calls |

## Failures

- rep1 K1-kayak selfbrowse: blocked: the site is asking to verify you are human at https://www.kayak.com/security/check?out=%2Fflights%2FCOK-ORD%2F2026-12-26%2F4adults&t=DXUqLlMYYSoXq2OubFarqFGXV9I. Re-run with --headed so you can complete it yourself.
