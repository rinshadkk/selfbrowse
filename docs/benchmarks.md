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

`benchmarks/compare/` runs the same tasks through each library with the same model and browser, behind a counting proxy so tokens are measured one way for all of them. Success is judged by code (the demo shop's state, or a fact looked up from the site's own API), never by the agent's claim.

```bash
python benchmarks/compare/run.py --suite usecases --libs selfbrowse,browser-use --model qwen3.8-bench --reps 1
python benchmarks/compare/run.py --suite usecases --libs selfbrowse,fastbrowse --model qwen3.8-bench   # Fastbrowse needs its own venv and OPENROUTER_API_KEY
python benchmarks/compare/run.py --suite kayak --libs selfbrowse,browser-use --model qwen3.8-bench       # a flight search on Kayak, judged by hand
python benchmarks/compare/learning_eval.py --model qwen3.8-bench                                         # learning on vs off
```

Add `--record-video --terminal` to record each run's browser and terminal side by side. Results, per-run data and versions are in `benchmarks/compare/results/`.

| Run | Success | Model calls | Tokens sent (avg) | Seconds (avg) |
|---|---|---|---|---|
| qwen3.8, 13 tasks (demo shop and real sites): Selfbrowse | 12/13 | 5.7 | 11,810 | 54 |
| qwen3.8, 13 tasks: browser-use 0.13.14 | 12/13 | 3.4 | 34,613 | 167 |
| qwen3.8, 6 real sites: Selfbrowse | 6/6 | 5.0 | 66,195 | 84 |
| qwen3.8, 6 real sites: Fastbrowse 0.10.0 | 4/6 | 5.0 | 160,574 | 171 |
| Claude Sonnet 5.5, 6 real sites: Selfbrowse | 5/6 | 7.2 | 22,474 | 22 |
| Claude Sonnet 5.5, 6 real sites: browser-use | 6/6 | 2.8 | 27,311 | 22 |

Read these with care:

- One run per task, so a single flaky result moves a row. These are small samples, not a ranking.
- Selfbrowse makes more model calls per task than browser-use but sends far fewer tokens per call (its page list is short), which is where the token and time difference comes from.
- With Fastbrowse, a hosted decision model chooses each action and its tokens are not counted here; only its language-model part (start page, field values, answer) ran on qwen3.8, with reasoning switched off. Fastbrowse used an installed Google Chrome and the others used Playwright's Chromium.
- The local model's results depend on the model and settings in `benchmarks/compare/Modelfile.*`.

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

The runs are in `benchmarks/compare/results/showcase-haiku5.5/` with the answers and token counts. The browser recordings are not kept in git; `python benchmarks/compare/run.py --suite showcase --libs selfbrowse --record-video --terminal` makes them (needs `asciinema`, `agg` and `ffmpeg` for the terminal view).
