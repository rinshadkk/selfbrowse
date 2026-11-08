"""Loop-breaking: cut-off replies, scroll circles, repeated clicks, key names."""
import pytest

from selfbrowse import Agent, Browser
from selfbrowse.browser import normalize_key
from tests.conftest import ScriptedLLM


@pytest.mark.parametrize("given,want", [
    ("Down", "ArrowDown"), ("down", "ArrowDown"), ("Return", "Enter"), ("esc", "Escape"),
    ("PageDown", "PageDown"), ("ctrl+a", "Control+a"), ("Cmd+Shift+Z", "Meta+Shift+Z"),
    ("Enter", "Enter"), ("a", "a"), ("+", "+"), ("F5", "F5"),
])
def test_normalize_key(given, want):
    assert normalize_key(given) == want


class FakeBrowser:
    """Just enough browser for the loop tests that do not need a real page."""
    headless = True
    url = "http://x.test/"
    title = ""

    def start(self): return self
    def close(self): pass
    def snapshot(self):
        from selfbrowse.browser import Snapshot
        return Snapshot("[page]\n#1 button \"Go\"", [{"ref": 1}], self.url, "")
    def visible_text(self, n=3000): return "some text"
    def describe_ref(self, ref): return {"role": "button", "text": "Go"}
    def scroll(self, direction="down", amount=600): return f"scrolled {direction}"
    def click_ref(self, ref): return "clicked #1"
    def bring_to_front(self): pass


def results_text(llm):
    return repr(llm.seen[-1])


def test_cut_off_reply_gets_a_specific_nudge_and_a_fresh_chance(tmp_path):
    llm = ScriptedLLM([("__cut__", "Let me think about this at great length..."), ("read", {}),
                       ("done", {"success": True, "answer": "ok"})])
    res = Agent("t", llm=llm, browser=FakeBrowser(), home=tmp_path, learn=False).run()
    assert res.success
    assert "cut off" in repr(llm.seen[1])
    # the cap is passed to the model
    assert res.usage.calls == 3


def test_endless_cut_offs_end_with_a_helpful_error(tmp_path):
    llm = ScriptedLLM([("__cut__", "thinking...")] * 5)
    res = Agent("t", llm=llm, browser=FakeBrowser(), home=tmp_path, learn=False).run()
    assert not res.success and "--max-output-tokens" in res.error


def test_nudge_budget_is_for_consecutive_misses(tmp_path):
    """Three isolated hiccups across a long run must not end it (it used to be a lifetime limit)."""
    script = []
    for _ in range(4):
        script += [("__text__", "hmm"), ("read", {})]
    script.append(("done", {"success": True, "answer": "ok"}))
    res = Agent("t", llm=ScriptedLLM(script), browser=FakeBrowser(), home=tmp_path, learn=False, max_steps=30).run()
    assert res.success


def test_scrolling_up_and_down_is_called_out(tmp_path):
    llm = ScriptedLLM([("scroll", {"direction": d}) for d in ("down", "up", "down", "up")] +
                      [("done", {"success": True, "answer": "ok"})])
    Agent("t", llm=llm, browser=FakeBrowser(), home=tmp_path, learn=False).run()
    assert "circles" in repr(llm.seen[4])
    assert "circles" not in repr(llm.seen[3])


def test_reading_between_scrolls_resets_the_circle_check(tmp_path):
    llm = ScriptedLLM([("scroll", {"direction": "down"}), ("scroll", {"direction": "up"}), ("read", {}),
                       ("scroll", {"direction": "down"}), ("scroll", {"direction": "up"}),
                       ("done", {"success": True, "answer": "ok"})])
    Agent("t", llm=llm, browser=FakeBrowser(), home=tmp_path, learn=False).run()
    assert "circles" not in repr(llm.seen)


def test_clicking_the_same_control_again_is_flagged(tmp_path):
    llm = ScriptedLLM([("click", {"ref": 1}), ("scroll", {"direction": "down"}), ("click", {"ref": 1}),
                       ("done", {"success": True, "answer": "ok"})])
    Agent("t", llm=llm, browser=FakeBrowser(), home=tmp_path, learn=False).run()
    assert 'already clicked "Go"' in repr(llm.seen[3])
    assert 'already clicked' not in repr(llm.seen[2])


@pytest.mark.browser
def test_press_accepts_sloppy_key_names(site):
    with Browser() as b:
        b.goto(site("form.html"))
        assert b.press("Down") == "pressed Down"      # used to raise: Unknown key "Down"
        assert b.press("ctrl+a") == "pressed ctrl+a"
