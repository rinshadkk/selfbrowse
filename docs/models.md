# Models

Use `provider:model`:

| Provider | Example |
|---|---|
| `anthropic` | `anthropic:claude-haiku-4-5` (prompt caching on) |
| `openai` | `openai:gpt-4o-mini` |
| `ollama` | `ollama:qwen3.6:latest` (local; the model must support tool calling) |
| `lmstudio` | `lmstudio:<model>` |
| `groq`, `deepseek`, `gemini`, `openrouter`, `together` | `groq:llama-3.3-70b-versatile` |

Your own provider (Azure OpenAI, AWS Bedrock, an internal gateway) works too; see [Bring your own model](#bring-your-own-model).

### Bring your own model

Any provider works if you give Selfbrowse an object with a `model` name and a `complete(system=, messages=, tools=, max_tokens=)` method that returns an `LLMResponse`. Messages and tools arrive as Anthropic-style blocks, so you translate to and from your SDK.

If your SDK speaks the OpenAI chat format (Azure OpenAI, and other OpenAI-compatible services), reuse the built-in translation:

```python
# my_llm.py
from openai import AzureOpenAI
from selfbrowse.llm.openai_compat import messages_to_openai, tools_to_openai, response_from_openai

class AzureLLM:
    model = "my-gpt4o-deployment"            # shown in traces

    def __init__(self):
        self.client = AzureOpenAI(azure_endpoint="https://RESOURCE.openai.azure.com",
                                  api_key="...", api_version="2024-10-21")

    def complete(self, *, system, messages, tools, max_tokens=2048):
        resp = self.client.chat.completions.create(
            model=self.model, max_tokens=max_tokens,
            messages=messages_to_openai(system, messages),
            tools=tools_to_openai(tools),
        )
        return response_from_openai(resp)
```

Use it from Python, the command line or the MCP server:

```python
BrowseAgent("task", llm=AzureLLM()).run()          # an object
BrowseAgent("task", llm="my_llm:AzureLLM").run()   # the same, by name
```

```bash
selfbrowse --model my_llm:AzureLLM "task"          # a module on your path, or in the folder you run from
selfbrowse --model ./my_llm.py:AzureLLM "task"     # or a file
selfbrowse-mcp --model ./my_llm.py:AzureLLM
```

The name after the colon can be a class (created with no arguments), a function that returns a model, or a ready object. Any `provider:` that is not built in is looked up this way, so a mistyped provider says so instead of failing quietly.

For a service with its own format (AWS Bedrock's Converse API, Vertex, an internal gateway), build the `LLMResponse` yourself: `content` is a list of `{"type": "text", "text": ...}` and `{"type": "tool_use", "id", "name", "input"}` blocks, `stop_reason` is `"tool_use"` or `"end_turn"`, and `usage` is a `selfbrowse.types.Usage` with your token counts so traces and budgets work. `selfbrowse/llm/base.py` has the full interface.

These routes are tested with a fake model. They have not been run against live Azure or AWS accounts.
