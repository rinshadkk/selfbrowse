# Remote browsers

Selfbrowse can drive a browser that runs somewhere else, such as a cloud browser service, instead of
launching Chromium on your machine. It attaches over the Chrome DevTools Protocol (CDP) and uses the
browser's first tab. The agent, the model calls and the guardrails still run where you run Selfbrowse.

## Any provider that gives you a CDP URL

Browserbase, Steel, Browserless, Anchor and similar services hand you a `wss://` address:

```bash
selfbrowse --cdp-url "wss://connect.example.com?apiKey=..." "open example.com and tell me the heading"
```

- If the provider wants a header instead of a key in the URL, add `--cdp-header NAME=VALUE` (repeatable).
- `$SELFBROWSE_CDP_URL` works too, which keeps the key out of your shell history.
- A local Chrome started with `--remote-debugging-port=9222` works the same way: `--cdp-url http://localhost:9222`.

From Python:

```python
from selfbrowse import Browser, BrowseAgent

browser = Browser(cdp_url="wss://...", cdp_headers={"x-api-key": "..."})
BrowseAgent("...", llm="anthropic:claude-sonnet-5-5", browser=browser).run()
```

## Amazon Bedrock AgentCore Browser

```bash
pip install 'selfbrowse[aws]'
selfbrowse --cloud agentcore --cloud-region us-east-1 "find the cheapest mystery book on books.toscrape.com"
```

Selfbrowse starts an AgentCore browser session, connects with the signed headers AWS issues, and stops the
session when the run ends. AWS credentials come from the usual places (environment, profile or role) and need
permission to start and stop AgentCore browser sessions. The session also has a timeout (15 minutes) as a
backstop if your process dies before it can stop it.

Use `--cloud-browser ID` to run on a custom AgentCore browser (for recording to S3, a VPC and so on). The
default is the AWS-managed `aws.browser.v1`. The live-view address is printed at the end of the run, and is on
`browser.live_view_url` from Python.

!!! note "Not yet run against a real AWS account"
    The AgentCore adapter is tested against a stand-in for the AWS SDK and a local browser. Try it on a real
    account before relying on it, and please report anything that behaves differently.

## What changes with a remote browser

| | |
|---|---|
| `--record-video`, `--profile`, `--channel` | not available: the provider runs the browser. Use the provider's own session replay |
| Window size | the provider's; Selfbrowse does not resize it |
| Hand-off to a person | off unless you pass your own `handoff=` handler: there is no window of yours to hand over. Use the provider's live view |
| Closing | Selfbrowse disconnects and leaves the remote browser's own tab and cookies alone |
| Speed | each step adds network round trips between you and the browser |
