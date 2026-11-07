"""Claude through the Anthropic API, with prompt caching on the stable prefix."""
from __future__ import annotations

import os
from typing import Any

from selfbrowse.llm.base import LLMError, LLMResponse
from selfbrowse.types import Usage


class AnthropicLLM:
    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        cache: bool = True,
    ) -> None:
        import anthropic

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("ANTHROPIC_API_KEY is not set (or pass api_key=...).")
        self.model = model
        self._cache = cache
        self._client = anthropic.Anthropic(api_key=key, base_url=base_url) if base_url else anthropic.Anthropic(api_key=key)

    def complete(
        self,
        *,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        system_blocks = []
        for block in system:
            item: dict[str, Any] = {"type": "text", "text": block["text"]}
            if self._cache and block.get("cache"):
                item["cache_control"] = {"type": "ephemeral"}
            system_blocks.append(item)

        tool_defs = [dict(t) for t in tools]
        if self._cache and tool_defs:
            tool_defs[-1]["cache_control"] = {"type": "ephemeral"}      # caches tools + the stable system prefix

        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_blocks,
            tools=tool_defs,
            messages=messages,
        )

        content: list[dict[str, Any]] = []
        for block in resp.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input or {})})

        u = resp.usage
        return LLMResponse(
            content=content,
            stop_reason=resp.stop_reason or "end_turn",
            usage=Usage(
                input_tokens=getattr(u, "input_tokens", 0) or 0,
                output_tokens=getattr(u, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
                calls=1,
            ),
        )
