"""Backend checks: auth, the event stream, and Stop. Uses a scripted model, so no API key and no network.

Run from the desktop folder:  backend/.venv/bin/python -m pytest backend -q
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

import server
from selfbrowse.llm.base import LLMResponse
from selfbrowse.types import Usage

H = {"Authorization": f"Bearer {server._TOKEN}"}


class Script:
    model = "scripted"

    def __init__(self, calls, delay=0.0):
        self.calls, self.delay = list(calls), delay

    def complete(self, *, system, messages, tools, max_tokens=2048):
        time.sleep(self.delay)
        name, args = self.calls.pop(0)
        return LLMResponse(content=[{"type": "tool_use", "id": "t", "name": name, "input": args}],
                           stop_reason="tool_use", usage=Usage(input_tokens=10, output_tokens=5, calls=1))


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SELFBROWSE_HOME", str(tmp_path))
    monkeypatch.setenv("SB_DESKTOP_DATA", str(tmp_path / "desktop"))
    server.RUNS.clear()
    yield TestClient(server.app, base_url="http://127.0.0.1")
    for _ in range(100):                               # a run from this test may still be shutting its browser down
        if server._RUN_LOCK.acquire(blocking=False):
            server._RUN_LOCK.release()
            break
        time.sleep(0.1)
    server.close_idle_sessions()                       # an answered run keeps its browser open; do not leak it past the test


def _events(client, run_id):
    text = client.get(f"/runs/{run_id}/events", headers=H).text
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def _patch_agent(monkeypatch, script):
    monkeypatch.setattr(server, "make_llm", lambda spec: script)


def test_needs_the_token(client):
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers=H).json() == {"status": "ok"}


def test_empty_prompt_is_refused(client):
    r = client.post("/runs", headers=H, json={"prompt": "  "})
    assert r.status_code == 400 and "prompt" in r.json()["detail"]


def test_run_streams_steps_then_done(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("goto", {"url": "data:text/html,<h1>hi</h1>"}),
                                      ("done", {"success": True, "answer": "all good"})]))
    run = client.post("/runs", headers=H, json={"prompt": "say hi", "headed": False}).json()["id"]
    events = _events(client, run)
    assert [e["type"] for e in events][-1] == "done"
    assert any(e["type"] == "step" and e["tool"] == "goto" for e in events)
    done = events[-1]
    assert done["success"] is True and done["output"] == "all good"


def test_stop_ends_the_run(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0})] * 30, delay=0.2))
    run = client.post("/runs", headers=H, json={"prompt": "loop", "headed": False}).json()["id"]
    time.sleep(0.8)
    assert client.post(f"/runs/{run}/stop", headers=H).status_code == 200
    done = _events(client, run)[-1]
    assert done["type"] == "done" and done["error"] == "Stopped by you."


def test_bad_key_shows_an_error_not_a_crash(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run = client.post("/runs", headers=H, json={"prompt": "x", "headed": False}).json()["id"]
    done = _events(client, run)[-1]
    assert done["success"] is False and "ANTHROPIC_API_KEY" in done["error"]


def test_token_in_the_url_is_not_accepted(client):
    assert client.get(f"/health?token={server._TOKEN}").status_code == 401


def test_a_foreign_host_name_is_refused(client):          # DNS rebinding: the page's own name resolves to 127.0.0.1
    r = client.get("/health", headers={**H, "Host": "evil.example.com"})
    assert r.status_code == 400


def test_only_the_app_origin_may_read_responses(client):
    ok = client.options("/health", headers={"Origin": "null", "Access-Control-Request-Method": "GET"})
    bad = client.options("/health", headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "null"
    assert "access-control-allow-origin" not in bad.headers


def test_inputs_are_bounded(client):
    for body in ({"prompt": "x" * 10_001}, {"prompt": "x", "max_steps": 100000}, {"prompt": "x", "model": "a b; rm -rf"}):
        assert client.post("/runs", headers=H, json=body).status_code == 422


def test_only_one_run_at_a_time(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0})] * 30, delay=0.2))
    first = client.post("/runs", headers=H, json={"prompt": "a", "headed": False})
    assert first.status_code == 200
    assert client.post("/runs", headers=H, json={"prompt": "b", "headed": False}).status_code == 409
    client.post(f"/runs/{first.json()['id']}/stop", headers=H)
    _events(client, first.json()["id"])               # wait for it to finish
    third = client.post("/runs", headers=H, json={"prompt": "c", "headed": False})
    assert third.status_code == 200
    client.post(f"/runs/{third.json()['id']}/stop", headers=H)
    _events(client, third.json()["id"])


# ── live view and taking over ───────────────────────────────────────────────────────────────
PAGE = (b"<!doctype html><title>Live</title><button onclick=\"location.hash='clicked'\" "
        b"style=\"position:fixed;left:0;top:0;width:400px;height:300px\">go</button>")


@pytest.fixture(scope="module")
def page_url():
    """A local page with one big button. Selfbrowse refuses data: pages, so the tests serve it over http."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/"
    srv.shutdown()


@pytest.fixture(autouse=True)
def _preload(monkeypatch, page_url):
    """Every browser these tests start opens the page first, as a person's start page would be."""
    class Preloaded(server.Browser):
        def start(self):
            super().start()
            self.page.goto(page_url)
            return self

    monkeypatch.setattr(server, "Browser", Preloaded)
    monkeypatch.setattr(server, "installed_chrome", lambda: False)    # tests use the bundled browser, not whatever is installed


def _wait_for(client, run_id, predicate, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        found = [e for e in server.RUNS[run_id].events if predicate(e)]
        if found:
            return found[0]
        time.sleep(0.05)
    raise AssertionError(f"timed out; events so far: {server.RUNS[run_id].events}")


def _start(client, **body):
    return client.post("/runs", headers=H, json={"prompt": "x", **body}).json()["id"]


def _frames(client, run_id):
    text = client.get(f"/runs/{run_id}/frames", headers=H).text
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_the_browser_is_mirrored_as_frames(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0}), ("done", {"success": True, "answer": "ok"})], delay=0.4))
    run = _start(client)
    frames = _frames(client, run)
    assert frames, "no frame arrived"
    assert frames[-1]["jpeg"].startswith("/9j/") and frames[-1]["w"] > 0 and frames[-1]["h"] > 0


