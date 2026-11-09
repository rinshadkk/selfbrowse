"""Log in without the model ever seeing the password.

The model writes <secret:NAME>; Selfbrowse swaps in the real value only when typing.
Secrets never enter the prompt, the history or the trace.

    SITE_PASSWORD='...' python examples/03_secrets.py
"""
import os

from selfbrowse import BrowseAgent

result = BrowseAgent(
    "Open https://example.com/login, sign in as demo@example.com using <secret:password>, "
    "and tell me the name shown on the account page.",
    llm="anthropic:claude-haiku-4-5",
    sensitive={"password": os.environ["SITE_PASSWORD"]},
).run()
print(result.output)
