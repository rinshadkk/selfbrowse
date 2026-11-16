# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse | 15/16 (94%) | 5.1 | 10,364 | 37,852 | 1,404 | 21 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse |
|---|---|
| T1-read-text | 2/2 · 4,912 tok · 3.0 calls |
| T2-search | 2/2 · 9,134 tok · 5.0 calls |
| T3-navigate | 2/2 · 11,217 tok · 6.0 calls |
| T4-cart | 1/2 · 16,180 tok · 8.0 calls |
| T5-login | 2/2 · 11,408 tok · 6.0 calls |
| T6-paginate | 2/2 · 15,386 tok · 7.0 calls |
| T7-live-hn (live) | 2/2 · 7,818 tok · 2.5 calls |
| T8-live-wiki (live) | 2/2 · 6,858 tok · 3.0 calls |

## Failures

- rep2 T4-cart selfbrowse: wrong answer: 'The Desk Lamp is added to the cart. The product page now shows "Added to cart." '
