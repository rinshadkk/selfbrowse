"""See exactly what is sent to the model, and keep a record of every run.

    python examples/08_tracing.py
    selfbrowse trace list
    selfbrowse trace show latest --full
"""
import re

from selfbrowse import Agent

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def show_request(*, system, messages, tools, n):
    print(f"[model call {n}: {len(messages)} messages, {len(tools)} tools]")


result = Agent(
    "Open example.com and tell me the heading.",
    llm="anthropic:claude-haiku-4-5",
    trace=True,                                       # JSON lines in ~/.selfbrowse/traces (or pass a folder)
    show_prompts=False,                               # True prints every request to stderr
    trace_content=True,                               # False stores sizes and hashes instead of text
    redact_trace=lambda text: EMAIL.sub("<email>", text),   # scrub anything written to the trace
    on_llm_request=show_request,                      # called before every model call
    # otel="http://localhost:4318",                   # also export spans (pip install 'selfbrowse[otel]')
).run()
print(result.output)
