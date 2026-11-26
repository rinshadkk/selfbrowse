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

## Build a distributable (macOS, Apple Silicon, unsigned)

    cd desktop
    npm install
    backend/.venv/bin/pip install pyinstaller      # once
    npm run dist                                   # dist/Selfbrowse-0.1.0-arm64.dmg

`npm run dist` freezes the Python backend with PyInstaller (`scripts/freeze-backend.sh`) and packs it with Electron using
electron-builder (the `build` section of `package.json`). The packaged app starts the frozen backend from its own `Resources/backend`
folder, so it needs no Python.

- **Unsigned.** macOS will warn on first launch. Open it with right-click > Open, or run `xattr -dr com.apple.quarantine /Applications/Selfbrowse.app`.
  Signing and notarizing need a Developer ID Application certificate; set `mac.identity` and the notarization settings in `package.json` when you have one.
- **Needs Google Chrome.** The packaged app drives the Chrome installed on the computer. It does not bundle a browser.
- **Left out:** Patchright stealth mode (it says "Not included in this build"). Presidio is not inside the app but can be added from it, see below.
- Apple Silicon only. An Intel build needs the backend frozen on an Intel Mac.

### The Presidio add-on

Presidio (names and ID numbers in page text) needs spaCy and a language model, and the packaged app has no pip. So it ships as a
separate program that the app downloads when someone presses **Install** next to "Detect more personal data" (the ⋯ menu on the Run screen).

- **What they see:** a sheet naming the file, its size and where it comes from, with Download and Cancel. Nothing is fetched before that yes.
  Afterwards it shows progress, then "Installed", and a **Remove** button deletes it to get the space back. Cancel works while downloading.
- **How it stays safe:** `backend/addon_manifest.json` (inside the app) pins the address, size and SHA-256 of the file. The app installs nothing
  if the download differs, refuses files that would unpack outside their folder, and starts the program once to check it finds an email
  address before it says "Installed". The program listens on `127.0.0.1` only, with a token the backend creates for each start, and quits after
  ten idle minutes or when the app quits. Page text never leaves the computer. Address, size and checksum are all you ever download.
- **Where it lives:** `<app data>/addons/presidio/`. About 95 MB unpacked, 50 MB downloaded.
- **Publishing it** (once per Presidio or model change, by whoever releases):
  1. Run the `desktop-addon` workflow in GitHub Actions. It builds on an Apple Silicon runner, checks the program starts, and attaches
     `presidio-addon-macos-arm64.zip` to the `desktop-addons` release. The job summary prints the checksum and size.
  2. Paste `sha256` and `size` into `backend/addon_manifest.json` and commit it.
  3. Build the app (`npm run dist`). Until the manifest has a checksum, the app says "has not been published for this version yet".
  Locally: `scripts/freeze-presidio.sh` builds the same zip into `build/` (needs Presidio, `en_core_web_sm` and PyInstaller in the backend venv).
  To try the download without publishing, point `SB_ADDON_MANIFEST` at a manifest whose `url` is a `file://` address.
- From source nothing changes: Install still pip-installs Presidio into the backend's own Python.

## Live view

