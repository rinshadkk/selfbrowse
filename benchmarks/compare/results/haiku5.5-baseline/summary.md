# Benchmark: model `claude-haiku-5-5`, 2 runs per task, max 30 steps, 900 s per run

Tokens are what the model itself reported for every call: input is the full prompt (cached text included), output is everything it generated (reasoning included). Per-call records are in `calls.jsonl`.

## Overall (averages per run)

| Library | Success | Model calls | Input tokens | Output tokens | Total tokens | First-call input | Wall s |
|---|---|---|---|---|---|---|---|
| browser-use | 26/26 (100%) | 4.5 | 64,768 | 1,893 | 66,661 | 17,703 | 14 |
| selfbrowse | 26/26 (100%) | 5.3 | 18,931 | 589 | 19,520 | 2,306 | 7 |

## Totals across all runs

| Library | Runs | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| browser-use | 26 | 117 | 1,683,967 | 49,219 | 1,733,186 |
| selfbrowse | 26 | 139 | 492,212 | 15,312 | 507,524 |

## Only the 13 tasks every library passed (averages per run)

| Library | Model calls | Input tokens | Output tokens | Total tokens | Wall s |
|---|---|---|---|---|---|
| browser-use | 4.5 | 64,768 | 1,893 | 66,661 | 14 |
| selfbrowse | 5.3 | 18,931 | 589 | 19,520 | 7 |

## Per task (successes / runs, average total tokens, model calls)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 19,238 tok · 2.0 calls | 2/2 · 7,845 tok · 3.0 calls |
| T2-search | 2/2 · 51,779 tok · 4.5 calls | 2/2 · 14,050 tok · 5.0 calls |
| T3-navigate | 2/2 · 50,820 tok · 4.0 calls | 2/2 · 16,276 tok · 6.0 calls |
| T4-cart | 2/2 · 74,804 tok · 5.5 calls | 2/2 · 19,680 tok · 7.0 calls |
| T5-login | 2/2 · 35,191 tok · 3.0 calls | 2/2 · 16,926 tok · 6.0 calls |
| T6-paginate | 2/2 · 102,132 tok · 7.0 calls | 2/2 · 20,650 tok · 7.0 calls |
| T7-live-hn (live) | 2/2 · 26,216 tok · 2.0 calls | 2/2 · 7,869 tok · 2.0 calls |
| T8-live-wiki (live) | 2/2 · 71,206 tok · 4.0 calls | 2/2 · 15,384 tok · 4.0 calls |
| U1-github (live) | 2/2 · 63,204 tok · 3.5 calls | 2/2 · 49,732 tok · 9.0 calls |
| U2-pypi (live) | 2/2 · 38,377 tok · 3.0 calls | 2/2 · 27,180 tok · 7.0 calls |
| U3-wikipedia (live) | 2/2 · 96,964 tok · 5.0 calls | 2/2 · 14,770 tok · 3.5 calls |
| U4-books (live) | 2/2 · 151,892 tok · 10.0 calls | 2/2 · 28,153 tok · 6.0 calls |
| U5-pydocs (live) | 2/2 · 84,770 tok · 5.0 calls | 2/2 · 15,248 tok · 4.0 calls |

## How the tokens were counted

| Library | Calls | Calls with no usage reported | Generic-tokenizer estimate of what was sent (not used above) |
|---|---|---|---|
| browser-use | 117 | 0 | 1,156,592 |
| selfbrowse | 139 | 0 | 360,362 |

The estimate uses one generic tokenizer over each request body, JSON schemas included, so it is not the model's own count: a local model may read a response schema as a grammar rather than as prompt text, and a hosted model has its own tokenizer. Any call with no usage reported would make the totals too low; the column above should be 0.

## Failures

