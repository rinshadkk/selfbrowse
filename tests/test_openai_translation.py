import json

from selfbrowse.llm.openai_compat import messages_to_openai, tools_to_openai


def test_tools():
    out = tools_to_openai([{"name": "click", "description": "d", "input_schema": {"type": "object", "properties": {}}}])
    assert out[0]["function"]["name"] == "click"


def test_tool_roundtrip_messages():
    msgs = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": [{"type": "text", "text": "ok"}, {"type": "tool_use", "id": "1", "name": "click", "input": {"ref": 3}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": [{"type": "text", "text": "done"}]}]},
    ]
    out = messages_to_openai([{"text": "sys", "cache": True}], msgs)
    assert out[0] == {"role": "system", "content": "sys"}
    assert json.loads(out[2]["tool_calls"][0]["function"]["arguments"]) == {"ref": 3}
    assert out[3] == {"role": "tool", "tool_call_id": "1", "content": "done"}
