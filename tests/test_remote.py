"""Remote browsers: attach over CDP, and the AgentCore adapter (against a fake SDK)."""
import socket
import subprocess
import sys
import urllib.request

import pytest

from selfbrowse import Browser
from selfbrowse.browser import BrowserError
from selfbrowse.cloud import AgentCoreBrowser, CdpTarget, CloudError, remote_kwargs


_HOLDER = """
import sys, time
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    pw.chromium.launch(headless=True, args=["--remote-debugging-port=" + sys.argv[1]]).new_page()
    print("ready", flush=True)
    time.sleep(300)
"""


@pytest.fixture
def chrome_cdp():
    """A Chromium run by a separate process with a debugging port, standing in for a provider's browser.
    (Started through Playwright so it gets the flags a bare Chromium needs to reach the network.)"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-c", _HOLDER, str(port)], stdout=subprocess.PIPE, text=True)
    try:
        if proc.stdout.readline().strip() != "ready":
            pytest.skip("could not start Chromium with a debugging port")
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.browser
def test_attaches_over_cdp_and_leaves_the_browser_running(chrome_cdp, site):
    with Browser(cdp_url=chrome_cdp) as b:
        b.goto(site("profile.html"))
        assert b.snapshot().elements
    # the remote browser survives our disconnect, and we can attach again
    with Browser(cdp_url=chrome_cdp) as b2:
        assert b2.snapshot() is not None
    assert urllib.request.urlopen(chrome_cdp + "/json/version", timeout=2).status == 200


class FakeClient:
    def __init__(self, ws):
        self.ws, self.calls = ws, []

    def start(self, **kw):
        self.calls.append(("start", kw))

    def generate_ws_headers(self):
        self.calls.append(("headers",))
        return self.ws, {"X-Test": "signed"}

    def generate_live_view_url(self, **kw):
        return "https://live.example/view"

    def stop(self):
        self.calls.append(("stop",))


@pytest.mark.browser
def test_agentcore_session_is_started_used_and_stopped(chrome_cdp, site):
    client = FakeClient(chrome_cdp)
    cloud = AgentCoreBrowser(region="eu-west-1", client=client)
    with Browser(cloud=cloud) as b:
        b.goto(site("profile.html"))
        assert b.snapshot().elements
        assert b.live_view_url == "https://live.example/view"
    names = [c[0] for c in client.calls]
    assert names == ["start", "headers", "stop"]
    assert client.calls[0][1]["identifier"] == "aws.browser.v1"


def test_agentcore_session_is_stopped_if_the_connection_fails():
    client = FakeClient("ws://127.0.0.1:1/devtools/browser/none")
    with pytest.raises(BrowserError, match="remote browser"):
        Browser(cloud=AgentCoreBrowser(client=client)).start()
    assert ("stop",) in client.calls


def test_agentcore_start_failure_is_a_clear_error():
    class Broken(FakeClient):
        def start(self, **kw):
            raise RuntimeError("AccessDenied")
    with pytest.raises(BrowserError, match="AccessDenied"):
        Browser(cloud=AgentCoreBrowser(region="us-west-2", client=Broken("x"))).start()


def test_missing_sdk_says_how_to_install(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("bedrock_agentcore"):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(CloudError, match=r"selfbrowse\[aws\]"):
        AgentCoreBrowser().open()


def test_options_that_make_no_sense_remotely_are_rejected(tmp_path):
    for kw in ({"record_video_dir": tmp_path}, {"user_data_dir": tmp_path}, {"channel": "chrome"}):
        with pytest.raises(BrowserError, match="remote browser"):
            Browser(cdp_url="ws://x", **kw)
    with pytest.raises(BrowserError, match="not both"):
        Browser(cdp_url="ws://x", cloud=AgentCoreBrowser(client=FakeClient("x")))


def test_remote_kwargs():
    assert remote_kwargs() == {}
    assert remote_kwargs(cdp_url="wss://p", headers=["X-Key=a=b"]) == {"cdp_url": "wss://p", "cdp_headers": {"X-Key": "a=b"}}
    assert isinstance(remote_kwargs(cloud="agentcore", region="us-east-1")["cloud"], AgentCoreBrowser)
    for bad in ({"headers": ["nokey"], "cdp_url": "ws://x"}, {"region": "us-east-1"}, {"cdp_url": "ws://x", "cloud": "agentcore"},
                {"cloud": "agentcore", "headers": ["A=b"]}, {"cloud": "nope"}):
        with pytest.raises(CloudError):
            remote_kwargs(**bad)


def test_cloud_target_defaults():
    t = CdpTarget(url="wss://x")
    assert t.headers == {} and t.live_view_url is None
