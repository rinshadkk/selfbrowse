# Pop-ups, notifications and permissions

**New tabs and windows** (`target=_blank`, OAuth login windows) are followed. The page list shows `[tabs: ...]` and the agent can `switch_tab` and `close_tab`.

**Overlays a site draws itself** (cookie banners, "Allow notifications?" cards, newsletter modals) are ordinary page elements, so the agent sees them in the list and clicks "No thanks" or "Accept".

**Browser permissions** (notifications, location, camera, microphone, clipboard) are off by default, so a site that asks is refused and nothing pops up. To allow some for every site you visit:

```bash
selfbrowse --permissions notifications,geolocation "Open weather.example.com and tell me today's forecast for my area"
```

```python
from selfbrowse import BrowseAgent, Browser

BrowseAgent("...", browser=Browser(permissions=["geolocation"]))
```

Names: `geolocation`, `notifications`, `camera`, `microphone`, `clipboard-read`, `clipboard-write`, `midi`, `midi-sysex`, `payment-handler`, `background-sync`, `accelerometer`, `gyroscope`, `magnetometer`, `ambient-light-sensor`, `accessibility-events`, `storage-access`. A misspelt name stops the run with the list. Grant the fewest you need, and combine with `--allow-domain` so only the site you meant gets them. The MCP server takes the same `--permissions` flag.

**JavaScript dialogs** (`alert`, `confirm`, `prompt`, "Leave site?") are shown to the model. After an action that raises one, the result says what it was and what happened, for example `[A confirm dialog appeared: "Delete everything?". It was dismissed.]`.

| `--dialogs` | `alert` / leave-page | `confirm` / `prompt` |
|---|---|---|
| `auto` (default) | accepted | dismissed (counts as Cancel) |
| `accept` | accepted | accepted |
| `dismiss` | dismissed | dismissed |

With `accept`, guardrails still apply: `--confirm-risky` asks a person before accepting a dialog about deleting, paying or sending, and the MCP server (where nobody can be asked) dismisses it. A dialog the model cannot answer in advance is declined, so if a task needs one accepted, run with `--dialogs accept`.

**Not visible to the agent:** the browser's own prompts that are drawn outside the page ("Save password?", file pickers, print dialogs). In `--headed` mode a person can click them. Permissions above cover the common ones.
