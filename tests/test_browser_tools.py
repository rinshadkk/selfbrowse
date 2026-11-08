"""Dropdowns, iframes, shadow DOM, tabs and find-on-page, against real pages in a real browser."""
import pytest

from selfbrowse import Agent, Browser
from tests.conftest import ScriptedLLM

pytestmark = pytest.mark.browser


def ref_of(snapshot_text: str, needle: str) -> int:
    return next(int(l.split()[0][1:]) for l in snapshot_text.splitlines() if l.startswith("#") and needle in l)


# ── A1 dropdown select ────────────────────────────────────────────────────────────
def test_select_lists_options_and_chooses(site):
    with Browser() as b:
        b.goto(site("form.html"))
        text = b.snapshot().text
        assert 'combobox "Country" (value="Select a country", options: Select a country | Canada | France' in text
        ref = ref_of(text, "Country")
        assert b.select_ref(ref, "Germany") == f'selected "Germany" in #{ref}'
        assert b.page.input_value("#country") == "de"
        assert "country=de" in b.visible_text()        # the page's change handler ran


def test_select_by_value_and_partial_text(site):
    with Browser() as b:
        b.goto(site("form.html"))
        ref = ref_of(b.snapshot().text, "Size")
        b.select_ref(ref, "large")                      # case-insensitive
        assert b.page.input_value("#size") == "Large"
        ref = ref_of(b.snapshot().text, "Country")
        b.select_ref(ref, "ca")                         # the option's value
        assert b.page.input_value("#country") == "ca"


def test_select_errors_list_the_options(site):
    with Browser() as b:
        b.goto(site("form.html"))
        ref = ref_of(b.snapshot().text, "Country")
        with pytest.raises(Exception, match="no option matches.*Options: Select a country \\| Canada"):
            b.select_ref(ref, "Narnia")
        with pytest.raises(Exception, match="more than one option"):
            b.select_ref(ref, "an")                     # Canada, France, Germany, French Guiana
        with pytest.raises(Exception, match="not a native dropdown"):
            b.select_ref(ref_of(b.snapshot().text, "Order form"), "x")


# ── A7 iframes ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("which", [0, 1], ids=["same-origin", "cross-origin"])
def test_form_inside_iframe_can_be_completed(site, which):
    with Browser() as b:
        b.goto(site("frames.html"))
        text = b.snapshot().text
        users = [l for l in text.splitlines() if "Frame username" in l]
        assert len(users) == 2, text                    # both frames are in the list
        user = int(users[which].split()[0][1:])
        b.click_ref(user)
        b.type_text("ada")
        text = b.snapshot().text
        go = [int(l.split()[0][1:]) for l in text.splitlines() if "Frame sign in" in l][which]
        b.click_ref(go)
        frame = [f for f in b.page.frames[1:]][which]
        assert frame.locator("#msg").inner_text() == "welcome ada"


def test_iframe_text_is_readable(site):
    with Browser() as b:
        b.goto(site("frames.html"))
        b.wait(1)
        assert "Sign in inside the frame" in b.visible_text()


# ── A8 shadow DOM ──────────────────────────────────────────────────────────────────
def test_shadow_dom_is_pierced(site):
    with Browser() as b:
        b.goto(site("shadow.html"))
        text = b.snapshot().text
        assert 'textbox "Shadow email"' in text and 'button "Shadow submit"' in text
        b.click_ref(ref_of(text, "Shadow email"))
        b.type_text("a@b.co")
        b.click_ref(ref_of(b.snapshot().text, "Shadow submit"))
        assert "submitted a@b.co" in b.visible_text()
        assert "tangerine" in b.visible_text()           # text inside the shadow root


