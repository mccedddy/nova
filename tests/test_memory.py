import json
from unittest.mock import patch

import pytest

import agent.memory as memory_module
import settings as settings_module
from agent.memory import (
    extract_candidate,
    forget,
    list_entries,
    load_entries,
    remember,
    render_memory_block,
    save_entries,
    should_capture,
    start_autocapture,
)


@pytest.fixture
def logfile(tmp_path, monkeypatch):
    # Redirect the diagnostic log so tests never touch the real memory.log.
    path = tmp_path / "memory.log"
    monkeypatch.setattr(memory_module, "LOG_PATH", path)
    return path


@pytest.fixture
def store(tmp_path, monkeypatch):
    # Redirect the store to a temp file so tests never touch the real memory.json.
    path = tmp_path / "memory.json"
    monkeypatch.setattr(memory_module, "MEMORY_PATH", path)
    return path


def test_remember_then_load_roundtrip(store):
    result = remember("preferred_shell", "pwsh")

    assert result["stored"] is True
    assert result["updated_existing"] is False
    assert result["entry"]["key"] == "preferred_shell"
    assert result["entry"]["value"] == "pwsh"
    assert result["entry"]["source"] == "explicit"

    entries = load_entries()
    assert len(entries) == 1
    assert entries[0]["key"] == "preferred_shell"


def test_remember_upserts_by_key_and_preserves_created(store):
    first = remember("user_name", "Cedri")
    second = remember("user_name", "Ced")

    assert second["updated_existing"] is True
    assert second["entry"]["created"] == first["entry"]["created"]
    assert second["entry"]["value"] == "Ced"
    assert len(load_entries()) == 1


def test_keys_are_normalized_and_case_insensitive(store):
    remember("User Name", "Cedri")
    remember("user_name", "Ced")

    entries = load_entries()
    assert len(entries) == 1
    assert entries[0]["key"] == "user_name"


def test_remember_rejects_empty_key_and_value(store):
    assert remember("", "something")["stored"] is False
    assert remember("key", "   ")["stored"] is False
    assert load_entries() == []


def test_value_length_is_clamped(store, monkeypatch):
    monkeypatch.setattr(memory_module, "MEMORY_MAX_VALUE_CHARS", 10)
    result = remember("note", "x" * 50)

    assert result["entry"]["value"] == "x" * 10 + "..."


def test_entry_cap_drops_oldest_first(store, monkeypatch):
    monkeypatch.setattr(memory_module, "MEMORY_MAX_ENTRIES", 3)

    for index in range(5):
        remember(f"key_{index}", str(index))

    keys = [entry["key"] for entry in load_entries()]
    assert keys == ["key_2", "key_3", "key_4"]


def test_forget_removes_entry_and_reports_missing_key(store):
    remember("temp_fact", "x")

    removed = forget("temp_fact")
    assert removed["forgotten"] is True
    assert removed["remaining"] == 0

    missing = forget("temp_fact")
    assert missing["forgotten"] is False
    assert "keys" in missing


def test_corrupt_store_degrades_to_empty_and_rewrites(store):
    store.write_text("{not valid json", encoding="utf-8")
    assert load_entries() == []

    remember("k", "v")
    assert json.loads(store.read_text(encoding="utf-8"))["entries"][0]["key"] == "k"


def test_store_tolerates_wrong_shapes_and_blank_keys(store):
    store.write_text(
        json.dumps({"entries": ["nope", {"key": "  ", "value": "x"}, {"key": "ok"}]}),
        encoding="utf-8",
    )

    entries = load_entries()
    assert len(entries) == 1
    assert entries[0]["key"] == "ok"
    assert entries[0]["value"] == ""


def test_render_memory_block_is_empty_for_empty_store(store):
    assert render_memory_block() == ""


def test_render_memory_block_lists_entries(store):
    remember("preferred_shell", "pwsh")
    block = render_memory_block()

    assert "preferred_shell: pwsh" in block
    assert "WHAT YOU REMEMBER ABOUT THE USER" in block


def test_list_entries_reports_count(store):
    remember("a", "1")
    remember("b", "2")

    payload = list_entries()
    assert payload["count"] == 2
    assert {entry["key"] for entry in payload["entries"]} == {"a", "b"}


@pytest.mark.parametrize(
    "text",
    [
        "from now on always use pwsh",
        "remember that I prefer dark mode",
        "call me Cedri",
        "my name is Cedri",
        "I never want emoji in code",
        "keep in mind I'm on a work laptop",
        "note that my shell is fish",
    ],
)
def test_extract_candidate_fires_on_standing_preferences(text):
    assert extract_candidate(text) is True