The agent drives its own Chromium (headless by default). The backend mirrors it into the window as JPEG frames (Chrome's screencast) and applies your clicks, scrolls and keys back to the page.

- **Take control** pauses the agent before its next model call, so no tokens are spent while you drive. **Hand back** resumes it.
- When the agent needs you (a bot check, a login, a model request for help) the window shows what it needs and gives you the browser. **I'm done, continue** hands it back.
- **Stop** works during a model call, not only between steps.
- Why a mirror and not an embedded browser view: embedding needs Electron's debugging port, which exposes the whole app (including its own window and the backend token) to any program on the computer, and the agent could see and switch to the app's own tab. The mirror adds no exposure.
- Playwright's synchronous API only delivers frames while its thread is inside a Playwright call, so `backend/live.py` runs the model call in a helper thread and pumps the browser every 50 ms meanwhile.
- Known limits: a little lag, no native scrolling feel or IME, and the frame is a picture of the page, not the browser's own chrome (tabs, address bar).

## Models on this computer

With Ollama or LM Studio selected, the model sheet lists what is installed there (and the quick-switch menu offers it), instead of asking you to type a name.

## Guardrails

The Guardrails screen sets every limit the library offers, once, for all runs (kept in the app's local storage):

- **Sites:** web pages only, an allow list, a block list. Checked on every page, including after a redirect.
- **Known phishing sites:** under "Never these sites", *Download the list* fetches the public [OpenPhish](https://openphish.com) community feed (one request to openphish.com, nothing about you sent), keeps the site names on this computer, and blocks them on every run. *Update the list* fetches it again; the switch turns it off without losing it. It sits beside your own list and never edits it. Hosts such as docs.google.com or github.io are left out so normal pages keep working, but a phishing page on a subdomain of one is still blocked. The feed lists live phishing pages only, so it is not complete, and it is not updated on its own: update it when you want a fresh copy. Check OpenPhish's terms for how you may use the feed.
- **Actions:** ask before risky clicks, uploads and dialogs (the run pauses with Allow / Don't allow). The words that make a click risky are an editable list. Watch for instructions hidden in pages.
- **Strict preset:** one button turns on the guardrails that limit what a hijacked agent could do, then asks for the sites the task needs. Clicks and form posts to a site outside the allow list are refused before any request is made.
- **Personal data in pages:** mask emails, phones, SSNs and card numbers (and, with Presidio installed, names) before the model reads the page; type them back or mask for good.
- **Limits:** most steps, tokens, seconds and dollars (a dollar limit needs your model's prices).
- **Messages to the model:** review before sending and show My info values in the answer, the same controls as on the Run screen.

They apply to agent runs, including follow-ups, not to replaying a saved flow.

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

- **Clean up with a model.** In the review sheet, “Clean up with a model” asks the model you chose to turn the recording into a clean flow: remove detours, rebuild messy steps (opening a dropdown and clicking an option becomes one `select`), name the values that change as inputs and write a short description. The model points at recorded steps and never writes an element, address or value itself, so it cannot invent one; steps that wait for a person and the step that reads the result must stay. It first shows exactly what will be sent (step wording and typed values only, no page contents; anything personal is replaced with `[removed: …]`, page addresses lose their query strings, and the instructions include the [flows documentation](../docs/flows.md)), and sends only after you press Send. Personal values in the result become inputs that are asked for on each run. You see the proposed steps and what was removed before accepting, and can undo. The model cannot see the page, so run the flow once to check it. A local model (Ollama) keeps everything on your computer.

- **History.** Each finished run (and flow replay) is summarised under History: the task, outcome, answer or error, steps, time and token counts. “Run again” puts the task back in the Run box. It is stored as small JSON files in the app's data folder (`history/`), the last 500 only. Pages, screenshots and what was sent to the model are not kept, and My info shared with the model is stripped from the task. Turn “Keep a history of runs” off to stop recording, or use Clear history.

- **Tying a form to a website.** A form with a field labelled Website (also Site, URL or Domain) holding an address is for that site: its values are typed only on that site and its subdomains, never anywhere else, and the agent is told so if it tries. When it asks for a saved login, it is offered the one saved for the page it is on, so a task does not need to name the form, and a login saved for another site is not offered at all. The form shows which site it is tied to. A form with no Website field works as before, on any site. This applies to agent runs; replaying a saved flow does not check the site yet.
- **Passwords and secrets in My info.** “Add password or secret” (and the Website login and Sensitive details templates) make protected fields: masked, kept only on this computer, never offered to the model, and never shown beside a placeholder in the inspector. Showing one needs Touch ID where the Mac has it (a plain confirmation elsewhere), and it covers itself again after 15 seconds or when you leave the tab. Like everything in My info they are encrypted with the system keychain. Card numbers are still refused.

- **Layout.** The Run screen has three states. Idle: a centred prompt box with Model, My info, Browser and ⋯ (personal-data detection, approve each call) pills, and shortcuts to your recent runs and flows. Running: a bar with the task, status and Stop, the steps on the left, the live browser in the middle and the Outbound inspector on the right. Finished: the result with its numbers, Run again, Save as flow, Copy summary, New run (Cmd+N) and a follow-up box that starts a new run with the last result as context.

- **Review before sending.** Under ⋯ (and in the run bar) choose Off, When something looks personal, or Every model call. The run stops before the call, shows exactly what is in it with the personal parts highlighted, and waits: Send as is, Send with these replaced (they go as placeholders like `<EMAIL_1>` from the library's own masking: the real value is typed back for the model on the site where it was seen, or on any site if you wrote it in the task, and your answer shows the real value), or Stop the run. A choice on a piece of text is remembered for the rest of the run, so one email in the task does not stop every call. The setting is remembered and can be changed during a run, which releases a held call if you switch it off. Checks: emails, phones, cards, your My info values, and names too if Presidio is on. Screenshots are not scanned.

  Replacing is reversible only when review was on when the run started (the run then carries the library's vault, about 55 more tokens per call for a note on how to use placeholders). If you switch review on mid-run, a replaced value goes as `[removed: …]` and is not put back. Saved flows turn a typed placeholder into a required input.

  Each flagged item in the banner has a tick: replace it or leave it. Presidio can take a form label (such as “Suff.” on a W-2) for a name and miss part of a real one, so you decide. Items you leave are not asked about again. When something is replaced the model is also told to write the placeholder in its answer, which is swapped for the real value before you read it.

- **Show My info values in the answer.** When the model reports one of your saved values it writes a placeholder such as `<secret:MY_BASIC_INFO_FIRST>`. The switch under ⋯ (on by default, remembered) swaps the real value in on your screen, in the result and in History. It is done at display time only: the stored answer and anything sent to a model keep the placeholder (a follow-up uses the placeholder version), and passwords and other protected fields are never swapped in.

- **Follow-ups stay in the same run.** The bar at the bottom of a run is always there (it waits while the agent is working). A follow-up carries on in the same browser, on the page it ended on, with the earlier task and answer as context, and its steps are added under a “Follow-up” mark in the same run and the same History entry. A masked value means the same thing across turns. The browser is kept open for 10 minutes after an answer; starting a new run, New run, or quitting the app closes it. If it has already closed, the follow-up starts a new run with the earlier result as context. A follow-up turn cannot be saved as a flow (it starts mid-way).
