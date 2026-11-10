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
| `--max-steps N` | stop after N tool calls (default 100) |
| `--channel chrome\|msedge` | use an installed browser instead of bundled Chromium |
| `--profile DIR` | keep cookies and logins in this folder between runs |
| `--stealth` | use Patchright to reduce common automation signals |
| `--page-text N` | also send up to N characters of on-screen text with every page list (more tokens, fewer `read` calls) |
| `--max-output-tokens N` | cap on each model reply (default 2048); raise it for reasoning models that think at length |
| `--vision` | let the model request screenshots (more tokens) |
| `--screenshots DIR` | save a screenshot after every step, plus an `index.html`, in a new folder under `DIR`, as evidence of what the agent did (see [Screenshots as evidence](#screenshots-as-evidence)) |
| `--permissions LIST` | grant browser permissions to every site, e.g. `notifications,geolocation` (default: none) |
| `--dialogs auto\|accept\|dismiss` | what to do with JavaScript `alert`/`confirm`/`prompt` (default `auto`) |
| `--no-handoff` | never pause for a person (CAPTCHA, login, 2FA) |
| `--trace` | record the run to `~/.selfbrowse/traces/` |
| `--show-prompts` | print every model request to stderr |
| `--trace-hashes` | trace sizes and hashes instead of prompt text |
| `--otel URL` / `--otel-content` | export spans to an OTLP endpoint (needs the `otel` extra) |
| `--allow-domain D` / `--block-domain D` | only visit / never visit these sites (repeatable) |
| `--confirm-risky` | ask before buy, pay, delete, send, sign-out clicks |
| `--redact-pii` | hide emails, phones, SSNs, cards from the model: it sees `<EMAIL_1>`, the real value is typed back for it, and your answer shows the real values (see [Keeping personal data from the model](#keeping-personal-data-from-the-model)) |
| `--redact-presidio` | also mask names and other personal data with Microsoft Presidio (needs the `presidio` extra; see [Names and other personal data](#names-and-other-personal-data-presidio)) |
| `--presidio-entities LIST` | which Presidio entities to mask, e.g. `PERSON,EMAIL_ADDRESS,LOCATION` |
| `--presidio-model NAME` | spaCy model for Presidio (default `en_core_web_sm`; `en_core_web_lg` finds more names) |
| `--no-restore` | with a redaction flag: mask for good as `[email]`. Nothing keeps the value, the model cannot type it, and the answer stays masked |
| `--watch-injection` | warn on instruction-like page text and confirm risky actions |
| `--max-tokens N` / `--max-seconds S` | stop a run that goes over |
| `--no-learn` | do not read or write site knowledge |
| `--json` | print the full result as JSON |
| `-q`, `--quiet` | do not print each step |
| `--version` | print the version |

Environment variables: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `TOGETHER_API_KEY`, `SELFBROWSE_MODEL`, `SELFBROWSE_HOME` (data folder, default `~/.selfbrowse`).

## What the agent can do

`goto`, `click`, `type`, `select` (native dropdowns), `press`, `scroll`, `back`, `wait`, `read` (text on screen), `find` (jump to a word on a long page), `switch_tab`, `close_tab`, `remember`, `ask_human` and `done`.

- **Dropdowns:** a native `<select>` is listed with its current value and options, and `select` picks one by its text or value.
- **Frames and web components:** controls inside iframes (same-origin and cross-origin) and open shadow roots appear in the same numbered list and are clicked the same way.
- **Tabs:** when a link or popup opens a new tab the agent follows it, and the page list starts with `[tabs: 1 "Shop" · 2 "Details" (current)]` so the model knows. Not supported yet: closed shadow roots, drag and drop, file uploads, custom (non-`<select>`) dropdowns beyond clicking them. See [ROADMAP.md](https://github.com/rinshadkk/selfbrowse/blob/main/ROADMAP.md).

Each tool schema is sent on every model call, so tools are kept few and short (about 790 tokens for all of them on a typical step).

## Use it from Claude, VS Code and other MCP clients

Selfbrowse can run as an [MCP](https://modelcontextprotocol.io) server, so an assistant can use it as its browser:

```bash
pip install 'selfbrowse[mcp]'
playwright install chromium
```

It offers two kinds of tools:

- **`browse(task)`** (task mode). Selfbrowse runs its own model loop and returns only the answer, so the assistant never reads the pages. This is where most of the token saving is. It needs `--model`, for example `ollama:qwen3.6` (free, local) or `anthropic:claude-haiku-4-5`.
- **`browser_snapshot`, `browser_click`, `browser_type`, `browser_select`, `browser_goto`, `browser_read`, `browser_find`, `browser_scroll`, `browser_press`, `browser_back`, `browser_switch_tab`, `browser_close_tab`** (step mode). The assistant drives the browser and reads Selfbrowse's short numbered list instead of a screenshot. No model is needed on the server. We have not measured how this compares with other browser tools.

**VS Code** (Copilot agent mode): add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "selfbrowse": {
      "command": "selfbrowse-mcp",
      "args": ["--model", "ollama:qwen3.6", "--headed", "--channel", "chrome", "--allow-domain", "example.com"]
    }
  }
}
```

**Claude Code:** `claude mcp add selfbrowse -- selfbrowse-mcp --model ollama:qwen3.6 --headed`

**Claude Desktop** (`claude_desktop_config.json`): `{"mcpServers": {"selfbrowse": {"command": "selfbrowse-mcp", "args": ["--model", "ollama:qwen3.6"]}}}`

Client config formats change between versions, so check your client's MCP docs if one of these is rejected.

Things to know:

- **Guardrails apply.** Use `--allow-domain`, `--block-domain`, `--block-risky`, `--redact-pii`, `--redact-presidio` (with `--presidio-entities` and `--presidio-model`), `--watch-injection`, `--max-tokens` and `--max-seconds`. There is nobody to ask in a terminal, so a risky click is refused, not confirmed; your client's own tool-approval prompt is a second check.
- **No terminal hand-off.** Stdout carries the protocol. When a CAPTCHA or login needs a person, the tool result says so; start the server with `--headed` so there is a window to finish it in.
- **Secrets:** set `SELFBROWSE_SECRET_<name>` in the server's environment; the assistant writes `<secret:name>` and never sees the value.
- **One browser per server.** Task mode and step mode share it, so a `browse` run starts from the page your step tools left open.
- Only `mcp` 2.x was tested. Selfbrowse also tries the 1.x import, but that path is untested.

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
selfbrowse trace show latest         # timeline: model calls, tokens, actions, guardrail decisions
selfbrowse trace show latest --full  # include the full prompts
```

A trace is one JSON line per event: `run_start`, `llm_request` (the exact system text, tool names and messages sent, with token estimates per part), `llm_response` (usage, timing, the model's reply), `tool_call`, `tool_result`, `replay`, `guardrail`, `handoff`, `run_end`.

- Secrets passed with `sensitive=` never appear: the model only sees `<secret:NAME>`.
- Prompts include page text, which may hold personal data. `--trace-hashes` (Python: `trace_content=False`) stores sizes and hashes only, and `redact_trace=fn` scrubs every string before it is written. Task text, typed text, tool results, reasons and URLs are covered too.
- Tracing never breaks a run: a failing sink or unwritable folder is ignored.

From Python:

```python
agent = BrowseAgent("task", trace=True, on_llm_request=lambda system, messages, tools, n: print(n, len(messages)))
agent.run()
print(agent.trace_path)
```

### OpenTelemetry

`pip install -e '.[otel]'`, then point it at any OTLP/HTTP receiver, including one on your own machine (Jaeger, Grafana Tempo, Arize Phoenix on `http://localhost:4318`):

```bash
selfbrowse --otel http://localhost:4318 "task"
```

Each run becomes a `selfbrowse.run` span with child spans per model call (`gen_ai.*` attributes, token usage) and per tool call; guardrail decisions and hand-offs are span events. Spans carry sizes and timings only. Add `--otel-content` to attach what the model was sent and what it answered: each `chat` span gets `gen_ai.system_instructions`, `gen_ai.input.messages` and `gen_ai.output.messages` (OpenTelemetry GenAI conventions, still experimental). LLM viewers such as Phoenix, Langfuse and Opik show these as a conversation; Jaeger shows them as JSON strings under the span's Tags. Long text is shortened part by part so the JSON stays valid. These attributes contain page text, so only send them to a backend you trust. Spans go only where you point them.

### Screenshots as evidence

To keep proof of what the agent saw and did, save a picture after every step:

```bash
selfbrowse --screenshots ./evidence "Add the cheapest USB-C cable to the cart on example.com"
# [screenshots: evidence/run-20261110-093015]
```

Each run gets its own folder with `step-01.jpg`, `step-02.jpg` and so on, and an `index.html` that lists every step (tool, arguments, URL, result) next to its picture. Python: `BrowseAgent("task", screenshots="./evidence")`, then `agent.screenshots_dir`; each `Step` has a `.screenshot` file name, and a trace records a `screenshot` event per image.

- **The picture shows the page after the step ran**, including the last page when the agent calls `done`.
- **The model never gets these images.** This is separate from `--vision`, which sends pictures to the model and costs tokens.
- **They are not redacted.** A screenshot shows the page as it really is: names, emails and anything the agent typed, even a password that is hidden everywhere else. The folder is created private to your user (mode 700). Do not share or commit it without looking, and avoid `--screenshots` on pages with data you would not want stored.
- **A picture that cannot be taken** (the page just closed, or a pop-up is blocking capture) leaves a gap, marked in `index.html`; the run carries on.
- The MCP server does not save screenshots.

## Guardrails

Rules between the model and the browser. Pass them as a list:

```python
from selfbrowse import BrowseAgent
from selfbrowse.guardrails import AllowedDomains, ConfirmRisky, RedactPII, PresidioRedact, InjectionWatch, Budget

BrowseAgent(
    "task",
    guardrails=[
        AllowedDomains(["example.com"]),      # also allows subdomains
        ConfirmRisky(),                       # asks before Buy / Pay / Delete / Send / Sign out
        RedactPII(),                          # hides emails, phones, SSNs, cards behind <EMAIL_1>-style placeholders
        PresidioRedact(),                     # optional: also names, via Microsoft Presidio (needs selfbrowse[presidio])
        InjectionWatch(),                     # warns on "ignore previous instructions"-style page text
        Budget(max_tokens=50_000, max_seconds=300),
    ],
).run()
```

| Guardrail | What it does |
|---|---|
| `SafeUrls` | http(s) pages only; blocks `file:`, `chrome:`, `data:`, `javascript:`. **Always on** unless `safe_urls=False` |
| `AllowedDomains([...])` | only these sites (judged on the real hostname, so `https://good.com@evil.com` is evil.com). Also undoes a click that lands elsewhere, and refuses a start page outside the list |
| `BlockedDomains([...])` | never these sites |
| `ConfirmRisky()` | asks a person before a click whose label looks irreversible; with nobody to ask (headless) it blocks instead |
| `RedactPII(kinds=..., restore=True)` | hides emails, phone numbers, US SSNs and Luhn-valid card numbers behind placeholders like `<EMAIL_1>`; the real value is typed back on the same site. Names and addresses are not detected. `restore=False` masks for good as `[email]` |
| `PresidioRedact(entities=, threshold=, model=)` | optional. Uses Microsoft Presidio and a spaCy model to mask names as well as emails, phones, cards, SSNs, IBANs, passports and similar. Runs locally. Install with `pip install 'selfbrowse[presidio]'`; see [Names and other personal data](#names-and-other-personal-data-presidio) |
| `InjectionWatch()` | flags instruction-like page text, tells the model to treat it as data, and requires confirmation before navigating, typing or risky clicks from that page |
| `Budget(max_tokens=, max_seconds=, max_usd=, price=(in, out))` | stops a run that goes over; `max_usd` needs the per-million-token prices you pay, and counts cached input at full price, so it is a ceiling |

Confirmations use the same prompt as a hand-off (`--headed`, press Enter to approve or `n` to deny). From Python, your `handoff=` function receives `request.kind == "confirm"`; return `True` to allow the action.

Your own rule is a small class; override only the hooks you need:

```python
from selfbrowse.guardrails import Guardrail, Block

class NoSocial(Guardrail):
    def check_url(self, url):                      # also: on_page, before_action, after_step
        if "facebook.com" in url:
            return Block("social sites are off limits")
```

### Names and other personal data (Presidio)

`RedactPII` is regex-only: it cannot see names or addresses. For those, turn on [Microsoft Presidio](https://microsoft.github.io/presidio/), which uses a small language model to find personal data in page text. It runs on your machine; nothing is sent to Microsoft or anyone else. It is optional, so the default install stays small.

```bash
pip install 'selfbrowse[presidio]'
python -m spacy download en_core_web_sm        # one-time model download (about 12 MB)

selfbrowse --redact-presidio "Open my account page and tell me the order status"
```

If either piece is missing, Selfbrowse stops before the run and prints the command to fix it. It never downloads a model by itself.

Choose what to mask with Presidio's entity names, and trade speed for accuracy with a bigger model:

```bash
selfbrowse --redact-presidio --presidio-entities PERSON,EMAIL_ADDRESS,LOCATION "task"
selfbrowse --redact-presidio --presidio-model en_core_web_lg "task"      # several hundred MB, slower, finds more names
```

```python
from selfbrowse.guardrails import PresidioRedact

PresidioRedact()                                   # defaults below
PresidioRedact(["PERSON", "LOCATION"])             # only these
PresidioRedact(threshold=0.7)                      # fewer false positives, more misses
PresidioRedact(model="en_core_web_lg")
PresidioRedact(analyzer=my_analyzer_engine)        # your own AnalyzerEngine: custom recognizers, other languages
```

- **Default entities:** `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `IBAN_CODE`, `US_PASSPORT`, `US_DRIVER_LICENSE`, `US_BANK_NUMBER`, `MEDICAL_LICENSE`, `CRYPTO`. `LOCATION` and `DATE_TIME` are off because page text is full of both; `IP_ADDRESS` is off because it would mask the address of a local page in the URL line. Add any of them by naming them. [All Presidio entity names](https://microsoft.github.io/presidio/supported_entities/).
- **What the model sees:** a placeholder in place of the value: `Hello <PERSON_1>, your email is <EMAIL_1>` (with `--no-restore`, a label: `[person]`, `[email]`). The model cannot read a hidden value, so a task like "find the contact email" needs `EMAIL_ADDRESS` left out of the list.
- **Use it with `--redact-pii` or alone.** Both can be on; the regex layer runs first, then Presidio.
- **Accuracy:** statistical name detection has false positives (a product called "Max Pro" may be masked) and misses, more so with the small model and on short fragments. It lowers exposure; it does not prove nothing leaked. Measure it on your own pages before relying on it.
- **Cost:** `en_core_web_sm` loads once per run (about 0.8 s on one laptop). After that a short page takes a few milliseconds and about 9,000 characters of page text took about 0.2 s. Those figures come from one machine and one synthetic page, so treat them as a rough guide, and `en_core_web_lg` will be slower.
- **Scope:** it masks the page text sent to the model. It does not scrub traces, screenshots (`--vision`) or text you type; use `redact_trace=` for traces and avoid `--vision` with sensitive pages.
- **MCP server:** `selfbrowse-mcp` takes the same `--redact-presidio`, `--presidio-entities` and `--presidio-model` flags and loads the model once at start-up.

### Keeping personal data from the model

Hiding a value has a cost: the model cannot use what it cannot see. With `[email]` on the page it cannot fill a form with that email. So `--redact-pii` and `--redact-presidio` do not just delete the value. Page text gets stable placeholders, `<EMAIL_1>`, `<PERSON_1>`, `<CARD_1>`. The model is told it can type a placeholder, and Selfbrowse swaps in the real value at the keyboard. This is the default; `--no-restore` turns it off.

```bash
pip install 'selfbrowse[presidio]'
selfbrowse --redact-pii --redact-presidio --allow-domain example.com \
  "On my account page, subscribe the email address on file to the newsletter"
```

What the model sees and does: `Email on file: <EMAIL_1>` ... `type #2 "<EMAIL_1>"`. What the page receives: `priya.raman@acme.com`.

```python
from selfbrowse.guardrails import RedactPII, PresidioRedact
BrowseAgent("...", guardrails=[RedactPII(), PresidioRedact()])      # placeholders, restored on typing and in your answer
BrowseAgent("...", guardrails=[RedactPII(restore=False)])             # mask for good: [email]
BrowseAgent("...", guardrails=[RedactPII()], restore_answer=False)    # keep the answer masked, e.g. if you forward it to a model or a log
```

- **The same value always gets the same token**, across pages and across both masking guardrails, so the model can tell two people apart.
- **Only `type` (and `find`) restore values.** `goto`, `select`, `click` and the traces only ever carry placeholders. Learned site flows never store typed text, so no placeholder can be replayed into a later run with a different meaning.
- **Same site only.** Each placeholder remembers which sites it was seen on and is refused anywhere else (`www.` and port are ignored). A page that tricks the model into typing `<EMAIL_1>` into a form on another site gets the placeholder back, not your email. The model is told why.
- **Echoes are masked too.** After the real value is typed, the page often shows it back (a text box now holding the name). Selfbrowse masks every value it already knows wherever it appears, even where the detector would not have recognised it.
- **Your answer shows the real values.** The model writes `Confirmation sent to <EMAIL_1>` and you get the real address. The recorded steps and traces keep the placeholders. If you pass the answer on to another model or a log, use `restore_answer=False` in Python. Over MCP the answer goes to the calling assistant, so it is never restored there.
- **It needs the model to copy the placeholder exactly.** Brackets are optional (`EMAIL_1` works) and `EMAIL_1` never matches `EMAIL_10`, but a model that rewrites a token into words (`the email`) cannot be restored. See the check below.
- **MCP server:** `selfbrowse-mcp --redact-pii` uses placeholders too; `browser_type` fills in the real value on the same site. `--no-restore` masks for good.
- **When to use `--no-restore`:** when your rule is that the value must not exist anywhere in the process. By default a mapping from placeholder to real value sits in memory for the length of the run (never on disk, in prompts or in traces). With `--no-restore` the value is discarded the moment the page is masked.
- **It does not remove the need to trust the page.** A value the detector missed was shown to the model in plain text. Combine this with `--allow-domain`.

**Checked against local qwen3.6** (`benchmarks/reversible/run.py`, 5 trials per mode, a profile page with a name and an email and a form that asks for both):

| | Form filled with the real values | Real value seen by the model | Model calls (median) | Tokens (median) | Time per run |
|---|---|---|---|---|---|
| placeholders (default) | 5 of 5 | 0 of 5 | 6 | 8,287 | 25 to 39 s (one run took 9 calls) |
| `--no-restore` (masked as `[email]`) | 0 of 5 | 0 of 5 | 10 | 21,676 | 187 to 225 s |

With `--no-restore` the model typed the literal text `[email]` into the form every time and still reported success, so the page received nothing useful and the model did not notice. This is one local model, one page and five trials, so read it as a working demonstration, not a rate. Raw rows are in `benchmarks/reversible/qwen3.6-result.json`; rerun with `python benchmarks/reversible/run.py --model ollama:qwen3.6-bench --trials 5`.


Learned-flow replays obey the same rules and never ask anyone: if a guardrail objects, the replay stops and the model takes over.

**These reduce risk; they are not guarantees.** Pattern matching (PII, injection) misses things. The domain allow-list, confirm-risky and budgets are the dependable ones. A hosted model still sees whatever page text you do not redact; only a local model keeps page content on your machine.

## Passwords and secrets

Never put a password in the task text. The task goes to the model; a secret should not. Give the secret to Selfbrowse instead, under a name. The model is told only the name (`<secret:NAME>`), writes that placeholder when it types, and Selfbrowse swaps in the real value at the keyboard. The value never appears in the prompt, the page list, the result, the step history or traces.

**Command line.** A full example, logging in to a site and reading something behind the login:

```bash
# 1. Put the secrets in your shell. `read -s` keeps the password out of your history.
export SELFBROWSE_SECRET_user='me@example.com'
read -s "SELFBROWSE_SECRET_pw?Password: " && export SELFBROWSE_SECRET_pw     # zsh
# bash:  read -s -p "Password: " SELFBROWSE_SECRET_pw && export SELFBROWSE_SECRET_pw

# 2. Run the task. Say which site to use, and lock the run to it.
selfbrowse --headed --allow-domain example.com \
  "Go to example.com/login, sign in with <secret:user> and <secret:pw>, then tell me my latest order number"
```

The name after `SELFBROWSE_SECRET_` is the name the model uses: `SELFBROWSE_SECRET_pw` becomes `<secret:pw>`. Every `SELFBROWSE_SECRET_*` variable is made available, and the model is told the names even if your task does not mention them.

For one command only, set the variable in front of it (the value is still visible in your history, so use this for throwaway values):

```bash
SELFBROWSE_SECRET_pw='throwaway' selfbrowse "log in to the staging site and open settings"
```

Or keep them in a file outside the project and load it when you need it:

```bash
# ~/.selfbrowse-secrets  (chmod 600; never commit it)
export SELFBROWSE_SECRET_user='me@example.com'
export SELFBROWSE_SECRET_pw='your-password'
```
```bash
source ~/.selfbrowse-secrets && selfbrowse "sign in to example.com and open my orders"
```

To be asked for a value each time, so it is never stored in your environment, name it with `--secret`:

```bash
selfbrowse --secret pw "Sign in to example.com as me@example.com with <secret:pw> and tell me my latest order number"
# Value for secret 'pw' (not shown):
```

Selfbrowse has no `--secret NAME=value` form on purpose: a value on the command line shows up in `ps` and your history.

**Python.**

```python
import os
BrowseAgent("log in and open my orders", sensitive={"user": "me@example.com", "pw": os.environ["SITE_PW"]})
```

**MCP server.** Set the same `SELFBROWSE_SECRET_<name>` variables in the server's environment (the `env` block of your client config). With `browser_type`, the calling assistant passes `<secret:pw>` as the text.

Tips:

- Name the field in your task ("log in with <secret:user> and <secret:pw>") if the site has more than one form.
- Use `--profile DIR` to log in once and keep the session, so later runs need no secret.
- For 2FA codes, CAPTCHAs and one-off values you do not want stored, let the model call `ask_human`; you type it in the browser window.
- Secrets hide what the model sees from the agent's side. They do not stop a page from showing your own details back (an account name, an email address). Add `--redact-pii` (or `--redact-presidio` for names too) for that.
- Pair secrets with `--allow-domain`, so a credential can only be typed on the site you meant.

## Pop-ups, notifications and permissions

**New tabs and windows** (`target=_blank`, OAuth login windows) are followed. The page list shows `[tabs: ...]` and the agent can `switch_tab` and `close_tab`.

**Overlays a site draws itself** (cookie banners, "Allow notifications?" cards, newsletter modals) are ordinary page elements, so the agent sees them in the list and clicks "No thanks" or "Accept".

**Browser permissions** (notifications, location, camera, microphone, clipboard) are off by default, so a site that asks is refused and nothing pops up. To allow some for every site you visit:

```bash
selfbrowse --permissions notifications,geolocation "Open weather.example.com and tell me today's forecast for my area"
```

```python
from selfbrowse import BrowseAgent, Browser

BrowseAgent("...", browser=Browser(permissions=["geolocation"]))
```

Names: `geolocation`, `notifications`, `camera`, `microphone`, `clipboard-read`, `clipboard-write`, `midi`, `midi-sysex`, `payment-handler`, `background-sync`, `accelerometer`, `gyroscope`, `magnetometer`, `ambient-light-sensor`, `accessibility-events`, `storage-access`. A misspelt name stops the run with the list. Grant the fewest you need, and combine with `--allow-domain` so only the site you meant gets them. The MCP server takes the same `--permissions` flag.

**JavaScript dialogs** (`alert`, `confirm`, `prompt`, "Leave site?") are shown to the model. After an action that raises one, the result says what it was and what happened, for example `[A confirm dialog appeared: "Delete everything?". It was dismissed.]`.

| `--dialogs` | `alert` / leave-page | `confirm` / `prompt` |
|---|---|---|
| `auto` (default) | accepted | dismissed (counts as Cancel) |
| `accept` | accepted | accepted |
| `dismiss` | dismissed | dismissed |

With `accept`, guardrails still apply: `--confirm-risky` asks a person before accepting a dialog about deleting, paying or sending, and the MCP server (where nobody can be asked) dismisses it. A dialog the model cannot answer in advance is declined, so if a task needs one accepted, run with `--dialogs accept`.

**Not visible to the agent:** the browser's own prompts that are drawn outside the page ("Save password?", file pickers, print dialogs). In `--headed` mode a person can click them. Permissions above cover the common ones.

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
from selfbrowse import BrowseAgent, Browser

def ask_person(request):                  # request.kind: "challenge" or "model"
    print(request.reason, request.url)    # notify however you like
    input("Press Enter when done: ")
    return True                           # False = give up

BrowseAgent("task", browser=Browser(headless=False), handoff=ask_person).run()
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

See [CONTRIBUTING.md](https://github.com/rinshadkk/selfbrowse/blob/main/CONTRIBUTING.md). MIT licensed.
