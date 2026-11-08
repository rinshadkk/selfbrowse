"""Site learning: notes and click paths that make repeat runs cheaper.

A path is only trusted after it worked for two different tasks (or twice for the same one),
risky clicks are never recorded, and notes expire after 90 days.

    python examples/09_learning.py
"""
from pathlib import Path

from selfbrowse import Agent
from selfbrowse.knowledge import SiteKnowledge

home = Path("~/.selfbrowse").expanduser()

for task in ("Open en.wikipedia.org and tell me the title of today's featured article.",
             "Open en.wikipedia.org and tell me what 'In the news' mentions first."):
    result = Agent(task, llm="anthropic:claude-haiku-4-5", home=home, learn=True).run()
    replayed = sum(1 for s in result.history if s.from_cache)
    print(f"{result.usage.calls} model calls, {replayed} replayed steps -> {result.output[:80]}")

store = SiteKnowledge(home / "sites")
print("learned sites:", store.domains())
# store.forget("en.wikipedia.org")      # or: selfbrowse forget en.wikipedia.org
# Agent(..., learn=False)               # to ignore and not write site knowledge
