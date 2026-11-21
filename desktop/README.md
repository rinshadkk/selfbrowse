# Selfbrowse desktop

An Electron app around the `selfbrowse` Python library. It lives in this folder and does not touch the package: the wheel only ships `src/selfbrowse`.

```
Electron window  ->  backend/server.py (FastAPI, 127.0.0.1 + one-time token)  ->  selfbrowse
```

## Run it (development)

Needs Node 20+ and Python 3.10+.

```bash
cd desktop
npm install
npm run backend:setup     # makes backend/.venv, installs selfbrowse from this repo, installs Chromium
export ANTHROPIC_API_KEY=...   # or the key for whichever model you type in
npm start
```

Start it from a terminal that has your API key exported. Keychain-based key storage is a later step.

## Status

The interface from `design/prototype.html` is built:

- **Run**: steps, the live browser, and an inspector for each model call: **Sent to model** (the exact messages, with placeholders and anything that looks personal marked), **Kept private**, and **Usage** (tokens, cache, and a cost if you enter your model's prices). Optional "approve each model call" holds a call until you press Send.
- **My info**: forms of personal details, each field set to *Only me* (the model gets a `<secret:NAME>` placeholder and Selfbrowse types the value), *Model may see*, or *Don't use*. Stored encrypted with the operating system keychain (Electron `safeStorage`). Card numbers are refused.
- **Flows**: save a successful run, replay it with no model, and share it. The share sheet lists everything in the file and replaces personal values it finds (values from My info, emails, phone and card numbers) before you save it.

- **Browser** (next to the model setting): remember logins in a profile folder, use the installed Chrome, and an optional stealth mode (needs `patchright`, not installed by default). "Clear browser data" forgets every login.

Not yet: confirm dialogs for risky actions, importing a flow file, publishing or links, run history, settings, packaging and signing. The prototype's "Ask first" setting and the removed-bar redaction need library changes and are not built.

## Live view

The agent drives its own Chromium (headless by default). The backend mirrors it into the window as JPEG frames (Chrome's screencast) and applies your clicks, scrolls and keys back to the page.

- **Take control** pauses the agent before its next model call, so no tokens are spent while you drive. **Hand back** resumes it.
- When the agent needs you (a bot check, a login, a model request for help) the window shows what it needs and gives you the browser. **I'm done, continue** hands it back.
- **Stop** works during a model call, not only between steps.
- Why a mirror and not an embedded browser view: embedding needs Electron's debugging port, which exposes the whole app (including its own window and the backend token) to any program on the computer, and the agent could see and switch to the app's own tab. The mirror adds no exposure.
- Playwright's synchronous API only delivers frames while its thread is inside a Playwright call, so `backend/live.py` runs the model call in a helper thread and pumps the browser every 50 ms meanwhile.
- Known limits: a little lag, no native scrolling feel or IME, and the frame is a picture of the page, not the browser's own chrome (tabs, address bar).

## Security model

- The backend listens on `127.0.0.1` only, on a random port, and every call needs a one-time token in the `Authorization` header (no token in URLs). Requests whose `Host` is not a loopback name are refused (DNS rebinding), and only the app's own `file://` origin may read responses.
- The window is sandboxed with context isolation, no Node in the page, a strict content security policy, no navigation or pop-ups, and no device permissions. The token is handed only to the app's own page.
- Page text from the sites the agent visits is shown as plain text, never as HTML.
- One run at a time, with bounded prompt length, step count and stored events. Input to the live view is refused unless you have taken control, and every event is validated (known types, bounded coordinates, a restricted key-name pattern, at most 50 per call).
- Runs write no trace files. Nothing is saved to disk by the app itself.
- Known and accepted for now: the agent can be steered by text on a web page (prompt injection), so confirmation for risky actions is the next step; the API key still comes from the shell's environment.
- Before packaging: enable Electron fuses, sign and notarize, and pin the Python dependencies.

- **Detect more personal data (optional).** Turn on the checkbox next to the model to have Microsoft Presidio scan what is sent for names and ID numbers, on this computer. It only flags: pair it with "approve each model call" to act on a flag. Press Install next to the checkbox to download it (about 30 MB, once), or run `backend/.venv/bin/pip install presidio-analyzer` then `backend/.venv/bin/python -m spacy download en_core_web_sm`.

- **Models.** The Model button on the Run screen picks a provider and model, or adds a custom source: any server that speaks the OpenAI chat API (vLLM, LiteLLM, a company gateway), with its own base URL, model name, optional key and a JSON-actions switch. API keys are stored encrypted (`models.bin` in the app's data folder) and sent only to the local backend with a run. Leave a provider's key empty to use its environment variable.

- **Reviewing a flow before it is saved.** Save as flow opens a review sheet: rename it, skip or reorder steps, edit the value a step types, and press “Make this an input” to turn a typed value into an input that is asked for each run (with a label, a default, or “Always ask”). “Make fixed” turns an input back into a plain value. The library checks the result and refuses a flow with a missing input or a bad step, with the reason.

- **Suggest inputs with a model.** In the review sheet, “Suggest inputs with a model” asks the model you chose which typed values should be inputs. It first shows exactly what will be sent (step wording and typed values only, no page contents; anything personal is replaced with `[removed: …]`, and page addresses lose their query strings), and sends only after you press Send. Suggestions are accepted or dismissed one by one. A local model (Ollama) keeps everything on your computer.

- **History.** Each finished run (and flow replay) is summarised under History: the task, outcome, answer or error, steps, time and token counts. “Run again” puts the task back in the Run box. It is stored as small JSON files in the app's data folder (`history/`), the last 500 only. Pages, screenshots and what was sent to the model are not kept, and My info shared with the model is stripped from the task. Turn “Keep a history of runs” off to stop recording, or use Clear history.

- **Passwords and secrets in My info.** “Add password or secret” (and the Website login and Sensitive details templates) make protected fields: masked, kept only on this computer, never offered to the model, and never shown beside a placeholder in the inspector. Showing one needs Touch ID where the Mac has it (a plain confirmation elsewhere), and it covers itself again after 15 seconds or when you leave the tab. Like everything in My info they are encrypted with the system keychain. Card numbers are still refused.

- **Layout.** The Run screen has three states. Idle: a centred prompt box with Model, My info, Browser and ⋯ (personal-data detection, approve each call) pills, and shortcuts to your recent runs and flows. Running: a bar with the task, status and Stop, the steps on the left, the live browser in the middle and the Outbound inspector on the right. Finished: the result with its numbers, Run again, Save as flow, Copy summary, New run (Cmd+N) and a follow-up box that starts a new run with the last result as context.

- **Review before sending.** Under ⋯ (and in the run bar) choose Off, When something looks personal, or Every model call. The run stops before the call, shows exactly what is in it with the personal parts highlighted, and waits: Send as is, Send with these replaced (they go as placeholders like `<EMAIL_1>` from the library's own masking: the real value is typed back for the model on the site where it was seen, or on any site if you wrote it in the task, and your answer shows the real value), or Stop the run. A choice on a piece of text is remembered for the rest of the run, so one email in the task does not stop every call. The setting is remembered and can be changed during a run, which releases a held call if you switch it off. Checks: emails, phones, cards, your My info values, and names too if Presidio is on. Screenshots are not scanned.

  Replacing is reversible only when review was on when the run started (the run then carries the library's vault, about 55 more tokens per call for a note on how to use placeholders). If you switch review on mid-run, a replaced value goes as `[removed: …]` and is not put back. Saved flows turn a typed placeholder into a required input.

  Each flagged item in the banner has a tick: replace it or leave it. Presidio can take a form label (such as “Suff.” on a W-2) for a name and miss part of a real one, so you decide. Items you leave are not asked about again. When something is replaced the model is also told to write the placeholder in its answer, which is swapped for the real value before you read it.

- **Show My info values in the answer.** When the model reports one of your saved values it writes a placeholder such as `<secret:MY_BASIC_INFO_FIRST>`. The switch under ⋯ (on by default, remembered) swaps the real value in on your screen, in the result and in History. It is done at display time only: the stored answer and anything sent to a model keep the placeholder (a follow-up uses the placeholder version), and passwords and other protected fields are never swapped in.
