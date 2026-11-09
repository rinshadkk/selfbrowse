"""Watch steps as they happen and inspect the result.

    python examples/11_progress_and_results.py
"""
import json

from selfbrowse import BrowseAgent, Step


def on_step(step: Step) -> None:
    tag = " (learned)" if step.from_cache else ""
    print(f"{step.number:>2}. {step.tool} {json.dumps(step.input)[:70]}{tag}")


result = BrowseAgent("Open example.com and tell me the heading.", llm="anthropic:claude-haiku-4-5",
               on_step=on_step, learn=False).run()

print("success:", result.success)
print("answer: ", result.output)
print("error:  ", result.error)
u = result.usage
print(f"usage:   {u.calls} calls, {u.total_input} in ({u.cache_read_tokens} cached), {u.output_tokens} out")
print(json.dumps(result.to_dict()["history"][0], indent=2)[:300])
