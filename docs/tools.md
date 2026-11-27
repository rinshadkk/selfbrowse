# What the agent can do

## What the agent can do

`goto`, `click`, `type`, `select` (dropdowns, native or custom), `press`, `scroll`, `back`, `wait`, `read` (text on screen), `find` (jump to a word on a long page), `switch_tab`, `close_tab`, `remember`, `ask_human` and `done`. Two more appear only when they can be used: `upload` (when you pass files) and `drag` (on a page that has something to drag).

- **Dropdowns:** a native `<select>` is listed with its current value and options, and `select` picks one by its text or value. `select` also works on custom dropdowns built from page elements (ARIA comboboxes and listboxes, menus, autocomplete suggestions, or plain `<div>` lists): it opens the dropdown if it is marked closed or nothing is showing, finds the option by its text, scrolls to it and clicks it, in one call. A combobox is shown as `(open)` or `(closed)`, and while it is open its choices are in the list as `option` lines. To use an autocomplete, `type` first, then `select` the suggestion. Limits: it matches visible text only, and a dropdown that is already open is read as it stands, so choices that only appear after more scrolling inside the dropdown are not found.
- **File upload:** `upload` attaches a file to a file input (shown as `file "Résumé" (accepts .pdf)`, even when the real input is hidden behind a styled button) or to a button that opens a file picker. The model can only use files you list: `--file PATH` on the command line (repeatable), `files=[...]` in Python, `--file` on `selfbrowse-mcp`. It sees their names, never their folders, and anything else is refused. Without any files the tool is not offered. With `--confirm-risky` a person approves each upload first. A saved flow cannot replay an upload yet, so a run that uploaded is not saved as a flow.
- **Drag and drop:** `drag(ref, to)` presses on one listed element, moves to another and lets go, using real mouse events, so HTML5 drag and drop and script-driven drag both run. Draggable elements (`draggable="true"`, or a page that listens for `dragstart`) are listed as `draggable`, and drop targets (a page that listens for `drop` or `dragover`) as `drop target` or `dropzone`. Limits: libraries that listen only on the page root hide their drop targets, so list the target by clicking its label or text instead; sliders and canvas-based drag are not covered.
- **Frames and web components:** controls inside iframes (same-origin and cross-origin) and open shadow roots appear in the same numbered list and are clicked the same way.
- **Tabs:** when a link or popup opens a new tab the agent follows it, and the page list starts with `[tabs: 1 "Shop" · 2 "Details" (current)]` so the model knows. Not supported yet: closed shadow roots. See [ROADMAP.md](https://github.com/rinshadkk/selfbrowse/blob/main/ROADMAP.md).

Each tool schema is sent on every model call, so tools are kept few and short (about 890 tokens for the standard set on a typical step; `upload` and `drag` add about 140 together when they are offered).

## How learning works

Knowledge is stored per site in `~/.selfbrowse/sites/<domain>.json`.

- **Memo**: short facts the model chose to save with the `remember` tool.
- **Flows**: click sequences that worked, keyed by page type (for example `/*/dp/*`). A flow is replayed without a model call only when it is trusted:
  - **generic**: it succeeded for at least two *different* tasks (a cookie banner, a sign-in step), so it is replayed for every task;
  - **repeat**: it succeeded at least twice for the *exact same* task, so it is replayed for that task only.
- Only successful runs are learned from. Steps after typing, or after a click that changes the page in place (such as "Add to cart"), are never recorded for that page; only clicks that open another page or dismiss a banner or dialog are replayed. Risky clicks (buy, pay, delete, send, sign out and similar) are never recorded. Failed actions and detours (clicks followed by going back) are not learned. A flow that stops working is dropped, and flows unused for 90 days expire.

When learning is used, the command line says so on that step: `(learned: replayed from saved flow, no model call)` for a replayed click, `(learned: used saved notes about this site)` when the model chose the step with saved notes in front of it. In Python, check `step.from_cache` and `step.used_notes`.

Each page type keeps up to eight distinct click sequences (*variants*), and trust is worked out for the **start** of a sequence. If the cookie-banner click came first in two different tasks, it is replayed for any task even though what followed differed. A different path on a later run is kept as another variant instead of erasing a trusted flow. Files written by earlier versions still load.

Replaying goes by page type and element label: the agent finds the stored control again by role and text on a fresh page list (an exact text match, or a single partial match). If it is missing or ambiguous the flow records a miss and the model takes over, and every replayed click still passes the guardrails.

**How much it saves:** not shown yet. In small tests on a demo shop with qwen3.8 and Claude Haiku 5.5, replay rarely triggered and we measured no reliable saving. When a model moves between pages by address instead of clicking, there is nothing to replay. The qwen3.8 runs are in `benchmarks/compare/results/qwen3.8-learning/`; run the comparison yourself with `benchmarks/compare/learning_eval.py`.

Known limit: research-style tasks learn little, because most of their clicks are specific to the question. Learning is aimed at generic steps and routine jobs you repeat.
