import json

import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse import flow as fl
from selfbrowse.cli import main
from tests.conftest import ScriptedLLM


def make_flow(**over):
    data = {"selfbrowse_flow": 1, "name": "t", "domains": ["example.com"],
            "steps": [{"do": "goto", "url": "https://example.com/"}]}
    data.update(over)
    return data


# ── the file format ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("change, message", [
    ({"steps": [{"do": "eval", "code": "1"}]}, "unknown step kind"),
    ({"steps": [{"do": "goto", "url": "file:///etc/passwd"}]}, r"http\(s\)"),
    ({"steps": [{"do": "goto", "url": "https://example.com/{{city}}"}]}, "not a declared parameter"),
    ({"steps": [{"do": "type", "target": {"role": "textbox", "text": "x"}, "text": "<secret:PW>"}]}, "not listed under secrets"),
    ({"steps": [{"do": "click"}]}, "click needs target"),
    ({"steps": [{"do": "wait", "run": "x"}]}, "unexpected field"),
    ({"steps": []}, "no steps"),
    ({"domains": []}, "must list its domains"),
    ({"selfbrowse_flow": 2}, "not a selfbrowse flow"),
])
def test_validation_rejects(change, message):
    with pytest.raises(fl.FlowError, match=message):
        fl.validate_flow(make_flow(**change))


def test_load_rejects_oversized_and_broken_files(tmp_path):
    big = tmp_path / "big.json"
    big.write_text(" " * (fl.MAX_FILE_BYTES + 1))
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    for path, message in ((big, "not a normal flow"), (bad, "not valid JSON"), (tmp_path / "none.json", "cannot read")):
        with pytest.raises(fl.FlowError, match=message):
            fl.load_flow(path)


# ── recording ────────────────────────────────────────────────────────────────────

def target(text, role="textbox", nth=0, of=1):
    return {"role": role, "text": text, "nth": nth, "of": of}


def test_typed_values_become_parameters_and_secrets_stay_names():
    rec = fl.FlowRecorder("find a fare", "https://x.example/")
    rec.add("type", {"ref": 1, "text": "COK"}, url_before="https://x.example/", url_after="https://x.example/", target=target("From"))
    rec.add("type", {"ref": 2, "text": "<secret:PW>"}, url_before="https://x.example/", url_after="https://x.example/", target=target("Password"))
    rec.add("type", {"ref": 3, "text": "<EMAIL_1>"}, url_before="https://x.example/", url_after="https://x.example/", target=target("Email"))
    flow = rec.build()
    assert flow["params"]["from"] == {"label": "From", "default": "COK"}
    assert flow["params"]["email"] == {"label": "Email", "required": True}      # never a default: it is personal data
    assert flow["secrets"] == ["PW"]
    assert [s["text"] for s in flow["steps"][1:]] == ["{{from}}", "<secret:PW>", "{{email}}"]
    assert flow["domains"] == ["x.example"]


def test_detours_and_extra_reads_are_dropped():
    rec = fl.FlowRecorder("t", "https://x.example/")
    a, b = "https://x.example/", "https://x.example/wrong"
    rec.add("click", {"ref": 1}, url_before=a, url_after=b, target=target("Wrong", "link"))
    rec.add("back", {}, url_before=b, url_after=a)
    rec.add("read", {}, url_before=a, url_after=a)
    rec.add("click", {"ref": 2}, url_before=a, url_after="https://x.example/right", target=target("Right", "link"))
    rec.add("read", {"full": True}, url_before="https://x.example/right", url_after="https://x.example/right")
    rec.add("remember", {"fact": "x"}, url_before=a, url_after=a)
    steps = rec.build()["steps"]
    assert [s["do"] for s in steps] == ["goto", "click", "read"]
    assert steps[1]["target"]["text"] == "Right" and steps[2] == {"do": "read", "full": True}


def test_runner_needs_every_parameter_and_secret():
    flow = make_flow(params={"email": {"required": True}}, secrets=["PW"],
                     steps=[{"do": "type", "target": target("e"), "text": "{{email}}"},
                            {"do": "type", "target": target("p"), "text": "<secret:PW>"}])
    with pytest.raises(fl.FlowError, match="has no default"):
        fl.FlowRunner(flow, None, secrets={"PW": "x"})
    with pytest.raises(fl.FlowError, match="SELFBROWSE_SECRET_PW"):
        fl.FlowRunner(flow, None, params={"email": "a@b.c"})
    with pytest.raises(fl.FlowError, match="unknown parameter"):
        fl.FlowRunner(flow, None, params={"email": "a", "nope": "b"}, secrets={"PW": "x"})


