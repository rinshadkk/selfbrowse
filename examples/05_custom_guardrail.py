"""Write your own guardrail: subclass Guardrail and override the hooks you need.

    python examples/05_custom_guardrail.py
"""
import re

from selfbrowse import BrowseAgent
from selfbrowse.guardrails import Action, Block, Confirm, Guardrail, RunState


class NoCheckoutPages(Guardrail):
    """Refuse to visit any URL that looks like a checkout."""

    def check_url(self, url):
        if re.search(r"checkout|/cart/pay", url, re.I):
            return Block("checkout pages are off limits for this agent")


class ConfirmBigTyping(Guardrail):
    """Ask before the agent types more than 200 characters into a field."""

    def before_action(self, action: Action):
        if action.tool == "type" and len(str(action.args.get("text", ""))) > 200:
            return Confirm("about to type a long text")


class HideInternalNames(Guardrail):
    """Rewrite page text before the model reads it."""

    def on_page(self, text: str, url: str) -> str:
        return re.sub(r"\bProject Falcon\b", "[internal project]", text)


class StopAfterTenSteps(Guardrail):
    def after_step(self, state: RunState):
        if state.steps >= 10:
            return Block("ten steps is enough for this task")


result = BrowseAgent(
    "Open example.com and tell me what the page says.",
    llm="anthropic:claude-haiku-4-5",
    guardrails=[NoCheckoutPages(), ConfirmBigTyping(), HideInternalNames(), StopAfterTenSteps()],
).run()
print(result.output)
