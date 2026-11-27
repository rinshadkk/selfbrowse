"""Stealth mode renames a headless browser's user agent. The brand headers and the brand list pages read must
survive that: a browser that calls itself Chrome but sends none of them contradicts itself."""
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from selfbrowse import Browser

pytestmark = pytest.mark.browser

SEEN = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/favicon.ico":
            SEEN.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.end_headers()
        self.wfile.write(b'<title>t</title><a href="/second" target="_blank">open</a>')

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    s = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    SEEN.clear()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()
    s.server_close()


@pytest.fixture
def stealth_without_patchright(monkeypatch):
    """The renaming is Selfbrowse's own code, so it can be checked on plain Playwright (CI has no Patchright)."""
    import playwright.sync_api
    monkeypatch.setitem(sys.modules, "patchright.sync_api", playwright.sync_api)


BRANDS = "() => navigator.userAgentData.brands.map(b => b.brand)"


def test_stealth_keeps_the_brand_headers(server, stealth_without_patchright):
    with Browser(stealth=True) as b:
        assert len(b.page.context.pages) == 1 and b.page.url == "about:blank"     # nothing left behind
        b.goto(server + "/first")
        path, headers = SEEN[0]
        assert "HeadlessChrome" not in headers["user-agent"]
        assert "Chrom" in headers["sec-ch-ua"] and "Headless" not in headers["sec-ch-ua"]
        assert headers["sec-ch-ua-platform"].strip('"')
        brands = b.page.evaluate(BRANDS)
        assert brands and not any("Headless" in name for name in brands)
        assert b.page.evaluate("history.length") <= 2                              # the page itself, after about:blank


def test_a_new_tab_has_the_same_brands(server, stealth_without_patchright):
    with Browser(stealth=True) as b:
        b.goto(server + "/first")
        first = b.page.evaluate(BRANDS)
        with b.page.context.expect_page() as opened:
            b.page.click("text=open")
        opened.value.wait_for_load_state()
        b.page.reload()                                                            # a tab's own first request may race
        assert SEEN[-1][0] == "/second" and "sec-ch-ua" in SEEN[-1][1]
        assert b.page.evaluate(BRANDS) == first


def test_stealth_leaves_no_probe_video(server, stealth_without_patchright, tmp_path):
    with Browser(stealth=True, record_video_dir=tmp_path) as b:
        b.goto(server + "/first")
    assert len(b.video_paths()) == 1 and len(list(tmp_path.glob("*.webm"))) == 1
