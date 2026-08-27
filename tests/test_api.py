import json
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.server as server
import agent.loop_events as events_module


client = TestClient(server.app)


def setup_function():
    server.CONVERSATIONS.clear()


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

    with patch.object(events_module, "chat", fake_chat), patch.dict(
        events_module.TOOL_REGISTRY, {"fake_tool": lambda: "value"}, clear=False
    ), patch.object(
        events_module, "TOOL_SCHEMAS", [
            {
                "type": "function",
                "function": {
                    "name": "fake_tool",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ],
    ):
        result = list(events_module.run_turn_events("do it", []))

    assert [event["type"] for event in result] == [
        "tool_started",
        "tool_finished",
        "answer",
    ]
    assert result[1]["result"] == "value"
    assert result[2]["text"] == "Done."


def test_chat_returns_ndjson_and_generated_conversation_id():
    def fake_events(message, messages):
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
    assert lines[1] == {"type": "answer", "text": "Hi."}


def test_conversations_are_isolated_and_reused_by_id():
    def fake_events(message, messages):
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
