"""Tool definitions the model sees. Kept deliberately small: every schema is paid for on every call."""
from __future__ import annotations

from typing import Any


def _tool(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": properties or {}, "required": required or []},
    }


def build_tools(*, vision: bool = False) -> list[dict[str, Any]]:
    tools = [
        _tool("goto", "Open a URL.", {"url": {"type": "string"}}, ["url"]),
        _tool("click", "Click element #ref from the latest page list.", {"ref": {"type": "integer"}}, ["ref"]),
        _tool(
            "type",
            "Click element #ref and type text into it. submit=true presses Enter afterwards. "
            "Use <secret:NAME> for stored secrets.",
            {"ref": {"type": "integer"}, "text": {"type": "string"}, "submit": {"type": "boolean"}},
            ["ref", "text"],
        ),
        _tool("press", "Press a key, e.g. Enter, Escape, Tab, ArrowDown.", {"key": {"type": "string"}}, ["key"]),
        _tool("scroll", "Scroll the page.", {"direction": {"type": "string", "enum": ["down", "up"]}}),
        _tool("back", "Go back one page."),
        _tool("wait", "Wait for the page to update.", {"seconds": {"type": "number"}}),
        _tool("read", "Return the text visible on screen (use when the answer is text, not a control)."),
        _tool("remember", "Save one short, reusable fact about this website for future runs.", {"fact": {"type": "string"}}, ["fact"]),
        _tool(
            "done",
            "Finish. success=false if the task cannot be completed.",
            {"success": {"type": "boolean"}, "answer": {"type": "string"}},
            ["success", "answer"],
        ),
    ]
    if vision:
        tools.insert(-2, _tool("screenshot", "See the page as an image (costly; use only when the list is not enough)."))
    return tools
