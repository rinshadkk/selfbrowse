# Security policy

## Reporting a vulnerability

Please do not open a public issue. [Report it privately on GitHub](https://github.com/rinshadkk/selfbrowse/security/advisories/new).

Say what you did, what happened, what you expected, and the version (`selfbrowse --version`). A small page or script
that shows the problem helps most. Remove real passwords, keys and personal data first.

Selfbrowse has one maintainer, so there is no guaranteed response time. You will be told whether the report is
confirmed, and credited in the fix if you wish.

## Supported versions

Fixes go into the latest release on [PyPI](https://pypi.org/project/selfbrowse/). Older releases are not patched.

## What counts

- A secret or masked personal value reaching the model, a trace, a log or a saved flow.
- A secret typed on a site it is not tied to.
- A way past a guardrail, such as reaching a site outside the allowed list or a risky action without confirmation.
- Page content that makes Selfbrowse itself run code or read local files.
- Problems in the desktop app or the MCP server that expose data or control to another program or website.

## Known limits

A model can be persuaded by text on a page. The injection watch matches known patterns and will miss others, so use
domain limits and confirmation on sites you do not control. A new wording that the watch misses is welcome as an
ordinary issue; getting past a domain limit or confirmation is a vulnerability. See
[Guardrails](https://selfbrowse.ai/docs/guardrails/) for what each protection covers.
