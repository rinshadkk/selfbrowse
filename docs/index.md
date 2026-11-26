# Selfbrowse

A small, open-source browser agent for Python. You describe a task in plain language and it drives a real browser to do it.

Instead of screenshots or raw HTML, the model reads each page as a short numbered list of what can be clicked or typed into. Selfbrowse remembers what worked on each site, so it can replay some clicks on a later visit without asking the model.

```bash
selfbrowse "Find the price of the Pixel 9 on example.com and tell me"
```

```python
from selfbrowse import BrowseAgent

result = BrowseAgent("Find the price of the Pixel 9 on example.com").run()
print(result.output)
```

!!! note "Early release"
    This is version 0.3. Install it with `pip install selfbrowse`; see [Get started](getting-started.md).

## Start here

| If you want to | Read |
|---|---|
| Install it and run a first task | [Get started](getting-started.md) |
| Look up a command line option | [Command line reference](cli.md) |
| See every feature and where it is explained | [Features](features.md) |
| Use it from Claude, VS Code or another MCP client | [MCP server](mcp.md) |
| Keep it safe on sites you do not control | [Guardrails](guardrails.md) |
| Understand how the parts fit together | [Architecture](architecture.md) |
