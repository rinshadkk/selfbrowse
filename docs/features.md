# Features

Each feature below is off unless you ask for it, apart from the core reading and learning.

## Doing the task

| Feature | What it does | Details |
|---|---|---|
| Numbered page list | The model sees each page as a short list of controls (`#1 button "Add to cart"`), not a screenshot | [What the agent can do](tools.md) |
| Learning per site | Remembers click sequences that worked and replays them without a model call | [What the agent can do](tools.md#how-learning-works) |
| Any model | Anthropic, OpenAI, Ollama and other OpenAI-compatible servers, including local models | [Models](models.md) |
| Hand-off to a person | Pauses for a CAPTCHA, login or 2-step code, then carries on | [CAPTCHAs and hand-off](captcha-handoff.md) |
| Pop-ups and permissions | Sees JavaScript dialogs; browser permissions such as notifications are granted only when you say so | [Pop-ups and permissions](popups-permissions.md) |

## Keeping things safe

| Feature | What it does | Details |
|---|---|---|
| Domain limits | `--allow-domain` and `--block-domain` keep a run on the sites you chose | [Guardrails](guardrails.md) |
| Risky-click approval | Asks before buy, pay, delete, send and sign-out clicks; blocks them when nobody can answer | [Guardrails](guardrails.md) |
| Injection watch | Flags page text that tries to give the agent orders | [Guardrails](guardrails.md) |
| Budgets | Stops a run past a token or time limit | [Guardrails](guardrails.md) |
| Personal data hidden from the model | Emails, phones, cards and (with Presidio) names become `<EMAIL_1>`-style placeholders; the real value is typed back on the same site | [Personal data](personal-data.md) |
| Secrets | Passwords are given by name and filled in at the keyboard; the model never sees them | [Passwords and secrets](secrets.md) |

## Seeing what happened

| Feature | What it does | Details |
|---|---|---|
| Traces | A timeline of every model call and tool call, with token counts | [Traces, prompts and screenshots](observability.md) |
| Prompt view | Print each request sent to the model | [Traces, prompts and screenshots](observability.md) |
| OpenTelemetry | Export runs to Jaeger, Grafana Tempo or Phoenix | [Traces, prompts and screenshots](observability.md#opentelemetry) |
| Screenshots as evidence | A picture after every step, with an `index.html` | [Traces, prompts and screenshots](observability.md#screenshots-as-evidence) |

## Using it from other tools

| Feature | What it does | Details |
|---|---|---|
| MCP server | `selfbrowse-mcp` gives Claude, VS Code and other MCP clients a browser, as one task tool or step by step | [MCP server](mcp.md) |
| Python API | `BrowseAgent(...)`, custom guardrails, step callbacks | [Get started](getting-started.md#python) |
