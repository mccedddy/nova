from unittest.mock import patch
import agent.loop as loop_module
from agent.loop import run_turn


def _fake_response(content="", tool_calls=None):
    return {"message": {"content": content, "tool_calls": tool_calls}}


def _tool_call(name, arguments):
    return [{"function": {"name": name, "arguments": arguments}}]


def test_successful_single_tool_call():
    responses = [
        _fake_response(tool_calls=_tool_call("get_system_diagnostics", {})),
        _fake_response(content="Your system looks fine."),
    ]

    def fake_chat_stream(messages, tools=None, on_token=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat_stream", fake_chat_stream):
        result = run_turn("how's my system", messages)

    # successful streamed answers return "" by design (already printed live);
    # the real text lives in the message history instead
    assert result == ""
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "Your system looks fine."


def test_missing_required_arg_retries_then_gives_up():
    responses = [
        _fake_response(tool_calls=_tool_call("search_files", {})),
        _fake_response(tool_calls=_tool_call("search_files", {})),
        _fake_response(tool_calls=_tool_call("search_files", {})),
        _fake_response(content="I couldn't complete that search."),
    ]

    def fake_chat_stream(messages, tools=None, on_token=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat_stream", fake_chat_stream):
        result = run_turn("find files", messages)

    assert result == ""
    assert messages[-1]["content"] == "I couldn't complete that search."


def test_unknown_tool_name_reported_as_error():
    responses = [
        _fake_response(tool_calls=_tool_call("delete_everything", {})),
        _fake_response(content="That tool doesn't exist, so I can't do that."),
    ]

    def fake_chat_stream(messages, tools=None, on_token=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat_stream", fake_chat_stream):
        result = run_turn("delete everything", messages)

    assert result == ""
    assert "can't do that" in messages[-1]["content"].lower()


def test_max_iterations_cap_reached():
    def fake_chat_stream(messages, tools=None, on_token=None):
        return _fake_response(tool_calls=_tool_call("get_system_diagnostics", {}))

    with patch.object(loop_module, "chat_stream", fake_chat_stream):
        result = run_turn("loop forever", [])

    assert "couldn't complete that after several tool calls" in result.lower()


def test_ollama_unavailable_returns_clean_error():
    from agent.client import OllamaUnavailableError

    def fake_chat_stream(messages, tools=None, on_token=None):
        raise OllamaUnavailableError("Can't reach Ollama at localhost:11434. Is 'ollama serve' running?")

    with patch.object(loop_module, "chat_stream", fake_chat_stream):
        result = run_turn("hi", [])

    assert "can't reach ollama" in result.lower()

def test_retry_recovers_after_model_self_corrects():
    # first attempt fails validation (missing "pattern"), model corrects
    # itself, succeeds
    responses = [
        _fake_response(tool_calls=_tool_call("search_files", {})),  # missing pattern
        _fake_response(tool_calls=_tool_call("search_files", {"pattern": "*.log"})),  # corrected
        _fake_response(content="Found some log files."),
    ]

    def fake_chat_stream(messages, tools=None, on_token=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat_stream", fake_chat_stream):
        result = run_turn("find log files", messages)

    assert result == ""
    assert messages[-1]["content"] == "Found some log files."
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert any("missing required argument" in m["content"] for m in tool_messages)


def test_multiple_tool_calls_in_one_response():
    # model requests two tool calls in a single turn
    responses = [
        _fake_response(tool_calls=[
            {"function": {"name": "get_system_diagnostics", "arguments": {}}},
            {"function": {"name": "get_disk_health", "arguments": {}}},
        ]),
        _fake_response(content="Here's your system and disk info."),
    ]

    def fake_chat_stream(messages, tools=None, on_token=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat_stream", fake_chat_stream):
        result = run_turn("check my system and disk", messages)

    assert result == ""
    assert messages[-1]["content"] == "Here's your system and disk info."
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 2  # both tool calls produced results


def test_tool_execution_exception_handled_gracefully():
    # simulate a real Python exception during tool execution, not a
    # validation failure -- e.g. a PermissionError from a real tool
    import agent.tool_registry as registry_module

    def broken_tool():
        raise PermissionError("Access denied")

    responses = [
        _fake_response(tool_calls=_tool_call("get_disk_health", {})),
        _fake_response(content="I couldn't check disk health due to a permissions issue."),
    ]

    def fake_chat_stream(messages, tools=None, on_token=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat_stream", fake_chat_stream), \
         patch.dict(registry_module.TOOL_REGISTRY, {"get_disk_health": broken_tool}):
        result = run_turn("is my disk healthy", messages)

    assert result == ""
    assert "permissions issue" in messages[-1]["content"].lower()
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert any("Access denied" in m["content"] for m in tool_messages)