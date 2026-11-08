"""Limit what the agent may do. Guardrails run in the order given.

    python examples/04_guardrails.py
"""
from selfbrowse import Agent, Browser
from selfbrowse.guardrails import (
    AllowedDomains, BlockedDomains, Budget, ConfirmRisky, InjectionWatch, RedactPII,
)

# ConfirmRisky and InjectionWatch ask a person in the terminal when the browser is visible.
# Headless, there is nobody to ask, so they block the action instead. That is why this runs visible.
with Browser(headless=False) as browser:
    result = Agent(
        "Find the price of the cheapest hair oil on walgreens.com and tell me the name.",
        llm="anthropic:claude-haiku-4-5",
        browser=browser,
        guardrails=[
            AllowedDomains(["walgreens.com"]),
            BlockedDomains(["ads.walgreens.com"]),
            ConfirmRisky(),
            RedactPII(),
            InjectionWatch(),
            Budget(max_tokens=60_000, max_seconds=180),
        ],
    ).run()
print(result.output if result.success else f"FAILED: {result.error}")
