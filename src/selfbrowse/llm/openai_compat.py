"""
Any OpenAI-compatible chat endpoint: OpenAI itself, Ollama, LM Studio, Groq, DeepSeek,
Gemini's compatibility layer, OpenRouter, Together, vLLM, ...

The translation functions are pure (no network) so they are unit-tested directly.
"""
from __future__ import annotations

import json
import os
from typing import Any

from selfbrowse.llm.base import LLMError, LLMResponse
from selfbrowse.types import Usage


# ── translation ────────────────────────────────────────────────────────────────────

def tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _image_url(block: dict[str, Any]) -> dict[str, Any]:
    src = block["source"]
    return {"type": "image_url", "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}}


def messages_to_openai(system: list[dict[str, Any]], messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic-style blocks → chat-completions messages."""
    out: list[dict[str, Any]] = []
    sys_text = "\n\n".join(b["text"] for b in system if b.get("text"))
    if sys_text:
        out.append({"role": "system", "content": sys_text})

    for msg in messages:
        content = msg["content"]
        if isinstance(content, str):
            out.append({"role": msg["role"], "content": content})
            continue

        if msg["role"] == "assistant":
            text = "".join(b.get("text", "") for b in content if b["type"] == "text")
            calls = [
                {"id": b["id"], "type": "function",
                 "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))}}
                for b in content if b["type"] == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
            continue

        # user turn: tool results become `tool` messages; text/images stay a user message
        pending_images: list[dict[str, Any]] = []
        user_parts: list[dict[str, Any]] = []
        for b in content:
            if b["type"] == "tool_result":
                inner = b.get("content", "")
                if isinstance(inner, list):
                    text = "\n".join(p.get("text", "") for p in inner if p.get("type") == "text")
                    pending_images += [_image_url(p) for p in inner if p.get("type") == "image"]
                else:
                    text = str(inner)
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": text or "(no output)"})
            elif b["type"] == "text":
                user_parts.append({"type": "text", "text": b["text"]})
            elif b["type"] == "image":
                user_parts.append(_image_url(b))
        # The `tool` role cannot carry images, so they follow as a user message.
        parts = user_parts + ([{"type": "text", "text": "Screenshot:"}] + pending_images if pending_images else [])
        if parts:
            out.append({"role": "user", "content": parts})
    return out


_FINISH = {"tool_calls": "tool_use", "function_call": "tool_use", "stop": "end_turn", "length": "max_tokens"}


def response_from_openai(resp: Any) -> LLMResponse:
    choice = resp.choices[0]
    msg = choice.message
    content: list[dict[str, Any]] = []
    if msg.content:
        content.append({"type": "text", "text": msg.content})
    for call in getattr(msg, "tool_calls", None) or []:
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        content.append({"type": "tool_use", "id": call.id, "name": call.function.name, "input": args})

    u = getattr(resp, "usage", None)
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    prompt = getattr(u, "prompt_tokens", 0) or 0
    stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else _FINISH.get(choice.finish_reason or "stop", "end_turn")
    return LLMResponse(
        content=content,
        stop_reason=stop,
        usage=Usage(
            input_tokens=max(prompt - cached, 0),
            output_tokens=getattr(u, "completion_tokens", 0) or 0,
            cache_read_tokens=cached,
            calls=1,
        ),
    )


# ── JSON-schema mode ─────────────────────────────────────────────────────────────────
# Small local models are unreliable at native tool calling: they write the call as text, invent tool
# names, or use the wrong argument names. In this mode there are no tools at all. The server is asked for
# one JSON object that must match a schema (constrained decoding), so the reply can only be a valid action.
#
#   {"thought": "<short>", "tool": "click", "ref": 3}

def action_schema(tools: list[dict[str, Any]], thought: bool = True) -> dict[str, Any]:
    """One flat schema: a ``tool`` name plus every argument any tool takes (all optional)."""
    props: dict[str, Any] = {}
    if thought:
        props["thought"] = {"type": "string"}
    props["tool"] = {"type": "string", "enum": [t["name"] for t in tools]}
    for t in tools:
        for key, spec in t.get("input_schema", {}).get("properties", {}).items():
            props.setdefault(key, {k: v for k, v in spec.items() if k != "description"})
    return {"type": "object", "properties": props, "required": (["thought"] if thought else []) + ["tool"],
            "additionalProperties": False}


def json_mode_instructions(tools: list[dict[str, Any]], thought: bool = True) -> str:
    lines = ['Reply with ONE JSON object and nothing else: '
             + ('{"thought": "<one short sentence>", ' if thought else '{') + '"tool": "<name>", <arguments>}.', "Tools:"]
    for t in tools:
        props = t.get("input_schema", {}).get("properties", {})
        req = set(t.get("input_schema", {}).get("required", []))
        args = ", ".join(f'{k}: {v.get("type", "string")}{"" if k in req else "?"}' for k, v in props.items())
        lines.append(f'- {t["name"]}({args}) — {t.get("description", "")}')
    return "\n".join(lines)


def messages_to_openai_json(system: list[dict[str, Any]], messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """History for JSON mode: past actions become the JSON the model wrote, results become user text."""
    out: list[dict[str, Any]] = []
    sys_text = "\n\n".join(b["text"] for b in system if b.get("text"))
    if sys_text:
        out.append({"role": "system", "content": sys_text})
    for msg in messages:
        content = msg["content"]
        if isinstance(content, str):
            out.append({"role": msg["role"], "content": content})
        elif msg["role"] == "assistant":
            thought = "".join(b.get("text", "") for b in content if b["type"] == "text").strip()
            use = next((b for b in content if b["type"] == "tool_use"), None)
            if use is not None:
                obj = ({"thought": thought} if thought else {}) | {"tool": use["name"]} | dict(use.get("input", {}))
                out.append({"role": "assistant", "content": json.dumps(obj, ensure_ascii=False)})
            else:
                out.append({"role": "assistant", "content": thought or "(no output)"})
        else:
            texts = []
            for b in content:
                if b["type"] == "tool_result":
                    inner = b.get("content", "")
                    texts.append("\n".join(p.get("text", "") for p in inner if p.get("type") == "text") if isinstance(inner, list) else str(inner))
                elif b["type"] == "text":
                    texts.append(b["text"])
            out.append({"role": "user", "content": "\n".join(t for t in texts if t) or "(no output)"})
    return out


def response_from_json(resp: Any, tools: list[dict[str, Any]]) -> LLMResponse:
    choice = resp.choices[0]
    raw = (choice.message.content or "").strip()
    u = getattr(resp, "usage", None)
    usage = Usage(
        input_tokens=getattr(u, "prompt_tokens", 0) or 0, output_tokens=getattr(u, "completion_tokens", 0) or 0, calls=1)
    names = {t["name"] for t in tools}
    try:
        obj = json.loads(raw)
        tool = obj.pop("tool")
        if tool not in names:
            raise ValueError(tool)
        thought = str(obj.pop("thought", "") or "")
        allowed = set(next(t for t in tools if t["name"] == tool).get("input_schema", {}).get("properties", {}))
        args = {k: v for k, v in obj.items() if k in allowed}
    except (ValueError, KeyError, TypeError, AttributeError):
        return LLMResponse(content=[{"type": "text", "text": raw}], stop_reason="end_turn", usage=usage)
    content: list[dict[str, Any]] = ([{"type": "text", "text": thought}] if thought else [])
    content.append({"type": "tool_use", "id": f"call_{abs(hash(raw)) % 10**8}", "name": tool, "input": args})
    return LLMResponse(content=content, stop_reason="tool_use", usage=usage)


# ── adapter ──────────────────────────────────────────────────────────────────────────

class OpenAICompatLLM:
    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        require_key: bool = True,
        json_mode: bool = False,
        json_thought: bool = True,
    ) -> None:
        import openai

        key = api_key or os.environ.get(api_key_env) or ("not-needed" if not require_key else None)
        if not key:
            raise LLMError(f"{api_key_env} is not set (or pass api_key=...).")
        self.model = model
        self.json_mode, self.json_thought = json_mode, json_thought
        self._client = openai.OpenAI(api_key=key, base_url=base_url)

    def complete(
        self,
        *,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if self.json_mode:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages_to_openai_json(
                    [*system, {"text": json_mode_instructions(tools, self.json_thought)}], messages),
                response_format={"type": "json_schema", "json_schema": {
                    "name": "action", "schema": action_schema(tools, self.json_thought), "strict": True}},
                max_tokens=max_tokens,
            )
            return response_from_json(resp, tools)
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages_to_openai(system, messages),
            tools=tools_to_openai(tools) or None,
            max_tokens=max_tokens,
        )
        return response_from_openai(resp)
