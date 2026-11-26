# Archived benchmark runs

This branch keeps the benchmark runs made before the current baseline. They are kept for reference and are not the
figures to quote. The baseline and the current numbers are on the main line, in `docs/benchmarks.md`.

- Many of these used an estimate of tokens sent, not the model's own counts.
- Runs with `sonnet5.5` or `gateway` in the name went through a local gateway that adds text to every call.
- `opus5.5-all` is incomplete: every browser-use call timed out.
- `../RESULTS.md` pools the later qwen3.8 and Sonnet 5.5 runs; `../pool.py` rebuilds those numbers.
