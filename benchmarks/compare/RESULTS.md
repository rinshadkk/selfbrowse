# Selfbrowse against browser-use: pooled results

Every valid run made with the same settings, pooled per model. Rebuild the numbers with `python benchmarks/compare/pool.py`.

## Method

- **Tasks:** 13 (a demo shop, plus live sites), judged by code from the site's state or its own API, never by the agent's claim.
- **Settings, identical for both libraries:** at most 30 steps and 900 seconds per run, one browser, one logging proxy. Selfbrowse ran with learning and hand-off off. browser-use 0.13.14 ran with default settings.
- **Tokens:** what the model itself reported for each call, input plus output (reasoning included), summed over the run. Calls with no usage reported: 0 in every run used here. Per-call records are in each folder's `calls.jsonl`.
- **Pooling:** each task is averaged over its runs first, then the 13 task averages are averaged, so a task with more runs does not count for more. The range is a bootstrap over runs (2,000 resamples).

| Model | Runs pooled | Folders |
|---|---|---|
| qwen3.8, local (Ollama, MLX) | 29 per library | `qwen3.8-baseline`, `qwen3.8-u5-rerun` |
| Claude Sonnet 5.5, through a local Claude Code gateway | 65 per library | `sonnet5.5-all`, `sonnet5.5-all-run2`, `sonnet5.5-u5`, `sonnet5.5-t6x10` |

## Overall (average per task)

| Model | Library | Passed | Model calls | Input | Output | **Total tokens** | First call | Seconds |
|---|---|---|---|---|---|---|---|---|
| qwen3.8 | Selfbrowse | 28/29 | 5.6 | 12,491 | 442 | **12,933** | 952 | 50 |
| | browser-use | 29/29 | 3.3 | 20,562 | 1,891 | 22,453 | 8,215 | 126 |
| Sonnet 5.5 | Selfbrowse | 63/65 | 4.6 | 25,933 | 683 | **26,616** | 3,808 | 16 |
| | browser-use | 64/65 | 3.3 | 89,866 | 1,881 | 91,747 | 37,034 | 22 |

**browser-use used 1.7 times as many tokens on qwen3.8 (range 1.5 to 2.0) and 3.4 times as many on Sonnet 5.5 (range 3.3 to 3.6).**

## Per task

Average total tokens per run, and passes. The ratio is browser-use tokens divided by Selfbrowse tokens.

| Task | qwen3.8 Selfbrowse | qwen3.8 browser-use | Ratio | Sonnet 5.5 Selfbrowse | Sonnet 5.5 browser-use | Ratio |
|---|---|---|---|---|---|---|
| T1 read text | 3,535 (2/2) | 8,846 (2/2) | 2.5 | 17,059 (4/4) | 32,956 (4/4) | 1.9 |
| T2 search | 6,408 (2/2) | 15,831 (2/2) | 2.5 | 26,474 (4/4) | 71,567 (4/4) | 2.7 |
| T3 navigate | 7,552 (2/2) | 25,072 (2/2) | 3.3 | 29,764 (4/4) | 101,240 (4/4) | 3.4 |
| T4 cart | 6,814 (2/2) | 21,459 (2/2) | 3.1 | 35,864 (4/4) | 113,296 (4/4) | 3.2 |
| T5 login | 6,104 (2/2) | 15,858 (2/2) | 2.6 | 18,279 (4/4) | 67,323 (4/4) | 3.7 |
| T6 paginate | 8,698 (**1/2**) | 23,774 (2/2) | 2.7 | 55,822 (**12/14**) | 146,924 (13/14) | 2.6 |
| T7 Hacker News | 4,934 (2/2) | 16,754 (2/2) | 3.4 | 14,676 (4/4) | 53,803 (4/4) | 3.7 |
| T8 Wikipedia fact | 8,614 (2/2) | 31,669 (2/2) | 3.7 | 18,781 (4/4) | 99,083 (4/4) | 5.3 |
| U1 GitHub | 7,066 (2/2) | 21,475 (2/2) | 3.0 | 20,896 (4/4) | 96,387 (4/4) | 4.6 |
| U2 PyPI | 8,602 (2/2) | 18,406 (2/2) | 2.1 | 30,126 (4/4) | 82,749 (4/4) | 2.7 |
| U3 Wikipedia | 17,854 (2/2) | 29,722 (2/2) | 1.7 | 18,783 (4/4) | 120,970 (4/4) | 6.4 |
| U4 books | 16,082 (2/2) | 42,640 (2/2) | 2.7 | 36,306 (4/4) | 118,257 (4/4) | 3.3 |
| U5 Python docs | 65,871 (5/5) | 20,384 (5/5) | **0.3** | 23,176 (7/7) | 88,154 (7/7) | 3.8 |

- Selfbrowse used fewer tokens on 13 of 13 tasks with Sonnet 5.5 and on 12 of 13 with qwen3.8. It was also faster on 13 of 13 with Sonnet 5.5 and 12 of 13 with qwen3.8.
- **U5 on qwen3.8 is the one loss.** The model re-searched one long page 9 or more times, so each call carried the whole page. Sonnet 5.5 did not.

## Reliability

- **One task accounts for every Selfbrowse miss: T6.** In both pooled sets the agent read some pages of a 4-page list, guessed what the others held, and answered "not found" without opening page 3. Selfbrowse missed 1 of 2 on qwen3.8 and 2 of 14 on Sonnet 5.5. browser-use missed 1 of 14 on Sonnet 5.5.
- On Sonnet 5.5 the same task passed 10 of 10 when run alone, and missed on rep 1 in both full-suite runs. The cause is not known.
- The same miss appears in earlier result folders (`after-store-sonnet`, `gateway-claude-sonnet-5-5`), so it is not new.

## What these numbers do not show

- **The Sonnet 5.5 runs went through a local Claude Code gateway, not the Anthropic API.** A wrapper can add text to every call, so quote the ratio, not the totals. A generic-tokenizer estimate of the same runs gives a similar ratio (3.1 on the first run, against 3.8 reported), so the comparison holds, but cost per task needs a direct-API run.
- **Two models, one machine, 13 tasks.** Seven tasks use live sites, so they depend on those sites staying the same.
- **Not included:** Claude Opus 5.5. Selfbrowse passed the 8 tasks it reached, but every browser-use call timed out after 90 seconds, so there is no valid comparison (`opus5.5-all`, partial). Earlier Haiku, muse-glimmer and Fastbrowse runs used an estimate of tokens and are kept only in `docs/benchmarks.md`.
- **Selfbrowse used more calls but fewer tokens**, so total cost depends on how a provider prices input, output and cached tokens.
