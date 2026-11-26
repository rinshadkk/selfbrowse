# Benchmark: model `claude-sonnet-5-5`, 10 runs per task, max 30 steps, 900 s per run

Tokens are what the model itself reported for every call: input is the full prompt (cached text included), output is everything it generated (reasoning included). Per-call records are in `calls.jsonl`.

## Overall (averages per run)

| Library | Success | Model calls | Input tokens | Output tokens | Total tokens | First-call input | Wall s |
|---|---|---|---|---|---|---|---|
| browser-use | 9/10 (90%) | 4.9 | 144,849 | 3,330 | 148,179 | 36,047 | 34 |
| selfbrowse | 10/10 (100%) | 10.1 | 55,248 | 1,850 | 57,098 | 3,806 | 32 |

## Totals across all runs

| Library | Runs | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| browser-use | 10 | 49 | 1,448,486 | 33,303 | 1,481,789 |
| selfbrowse | 10 | 101 | 552,483 | 18,495 | 570,978 |

## Only the 1 tasks every library passed (averages per run)

| Library | Model calls | Input tokens | Output tokens | Total tokens | Wall s |
|---|---|---|---|---|---|
| browser-use | 5.0 | 149,266 | 3,327 | 152,594 | 35 |
| selfbrowse | 10.1 | 55,248 | 1,850 | 57,098 | 32 |

## Per task (successes / runs, average total tokens, model calls)

| Task | browser-use | selfbrowse |
|---|---|---|
| T6-paginate | 9/10 · 148,179 tok · 4.9 calls | 10/10 · 57,098 tok · 10.1 calls |

## How the tokens were counted

| Library | Calls | Calls with no usage reported | Generic-tokenizer estimate of what was sent (not used above) |
|---|---|---|---|
| browser-use | 49 | 0 | 438,514 |
| selfbrowse | 101 | 0 | 258,570 |

The estimate uses one generic tokenizer over each request body, JSON schemas included. A local model reads a response schema as a grammar, not as prompt text, so the estimate overstates libraries that send a large schema. Any call with no usage reported would make the totals too low; the column above should be 0.

## Failures

- rep4 T6-paginate browser-use: wrong answer: "I couldn't find an item with SKU ZX-4471 on the list, so I have no name to give "
