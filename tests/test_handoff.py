import pytest

from selfbrowse import Agent, Browser
from selfbrowse.handoff import detect_block
from tests.conftest import ScriptedLLM

DONE = ("done", {"success": True, "answer": "ok"})


# ── detection (no browser) ───────────────────────────────────────────────────
def test_detects_challenge_by_title():
    assert detect_block("Just a moment...", "", 5)


def test_detects_challenge_by_text_on_sparse_page():
    assert detect_block("Walmart", "Please verify you are human to continue", 4)


def test_article_mentioning_captcha_is_not_a_block():
    assert detect_block("How CAPTCHAs work - Wiki", "A captcha is a test ...", 120) is None


def test_normal_page_is_fine():
    assert detect_block("Demo Shop", "Add to cart", 5) is None


# ── behaviour (browser) ──────────────────────────────────────────────────────
pytestmark_browser = pytest.mark.browser


@pytest.fixture
def challenge_url(shop_url):
    return shop_url.replace("shop.html", "challenge.html")


@pytest.mark.browser
def test_headless_challenge_stops_with_clear_error(challenge_url, tmp_path):
    llm = ScriptedLLM([DONE])
    with Browser() as b:                              # headless: no one to hand off to
        b.goto(challenge_url)
        res = Agent("t", llm=llm, browser=b, home=tmp_path).run()
    assert not res.success and "--headed" in res.error and "blocked" in res.error
    assert res.usage.calls == 0                       # no model money spent on a page it cannot use


@pytest.mark.browser
def test_handler_resumes_after_person_solves(challenge_url, shop_url, tmp_path):
    seen = []

    def person(req):
        seen.append(req)
        b.page.goto(shop_url)                         # the "person" gets past the check
        return True

    llm = ScriptedLLM([DONE])
    with Browser() as b:
        b.goto(challenge_url)
        res = Agent("t", llm=llm, browser=b, home=tmp_path, handoff=person).run()
    assert res.success and len(seen) == 1 and seen[0].kind == "challenge"
    first_prompt = repr(llm.seen[0])
    assert "The person handled it" in first_prompt and "Add to cart" in first_prompt


@pytest.mark.browser
def test_declined_handoff_fails_the_run(challenge_url, tmp_path):
    with Browser() as b:
        b.goto(challenge_url)
        res = Agent("t", llm=ScriptedLLM([DONE]), browser=b, home=tmp_path, handoff=lambda r: False).run()
    assert not res.success and "did not continue" in res.error


@pytest.mark.browser
def test_model_can_ask_for_help(shop_url, tmp_path):
    seen = []
    llm = ScriptedLLM([("goto", {"url": shop_url}), ("ask_human", {"reason": "enter the 2FA code"}), DONE])
    with Browser() as b:
        res = Agent("t", llm=llm, browser=b, home=tmp_path, handoff=lambda r: seen.append(r) or True).run()
    assert res.success and seen[0].kind == "model" and "2FA" in seen[0].reason
    assert any(s.tool == "ask_human" for s in res.history)


@pytest.mark.browser
def test_ask_human_not_offered_without_handler(shop_url, tmp_path):
    llm = ScriptedLLM([("goto", {"url": shop_url}), DONE])
    with Browser() as b:
        agent = Agent("t", llm=llm, browser=b, home=tmp_path)      # headless + auto → no handler
        agent.run()
    assert "ask_human" not in [t["name"] for t in agent.tools]


@pytest.mark.browser
def test_gives_up_after_max_handoffs(challenge_url, tmp_path):
    with Browser() as b:
        b.goto(challenge_url)
        res = Agent("t", llm=ScriptedLLM([DONE] * 5), browser=b, home=tmp_path,
                    handoff=lambda r: True, max_handoffs=2).run()     # "solves" but the page never changes
    assert not res.success and "2 hand-offs" in res.error


def test_terminal_handler_declines_without_a_terminal(monkeypatch):
    import io
    import sys

    from selfbrowse.handoff import HandoffRequest, terminal_handler
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))        # not a tty
    assert terminal_handler(HandoffRequest("challenge", "x", "https://a.b")) is False
