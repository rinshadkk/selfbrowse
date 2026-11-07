# Contributing

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
pytest            # browser tests need Chromium or Chrome installed
```

Keep prompts and tool schemas small — they are sent on every step. If you change what the model sees, run `python benchmarks/step_tokens.py` and include the numbers in your PR.
