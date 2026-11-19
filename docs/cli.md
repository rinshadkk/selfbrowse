# Command line reference

```
selfbrowse [options] "task"
selfbrowse sites                 list sites it has learned
selfbrowse forget <domain>       delete what it learned about a site
selfbrowse trace list            list recorded runs
selfbrowse trace show <id|latest> [--full]   timeline of a run (--full adds prompts)
```

| Option | Meaning |
|---|---|
| `-m`, `--model` | `provider:model` (default `anthropic:claude-haiku-4-5`, or `$SELFBROWSE_MODEL`), or your own model as `module:Name` or `./file.py:Name` (see [Bring your own model](models.md#bring-your-own-model)) |
| `--headed` | show the browser window |
| `--max-steps N` | stop after N tool calls (default 100) |
| `--channel chrome\|msedge` | use an installed browser instead of bundled Chromium |
| `--profile DIR` | keep cookies and logins in this folder between runs |
| `--stealth` | use Patchright to reduce common automation signals |
| `--page-text N` | also send up to N characters of on-screen text with every page list (more tokens, fewer `read` calls) |
| `--max-output-tokens N` | cap on each model reply (default 2048); raise it for reasoning models that think at length |
| `--file PATH` | a local file the agent may upload with the `upload` tool (repeatable). Without it the tool is not offered; the model sees file names, never folders |
| `--vision` | let the model request screenshots (more tokens) |
| `--screenshots DIR` | save a screenshot after every step, plus an `index.html`, in a new folder under `DIR`, as evidence of what the agent did (see [Screenshots as evidence](observability.md#screenshots-as-evidence)) |
| `--record-video DIR` | record a video (WebM) of the browser, one file per page, saved in `DIR` when the run ends; the path is printed as `[video: ...]`. Like screenshots it is not redacted |
| `--cdp-url URL` | attach to a browser that is already running over CDP (a cloud provider's `wss://...`, or `http://localhost:9222`) instead of launching one; also `$SELFBROWSE_CDP_URL`. See [Remote browsers](remote-browsers.md) |
| `--cdp-header NAME=VALUE` | header for the CDP connection, for provider auth (repeatable) |
| `--cloud agentcore` | start a session on Amazon Bedrock AgentCore's managed browser (needs `pip install 'selfbrowse[aws]'` and AWS credentials) |
| `--cloud-region REGION` / `--cloud-browser ID` | AWS region (default `$AWS_REGION`, else `us-east-1`) and browser id (default `aws.browser.v1`) |
| `--permissions LIST` | grant browser permissions to every site, e.g. `notifications,geolocation` (default: none) |
| `--dialogs auto\|accept\|dismiss` | what to do with JavaScript `alert`/`confirm`/`prompt` (default `auto`) |
| `--no-handoff` | never pause for a person (CAPTCHA, login, 2FA) |
| `--trace` | record the run to `~/.selfbrowse/traces/` |
| `--show-prompts` | print every model request to stderr |
| `--trace-hashes` | trace sizes and hashes instead of prompt text |
| `--otel URL` / `--otel-content` | export spans to an OTLP endpoint (needs the `otel` extra) |
| `--allow-domain D` / `--block-domain D` | only visit / never visit these sites (repeatable) |
| `--confirm-risky` | ask before buy, pay, delete, send, sign-out clicks |
| `--redact-pii` | hide emails, phones, SSNs, cards from the model: it sees `<EMAIL_1>`, the real value is typed back for it, and your answer shows the real values (see [Keeping personal data from the model](personal-data.md#placeholders-and-getting-the-values-back)) |
| `--redact-presidio` | also mask names and other personal data with Microsoft Presidio (needs the `presidio` extra; see [Names and other personal data](personal-data.md#names-and-other-personal-data-presidio)) |
| `--presidio-entities LIST` | which Presidio entities to mask, e.g. `PERSON,EMAIL_ADDRESS,LOCATION` |
| `--presidio-model NAME` | spaCy model for Presidio (default `en_core_web_sm`; `en_core_web_lg` finds more names) |
| `--no-restore` | with a redaction flag: mask for good as `[email]`. Nothing keeps the value, the model cannot type it, and the answer stays masked |
| `--watch-injection` | warn on instruction-like page text and confirm risky actions |
| `--max-tokens N` / `--max-seconds S` | stop a run that goes over |
| `--no-learn` | do not read or write site knowledge |
| `--save-flow FILE` | when the run succeeds, save every step to FILE as a [flow](flows.md) |
| `--param NAME=VALUE` | with `flow run`: set a flow parameter (repeatable) |
| `--answer-with-model` | with `flow run -m MODEL`: one model call turns the text the flow read into an answer ([Flows](flows.md#optional-let-a-model-help)) |
| `--repair-with-model` | with `flow run -m MODEL`: if a step cannot find its element, the model finishes the task from that page |
| `--repair-max-steps N` / `--save-repaired FILE` / `--ask TEXT` | cap the repair, keep the repaired flow, or replace the question given to the model |
| `--json` | print the full result as JSON |
| `-q`, `--quiet` | do not print each step |
| `--version` | print the version |

Each step prints with the tokens its model call used, for example `2. done {...}  [901 in / 76 out]`. A step that used saved knowledge ends with `(learned: replayed from saved flow, no model call)` or `(learned: used saved notes about this site)`. The last line gives the totals and the elapsed time: `[2 steps, 2 model calls, 1746 in / 141 out tokens, 24.1s]`.

Environment variables: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `TOGETHER_API_KEY`, `SELFBROWSE_MODEL`, `SELFBROWSE_HOME` (data folder, default `~/.selfbrowse`).
