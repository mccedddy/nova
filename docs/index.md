# NOVA — Codebase Map

Where things live and what each piece is for. For conventions, run commands, and design decisions see **`AGENTS.md`**, which is the required reading for anyone working here — this file is only navigation.

> **This map deliberately carries no signatures, return shapes, or constant values.**
> Those drift silently, and a confidently wrong signature is worse than none: an agent that trusts a stale `chat()` signature writes code that appears to work while quietly failing to disable model reasoning. Read the source for anything at call level. This file answers "where do I look?", not "what does it return?".

## Architecture

Three layers. The **Python agent core** (`agent/`, `tools/`) runs a ReAct tool-calling loop. The **Python API** (`api/server.py`) exposes that loop over HTTP as NDJSON event streams. The **Electron client** (`app/`) is a desktop UI that consumes the API and never runs Python tools directly — every tool action crosses the process boundary.

16 tools are registered. Permission tiers are enforced in Python, never by model self-report. `execute_powershell` is the only tool whose risk is classified per-invocation; everything else resolves from a static set lookup.

Conversations are **in-memory only**, keyed by `conversation_id`, with no persistence across restarts. `memory.json` is the single durable store.

---

## File tree

```
nova/
  main.py                 # terminal CLI entry point
  settings.py             # settings loader/validator -> module constants
  settings.json           # user-editable runtime config
  agent/
    loop.py               # ReAct loop (terminal + API entry points)
    client.py             # Ollama /api/chat wrapper
    prompts.py            # system prompt + build_system_prompt()
    permissions.py        # risk classification + confirmation
    annotations.py        # recovery/verification notes on tool results
    memory.py             # durable fact store, prompt injection, autocapture
    tool_registry.py      # name -> tool function map
  api/
    server.py             # FastAPI server (127.0.0.1:8000)
  tools/
    __init__.py
    tool_schemas.py       # TOOL_SCHEMAS (JSON function schemas)
    filesystem.py
    memory.py
    powershell.py
    processes.py
    registry.py
    system.py
    websearch.py
  app/
    main.js               # Electron main process
    preload.js            # contextBridge -> window.nova
    renderer/
      index.html
      renderer.js
      style.css
      vendor/             # bundled xterm.js, marked.umd.js
    settings.js           # Electron client settings (userData)
    terminals.js          # node-pty PowerShell terminals
    package.json
  tests/
    test_agent_loop.py
    test_api.py
    test_memory.py
    test_permissions.py
    test_powershell.py
    test_validation.py
    test_websearch.py
  docs/index.md
  requirements.txt
  pytest.ini
  README.md
```

Two runtime artifacts sit at the project root and are gitignored: **`memory.json`** (durable user facts) and **`memory.log`** (autocapture diagnostics).

---

## agent/

### client.py
The only module that talks to Ollama. Wraps `/api/chat` and converts connection, timeout, and HTTP failures into `OllamaUnavailableError` so nothing downstream has to handle raw `requests` exceptions. Carries two optional knobs used by memory extraction — a token budget override and a reasoning toggle — both of which the main agent deliberately leaves unset.

### loop.py
The ReAct loop: chat, extract tool calls, validate, classify risk, request permission when required, execute, annotate, repeat until an answer or the iteration cap. Yields a fixed vocabulary of events that become NDJSON.

Two entry points exist on purpose — one for the terminal, one for the API — both thin wrappers over a shared core. See `AGENTS.md` for why they were not merged back into one.

Memory and incognito are enforced here, not in the prompt: a blocked memory tool never reaches the registry.

Adding a new event type requires a matching `case` in the Electron renderer; unhandled types render as a visible error line.

### permissions.py
Risk classification, kept deliberately separate from any model self-report.

Three sets, with distinct meanings:
- **`READ_ONLY_TOOLS`** — genuinely read-only tools.
- **`AUTO_APPROVE_TOOLS`** — tools that write but should not prompt (`remember`/`forget`). Kept *separate* from the read-only set so that set stays honest about what it contains.
- **`MEMORY_TOOLS`** — refused outright while incognito mode is on.

Tools in neither set fall to the most conservative tier. Recognized PowerShell commands are classified by regex; an unrecognized command lands on an intermediate default rather than the safest tier, which is intentional — see `AGENTS.md` before changing it.

### annotations.py
Post-processing on tool results: attaches recovery notes to failed commands and verification notes to anything that wasn't read-only, scaled by a retry cap so the model isn't told the same thing repeatedly.

### prompts.py
The system prompt is **intentionally compact — numbered rules, not prose**, because it is consumed by a small local model. Do not pad it with explanation.

`build_system_prompt()` is the single composer. It injects the live date and, when appropriate, the memory block. Both the terminal and the API call it rather than assembling prompts themselves.

