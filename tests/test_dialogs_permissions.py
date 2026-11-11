import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.browser import BrowserError, dialog_note
from selfbrowse.guardrails import ConfirmRisky
from tests.conftest import ScriptedLLM

pytestmark = pytest.mark.browser


def click(b, label):
    b.snapshot()
    ref = next(r for r, d in ((i, b.describe_ref(i)) for i in range(1, 12)) if d and d["text"] == label)
    return b.click_ref(ref)


def out(b):
    return b.page.inner_text("#o")


def test_alert_is_accepted_and_recorded(site):
    with Browser() as b:
        b.goto(site("dialogs.html"))
        click(b, "Save")
        assert out(b) == "alert:done"
        d = b.pop_dialogs()
        assert d == [{"type": "alert", "message": "Saved!", "action": "accepted"}]
        assert b.pop_dialogs() == []


def test_auto_declines_a_choice(site):
    with Browser() as b:
        b.goto(site("dialogs.html"))
        click(b, "Remove all")
        assert out(b) == "confirm:false"
        assert b.pop_dialogs()[0]["action"] == "dismissed"


def test_accept_policy_and_dismiss_policy(site):
    with Browser(dialogs="accept") as b:
        b.goto(site("dialogs.html"))
        click(b, "Next")
        assert out(b) == "ok-confirm:true"
    with Browser(dialogs="dismiss") as b:
        b.goto(site("dialogs.html"))
        click(b, "Save")
        assert b.pop_dialogs()[0]["action"] == "dismissed"


def test_guardrail_vetoes_a_risky_accept(site, tmp_path):
    llm = ScriptedLLM([("done", {"answer": "x", "success": True})])
    with Browser(dialogs="accept") as b:
        b.goto(site("dialogs.html"))
        agent = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, guardrails=[ConfirmRisky()], handoff=False)
        b.on_dialog = agent._dialog_veto
        click(b, "Remove all")                      # "Delete everything?" is risky, nobody can approve it
        assert out(b) == "confirm:false"
        assert b.pop_dialogs()[0].get("vetoed") is True
        click(b, "Next")                            # harmless: accepted
        assert out(b) == "ok-confirm:true"


def test_agent_tells_the_model_about_the_dialog(site, tmp_path):
    with Browser() as b:
        b.goto(site("dialogs.html"))
        b.snapshot()
        ref = next(i for i in range(1, 12) if (d := b.describe_ref(i)) and d["text"] == "Remove all")
        llm = ScriptedLLM([("click", {"ref": ref}), ("done", {"answer": "ok", "success": True})])
        res = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False).run()
    seen = str(llm.seen[1])
    assert "confirm dialog appeared" in seen and "Delete everything?" in seen and "dismissed" in seen
    assert res.success


def test_dialog_note_text():
    assert "vetoed" not in dialog_note([{"type": "confirm", "message": "Sure?", "action": "dismissed"}])
    assert "guardrail" in dialog_note([{"type": "confirm", "message": "x", "action": "dismissed", "vetoed": True}])


def test_notifications_and_geolocation_permissions(site):
    with Browser() as b:
        b.goto(site("dialogs.html"))
        click(b, "Notify me")
        b.page.wait_for_function("document.getElementById('o').textContent.startsWith('notif:')")
        assert out(b) != "notif:granted"
        click(b, "Where")
        b.page.wait_for_function("document.getElementById('o').textContent.startsWith('geo:')")
        assert out(b) != "geo:granted"
    with Browser(permissions=["notifications", "geolocation"]) as b:
        b.goto(site("dialogs.html"))
        click(b, "Notify me")
        b.page.wait_for_function("document.getElementById('o').textContent.startsWith('notif:')")
        assert out(b) == "notif:granted"
        click(b, "Where")
        b.page.wait_for_function("document.getElementById('o').textContent.startsWith('geo:')")
        assert out(b) == "geo:granted"


def test_unknown_permission_and_policy_are_rejected():
    with pytest.raises(BrowserError, match="notifcations"):
        Browser(permissions=["notifcations"])
    with pytest.raises(BrowserError, match="dialogs"):
        Browser(dialogs="maybe")


def test_a_dialog_is_recorded_once_even_when_the_page_event_fires_first(site):
    """On some platforms new_page() fires the context's page event before start() finishes."""
    with Browser() as b:
        b.goto(site("dialogs.html"))
        b._watch_dialogs(b.page)            # attaching again must not add a second listener
        click(b, "Save")
        assert len(b.pop_dialogs()) == 1
