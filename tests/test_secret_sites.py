"""A saved value belongs to a site: it is typed only there, and only that site's values are offered on a page."""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.agent import normalize_site, site_allows
from tests.conftest import ScriptedLLM
from tests.test_browser_tools import ref_of

DONE = ("done", {"success": True, "answer": "ok"})


# ---- reading a site name ----

@pytest.mark.parametrize("raw,site", [
    ("shop.example", "shop.example"), ("https://www.Shop.example/login?x=1", "shop.example"),
    ("www.shop.example:8443/a", "shop.example"), ("localhost:8000", "localhost"), ("http://127.0.0.1:8765/x", "127.0.0.1"),
    ("not a site", ""), ("com", ""), ("javascript:alert(1)", ""), ("", ""), ("   ", ""),
])
def test_normalize_site(raw, site):
    assert normalize_site(raw) == site


def test_a_site_covers_its_subdomains_and_nothing_that_only_looks_like_it():
    ok = lambda url: site_allows("shop.example", url)       # noqa: E731
    assert ok("https://www.shop.example/x") and ok("https://secure.shop.example:8443/") and ok("http://shop.example")
    assert not ok("https://evilshop.example") and not ok("https://shop.example.evil.io/")
    assert not ok("https://evil.com/@shop.example") and not ok("https://user@evil.com/shop.example") and not ok("about:blank")
    assert not site_allows("", "https://shop.example")


# ---- in the browser ----

@pytest.fixture()
def login_page():
    """One page with a password box, served under two names a browser treats as two sites."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<form><input type="password" aria-label="Password"><input aria-label="Search"></form>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_port
    srv.shutdown()


def agent(b, steps, tmp_path, **kw):
    return BrowseAgent("t", llm=ScriptedLLM(steps), browser=b, home=tmp_path, **kw)


@pytest.mark.browser
def test_a_value_is_typed_on_its_own_site(login_page, tmp_path):
    with Browser() as b:
        b.goto(f"http://localhost:{login_page}/")
        ref = ref_of(b.snapshot().text, "Password")
        res = agent(b, [("type", {"ref": ref, "text": "<secret:PW>"}), DONE], tmp_path,
                    sensitive={"PW": "hunter2"}, sensitive_sites={"PW": "localhost"}).run()
        assert b.page.input_value("input[type=password]") == "hunter2"
    assert res.history[0].result.startswith("typed")


@pytest.mark.browser
def test_a_value_is_not_typed_on_another_site(login_page, tmp_path):
    with Browser() as b:
        b.goto(f"http://127.0.0.1:{login_page}/")                  # same server, a different site
        ref = ref_of(b.snapshot().text, "Password")
        res = agent(b, [("type", {"ref": ref, "text": "<secret:PW>"}), DONE], tmp_path,
                    sensitive={"PW": "hunter2"}, sensitive_sites={"PW": "localhost"}).run()
        assert b.page.input_value("input[type=password]") == ""    # nothing was typed
    out = res.history[0].result
    assert "Blocked" in out and "saved for localhost" in out and "127.0.0.1" in out and "hunter2" not in out


@pytest.mark.browser
def test_it_is_also_blocked_when_the_secret_is_part_of_longer_text(login_page, tmp_path):
    with Browser() as b:
        b.goto(f"http://127.0.0.1:{login_page}/")
        ref = ref_of(b.snapshot().text, "Search")
        res = agent(b, [("type", {"ref": ref, "text": "pw is <secret:PW>"}), DONE], tmp_path,
                    sensitive={"PW": "hunter2"}, sensitive_sites={"PW": "localhost"}).run()
        assert b.page.input_value("input[aria-label=Search]") == ""
    assert "Blocked" in res.history[0].result


@pytest.mark.browser
def test_a_value_with_no_site_is_typed_anywhere_as_before(login_page, tmp_path):
    with Browser() as b:
        b.goto(f"http://127.0.0.1:{login_page}/")
        ref = ref_of(b.snapshot().text, "Search")
        res = agent(b, [("type", {"ref": ref, "text": "<secret:CITY>"}), DONE], tmp_path,
                    sensitive={"CITY": "Chicago", "PW": "x"}, sensitive_sites={"PW": "localhost"}).run()
        assert b.page.input_value("input[aria-label=Search]") == "Chicago"
    assert res.history[0].result.startswith("typed")


@pytest.mark.browser
def test_an_unreadable_site_binds_nothing_instead_of_everything(login_page, tmp_path):
    a = BrowseAgent("t", llm=ScriptedLLM([DONE]), browser=None, home=tmp_path, sensitive={"PW": "x"}, sensitive_sites={"PW": "not a site"})
    assert a.sites == {}


@pytest.mark.browser
def test_the_lookup_offers_this_sites_values_and_hides_the_rest(login_page, tmp_path):
    sensitive = {"LOCAL_PW": "a", "OTHER_PW": "b", "CITY": "Chicago"}
    hints = {"LOCAL_PW": "Local login > Password", "OTHER_PW": "Amazon login > Password", "CITY": "Address > City"}
    sites = {"LOCAL_PW": "localhost", "OTHER_PW": "example.com"}
    with Browser() as b:
        b.goto(f"http://localhost:{login_page}/")
        res = agent(b, [("find_saved_detail", {"what": "password"}), DONE], tmp_path, sensitive=sensitive,
                    sensitive_hints=hints, sensitive_sites=sites).run()
    out = res.history[0].result
    assert "<secret:LOCAL_PW>" in out and "OTHER_PW" not in out and "Amazon" not in out


@pytest.mark.browser
def test_the_lookup_on_this_site_needs_no_form_name(login_page, tmp_path):
    """A model that only says it is logging in still gets the login saved for the page it is on."""
    sensitive = {"LOCAL_USER": "me", "OTHER_USER": "you"}
    hints = {"LOCAL_USER": "Pharmacy > Username", "OTHER_USER": "Shop > Username"}
    sites = {"LOCAL_USER": "localhost", "OTHER_USER": "example.com"}
    with Browser() as b:
        b.goto(f"http://localhost:{login_page}/")
        res = agent(b, [("find_saved_detail", {"what": "log in"}), DONE], tmp_path, sensitive=sensitive,
                    sensitive_hints=hints, sensitive_sites=sites).run()
    out = res.history[0].result
    assert "<secret:LOCAL_USER>" in out and "OTHER_USER" not in out


@pytest.mark.browser
def test_the_lookup_says_when_the_match_is_saved_for_another_site(login_page, tmp_path):
    with Browser() as b:
        b.goto(f"http://127.0.0.1:{login_page}/")
        res = agent(b, [("find_saved_detail", {"what": "password"}), DONE], tmp_path, sensitive={"PW": "b"},
                    sensitive_hints={"PW": "Amazon login > Password"}, sensitive_sites={"PW": "example.com"}).run()
    out = res.history[0].result
    assert "different site" in out and "PW" not in out.replace("password", "")
