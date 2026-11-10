# Get started

## Install

```bash
git clone <your-repo-url> selfbrowse && cd selfbrowse
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium        # or use your installed Chrome with --channel chrome
```

Optional extras: `pip install -e '.[stealth]'` (Patchright), `pip install -e '.[otel]'` (OpenTelemetry export), `pip install -e '.[mcp]'` (MCP server), `pip install -e '.[presidio]'` (name and personal-data masking; also run `python -m spacy download en_core_web_sm`), `pip install -e '.[bench]'` (token benchmark).

## Quick start

With Claude (set your key in your own shell; never paste it into a chat or commit it):

```bash
export ANTHROPIC_API_KEY=your-key-here
selfbrowse "Open news.ycombinator.com and tell me the title of the top story."
```

With a local, free model through Ollama (no key):

```bash
selfbrowse -m ollama:qwen3.6:latest "Open news.ycombinator.com and tell me the title of the top story."
```

Watch it work in a visible window:

```bash
selfbrowse --headed "Open news.ycombinator.com and tell me the title of the top story."
```

Each step prints as it runs. The last lines are the answer and a token summary.

If you cannot see the output, save it to a file and open that:

```bash
selfbrowse "your task" > result.txt 2>&1
```

## Python

```python
from selfbrowse import BrowseAgent

result = BrowseAgent("find the top story on Hacker News", llm="anthropic:claude-haiku-4-5").run()
print(result.output)
print(result.usage)        # input/output/cache tokens and number of model calls
```

`result` has `success`, `output`, `steps`, `usage`, `history` and `error`.

Fourteen runnable examples (local models, secrets, guardrails, name masking, hand-off, real Chrome, tracing, learning, and two that need no key) are in [examples/](https://github.com/rinshadkk/selfbrowse/blob/main/examples/README.md).
