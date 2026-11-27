"""Hand the browser to a person when it cannot go further (CAPTCHA, login, 2FA, payment).

Visible browser: the default terminal prompt appears. Your own handler: any function that takes a
HandoffRequest and returns True (continue / approve) or False (stop / decline).

    python examples/06_handoff.py https://your-site.example
"""
import sys

from selfbrowse import BrowseAgent, Browser
from selfbrowse.handoff import HandoffRequest


def my_handler(req: HandoffRequest) -> bool:
    # kind is "challenge" (a bot check was detected), "model" (the agent asked for help)
    # or "confirm" (a guardrail wants approval).
    print(f"\n[{req.kind}] {req.reason}\n  at {req.url}")
    if req.kind == "confirm":
        return input("  Allow it? [y/N] ").strip().lower() == "y"
    input("  Fix it in the browser window, then press Enter... ")
    return True


url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

with Browser(headless=False, channel="chrome") as browser:
    result = BrowseAgent(
        f"Open {url} and tell me the main heading.",
        llm="anthropic:claude-haiku-4-5",
        browser=browser,
        handoff=my_handler,       # True/"auto" = built-in terminal prompt when visible; False = never ask
        max_handoffs=3,
    ).run()
print(result.output if result.success else f"FAILED: {result.error}")
