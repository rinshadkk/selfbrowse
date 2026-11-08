"""Tool definitions the model sees. Kept deliberately small: every schema is paid for on every call."""
from __future__ import annotations

from typing import Any


def _tool(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": properties or {}, "required": required or []},
    }


def build_tools(*, vision: bool = False, human: bool = False) -> list[dict[str, Any]]:
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
        _tool("select", "Choose an option in a native dropdown (a combobox listing options:). Give the option's text.",
              {"ref": {"type": "integer"}, "option": {"type": "string"}}, ["ref", "option"]),
        _tool("press", "Press a key, e.g. Enter, Escape, Tab, ArrowDown.", {"key": {"type": "string"}}, ["key"]),
        _tool("scroll", "Scroll the page.", {"direction": {"type": "string", "enum": ["down", "up"]}}),
        _tool("back", "Go back one page."),
        _tool("wait", "Wait for the page to update.", {"seconds": {"type": "number"}}),
        _tool("find", "Scroll to text on the page and show what is around it. nth=2 jumps to the next match.",
              {"text": {"type": "string"}, "nth": {"type": "integer"}}, ["text"]),
        _tool("switch_tab", "Switch to another open tab by its number (see [tabs: ...]).", {"index": {"type": "integer"}}, ["index"]),
        _tool("close_tab", "Close a tab (default: the current one) and return to the previous one.", {"index": {"type": "integer"}}),
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
    if human:
        tools.insert(-1, _tool("ask_human", "Hand the browser to the person for something only they can do (CAPTCHA, login, 2FA, payment). Give a short reason.", {"reason": {"type": "string"}}, ["reason"]))
    return tools


# ── making sloppy tool calls usable ─────────────────────────────────────────────────
# Small models often send the right idea with the wrong key ({"id": 3} instead of {"ref": 3}).
# Fix what is unambiguous, and when it cannot be fixed say exactly what is expected.

_ALIASES: dict[str, tuple[str, ...]] = {
    "ref": ("id", "idx", "index", "element", "element_id", "ref_id", "number", "target", "node", "selector"),
    "text": ("txt", "value", "input", "content", "keys", "string", "query", "search"),
    "option": ("value", "choice", "label", "text", "item", "selection", "name"),
    "url": ("link", "href", "address", "page", "website"),
    "key": ("keys", "button", "name"),
    "answer": ("result", "output", "response", "final_answer", "text", "message"),
    "direction": ("dir", "where"),
    "seconds": ("duration", "time", "secs", "wait"),
    "reason": ("message", "why", "text"),
    "fact": ("note", "memo", "text", "message"),
    "success": ("ok", "succeeded", "completed"),
    "submit": ("enter", "press_enter"),
}
_EXAMPLE = {"integer": 3, "number": 2, "boolean": True, "string": "..."}


def _coerce(value: Any, typ: str) -> Any:
    import re as _re
    if typ == "integer":
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, (int, float)) and float(value) == int(value):
            return int(value)
        m = _re.search(r"-?\d+", str(value))
        if m:
            return int(m.group(0))
        raise ValueError
    if typ == "number":
        return float(value)
    if typ == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in ("true", "yes", "1"):
            return True
        if str(value).strip().lower() in ("false", "no", "0"):
            return False
        raise ValueError
    return value if isinstance(value, str) else str(value)


def example_call(tool: dict[str, Any]) -> str:
    import json as _json
    props = tool["input_schema"].get("properties", {})
    req = tool["input_schema"].get("required", [])
    ex = {k: (v["enum"][0] if "enum" in v else _EXAMPLE.get(v.get("type", "string"), "...")) for k, v in props.items() if k in req}
    return _json.dumps(ex)


def normalize_args(tool: dict[str, Any], args: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Return (cleaned args, None) or (args, a message telling the model exactly what to send)."""
    schema = tool["input_schema"]
    props: dict[str, Any] = schema.get("properties", {})
    required: list[str] = schema.get("required", [])
    given = dict(args or {})
    out: dict[str, Any] = {}
    for key, spec in props.items():
        if key in given:
            raw = given[key]
        else:
            alias = next((a for a in _ALIASES.get(key, ()) if a in given and a not in props), None)
            if alias is None:
                continue
            raw = given[alias]
        try:
            val = _coerce(raw, spec.get("type", "string"))
        except (ValueError, TypeError):
            return args, f'Error: {tool["name"]} needs "{key}" as {spec.get("type", "string")}, e.g. {example_call(tool)}. You sent {given}.'
        if "enum" in spec and val not in spec["enum"]:
            return args, f'Error: "{key}" must be one of {spec["enum"]}, e.g. {{"{key}": "{spec["enum"][0]}"}}.'
        out[key] = val
    missing = [k for k in required if k not in out]
    if missing:
        return args, f'Error: {tool["name"]} needs {", ".join(missing)}. Example: {tool["name"]} {example_call(tool)}. You sent {given}.'
    return out, None


def extract_text_tool_call(text: str, tools: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """Models that cannot do native tool calls often write one as text: ``{"name": "click", "parameters": {...}}``
    or ``read()``. Recover the call if (and only if) it names a real tool."""
    import json as _json
    import re as _re
    names = {t["name"] for t in tools}
    stripped = (text or "").strip()
    m = _re.fullmatch(r"(\w+)\(\s*\)", stripped)
    if m and m.group(1) in names:
        return m.group(1), {}
    dec = _json.JSONDecoder()
    for i, ch in enumerate(stripped):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(stripped[i:])
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        name = next((obj[k] for k in ("name", "tool", "function", "action") if isinstance(obj.get(k), str)), None)
        if name not in names:
            continue
        for key in ("parameters", "arguments", "input", "args", "params"):
            if isinstance(obj.get(key), dict):
                return name, dict(obj[key])
        return name, {k: v for k, v in obj.items() if k not in ("name", "tool", "function", "action")}
    return None


def looks_like_junk(text: str) -> bool:
    """Text a model produces when it is imitating the transcript instead of answering."""
    import re as _re
    return bool(
        "--- page ---" in text
        or _re.search(r"^\s*#\d+ (link|button|textbox|heading|combobox|checkbox|radio)\b", text, _re.M)
        or _re.search(r"\b(goto|click|type|select|press|scroll|back|wait|read|find|switch_tab|close_tab|remember|done)\(", text)
        or _re.search(r'\{\s*"(name|tool|function)"\s*:', text)
    )
