"""
Model providers.

Pass a model to ``BrowseAgent`` as a string ``"provider:model"`` or as any object implementing
the :class:`LLM` protocol::

    BrowseAgent(task, llm="anthropic:claude-haiku-4-5")
    BrowseAgent(task, llm="openai:gpt-4o-mini")
    BrowseAgent(task, llm="ollama:qwen2.5:14b")          # local, free
    BrowseAgent(task, llm="groq:llama-3.3-70b-versatile")
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

    Your own model: ``"my_package.my_module:MyLLM"`` or ``"./my_llm.py:MyLLM"``. The name after the
    colon is a class (created with no arguments), a function that returns a model, or a ready model
    object. Any provider that is not built in is looked up this way.
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
    return _load_custom(spec, **kwargs)


def _load_custom(spec: str, **kwargs) -> LLM:
    """Import ``module:Name`` or ``path/to/file.py:Name`` and turn it into a model."""
    import importlib
    import importlib.util
    import inspect
    import sys
    from pathlib import Path

    target, _, name = spec.rpartition(":")
    known = ", ".join(["anthropic", *_OPENAI_COMPATIBLE])
    hint = f"Built in: {known}. For your own model use 'module:Name' or 'path/to/file.py:Name'."
    if not target or not name:
        raise LLMError(f"Unknown model {spec!r}. {hint}")
    try:
        if target.endswith(".py"):
            path = Path(target).expanduser()
            if not path.is_file():
                raise LLMError(f"No such file {target!r} for model {spec!r}.")
            modspec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(modspec)
            sys.path.insert(0, str(path.resolve().parent))
            try:
                modspec.loader.exec_module(module)
            finally:
                sys.path.pop(0)
        else:
            if "" not in sys.path and str(Path.cwd()) not in sys.path:
                sys.path.insert(0, str(Path.cwd()))     # like `python -m`: your module next to where you run
            module = importlib.import_module(target)
    except LLMError:
        raise
    except ModuleNotFoundError as exc:
        if exc.name and target.split(".")[0] == exc.name:
            raise LLMError(f"Unknown provider or module {target!r} in {spec!r}. {hint}") from exc
        raise LLMError(f"Importing {target!r} failed: {exc}") from exc
    except Exception as exc:
        raise LLMError(f"Importing {target!r} failed: {type(exc).__name__}: {exc}") from exc
    if not hasattr(module, name):
        raise LLMError(f"{target!r} has no {name!r}.")
    obj = getattr(module, name)
    try:
        if inspect.isclass(obj) or (callable(obj) and not hasattr(obj, "complete")):
            obj = obj(**kwargs)                     # a class, or a function that builds the model
    except Exception as exc:
        raise LLMError(f"Creating the model {spec!r} failed: {type(exc).__name__}: {exc}") from exc
    if not callable(getattr(obj, "complete", None)):
        raise LLMError(f"{spec!r} is not a model: it needs a complete(system=, messages=, tools=, max_tokens=) method.")
    if not hasattr(obj, "model"):
        try:
            obj.model = name
        except Exception:
            pass
    return obj


__all__ = ["LLM", "LLMError", "LLMResponse", "make_llm"]
