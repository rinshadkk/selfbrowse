"""
Model providers.

Pass a model to ``Agent`` as a string ``"provider:model"`` or as any object implementing
the :class:`LLM` protocol::

    Agent(task, llm="anthropic:claude-haiku-4-5")
    Agent(task, llm="openai:gpt-4o-mini")
    Agent(task, llm="ollama:qwen2.5:14b")          # local, free
    Agent(task, llm="groq:llama-3.3-70b-versatile")
"""
from __future__ import annotations

from selfbrowse.llm.base import LLM, LLMError, LLMResponse

# provider → (base_url, api-key env var, key required)
_OPENAI_COMPATIBLE: dict[str, tuple[str | None, str, bool]] = {
    "openai":     (None, "OPENAI_API_KEY", True),
    "ollama":     ("http://localhost:11434/v1", "OLLAMA_API_KEY", False),
    "lmstudio":   ("http://localhost:1234/v1", "LMSTUDIO_API_KEY", False),
    "groq":       ("https://api.groq.com/openai/v1", "GROQ_API_KEY", True),
    "deepseek":   ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", True),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", True),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", True),
    "together":   ("https://api.together.xyz/v1", "TOGETHER_API_KEY", True),
}


# Local runtimes (small models, unreliable native tool calling) default to JSON-schema mode.
_JSON_MODE_DEFAULT = {"ollama", "lmstudio"}


def make_llm(spec: "str | LLM", **kwargs) -> LLM:
    """Build a model from ``"provider:model"`` (or pass an existing LLM through unchanged).

    OpenAI-compatible providers accept ``json_mode=True/False`` to force the JSON-schema action mode
    (default on for ollama and lmstudio) or native tool calling.
    """
    if not isinstance(spec, str):
        return spec
    provider, sep, model = spec.partition(":")
    if not sep or not model:
        raise LLMError(f"Model must look like 'provider:model', e.g. 'anthropic:claude-haiku-4-5' (got {spec!r}).")
    provider = provider.lower()

    if provider == "anthropic":
        from selfbrowse.llm.anthropic import AnthropicLLM
        return AnthropicLLM(model, **kwargs)
    if provider in _OPENAI_COMPATIBLE:
        from selfbrowse.llm.openai_compat import OpenAICompatLLM
        base_url, key_env, required = _OPENAI_COMPATIBLE[provider]
        kwargs.setdefault("base_url", base_url)
        kwargs.setdefault("api_key_env", key_env)
        kwargs.setdefault("require_key", required)
        kwargs.setdefault("json_mode", provider in _JSON_MODE_DEFAULT)
        return OpenAICompatLLM(model, **kwargs)
    known = ", ".join(["anthropic", *_OPENAI_COMPATIBLE])
    raise LLMError(f"Unknown provider {provider!r}. Known: {known}.")


__all__ = ["LLM", "LLMError", "LLMResponse", "make_llm"]
