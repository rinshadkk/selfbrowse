# What the agent can do

## What the agent can do

`goto`, `click`, `type`, `select` (native dropdowns), `press`, `scroll`, `back`, `wait`, `read` (text on screen), `find` (jump to a word on a long page), `switch_tab`, `close_tab`, `remember`, `ask_human` and `done`.

- **Dropdowns:** a native `<select>` is listed with its current value and options, and `select` picks one by its text or value.
- **Frames and web components:** controls inside iframes (same-origin and cross-origin) and open shadow roots appear in the same numbered list and are clicked the same way.
- **Tabs:** when a link or popup opens a new tab the agent follows it, and the page list starts with `[tabs: 1 "Shop" · 2 "Details" (current)]` so the model knows. Not supported yet: closed shadow roots, drag and drop, file uploads, custom (non-`<select>`) dropdowns beyond clicking them. See [ROADMAP.md](https://github.com/rinshadkk/selfbrowse/blob/main/ROADMAP.md).

Each tool schema is sent on every model call, so tools are kept few and short (about 790 tokens for all of them on a typical step).

## How learning works

Knowledge is stored per site in `~/.selfbrowse/sites/<domain>.json`.

- **Memo**: short facts the model chose to save with the `remember` tool.
- **Flows**: click sequences that worked, keyed by page type (for example `/*/dp/*`). A flow is replayed without a model call only when it is trusted:
  - **generic**: it succeeded for at least two *different* tasks (a cookie banner, a sign-in step), so it is replayed for every task;
  - **repeat**: it succeeded at least twice for the *exact same* task, so it is replayed for that task only.
- Only successful runs are learned from. Steps after typing on a page are never recorded for that page. Risky clicks (buy, pay, delete, send, sign out and similar) are never recorded. Failed actions and detours (clicks followed by going back) are not learned. A flow that stops working is dropped, and flows unused for 90 days expire.

Known limit: research-style tasks learn little, because most of their clicks are specific to the question. The biggest wins are generic steps and routine jobs you repeat.
