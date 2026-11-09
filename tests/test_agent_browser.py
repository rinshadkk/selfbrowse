import pytest

from selfbrowse import BrowseAgent, Browser
from tests.conftest import ScriptedLLM

pytestmark = pytest.mark.browser


def make_browser():
    return Browser(channel=None)


def test_snapshot_lists_controls(shop_url):
    with make_browser() as b:
        b.goto(shop_url)
        text = b.snapshot().text
    assert 'button "Add to cart"' in text and 'textbox "Search"' in text and "Password" in text


def test_full_run_with_secret_and_trimmed_history(shop_url, tmp_path):
    llm = ScriptedLLM([
        ("goto", {"url": shop_url}),
        ("click", {"ref": 1}),                     # placeholder; fixed below by looking at refs
        ("done", {"success": True, "answer": "ok"}),
    ])
    # find refs dynamically via a first snapshot
    with make_browser() as b:
        b.goto(shop_url)
        snap = b.snapshot().text
        add = next(int(l.split()[0][1:]) for l in snap.splitlines() if "Add to cart" in l)
        pw = next(int(l.split()[0][1:]) for l in snap.splitlines() if "Password" in l)
        llm.script[1] = ("click", {"ref": add})
        llm.script.insert(2, ("type", {"ref": pw, "text": "<secret:pw>"}))
        agent = BrowseAgent("buy", llm=llm, browser=b, home=tmp_path, sensitive={"pw": "hunter2"})
        res = agent.run()
        assert res.success and res.output == "ok"
        assert b.page.input_value("#pw") == "hunter2"
    # secret never reached the model or the history
    assert "hunter2" not in repr(llm.seen) and "hunter2" not in repr(res.history)
    # only the latest page list survives in earlier tool results
    last_msgs = llm.seen[-1]
    pages = sum(1 for m in last_msgs if m["role"] == "user" and not isinstance(m["content"], str)
                for blk in m["content"] for part in blk["content"] if "viewport shows" in part["text"])
    assert pages == 1


def test_replay_after_two_successes(shop_url, tmp_path):
    def run(script):
        llm = ScriptedLLM(script)
        with make_browser() as b:
            b.goto(shop_url)
            snap = b.snapshot().text
            accept = next(int(l.split()[0][1:]) for l in snap.splitlines() if '"Accept"' in l)
            llm.script = [("click", {"ref": accept}), *script]
            res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path).run()
        return res, llm

    done = [("done", {"success": True, "answer": "x"})]
    for _ in range(2):
        res, _ = run(done)
        assert res.success
    # third run: the cookie banner click is replayed with no model call for it
    llm = ScriptedLLM(done)
    with make_browser() as b:
        b.goto(shop_url)
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path).run()
    assert res.history[0].from_cache and res.usage.calls == 1


def test_page_list_survives_a_read(shop_url, tmp_path):
    """After `read` the model must still have the numbered list (regression: it used to be trimmed)."""
    llm = ScriptedLLM([("read", {}), ("done", {"success": True, "answer": "ok"})])
    with Browser() as b:
        b.goto(shop_url)
        BrowseAgent("t", llm=llm, browser=b, home=tmp_path).run()
    assert "Add to cart" in repr(llm.seen[1])
