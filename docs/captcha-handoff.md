# CAPTCHAs and handing off to a person

## Sites that show a CAPTCHA (Walmart, Target and similar)

Large retailers run bot detection that scores each visit before showing the page. The default setup (bundled headless Chromium, fresh profile, no history) looks like automation and often gets a challenge. A tool attached to your everyday Chrome passes more often because it has your cookies, history and a normal browser fingerprint.

Try these in order:

1. Your installed Chrome, visible, with a saved profile:

```bash
selfbrowse --headed --channel chrome --profile ~/.selfbrowse/profile "open walmart.com and tell me the heading"
```

2. If it is still blocked, add the stealth option (`pip install -e '.[stealth]'`):

```bash
selfbrowse --headed --channel chrome --profile ~/.selfbrowse/profile --stealth "open walmart.com and tell me the heading"
```

3. Browse to the site once yourself in that same profile window, so it has real cookies and history.

Selfbrowse does not solve or defeat CAPTCHAs. Instead it hands the browser to you (next section). Also check each site's terms of service before automating shopping or scraping at scale.

## Handing off to a person

When the agent cannot go further, it pauses and lets you act in the visible browser window, then continues from wherever you leave the page. It happens when:

- **a bot check appears** (CAPTCHA, "verify you are human", "press and hold", Cloudflare "Just a moment"). Detected automatically; the model is not called while the page is blocked.
- **the model asks**: for a login with no stored secret, a 2FA code, a payment step or a choice only you can make, it calls `ask_human`.

```bash
selfbrowse --headed --profile ~/.selfbrowse/profile "open target.com and tell me the heading"
```

When it needs you, the terminal shows a box with the reason and URL and rings the bell. Do the step in the browser window, then press **Enter** in the terminal to continue (type `q` + Enter to give up). Using `--profile` keeps the cookies from a solved check for later runs.

- Without `--headed` there is nobody to hand off to, so the run stops at once with a clear error ("blocked: ... re-run with --headed") instead of wasting model calls.
- Nothing you type or see is sent to the model; it is only told you finished.
- It gives up after 3 hand-offs in one run, or if the page is still blocked after you resume.
- `--no-handoff` turns this off.

From Python, use the built-in terminal prompt or plug in your own (a desktop notification, a Slack message, a web UI):

```python
from selfbrowse import BrowseAgent, Browser

def ask_person(request):                  # request.kind: "challenge" or "model"
    print(request.reason, request.url)    # notify however you like
    input("Press Enter when done: ")
    return True                           # False = give up

BrowseAgent("task", browser=Browser(headless=False), handoff=ask_person).run()
```

`handoff="auto"` (default) uses the terminal prompt when the window is visible; `handoff=False` disables it.
