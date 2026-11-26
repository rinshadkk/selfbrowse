# Tests and benchmarks

## Tests

```bash
python -m pytest -q
```

Browser tests use a local fixture page and need Chromium or Chrome installed. The model is faked, so no API key is needed.

## Benchmarks

Quick check of what is sent on the first step (no key, approximate tokenizer):

```bash
pip install -e '.[bench]'
python benchmarks/step_tokens.py
```

### Comparing with other agents

`benchmarks/compare/` runs the same tasks through each library with the same model and browser, behind a counting proxy so tokens are measured one way for all of them (the model's own reported counts). Success is judged by code (the demo shop's state, or a fact looked up from the site's own API), never by the agent's claim.

```bash
bash benchmarks/compare/run-haiku-baseline.sh   # the baseline below; asks for an Anthropic API key
python benchmarks/compare/run.py --suite usecases --libs selfbrowse,fastbrowse --model qwen3.8-bench   # Fastbrowse needs its own venv and OPENROUTER_API_KEY
python benchmarks/compare/run.py --suite kayak --libs selfbrowse,browser-use --model qwen3.8-bench       # a flight search on Kayak, judged by hand
python benchmarks/compare/learning_eval.py --model qwen3.8-bench                                         # learning on vs off
```

Add `--record-video --terminal` to record each run's browser and terminal side by side. Results, per-run data and versions are in `benchmarks/compare/results/`.

### Baseline: Claude Haiku 5.5

13 tasks (the demo shop and live sites), 2 runs per task, at most 30 steps and 900 seconds per run, the same for both libraries, run on 25 November 2026 against the Anthropic API directly. Selfbrowse is the library source at commit `479ac09`; browser-use is 0.13.14. Both ran headless in the same Chromium, with vision off. Averages per run:

| Library | Passed | Model calls | Input tokens | Output tokens | Total tokens | First call | Seconds |
|---|---|---|---|---|---|---|---|
| Selfbrowse | 26/26 | 5.3 | 18,931 | 589 | **19,520** | 2,306 | 7 |
| browser-use | 26/26 | 4.5 | 64,768 | 1,893 | 66,661 | 17,703 | 14 |

Over all 26 runs: Selfbrowse 507,524 tokens in 139 calls, browser-use 1,733,186 tokens in 117 calls.

**How tokens are counted.** Each figure is what the model reported for each call: the full prompt (cached text included) plus everything it generated, summed over the run. The harness writes one record per call to `calls.jsonl`, so every total can be checked by adding them up. No call in this run was missing its usage.

The results are in `benchmarks/compare/results/haiku5.5-baseline/`: `runs.jsonl`, `calls.jsonl`, `meta.json` and `summary.md`.

### Per task

Average total tokens over 2 runs, and passes. The ratio is browser-use tokens divided by Selfbrowse tokens.

| Task | Selfbrowse | browser-use | Ratio |
|---|---|---|---|
| T1 read text | 7,845 (2/2) | 19,238 (2/2) | 2.5 |
| T2 search | 14,050 (2/2) | 51,779 (2/2) | 3.7 |
| T3 navigate | 16,276 (2/2) | 50,820 (2/2) | 3.1 |
| T4 cart | 19,680 (2/2) | 74,804 (2/2) | 3.8 |
| T5 login | 16,926 (2/2) | 35,191 (2/2) | 2.1 |
| T6 paginate | 20,650 (2/2) | 102,132 (2/2) | 4.9 |
| T7 live: Hacker News | 7,869 (2/2) | 26,216 (2/2) | 3.3 |
| T8 live: Wikipedia fact | 15,384 (2/2) | 71,206 (2/2) | 4.6 |
| U1 live: GitHub | 49,732 (2/2) | 63,204 (2/2) | 1.3 |
| U2 live: PyPI | 27,180 (2/2) | 38,377 (2/2) | 1.4 |
| U3 live: Wikipedia | 14,770 (2/2) | 96,964 (2/2) | 6.6 |
| U4 live: books | 28,153 (2/2) | 151,892 (2/2) | 5.4 |
| U5 live: Python docs | 15,248 (2/2) | 84,770 (2/2) | 5.6 |

### How much to trust the numbers

- **Small sample.** One model and 2 runs per task. A single odd run moves a row, and the live sites change over time.
- **Tokens are not cost.** The totals include text served from the prompt cache (about 60% of Selfbrowse's input and 75% of browser-use's), which is billed at a lower rate.
- **Both passed everything here**, so this run says nothing about which is more reliable. In earlier runs with other models, Selfbrowse sometimes answered "not found" on a paginated list without opening every page (task T6).
- **Selfbrowse makes more calls** and sends much less in each one. It was slower on one task, U1.
- **Default settings.** browser-use ran as installed. Selfbrowse ran with learning and hand-off off, so runs are independent.

### Earlier runs

Runs made before this baseline, with other models and harness versions, are kept on the [`benchmark-archive` branch](https://github.com/rinshadkk/selfbrowse/tree/benchmark-archive/benchmarks/compare/results). Many of them estimated the tokens sent instead of using the model's counts, so they are not comparable with the figures above.

## Showcase

Three read-only tasks you can run yourself. Nothing is bought, booked or sent. Add `--headed` to watch the browser, and `--record-video ./demo` to keep a recording (see [Screenshots as evidence](observability.md#screenshots-as-evidence)).

**A flight search with a preference.** Google Flights hides the search behind an autocomplete form, which is why many agents struggle with it.

```bash
selfbrowse --model anthropic:claude-haiku-5-5 --headed \
  "Find the cheapest price for tickets from COK to SFO on Dec 26th for 4 people. Prefer shortest layover"
```

**A lookup on a live page.**

```bash
selfbrowse --model anthropic:claude-haiku-5-5 \
  "Go to github.com/trending and tell me the top repository today, what it does, its star count and its main language."
```

**A comparison across pages.** The category has two pages and the agent has to check both.

```bash
selfbrowse --model anthropic:claude-haiku-5-5 \
  "On books.toscrape.com, open the 'Mystery' category and tell me the title and price of the cheapest book. The category has more than one page, so check them all."
```

Three runs of each on Claude Haiku 5.5, headless, with learning off so the runs are independent. Cost is the token counts priced at the list price of $0.10 per million input tokens, $0.50 per million output tokens and $0.01 per million cached input tokens.

| Task | Answered | Steps per run | Tokens sent | Time | Cost per run |
|---|---|---|---|---|---|
| Flight COK to SFO, 4 people | 3 of 3 | 33, 39, 7 | 18k to 229k | 30 to 175 s | $0.004 to $0.033 |
| GitHub trending, top repo | 3 of 3 | 3, 3, 2 | about 6.7k | 14 to 15 s | about $0.001 |
| Cheapest Mystery book | 3 of 3 | 7, 7, 7 | about 22k | 26 to 30 s | about $0.004 |

What came back:

- **Flight:** the cheapest fare was $4,715 for 4 adults, one way, on Qatar Airways and Alaska with 2 stops (via DOH and LAX, 26 h 49 min), in all three runs. Each run also named a pricier 1-stop Emirates flight at $5,979 as the better choice for a short layover (1 h 45 min in Dubai in the last two runs; the first run's saved text is cut off before the layover). The last run also noted that the shortest layover overall was Singapore Airlines at 1 h, for $10,737, and that layover lengths for 2-stop options are not shown on the results page. Prices change daily, and I did not check these against Google Flights by hand, so look at the page before relying on them.
- **GitHub trending:** `dream-num/univer` in all three runs, which is what the page listed when the runs were judged.
- **Books:** "Tastes Like Fear (DI Marnie Rome #3)" at £10.69, after checking both pages (32 books).

The flight search is the one to expect variation on. Two runs took more than 30 steps and one took 7, for the same prompt and model, so its cost varied by a factor of nine. The other two tasks were steady. In an earlier set of five runs of a similar flight prompt (COK to ORD), the same model finished in 5 to 8 steps each time. Five runs of one prompt are not enough to promise that, so treat the step count as a range.

The runs, with the answers and token counts, are in [`showcase-haiku5.5`](https://github.com/rinshadkk/selfbrowse/tree/benchmark-archive/benchmarks/compare/results/showcase-haiku5.5) on the `benchmark-archive` branch. The browser recordings are not kept in git; `python benchmarks/compare/run.py --suite showcase --libs selfbrowse --record-video --terminal` makes them (needs `asciinema`, `agg` and `ffmpeg` for the terminal view).
