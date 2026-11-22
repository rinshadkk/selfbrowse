"""An allow list must stop a click or a form post before the request is made, not after the page has loaded."""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import AllowedDomains, BlockedDomains
from tests.conftest import ScriptedLLM
from tests.test_browser_tools import ref_of

pytestmark = pytest.mark.browser
DONE = ("done", {"success": True, "answer": "ok"})


@pytest.fixture()
def trap_site():
    """The page is on 127.0.0.1; its link and form lead to the same server under the name localhost, which a browser
    treats as another site. ``hits`` records every request the server receives."""
    hits: list[str] = []
    port_box: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            p = port_box[0]
            body = (f'<a href="http://localhost:{p}/trap?from=link">Live price</a>'
                    f'<form action="http://localhost:{p}/trap" method="get"><input name="email" aria-label="Email">'
                    f'<button>Check</button></form>' if self.path == "/" else "<p>trap</p>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    port_box.append(srv.server_port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/", hits
    srv.shutdown()


def traps(hits):
    return [h for h in hits if h.startswith("/trap")]


def test_a_click_to_a_disallowed_site_is_stopped_before_the_request(trap_site, tmp_path):
    url, hits = trap_site
    with Browser() as b:
        b.goto(url)
        ref = ref_of(b.snapshot().text, "Live price")
        llm = ScriptedLLM([("click", {"ref": ref}), DONE])
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[AllowedDomains(["127.0.0.1"])]).run()
        assert "127.0.0.1" in b.url
    assert traps(hits) == []                                        # the server never saw the request
    assert "Blocked by guardrail AllowedDomains" in res.history[0].result
    assert "The page was not opened" in res.history[0].result


def test_a_form_post_to_a_disallowed_site_never_leaves(trap_site, tmp_path):
    url, hits = trap_site
    with Browser() as b:
        b.goto(url)
        snap = b.snapshot().text
        llm = ScriptedLLM([("type", {"ref": ref_of(snap, "Email"), "text": "a@example.com"}),
                           ("click", {"ref": ref_of(snap, "Check")}), DONE])
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[AllowedDomains(["127.0.0.1"])]).run()
    assert traps(hits) == []                                        # the email was not sent
    assert "The page was not opened" in res.history[1].result


def test_a_blocked_domain_is_stopped_the_same_way(trap_site, tmp_path):
    url, hits = trap_site
    with Browser() as b:
        b.goto(url)
        llm = ScriptedLLM([("click", {"ref": ref_of(b.snapshot().text, "Live price")}), DONE])
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[BlockedDomains(["localhost"])]).run()
    assert traps(hits) == []
    assert "Blocked by guardrail BlockedDomains" in res.history[0].result


def test_without_a_site_guardrail_the_click_goes_through(trap_site, tmp_path):
    url, hits = trap_site
    with Browser() as b:
        b.goto(url)
        llm = ScriptedLLM([("click", {"ref": ref_of(b.snapshot().text, "Live price")}), DONE])
        BrowseAgent("t", llm=llm, browser=b, home=tmp_path).run()
    assert traps(hits) == ["/trap?from=link"]                       # nothing was restricted, so nothing is interfered with
