# Flows: replay a whole run with no model

A *flow* is a whole run saved as a file. Once you have one, `selfbrowse flow run` plays it back with **no model call**: no tokens, no API key, a few seconds, and the same steps every time.

Learning (see [How learning works](tools.md#how-learning-works)) replays only the start of a run, and only once it is trusted. A flow is the entire run, available after one success.

## Record one

Add `--save-flow` to any task. The file is written only if the run succeeds.

Give it a bare name and the flow is kept in `~/.selfbrowse/flows/` (or `$SELFBROWSE_HOME/flows/`), next to the learned `sites` and the `traces`. Give it a path, meaning anything with a folder or `.json`, and it goes exactly there.

```bash
selfbrowse "Find the cheapest flight from COK to SFO" --save-flow fare         # ~/.selfbrowse/flows/fare.json
selfbrowse "Find the cheapest flight from COK to SFO" --save-flow ./fare.json   # this folder
```

From Python:

```python
agent = BrowseAgent("Find the cheapest flight from COK to SFO", save_flow="fare.json")
agent.run()
print(agent.flow_path)
```

## Look at it, then run it

```bash
selfbrowse flow list                       # the flows saved by name
selfbrowse flow show fare
selfbrowse flow run fare
selfbrowse flow run fare --param from=BLR --param to=LHR
selfbrowse flow run ./fare.json            # a file anywhere
```

`flow show` lists the sites, the parameters, the secrets and every step, so you can read what a flow will do before you run it. From Python, `run_flow("fare.json", params={"from": "BLR"})`.

## Optional: let a model help

By default a flow never calls a model. Two switches turn one on. Both use the one model you give with `-m` (or `$SELFBROWSE_MODEL`), and the run stops with an error if you ask for either without a model, so nothing is ever spent by default.

| Switch | What it does | Cost |
|---|---|---|
| `--answer-with-model` | After the last step, sends the text the flow read to the model and prints its answer to the task | One call |
| `--repair-with-model` | If a step cannot find its element, the model carries on from the page the flow reached and finishes the task | Like a normal run from that page, capped by `--repair-max-steps` (default 15) |

```bash
selfbrowse flow run fare.json -m anthropic:claude-haiku-4-5 --answer-with-model --ask "Which fare is cheapest?"
selfbrowse flow run fare.json -m anthropic:claude-haiku-4-5 --repair-with-model --save-repaired fare.v2.json
```

`--ask` replaces the flow's recorded task as the question. `--save-repaired FILE` keeps a new flow made of the steps before the failure plus the steps the model took; it never overwrites the original, so read it with `flow show` before you rely on it. From Python: `run_flow(flow, llm="anthropic:...", answer_with_model=True, repair_with_model=True)`, then `result.repaired_flow`.

Rules for repair:

- **Only a missing element is repaired.** A guardrail block, a declined approval, a missing secret or a wrong landing page always stops the run. Nothing has happened at the failed step, so the model cannot repeat a click or submit.
- **The same guardrails apply**: the flow's sites, risky-click approval, and any `--allow-domain` you added.
- **Your private values stay hidden.** The model sees `<secret:NAME>` for secrets and for parameters that had no default (personal data), and those values are replaced with the placeholder if they show up in the page list. Values shorter than 3 characters cannot be masked this way. Parameters that have a default, and the page text, are sent to the model.
- **A model reading page text can be misled by that text**, as in any run. For a flow you did not record, use `--headed`.
- The summary line shows model calls and tokens, so a flow that has started needing repair is visible.

## Parameters

Anything that was typed or chosen becomes a parameter, named after the field (`from`, `to`), with the recorded value as its default. Pass `--param NAME=VALUE` to change it. An unknown parameter name stops the run. A required parameter (one with no default) that you did not pass is asked for when you run in a terminal; in a script or cron job, where nobody can answer, the run stops with an error naming the parameter instead of hanging.

## What is never written to the file

| Value | In the file | At run time |
|---|---|---|
| A secret typed as `<secret:PASSWORD>` | The name `PASSWORD` only | Read from `$SELFBROWSE_SECRET_PASSWORD`; the run refuses to start without it |
| A personal value masked for the model, such as `<EMAIL_1>` | A required parameter with no default | You pass `--param email=...` |
| Page text the model read | Nothing | Read again from the live page |

## Safety rules a flow always follows

- It stays on the sites it was recorded on (`domains` in the file), plus any `--allow-domain` or `--block-domain` you add. A step that lands elsewhere stops the run.
- A click on something like Buy, Pay, Delete or Send asks a person first, as in a normal run. With `--headed` you are asked in the terminal; headless, the run stops.
- Only `http` and `https` pages. The file is checked before anything runs: known step kinds, a size limit, and every parameter and secret declared.

## When it fails

Elements are found again by role, label and position among identical ones. If the site changed and one is gone or unclear, the run stops and names the step, for example `step 4 (click button "Search"): could not find ...`. Record the flow again, or run it with `--repair-with-model` (below). Without that switch a flow never asks a model for help.

## What a flow cannot do

- **It cannot summarise on its own.** Its output is the text of the last `read` step, or the visible text of the final page if there was none. `--answer-with-model` adds the summary.
- **It repeats a path, it does not decide.** A site that shows different pages on different days (a pop-up, an A/B test) can stop it.
- **A CAPTCHA or login pause** is recorded as a `pause` step and needs `--headed` and a person each time.

## File format

JSON, one file per flow. The fields are `selfbrowse_flow` (the format version, `1`), `name`, `description`, `domains`, `params`, `secrets` and `steps`. A step is `{"do": "click", "target": {"role": "button", "text": "Search", "nth": 0, "of": 1}}`. The kinds are `goto`, `click`, `type`, `select`, `press`, `scroll`, `back`, `wait`, `switch_tab`, `close_tab`, `read`, `find` and `pause`.
