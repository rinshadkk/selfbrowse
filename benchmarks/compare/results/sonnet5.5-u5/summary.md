# Benchmark: model `claude-sonnet-5-5`, 3 runs per task, max 30 steps, 900 s per run

Tokens are what the model itself reported for every call: input is the full prompt (cached text included), output is everything it generated (reasoning included). Per-call records are in `calls.jsonl`.

## Overall (averages per run)

| Library | Success | Model calls | Input tokens | Output tokens | Total tokens | First-call input | Wall s |
|---|---|---|---|---|---|---|---|
| browser-use | 3/3 (100%) | 3.0 | 80,438 | 1,783 | 82,221 | 24,597 | 24 |
| selfbrowse | 3/3 (100%) | 3.7 | 21,425 | 578 | 22,003 | 3,805 | 12 |

## Totals across all runs

| Library | Runs | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| browser-use | 3 | 9 | 241,314 | 5,350 | 246,664 |
| selfbrowse | 3 | 11 | 64,276 | 1,733 | 66,009 |

## Only the 1 tasks every library passed (averages per run)

| Library | Model calls | Input tokens | Output tokens | Total tokens | Wall s |
|---|---|---|---|---|---|
| browser-use | 3.0 | 80,438 | 1,783 | 82,221 | 24 |
| selfbrowse | 3.7 | 21,425 | 578 | 22,003 | 12 |

## Per task (successes / runs, average total tokens, model calls)

| Task | browser-use | selfbrowse |
|---|---|---|
| U5-pydocs (live) | 3/3 · 82,221 tok · 3.0 calls | 3/3 · 22,003 tok · 3.7 calls |

## How the tokens were counted

| Library | Calls | Calls with no usage reported | Generic-tokenizer estimate of what was sent (not used above) |
|---|---|---|---|
| browser-use | 9 | 0 | 81,577 |
| selfbrowse | 11 | 0 | 26,940 |

The estimate uses one generic tokenizer over each request body, JSON schemas included. A local model reads a response schema as a grammar, not as prompt text, so the estimate overstates libraries that send a large schema. Any call with no usage reported would make the totals too low; the column above should be 0.

## Failures

