import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import AllowedDomains, Budget, ConfirmRisky, InjectionWatch, RedactPII
from tests.conftest import ScriptedLLM

pytestmark = pytest.mark.browser
DONE = ("done", {"success": True, "answer": "ok"})


def page(shop_url, name):
    return shop_url.replace("shop.html", name)


def first_prompt(llm):
    return repr(llm.seen[0])


def test_allowed_domains_blocks_goto(shop_url, tmp_path):
    llm = ScriptedLLM([("goto", {"url": "https://evil.example/"}), DONE])
    with Browser() as b:
        b.goto(shop_url)
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[AllowedDomains(["127.0.0.1"])]).run()
        assert "127.0.0.1" in b.url                                 # never left
    assert res.success
    assert "Blocked by guardrail AllowedDomains" in res.history[0].result


def test_start_page_outside_allowed_domains_stops_run(shop_url, tmp_path):
    with Browser() as b:
        b.goto(shop_url)
        res = BrowseAgent("t", llm=ScriptedLLM([DONE]), browser=b, home=tmp_path,
                    guardrails=[AllowedDomains(["example.org"])]).run()
    assert not res.success and "AllowedDomains" in res.error and res.usage.calls == 0


def test_link_that_lands_off_domain_is_undone(shop_url, tmp_path):
    # contact.html links to shop.html on the same host; allow only the contact page's own host via a BlockedDomains-like rule
    from selfbrowse.guardrails import Block, Guardrail

    class NoShop(Guardrail):
        def check_url(self, url):
            return Block("shop is off limits") if url.endswith("shop.html") else None

    contact = page(shop_url, "contact.html")
    with Browser() as b:
        b.goto(contact)
        snap = b.snapshot().text
        link = next(int(l.split()[0][1:]) for l in snap.splitlines() if 'link "Shop"' in l)
        llm = ScriptedLLM([("click", {"ref": link}), DONE])
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[NoShop()]).run()
        assert b.url.endswith("contact.html")                       # sent back
    assert "Blocked by guardrail NoShop" in res.history[0].result


def test_confirm_risky_declined_does_not_click(shop_url, tmp_path):
    contact = page(shop_url, "contact.html")
    asked = []
    with Browser() as b:
        b.goto(contact)
        snap = b.snapshot().text
        delete = next(int(l.split()[0][1:]) for l in snap.splitlines() if "Delete account" in l)
        llm = ScriptedLLM([("click", {"ref": delete}), DONE])

        def person(req):
            asked.append(req)
            return False

        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[ConfirmRisky()], handoff=person).run()
        assert b.page.inner_text("#o") == ""                         # nothing deleted
    assert asked and asked[0].kind == "confirm" and "declined" in res.history[0].result


def test_confirm_risky_approved_clicks(shop_url, tmp_path):
    contact = page(shop_url, "contact.html")
    with Browser() as b:
        b.goto(contact)
        snap = b.snapshot().text
        delete = next(int(l.split()[0][1:]) for l in snap.splitlines() if "Delete account" in l)
        llm = ScriptedLLM([("click", {"ref": delete}), DONE])
        BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[ConfirmRisky()], handoff=lambda r: True).run()
        assert b.page.inner_text("#o") == "deleted"


def test_confirm_without_a_person_blocks(shop_url, tmp_path):
    contact = page(shop_url, "contact.html")
    with Browser() as b:                                              # headless, no handler
        b.goto(contact)
        snap = b.snapshot().text
        delete = next(int(l.split()[0][1:]) for l in snap.splitlines() if "Delete account" in l)
        res = BrowseAgent("t", llm=ScriptedLLM([("click", {"ref": delete}), DONE]), browser=b, home=tmp_path,
                    guardrails=[ConfirmRisky()]).run()
        assert b.page.inner_text("#o") == "" and "no person is available" in res.history[0].result


def test_redaction_happens_before_the_model_sees_the_page(shop_url, tmp_path):
    llm = ScriptedLLM([("read", {}), DONE])
    with Browser() as b:
        b.goto(page(shop_url, "contact.html"))
        BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[RedactPII(restore=False)]).run()
    seen = repr(llm.seen)
    assert "jane.doe@example.com" not in seen and "555-0187" not in seen and "4111" not in seen
    assert "[email]" in seen and "[card]" in seen


def test_without_redaction_the_model_sees_it(shop_url, tmp_path):
    llm = ScriptedLLM([("read", {}), DONE])
    with Browser() as b:
        b.goto(page(shop_url, "contact.html"))
        BrowseAgent("t", llm=llm, browser=b, home=tmp_path).run()
    assert "jane.doe@example.com" in repr(llm.seen)


def test_injection_warning_is_shown(shop_url, tmp_path):
    llm = ScriptedLLM([("read", {}), DONE])
    with Browser() as b:
        b.goto(page(shop_url, "injected.html"))
        BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[InjectionWatch()]).run()
    assert "looks like instructions aimed at an AI" in repr(llm.seen[1])


def test_budget_stops_run(shop_url, tmp_path):
    llm = ScriptedLLM([("wait", {"seconds": 0.1})] * 10)
    with Browser() as b:
        b.goto(shop_url)
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, max_steps=10, guardrails=[Budget(max_tokens=250)]).run()
    assert not res.success and "token budget exceeded" in res.error and res.usage.calls == 3


def test_default_blocks_non_http_urls(shop_url, tmp_path):
    llm = ScriptedLLM([("goto", {"url": "file:///etc/passwd"}), DONE])
    with Browser() as b:
        b.goto(shop_url)
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path).run()
    assert "only http(s)" in res.history[0].result
