# Selfbrowse

A small browser agent. You describe a task in plain language; it drives a real browser to do it.

Instead of screenshots or raw HTML, the model reads each page as a short numbered list of what can be clicked or typed into, and Selfbrowse remembers what worked on each site so repeat visits need fewer model calls.

> **Status: early (0.1), not yet on PyPI.** Install from source (below). Cost and speed claims are not yet benchmarked against other tools; see [Benchmarks](#benchmarks).

## Install

```bash
git clone <your-repo-url> selfbrowse && cd selfbrowse
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium        # or use your installed Chrome with --channel chrome
```

Optional extras: `pip install -e '.[stealth]'` (Patchright), `pip install -e '.[otel]'` (OpenTelemetry export), `pip install -e '.[bench]'` (token benchmark).

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
from selfbrowse import Agent

result = Agent("find the top story on Hacker News", llm="anthropic:claude-haiku-4-5").run()
print(result.output)
print(result.usage)        # input/output/cache tokens and number of model calls
```

`result` has `success`, `output`, `steps`, `usage`, `history` and `error`.

## Command line reference

```
selfbrowse [options] "task"
selfbrowse sites                 list sites it has learned
selfbrowse forget <domain>       delete what it learned about a site
selfbrowse trace list            list recorded runs
selfbrowse trace show <id|latest> [--full]   timeline of a run (--full adds prompts)
```

| Option | Meaning |
|---|---|
| `-m`, `--model` | `provider:model` (default `anthropic:claude-haiku-4-5`, or `$SELFBROWSE_MODEL`) |
| `--headed` | show the browser window |
| `--max-steps N` | stop after N tool calls (default 25) |
| `--channel chrome\|msedge` | use an installed browser instead of bundled Chromium |
| `--profile DIR` | keep cookies and logins in this folder between runs |
| `--stealth` | use Patchright to reduce common automation signals |
| `--vision` | let the model request screenshots (more tokens) |
| `--no-handoff` | never pause for a person (CAPTCHA, login, 2FA) |
| `--trace` | record the run to `~/.selfbrowse/traces/` |
| `--show-prompts` | print every model request to stderr |
| `--trace-hashes` | trace sizes and hashes instead of prompt text |
| `--otel URL` / `--otel-content` | export spans to an OTLP endpoint (needs the `otel` extra) |
| `--no-learn` | do not read or write site knowledge |
| `--json` | print the full result as JSON |
| `-q`, `--quiet` | do not print each step |
| `--version` | print the version |

Environment variables: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `TOGETHER_API_KEY`, `SELFBROWSE_MODEL`, `SELFBROWSE_HOME` (data folder, default `~/.selfbrowse`).

## Models

Use `provider:model`:

| Provider | Example |
|---|---|
| `anthropic` | `anthropic:claude-haiku-4-5` (prompt caching on) |
| `openai` | `openai:gpt-4o-mini` |
| `ollama` | `ollama:qwen3.6:latest` (local; the model must support tool calling) |
| `lmstudio` | `lmstudio:<model>` |
| `groq`, `deepseek`, `gemini`, `openrouter`, `together` | `groq:llama-3.3-70b-versatile` |

Any object with a `complete(...)` method works too; see `selfbrowse/llm/base.py`.

## Seeing what is sent to the model

```bash
selfbrowse --show-prompts "task"     # prints every model request live (stderr)
selfbrowse --trace "task"            # also saves the run to ~/.selfbrowse/traces/<run-id>.jsonl
selfbrowse trace list
selfbrowse trace show latest         # timeline: model calls, tokens, actions
selfbrowse trace show latest --full  # include the full prompts
```

A trace is one JSON line per event: `run_start`, `llm_request` (the exact system text, tool names and messages sent, with token estimates per part), `llm_response` (usage, timing, the model's reply), `tool_call`, `tool_result`, `replay`, `handoff`, `run_end`.

- Secrets passed with `sensitive=` never appear: the model only sees `<secret:NAME>`.
- Prompts include page text, which may hold personal data. `--trace-hashes` (Python: `trace_content=False`) stores sizes and hashes only, and `redact_trace=fn` scrubs every string before it is written. Task text, typed text, tool results, reasons and URLs are covered too.
- Tracing never breaks a run: a failing sink or unwritable folder is ignored.

From Python:

```python
agent = Agent("task", trace=True, on_llm_request=lambda system, messages, tools, n: print(n, len(messages)))
agent.run()
print(agent.trace_path)
```

### OpenTelemetry

`pip install -e '.[otel]'`, then point it at any OTLP/HTTP receiver, including one on your own machine (Jaeger, Grafana Tempo, Arize Phoenix on `http://localhost:4318`):

```bash
selfbrowse --otel http://localhost:4318 "task"
```

Each run becomes a `selfbrowse.run` span with child spans per model call (`gen_ai.*` attributes, token usage) and per tool call; hand-offs are span events. Spans carry sizes and timings only; add `--otel-content` to attach the task and prompt text. Spans go only where you point them.

## Passwords and secrets

Pass secrets to the agent, not to the model:

```python
Agent("log in and open my orders", sensitive={"pw": "hunter2"})
```

The model writes `<secret:pw>`; Selfbrowse substitutes the real value only when typing. The value never appears in prompts, results or step history.

## Sites that show a CAPTCHA (Walmart, Target and similar)

Large retailers run bot detection that scores each visit before showing the page. The default setup (bundled headless Chromium, fresh profile, no history) looks like automation and often gets a challenge. A tool attached to your everyday Chrome passes more often because it has your cookies, history and a normal browser fingerprint.

Try these in order:

1. Your installed Chrome, visible, with a saved profile:

```bash
selfbrowse --headed --channel chrome --profile ~/.selfbrowse/profile "open walmart.com and tell me the heading"
```

2. If it is still blocked, add the stealth option (`pip install -e '.[stealth]'`):

```bash
selfbrowse --headed --channel chrome --profile ~/.selfbrowse/profile --stealth "open walmart.com and tell me the heading"
```

3. Browse to the site once yourself in that same profile window, so it has real cookies and history.

Selfbrowse does not solve or defeat CAPTCHAs. Instead it hands the browser to you (next section). Also check each site's terms of service before automating shopping or scraping at scale.

## Handing off to a person

When the agent cannot go further, it pauses and lets you act in the visible browser window, then continues from wherever you leave the page. It happens when:

- **a bot check appears** (CAPTCHA, "verify you are human", "press and hold", Cloudflare "Just a moment"). Detected automatically; the model is not called while the page is blocked.
- **the model asks**: for a login with no stored secret, a 2FA code, a payment step or a choice only you can make, it calls `ask_human`.

```bash
selfbrowse --headed --profile ~/.selfbrowse/profile "open target.com and tell me the heading"
```

When it needs you, the terminal shows a box with the reason and URL and rings the bell. Do the step in the browser window, then press **Enter** in the terminal to continue (type `q` + Enter to give up). Using `--profile` keeps the cookies from a solved check for later runs.

- Without `--headed` there is nobody to hand off to, so the run stops at once with a clear error ("blocked: ... re-run with --headed") instead of wasting model calls.
- Nothing you type or see is sent to the model; it is only told you finished.
- It gives up after 3 hand-offs in one run, or if the page is still blocked after you resume.
- `--no-handoff` turns this off.

From Python, use the built-in terminal prompt or plug in your own (a desktop notification, a Slack message, a web UI):

```python
from selfbrowse import Agent, Browser

def ask_person(request):                  # request.kind: "challenge" or "model"
    print(request.reason, request.url)    # notify however you like
    input("Press Enter when done: ")
    return True                           # False = give up

Agent("task", browser=Browser(headless=False), handoff=ask_person).run()
```

`handoff="auto"` (default) uses the terminal prompt when the window is visible; `handoff=False` disables it.

## How learning works

Knowledge is stored per site in `~/.selfbrowse/sites/<domain>.json`.

- **Memo**: short facts the model chose to save with the `remember` tool.
- **Flows**: click sequences that worked, keyed by page type (for example `/*/dp/*`). A flow is replayed without a model call only when it is trusted:
  - **generic**: it succeeded for at least two *different* tasks (a cookie banner, a sign-in step), so it is replayed for every task;
  - **repeat**: it succeeded at least twice for the *exact same* task, so it is replayed for that task only.
- Only successful runs are learned from. Steps after typing on a page are never recorded for that page. Risky clicks (buy, pay, delete, send, sign out and similar) are never recorded. Failed actions and detours (clicks followed by going back) are not learned. A flow that stops working is dropped, and flows unused for 90 days expire.

Known limit: research-style tasks learn little, because most of their clicks are specific to the question. The biggest wins are generic steps and routine jobs you repeat.

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

## Renaming

The name lives in `src/selfbrowse/_about.py`, the package folder, `pyproject.toml` and the docs.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed.
