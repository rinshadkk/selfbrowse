# Tests and benchmarks

## Tests

```bash
python -m pytest -q
```

Browser tests use a local fixture page and need Chromium or Chrome installed. The model is faked, so no API key is needed.

## Benchmarks

```bash
pip install -e '.[bench]'
python benchmarks/step_tokens.py
```

This prints what is sent to the model on the first step for four real pages (system prompt, tool schemas, page list). It uses an approximate tokenizer and needs no key. It does not compare against other tools yet.
