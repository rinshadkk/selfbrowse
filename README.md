# Selfbrowse

A small browser agent that gets cheaper the more you use it.

Selfbrowse reads a page as a short numbered list of what you can click or type into, instead of screenshots or raw HTML, and learns each site as it goes: flows that worked twice are replayed without calling the model.

```bash
pip install selfbrowse
playwright install chromium
export ANTHROPIC_API_KEY=...
selfbrowse "open news.ycombinator.com and tell me the top story"
```

```python
from selfbrowse import Agent

result = Agent("find the top story on Hacker News", llm="anthropic:claude-haiku-4-5").run()
print(result.output, result.usage)
```

## Models

`provider:model` — `anthropic`, `openai`, `ollama` (local, free), `lmstudio`, `groq`, `deepseek`, `gemini`, `openrouter`, `together`.

## Passwords

Pass secrets with `sensitive={"pw": "..."}`; the model writes `<secret:pw>` and Selfbrowse substitutes it only at typing time, so the real value never reaches the model.

## Learned sites

Stored under `~/.selfbrowse/sites/`. `selfbrowse sites` lists them, `selfbrowse forget <domain>` deletes one.

## Status

Early (0.1). Token-saving claims are measured, not assumed: see `benchmarks/`.

MIT licensed.