def test_input_is_refused_until_you_take_control(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0})] * 20, delay=0.2))
    run = _start(client)
    _wait_for(client, run, lambda e: e["type"] == "step")
    r = client.post(f"/runs/{run}/input", headers=H, json=[{"t": "move", "x": 1, "y": 1}])
    assert r.status_code == 409
    client.post(f"/runs/{run}/stop", headers=H)
    _events(client, run)


def test_you_can_take_over_and_click_in_the_live_view(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0})] * 7 + [("done", {"success": True, "answer": "ok"})], delay=0.3))
    run = _start(client)
    _wait_for(client, run, lambda e: e["type"] == "step")
    client.post(f"/runs/{run}/control", headers=H, json={"on": True})
    _wait_for(client, run, lambda e: e["type"] == "paused" and e["paused"])          # the agent waits for you
    n = len([e for e in server.RUNS[run].events if e["type"] == "step"])
    time.sleep(0.8)
    assert len([e for e in server.RUNS[run].events if e["type"] == "step"]) == n, "the agent kept going"
    ev = [{"t": "move", "x": 100, "y": 100}, {"t": "down", "x": 100, "y": 100}, {"t": "up", "x": 100, "y": 100}]
    assert client.post(f"/runs/{run}/input", headers=H, json=ev).status_code == 200
    time.sleep(0.5)
    client.post(f"/runs/{run}/control", headers=H, json={"on": False})
    events = _events(client, run)
    assert events[-1]["success"] is True
    assert any(e["type"] == "step" and e["url"].endswith("#clicked") for e in events), "the click did not reach the page"


def test_a_hand_off_waits_for_you_then_continues(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0}), ("ask_human", {"reason": "log in"}),
                                      ("done", {"success": True, "answer": "ok"})], delay=0.1))
    run = _start(client)
    ask = _wait_for(client, run, lambda e: e["type"] == "handoff")
    assert ask["reason"] and ask["kind"] in ("model", "challenge", "confirm")
    assert client.post(f"/runs/{run}/input", headers=H, json=[{"t": "move", "x": 5, "y": 5}]).status_code == 200  # control is on
    client.post(f"/runs/{run}/handoff", headers=H, json={"resume": True})
    events = _events(client, run)
    assert events[-1]["type"] == "done" and events[-1]["success"] is True


def test_stop_interrupts_a_model_call_in_progress(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0})], delay=4))
    run = _start(client)
    time.sleep(1.5)                                    # the browser is up and the (slow) model call has started
    started = time.time()
    client.post(f"/runs/{run}/stop", headers=H)
    done = _events(client, run)[-1]
    assert done["error"] == "Stopped by you." and time.time() - started < 2.5


def test_input_events_are_validated(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0})] * 20, delay=0.2))
    run = _start(client)
    _wait_for(client, run, lambda e: e["type"] == "step")
    client.post(f"/runs/{run}/control", headers=H, json={"on": True})
    for bad in ([{"t": "exec", "x": 1}], [{"t": "key", "key": "a; rm -rf /"}], [{"t": "move", "x": -5}],
                [{"t": "move", "x": 1, "y": 1}] * 51):
        assert client.post(f"/runs/{run}/input", headers=H, json=bad).status_code == 422
    client.post(f"/runs/{run}/control", headers=H, json={"on": False})
    client.post(f"/runs/{run}/stop", headers=H)
    _events(client, run)


# ── what was sent to the model, approval, flows ─────────────────────────────────────────────
def test_each_call_is_recorded_with_its_usage(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0}), ("done", {"success": True, "answer": "ok"})]))
    run = _start(client, sensitive={"CITY": "Chicago"})
    events = _events(client, run)
    calls = [e for e in events if e["type"] == "call"]
    done = [e for e in events if e["type"] == "call_done"]
    assert len(calls) == 2 and len(done) == 2
    assert done[0]["usage"] == {"input": 10, "cache_read": 0, "cache_write": 0, "output": 5} and "wait" in done[0]["reply"]
    table = {**calls[0]["new"], **calls[1]["new"]}
    assert [table[i]["role"] for i in calls[0]["ids"]][0] == "system"
    assert calls[1]["ids"][0] == calls[0]["ids"][0], "the instructions are the same every call, so stored once"
    assert calls[1]["new"].keys().isdisjoint(calls[0]["new"]), "a message is only sent to the window once"
    assert any("CITY" in m["refs"] for m in table.values()), "the model should be offered the name"
    assert not any("Chicago" in m["text"] for m in table.values()), "the value must never be in what was sent"


