# Benchmark: model `qwen3.8-bench`, 3 runs per task, max 30 steps, 900 s per run

Tokens are what the model itself reported for every call: input is the full prompt (cached text included), output is everything it generated (reasoning included). Per-call records are in `calls.jsonl`.

## Overall (averages per run)

| Library | Success | Model calls | Input tokens | Output tokens | Total tokens | First-call input | Wall s |
|---|---|---|---|---|---|---|---|
| browser-use | 3/3 (100%) | 3.0 | 18,823 | 1,584 | 20,407 | 5,850 | 173 |
| selfbrowse | 3/3 (100%) | 14.3 | 53,439 | 1,200 | 54,639 | 945 | 206 |

## Totals across all runs

| Library | Runs | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| browser-use | 3 | 9 | 56,469 | 4,751 | 61,220 |
| selfbrowse | 3 | 43 | 160,316 | 3,601 | 163,917 |

## Only the 1 tasks every library passed (averages per run)

| Library | Model calls | Input tokens | Output tokens | Total tokens | Wall s |
|---|---|---|---|---|---|
| browser-use | 3.0 | 18,823 | 1,584 | 20,407 | 173 |
| selfbrowse | 14.3 | 53,439 | 1,200 | 54,639 | 206 |

## Per task (successes / runs, average total tokens, model calls)

| Task | browser-use | selfbrowse |
|---|---|---|
| U5-pydocs (live) | 3/3 · 20,407 tok · 3.0 calls | 3/3 · 54,639 tok · 14.3 calls |

## How the tokens were counted

| Library | Calls | Calls with no usage reported | Generic-tokenizer estimate of what was sent (not used above) |
|---|---|---|---|
| browser-use | 9 | 0 | 89,994 |
| selfbrowse | 43 | 0 | 175,582 |

The estimate uses one generic tokenizer over each request body, JSON schemas included. A local model reads a response schema as a grammar, not as prompt text, so the estimate overstates libraries that send a large schema. Any call with no usage reported would make the totals too low; the column above should be 0.

## Failures

