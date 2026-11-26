"""A shopping task with the safety belts on: approvals, a budget, room to finish.

    python examples/10_shopping_safely.py

It runs against a small demo shop on your own computer, so nothing is really bought.
"""
import sys
from pathlib import Path

from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import (
    AllowedDomains, Budget, ConfirmRisky, RedactPII,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks" / "compare"))
import store  # noqa: E402  (the small demo shop that ships in this repository)

shop = store.serve()[1]                              # http://127.0.0.1:<a free port>

with Browser(headless=False) as browser:
    result = BrowseAgent(
        f"On {shop}, add a kettle under $30 to the cart, open the cart and stop there. "
        "Do not place an order.",
        llm="anthropic:claude-haiku-4-5",
        browser=browser,
        max_steps=40,                       # a real checkout flow takes 15-25 steps by itself
        max_output_tokens=4096,
        guardrails=[
            AllowedDomains(["127.0.0.1"]),
            ConfirmRisky(),                 # "Place order", "Pay now" ask you first
            RedactPII(),
            Budget(max_tokens=150_000, max_seconds=420),
        ],
        trace=True,
    ).run()
print(result.output if result.success else f"FAILED: {result.error}")
