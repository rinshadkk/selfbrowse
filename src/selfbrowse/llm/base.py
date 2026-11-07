"""
The model interface.

Internally everything uses Anthropic-style content blocks, because they express tool use
and tool results cleanly::

    assistant: [{"type": "text", "text": ...}, {"type": "tool_use", "id", "name", "input"}]
    user:      [{"type": "tool_result", "tool_use_id", "content": [{"type": "text", ...}]}]

Each provider adapter translates to and from its own wire format.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from selfbrowse.types import Usage


@dataclass
class LLMResponse:
    content: list[dict[str, Any]]       # text and tool_use blocks
    stop_reason: str                    # "tool_use" | "end_turn" | "max_tokens"
    usage: Usage


@runtime_checkable
class LLM(Protocol):
    model: str

    def complete(
        self,
        *,
        system: list[dict[str, Any]],      # [{"text": str, "cache": bool}] — cache marks a stable prefix
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],       # [{"name", "description", "input_schema"}]
        max_tokens: int = 2048,
    ) -> LLMResponse: ...


class LLMError(RuntimeError):
    """A model call failed in a way the caller should see."""
