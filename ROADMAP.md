# Selfbrowse roadmap

A living list of what to build next. Add features at the bottom of the right section, give them the next free ID, and move them up or down by changing the priority, not by reordering the file.

## How to use this file

- **Status:** `[ ]` todo · `[~]` in progress · `[x]` done (add the commit or version) · `[-]` dropped (say why).
- **Priority:** **P0** do first, unblocks everything · **P1** next release · **P2** soon · **P3** nice to have.
- **Done when:** a test or observable result. If you cannot write one, the item is not ready.
- **Proves it:** the benchmark or measurement that should move. A feature that claims to help must show it (see O-section). No benchmark, no claim in the README.
- **Adding an item:** copy the template at the end, take the next ID in the section (e.g. `A19`), and put a one-line reason ("why").

## Now (P0, in this order)

1. **O1** Commit the benchmark harness and the results collected so far.
2. **R1** Decide the default tool mode (native vs JSON) from the finished model results.
3. **R2** Refuse `done` as the very first action.
4. **L1** Measure whether site learning helps at all.
5. **P1/P5** Trademark search and employer-IP check before any public release.

---

## A. Capabilities (what the agent can do and see)

- [x] **A1 Dropdown select** (P1) — `select` tool for native `<select>` (custom dropdowns are A17). *Done when:* a fixture form with a select is filled correctly by a scripted run. *Proves it:* new benchmark task "fill a form". *Done: `select` tool, options shown in the page list; tests in `tests/test_browser_tools.py`. Not yet measured on a benchmark task.*
- [ ] **A2 File upload** (P2) — attach a local file to a file input; guarded by `ConfirmRisky`-style approval. *Done when:* fixture upload page receives the file.
- [x] **A3 Tabs and popups** (P1) — list, switch to and close tabs; handle `window.open`. Today the agent silently follows the newest tab. *Done when:* a fixture that opens a link in a new tab can be completed and returned from. *Done: `[tabs: …]` line, `switch_tab`, `close_tab`; closing a popup returns to its opener.*
- [ ] **A4 Drag and drop** (P3) — `drag(from_ref, to_ref)`.
- [ ] **A5 Hover and key chords** (P3) — expose `hover` (already in `Browser`) and modifier keys.
- [ ] **A6 Downloads** (P2) — detect, save to a safe folder, report the path; require confirmation.
- [x] **A7 Iframes** (P1) — include elements inside same-origin and cross-origin iframes in the page list and click them. Today only the top document is read. *Done when:* a fixture with a login form inside an iframe is completed. *Done: same-origin and cross-origin frames in the list, click/type/read/find work. Limit: nested frames beyond 8 are skipped; an overlay covering a frame is not detected.*
- [x] **A8 Shadow DOM** (P1) — pierce open shadow roots in the snapshot. *Done when:* a fixture built from web components is completed. *Done for open shadow roots (snapshot, read, find, overlay check). Closed roots are invisible to page scripts and stay unsupported.*
- [x] **A9 Page text in the state** (P1) — optional compact visible text next to the element list, so facts do not need a separate `read` call. Trade-off: more tokens. *Proves it:* T1, T6, T8; compare success and tokens with and without. *Done as an option: `Agent(page_text=N)` / `--page-text N`, off by default. Still to do: compare T1, T6, T8 with and without it.*
- [ ] **A10 Working vision** (P1) — `--vision` is currently a stub that returns "unavailable". Send a screenshot to Anthropic, OpenAI and Ollama vision models. *Done when:* a canvas-only fixture page can be read.
- [ ] **A11 Scrolling containers and infinite scroll** (P2) — scroll inside a scrollable div; detect new content loaded.
- [ ] **A12 Structured output** (P1) — `Agent(..., output_schema=PydanticModel | JSON schema)`, returns validated data in `result.data`. *Done when:* a task returns a list of products with typed fields.
- [ ] **A13 Custom tools** (P2) — let users register their own actions (a function plus a schema).
- [ ] **A14 Multi-action turns** (P2) — optionally accept several actions per model reply to cut calls on long forms. *Proves it:* calls per task on form tasks.
- [ ] **A15 Run JavaScript** (P3) — opt-in only, behind a guardrail.
- [ ] **A16 Visual click fallback** (P3) — click by coordinates from a screenshot when no element is listed. Depends on A10.
- [ ] **A17 Combobox and autocomplete widgets** (P2) — type, wait for suggestions, pick one.
- [ ] **A18 Date pickers** (P3).

## R. Agent reliability (the loop itself)

