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

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat", fake_chat):
        result = run_turn("how's my system", messages)

    assert result == "Your system looks fine."
    assert messages[-1]["content"] == "Your system looks fine."


def test_missing_required_arg_retries_then_gives_up():
    responses = [
        _fake_response(tool_calls=_tool_call("search_files", {})),
        _fake_response(tool_calls=_tool_call("search_files", {})),
        _fake_response(tool_calls=_tool_call("search_files", {})),
        _fake_response(content="I couldn't complete that search."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat", fake_chat):
        result = run_turn("find files", messages)

    assert result == "I couldn't complete that search."


def test_unknown_tool_name_reported_as_error():
    responses = [
        _fake_response(tool_calls=_tool_call("delete_everything", {})),
        _fake_response(content="That tool doesn't exist, so I can't do that."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat", fake_chat):
        result = run_turn("delete everything", messages)

    assert "can't do that" in result.lower()


def test_max_iterations_cap_reached():
    def fake_chat(messages, tools=None):
        if tools == []:
            return _fake_response(content="Based on the information gathered so far, here is the answer.")
        return _fake_response(tool_calls=_tool_call("get_system_diagnostics", {}))

    messages = []
    with patch.object(loop_module, "chat", fake_chat):
        result = run_turn("loop forever", messages)

    assert result == "Based on the information gathered so far, here is the answer."
    assert messages[-1]["role"] == "assistant"


def test_ollama_unavailable_returns_clean_error():
    from agent.client import OllamaUnavailableError

    def fake_chat(messages, tools=None):
        raise OllamaUnavailableError("Can't reach Ollama at localhost:11434. Is 'ollama serve' running?")

    with patch.object(loop_module, "chat", fake_chat):
        result = run_turn("hi", [])

    assert "can't reach ollama" in result.lower()


def test_retry_recovers_after_model_self_corrects():
    responses = [
        _fake_response(tool_calls=_tool_call("search_files", {})),
        _fake_response(tool_calls=_tool_call("search_files", {"pattern": "*.log"})),
        _fake_response(content="Found some log files."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat", fake_chat):
        result = run_turn("find log files", messages)

    assert result == "Found some log files."
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert any("missing required argument" in m["content"] for m in tool_messages)


def test_multiple_tool_calls_in_one_response():
    responses = [
        _fake_response(tool_calls=[
            {"function": {"name": "get_system_diagnostics", "arguments": {}}},
            {"function": {"name": "get_disk_health", "arguments": {}}},
        ]),
        _fake_response(content="Here's your system and disk info."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat", fake_chat):
        result = run_turn("check my system and disk", messages)

    assert result == "Here's your system and disk info."
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 2


def test_tool_execution_exception_handled_gracefully():
    import agent.tool_registry as registry_module

    def broken_tool():
        raise PermissionError("Access denied")

    responses = [
        _fake_response(tool_calls=_tool_call("get_disk_health", {})),
        _fake_response(content="I couldn't check disk health due to a permissions issue."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat", fake_chat), \
         patch.dict(registry_module.TOOL_REGISTRY, {"get_disk_health": broken_tool}):
        result = run_turn("is my disk healthy", messages)

    assert "permissions issue" in result.lower()
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert any("Access denied" in m["content"] for m in tool_messages)


def test_unconfirmed_powershell_action_is_blocked():
    import agent.tool_registry as registry_module

    executed = []
    responses = [
        _fake_response(tool_calls=_tool_call(
            "execute_powershell", {"command": "Remove-Item C:\\temp\\file.txt"}
        )),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.object(
        loop_module, "request_confirmation", return_value=False
    ), patch.dict(
        registry_module.TOOL_REGISTRY,
        {"execute_powershell": lambda command: executed.append(command)},
    ):
        result = run_turn("delete the file", [])

    assert result == "The action was not executed because confirmation was declined."
    assert executed == []


# ---- memory + incognito -------------------------------------------------


def test_incognito_refuses_memory_tool_without_executing_it():
    import agent.tool_registry as registry_module

    executed = []
    responses = [
        _fake_response(tool_calls=_tool_call("remember", {"key": "shell", "value": "pwsh"})),
        _fake_response(content="I am not remembering anything right now."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    messages = []
    with patch.object(loop_module, "chat", fake_chat), patch.dict(
        registry_module.TOOL_REGISTRY,
        {"remember": lambda key, value: executed.append((key, value))},
    ):
        result = run_turn("remember my shell is pwsh", messages, incognito=True)

    assert executed == []
    assert "not remembering anything" in result
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert any("incognito mode is on" in m["content"] for m in tool_messages)


def test_incognito_does_not_ask_for_confirmation_on_memory_tool():
    # The refusal happens before risk classification, so no prompt is possible.
    import agent.tool_registry as registry_module

    responses = [
        _fake_response(tool_calls=_tool_call("forget", {"key": "shell"})),
        _fake_response(content="Noted."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.object(
        loop_module, "request_confirmation", side_effect=AssertionError("should not prompt")
    ), patch.dict(
        registry_module.TOOL_REGISTRY,
        {"forget": lambda key: "forgotten"},
    ):
        result = run_turn("forget that", [], incognito=True)

    assert result == "Noted."


def test_memory_tool_executes_when_not_incognito():
    import agent.tool_registry as registry_module

    executed = []
    responses = [
        _fake_response(tool_calls=_tool_call("remember", {"key": "shell", "value": "pwsh"})),
        _fake_response(content="Saved."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.dict(
        registry_module.TOOL_REGISTRY,
        {"remember": lambda key, value: executed.append((key, value)) or "stored"},
    ):
        result = run_turn("remember my shell is pwsh", [])

    assert executed == [("shell", "pwsh")]
    assert result == "Saved."


def test_autocapture_runs_after_the_answer_is_collected():
    calls = []
    responses = [_fake_response(content="Noted, I'll use pwsh from now on.")]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.object(
        loop_module, "start_autocapture",
        lambda user, answer, mode="trigger": calls.append((user, answer, mode)),
    ):
        result = run_turn("from now on use pwsh", [])

    assert result == "Noted, I'll use pwsh from now on."
    assert calls == [("from now on use pwsh", "Noted, I'll use pwsh from now on.", loop_module.MEMORY_AUTOCAPTURE_MODE)]


def test_autocapture_is_skipped_while_incognito():
    calls = []
    responses = [_fake_response(content="Sure.")]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.object(
        loop_module, "start_autocapture",
        lambda user, answer, mode="trigger": calls.append((user, answer, mode)),
    ):
        run_turn("from now on use pwsh", [], incognito=True)

    assert calls == []


def test_autocapture_is_skipped_when_memory_disabled_in_settings():
    calls = []
    responses = [_fake_response(content="Sure.")]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.object(
        loop_module, "MEMORY_ENABLED", False
    ), patch.object(
        loop_module, "start_autocapture",
        lambda user, answer, mode="trigger": calls.append((user, answer, mode)),
    ):
        run_turn("from now on use pwsh", [])

    assert calls == []


def test_autocapture_receives_always_mode_from_settings():
    """In "always" mode the gate lives inside should_capture, so the loop must
    still call through for non-triggering turns and hand over the mode."""
    calls = []
    responses = [_fake_response(content="Sure.")]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.object(
        loop_module, "MEMORY_AUTOCAPTURE_MODE", "always"
    ), patch.object(
        loop_module, "start_autocapture",
        lambda user, answer, mode="trigger": calls.append((user, answer, mode)),
    ):
        run_turn("what's 2 + 2", [])

    assert calls == [("what's 2 + 2", "Sure.", "always")]


def test_memory_tools_are_refused_when_memory_disabled_globally():
    import agent.tool_registry as registry_module

    executed = []
    responses = [
        _fake_response(tool_calls=_tool_call("remember", {"key": "shell", "value": "pwsh"})),
        _fake_response(content="Memory is off."),
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.object(
        loop_module, "MEMORY_ENABLED", False
    ), patch.dict(
        registry_module.TOOL_REGISTRY,
        {"remember": lambda key, value: executed.append((key, value))},
    ):
        run_turn("remember my shell is pwsh", [])

    assert executed == []