# Flows: replay a whole run with no model

A *flow* is a whole run saved as a file. Once you have one, `selfbrowse flow run` plays it back with **no model call**: no tokens, no API key, a few seconds, and the same steps every time.

Learning (see [How learning works](tools.md#how-learning-works)) replays only the start of a run, and only once it is trusted. A flow is the entire run, available after one success.

## Record one

Add `--save-flow` to any task. The file is written only if the run succeeds.

```bash
selfbrowse "Find the cheapest flight from COK to SFO" --save-flow fare.json
```

From Python:

```python
agent = BrowseAgent("Find the cheapest flight from COK to SFO", save_flow="fare.json")
agent.run()
print(agent.flow_path)
```

## Look at it, then run it

```bash
selfbrowse flow show fare.json
selfbrowse flow run fare.json
selfbrowse flow run fare.json --param from=BLR --param to=LHR
```

`flow show` lists the sites, the parameters, the secrets and every step, so you can read what a flow will do before you run it. From Python, `run_flow("fare.json", params={"from": "BLR"})`.

## Parameters

Anything that was typed or chosen becomes a parameter, named after the field (`from`, `to`), with the recorded value as its default. Pass `--param NAME=VALUE` to change it. A flow with an unknown or missing parameter stops before opening a browser.

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

Elements are found again by role, label and position among identical ones. If the site changed and one is gone or unclear, the run stops and names the step, for example `step 4 (click button "Search"): could not find ...`. Record the flow again. A flow never asks a model to repair itself.

## What a flow cannot do

- **It cannot summarise.** Its output is the text of the last `read` step, or the visible text of the final page if there was none.
- **It repeats a path, it does not decide.** A site that shows different pages on different days (a pop-up, an A/B test) can stop it.
- **A CAPTCHA or login pause** is recorded as a `pause` step and needs `--headed` and a person each time.

## File format

JSON, one file per flow. The fields are `selfbrowse_flow` (the format version, `1`), `name`, `description`, `domains`, `params`, `secrets` and `steps`. A step is `{"do": "click", "target": {"role": "button", "text": "Search", "nth": 0, "of": 1}}`. The kinds are `goto`, `click`, `type`, `select`, `press`, `scroll`, `back`, `wait`, `switch_tab`, `close_tab`, `read`, `find` and `pause`.
