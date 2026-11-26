# Benchmark: model `claude-sonnet-5-5`, 2 runs per task, max 30 steps, 900 s per run

Tokens are what the model itself reported for every call: input is the full prompt (cached text included), output is everything it generated (reasoning included). Per-call records are in `calls.jsonl`.

## Overall (averages per run)

| Library | Success | Model calls | Input tokens | Output tokens | Total tokens | First-call input | Wall s |
|---|---|---|---|---|---|---|---|
| browser-use | 26/26 (100%) | 3.4 | 93,090 | 1,972 | 95,063 | 36,345 | 24 |
| selfbrowse | 25/26 (96%) | 4.4 | 24,521 | 664 | 25,185 | 3,808 | 16 |

## Totals across all runs

| Library | Runs | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| browser-use | 26 | 88 | 2,420,353 | 51,282 | 2,471,635 |
| selfbrowse | 26 | 115 | 637,545 | 17,264 | 654,809 |

## Only the 13 tasks every library passed (averages per run)

| Library | Model calls | Input tokens | Output tokens | Total tokens | Wall s |
|---|---|---|---|---|---|
| browser-use | 3.4 | 93,090 | 1,972 | 95,063 | 24 |
| selfbrowse | 4.4 | 24,632 | 648 | 25,280 | 16 |

## Per task (successes / runs, average total tokens, model calls)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 28,192 tok · 2.0 calls | 2/2 · 17,078 tok · 3.0 calls |
| T2-search | 2/2 · 67,034 tok · 3.0 calls | 2/2 · 26,562 tok · 5.0 calls |
| T3-navigate | 2/2 · 113,162 tok · 4.5 calls | 2/2 · 30,874 tok · 6.0 calls |
| T4-cart | 2/2 · 113,225 tok · 4.0 calls | 2/2 · 35,902 tok · 7.0 calls |
| T5-login | 2/2 · 73,313 tok · 3.0 calls | 2/2 · 19,429 tok · 4.0 calls |
| T6-paginate | 2/2 · 163,490 tok · 5.5 calls | 1/2 · 39,819 tok · 8.0 calls |
| T7-live-hn (live) | 2/2 · 45,992 tok · 2.0 calls | 2/2 · 14,636 tok · 2.0 calls |
| T8-live-wiki (live) | 2/2 · 99,113 tok · 3.0 calls | 2/2 · 18,747 tok · 3.0 calls |
| U1-github (live) | 2/2 · 95,540 tok · 3.0 calls | 2/2 · 20,270 tok · 3.0 calls |
| U2-pypi (live) | 2/2 · 86,810 tok · 3.0 calls | 2/2 · 30,166 tok · 5.0 calls |
| U3-wikipedia (live) | 2/2 · 138,180 tok · 3.5 calls | 2/2 · 20,480 tok · 3.0 calls |
| U4-books (live) | 2/2 · 114,535 tok · 4.5 calls | 2/2 · 34,612 tok · 5.0 calls |
| U5-pydocs (live) | 2/2 · 97,230 tok · 3.0 calls | 2/2 · 18,830 tok · 3.5 calls |

## How the tokens were counted

| Library | Calls | Calls with no usage reported | Generic-tokenizer estimate of what was sent (not used above) |
|---|---|---|---|
| browser-use | 88 | 0 | 794,205 |
| selfbrowse | 115 | 0 | 257,840 |

The estimate uses one generic tokenizer over each request body, JSON schemas included. A local model reads a response schema as a grammar, not as prompt text, so the estimate overstates libraries that send a large schema. Any call with no usage reported would make the totals too low; the column above should be 0.

## Failures

- rep1 T6-paginate selfbrowse: wrong answer: 'SKU ZX-4471 is not in the parts list. The list has 4 pages and covers only ZX-44'
