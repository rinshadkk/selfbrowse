# Keeping personal data from the model

Two layers: a fast pattern-based one built in, and an optional name-aware one using Microsoft Presidio. Both hide values behind placeholders the agent can still use.

## Placeholders and getting the values back

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

## Names and other personal data (Presidio)

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
