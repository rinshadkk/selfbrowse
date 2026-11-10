import json

import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.cli import main
from tests.conftest import ScriptedLLM


@pytest.mark.browser
def test_one_image_per_step_and_an_index(site, tmp_path):
    with Browser() as b:
        b.goto(site("profile.html"))
        llm = ScriptedLLM([("read", {}), ("scroll", {"direction": "down"}), ("done", {"answer": "ok", "success": True})])
        agent = BrowseAgent("look around", llm=llm, browser=b, home=tmp_path, learn=False, screenshots=tmp_path / "ev")
        res = agent.run()
    d = agent.screenshots_dir
    assert d and d.parent == tmp_path / "ev" and d.name.startswith("run-")
    assert [s.screenshot for s in res.history] == ["step-01.jpg", "step-02.jpg", "step-03.jpg"]
    for s in res.history:
        assert (d / s.screenshot).read_bytes()[:2] == b"\xff\xd8"          # a real JPEG
    page = (d / "index.html").read_text()
    assert "look around" in page and "step-03.jpg" in page and "succeeded" in page
    assert oct(d.stat().st_mode & 0o777) == "0o700"


@pytest.mark.browser
def test_each_run_gets_its_own_folder(site, tmp_path):
    dirs = []
    for _ in range(2):
        with Browser() as b:
            b.goto(site("profile.html"))
            llm = ScriptedLLM([("done", {"answer": "ok", "success": True})])
            a = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False, screenshots=tmp_path / "ev")
            a.run()
            dirs.append(a.screenshots_dir)
    assert dirs[0] != dirs[1] and all(d.is_dir() for d in dirs)


@pytest.mark.browser
def test_images_are_never_sent_to_the_model_and_off_by_default(site, tmp_path):
    with Browser() as b:
        b.goto(site("profile.html"))
        llm = ScriptedLLM([("read", {}), ("done", {"answer": "ok", "success": True})])
        agent = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False)
        res = agent.run()
    assert agent.screenshots_dir is None and all(s.screenshot == "" for s in res.history)
    assert not (tmp_path / "ev").exists()


@pytest.mark.browser
def test_a_failed_capture_does_not_stop_the_run(site, tmp_path, monkeypatch):
    with Browser() as b:
        b.goto(site("profile.html"))
        monkeypatch.setattr(b, "save_screenshot", lambda path: False)
        llm = ScriptedLLM([("done", {"answer": "ok", "success": True})])
        agent = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False, screenshots=tmp_path / "ev")
        res = agent.run()
    assert res.success and res.history[0].screenshot == ""
    assert "no screenshot" in (agent.screenshots_dir / "index.html").read_text()


@pytest.mark.browser
def test_screenshot_event_is_in_the_trace(site, tmp_path):
    with Browser() as b:
        b.goto(site("profile.html"))
        llm = ScriptedLLM([("done", {"answer": "ok", "success": True})])
        agent = BrowseAgent("t", llm=llm, browser=b, home=tmp_path, learn=False, trace=True, screenshots=tmp_path / "ev")
        agent.run()
    events = [json.loads(line) for line in agent.trace_path.read_text().splitlines()]
    shots = [e for e in events if e["type"] == "screenshot"]
    assert len(shots) == 1 and shots[0]["path"].endswith("step-01.jpg")


def test_cli_flag_is_accepted(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0 and "--screenshots DIR" in capsys.readouterr().out