- [ ] **R1 Default tool mode** (P0) — currently JSON-schema mode is the default for Ollama and LM Studio. Llama results said native tool calling plus the error fixes is better. *Done when:* the default matches the finished results for Llama, qwen3.6 and muse-glimmer, and the README says why.
- [ ] **R2 Refuse an immediate `done`** (P0) — in JSON mode the model could say "added" without doing anything (T4). Require at least one real action, or a `read`, before `done` is accepted. *Proves it:* T4 and T2 with Llama.
- [ ] **R3 Validate the answer field** (P1) — reject answers like "done with success=true" that contain no answer. *Proves it:* T3 with Llama (native).
- [ ] **R4 Retry and backoff for model errors** (P1) — rate limits, timeouts and 5xx currently end the run. *Done when:* a fake model that fails twice then works completes the task.
- [ ] **R5 Optional reflection field** (P2) — a short "what happened / what next" per step for weak models (browser-use requires one). Measure the token cost against the success gain.
- [ ] **R6 Stall recovery** (P1) — beyond the current "repeated 3 times" warning: go back, reload, or try another path. *Proves it:* T6 and T8.
- [ ] **R7 Stale-click protection** (P2) — confirm the element is still under the target point before clicking; fall back to its role and text.
- [ ] **R8 Smarter waiting** (P1) — wait for DOM and network to settle instead of fixed sleeps. *Proves it:* wall time per step and flaky-click rate.
- [~] **R9 Find on page** (P1) — a `find(text)` tool that scrolls to a match, and a `read` that can page through long text. *Proves it:* T6 (paginated list) and T8 (Wikipedia). *Partly done: `find(text, nth)` works across shadow roots and frames. Still to do: a `read` that pages through long text, and the T6/T8 comparison.*
- [ ] **R10 Conversation compaction** (P2) — shrink old turns on long runs.
- [ ] **R11 Model profiles** (P3) — prompt and mode presets per model strength.
- [ ] **R12 Generic popup handling** (P2) — dismiss cookie banners and modals by pattern before asking the model.

## L. Learning (per-site memory)

- [ ] **L1 Measure it** (P0) — run a task sequence with learning on and off in the benchmark and compare calls, tokens, time and success. *Done when:* a table in the README shows the result, good or bad.
- [ ] **L2 Keep only useful steps** (P1) — record only clicks on the path to the final success, not exploration. Today incidental clicks ("History", "(Top)") get saved.
- [ ] **L3 Self-healing flows** (P2) — verify a flow still works, repair or drop it when the site changes.
- [ ] **L4 Export and import knowledge** (P3) — share site notes between machines, opt-in.
- [ ] **L5 Seed packs** (P3) — shipped generic knowledge (cookie banners on common platforms).
- [ ] **L6 Make `remember` useful** (P2) — models rarely call it. Test automatic fact extraction at the end of a successful run.

## S. Safety and security

- [ ] **S1 Per-domain secrets** (P1) — a secret can only be typed on the domains it is bound to (browser-use does this).
- [ ] **S2 Secrets everywhere** (P2) — also allow secrets in URLs and headers, not only typed text.
- [ ] **S3 Sandboxed browser** (P2) — optional container or separate OS user, no access to the host profile.
- [ ] **S4 Stronger injection defense** (P2) — tag text by origin, treat page text as data in every message, require approval for new actions after untrusted content.
- [ ] **S5 Politeness** (P2) — per-domain rate limits and an optional robots.txt check.
- [ ] **S6 Better risk detection** (P1) — look at form submits and typed purchase confirmations, not only button labels. *Proves it:* a fixture where "Buy" is an icon with no text.
- [ ] **S7 Terms-of-service guidance** (P3) — document what is and is not appropriate to automate.
- [ ] **S8 Pluggable sensitive-data detection** (P1) — turn `RedactPII` (regex only today) into a list of detectors: rules (regex with checksums, secrets scanner, user dictionary), Presidio, GLiNER with custom labels, and an optional local-LLM pass for ambiguous text. *Why:* regexes miss names, addresses and context-dependent data, and a person needs a way to define "sensitive" for their own data.
  - **Reversible placeholders:** replace values with stable tokens like `<EMAIL_1>`, keep the mapping in memory only, and swap the real value back when the model types the token into a form.
  - **Optional and light by default:** heavy parts live in extras (`selfbrowse[pii]`, `selfbrowse[pii-ner]`), imported lazily. Plain `--redact-pii` stays on the cheap rules layer; `--redact-pii=presidio|ner` and `--redact-pii-llm MODEL` add layers. A missing extra stops with an install hint instead of silently running without it.
  - **Python API:** `RedactPII(detectors=[Rules(), Presidio(), GLiNER(labels=[...])])`; a custom detector is anything with `find(text) -> list[Span]`.
  - **Limits and scope:** a per-page time budget (about 200 ms) that falls back to the faster layers and logs it in the trace; per-domain scope; cover traces, screenshots and site knowledge, not only page text.
  *Done when:* each layer can be turned on or off, a fixture page with seeded sensitive values is masked end to end, and a form field can still be filled from a placeholder. *Proves it:* a leak benchmark that reports recall, false positives (masked values that broke the task) and added latency per layer, in a table in the README. Cost figures (size, memory, latency) are estimates until measured.

