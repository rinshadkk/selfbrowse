"""Limit what the agent may do. Guardrails run in the order given.

    python examples/04_guardrails.py

It runs against a small demo shop on your own computer.
"""
import sys
from pathlib import Path

from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import (
    AllowedDomains, BlockedDomains, Budget, ConfirmRisky, InjectionWatch, RedactPII,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks" / "compare"))
import store  # noqa: E402  (the small demo shop that ships in this repository)

shop = store.serve()[1]                              # http://127.0.0.1:<a free port>

# ConfirmRisky and InjectionWatch ask a person in the terminal when the browser is visible.
# Headless, there is nobody to ask, so they block the action instead. That is why this runs visible.
with Browser(headless=False) as browser:
    result = BrowseAgent(
        f"On {shop}, find the cheapest kettle and tell me its name and price.",
        llm="anthropic:claude-haiku-4-5",
        browser=browser,
        guardrails=[
            AllowedDomains(["127.0.0.1"]),
            BlockedDomains(["ads.example.com"]),
            ConfirmRisky(),
            RedactPII(),
            InjectionWatch(),
            Budget(max_tokens=60_000, max_seconds=180),
        ],
    ).run()
print(result.output if result.success else f"FAILED: {result.error}")
