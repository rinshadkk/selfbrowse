import pytest

from selfbrowse.tools import build_tools, extract_text_tool_call, looks_like_junk, normalize_args

T = {t["name"]: t for t in build_tools(human=True)}


@pytest.mark.parametrize("sent", [{"ref": 3}, {"id": "3"}, {"idx": 3}, {"selector": "button:3"}, {"element": "#3"}, {"ref": "3", "force": True}])
def test_click_accepts_common_variants(sent):
    assert normalize_args(T["click"], sent) == ({"ref": 3}, None)


def test_type_aliases_and_types():
    args, err = normalize_args(T["type"], {"id": 6, "txt": "alice", "enter": "true"})
    assert err is None and args == {"ref": 6, "text": "alice", "submit": True}


def test_done_aliases():
    assert normalize_args(T["done"], {"ok": "false", "result": "no"}) == ({"success": False, "answer": "no"}, None)


def test_missing_argument_says_what_is_needed():
    _, err = normalize_args(T["click"], {"foo": "bar"})
    assert err.startswith("Error: click needs ref") and '{"ref": 3}' in err


def test_bad_enum_says_valid_values():
    _, err = normalize_args(T["scroll"], {"direction": "sideways"})
    assert "must be one of" in err and "down" in err


def test_unfixable_type():
    _, err = normalize_args(T["click"], {"ref": "none"})
    assert err.startswith("Error:") and "integer" in err


TOOLS = list(T.values())


def test_extract_json_tool_call_in_text():
    assert extract_text_tool_call('{"name": "click", "parameters": {"ref": 4}}', TOOLS) == ("click", {"ref": 4})
    assert extract_text_tool_call('Sure! {"tool": "goto", "url": "a.com"} done', TOOLS) == ("goto", {"url": "a.com"})
    assert extract_text_tool_call("read()", TOOLS) == ("read", {})


def test_unknown_tool_in_text_is_not_extracted():
    assert extract_text_tool_call('{"name": "send_keys", "parameters": {"idx": 6}}', TOOLS) is None
    assert extract_text_tool_call("The answer is 42", TOOLS) is None


def test_junk_detection():
    assert looks_like_junk('click #1 button "Accept"\n--- page ---\n#1 link "x"')
    assert looks_like_junk('read()\n"The store was founded in 2010"')
    assert looks_like_junk('{"name": "send_keys"}')
    assert not looks_like_junk("Demo Store was founded in 1987.")
