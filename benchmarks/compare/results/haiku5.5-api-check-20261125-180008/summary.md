# Benchmark: model `claude-haiku-5-5`, 1 runs per task, max 30 steps, 900 s per run

Tokens are what the model itself reported for every call: input is the full prompt (cached text included), output is everything it generated (reasoning included). Per-call records are in `calls.jsonl`.

## Overall (averages per run)

| Library | Success | Model calls | Input tokens | Output tokens | Total tokens | First-call input | Wall s |
|---|---|---|---|---|---|---|---|
| browser-use | 1/1 (100%) | 2.0 | 18,550 | 764 | 19,314 | 15,356 | 8 |
| selfbrowse | 1/1 (100%) | 3.0 | 7,463 | 212 | 7,675 | 2,299 | 5 |

## Totals across all runs

| Library | Runs | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| browser-use | 1 | 2 | 18,550 | 764 | 19,314 |
| selfbrowse | 1 | 3 | 7,463 | 212 | 7,675 |

## Only the 1 tasks every library passed (averages per run)

| Library | Model calls | Input tokens | Output tokens | Total tokens | Wall s |
|---|---|---|---|---|---|
| browser-use | 2.0 | 18,550 | 764 | 19,314 | 8 |
| selfbrowse | 3.0 | 7,463 | 212 | 7,675 | 5 |

## Per task (successes / runs, average total tokens, model calls)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 1/1 · 19,314 tok · 2.0 calls | 1/1 · 7,675 tok · 3.0 calls |

## How the tokens were counted

| Library | Calls | Calls with no usage reported | Generic-tokenizer estimate of what was sent (not used above) |
|---|---|---|---|
| browser-use | 2 | 0 | 12,246 |
| selfbrowse | 3 | 0 | 5,059 |

The estimate uses one generic tokenizer over each request body, JSON schemas included. A local model reads a response schema as a grammar, not as prompt text, so the estimate overstates libraries that send a large schema. Any call with no usage reported would make the totals too low; the column above should be 0.

## Failures

