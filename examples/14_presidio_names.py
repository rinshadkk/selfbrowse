"""Mask names and other personal data with Microsoft Presidio, on your own machine.

One-time setup:
    pip install 'selfbrowse[presidio]'
    python -m spacy download en_core_web_sm        # or en_core_web_lg: slower, finds more names

Run (no model key needed; this uses a scripted model and a local page, so you can see what is masked):
    python examples/14_presidio_names.py
"""
import tempfile
from pathlib import Path

from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import PresidioRedact, RedactPII

PAGE = """<!doctype html><title>Account</title>
<h1>Account</h1>
<p>Hello Priya Raman, your email is priya.raman@acme.com. Card on file: 4111 1111 1111 1111.</p>
<button>Continue</button>"""


class Script:
    """Reads the page, then finishes. It records what the 'model' was actually shown."""
    model = "scripted"

    def __init__(self):
        self.calls, self.seen = [("read", {}), ("done", {"answer": "ok", "success": True})], []

    def complete(self, *, system, messages, tools, max_tokens=2048):
        from selfbrowse.llm.base import LLMResponse
        from selfbrowse.types import Usage
        self.seen.append(str(messages[-1]))
        name, args = self.calls.pop(0)
        return LLMResponse(content=[{"type": "tool_use", "id": f"t{len(self.seen)}", "name": name, "input": args}],
                           stop_reason="tool_use", usage=Usage(input_tokens=1, output_tokens=1, calls=1))


page = Path(tempfile.mkdtemp()) / "account.html"
page.write_text(PAGE)

for label, guards in [
    ("RedactPII only (regex: no names)", [RedactPII()]),
    ("PresidioRedact (names too)", [PresidioRedact()]),
    ("PresidioRedact, only emails", [PresidioRedact(["EMAIL_ADDRESS"])]),
]:
    llm = Script()
    with Browser() as browser:
        browser.goto(page.as_uri())
        BrowseAgent("read the page", llm=llm, browser=browser, guardrails=guards, safe_urls=False, learn=False).run()
    shown = llm.seen[1]
    print(f"\n{label}\n  Priya Raman visible: {'Priya' in shown}   email visible: {'acme.com' in shown}")

# On the command line:
#   selfbrowse --redact-presidio "task"
#   selfbrowse --redact-presidio --presidio-entities PERSON,EMAIL_ADDRESS,LOCATION "task"
#   selfbrowse --redact-presidio --presidio-model en_core_web_lg "task"