def test_a_flow_cannot_leave_its_sites():
    flow = make_flow(steps=[{"do": "goto", "url": "https://evil.test/"}])
    result = fl.FlowRunner(flow, object()).run()
    assert not result.success and result.failed_step == 1 and "evil.test" in result.error


# ── with a real browser ──────────────────────────────────────────────────────────

pytestmark_browser = pytest.mark.browser


@pytest.fixture
def recorded(site, tmp_path):
    """Record 'search a fare' once with a scripted model, and return the flow file."""
    path = tmp_path / "fare.json"
    with Browser(channel=None) as b:
        b.goto(site("flow_search.html"))
        refs = {l.split('"')[1]: int(l.split()[0][1:]) for l in b.snapshot().text.splitlines() if l.startswith("#")}
        llm = ScriptedLLM([
            ("type", {"ref": refs["From"], "text": "COK"}),
            ("type", {"ref": refs["To"], "text": "SFO"}),
            ("type", {"ref": refs["Password"], "text": "<secret:PW>"}),
            ("click", {"ref": refs["Search"]}),
            ("read", {}),
            ("done", {"success": True, "answer": "Fares COK to SFO"}),
        ])
        agent = BrowseAgent("find a fare", llm=llm, browser=b, home=tmp_path, save_flow=path, sensitive={"PW": "hunter2"})
        res = agent.run()
    assert res.success and agent.flow_path == path
    return path


@pytest.mark.browser
def test_recorded_flow_replays_with_no_model(recorded, site):
    text = recorded.read_text()
    assert "hunter2" not in text                                  # the secret value is never written
    flow = fl.load_flow(recorded)
    assert flow["secrets"] == ["PW"] and set(flow["params"]) == {"from", "to"}
    assert [s["do"] for s in flow["steps"]] == ["goto", "type", "type", "type", "click", "read"]

    with Browser(channel=None) as b:
        result = fl.FlowRunner(flow, b, secrets={"PW": "hunter2"}).run()
    assert result.success and result.steps_run == 6
    assert "Fares COK to SFO" in result.output and "password length 7" in result.output

    with Browser(channel=None) as b:                              # same flow, other airports
        result = fl.FlowRunner(flow, b, params={"from": "BLR", "to": "LHR"}, secrets={"PW": "hunter2"}).run()
    assert "Fares BLR to LHR" in result.output


@pytest.mark.browser
def test_flow_stops_and_names_the_step_when_the_page_changed(recorded):
    flow = fl.load_flow(recorded)
    flow["steps"][3]["target"]["text"] = "Sign in"                # the page no longer has this control
    with Browser(channel=None) as b:
        result = fl.FlowRunner(flow, b, secrets={"PW": "x"}, find_attempts=1).run()
    assert not result.success and result.failed_step == 4 and "Sign in" in result.error


@pytest.mark.browser
def test_risky_click_needs_a_person(recorded, site):
    flow = fl.load_flow(recorded)
    flow["steps"].append({"do": "click", "target": {"role": "button", "text": "Buy now", "nth": 0, "of": 1}})
    with Browser(channel=None) as b:
        result = fl.FlowRunner(flow, b, secrets={"PW": "x"}).run()
    assert not result.success and result.failed_step == 7 and "no person is available" in result.error
    asked = []
    with Browser(channel=None) as b:
        result = fl.FlowRunner(flow, b, secrets={"PW": "x"}, handler=lambda req: asked.append(req.reason) or True).run()
    assert result.success and asked and "Buy now" in asked[0]


@pytest.mark.browser
def test_cli_show_and_run(recorded, monkeypatch, capsys):
    assert main(["flow", "show", str(recorded)]) == 0
    shown = capsys.readouterr().out
    assert "from='COK'" in shown and "secrets: PW" in shown and "<secret>" in shown and "hunter2" not in shown
    monkeypatch.setenv("SELFBROWSE_SECRET_PW", "abc")
    assert main(["flow", "run", str(recorded), "--param", "to=NRT", "--json", "-q"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["success"] and "Fares COK to NRT" in out["output"]
    assert main(["flow", "run", str(recorded), "--param", "nope=1", "-q"]) == 2
