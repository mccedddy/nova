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