# ── A3 tabs ────────────────────────────────────────────────────────────────────────
def test_link_in_new_tab_is_announced_and_can_be_closed(site):
    with Browser() as b:
        b.goto(site("tabs.html"))
        assert "[tabs:" not in b.snapshot().text
        b.click_ref(ref_of(b.snapshot().text, "Open details"))
        text = b.snapshot().text
        assert '[tabs: 1 "Tabs home" · 2 "Details tab" (current)]' in text
        assert "4821" in b.visible_text()
        assert b.close_tab().startswith("closed tab 2")
        assert "Tabs home" in b.title and "[tabs:" not in b.snapshot().text


def test_switch_tab_and_popup_window(site):
    with Browser() as b:
        b.goto(site("tabs.html"))
        b.click_ref(ref_of(b.snapshot().text, "Popup details"))
        assert "Details tab" in b.title
        assert b.switch_tab(1).startswith("switched to tab 1")
        assert "Tabs home" in b.title
        with pytest.raises(Exception, match="No tab 5"):
            b.switch_tab(5)
        b.close_tab(2)
        with pytest.raises(Exception, match="only open tab"):
            b.close_tab()


# ── R9 find on page ────────────────────────────────────────────────────────────────
def test_find_scrolls_to_text_and_steps_through_matches(site):
    with Browser() as b:
        b.goto(site("long.html"))
        first = b.find_text("needle")
        assert "match 1 of 2" in first and "nth=2" in first
        second = b.find_text("needle", 2)
        assert "match 2 of 2" in second and "returns are free" in second
        assert "shipping policy" in b.visible_text()     # it really scrolled there
        assert "no match number 3" in b.find_text("needle", 3)
        assert "is not on this page" in b.find_text("zebra")


def test_find_reaches_shadow_and_frames(site):
    with Browser() as b:
        b.goto(site("shadow.html"))
        assert "match 1 of 1" in b.find_text("tangerine")
        b.goto(site("frames.html"))
        b.wait(1)
        assert "of 2" in b.find_text("sign in inside")


# ── through the agent ─────────────────────────────────────────────────────────────
def test_agent_runs_the_new_tools(site, tmp_path):
    with Browser() as b:
        b.goto(site("form.html"))
        ref = ref_of(b.snapshot().text, "Country")
        llm = ScriptedLLM([
            ("select", {"ref": ref, "option": "France"}),
            ("find", {"text": "country=fr"}),
            ("done", {"success": True, "answer": "ok"}),
        ])
        res = Agent("pick", llm=llm, browser=b, home=tmp_path, learn=False).run()
        assert res.success and b.page.input_value("#country") == "fr"
        assert [s.tool for s in res.history] == ["select", "find", "done"]
        assert "selected" in res.history[0].result and "found" in res.history[1].result


def test_new_tool_names_are_sloppy_call_friendly():
    from selfbrowse.tools import build_tools, normalize_args
    tool = next(t for t in build_tools() if t["name"] == "select")
    assert normalize_args(tool, {"id": "3", "value": "France"})[0] == {"ref": 3, "option": "France"}
    find = next(t for t in build_tools() if t["name"] == "find")
    assert normalize_args(find, {"query": "refund", "nth": "2"})[0] == {"text": "refund", "nth": 2}


def test_page_text_adds_text_to_the_state(site, tmp_path):
    llm = ScriptedLLM([("done", {"success": True, "answer": "ok"})])
    llm2 = ScriptedLLM([("wait", {"seconds": 0.1}), ("done", {"success": True, "answer": "ok"})])
    with Browser() as b:
        b.goto(site("form.html"))
        Agent("t", llm=llm2, browser=b, home=tmp_path, learn=False, page_text=300).run()
        assert "[text on screen]" in repr(llm2.seen[1]) and "nothing chosen" in repr(llm2.seen[1])
        llm3 = ScriptedLLM([("wait", {"seconds": 0.1}), ("done", {"success": True, "answer": "ok"})])
        Agent("t", llm=llm3, browser=b, home=tmp_path, learn=False).run()
        assert "[text on screen]" not in repr(llm3.seen[1])
