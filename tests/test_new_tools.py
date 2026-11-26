"""File upload, drag and drop and custom dropdowns, against real pages in a real browser."""
import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import ConfirmRisky
from tests.conftest import ScriptedLLM
from tests.test_browser_tools import ref_of

pytestmark = pytest.mark.browser


@pytest.fixture()
def files(tmp_path):
    cv = tmp_path / "cv.txt"
    cv.write_text("hello")
    photo = tmp_path / "me.png"
    photo.write_bytes(b"\x89PNG\r\n")
    badge = tmp_path / "badge.txt"
    badge.write_text("id")
    return cv, photo, badge


# ── file upload ────────────────────────────────────────────────────────────────────
def test_file_inputs_are_listed_even_when_hidden(site):
    with Browser() as b:
        b.goto(site("upload.html"))
        text = b.snapshot().text
        assert 'file "Résumé" (accepts .pdf,.txt)' in text
        assert 'file "Choose photo" (several files)' in text      # the real input is display:none inside a label


def test_upload_to_a_visible_and_a_hidden_input(site, files):
    cv, photo, _ = files
    with Browser() as b:
        b.goto(site("upload.html"))
        snap = b.snapshot().text
        assert b.upload_ref(ref_of(snap, "Résumé"), str(cv)).startswith('attached "cv.txt"')
        assert b.page.inner_text("#cv-out") == "cv.txt"          # the page's change handler ran
        b.upload_ref(ref_of(snap, "Choose photo"), str(photo))
        assert b.page.inner_text("#photo-out") == "me.png"


def test_upload_through_a_button_that_opens_a_file_picker(site, files):
    _, _, badge = files
    with Browser() as b:
        b.goto(site("upload.html"))
        ref = ref_of(b.snapshot().text, "Upload badge")
        b.upload_ref(ref, str(badge))
        assert b.page.inner_text("#badge-out") == "badge.txt"


def test_upload_to_something_that_takes_no_file_says_so(site, files):
    cv, _, _ = files
    with Browser() as b:
        b.goto(site("upload.html"))
        with pytest.raises(Exception, match="did not open a file picker"):
            b.upload_ref(ref_of(b.snapshot().text, "Apply"), str(cv))


def test_agent_only_uploads_allowed_files_and_never_shows_folders(site, files, tmp_path):
    cv, photo, _ = files
    secret = tmp_path / "private.key"
    secret.write_text("nope")
    url = site("upload.html")
    llm = ScriptedLLM([("upload", {}), ("upload", {}), ("done", {"success": True, "answer": "ok"})])
    with Browser() as b:
        b.goto(url)
        ref = ref_of(b.snapshot().text, "Résumé")
        llm.script[0] = ("upload", {"ref": ref, "file": "private.key"})      # not on the allowed list
        llm.script[1] = ("upload", {"ref": ref, "file": "cv.txt"})
        res = BrowseAgent("upload my cv", llm=llm, browser=b, learn=False, files=[cv, photo]).run()
        assert res.success
        assert b.page.inner_text("#cv-out") == "cv.txt"
    first = res.history[0].result
    assert 'not a file you may upload' in first and "cv.txt" in first and "me.png" in first
    first_prompt = str(llm.seen[0])
    assert "cv.txt" in first_prompt and str(tmp_path) not in first_prompt        # names, not folders


def test_upload_tool_is_only_offered_when_files_are_given(site, files):
    cv, _, _ = files
    assert "upload" not in [t["name"] for t in BrowseAgent("t", llm=ScriptedLLM([]), learn=False).tools]
    assert "upload" in [t["name"] for t in BrowseAgent("t", llm=ScriptedLLM([]), learn=False, files=[cv]).tools]
    with pytest.raises(ValueError, match="is not a file"):
        BrowseAgent("t", llm=ScriptedLLM([]), files=["/no/such/file.pdf"])