def test_personal_text_that_was_sent_is_flagged(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = _start(client, prompt="Email ava.moreno@example.com and call (312) 555-0148 about 4111 1111 1111 1111",
                 sensitive={"NAME": "Ava Moreno"})
    call = [e for e in _events(client, run) if e["type"] == "call"][0]
    flags = [f for m in call["new"].values() for f in m["flags"]]
    assert {f["kind"] for f in flags} >= {"email", "phone", "card"}


def test_a_value_from_my_info_that_reaches_the_model_is_flagged(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = _start(client, prompt="Ship it to Ava Moreno", sensitive={"FULL_NAME": "Ava Moreno"})
    call = [e for e in _events(client, run) if e["type"] == "call"][0]
    assert any(f["kind"] == "value" and f["name"] == "FULL_NAME" for m in call["new"].values() for f in m["flags"])


def test_bad_secret_names_are_refused(client):
    assert client.post("/runs", headers=H, json={"prompt": "x", "sensitive": {"a b": "v"}}).status_code == 422
    assert client.post("/runs", headers=H, json={"prompt": "x", "sensitive": {"A": "v" * 501}}).status_code == 422


def test_a_held_call_waits_for_your_ok(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = _start(client, review=True)
    held = _wait_for(client, run, lambda e: e["type"] == "call")
    assert held["holding"] is True
    time.sleep(0.8)
    assert not any(e["type"] == "call_done" for e in server.RUNS[run].events), "it was sent without approval"
    client.post(f"/runs/{run}/call", headers=H, json={"send": True})
    events = _events(client, run)
    assert any(e["type"] == "call_sent" for e in events) and events[-1]["success"] is True


def test_refusing_a_held_call_stops_the_run_before_anything_is_sent(client, monkeypatch):
    script = Script([("done", {"success": True, "answer": "ok"})])
    _patch_agent(monkeypatch, script)
    run = _start(client, review=True)
    _wait_for(client, run, lambda e: e["type"] == "call")
    client.post(f"/runs/{run}/call", headers=H, json={"send": False})
    events = _events(client, run)
    assert events[-1]["error"] == "Stopped by you."
    assert len(script.calls) == 1, "the model was called anyway"


def test_save_a_run_as_a_flow_and_replay_it_for_free(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("goto", {"url": page_url}), ("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    done = _events(client, run)[-1]
    assert done["success"] and done["can_save_flow"]
    saved = client.post(f"/runs/{run}/save-flow", headers=H, json={"name": "Open the page"})
    assert saved.status_code == 200
    flow_id = saved.json()["id"]
    assert [f["id"] for f in client.get("/flows", headers=H).json()] == [flow_id]
    rerun = client.post(f"/flows/{flow_id}/run", headers=H, json={}).json()["id"]
    events = _events(client, rerun)
    assert events[-1]["type"] == "done" and events[-1]["tokens"] == 0 and events[-1]["success"] is True
    assert client.delete(f"/flows/{flow_id}", headers=H).status_code == 200
    assert client.get("/flows", headers=H).json() == []


def test_flow_ids_cannot_escape_the_flows_folder(client):
    for bad in ("..%2F..%2Fetc%2Fpasswd", "a.b", "A" * 70):
        assert client.delete(f"/flows/{bad}", headers=H).status_code in (404, 405)
        assert client.post(f"/flows/{bad}/share-check", headers=H, json={}).status_code == 404


def test_sharing_replaces_personal_values_the_recorder_missed():
    from selfbrowse.flow import FORMAT_VERSION
    flow = {"selfbrowse_flow": FORMAT_VERSION, "name": "Ship to Ava", "description": "Ship to ava@example.com", "domains": ["shop.test"],
            "params": {"note": {"label": "Note", "default": "call (312) 555-0148"}}, "secrets": [],
            "steps": [{"do": "goto", "url": "https://shop.test/"},
                      {"do": "type", "target": {"role": "textbox", "text": "City"}, "text": "Chicago"},
                      {"do": "type", "target": {"role": "textbox", "text": "Email"}, "text": "ava@example.com"},
                      {"do": "type", "target": {"role": "textbox", "text": "Street"}, "text": "<secret:STREET>"}]}
    flow["secrets"] = ["STREET"]
    safe, replaced = server.sanitize_flow(flow, {"CITY": "Chicago"})
    text = json.dumps(safe)
    assert "Chicago" not in text and "ava@example.com" not in text and "555-0148" not in text
    assert safe["steps"][1]["text"] == "<secret:CITY>" and "CITY" in safe["secrets"]
    assert safe["steps"][2]["text"].startswith("{{personal_") and safe["params"]["personal_1"]["required"]
    assert safe["params"]["note"].get("default") is None and safe["params"]["note"]["required"]
    assert {r["where"] for r in replaced} >= {"step 2", "step 3", "description"}
    assert flow["steps"][1]["text"] == "Chicago", "the original must not be changed"


# ── browser options: profile, installed Chrome, stealth ─────────────────────────────────────
def test_the_browser_gets_a_profile_and_the_installed_chrome(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(server, "Browser", lambda **kw: seen.update(kw))
    monkeypatch.setattr(server, "installed_chrome", lambda: True)
    monkeypatch.setenv("SB_DESKTOP_DATA", str(tmp_path))
    server.make_browser(server.BrowserOptions())
    assert seen == {"headless": True, "user_data_dir": tmp_path / "browser-profile", "channel": "chrome"}
    seen.clear()
    server.make_browser(server.BrowserOptions(profile=False, chrome=False, stealth=True), headed=True)
    assert seen == {"headless": False, "stealth": True}
    seen.clear()
    monkeypatch.setattr(server, "installed_chrome", lambda: False)
    server.make_browser(server.BrowserOptions(profile=False))
    assert "channel" not in seen, "no Chrome here, so use the bundled browser"


def test_stealth_without_its_package_says_how_to_install_it(client, monkeypatch):
    monkeypatch.setattr(server, "stealth_installed", lambda: False)
    r = client.post("/runs", headers=H, json={"prompt": "x", "stealth": True})
    assert r.status_code == 400 and "patchright" in r.json()["detail"]
    r = client.post("/flows/abc/run", headers=H, json={"stealth": True})
    assert r.status_code == 404                       # no such flow: the check order does not leak anything


def test_browser_info_and_clearing_the_profile(client, monkeypatch, tmp_path):
    for _ in range(100):                               # a run from an earlier test may still be shutting down
        if server._RUN_LOCK.acquire(blocking=False):
            server._RUN_LOCK.release()
            break
        time.sleep(0.1)
    p = server.profile_dir()
    p.mkdir(parents=True)
    (p / "Cookies").write_bytes(b"x" * 100)
    info = client.get("/browser-info", headers=H).json()
    assert info["profile_bytes"] == 100 and set(info) == {"chrome", "stealth", "presidio", "profile_bytes"}
    assert client.post("/browser-data/clear", headers=H).json() == {"cleared": True}
    assert not p.exists()
    assert client.get("/browser-info", headers=H).json()["profile_bytes"] == 0


def test_the_profile_cannot_be_cleared_while_a_run_uses_it(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("wait", {"seconds": 0})] * 30, delay=0.2))
    run = _start(client)
    assert client.post("/browser-data/clear", headers=H).status_code == 409
    client.post(f"/runs/{run}/stop", headers=H)
    _events(client, run)


# ── Presidio (optional personal-data detection) ──────────────────────────────────────────────
def test_presidio_findings_are_flagged_and_not_duplicated(monkeypatch):
    import record
    monkeypatch.setattr(record, "_presidio_scan", lambda t: [
        {"kind": "pii", "name": "person", "match": "Jane Doe"},
        {"kind": "pii", "name": "email address", "match": "jane@example.com"}])   # the email pattern already caught this
    found = record.scan("Ship to Jane Doe, jane@example.com", {}, presidio=True)
    assert sorted(f["name"] for f in found) == ["email address", "person"]
    assert record.scan("Ship to Jane Doe", {}, presidio=False) == []


def test_presidio_without_its_package_says_how_to_install_it(client, monkeypatch):
    import record
    monkeypatch.setattr(record, "presidio_available", lambda: False)
    r = client.post("/runs", headers=H, json={"prompt": "x", "presidio": True})
    assert r.status_code == 400 and "presidio-analyzer" in r.json()["detail"]


def test_install_presidio_from_the_app(client, monkeypatch):
    import record
    state = {"ok": False}
    calls = []
    monkeypatch.setattr(record, "presidio_available", lambda: state["ok"])

    class Done:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(cmd, **kw):
        calls.append(cmd[1:4])
        state["ok"] = len(calls) == 2
        return Done()
    monkeypatch.setattr(server.subprocess, "run", fake_run)
    assert client.get("/presidio/install", headers=H).json()["state"] == "idle"
    client.post("/presidio/install", headers=H)
    for _ in range(50):
        if client.get("/presidio/install", headers=H).json()["state"] == "done":
            break
        time.sleep(0.05)
    assert client.get("/presidio/install", headers=H).json() == {"state": "done", "error": ""}
    assert calls[0][:2] == ["-m", "pip"] and calls[1][:2] == ["-m", "spacy"]


# ── choosing a model, including a custom source ───────────────────────────────────────────────
def test_custom_source_builds_an_openai_compatible_model(monkeypatch):
    seen = {}

    class Fake:
        def __init__(self, model, **kw):
            seen.update(model=model, **kw)
    import selfbrowse.llm.openai_compat as oc
    monkeypatch.setattr(oc, "OpenAICompatLLM", Fake)
    req = server.RunRequest(prompt="x", model="my-model", api_key="k1",
                            custom={"base_url": "https://llm.example.com/v1", "json_mode": True})
    server.build_llm(req)
    assert seen == {"model": "my-model", "api_key": "k1", "base_url": "https://llm.example.com/v1",
                    "require_key": False, "json_mode": True}


def test_provider_key_from_the_app_is_passed_on(monkeypatch):
    seen = {}
    monkeypatch.setattr(server, "make_llm", lambda spec, **kw: seen.update(spec=spec, **kw) or "llm")
    server.build_llm(server.RunRequest(prompt="x", model="openai:gpt-4o-mini", api_key="sk-1"))
    assert seen == {"spec": "openai:gpt-4o-mini", "api_key": "sk-1"}
    seen.clear()
    server.build_llm(server.RunRequest(prompt="x", model="openai:gpt-4o-mini"))
    assert seen == {"spec": "openai:gpt-4o-mini"}


def test_custom_source_url_must_be_http(client):
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "llm.example.com", "https://a b"):
        r = client.post("/runs", headers=H, json={"prompt": "x", "model": "m", "custom": {"base_url": bad}})
        assert r.status_code == 422


def test_every_element_the_page_scripts_look_up_exists():
    """A script that looks up a missing element throws on load and the whole window goes dead."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent / "src" / "renderer"
    html = (root / "index.html").read_text()
    have = set(re.findall(r'\bid="([^"]+)"', html))
    for f in root.glob("*.js"):
        text = f.read_text()
        have |= set(re.findall(r"\bid: '([^']+)'", text))                # elements the scripts create themselves
    missing = {}
    for f in root.glob("*.js"):
        for ident in re.findall(r"\$\('([^']+)'\)", f.read_text()):
            if ident not in have:
                missing.setdefault(ident, f.name)
    assert not missing, missing


# ── a Chrome left behind by an earlier run must not lock every later run out ───────────────────
def _lock(profile, pid):
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "SingletonLock").symlink_to(f"host-{pid}")
    (profile / "SingletonCookie").symlink_to("123")


def test_stale_profile_lock_is_cleared(tmp_path):
    prof = tmp_path / "browser-profile"
    _lock(prof, 2_999_999)                              # no such process
    server.free_profile(prof)
    assert not (prof / "SingletonLock").is_symlink() and not (prof / "SingletonCookie").is_symlink()


def test_orphaned_browser_holding_the_profile_is_closed(tmp_path):
    import subprocess
    import sys
    prof = tmp_path / "browser-profile"
    orphan = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(prof)])
    try:
        _lock(prof, orphan.pid)
        server.free_profile(prof)
        assert orphan.wait(timeout=5) is not None and not (prof / "SingletonLock").is_symlink()
    finally:
        orphan.kill()


def test_someone_elses_browser_is_left_alone(tmp_path):
    import subprocess
    import sys
    prof = tmp_path / "browser-profile"
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        _lock(prof, other.pid)
        with pytest.raises(RuntimeError, match="another browser"):
            server.free_profile(prof)
        assert other.poll() is None
    finally:
        other.kill()


# ── reviewing a flow before saving it ────────────────────────────────────────────────────────
def test_review_a_flow_then_save_it_with_an_input(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("goto", {"url": page_url}), ("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    _events(client, run)
    draft = client.get(f"/runs/{run}/flow", headers=H).json()
    assert draft["flow"]["steps"][0]["do"] == "goto" and draft["lines"][0].startswith("goto ")
    steps = draft["flow"]["steps"] + [{"do": "find", "text": "{{word}}"}]
    saved = client.post(f"/runs/{run}/save-flow", headers=H, json={
        "name": "With input", "description": "d",
        "edited": {"params": {"word": {"label": "Word", "default": "hello"}}, "steps": steps}})
    assert saved.status_code == 200
    body = saved.json()
    assert body["params"]["word"]["default"] == "hello" and body["steps"] == len(steps) and body["description"] == "d"


def test_a_bad_edit_is_refused_with_a_reason(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("goto", {"url": page_url}), ("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    _events(client, run)
    steps = client.get(f"/runs/{run}/flow", headers=H).json()["flow"]["steps"] + [{"do": "find", "text": "{{nope}}"}]
    r = client.post(f"/runs/{run}/save-flow", headers=H, json={"name": "x", "edited": {"params": {}, "steps": steps}})
    assert r.status_code == 400 and "nope" in r.json()["detail"]
    r = client.post(f"/runs/{run}/save-flow", headers=H, json={"name": "x", "edited": {"params": {}, "steps": []}})
    assert r.status_code == 400 and client.get("/flows", headers=H).json() == []


# ── asking a model which values should be inputs ─────────────────────────────────────────────
def _suggest_body(steps, **extra):
    return {"model": "scripted", "steps": steps, "sensitive": {"HOME_CITY": "Springfield"}, **extra}


STEPS = [{"do": "goto", "url": "https://shop.example.com/search?email=jane@example.com&q=1"},
         {"do": "type", "target": {"role": "textbox", "text": "City"}, "text": "Springfield"},
         {"do": "type", "target": {"role": "textbox", "text": "Email"}, "text": "jane@example.com"},
         {"do": "type", "target": {"role": "textbox", "text": "Search"}, "text": "{{already}}"},
         {"do": "click", "target": {"role": "button", "text": "Go"}}]


def test_suggestion_preview_hides_personal_data_and_query_strings(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    _events(client, run)
    pre = client.post(f"/runs/{run}/suggest-inputs/preview", headers=H, json=_suggest_body(STEPS)).json()
    assert "jane@example.com" not in pre["text"] and "Springfield" not in pre["text"] and "q=1" not in pre["text"]
    assert "[removed: email address]" in pre["text"] and "(already an input)" in pre["text"]
    assert set(pre["hidden"]) == {"HOME_CITY", "email address"}


def test_suggestions_are_checked_before_they_are_returned(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    _events(client, run)
    asked = {}

    class Fake:
        def complete(self, **kw):
            asked.update(kw)
            return LLMResponse(content=[{"type": "tool_use", "id": "1", "name": "suggest_inputs", "input": {"inputs": [
                {"step": 2, "label": "City", "reason": "changes"},
                {"step": 4, "label": "Already"},        # already an input: refused
                {"step": 5, "label": "Go"},             # a click has no value: refused
                {"step": 99, "label": "Nowhere"},       # no such step: refused
                {"step": 2, "label": "Duplicate"}]}}], stop_reason="tool_use", usage=Usage())
    monkeypatch.setattr(server, "build_llm", lambda req: Fake())
    r = client.post(f"/runs/{run}/suggest-inputs", headers=H, json=_suggest_body(STEPS))
    assert r.json()["suggestions"] == [{"step": 2, "label": "City", "reason": "changes"}]
    sent = asked["messages"][0]["content"]
    assert "Springfield" not in sent and "jane@example.com" not in sent           # the model never saw them


def test_custom_source_can_speak_the_anthropic_api(monkeypatch):
    seen = {}

    class Fake:
        def __init__(self, model, **kw):
            seen.update(model=model, **kw)
    import selfbrowse.llm.anthropic as an
    monkeypatch.setattr(an, "AnthropicLLM", Fake)
    for url in ("http://127.0.0.1:3000", "http://127.0.0.1:3000/v1/"):
        server.build_llm(server.RunRequest(prompt="x", model="sonnet", custom={"base_url": url, "api": "anthropic"}))
        assert seen == {"model": "sonnet", "api_key": "not-needed", "base_url": "http://127.0.0.1:3000"}


# ── history ───────────────────────────────────────────────────────────────────────────────────
def test_a_finished_run_appears_in_history_without_the_pages_or_my_info(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("goto", {"url": page_url}), ("done", {"success": True, "answer": "the answer"})]))
    r = client.post("/runs", headers=H, json={"prompt": "Find it" + server.SHARED_MARK + "\nCity: Springfield", "model": "scripted"})
    run = r.json()["id"]
    _events(client, run)
    time.sleep(0.3)
    items = client.get("/history", headers=H).json()
    assert [i["id"] for i in items] == [run] and items[0]["prompt"] == "Find it" and items[0]["success"] is True
    full = client.get(f"/history/{run}", headers=H).json()
    assert full["answer"] == "the answer" and full["steps"] and full["calls"] >= 1
    assert "Springfield" not in json.dumps(full) and "?" not in full["steps"][0]["url"]


def test_history_can_be_switched_off_deleted_and_cleared(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    off = client.post("/runs", headers=H, json={"prompt": "x", "model": "scripted", "history": False}).json()["id"]
    _events(client, off)
    time.sleep(0.3)
    assert client.get("/history", headers=H).json() == []
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    on = _start(client)
    _events(client, on)
    time.sleep(0.3)
    assert len(client.get("/history", headers=H).json()) == 1
    assert client.delete(f"/history/{on}", headers=H).json() == {"deleted": True}
    assert client.get(f"/history/{on}", headers=H).status_code == 404
    assert client.delete("/history/..%2F..%2Fx", headers=H).status_code in (404, 405)
    assert client.delete("/history", headers=H).json() == {"deleted": 0}


def test_the_saved_details_note_is_not_kept_in_history(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    note = server.SAVED_MARK + " (type them with the placeholder):\n<secret:A_B> is Basic info › First name"
    run = client.post("/runs", headers=H, json={"prompt": "Apply for this job" + note, "model": "scripted"}).json()["id"]
    _events(client, run)
    time.sleep(0.3)
    assert client.get(f"/history/{run}", headers=H).json()["prompt"] == "Apply for this job"


def test_saved_details_reach_the_model_only_when_it_asks(client, monkeypatch, page_url):
    seen = []

    class Spy(Script):
        def complete(self, *, system, messages, tools, max_tokens=2048):
            seen.append((json.dumps(messages, ensure_ascii=False), [t["name"] for t in tools]))
            return super().complete(system=system, messages=messages, tools=tools, max_tokens=max_tokens)
    _patch_agent(monkeypatch, Spy([("goto", {"url": page_url}), ("find_saved_detail", {"what": "city"}),
                                   ("done", {"success": True, "answer": "ok"})]))
    run = _start(client, sensitive={"HOME_CITY": "Springfield", "HOME_PHONE": "555"},
                 labels={"HOME_CITY": "Home › City", "HOME_PHONE": "Home › Phone"})
    assert _events(client, run)[-1]["success"] is True
    first_msgs, tools = seen[0]
    assert "find_saved_detail" in tools
    assert "HOME_CITY" not in first_msgs and "Home › City" not in first_msgs and "Springfield" not in first_msgs
    later = seen[-1][0]
    assert "<secret:HOME_CITY> is Home › City" in later and "HOME_PHONE" not in later and "Springfield" not in later


def _lookup_result(client, monkeypatch, page_url, sites):
    seen = []

    class Spy(Script):
        def complete(self, *, system, messages, tools, max_tokens=2048):
            seen.append(json.dumps(messages, ensure_ascii=False))
            return super().complete(system=system, messages=messages, tools=tools, max_tokens=max_tokens)
    _patch_agent(monkeypatch, Spy([("goto", {"url": page_url}), ("find_saved_detail", {"what": "password"}),
                                   ("done", {"success": True, "answer": "ok"})]))
    run = _start(client, sensitive={"SHOP_PASSWORD": "hunter2"}, labels={"SHOP_PASSWORD": "Shop › Password"}, sensitive_sites=sites)
    assert _events(client, run)[-1]["success"] is True
    return seen[-1]


def test_a_value_saved_for_another_site_is_not_offered_on_this_page(client, monkeypatch, page_url):
    later = _lookup_result(client, monkeypatch, page_url, {"SHOP_PASSWORD": "shop.example.com"})
    assert "different site" in later and "SHOP_PASSWORD" not in later.split("different site")[-1] and "hunter2" not in later


def test_a_value_saved_for_this_site_is_offered(client, monkeypatch, page_url):
    later = _lookup_result(client, monkeypatch, page_url, {"SHOP_PASSWORD": "https://127.0.0.1:1/any/path"})
    assert "<secret:SHOP_PASSWORD> is Shop › Password" in later and "hunter2" not in later


def test_sites_are_written_in_any_common_form_and_bad_ones_are_refused(client):
    ok = client.post("/runs", headers=H, json={"prompt": "x", "model": "scripted", "sensitive": {"A": "1"},
                                                "sensitive_sites": {"A": "https://www.Walgreens.com/login"}})
    assert ok.status_code != 422
    for bad in ({"A": "not a site"}, {"A": ""}, {"bad name": "walgreens.com"}, {"A": "javascript:alert(1)"}):
        r = client.post("/runs", headers=H, json={"prompt": "x", "model": "scripted", "sensitive_sites": bad})
        assert r.status_code == 422, bad


# ── a flow replay with optional model help ───────────────────────────────────────────────────
def _save_flow_with_read(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("goto", {"url": page_url}), ("read", {}), ("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    _events(client, run)
    return client.post(f"/runs/{run}/save-flow", headers=H, json={"name": "Read it"}).json()["id"]


def test_replay_uses_no_model_unless_asked(client, monkeypatch, page_url):
    fid = _save_flow_with_read(client, monkeypatch, page_url)
    called = []
    monkeypatch.setattr(server, "build_llm", lambda req: called.append(1))
    done = _events(client, client.post(f"/flows/{fid}/run", headers=H, json={}).json()["id"])[-1]
    assert done["success"] and done["tokens"] == 0 and done["model_calls"] == 0 and not called


def test_replay_can_summarize_with_a_model_and_hides_personal_data(client, monkeypatch, page_url):
    fid = _save_flow_with_read(client, monkeypatch, page_url)
    seen = []

    class Summarizer:
        model = "scripted"

        def complete(self, *, system, messages, tools, max_tokens=2048):
            seen.append(json.dumps(messages, ensure_ascii=False))
            return LLMResponse(content=[{"type": "tool_use", "id": "1", "name": "answer", "input": {"answer": "A short summary."}}],
                               stop_reason="tool_use", usage=Usage(input_tokens=30, output_tokens=7, calls=1))
    monkeypatch.setattr(server, "build_llm", lambda req: Summarizer())
    r = client.post(f"/flows/{fid}/run", headers=H, json={
        "summarize": True, "model": "scripted", "ask": "Summarize this for jane@example.com, from Springfield",
        "sensitive": {"HOME_CITY": "Springfield"}})
    assert r.status_code == 200, r.text
    done = _events(client, r.json()["id"])[-1]
    assert done["success"] and done["output"] == "A short summary." and done["summarized"] is True
    assert done["model_calls"] == 1 and done["tokens"] == 37
    assert seen and "jane@example.com" not in seen[0] and "Springfield" not in seen[0]
    assert "[removed: email address]" in seen[0] and "[removed: HOME_CITY]" in seen[0]


def test_replay_with_a_model_option_needs_a_model(client, monkeypatch, page_url):
    fid = _save_flow_with_read(client, monkeypatch, page_url)
    r = client.post(f"/flows/{fid}/run", headers=H, json={"failover": True})
    assert r.status_code == 400 and "model" in r.json()["detail"].lower()


# ── review before sending: off, only when something looks personal, every call ───────────────
class Spy(Script):
    def __init__(self, calls):
        super().__init__(calls)
        self.sent = []

    def complete(self, *, system, messages, tools, max_tokens=2048):
        self.sent.append(json.dumps(messages, ensure_ascii=False))
        return super().complete(system=system, messages=messages, tools=tools, max_tokens=max_tokens)


def test_flagged_mode_does_not_hold_a_request_with_nothing_personal(client, monkeypatch, page_url):
    spy = Spy([("goto", {"url": page_url}), ("done", {"success": True, "answer": "ok"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="flagged", prompt="find the price of a stapler")
    events = _events(client, run)
    assert events[-1]["success"] is True and not any(e.get("holding") for e in events if e["type"] == "call")


def test_flagged_mode_holds_a_request_with_an_email_until_you_choose(client, monkeypatch, page_url):
    spy = Spy([("goto", {"url": page_url}), ("done", {"success": True, "answer": "ok"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="flagged", prompt="reply to jane@example.com")
    held = _wait_for(client, run, lambda e: e["type"] == "call")
    assert held["holding"] is True and held["mode"] == "flagged"
    assert [f["match"] for f in held["reason"]] == ["jane@example.com"]
    time.sleep(0.5)
    assert spy.sent == [], "it was sent without approval"
    client.post(f"/runs/{run}/call", headers=H, json={"send": True, "mask": False})
    events = _events(client, run)
    assert events[-1]["success"] is True and "jane@example.com" in spy.sent[0]


def test_send_masked_replaces_the_flagged_text_and_remembers_the_choice(client, monkeypatch, page_url):
    spy = Spy([("goto", {"url": page_url}), ("done", {"success": True, "answer": "ok"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="flagged", prompt="reply to jane@example.com")
    _wait_for(client, run, lambda e: e["type"] == "call")
    client.post(f"/runs/{run}/call", headers=H, json={"send": True, "mask": True})
    events = _events(client, run)
    calls = [e for e in events if e["type"] == "call"]
    assert events[-1]["success"] is True and len(calls) == 2
    assert all("jane@example.com" not in m and "<EMAIL_1>" in m for m in spy.sent)
    assert "placeholders like" in spy.sent[0]                             # the model is told how to use them
    assert calls[1]["holding"] is False                                   # the same text is not asked about again
    assert any(e["type"] == "call_masked" for e in events)


def test_a_masked_value_is_put_back_in_the_answer_you_read(client, monkeypatch, page_url):
    spy = Spy([("done", {"success": True, "answer": "I wrote to <EMAIL_1> as asked."})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="flagged", prompt="reply to jane@example.com")
    _wait_for(client, run, lambda e: e["type"] == "call")
    client.post(f"/runs/{run}/call", headers=H, json={"send": True, "mask": True})
    done = _events(client, run)[-1]
    assert "jane@example.com" not in spy.sent[0]                          # the model never saw it
    assert done["output"] == "I wrote to jane@example.com as asked."      # you do


def test_without_a_vault_masking_is_one_way_and_a_saved_value_becomes_its_placeholder():
    from live import LiveView, MirrorLLM
    m = MirrorLLM(Script([]), LiveView(), lambda: None)                  # no agent, so no vault
    tokens = m._tokens([{"kind": "email", "name": "email address", "match": "a@b.co"},
                        {"kind": "value", "name": "HOME_CITY", "match": "Springfield"}], {"ids": []})
    assert tokens == {"a@b.co": "[removed: email address]", "Springfield": "<secret:HOME_CITY>"}


def test_refusing_a_flagged_request_stops_the_run_and_sends_nothing(client, monkeypatch, page_url):
    spy = Spy([("done", {"success": True, "answer": "ok"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="flagged", prompt="reply to jane@example.com")
    _wait_for(client, run, lambda e: e["type"] == "call")
    client.post(f"/runs/{run}/call", headers=H, json={"send": False})
    assert _events(client, run)[-1]["error"] == "Stopped by you." and spy.sent == []


def test_every_call_mode_holds_even_a_clean_request_and_can_be_switched_off(client, monkeypatch, page_url):
    spy = Spy([("goto", {"url": page_url}), ("done", {"success": True, "answer": "ok"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="always", prompt="find the price of a stapler")
    held = _wait_for(client, run, lambda e: e["type"] == "call")
    assert held["holding"] is True and held["mode"] == "always"
    client.post(f"/runs/{run}/review", headers=H, json={"mode": "off"})      # switching it off releases the held call
    assert _events(client, run)[-1]["success"] is True and len(spy.sent) == 2


def test_you_can_replace_only_some_of_what_was_flagged(client, monkeypatch, page_url):
    spy = Spy([("done", {"success": True, "answer": "ok"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="flagged", prompt="write to jane@example.com or call (312) 555-0187")
    held = _wait_for(client, run, lambda e: e["type"] == "call")
    assert {f["match"] for f in held["reason"]} == {"jane@example.com", "(312) 555-0187"}
    client.post(f"/runs/{run}/call", headers=H, json={"send": True, "mask": True, "replace": ["jane@example.com"]})
    _events(client, run)
    assert "jane@example.com" not in spy.sent[0] and "<EMAIL_1>" in spy.sent[0]
    assert "(312) 555-0187" in spy.sent[0]                                  # left alone, as you chose


def test_the_model_is_told_to_write_placeholders_in_its_answer(client, monkeypatch, page_url):
    spy = Spy([("done", {"success": True, "answer": "ok"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="flagged", prompt="write to jane@example.com")
    _wait_for(client, run, lambda e: e["type"] == "call")
    client.post(f"/runs/{run}/call", headers=H, json={"send": True, "mask": True})
    _events(client, run)
    assert "write its placeholder exactly" in spy.sent[0]


# ── a follow-up carries on in the same run ───────────────────────────────────────────────────
def test_a_follow_up_continues_in_the_same_run_and_browser(client, monkeypatch, page_url):
    spy = Spy([("done", {"success": True, "answer": "First answer"}), ("done", {"success": True, "answer": "Second answer"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, prompt="find the lamp price")
    assert _events(client, run)[-1]["output"] == "First answer"
    browser = server.RUNS[run].session.browser
    r = client.post(f"/runs/{run}/followup", headers=H, json={"prompt": "and the desk price?"})
    assert r.status_code == 200
    events = _events(client, run)
    kinds = [e["type"] for e in events]
    assert kinds.count("done") == 2 and "turn" in kinds and events[-1]["output"] == "Second answer", events[-1].get("error")
    assert server.RUNS[run].session.browser is browser                       # the same browser, not a new one
    assert len(client.get("/history", headers=H).json()) == 1                # one run in History, not two
    second = spy.sent[1]
    assert "find the lamp price" in second and "First answer" in second and "and the desk price?" in second


def test_a_follow_up_needs_a_finished_run_with_its_browser(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    _events(client, run)
    time.sleep(0.2)
    assert client.post(f"/runs/{run}/close", headers=H).json() == {"closed": True}
    r = client.post(f"/runs/{run}/followup", headers=H, json={"prompt": "more"})
    assert r.status_code == 409 and "follow-up" in r.json()["detail"]
    assert client.post("/runs/nosuchrun/followup", headers=H, json={"prompt": "x"}).status_code == 404


def test_starting_a_new_run_closes_the_old_ones_browser(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"}), ("done", {"success": True, "answer": "ok"})]))
    first = _start(client)
    _events(client, first)
    time.sleep(0.2)
    assert server.RUNS[first].session is not None
    second = _start(client)
    _events(client, second)
    assert server.RUNS[first].session is None
    assert server.close_idle_sessions(max_age=0) in (0, 1)


def test_idle_browsers_are_closed_after_a_while(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    _events(client, run)
    time.sleep(0.2)
    assert server.close_idle_sessions(max_age=3600) == 0 and server.RUNS[run].session is not None
    server.RUNS[run].session.idle_since -= 7200
    assert server.close_idle_sessions(max_age=3600) == 1 and server.RUNS[run].session is None


def test_a_masked_value_means_the_same_thing_in_the_follow_up(client, monkeypatch, page_url):
    spy = Spy([("done", {"success": True, "answer": "Wrote to <EMAIL_1>"}), ("done", {"success": True, "answer": "Again to <EMAIL_1>"})])
    _patch_agent(monkeypatch, spy)
    run = _start(client, review_mode="flagged", prompt="reply to jane@example.com")
    _wait_for(client, run, lambda e: e["type"] == "call")
    client.post(f"/runs/{run}/call", headers=H, json={"send": True, "mask": True})
    assert _events(client, run)[-1]["output"] == "Wrote to jane@example.com"
    client.post(f"/runs/{run}/followup", headers=H, json={"prompt": "send it again"})
    done = _events(client, run)[-1]
    assert done["output"] == "Again to jane@example.com"                     # the same token, restored again
    assert "jane@example.com" not in spy.sent[1] and "<EMAIL_1>" in spy.sent[1]


def test_events_can_be_read_from_an_offset(client, monkeypatch, page_url):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = _start(client)
    full = _events(client, run)
    text = client.get(f"/runs/{run}/events?after={len(full) - 1}", headers=H).text
    tail = [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]
    assert [e["type"] for e in tail] == ["done"]


# ---- guardrail settings ----

def test_a_bad_site_name_is_refused(client):
    r = client.post("/runs", headers=H, json={"prompt": "x", "guards": {"allow": ["exa mple.com/<script>"]}})
    assert r.status_code == 422


def test_a_dollar_limit_needs_prices(client):
    r = client.post("/runs", headers=H, json={"prompt": "x", "guards": {"max_usd": 1}})
    assert r.status_code == 422
    ok = server.GuardSettings(max_usd=1, price_in=1, price_out=5)
    assert [g.name for g in ok.build()] == ["Budget"]


def test_settings_become_the_libraries_guardrails():
    g = server.GuardSettings(allow=["https://Example.com/"], block=["bad.test"], confirm_risky=True, watch_injection=True,
                             redact=["email", "card"], max_tokens=5000, max_seconds=60)
    names = [x.name for x in g.build()]
    assert names == ["AllowedDomains", "BlockedDomains", "ConfirmRisky", "RedactPII", "InjectionWatch", "Budget"]
    assert g.allow == ["example.com"]
    pii = [x for x in g.build() if x.name == "RedactPII"][0]
    assert pii.kinds == ("card", "email")


def test_nothing_set_adds_no_guardrails():
    assert server.GuardSettings().build() == []


def test_a_blocked_site_stops_the_run(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))      # the test browser starts on 127.0.0.1
    run = client.post("/runs", headers=H, json={"prompt": "go", "guards": {"block": ["127.0.0.1"]}}).json()["id"]
    done = _events(client, run)[-1]
    assert done["success"] is False and "BlockedDomains" in done["error"]


def test_a_site_outside_the_allowed_list_stops_the_run(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = client.post("/runs", headers=H, json={"prompt": "go", "guards": {"allow": ["example.org"]}}).json()["id"]
    done = _events(client, run)[-1]
    assert done["success"] is False and "AllowedDomains" in done["error"]


def test_an_allowed_site_runs(client, monkeypatch):
    _patch_agent(monkeypatch, Script([("done", {"success": True, "answer": "ok"})]))
    run = client.post("/runs", headers=H, json={"prompt": "go", "guards": {"allow": ["127.0.0.1"]}}).json()["id"]
    assert _events(client, run)[-1]["success"] is True


# ---- models installed on this computer ----

class _Reply:
    def __init__(self, data):
        self._d = json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._d


def test_installed_ollama_models_are_listed(client, monkeypatch):
    import urllib.request
    seen = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=0: seen.append(url) or _Reply(
        {"models": [{"name": "qwen3:latest", "size": 5}, {"name": "llama3.1:latest", "size": 4}, {"bad": 1}]}))
    r = client.get("/local-models/ollama", headers=H).json()
    assert r["ok"] and [m["name"] for m in r["models"]] == ["llama3.1:latest", "qwen3:latest"]
    assert seen == ["http://127.0.0.1:11434/api/tags"]


def test_lm_studio_models_are_listed(client, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=0: _Reply({"data": [{"id": "phi-4"}]}))
    r = client.get("/local-models/lmstudio", headers=H).json()
    assert r["ok"] and r["models"] == [{"name": "phi-4", "size": 0}]


def test_ollama_not_running_says_so(client, monkeypatch):
    import urllib.request

    def refuse(url, timeout=0):
        raise OSError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    r = client.get("/local-models/ollama", headers=H).json()
    assert r["ok"] is False and r["models"] == [] and "not running" in r["error"]


def test_only_known_local_sources_are_listed(client):
    assert client.get("/local-models/evil", headers=H).status_code == 422
    assert client.get("/local-models/ollama").status_code == 401


def test_ollama_host_may_only_point_at_this_computer(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "10.0.0.5:11434")
    assert server._local_base("ollama") == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "localhost:9999")
    assert server._local_base("ollama") == "http://localhost:9999"


# ---- the words that make a click risky ----

def _ask(g, text):
    from selfbrowse.guardrails import Action
    c = [x for x in g.build() if x.name == "ConfirmRisky"][0]
    return c.before_action(Action("click", {}, "http://x/", text=text)) is not None


def test_the_default_words_apply_when_none_are_set():
    g = server.GuardSettings(confirm_risky=True)
    assert _ask(g, "Delete account") and not _ask(g, "Proceed to payment")


def test_your_own_words_replace_the_defaults():
    g = server.GuardSettings(confirm_risky=True, risky_words=["Payment", " close   account ", "payment"])
    assert g.risky_words == ["payment", "close account"]
    assert _ask(g, "Proceed to payment") and _ask(g, "Close account") and not _ask(g, "Delete account")


def test_words_match_whole_words_and_are_not_patterns():
    g = server.GuardSettings(confirm_risky=True, risky_words=["pay", "a.c"])
    assert _ask(g, "Pay now") and not _ask(g, "Payment") and not _ask(g, "abc")


def test_an_empty_word_list_leaves_only_uploads_and_dialogs():
    from selfbrowse.guardrails import Action
    g = server.GuardSettings(confirm_risky=True, risky_words=[])
    assert not _ask(g, "Delete account")
    c = [x for x in g.build() if x.name == "ConfirmRisky"][0]
    assert c.before_action(Action("upload", {"file": "cv.pdf"}, "http://x/")) is not None


def test_too_long_a_word_is_refused(client):
    r = client.post("/runs", headers=H, json={"prompt": "x", "guards": {"confirm_risky": True, "risky_words": ["x" * 41]}})
    assert r.status_code == 422