@pytest.mark.parametrize(
    "text",
    [
        # The exact inputs used by the existing test suite. If autocapture ever
        # fires on one of these, a real extraction call could run mid-test.
        "how's my system",
        "find files",
        "delete everything",
        "loop forever",
        "hi",
        "find log files",
        "check my system and disk",
        "is my disk healthy",
        "delete the file",
        "do it",
        "keep going",
    ],
)
def test_extract_candidate_does_not_fire_on_existing_test_inputs(text):
    assert extract_candidate(text) is False


def test_autocapture_stores_parsed_facts(store, monkeypatch):
    monkeypatch.setattr(
        memory_module,
        "chat",
        lambda *args, **kwargs: {
            "message": {
                "content": 'Sure. {"facts": [{"key": "preferred_shell", "value": "pwsh"}]}'
            }
        },
    )

    memory_module.autocapture("from now on use pwsh", "Noted.")

    entries = load_entries()
    assert len(entries) == 1
    assert entries[0]["key"] == "preferred_shell"
    assert entries[0]["source"] == "autocapture"


def test_autocapture_never_raises_when_model_misbehaves(store, monkeypatch):
    monkeypatch.setattr(
        memory_module,
        "chat",
        lambda *args, **kwargs: {"message": {"content": "no json here at all"}},
    )

    memory_module.autocapture("from now on use pwsh", "Noted.")
    assert load_entries() == []


def test_autocapture_swallows_client_errors(store, monkeypatch):
    from agent.client import OllamaUnavailableError

    def boom(*args, **kwargs):
        raise OllamaUnavailableError("ollama is down")

    monkeypatch.setattr(memory_module, "chat", boom)

    memory_module.autocapture("from now on use pwsh", "Noted.")
    assert load_entries() == []


def test_start_autocapture_skips_thread_when_trigger_does_not_fire(store, monkeypatch):
    started = []
    monkeypatch.setattr(
        memory_module, "chat", lambda *a, **k: started.append(1) or {"message": {"content": ""}}
    )

    assert memory_module.start_autocapture("what is my disk size", "big", mode="trigger") is False
    assert started == []


def test_should_capture_always_mode_skips_the_trigger_gate():
    assert should_capture("what is my disk size", "always") is True
    assert should_capture("what is 2 + 2", "always") is True


def test_should_capture_trigger_mode_gates_on_phrases():
    assert should_capture("from now on use pwsh", "trigger") is True
    assert should_capture("what is 2 + 2", "trigger") is False


def test_should_capture_unknown_mode_falls_back_to_the_cheap_gate():
    # An unrecognised mode must not silently pay for an extraction call every turn.
    assert should_capture("what is 2 + 2", "nonsense") is False
    assert should_capture("always use pwsh", "nonsense") is True


def test_start_autocapture_always_mode_spawns_on_a_non_triggering_turn(monkeypatch):
    spawned = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            self.args = args
            self.daemon = daemon

        def start(self):
            spawned.append(self.args)

    with patch.object(memory_module.threading, "Thread", FakeThread):
        assert start_autocapture("what is my disk size", "big", mode="always") is True

    assert spawned == [("what is my disk size", "big")]


def test_start_autocapture_defaults_to_trigger_mode(store, monkeypatch):
    started = []
    monkeypatch.setattr(
        memory_module, "chat", lambda *a, **k: started.append(1) or {"message": {"content": ""}}
    )

    assert memory_module.start_autocapture("what is 2 + 2", "four") is False
    assert started == []


def test_save_entries_caps_and_persists(store, monkeypatch):
    monkeypatch.setattr(memory_module, "MEMORY_MAX_ENTRIES", 2)
    save_entries([
        {"key": "a", "value": "1", "source": "explicit", "created": "2026-01-01T00:00:00", "updated": ""},
        {"key": "b", "value": "2", "source": "explicit", "created": "2026-01-02T00:00:00", "updated": ""},
        {"key": "c", "value": "3", "source": "explicit", "created": "2026-01-03T00:00:00", "updated": ""},
    ])

    assert [entry["key"] for entry in load_entries()] == ["b", "c"]


# --- extractor payload: reasoning models need think=False -----------------------


def test_extractor_requests_no_thinking(store, logfile, monkeypatch):
    """Without think=False, qwen3.5-style models spend the whole num_predict
    budget on thinking and return an empty reply, so nothing is ever stored."""
    seen = {}

    def capture(messages, tools=None, **kwargs):
        seen.update(kwargs)
        return {"message": {"content": '{"facts": []}'}}

    monkeypatch.setattr(memory_module, "chat", capture)
    memory_module.autocapture("from now on use pwsh", "Noted.")

    assert seen["think"] is False
    assert seen["num_predict"] == memory_module.EXTRACT_NUM_PREDICT


