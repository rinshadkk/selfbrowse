"""Run the whole agent with no API key and no network: a scripted "model" on a local page.

Handy for learning the loop, writing tests, and checking your own guardrails.

    python examples/13_offline_no_key.py
"""
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from selfbrowse import Agent, Browser
from selfbrowse.llm.base import LLMResponse
from selfbrowse.types import Usage

PAGE = Path(__file__).parent.parent / "tests" / "fixtures"


class Script:
    """A stand-in model that replays fixed tool calls."""
    model = "scripted"

    def __init__(self, calls):
        self.calls = list(calls)

    def complete(self, *, system, messages, tools, max_tokens=2048):
        name, args = self.calls.pop(0)
        return LLMResponse(content=[{"type": "tool_use", "id": f"t{len(self.calls)}", "name": name, "input": args}],
                           stop_reason="tool_use", usage=Usage(input_tokens=100, output_tokens=10, calls=1))


handler = lambda *a, **k: SimpleHTTPRequestHandler(*a, directory=str(PAGE), **k)
server = HTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/form.html"

with Browser() as browser:
    browser.goto(url)
    country = next(e["ref"] for e in browser.snapshot().elements if e["text"] == "Country")
    model = Script([("select", {"ref": country, "option": "France"}),
                    ("read", {}),
                    ("done", {"success": True, "answer": "France selected"})])
    result = Agent("Pick France", llm=model, browser=browser, learn=False).run()

print(result.output, "|", [s.tool for s in result.history])
server.shutdown()
