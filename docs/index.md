# NOVA — File Reference

File-by-file API reference for the NOVA codebase. For conventions, run commands, and design decisions see `AGENTS.md`; this file covers signatures, arguments, and return shapes only.

> **Trust the source.** This reference may drift from the code. When a detail here conflicts with what the code actually does, the code wins — read the source to be sure.

## Architecture in one line

Three layers: the **Python agent core** (`agent/`, `tools/`) runs the ReAct tool-calling loop; the **Python API** (`api/server.py`) exposes it over HTTP as NDJSON events; the **Electron client** (`app/`) is a desktop UI that consumes the API and never runs Python tools directly.

**14 tools** are registered (`tools/tool_schemas.py`): system diagnostics, running processes, network connections, GPU driver info, disk health, registry query, installed apps, file search, folder size, file relevance, web search, page fetch, approximate location, and dynamic PowerShell execution. All are READ-tier auto-execute except `execute_powershell`, whose risk is classified per-command.

**Permissions** (READ / MODIFY / DESTRUCTIVE-SYSTEM-LEVEL) are enforced in Python (`agent/permissions.py`), never by model self-report. MODIFY and DESTRUCTIVE require user confirmation.

---

# File structure

```
nova/
  main.py                 # terminal CLI entry point
  settings.py             # settings loader/validator -> module constants
  settings.json           # user-editable runtime config
  agent/
    loop.py               # ReAct loop (terminal + API entry points)
    client.py             # Ollama /api/chat wrapper
    prompts.py            # system prompt
    permissions.py        # risk classification + confirmation
    annotations.py        # recovery/verification notes on tool results
    tool_registry.py      # name -> tool function map
  api/
    server.py             # FastAPI server (127.0.0.1:8000)
  tools/
    __init__.py
    tool_schemas.py       # TOOL_SCHEMAS (JSON function schemas)
    filesystem.py
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
    test_permissions.py
    test_validation.py
    test_powershell.py
    test_websearch.py
  docs/index.md
  requirements.txt
  pytest.ini
  README.md
```

---

# agent/

## client.py
`OllamaUnavailableError` exception. Wraps Ollama's `/api/chat`.