def test_extraction_budget_is_large_enough_to_contain_a_reply():
    # 120 was fully consumed by thinking tokens; the reply never materialised.
    assert memory_module.EXTRACT_NUM_PREDICT >= 256


def test_extraction_prompt_no_longer_tells_the_model_to_return_nothing():
    # This phrasing measurably suppressed extraction on a lazy 9B model.
    assert "normal, expected answer" not in memory_module.EXTRACTION_PROMPT


def test_chat_omits_think_key_when_not_requested(monkeypatch):
    from agent import client as client_module

    sent = {}

    class FakeResponse:
        text = "{}"

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": ""}}

    def fake_post(url, json=None, timeout=None):
        sent.update(json)
        return FakeResponse()

    monkeypatch.setattr(client_module.requests, "post", fake_post)
    client_module.chat([{"role": "user", "content": "hi"}])

    assert "think" not in sent


def test_chat_includes_think_key_when_requested(monkeypatch):
    from agent import client as client_module

    sent = {}

    class FakeResponse:
        text = "{}"

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": ""}}

    def fake_post(url, json=None, timeout=None):
        sent.update(json)
        return FakeResponse()

    monkeypatch.setattr(client_module.requests, "post", fake_post)
    client_module.chat([{"role": "user", "content": "hi"}], think=False)

    assert sent["think"] is False


# --- diagnostics ----------------------------------------------------------------


def test_log_records_a_successful_store(store, logfile, monkeypatch):
    monkeypatch.setattr(
        memory_module,
        "chat",
        lambda *a, **k: {
            "message": {"content": '{"facts": [{"key": "preferred_shell", "value": "pwsh"}]}'}
        },
    )

    memory_module.autocapture("from now on use pwsh", "Noted.")

    text = logfile.read_text(encoding="utf-8")
    assert "autocapture.stored" in text
    assert "preferred_shell" in text


def test_log_records_the_empty_reply_that_looks_like_success(store, logfile, monkeypatch):
    """The silent-failure case: no error, no facts, nothing to show for it."""
    monkeypatch.setattr(
        memory_module,
        "chat",
        lambda *a, **k: {"done_reason": "length", "eval_count": 120, "message": {"content": ""}},
    )

    memory_module.autocapture("from now on use pwsh", "Noted.")

    text = logfile.read_text(encoding="utf-8")
    assert "autocapture.nothing" in text
    assert "done_reason='length'" in text
    assert "reply_len='0'" in text


def test_log_records_client_failures(store, logfile, monkeypatch):
    from agent.client import OllamaUnavailableError

    def boom(*a, **k):
        raise OllamaUnavailableError("ollama is down")

    monkeypatch.setattr(memory_module, "chat", boom)

    memory_module.autocapture("from now on use pwsh", "Noted.")

    text = logfile.read_text(encoding="utf-8")
    assert "autocapture.unavailable" in text
    assert "ollama is down" in text


def test_log_records_unexpected_exceptions(store, logfile, monkeypatch):
    def boom(*a, **k):
        raise ValueError("unexpected")

    monkeypatch.setattr(memory_module, "chat", boom)

    memory_module.autocapture("from now on use pwsh", "Noted.")

    text = logfile.read_text(encoding="utf-8")
    assert "autocapture.error" in text
    assert "ValueError" in text


def test_gate_decline_is_logged_separately_from_an_empty_extraction(store, logfile, monkeypatch):
    """These two look identical to a user and mean opposite things."""
    monkeypatch.setattr(memory_module, "chat", lambda *a, **k: {"message": {"content": ""}})

    assert memory_module.start_autocapture("what is my disk size", "big", mode="trigger") is False
    text = logfile.read_text(encoding="utf-8")
    assert "autocapture.skipped" in text
    assert "trigger did not match" in text


def test_logging_never_raises_when_the_path_is_unwritable(store, monkeypatch, tmp_path):
    monkeypatch.setattr(memory_module, "LOG_PATH", tmp_path / "nope" / "deep" / "memory.log")

    # A directory that does not exist: the log must fail silently.
    memory_module._log("autocapture.spawned", mode="trigger")


def test_log_is_capped_so_it_cannot_grow_without_bound(store, logfile, monkeypatch):
    monkeypatch.setattr(memory_module, "LOG_MAX_BYTES", 200)
    for index in range(60):
        memory_module._log("autocapture.spawned", mode="trigger", index=index)

    text = logfile.read_text(encoding="utf-8")
    assert "earlier entries dropped" in text
    assert len(text) < 4000
