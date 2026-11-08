import json
from types import SimpleNamespace as NS

from selfbrowse.llm import make_llm
from selfbrowse.llm.openai_compat import (
    OpenAICompatLLM, action_schema, json_mode_instructions, messages_to_openai_json, response_from_json,
)
from selfbrowse.tools import build_tools

TOOLS = build_tools(human=True)


def fake_resp(content, prompt=100, completion=20):
    return NS(choices=[NS(message=NS(content=content, tool_calls=None), finish_reason="stop")],
              usage=NS(prompt_tokens=prompt, completion_tokens=completion, prompt_tokens_details=None))


def test_schema_has_every_tool_and_argument_once():
    s = action_schema(TOOLS)
    assert set(s["properties"]["tool"]["enum"]) == {t["name"] for t in TOOLS}
    assert {"ref", "text", "url", "key", "direction", "seconds", "fact", "success", "answer", "reason", "submit"} <= set(s["properties"])
    assert s["required"] == ["thought", "tool"] and s["additionalProperties"] is False
    assert "thought" not in action_schema(TOOLS, thought=False)["properties"]


def test_instructions_list_tools_and_signatures():
    text = json_mode_instructions(TOOLS)
    assert "click(ref: integer)" in text and "done(success: boolean, answer: string)" in text and "ONE JSON object" in text


def test_history_roundtrip():
    msgs = [
        {"role": "user", "content": "Task: x"},
        {"role": "assistant", "content": [{"type": "text", "text": "open it"},
                                          {"type": "tool_use", "id": "1", "name": "goto", "input": {"url": "a.com"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": [{"type": "text", "text": "opened a.com"}]}]},
    ]
    out = messages_to_openai_json([{"text": "SYS"}], msgs)
    assert out[0] == {"role": "system", "content": "SYS"}
    assert json.loads(out[2]["content"]) == {"thought": "open it", "tool": "goto", "url": "a.com"}
    assert out[3] == {"role": "user", "content": "opened a.com"}      # a user message, not a `tool` role


def test_response_parsed_into_tool_use():
    r = response_from_json(fake_resp('{"thought": "click it", "tool": "click", "ref": 4, "bogus": 1}'), TOOLS)
    use = next(b for b in r.content if b["type"] == "tool_use")
    assert use["name"] == "click" and use["input"] == {"ref": 4}          # stray keys dropped
    assert r.stop_reason == "tool_use" and r.usage.input_tokens == 100 and r.content[0]["text"] == "click it"


def test_unparseable_reply_falls_back_to_text():
    r = response_from_json(fake_resp("Sorry, I cannot do that"), TOOLS)
    assert r.stop_reason == "end_turn" and r.content == [{"type": "text", "text": "Sorry, I cannot do that"}]
    r = response_from_json(fake_resp('{"tool": "send_keys"}'), TOOLS)         # unknown tool
    assert r.stop_reason == "end_turn"


def test_adapter_sends_schema_and_no_tools():
    llm = OpenAICompatLLM("m", api_key="x", json_mode=True)
    seen = {}

    def create(**kw):
        seen.update(kw)
        return fake_resp('{"thought": "t", "tool": "back"}')

    llm._client = NS(chat=NS(completions=NS(create=create)))
    resp = llm.complete(system=[{"text": "SYS", "cache": True}], messages=[{"role": "user", "content": "hi"}], tools=TOOLS)
    assert "tools" not in seen and seen["response_format"]["type"] == "json_schema"
    assert seen["response_format"]["json_schema"]["strict"] is True
    assert "ONE JSON object" in seen["messages"][0]["content"]
    assert resp.content[-1]["name"] == "back"


def test_native_mode_unchanged():
    llm = OpenAICompatLLM("m", api_key="x", json_mode=False)
    seen = {}

    def create(**kw):
        seen.update(kw)
        return fake_resp("hello")

    llm._client = NS(chat=NS(completions=NS(create=create)))
    llm.complete(system=[], messages=[{"role": "user", "content": "hi"}], tools=TOOLS)
    assert "tools" in seen and "response_format" not in seen


def test_local_providers_default_to_json_mode():
    assert make_llm("ollama:x").json_mode is True
    assert make_llm("lmstudio:x").json_mode is True
    assert make_llm("ollama:x", json_mode=False).json_mode is False
