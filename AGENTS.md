# NOVA — Agent Instructions

## What this is

Local Windows AI assistant with three separate layers:
- **Python agent core** (`agent/`, `tools/`): ReAct-style tool-calling loop, 16 registered tools, permission enforcement
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
- **Settings flow**: `settings.json` (project root during dev) → `settings.py` validates and loads → exported as module-level constants consumed everywhere. All tool timeouts, iteration caps, and model params live here. Boolean keys must be listed in `BOOL_KEYS` or they get no type validation; `GET /settings` returns that list as `bools` so the Electron client renders them as checkboxes.
- **API binding**: Always `127.0.0.1:8000`, never `0.0.0.0`. No auth layer exists yet.
- **Conversations**: In-memory only, keyed by `conversation_id`. No persistence. Terminal and API each maintain their own message lists. The only durable store is `memory.json` (see below).
- **Date injection**: Real current date/time is appended to the system prompt at runtime via `build_system_prompt()` in `agent/prompts.py`. Don't hardcode dates in prompts.
- **Memory** (`agent/memory.py`): Durable user facts as `{key, value, source, created, updated}` in `memory.json` at the project root, shared by both clients and gitignored. `render_memory_block()` returns `""` for an empty store, so a fresh install's prompt is unchanged. `remember`/`forget` are the model-facing tools; autocapture additionally distills facts in a daemon thread after a turn. Capture is governed by `memory_autocapture_mode`: `"trigger"` (default) gates on the narrow `CAPTURE_TRIGGERS` regex so non-matching turns cost nothing, `"always"` skips the gate and lets the model adjudicate every turn. An unrecognised mode falls back to the trigger gate. Incognito blocks both reads and writes **in the loop**, before the tool reaches the registry — never in the prompt.
- **Autocapture needs `think=False`**: `autocapture()` passes `think=False` and `num_predict=EXTRACT_NUM_PREDICT` (384). On hybrid reasoning models (`qwen3.5` and similar) thinking otherwise consumes the entire token budget and the reply comes back with **zero characters** — a silent no-op indistinguishable from "nothing worth keeping". Do not restore the "returning an empty list is the normal, expected answer" line in `EXTRACTION_PROMPT`; it measurably suppressed extraction on a lazy 9B model.
- **Autocapture is ~60% reliable and that is not a bug**: measured against `qwen3.5:9b`, roughly 3 in 5 trigger-phrased turns yield a fact. Do not judge changes by single samples — the model is nondeterministic and n=1 comparisons are noise. Repeat trials before believing any prompt or setting change.
- **Do not try to make implicit capture work by prompting.** Measured against the real system prompt (10.8k chars, memory block inside the system message), telling the model to call `remember` unprompted scores 0–33% regardless of where the rule goes (appended, prepended, beside the block, or as a numbered rule). A 9B model has no reliable "call this tool unprompted" behaviour here; it calls `remember` reliably only when the user asks. Autocapture exists because of that, not as a nicety.
- **Every capture attempt is logged to `memory.log`** (project root, gitignored, capped at 256 KB): gate decision, `done_reason`, `eval_count`, reply length, truncated reply, and any exception. This is deliberate — a capture that quietly does nothing must be distinguishable from one that correctly found nothing. If memory is not being written, read this file first.
- **Incognito**: A per-request flag (`ChatRequest.incognito`) that suppresses the memory block and refuses `MEMORY_TOOLS`. Toggling it mid-conversation **rebuilds** the conversation, because the memory block is baked into `messages[0]`. The server tracks state in `INCOGNITO`, a set of conversation ids.

## Testing patterns

- Tests mock `agent.loop.chat` (the Ollama client) with scripted response sequences and assert on message history and yielded events.
- `test_api.py` uses `fastapi.testclient.TestClient`; clear `server.CONVERSATIONS` in `setup_function`.
- `test_permissions.py` tests the classifier directly — `classify_command` for PowerShell strings, `classify_operation` for tool+args.
- `test_agent_loop.py` patches `request_confirmation` to simulate approval/denial.

## Deliberate decisions / out of scope

- **Streaming was tried and removed (terminal)**: token-by-token display added real complexity and caused a print-duplication bug when combined with tool-call handling, with no quality/correctness benefit. Non-streaming (wait for full response, then print) is the settled terminal approach. The API still streams *events* (NDJSON), but not raw answer tokens.
- **Terminal/API loops kept separate on purpose**: both call the shared `run_turn_core`, but `run_turn` and `run_turn_events` are distinct entry points. An earlier attempt to make one function serve both caused a broken-indentation bug and a print-duplication bug. Don't "simplify" them back together.
- **Memory writes don't prompt**: `remember`/`forget` write to disk but are classified READ via `AUTO_APPROVE_TOOLS` in `agent/permissions.py`. Deliberate — the write is scoped to NOVA's own store and is trivially reversible, so a "DESTRUCTIVE/SYSTEM-LEVEL" prompt per saved preference would be noise. They are kept out of `READ_ONLY_TOOLS` so that set stays honest about what it contains. Incognito is the escape hatch and is enforced separately.
- **Autocapture runs in a daemon thread after the answer**: the turn never waits on it, and `agent/memory.py` holds its own `chat` reference so patching `agent.loop.chat` in tests can't redirect it. Every failure inside `autocapture` is swallowed — memory extraction must never break a turn.
- **Out of scope unless deliberately started**: public/unauthenticated remote API access (API stays bound to `127.0.0.1:8000`, no auth layer); conversation/log persistence across sessions (memory is durable, the transcript is not); desktop operations beyond what exists (voice STT/TTS, plugin system). None of these should be built incidentally while working on something else.

## Common pitfalls

- Adding a new tool requires changes in three places: `tools/<module>.py` (implementation), `tools/tool_schemas.py` (JSON schema), `agent/tool_registry.py` (registry entry). If it's read-only, also add its name to `READ_ONLY_TOOLS` in `agent/permissions.py`; if it should auto-approve without prompting, use `AUTO_APPROVE_TOOLS` instead.
- `settings.json` keys with invalid types or out-of-range values are silently ignored (defaults used). `powershell_max_timeout` is clamped to be ≥ `powershell_timeout`.
- Ollama availability errors are caught at the client level and surfaced as `OllamaUnavailableError` — never let them propagate as unhandled exceptions.
- The system prompt in `agent/prompts.py` is intentionally compact (numbered rules, not prose) for small-model compatibility. Don't pad it with verbose explanations.
- `settings.json` keys with invalid types or out-of-range values are silently ignored (defaults used). `powershell_max_timeout` is clamped to be ≥ `powershell_timeout`.
- `memory.json` is gitignored personal data. Tests must redirect it with `monkeypatch.setattr(memory_module, "MEMORY_PATH", tmp_path / ...)`, never write the real one.
- Any new NDJSON event type needs an explicit `case` in `handleEvent` in `app/renderer/renderer.js` — unhandled types fall through to `default:` and render as a red error line.
- `node-pty` in `app/package.json` may require native compilation (`npm rebuild node-pty`) on Windows.
