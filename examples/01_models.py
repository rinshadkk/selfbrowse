"""Pick a model. Any "provider:model" works; the rest of your code stays the same.

    python examples/01_models.py anthropic:claude-haiku-4-5
    python examples/01_models.py ollama:qwen3.6
    python examples/01_models.py openai:gpt-4o-mini
"""
import sys

from selfbrowse import BrowseAgent

model = sys.argv[1] if len(sys.argv) > 1 else "anthropic:claude-haiku-4-5"

result = BrowseAgent("Open news.ycombinator.com and tell me the title of the top story.", llm=model).run()
print(result.output)
print(f"{result.steps} steps, {result.usage.calls} model calls, {result.usage.total_input} input tokens")

# Other providers use the same form and read their key from the environment:
#   "openai:gpt-4o-mini"   OPENAI_API_KEY        "groq:llama-3.3-70b-versatile"  GROQ_API_KEY
#   "gemini:gemini-2.0-flash"  GEMINI_API_KEY    "openrouter:meta-llama/llama-3.3-70b-instruct"
#   "ollama:<name>" and "lmstudio:<name>" run on your own machine and need no key.
