# Examples

Each file runs on its own. Most need a model key (`ANTHROPIC_API_KEY`), or a local model for 02.
`12`, `13` and `14` need no key; `14` needs the `presidio` extra.

| File | Shows |
|---|---|
| `quickstart.py` | The smallest possible run |
| `01_models.py` | Switching providers: Anthropic, OpenAI, Groq, Gemini, Ollama, LM Studio |
| `02_local_model.py` | Local and "thinking" models: native tool mode, output cap, more steps |
| `03_secrets.py` | Signing in without the model seeing the password |
| `04_guardrails.py` | Domain limits, risky-click approval, PII masking (`RedactPII`), injection watch, budgets |
| `05_custom_guardrail.py` | Writing your own guardrail |
| `06_handoff.py` | Handing the browser to a person (CAPTCHA, 2FA, approvals) with a custom handler |
| `07_real_chrome_and_stealth.py` | Real Chrome, saved profile, Patchright, to cut bot blocks |
| `08_tracing.py` | Traces, prompt visibility, redaction, OpenTelemetry |
| `09_learning.py` | Site learning and inspecting what was learned |
| `10_shopping_safely.py` | A checkout-style task with approvals, budget and enough steps |
| `11_progress_and_results.py` | Step callbacks, usage, and the result object |
| `12_browser_only.py` | The browser layer on its own: snapshot, find, dropdowns, tabs |
| `13_offline_no_key.py` | The full loop with a scripted model on a local page |
| `14_presidio_names.py` | Masking names and other personal data with Microsoft Presidio (needs the `presidio` extra) |

The same options exist on the command line; see the main README.
