import pytest

from selfbrowse import Agent, Browser
from tests.conftest import ScriptedLLM

pytestmark = pytest.mark.browser
DONE = ("done", {"success": True, "answer": "ok"})


def refs(browser):
    snap = browser.snapshot().text
    find = lambda needle: next(int(l.split()[0][1:]) for l in snap.splitlines() if needle in l)
    return find


def run(shop_url, tmp_path, script, **kw):
    llm = ScriptedLLM(script)
    with Browser() as b:
        b.goto(shop_url)
        f = refs(b)
        llm.script = [(n, a(f) if callable(a) else a) for n, a in llm.script]
        res = Agent("t", llm=llm, browser=b, home=tmp_path, **kw).run()
        state = b.page.inner_text("#out")
    return res, llm, state


def test_wrong_argument_name_still_clicks(shop_url, tmp_path):
    res, _, out = run(shop_url, tmp_path, [("click", lambda f: {"id": str(f("Add to cart"))}), DONE])
    assert out == "Added to cart" and res.success


def test_unfixable_args_get_a_helpful_error_not_a_bare_key_error(shop_url, tmp_path):
    res, llm, _ = run(shop_url, tmp_path, [("click", {"foo": 1}), DONE])
    assert "click needs ref" in repr(llm.seen[1]) and "'ref'" not in res.history[0].result.replace("click needs ref", "")


def test_tool_call_written_as_text_is_executed(shop_url, tmp_path):
    res, _, out = run(shop_url, tmp_path, [
        ("__text__", lambda f: '{"name": "click", "parameters": {"ref": %d}}' % f("Add to cart")), DONE])
    assert out == "Added to cart" and res.success and res.history[0].tool == "click"


def test_junk_text_is_not_accepted_as_an_answer(shop_url, tmp_path):
    res, llm, _ = run(shop_url, tmp_path, [("read", {}), ("__text__", "read()\nThe store opened in 2010"), DONE])
    assert res.success and res.output == "ok"                      # it had to call done
    assert "exactly one tool call" in repr(llm.seen[2])


def test_clean_text_after_acting_is_accepted(shop_url, tmp_path):
    res, _, _ = run(shop_url, tmp_path, [("read", {}), ("__text__", "The page says Demo Shop.")])
    assert res.success and res.output == "The page says Demo Shop."


def test_text_before_any_action_is_not_accepted(shop_url, tmp_path):
    res, _, _ = run(shop_url, tmp_path, [("__text__", "42"), DONE])
    assert res.success and res.output == "ok"


def test_gives_up_after_repeated_text_nonsense(shop_url, tmp_path):
    res, _, _ = run(shop_url, tmp_path, [("__text__", "blah")] * 6)
    assert not res.success and "never produced a valid action" in res.error


def test_repeated_failures_stop_the_run_early(shop_url, tmp_path):
    res, _, _ = run(shop_url, tmp_path, [("click", {"ref": 99})] * 20, max_steps=20)
    assert not res.success and "keeps producing invalid" in res.error and res.usage.calls == 6


def test_unknown_tool_lists_real_tools(shop_url, tmp_path):
    res, llm, _ = run(shop_url, tmp_path, [("send_keys", {"idx": 1}), DONE])
    assert "unknown tool 'send_keys'" in res.history[0].result and "click" in res.history[0].result