### tool_registry.py
Maps tool names to callables. Kept as an explicit dict so an agent can see the full tool surface in one place.

### memory.py
Durable fact storage plus prompt injection plus background autocapture. Storage is tolerant by design: a missing or malformed file degrades to an empty store rather than breaking a conversation, and no read or write path raises.

Autocapture runs on a daemon thread after the answer and never blocks a turn. Every failure is swallowed, and every attempt is logged — see the four `think=False` / reliability / logging bullets in `AGENTS.md` before changing anything here. The known-good reason it needs an explicit reasoning toggle is not obvious from the code and will look like removable cruft if undocumented.

---

## api/

### server.py
FastAPI app bound to `127.0.0.1:8000` and never `0.0.0.0`; there is no authentication layer. Holds conversation history in memory and tracks per-conversation incognito state.

Streaming is newline-delimited JSON. The first line identifies the conversation; a second line reports the resolved session mode when a conversation is new or its mode changed. Changing incognito mid-conversation **rebuilds** it, because the memory block is baked into the first message.

Settings endpoints serve both the Electron form and any other client: they separate boolean keys, ranged integers, and enumerated strings so a UI can render checkboxes, number inputs, and dropdowns instead of free text. Post-validating settings reports that a restart is required, because the Python constants snapshot at import.

---

## tools/

One module per problem area, all thin and side-effect-free apart from `powershell.py`.

### tool_schemas.py
Declarative JSON function schemas — metadata only, no executables. Descriptions are kept short for small-model compatibility.

### memory.py
The two model-facing memory tools. Thin wrappers over `agent/memory.py`; no logic of their own.

### filesystem.py
File search, folder size, and a relevance *signals* analysis (recency, size, temp-path membership, lock state). The relevance tool deliberately reports signals and never renders a delete verdict — deletion is the user's decision, not the model's.

### powershell.py
The dynamic-command tool. Wraps commands with strict error handling and profiles disabled, clamps the timeout, and returns partial output when it expires.

### processes.py
Running processes and network connections via psutil, with hard result caps and a stable sort. Some information requires elevation and reports that as an error rather than returning partial data as if complete.

### registry.py
Windows registry reads restricted to the safe hive roots, with value and subkey caps.

### system.py
CPU, RAM, disk, OS, GPU driver, and SMART disk health. NVIDIA driver detail is enriched with `nvidia-smi` when available; the OS-specific paths shell out to PowerShell.

### websearch.py
Two-tier search where the escalation decision lives in the tool, not the model: free backends first, an API-backed tier only when the results fail a quality gate. Also page fetching and IP geolocation. The geolocation tool is the only one that sends anything externally.

---

## app/

### main.js
Electron main process: frameless always-on-top window, tray, global shortcut, single-instance lock, API communication, IPC handlers, and PTY terminals. Runs with `contextIsolation` enabled, `nodeIntegration` disabled, and the sandbox on — keep it that way.

IPC channels cover window control, settings, health, chat streaming, permission responses, memory listing and deletion, conversation reset, and terminal I/O.

### preload.js
Exposes a narrow, renderer-safe surface on `window.nova` through `contextBridge`. The renderer has no direct Node access; anything the UI needs must be added here deliberately.

### renderer/
Single-page chat UI: sidebar navigation (Chat, terminals, Settings, Memory, and a persisted Incognito toggle), markdown-rendered chat log, tier-coloured tool indicators, inline permission prompts, embedded terminals, and a settings view. Agent settings render dynamically from what the API reports about key types.

Any new NDJSON event type needs an explicit handler here or it surfaces as a red error line in the chat log.

### settings.js
Electron client settings, stored as JSON in `userData` and separate from `settings.json`. Includes the persisted `incognito` toggle alongside the API base URL and global shortcut. Loads defensively, falling back to defaults on a missing or invalid file.

### terminals.js
Two node-pty PowerShell terminals. Activates the project virtualenv when present and aims for UTF-8 output.

### package.json
`node-pty` is native and may need `npm rebuild node-pty` on Windows.

---

## Root

### main.py
Terminal REPL. Prints a banner, then loops on stdin driving the sync loop entry point. Debug flags surface raw tool names, arguments, and results.

### settings.py
Validates `settings.json` and re-exports it as module constants consumed everywhere. Declares defaults, integer ranges, boolean keys, and enumerated-string choices; invalid values silently fall back to defaults rather than raising. Also enforces the relationship between the two PowerShell timeouts.

### settings.json
User-editable runtime config: model connection and parameters, loop caps, terminal truncation, per-tool timeouts and limits, and the memory subsystem's four keys (`memory_enabled`, `memory_autocapture_mode`, `memory_max_entries`, `memory_max_value_chars`).

### requirements.txt
Python dependencies.

### pytest.ini
Puts the repo root on the import path so tests resolve project modules.

### README.md
Project front page and install/run instructions.