from __future__ import annotations

from pathlib import Path

import pytest

from selfbrowse.llm.base import LLMResponse
from selfbrowse.types import Usage

FIXTURES = Path(__file__).parent / "fixtures"


class ScriptedLLM:
    """Replays a fixed list of tool calls and records what it was shown."""

    model = "scripted"

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def complete(self, *, system, messages, tools, max_tokens=2048):
        self.seen.append(messages)
        name, args = self.script.pop(0)
        return LLMResponse(
            content=[{"type": "tool_use", "id": f"t{len(self.seen)}", "name": name, "input": args}],
            stop_reason="tool_use",
            usage=Usage(input_tokens=100, output_tokens=10, calls=1),
        )


@pytest.fixture(scope="session")
def shop_url():
    """Serve the fixture over http://127.0.0.1 (learned flows only apply to http(s) pages)."""
    import functools
    import threading
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(FIXTURES))
    handler.log_message = lambda *a, **k: None
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/shop.html"
    server.shutdown()