- `chat(messages, tools=None, stream=False, timeout=OLLAMA_REQUEST_TIMEOUT)` — POST to `OLLAMA_URL` with `model`, `messages`, `tools`, `num_ctx`/`num_predict`. Raises `OllamaUnavailableError` on connection/timeout/HTTP errors. Returns parsed JSON.
- `extract_tool_calls(response_json)` — returns `[{"name", "arguments": {...}}]`. Handles string-encoded JSON arguments; on parse failure wraps args as `{"_raw": ...}`. Empty list if no tool calls.
- `get_final_text(response_json)` — returns `message.content` (the model's plain-text answer).

## loop.py
`run_turn_core` is the shared event generator; `run_turn` (terminal) and `run_turn_events` (API) are separate thin wrappers (deliberately kept distinct).

- `run_turn_core(user_input, messages, conversation_id=None, sync_confirm_callback=None)` — the ReAct loop: chat → extract tool calls → validate → classify risk → request permission if not READ → execute → annotate → repeat until answer or `MAX_ITERATIONS`. Yields events:
  - `{"type": "tool_started", name, args, tier, display}`
  - `{"type": "tool_finished", name, result, tier}`
  - `{"type": "permission_requested", id, details}`
  - `{"type": "answer", text}`
  - `{"type": "error", text}`
- `run_turn(user_input, messages, show_debug_tools=False, show_full_output=False)` — terminal interface; consumes events, prints progress, uses sync `request_confirmation`. Returns final text.
- `run_turn_events(user_input, messages, conversation_id)` — API interface; yields all core events (consumed as NDJSON). Uses async `PermissionManager`.
- `validate_tool_call(name, args, registry, schemas)` — checks registry membership, required args, and coercible scalar types. Returns `(ok, validated_args | error_message)`.
- `format_tool_progress(tool_number, name, arguments)` — `"N. <description>"` via `TOOL_PROGRESS_MESSAGES`.
- `resolve_permission(conversation_id, approved)` — resolves a pending async permission request.
- `PermissionManager` — thread-safe async permission resolution keyed by `conversation_id`.

## permissions.py
`RiskTier` enum: `READ`, `MODIFY`, `DESTRUCTIVE` (displayed "DESTRUCTIVE/SYSTEM-LEVEL").

- `classify_command(command)` — regex-classifies a PowerShell string. Order checked: DESTRUCTIVE patterns, MODIFY patterns, READ pattern, else **default MODIFY** (conservative).
- `classify_operation(tool_name, arguments)` — `execute_powershell` → `classify_command`; names in `READ_ONLY_TOOLS` → READ; anything else → DESTRUCTIVE (safety default). Never trusts model-supplied labels.
- `confirmation_details(tool_name, arguments, tier)` — human-readable prompt: action, actual operation, concrete impact, risk tier.
- `request_confirmation(details)` — terminal stdin `[y/N]`, returns bool.
- `execute_tool(tool_name, arguments, registry)` — pure executor; permission enforcement lives in the loop.
- `READ_ONLY_TOOLS` set — tool names that auto-execute (all except `execute_powershell`).

## annotations.py
- `is_execution_failure(tool_name, result)` — True if `execute_powershell` timed out or returned non-zero.
- `needs_verification(tool_name, arguments)` — True if the operation tier is not READ.
- `annotate_result(result, annotation_type, attempt_count=None)` — adds `_recovery_note` (scaled by `MAX_COMMAND_RETRIES=2`) or `_verification_note` to a result dict for model guidance.

## prompts.py
`SYSTEM_PROMPT` — compact numbered-rule system prompt (identity, personality, response length, user authority, 17 tool/system rules). Real current date/time is appended at runtime by `main.py` and `api/server.py`; never hardcode dates here.

## tool_registry.py
`TOOL_REGISTRY` — dict mapping each of the 14 tool names to its function reference.

---

# api/

## server.py
FastAPI app bound to `127.0.0.1:8000`. `CONVERSATIONS` dict holds in-memory message history keyed by `conversation_id`. No persistence.

- `GET /health` — `{"api": "ok", "ollama_reachable": bool}` (checks Ollama on localhost:11434 with `API_HEALTH_TIMEOUT`).
- `POST /chat` — body `{message, conversation_id?}`. Creates/reuses a conversation (fresh system prompt with current date), streams NDJSON: first `{"type":"conversation_id","id":...}`, then each event from `run_turn_events`. `Content-Type: application/x-ndjson`.
- `POST /permission` — body `{conversation_id, approved}`. Resolves a pending permission request. Returns `{"ok": True, ...}` or `{"ok": False, "error": "No pending permission request."}`.
- `GET /settings` — `{"values", "defaults", "ranges"}` from `settings.py`.
- `POST /settings` — body `{values: {...}}`. Validates + persists partial update. Returns `{"ok", "values", "rejected": [...], "restart_required": True}`.

---

# tools/

## tool_schemas.py
`TOOL_SCHEMAS` — list of OpenAI-style function schemas (`type: "function"`, `function: {name, description, parameters}`). Declarative metadata only; no executables. Descriptions are deliberately concise for small-model compatibility. **14 tools.**

## filesystem.py
- `search_files(pattern, root_path=None)` — PowerShell `Get-ChildItem -Recurse -Filter` over default roots (USERPROFILE, Program Files, Program Files x86) or a given root, with a time budget and `MAX_RESULTS` cap. Returns `{pattern, roots_searched, matches:[{path,size_mb}], count, truncated_by_time, truncated_by_count}`.
- `get_folder_size(path)` — recursive total size + top 10 immediate child items. Returns `{path, total_size_gb, largest_items:[{path,type,size_gb}], largest_items_truncated_by_time}` or `{error}`.
- `analyze_file_relevance(path)` — pure-Python signals: `{path, days_since_accessed, days_since_modified, in_temp_or_cache_path, appears_locked_by_another_process, size_mb|"n/a (folder)"}`. Reports signals only — never a delete verdict.
- `_default_roots()`, `_search_one_root(root, pattern, timeout)`, `_get_total_size(path, timeout)`, `_get_largest_items(path, timeout)`, `_check_if_locked(path)` — private helpers. `TEMP_CACHE_PATTERNS` is an extensible list.

## powershell.py
- `execute_powershell(command, timeout=DEFAULT_TIMEOUT)` — runs wrapped commands with `$ErrorActionPreference='Stop'` in `-NoProfile -NonInteractive`. Timeout clamped to `[1, POWERSHELL_MAX_TIMEOUT]`. Returns `{command, stdout, stderr, returncode, timed_out}`. On timeout captures partial output; on missing PowerShell sets a clear stderr message.

## processes.py
- `list_running_processes(limit=30, sort_by="memory")` — psutil enumeration. Returns `{processes:[{pid,name,memory_mb,exe_path}], shown, total_running, truncated}`. Sorted by memory (default) or name.
- `get_network_connections(limit=30)` — psutil `net_connections(kind="inet")`. ESTABLISHED sorted first; hard cap 40. Returns `{connections:[{pid,process_name,status,local_address,remote_address}], shown, total_connections, truncated}` or `{error, connections:[]}` (e.g. requires admin).

## registry.py
- `query_registry(key_path)` — reads a key via `winreg`. Allows only HKLM/HKCU/HKCR/HKU roots. Caps values at `REGISTRY_MAX_VALUES`, subkeys at `REGISTRY_MAX_SUBKEYS`. Returns `{key_path, values:[{name,value}], values_truncated, subkeys:[...], subkeys_truncated}` or `{error}`.
- `list_installed_apps()` — scans HKLM + HKCU + WOW6432 uninstall paths. Returns `{apps:[{name,version,publisher,install_date}], count, errors}`. Deduped by name+version; sorted by name.
- `_get_value`, `_read_values`, `_read_subkeys` — private helpers.

## system.py
- `get_system_diagnostics()` — `{cpu:{usage_percent,core_count_physical,core_count_logical}, ram:{total_gb,used_gb,percent_used}, disks:[{drive,total_gb,used_gb,free_gb,percent_used}], os:{name,version,build,uptime}}`. CPU/RAM/disk via psutil; OS info via PowerShell WMI.
- `get_gpu_driver_info()` — `{gpus:[{name,driver_version,driver_date,vram_gb}]}`. WMI base, enriched for NVIDIA with `_try_nvidia_smi()` (accurate driver version + VRAM).
- `get_disk_health()` — SMART via `Get-PhysicalDisk`. Returns per-disk `{device_id, friendly_name, media_type, health_status, operational_status, size}`; detects admin-required access-denied case.
- `_try_nvidia_smi()` — single implementation; runs `nvidia-smi --query-gpu=driver_version,memory.total`, returns `{driver_version, vram_gb}` or `None` if nvidia-smi is unavailable.

## websearch.py
Two-tier search; escalation logic lives in the tool, not the model.

- `web_search(query)` — tier 1 tries DDG→Bing→Google backends (`BACKENDS`); escalates to tier 2 (`Ollama` web search API, needs `OLLAMA_API_KEY` from `.env`). Quality gate `_results_are_sufficient()` (≥3 unique URLs, ≥3 detailed snippets, low CVE-count noise). Returns `{query, backend_used, tier, escalated, results:[{title,snippet,url}], warning?|error?}`.
- `fetch_page(url, max_chars=8000)` — `requests.get` + BeautifulSoup; strips script/style/nav/header/footer/aside/form; hard 20000-char ceiling. Returns `{url, content, truncated}` or `{url, error}`.
- `get_approximate_location()` — IP geolocation via `ip-api.com`. Returns `{location, source}` ("ip_geolocation" or "default_fallback"). The only tool that sends the public IP externally.

---

# app/

## main.js — Electron main process
Window (frameless, transparent, always-on-top, ~640x460), tray, global shortcut (default `Alt+Space`), single-instance lock, API communication, IPC handlers, PTY terminals. Security: `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`.

- `checkHealth(baseUrl)`, `streamChat(baseUrl, message, conversationId, onEvent)` (reads NDJSON body), `respondToPermission(...)`, `getAgentSettings(baseUrl)`, `saveAgentSettings(...)`.
- IPC channels: `nova:hide`, `nova:get-settings`, `nova:save-settings`, `nova:health`, `nova:permission`, `nova:send`, `nova:new-conversation`, `nova:get-agent-settings`, `nova:save-agent-settings`, and terminal channels.
- Note: the blur-to-hide behavior in `createWindow` is currently **commented out**.

## preload.js
`contextBridge.exposeInMainWorld("nova", ...)` — narrow renderer-safe surface: `send`, `newConversation`, `hide`, `onEvent`, `onStreamEnd`, `onFocusInput`, `health`, `respondToPermission`, `getSettings`, `saveSettings`, `getAgentSettings`, `saveAgentSettings`, `terminalStart/Input/Resize/Kill`, `onTerminalData`, `onTerminalExit`.

## renderer/index.html, renderer.js, style.css
Single-page chat UI: sidebar (Chat / Terminal 1 / Terminal 2 / Settings / New Conversation / status dot), chat log with markdown rendering (marked), tier-colored tool indicators, Approve/Decline permission prompts, two xterm terminals, and settings view. App settings fields: **API base URL** and **global shortcut** only. Light theme active via `[data-theme]`; dark theme also defined in CSS. `renderer.js` handles events, permission flow, settings load/save, terminal binding, and 15s health polling.

## settings.js
Electron client settings stored as JSON in `userData`. **DEFAULTS: `{ apiBaseUrl: "http://127.0.0.1:8000", globalShortcut: "Alt+Space" }`.** Functions: `settingsPath()`, `loadSettings()` (merges defaults, falls back on missing/invalid), `saveSettings(settings)`.

## terminals.js
Two node-pty PowerShell PTYs (IDs 1 and 2, both start in `C:\DEV\nova`). `startTerminal`, `writeTerminal`, `resizeTerminal`, `killTerminal`, `killAllTerminals`. Activates the project venv if present; aims for UTF-8 output.

## package.json
Dependencies: `@xterm/xterm`, `marked`, `node-pty` (native — `npm rebuild node-pty` may be needed). Dev: `electron`, `electron-builder`.

---

# Root

## main.py
Terminal CLI REPL. `main(show_debug_tools=False, show_full_output=False)` prints the banner, injects current date into the system prompt, loops on stdin calling `run_turn`. Handles `exit`/`quit`/EOF/Ctrl-C. `--debug-tools` shows raw tool calls; `--full-output` untruncates them (needs `--debug-tools`).

## settings.py
Loads and validates `settings.json` → exports module-level constants consumed everywhere. `DEFAULTS` + `INTEGER_RANGES` define allowed keys, types, and ranges; invalid values silently fall back to defaults. `save_settings(partial)` persists and returns `(merged, rejected)`. Enforces `powershell_max_timeout >= powershell_timeout`.

## settings.json
User-editable runtime config: model (`ollama_url`, `model`, `num_ctx`, `num_predict`), loop caps (`max_iterations`, `max_retries`), terminal truncation, PowerShell/filesystem/web/registry timeouts and limits, and internal tool timeout budgets.

## requirements.txt
Python dependencies. Install with `pip install -r requirements.txt`.

## pytest.ini
Sets `pythonpath = .` so imports resolve from the repo root.

## README.md
Project front page (currently a stub).
