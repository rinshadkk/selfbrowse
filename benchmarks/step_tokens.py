"""
Measure what Selfbrowse sends to the model on the first step for a few real pages.

No model or API key needed: a recording fake model captures the exact request.
Token counts use tiktoken's o200k_base, an approximation of any vendor's tokenizer.

    pip install -e '.[bench]' && python benchmarks/step_tokens.py
"""
from __future__ import annotations

import json

import tiktoken

from selfbrowse import BrowseAgent, Browser
from selfbrowse.llm.base import LLMResponse
from selfbrowse.types import Usage

PAGES = {
    "Hacker News": "https://news.ycombinator.com/",
    "Wikipedia article": "https://en.wikipedia.org/wiki/Web_browser",
    "Wikipedia search": "https://en.wikipedia.org/w/index.php?search=browser+agent",
    "BBC News": "https://www.bbc.com/news",
}
enc = tiktoken.get_encoding("o200k_base")


def count(obj) -> int:
    return len(enc.encode(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)))


class Recorder:
    model = "recorder"

    def __init__(self):
        self.req = None

    def complete(self, *, system, messages, tools, max_tokens=2048):
        self.req = (system, messages, tools)
        return LLMResponse([{"type": "tool_use", "id": "1", "name": "done", "input": {"success": True, "answer": "-"}}],
                           "tool_use", Usage(calls=1))


def main() -> None:
    print(f"{'page':<20}{'system':>8}{'tools':>8}{'page':>8}{'total':>8}")
    with Browser() as b:
        for name, url in PAGES.items():
            b.goto(url)
            rec = Recorder()
            BrowseAgent("benchmark", llm=rec, browser=b, learn=False).run()
            system, messages, tools = rec.req
            s, t, p = count(system[0]["text"]), count(tools), count(messages[0]["content"])
            print(f"{name:<20}{s:>8}{t:>8}{p:>8}{s + t + p:>8}")


if __name__ == "__main__":
    main()
