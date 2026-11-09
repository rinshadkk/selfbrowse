"""A shopping task with the safety belts on: approvals, a budget, room to finish.

    python examples/10_shopping_safely.py
"""
from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import AllowedDomains, Budget, ConfirmRisky, RedactPII

with Browser(headless=False, channel="chrome", user_data_dir="~/.selfbrowse/shop") as browser:
    result = BrowseAgent(
        "On walgreens.com add a Dove shampoo under $10 to the cart and stop at the checkout page. "
        "Do not place the order.",
        llm="anthropic:claude-haiku-4-5",
        browser=browser,
        max_steps=40,                       # a real checkout flow takes 15-25 steps by itself
        max_output_tokens=4096,
        guardrails=[
            AllowedDomains(["walgreens.com"]),
            ConfirmRisky(),                 # "Place order", "Pay now" ask you first
            RedactPII(),
            Budget(max_tokens=150_000, max_seconds=420),
        ],
        trace=True,
    ).run()
print(result.output if result.success else f"FAILED: {result.error}")
