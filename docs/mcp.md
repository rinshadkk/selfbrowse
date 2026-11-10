# Use it from Claude, VS Code and other MCP clients

Selfbrowse can run as an [MCP](https://modelcontextprotocol.io) server, so an assistant can use it as its browser:

```bash
pip install 'selfbrowse[mcp]'
playwright install chromium
```

It offers two kinds of tools:

- **`browse(task)`** (task mode). Selfbrowse runs its own model loop and returns only the answer, so the assistant never reads the pages. This is where most of the token saving is. It needs `--model`, for example `ollama:qwen3.6` (free, local) or `anthropic:claude-haiku-4-5`.
- **`browser_snapshot`, `browser_click`, `browser_type`, `browser_select`, `browser_goto`, `browser_read`, `browser_find`, `browser_scroll`, `browser_press`, `browser_back`, `browser_switch_tab`, `browser_close_tab`** (step mode). The assistant drives the browser and reads Selfbrowse's short numbered list instead of a screenshot. No model is needed on the server. We have not measured how this compares with other browser tools.

**VS Code** (Copilot agent mode): add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "selfbrowse": {
      "command": "selfbrowse-mcp",
      "args": ["--model", "ollama:qwen3.6", "--headed", "--channel", "chrome", "--allow-domain", "example.com"]
    }
  }
}
```

**Claude Code:** `claude mcp add selfbrowse -- selfbrowse-mcp --model ollama:qwen3.6 --headed`

**Claude Desktop** (`claude_desktop_config.json`): `{"mcpServers": {"selfbrowse": {"command": "selfbrowse-mcp", "args": ["--model", "ollama:qwen3.6"]}}}`

Client config formats change between versions, so check your client's MCP docs if one of these is rejected.

Things to know:

- **Guardrails apply.** Use `--allow-domain`, `--block-domain`, `--block-risky`, `--redact-pii`, `--redact-presidio` (with `--presidio-entities` and `--presidio-model`), `--watch-injection`, `--max-tokens` and `--max-seconds`. There is nobody to ask in a terminal, so a risky click is refused, not confirmed; your client's own tool-approval prompt is a second check.
- **No terminal hand-off.** Stdout carries the protocol. When a CAPTCHA or login needs a person, the tool result says so; start the server with `--headed` so there is a window to finish it in.
- **Secrets:** set `SELFBROWSE_SECRET_<name>` in the server's environment; the assistant writes `<secret:name>` and never sees the value.
- **One browser per server.** Task mode and step mode share it, so a `browse` run starts from the page your step tools left open.
- Only `mcp` 2.x was tested. Selfbrowse also tries the 1.x import, but that path is untested.
