import textwrap

import pytest

from selfbrowse import BrowseAgent, Browser
from selfbrowse.cli import main
from selfbrowse.llm import LLMError, make_llm

MODEL = textwrap.dedent('''
    from selfbrowse.llm.base import LLMResponse
    from selfbrowse.types import Usage

    class Fixed:
        model = "fixed"
        def __init__(self, calls=None):
            self.script = [("goto", {{"url": "{url}"}}), ("done", {{"answer": "Demo Shop", "success": True}})]
        def complete(self, *, system, messages, tools, max_tokens=2048):
            name, args = self.script.pop(0)
            return LLMResponse(content=[{{"type": "tool_use", "id": "t", "name": name, "input": args}}],
                               stop_reason="tool_use", usage=Usage(input_tokens=1, output_tokens=1, calls=1))

    def build():
        return Fixed()

    instance = Fixed()
    not_a_model = 42
''')


def write(tmp_path, url="http://127.0.0.1:1/"):
    f = tmp_path / "my_llm.py"
    f.write_text(MODEL.format(url=url))
    return f


def test_a_file_path_with_a_class(tmp_path):
    f = write(tmp_path)
    llm = make_llm(f"{f}:Fixed")
    assert llm.model == "fixed" and callable(llm.complete)


def test_a_function_that_builds_the_model_and_a_ready_instance(tmp_path):
    f = write(tmp_path)
    assert make_llm(f"{f}:build").model == "fixed"
    assert make_llm(f"{f}:instance").model == "fixed"


def test_a_module_name_next_to_where_you_run(tmp_path, monkeypatch):
    write(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    assert make_llm("my_llm:Fixed").model == "fixed"


def test_a_model_object_passes_through_unchanged(tmp_path):
    f = write(tmp_path)
    llm = make_llm(f"{f}:Fixed")
    assert make_llm(llm) is llm


@pytest.mark.parametrize("spec, words", [
    ("antropic:claude-haiku-4-5", "Unknown provider or module"),       # a typo in a built-in provider
    ("/no/such/file.py:Thing", "No such file"),
    ("justaname", "provider:model"),
])
def test_helpful_errors(spec, words):
    with pytest.raises(LLMError, match=words):
        make_llm(spec)


def test_errors_for_a_bad_name_or_a_non_model(tmp_path):
    f = write(tmp_path)
    with pytest.raises(LLMError, match="has no 'Nope'"):
        make_llm(f"{f}:Nope")
    with pytest.raises(LLMError, match="not a model"):
        make_llm(f"{f}:not_a_model")


def test_a_broken_file_reports_the_cause(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("raise RuntimeError('boom')\n")
    with pytest.raises(LLMError, match="boom"):
        make_llm(f"{f}:X")


def test_built_in_providers_still_win():
    assert make_llm("ollama:qwen3.6").model == "qwen3.6"


@pytest.mark.browser
def test_the_agent_runs_a_task_with_a_model_from_a_file(site, tmp_path):
    f = write(tmp_path, site("shop.html"))
    with Browser() as b:
        res = BrowseAgent("heading?", llm=f"{f}:Fixed", browser=b, home=tmp_path, learn=False).run()
    assert res.success and res.output == "Demo Shop"


@pytest.mark.browser
def test_the_command_line_accepts_a_model_from_a_file(site, tmp_path, capsys, monkeypatch):
    f = write(tmp_path, site("shop.html"))
    monkeypatch.setenv("SELFBROWSE_HOME", str(tmp_path / "home"))
    code = main(["--model", f"{f}:Fixed", "--no-learn", "--quiet", "what is the heading"])
    assert code == 0 and "Demo Shop" in capsys.readouterr().out


def test_the_mcp_server_accepts_a_model_from_a_file(tmp_path):
    from selfbrowse.mcp_server import parse_args
    f = write(tmp_path)
    cfg = parse_args(["--model", f"{f}:Fixed"])
    assert make_llm(cfg.model).model == "fixed"
