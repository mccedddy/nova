import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.server as server
import agent.loop as loop_module
import agent.permissions as permissions_module


client = TestClient(server.app)


def setup_function():
    server.CONVERSATIONS.clear()
    server.INCOGNITO.clear()


def test_event_loop_yields_tool_lifecycle_and_answer():
    responses = [
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "fake_tool", "arguments": {}}},
                ],
            },
        },
        {"message": {"content": "Done.", "tool_calls": []}},
    ]

    def fake_chat(messages, tools=None):
        return responses.pop(0)

    with patch.object(loop_module, "chat", fake_chat), patch.dict(
        loop_module.TOOL_REGISTRY, {"fake_tool": lambda: "value"}, clear=False
    ), patch.object(
        permissions_module,
        "READ_ONLY_TOOLS",
        permissions_module.READ_ONLY_TOOLS | {"fake_tool"},
    ), patch.object(
        loop_module, "TOOL_SCHEMAS", [
            {
                "type": "function",
                "function": {
                    "name": "fake_tool",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ],
    ):
        result = list(loop_module.run_turn_events("do it", [], "test-conv-id"))

    assert [event["type"] for event in result] == [
        "tool_started",
        "tool_finished",
        "answer",
    ]
    assert result[0]["display"] == "1. Working"
    assert result[1]["result"] == "value"
    assert result[2]["text"] == "Done."


def test_event_loop_summarizes_after_tool_limit():
    def fake_chat(messages, tools=None):
        if tools == []:
            return {"message": {"content": "Summary from gathered results.", "tool_calls": []}}
        return {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "fake_tool", "arguments": {}}},
                ],
            },
        }

    with patch.object(loop_module, "chat", fake_chat), patch.dict(
        loop_module.TOOL_REGISTRY, {"fake_tool": lambda: "value"}, clear=False
    ), patch.object(
        permissions_module,
        "READ_ONLY_TOOLS",
        permissions_module.READ_ONLY_TOOLS | {"fake_tool"},
    ), patch.object(
        loop_module, "TOOL_SCHEMAS", [
            {
                "type": "function",
                "function": {
                    "name": "fake_tool",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ],
    ):
        result = list(loop_module.run_turn_events("keep going", [], "test-conv-id"))

    assert result[-1] == {"type": "answer", "text": "Summary from gathered results."}


def test_chat_returns_ndjson_and_generated_conversation_id():
    def fake_events(message, messages, conversation_id, incognito=False):
        assert message == "hello"
        assert messages[0]["role"] == "system"
        messages.append({"role": "user", "content": message})
        yield {"type": "answer", "text": "Hi."}

    with patch.object(server, "run_turn_events", fake_events):
        response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert lines[0]["type"] == "conversation_id"
    assert lines[0]["id"] in server.CONVERSATIONS
    assert lines[1] == {"type": "session_mode", "incognito": False}
    assert lines[2] == {"type": "answer", "text": "Hi."}


def test_conversations_are_isolated_and_reused_by_id():
    def fake_events(message, messages, conversation_id, incognito=False):
        messages.append({"role": "user", "content": message})
        messages.append({"role": "assistant", "content": message})
        yield {"type": "answer", "text": message}

    with patch.object(server, "run_turn_events", fake_events):
        first = client.post("/chat", json={"message": "first"})
        first_id = json.loads(first.text.splitlines()[0])["id"]
        second = client.post("/chat", json={"message": "second"})
        second_id = json.loads(second.text.splitlines()[0])["id"]
        client.post("/chat", json={"message": "follow-up", "conversation_id": first_id})

    assert first_id != second_id
    assert [message["content"] for message in server.CONVERSATIONS[first_id] if message["role"] == "user"] == [
        "first",
        "follow-up",
    ]
    assert [message["content"] for message in server.CONVERSATIONS[second_id] if message["role"] == "user"] == [
        "second",
    ]


def test_health_reports_only_api_and_ollama_status():
    with patch.object(server.requests, "get", return_value=object()):
        response = client.get("/health")

    assert response.json() == {"api": "ok", "ollama_reachable": True}

    with patch.object(server.requests, "get", side_effect=server.requests.exceptions.Timeout):
        response = client.get("/health")

    assert response.json() == {"api": "ok", "ollama_reachable": False}


# ---- incognito + memory -------------------------------------------------


@pytest.fixture
def memory_store(tmp_path, monkeypatch):
    # Point the API at a temp store so tests never touch the real memory.json.
    import agent.memory as memory_module

    monkeypatch.setattr(memory_module, "MEMORY_PATH", tmp_path / "memory.json")
    return memory_module


def test_incognito_chat_marks_conversation_and_omits_memory(memory_store):
    seen = {}

    def fake_events(message, messages, conversation_id, incognito=False):
        seen["incognito"] = incognito
        seen["system_prompt"] = messages[0]["content"]
        yield {"type": "answer", "text": "Hi."}

    with patch.object(server, "run_turn_events", fake_events):
        response = client.post("/chat", json={"message": "hi", "incognito": True})

    lines = [json.loads(line) for line in response.text.splitlines()]
    conv_id = lines[0]["id"]

    assert lines[1] == {"type": "session_mode", "incognito": True}
    assert seen["incognito"] is True
    assert conv_id in server.INCOGNITO
    assert "WHAT YOU REMEMBER" not in seen["system_prompt"]


def test_memory_block_appears_when_store_is_populated(memory_store):
    memory_store.remember("preferred_shell", "pwsh")
    seen = {}

    def fake_events(message, messages, conversation_id, incognito=False):
        seen["system_prompt"] = messages[0]["content"]
        yield {"type": "answer", "text": "Hi."}

    with patch.object(server, "run_turn_events", fake_events):
        client.post("/chat", json={"message": "hi"})

    assert "preferred_shell: pwsh" in seen["system_prompt"]


def test_toggling_incognito_rebuilds_the_conversation(memory_store):
    memory_store.remember("preferred_shell", "pwsh")
    prompts = []

    def fake_events(message, messages, conversation_id, incognito=False):
        prompts.append(messages[0]["content"])
        yield {"type": "answer", "text": "Hi."}

    with patch.object(server, "run_turn_events", fake_events):
        first = client.post("/chat", json={"message": "one"})
        conv_id = json.loads(first.text.splitlines()[0])["id"]
        assert "preferred_shell: pwsh" in prompts[0]

        # Same conversation, incognito on -- the memory block must not survive.
        client.post("/chat", json={"message": "two", "conversation_id": conv_id, "incognito": True})
        assert "preferred_shell: pwsh" not in prompts[1]

        # And back off.
        client.post("/chat", json={"message": "three", "conversation_id": conv_id, "incognito": False})
        assert "preferred_shell: pwsh" in prompts[2]

    assert conv_id not in server.INCOGNITO
    # Mode changes rebuild, so the transcript holds only the last exchange.
    assert len(server.CONVERSATIONS[conv_id]) == 1


def test_steady_state_request_does_not_resend_session_mode(memory_store):
    def fake_events(message, messages, conversation_id, incognito=False):
        yield {"type": "answer", "text": "Hi."}

    with patch.object(server, "run_turn_events", fake_events):
        first = client.post("/chat", json={"message": "one"})
        conv_id = json.loads(first.text.splitlines()[0])["id"]
        second = client.post("/chat", json={"message": "two", "conversation_id": conv_id})

    types = [json.loads(line)["type"] for line in second.text.splitlines()]
    assert "session_mode" not in types


def test_memory_endpoints_list_and_delete(memory_store):
    memory_store.remember("preferred_shell", "pwsh")

    listed = client.get("/memory")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    deleted = client.delete("/memory/preferred_shell")
    assert deleted.json()["ok"] is True
    assert client.get("/memory").json()["count"] == 0

    missing = client.delete("/memory/preferred_shell")
    assert missing.json()["ok"] is False


def test_settings_reports_bool_keys_so_ui_can_render_checkboxes():
    payload = client.get("/settings").json()
    assert "memory_enabled" in payload["bools"]
    # memory_autocapture_mode is a string, not a bool, so it must NOT be a checkbox.
    assert "memory_autocapture_mode" not in payload["bools"]
    assert payload["defaults"]["memory_autocapture_mode"] == "trigger"


def test_memory_settings_reject_non_boolean_and_wrong_range():
    response = client.post("/settings", json={"values": {
        "memory_enabled": "yes",
        "memory_max_entries": 99999,
    }})

    body = response.json()
    assert "memory_enabled" in body["rejected"]
    assert "memory_max_entries" in body["rejected"]


def test_autocapture_mode_only_accepts_known_modes():
    bad = client.post("/settings", json={"values": {"memory_autocapture_mode": "aggressive"}})
    assert "memory_autocapture_mode" in bad.json()["rejected"]

    worse = client.post("/settings", json={"values": {"memory_autocapture_mode": True}})
    assert "memory_autocapture_mode" in worse.json()["rejected"]
