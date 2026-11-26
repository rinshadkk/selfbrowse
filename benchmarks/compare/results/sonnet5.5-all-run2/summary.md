# Benchmark: model `claude-sonnet-5-5`, 2 runs per task, max 30 steps, 900 s per run

Tokens are what the model itself reported for every call: input is the full prompt (cached text included), output is everything it generated (reasoning included). Per-call records are in `calls.jsonl`.

## Overall (averages per run)

| Library | Success | Model calls | Input tokens | Output tokens | Total tokens | First-call input | Wall s |
|---|---|---|---|---|---|---|---|
| browser-use | 26/26 (100%) | 3.2 | 86,838 | 1,795 | 88,633 | 37,922 | 21 |
| selfbrowse | 25/26 (96%) | 4.9 | 26,995 | 696 | 27,691 | 3,808 | 15 |

## Totals across all runs

| Library | Runs | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| browser-use | 26 | 82 | 2,257,788 | 46,660 | 2,304,448 |
| selfbrowse | 26 | 128 | 701,869 | 18,105 | 719,974 |

## Only the 13 tasks every library passed (averages per run)

| Library | Model calls | Input tokens | Output tokens | Total tokens | Wall s |
|---|---|---|---|---|---|
| browser-use | 3.2 | 86,838 | 1,795 | 88,633 | 21 |
| selfbrowse | 4.6 | 25,436 | 642 | 26,079 | 15 |

## Per task (successes / runs, average total tokens, model calls)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 37,720 tok · 2.0 calls | 2/2 · 17,040 tok · 3.0 calls |
| T2-search | 2/2 · 76,099 tok · 3.0 calls | 2/2 · 26,386 tok · 5.0 calls |
| T3-navigate | 2/2 · 89,318 tok · 4.0 calls | 2/2 · 28,652 tok · 6.0 calls |
| T4-cart | 2/2 · 113,367 tok · 4.0 calls | 2/2 · 35,828 tok · 7.0 calls |
| T5-login | 2/2 · 61,334 tok · 3.0 calls | 2/2 · 17,128 tok · 4.0 calls |
| T6-paginate | 2/2 · 124,080 tok · 4.0 calls | 1/2 · 65,444 tok · 12.5 calls |
| T7-live-hn (live) | 2/2 · 61,613 tok · 2.0 calls | 2/2 · 14,716 tok · 2.0 calls |
| T8-live-wiki (live) | 2/2 · 99,053 tok · 3.0 calls | 2/2 · 18,814 tok · 3.0 calls |
| U1-github (live) | 2/2 · 97,235 tok · 3.0 calls | 2/2 · 21,522 tok · 3.0 calls |
| U2-pypi (live) | 2/2 · 78,688 tok · 3.0 calls | 2/2 · 30,087 tok · 5.5 calls |
| U3-wikipedia (live) | 2/2 · 103,760 tok · 3.0 calls | 2/2 · 17,086 tok · 3.0 calls |
| U4-books (live) | 2/2 · 121,980 tok · 4.0 calls | 2/2 · 38,001 tok · 5.0 calls |
| U5-pydocs (live) | 2/2 · 87,976 tok · 3.0 calls | 2/2 · 29,280 tok · 5.0 calls |

## How the tokens were counted

| Library | Calls | Calls with no usage reported | Generic-tokenizer estimate of what was sent (not used above) |
|---|---|---|---|
| browser-use | 82 | 0 | 737,509 |
| selfbrowse | 128 | 0 | 301,747 |

The estimate uses one generic tokenizer over each request body, JSON schemas included. A local model reads a response schema as a grammar, not as prompt text, so the estimate overstates libraries that send a large schema. Any call with no usage reported would make the totals too low; the column above should be 0.

## Failures

- rep1 T6-paginate selfbrowse: wrong answer: 'SKU ZX-4471 does not exist on the site. The parts list has only 40 items (ZX-440'
