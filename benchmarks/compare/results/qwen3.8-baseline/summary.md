# Benchmark: model `qwen3.8-bench`, 2 runs per task, max 30 steps, 900 s per run

Tokens are what the model itself reported for every call: input is the full prompt (cached text included), output is everything it generated (reasoning included). Per-call records are in `calls.jsonl`.

## Overall (averages per run)

| Library | Success | Model calls | Input tokens | Output tokens | Total tokens | First-call input | Wall s |
|---|---|---|---|---|---|---|---|
| browser-use | 26/26 (100%) | 3.3 | 20,563 | 1,888 | 22,451 | 8,215 | 126 |
| selfbrowse | 25/26 (96%) | 5.7 | 13,759 | 470 | 14,229 | 952 | 53 |

## Totals across all runs

| Library | Runs | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|---|
| browser-use | 26 | 85 | 534,626 | 49,090 | 583,716 |
| selfbrowse | 26 | 149 | 357,730 | 12,233 | 369,963 |

## Only the 13 tasks every library passed (averages per run)

| Library | Model calls | Input tokens | Output tokens | Total tokens | Wall s |
|---|---|---|---|---|---|
| browser-use | 3.3 | 20,563 | 1,888 | 22,451 | 126 |
| selfbrowse | 5.8 | 14,040 | 467 | 14,506 | 54 |

## Per task (successes / runs, average total tokens, model calls)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 8,846 tok · 2.0 calls | 2/2 · 3,535 tok · 3.0 calls |
| T2-search | 2/2 · 15,831 tok · 3.0 calls | 2/2 · 6,408 tok · 5.0 calls |
| T3-navigate | 2/2 · 25,072 tok · 4.5 calls | 2/2 · 7,552 tok · 6.0 calls |
| T4-cart | 2/2 · 21,459 tok · 4.0 calls | 2/2 · 6,814 tok · 5.5 calls |
| T5-login | 2/2 · 15,858 tok · 3.0 calls | 2/2 · 6,104 tok · 5.0 calls |
| T6-paginate | 2/2 · 23,774 tok · 4.0 calls | 1/2 · 8,698 tok · 6.0 calls |
| T7-live-hn (live) | 2/2 · 16,754 tok · 2.0 calls | 2/2 · 4,934 tok · 2.0 calls |
| T8-live-wiki (live) | 2/2 · 31,669 tok · 3.5 calls | 2/2 · 8,614 tok · 4.0 calls |
| U1-github (live) | 2/2 · 21,475 tok · 2.5 calls | 2/2 · 7,066 tok · 3.0 calls |
| U2-pypi (live) | 2/2 · 18,406 tok · 3.0 calls | 2/2 · 8,602 tok · 5.5 calls |
| U3-wikipedia (live) | 2/2 · 29,722 tok · 3.0 calls | 2/2 · 17,854 tok · 7.0 calls |
| U4-books (live) | 2/2 · 42,640 tok · 5.0 calls | 2/2 · 16,082 tok · 6.0 calls |
| U5-pydocs (live) | 2/2 · 20,350 tok · 3.0 calls | 2/2 · 82,719 tok · 16.5 calls |

## How the tokens were counted

| Library | Calls | Calls with no usage reported | Generic-tokenizer estimate of what was sent (not used above) |
|---|---|---|---|
| browser-use | 85 | 0 | 859,967 |
| selfbrowse | 149 | 0 | 399,088 |

The estimate uses one generic tokenizer over each request body, JSON schemas included. A local model reads a response schema as a grammar, not as prompt text, so the estimate overstates libraries that send a large schema. Any call with no usage reported would make the totals too low; the column above should be 0.

## Failures

- rep2 T6-paginate selfbrowse: wrong answer: 'There is no item with SKU ZX-4471 in the parts list; it only contains SKUs ZX-44'
