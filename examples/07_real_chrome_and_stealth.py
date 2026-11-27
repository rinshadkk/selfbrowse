"""Fewer bot blocks: real Chrome, a saved profile, and optional Patchright.

Large retail sites score headless, cookie-less browsers harshly. Visible, installed
Chrome with a profile that keeps cookies between runs gets through far more often.

    pip install 'selfbrowse[stealth]' && patchright install chromium     # only for stealth=True
    python examples/07_real_chrome_and_stealth.py https://your-site.example
"""
import sys
from pathlib import Path

from selfbrowse import BrowseAgent, Browser

url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

browser = Browser(
    headless=False,                                  # visible
    channel="chrome",                                # your installed Chrome, not bundled Chromium
    user_data_dir=Path("~/.selfbrowse/profile").expanduser(),   # cookies and logins survive between runs
    stealth=False,                                   # True: Patchright; helps on some sites, never a guarantee
    viewport=(1366, 850),
)
with browser:
    result = BrowseAgent(f"Open {url} and tell me the main heading.",
                         llm="anthropic:claude-haiku-4-5", browser=browser).run()
print(result.output if result.success else f"FAILED: {result.error}")
