# Guardrails

Rules between the model and the browser. Pass them as a list:

```python
from selfbrowse import BrowseAgent
from selfbrowse.guardrails import AllowedDomains, ConfirmRisky, RedactPII, PresidioRedact, InjectionWatch, Budget

BrowseAgent(
    "task",
    guardrails=[
        AllowedDomains(["example.com"]),      # also allows subdomains
        ConfirmRisky(),                       # asks before Buy / Pay / Delete / Send / Sign out
        RedactPII(),                          # hides emails, phones, SSNs, cards behind <EMAIL_1>-style placeholders
        PresidioRedact(),                     # optional: also names, via Microsoft Presidio (needs selfbrowse[presidio])
        InjectionWatch(),                     # warns on "ignore previous instructions"-style page text
        Budget(max_tokens=50_000, max_seconds=300),
    ],
).run()
```

| Guardrail | What it does |
|---|---|
| `SafeUrls` | http(s) pages only; blocks `file:`, `chrome:`, `data:`, `javascript:`. **Always on** unless `safe_urls=False` |
| `AllowedDomains([...])` | only these sites (judged on the real hostname, so `https://good.com@evil.com` is evil.com). Also undoes a click that lands elsewhere, and refuses a start page outside the list |
| `BlockedDomains([...])` | never these sites |
| `ConfirmRisky()` | asks a person before a click whose label looks irreversible; with nobody to ask (headless) it blocks instead |
| `RedactPII(kinds=..., restore=True)` | hides emails, phone numbers, US SSNs and Luhn-valid card numbers behind placeholders like `<EMAIL_1>`; the real value is typed back on the same site. Names and addresses are not detected. `restore=False` masks for good as `[email]` |
| `PresidioRedact(entities=, threshold=, model=)` | optional. Uses Microsoft Presidio and a spaCy model to mask names as well as emails, phones, cards, SSNs, IBANs, passports and similar. Runs locally. Install with `pip install 'selfbrowse[presidio]'`; see [Names and other personal data](personal-data.md#names-and-other-personal-data-presidio) |
| `InjectionWatch()` | flags instruction-like page text, tells the model to treat it as data, and requires confirmation before navigating, typing or risky clicks from that page |
| `Budget(max_tokens=, max_seconds=, max_usd=, price=(in, out))` | stops a run that goes over; `max_usd` needs the per-million-token prices you pay, and counts cached input at full price, so it is a ceiling |

Confirmations use the same prompt as a hand-off (`--headed`, press Enter to approve or `n` to deny). From Python, your `handoff=` function receives `request.kind == "confirm"`; return `True` to allow the action.

Your own rule is a small class; override only the hooks you need:

```python
from selfbrowse.guardrails import Guardrail, Block

class NoSocial(Guardrail):
    def check_url(self, url):                      # also: on_page, before_action, after_step
        if "facebook.com" in url:
            return Block("social sites are off limits")
```
