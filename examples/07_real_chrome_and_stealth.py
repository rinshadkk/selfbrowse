"""Fewer bot blocks: real Chrome, a saved profile, and optional Patchright.

Sites like Target and Walgreens score headless, cookie-less browsers harshly. Visible, installed
Chrome with a profile that keeps cookies between runs gets through far more often.

    pip install 'selfbrowse[stealth]' && patchright install chromium     # only for stealth=True
    python examples/07_real_chrome_and_stealth.py
"""
from pathlib import Path

from selfbrowse import BrowseAgent, Browser

browser = Browser(
    headless=False,                                  # visible
    channel="chrome",                                # your installed Chrome, not bundled Chromium
    user_data_dir=Path("~/.selfbrowse/profile").expanduser(),   # cookies and logins survive between runs
    stealth=False,                                   # True: Patchright; helps on some sites, never a guarantee
    viewport=(1366, 850),
)
with browser:
    result = BrowseAgent("Open target.com and tell me today's top deal banner.",
                   llm="anthropic:claude-haiku-4-5", browser=browser).run()
print(result.output if result.success else f"FAILED: {result.error}")
