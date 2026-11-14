"""
Remote browsers.

A *cloud browser* is a Chromium that someone else runs and exposes over the Chrome DevTools
Protocol (CDP). Selfbrowse attaches to it with Playwright's ``connect_over_cdp`` and drives it
like a local one.

Most providers (Browserbase, Steel, Browserless, Anchor...) hand you a ``wss://`` URL: pass it
as ``Browser(cdp_url=...)`` or ``--cdp-url``. Amazon Bedrock AgentCore needs a session started
first and a signed connection; :class:`AgentCoreBrowser` does that.

A provider is any object with ``open() -> CdpTarget`` and ``close()``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class CdpTarget:
    url: str                                                    # ws:// or wss:// (or http:// for a local debug port)
    headers: dict[str, str] = field(default_factory=dict)
    live_view_url: str | None = None                            # where a person can watch, if the provider has one


class CloudBrowser(Protocol):
    def open(self) -> CdpTarget: ...
    def close(self) -> None: ...


class CloudError(RuntimeError):
    pass


class AgentCoreBrowser:
    """
    Amazon Bedrock AgentCore Browser (a managed Chromium).

    Needs ``pip install 'selfbrowse[aws]'`` and AWS credentials the usual way (environment, profile
    or role) with permission to start and stop AgentCore browser sessions.

    Args:
        region: AWS region. Default: ``AWS_REGION`` / ``AWS_DEFAULT_REGION``, else ``us-east-1``.
        identifier: the browser to use. The AWS-managed default is ``aws.browser.v1``; pass your own
            custom browser's id to get recording to S3, a VPC and so on.
        session_timeout: seconds before AWS ends the session on its own (default 900), a backstop in
            case this process dies before it can stop the session.
        client: an existing ``bedrock_agentcore`` ``BrowserClient`` (tests, custom setup).
    """

    def __init__(self, *, region: str | None = None, identifier: str = "aws.browser.v1",
                 session_timeout: int = 900, client: Any = None) -> None:
        import os
        self.region = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        self.identifier = identifier
        self.session_timeout = session_timeout
        self._client = client
        self._started = False

    def open(self) -> CdpTarget:
        if self._client is None:
            try:
                from bedrock_agentcore.tools.browser_client import BrowserClient
            except ImportError as exc:
                raise CloudError("AgentCore needs its SDK: pip install 'selfbrowse[aws]'") from exc
            self._client = BrowserClient(self.region)
        try:
            self._client.start(identifier=self.identifier, session_timeout_seconds=self.session_timeout)
            self._started = True
            url, headers = self._client.generate_ws_headers()
        except Exception as exc:
            self.close()
            raise CloudError(f"Could not start an AgentCore browser session in {self.region}: {exc}") from exc
        live = None
        try:
            live = self._client.generate_live_view_url()
        except Exception:
            pass                                                # the live view is a convenience, not a requirement
        return CdpTarget(url=url, headers=dict(headers or {}), live_view_url=live)

    def close(self) -> None:
        if self._client is not None and self._started:
            self._started = False
            try:
                self._client.stop()
            except Exception:
                pass


def make_cloud(name: str, **options: Any) -> CloudBrowser:
    """The provider called ``name`` (``"agentcore"``)."""
    if name == "agentcore":
        return AgentCoreBrowser(**{k: v for k, v in options.items() if v is not None})
    raise CloudError(f"Unknown cloud browser {name!r}. Available: agentcore.")


def remote_kwargs(*, cdp_url: str | None = None, headers: list[str] | None = None, cloud: str | None = None,
                  region: str | None = None, identifier: str | None = None) -> dict[str, Any]:
    """Keyword arguments for ``Browser`` from command-line style options (``headers`` are ``NAME=VALUE``)."""
    if not (cdp_url or cloud):
        if headers or region or identifier:
            raise CloudError("--cdp-header, --cloud-region and --cloud-browser need --cdp-url or --cloud.")
        return {}
    if cdp_url and cloud:
        raise CloudError("Use either --cdp-url or --cloud, not both.")
    parsed: dict[str, str] = {}
    for h in headers or []:
        name, sep, value = h.partition("=")
        if not sep or not name.strip():
            raise CloudError(f"--cdp-header expects NAME=VALUE, got {h!r}.")
        parsed[name.strip()] = value
    if cloud:
        if parsed:
            raise CloudError("--cdp-header goes with --cdp-url; a --cloud provider signs its own connection.")
        return {"cloud": make_cloud(cloud, region=region, identifier=identifier)}
    if region or identifier:
        raise CloudError("--cloud-region and --cloud-browser go with --cloud.")
    return {"cdp_url": cdp_url, "cdp_headers": parsed}