## D. Distribution and integration

- [ ] **D1 MCP server mode** (P1) — expose Selfbrowse as an MCP server so Claude, IDEs and other agents can use it.
- [ ] **D2 Publish to PyPI** (P0, blocked on P1) — only after the name is cleared.
- [ ] **D3 Async API and streaming** (P1) — `await agent.arun()` and an event stream for UIs.
- [ ] **D4 Attach to a running Chrome** (P1) — connect over CDP to the user's own browser (fixes most bot-check problems because it uses real cookies and fingerprint).
- [ ] **D5 Remote browsers** (P2) — connect to a hosted browser by CDP URL.
- [ ] **D6 Docker image and HTTP API** (P2).
- [ ] **D7 LangChain and LlamaIndex wrappers** (P3).
- [ ] **D8 TypeScript client** (P3).
- [ ] **D9 CI on macOS, Linux and Windows** (P1) — browser tests and a lint step. Windows is untested (the terminal prompt uses `select` on stdin).
- [ ] **D10 Release workflow** (P2) — tagged releases, changelog.

## O. Observability and evaluation

- [ ] **O1 Commit the benchmark harness and results** (P0) — `benchmarks/compare/` plus the result folders. Record versions, model aliases and settings.
- [ ] **O2 Harder tasks** (P1) — real-site tasks and a subset of a public benchmark (WebVoyager or Mind2Web style). The current six tasks use a toy store.
- [ ] **O3 Fair browser-use comparison** (P1) — rerun with its recommended settings for each model, longer timeouts for slow models, and several runs.
- [ ] **O4 More models** (P1) — gpt-oss 20B, Qwen3-Coder 30B, Devstral 24B, Gemma 4 E4B, a 3–4B model, plus Claude Haiku/Sonnet. Same settings alias for each.
- [ ] **O5 Confidence in the summary** (P1) — multiple runs, a confidence interval, and a note when the sample is too small to compare.
- [ ] **O6 Cost accounting** (P2) — configurable price table per model, shown in the summary.
- [ ] **O7 HTML trace viewer** (P2) — one file you can open to see a run.
- [ ] **O8 Regression tracking** (P2) — keep results over time and flag drops.
- [ ] **O9 Fast CI smoke benchmark** (P2) — a scripted fake model, no network.

## P. Project and release

- [ ] **P1 Name and trademark** (P0) — USPTO search in classes 9 and 42, then register PyPI, GitHub and the domain. Selfbrowse is a descriptive name and weak to protect.
- [ ] **P2 Docs and examples** (P2) — a task gallery, a guide for each guardrail, a "choose a model" page.
- [ ] **P3 Community files** (P2) — issue templates, code of conduct, PR template.
- [ ] **P4 SECURITY.md** (P2) — how to report issues; what the tool does and does not protect.
- [ ] **P5 Employer IP check** (P0) — confirm the project can be released from your account before publishing.
- [ ] **P6 Split `agent.py`** (P2) — it now mixes the loop, guardrail glue, hand-off and repair logic.

---

## Known limitations (not features, but should not be forgotten)

- `--vision` is not implemented (A10).
- `read` returns at most about 3,000 characters of visible text.
- The agent follows the newest tab without telling the model (A3).
- Confirmations block instead of asking when running headless.
- One `Agent` instance should not run two tasks at once.
- Live-site tasks (T7, T8) are noisy: the page changes and sites may challenge headless browsers.
- Benchmarks so far: one toy store, six local tasks, one or two runs each.

## Decisions waiting on data

| Question | Waiting on | Linked |
|---|---|---|
| Native or JSON tool mode as the Ollama default? | muse-glimmer results | R1 |
| Is learning worth keeping on by default? | the learning experiment | L1 |
| Is the 8B model even a supported target? | more small-model runs | O4 |

## Item template

```
- [ ] **X0 Short title** (P2) — what it is, in one line. *Why:* the problem it solves.
  *Done when:* the concrete test or result. *Proves it:* the benchmark or metric that should move.
```
