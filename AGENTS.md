# NOVA — Agent Instructions

## What this is

Local Windows AI assistant with three separate layers:
- **Python agent core** (`agent/`, `tools/`): ReAct-style tool-calling loop, 14 registered tools, permission enforcement
- **Python API** (`api/server.py`): FastAPI server for desktop/remote clients, streams events as newline-delimited JSON
- **Electron client** (`app/`): Desktop UI consuming the API; does not execute Python tools directly

The agent loop (`agent/loop.py`) has two entry points: `run_turn` (terminal, sync) and `run_turn_events` (API, async generator). They share `run_turn_core` but are kept separate to avoid regressions.

## Run commands

```bash
# Terminal client (requires Ollama running on localhost:11434)
python main.py
python main.py --debug-tools          # show raw tool names/args/results
python main.py --debug-tools --full-output  # untruncated tool results

# API server
python api/server.py                  # uvicorn on 127.0.0.1:8000

# Electron desktop client
cd app && npm start

# Tests
pytest                                # all tests (uses mocked Ollama, no live model needed)
pytest tests/test_agent_loop.py       # single test file
pytest tests/test_permissions.py::test_command_classifier_detects_known_risk_patterns  # single test
```

No lint/typecheck configured. No formatter configured. Tests mock the Ollama chat function — no live model or Ollama needed.

## Key conventions

- **Permission tiers** (enforced in Python, not by the model): READ auto-executes, MODIFY and DESTRUCTIVE require user confirmation. `execute_powershell` commands are classified by regex patterns in `agent/permissions.py`. All other tools have a fixed tier based on their name in `READ_ONLY_TOOLS`.
- **Tool preference**: Model should use native tools (e.g. `get_system_diagnostics`) over `execute_powershell` for known operations. This is enforced in the system prompt, not code.
- **Settings flow**: `settings.json` (project root during dev) → `settings.py` validates and loads → exported as module-level constants consumed everywhere. All tool timeouts, iteration caps, and model params live here.
- **API binding**: Always `127.0.0.1:8000`, never `0.0.0.0`. No auth layer exists yet.
- **Conversations**: In-memory only, keyed by `conversation_id`. No persistence. Terminal and API each maintain their own message lists.
- **Date injection**: Real current date/time is appended to the system prompt at runtime (both terminal and API paths). Don't hardcode dates in prompts.

## Testing patterns

- Tests mock `agent.loop.chat` (the Ollama client) with scripted response sequences and assert on message history and yielded events.
- `test_api.py` uses `fastapi.testclient.TestClient`; clear `server.CONVERSATIONS` in `setup_function`.
- `test_permissions.py` tests the classifier directly — `classify_command` for PowerShell strings, `classify_operation` for tool+args.
- `test_agent_loop.py` patches `request_confirmation` to simulate approval/denial.

## Deliberate decisions / out of scope

- **Streaming was tried and removed (terminal)**: token-by-token display added real complexity and caused a print-duplication bug when combined with tool-call handling, with no quality/correctness benefit. Non-streaming (wait for full response, then print) is the settled terminal approach. The API still streams *events* (NDJSON), but not raw answer tokens.
- **Terminal/API loops kept separate on purpose**: both call the shared `run_turn_core`, but `run_turn` and `run_turn_events` are distinct entry points. An earlier attempt to make one function serve both caused a broken-indentation bug and a print-duplication bug. Don't "simplify" them back together.
- **Out of scope unless deliberately started**: public/unauthenticated remote API access (API stays bound to `127.0.0.1:8000`, no auth layer); persistent memory/logging across sessions; desktop operations beyond what exists (voice STT/TTS, plugin system). None of these should be built incidentally while working on something else.

## Common pitfalls

- Adding a new tool requires changes in three places: `tools/<module>.py` (implementation), `tools/tool_schemas.py` (JSON schema), `agent/tool_registry.py` (registry entry). If it's read-only, also add its name to `READ_ONLY_TOOLS` in `agent/permissions.py`.
- `settings.json` keys with invalid types or out-of-range values are silently ignored (defaults used). `powershell_max_timeout` is clamped to be ≥ `powershell_timeout`.
- Ollama availability errors are caught at the client level and surfaced as `OllamaUnavailableError` — never let them propagate as unhandled exceptions.
- The system prompt in `agent/prompts.py` is intentionally compact (numbered rules, not prose) for small-model compatibility. Don't pad it with verbose explanations.
- `node-pty` in `app/package.json` may require native compilation (`npm rebuild node-pty`) on Windows.
