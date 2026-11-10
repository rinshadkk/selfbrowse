# Contributing

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
pytest            # browser tests need Chromium or Chrome installed
```

The Presidio tests skip themselves unless you also run `pip install -e '.[presidio]'` and `python -m spacy download en_core_web_sm`.

Keep prompts and tool schemas small — they are sent on every step. If you change what the model sees, run `python benchmarks/step_tokens.py` and include the numbers in your PR.

Planned work and priorities live in [ROADMAP.md](ROADMAP.md). Pick an item, say so in an issue, and use its "Done when" line as the acceptance test. A feature that claims to save tokens or raise success needs a benchmark result to back it up.