def test_confirm_risky_asks_before_an_upload(site, files):
    cv, _, _ = files
    with Browser() as b:
        b.goto(site("upload.html"))
        ref = ref_of(b.snapshot().text, "Résumé")
        llm = ScriptedLLM([("upload", {"ref": ref, "file": "cv.txt"}), ("done", {"success": True, "answer": "x"})])
        res = BrowseAgent("t", llm=llm, browser=b, learn=False, files=[cv], guardrails=[ConfirmRisky()], handoff=False).run()
        assert "sends a local file" in res.history[0].result
        assert b.page.inner_text("#cv-out") == "none"


# ── drag and drop ──────────────────────────────────────────────────────────────────
def test_draggables_and_drop_targets_are_listed(site):
    with Browser() as b:
        b.goto(site("dnd.html"))
        text = b.snapshot().text
        assert "Write tests" in text and "draggable" in text
        assert "drop target" in text or "dropzone" in text
        assert b.has_drag_targets()


def test_drag_moves_a_card(site):
    with Browser() as b:
        b.goto(site("dnd.html"))
        snap = b.snapshot().text
        card, done = ref_of(snap, 'draggable "Write tests"'), ref_of(snap, 'dropzone "Done"')
        msg = b.drag_ref(card, done)
        assert msg.startswith('dragged #') and "Write tests" in msg
        assert b.page.inner_text("#log") == "Write tests -> done"
        assert b.page.locator("#done #c1").count() == 1


def test_drag_needs_two_different_elements(site):
    with Browser() as b:
        b.goto(site("dnd.html"))
        ref = ref_of(b.snapshot().text, "Ship it")
        with pytest.raises(Exception, match="two different elements"):
            b.drag_ref(ref, ref)


def test_drag_is_offered_only_on_pages_with_something_to_drag(site):
    with Browser() as b:
        b.goto(site("form.html"))
        agent = BrowseAgent("t", llm=ScriptedLLM([]), browser=b, learn=False)
        b.snapshot()
        assert "drag" not in [t["name"] for t in agent._tools_now()]
        b.goto(site("dnd.html"))
        b.snapshot()
        assert "drag" in [t["name"] for t in agent._tools_now()]
        b.goto(site("form.html"))
        b.snapshot()
        assert "drag" in [t["name"] for t in agent._tools_now()]      # once offered, it stays


def test_flow_is_not_saved_when_a_run_used_drag(site, tmp_path):
    with Browser() as b:
        b.goto(site("dnd.html"))
        snap = b.snapshot().text
        card, done = ref_of(snap, 'draggable "Write tests"'), ref_of(snap, 'dropzone "Done"')
        llm = ScriptedLLM([("drag", {"ref": card, "to": done}), ("done", {"success": True, "answer": "moved"})])
        agent = BrowseAgent("move it", llm=llm, browser=b, learn=False, save_flow=tmp_path / "f.json")
        res = agent.run()
        assert res.success and not (tmp_path / "f.json").exists() and agent.flow is None


