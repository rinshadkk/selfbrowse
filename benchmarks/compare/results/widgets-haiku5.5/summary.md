# Benchmark: model `claude-haiku-5-5`, 3 runs per task, max 50 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 9/9 (100%) | 6.4 | 60,685 | 153,233 | 10,196 | 43 |
| selfbrowse | 8/9 (89%) | 7.0 | 17,489 | 51,076 | 1,472 | 26 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| W1-dropdowns | 3/3 · 61,344 tok · 6.7 calls | 2/3 · 40,053 tok · 14.0 calls |
| W2-drag | 3/3 · 98,104 tok · 9.7 calls | 3/3 · 7,321 tok · 4.0 calls |
| W3-upload | 3/3 · 22,608 tok · 3.0 calls | 3/3 · 5,095 tok · 3.0 calls |

## Failures

- rep2 W1-dropdowns selfbrowse: wrong answer: 'Partial: Favourite fruit is set to Banana, but T-shirt size is still unset. The '
