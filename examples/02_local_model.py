"""Run on a local model (Ollama). Small and "thinking" models need a little help.

    ollama pull qwen3.6
    python examples/02_local_model.py
"""
from selfbrowse import Agent
from selfbrowse.llm import make_llm

# Native tool calling vs JSON-schema mode. Native plus Selfbrowse's argument repair did better
# in our benchmarks (see benchmarks/compare/results), so ask for it explicitly:
llm = make_llm("ollama:qwen3.6", json_mode=False)

result = Agent(
    "Open news.ycombinator.com and tell me the title of the top story.",
    llm=llm,
    max_steps=30,               # weak models wander; give them room
    max_output_tokens=4096,     # reasoning models can spend 2,000+ tokens thinking before they act
    page_text=600,              # send on-screen text with the page list: fewer `read` calls
).run()

print(result.output if result.success else f"FAILED: {result.error}")