# ── custom dropdowns ───────────────────────────────────────────────────────────────
def test_open_dropdown_options_show_in_the_list(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        text = b.snapshot().text
        assert 'combobox "Pick a fruit" (closed)' in text
        b.click_ref(ref_of(text, "Pick a fruit"))
        text = b.snapshot().text
        line = next(l for l in text.splitlines() if 'combobox "Pick a fruit"' in l)
        assert "open" in line and "closed" not in line
        assert 'option "Banana"' in text


def test_select_picks_from_an_aria_dropdown_in_one_call(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        ref = ref_of(b.snapshot().text, "Pick a fruit")
        assert b.select_ref(ref, "banana") == f'selected "Banana" in #{ref}'
        assert b.page.inner_text("#fruit-out") == "fruit=Banana"


def test_select_opens_a_closed_dropdown_when_other_options_are_on_the_page(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        # items elsewhere on the page that are marked as options, as a site's navigation or a filled-in field can be
        b.page.evaluate("""() => document.body.insertAdjacentHTML('beforeend',
            '<div role="menu"><div role="menuitem">Flights</div></div><div role="listbox"><div role="option">Banana bread</div></div>')""")
        ref = ref_of(b.snapshot().text, "Pick a fruit")
        assert b.select_ref(ref, "banana") == f'selected "Banana" in #{ref}'
        assert b.page.inner_text("#fruit-out") == "fruit=Banana"


def test_an_option_with_its_text_in_a_child_element_is_one_choice(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        b.page.evaluate("""() => document.querySelectorAll('#fruit-list li')
            .forEach(li => li.innerHTML = '<span>' + li.textContent + '</span>')""")
        ref = ref_of(b.snapshot().text, "Pick a fruit")
        assert "Options: Apple | Banana | Cherry" == _err(lambda: b.select_ref(ref, "Durian")).split(". ", 1)[1]
        b.page.reload()
        b.page.evaluate("""() => document.querySelectorAll('#fruit-list li')
            .forEach(li => li.innerHTML = '<span>' + li.textContent + '</span>')""")
        ref = ref_of(b.snapshot().text, "Pick a fruit")
        assert b.select_ref(ref, "Banana") == f'selected "Banana" in #{ref}'
        assert b.page.inner_text("#fruit-out") == "fruit=Banana"


def test_select_picks_from_a_dropdown_with_no_aria(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        ref = ref_of(b.snapshot().text, '"Size"')
        b.select_ref(ref, "Large")
        assert b.page.inner_text("#size-out") == "size=Large"


def test_choices_of_a_dropdown_with_no_aria_are_listed_after_the_click_that_opened_it(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        b.click_ref(ref_of(b.snapshot().text, '"Size"'))
        text = b.snapshot().text
        assert 'option "Small"' in text and 'option "Large"' in text
        b.click_ref(ref_of(text, 'option "Medium"'))                    # the model can simply click what it sees
        assert b.page.inner_text("#size-out") == "size=Medium"


def test_select_on_a_dropdown_the_model_already_opened_does_not_close_it(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        ref = ref_of(b.snapshot().text, '"Size"')
        b.click_ref(ref)                                                 # opened by the model's own click
        b.snapshot()
        assert b.select_ref(ref, "Large") == f'selected "Large" in #{ref}'
        assert b.page.inner_text("#size-out") == "size=Large"


def test_the_listed_choices_go_away_with_the_dropdown(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        ref = ref_of(b.snapshot().text, '"Size"')
        b.select_ref(ref, "Small")
        assert 'option "Large"' not in b.snapshot().text


def test_select_picks_a_suggestion_after_typing(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        ref = ref_of(b.snapshot().text, "City")
        b.click_ref(ref)
        b.type_text("ch")
        b.snapshot()                                  # the suggestions are on the page now
        assert "more than one" in _err(lambda: b.select_ref(ref, "ch"))
        b.select_ref(ref, "Chicago")
        assert b.page.inner_text("#city-out") == "city=Chicago"


def test_select_errors_list_what_is_showing(site):
    with Browser() as b:
        b.goto(site("dropdowns.html"))
        ref = ref_of(b.snapshot().text, "Pick a fruit")
        msg = _err(lambda: b.select_ref(ref, "Durian"))
        assert "no option matches" in msg and "Apple | Banana | Cherry" in msg


def test_a_native_select_still_works_and_a_heading_is_not_a_dropdown(site):
    with Browser() as b:
        b.goto(site("form.html"))
        snap = b.snapshot().text
        b.select_ref(ref_of(snap, "Country"), "Germany")
        assert b.page.input_value("#country") == "de"
        assert "not a dropdown" in _err(lambda: b.select_ref(ref_of(snap, "Order form"), "x"))


def _err(fn):
    try:
        fn()
    except Exception as exc:
        return str(exc)
    raise AssertionError("expected an error")
