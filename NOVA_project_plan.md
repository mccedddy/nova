# N.O.V.A. — Native Operating-system Virtual Assistant
## Project Plan

Local Windows-inspection and control agent powered by Ollama (currently `qwen3.5:9b`) using tool-calling. The first client is terminal-based; a local Python API is planned for future web and desktop clients.

---

## How to use this plan

Work top to bottom. Each phase has a **goal**, a **"done when" checkpoint**, and small numbered steps. Don't move to the next phase until the current phase's checkpoint passes. Later phases depend heavily on earlier ones being solid — a shaky agent loop or a permission layer built as an afterthought will cause problems far downstream.

---

## Phase 0 — Environment & groundwork
**Goal:** Confirm every moving part works in isolation before writing agent code.
**Done when:** You can hit Ollama's API from Python and get a normal chat response back, and you can run a PowerShell command from Python and capture its output.

1. Confirm `ollama serve` is running and `qwen3.5:9b` is available (`ollama list`).
2. Confirm the model supports tool calling in your Ollama version — test with a trivial `curl`/Python call to `/api/chat` passing a single dummy tool schema and see if it returns a `tool_calls` field instead of plain text.
3. Set up the Python project folder structure (see "Suggested folder layout" below).
4. Set up a virtual environment, install base deps (`requests` or `ollama` python package, `pywin32` for winreg/WMI helpers, `psutil` for process/network info).
5. Write a throwaway script that sends "hello" to Ollama's `/api/chat` and prints the reply — confirms the model endpoint works before any agent logic exists.
6. Write a throwaway script that runs a harmless PowerShell command (`Get-Date`) via `subprocess` and captures stdout — confirms the OS-interaction path works.
7. Decide and note down: which Python package for WMI (`wmi` package vs raw `Get-CimInstance` via subprocess vs `wmic`, noting `wmic` is deprecated on newer Windows builds — prefer `Get-CimInstance`).

**Suggested folder layout**
```
nova/
  main.py                 # entry point, terminal loop
  agent/
    loop.py                # one conversation turn and tool-calling loop
    client.py               # thin wrapper around Ollama /api/chat
    prompts.py              # system prompt
    progress.py             # terminal progress messages
    tool_registry.py        # executable tool lookup table
    validation.py           # tool-call validation
  tools/
    __init__.py             # tools package
    tool_schemas.py         # JSON schemas for all tools
    filesystem.py                 # search_files, get_folder_size, analyze_file_relevance
    registry.py                     # query_registry, list_installed_apps
    system.py                        # get_system_diagnostics, get_gpu_driver_info, get_disk_health
    processes.py                      # list_running_processes, get_network_connections
    websearch.py                       # web_search
  tests/
    test_<tool>.py          # focused tool tests
    test_agent.py           # mocked agent-loop tests
  api/                      # planned Python API for web/desktop clients
    server.py               # local HTTP entry point
    routes.py               # chat and health routes
    models.py               # request/response models
```

---

## Phase 1 — Minimal agent loop (completed)
**Goal:** Build the ReAct-style loop with one fake tool, so the plumbing is proven before real complexity enters.
**Done when:** The model can call a tool, receive its result, and answer in natural language — end to end.

1. Write `client.py`: a function `chat(messages, tools)` that POSTs to `/api/chat` with `stream=False` and returns the parsed JSON.
2. Write a small tool and its JSON schema by hand — this became the template for the real tools.
3. Write `loop.py`'s core cycle:
   - send user message + tool schemas to model
   - if response has `tool_calls`: execute the matching Python function, append result as a `tool` role message, loop again
   - if response has plain text and no tool call: print it, end turn
4. Add a hard iteration cap (e.g. max 6 tool calls per user turn) so a confused model can't loop forever.
5. Add basic console logging of every tool call the model makes and its result — you'll need this for debugging constantly, build it now not later.
6. Test manually: ask a question that requires the fake tool, confirm the full round trip works.

---

## Phase 2 — Tool-call robustness (completed)
**Goal:** Handle the fact that a local model *will* occasionally mangle tool calls — wrong tool name, malformed JSON args, missing required args, or calling a tool when it should've just answered in text.
**Done when:** You can feed the loop deliberately bad/edge-case inputs and it degrades gracefully instead of crashing.

1. Write a `validation.py` module that, before executing any tool call:
   - checks the tool name exists in your registry (if not: return an error message to the model as a tool result, not a Python exception, so the model can self-correct)
   - checks required args are present and roughly the right type (coerce simple mismatches like string "5" → int 5 where safe)
   - catches JSON parse failures on the arguments blob and returns a corrective error message to the model instead of crashing the loop
2. Add a retry policy: if a tool call fails validation, feed the error back to the model as a tool result ("invalid arguments: missing `path`") and let it try again — cap retries per tool call (e.g. 2) before giving up and telling the user directly.
3. Add a global try/except around actual tool *execution* (not just parsing) — a PowerShell call can fail for a hundred real-world reasons (permissions, path not found, etc.) and that should come back to the model as a normal tool result, not kill the process.
4. Decide on a timeout for tool execution (PowerShell/WMI calls can hang) — wrap subprocess calls with `timeout=` and handle `TimeoutExpired`.
5. Write a few deliberately adversarial manual tests: ask something ambiguous, ask something the model has no tool for, ask something where the natural first guess would be a malformed path.
6. Add explicit handling for Ollama itself being unreachable (connection refused, timeout, HTTP error) — catch these at the client level and surface a clean message rather than an unhandled traceback.

---

## Phase 3 — Implement real tools, one at a time (completed)
**Goal:** Each tool gets built, schema'd, and manually tested against your real machine before moving to the next. Don't batch these.

Suggested build order (easiest/lowest-risk first, so you're validating the loop pattern, not fighting tool complexity):

### 3.1 `get_system_diagnostics()`
- CPU model/usage, RAM total/used, per-drive space, OS build, uptime.
- Source: `Get-CimInstance Win32_OperatingSystem`, `Win32_Processor`, `Win32_LogicalDisk`, or `psutil` for CPU/RAM (simpler, cross-checks WMI).
- Good first tool: no arguments, low risk, easy to eyeball-verify against Task Manager.

### 3.2 `list_running_processes()`
- Name, PID, memory, exe path. `psutil.process_iter()` is simplest here.
- Decide on output shaping now: raw dump of 200+ processes will blow up context — cap/sort by memory, or let the model pass a filter arg.

### 3.3 `get_network_connections()`
- netstat-style: local/remote address, port, owning process. `psutil.net_connections()` (may need admin privileges — note this down and handle the permission-denied case explicitly).

### 3.4 `get_gpu_driver_info()`
- `Get-CimInstance Win32_VideoController` for model + driver version. If NVIDIA, optionally also try `nvidia-smi` and merge/prefer whichever is more precise — WMI's `AdapterRAM` field is known to overflow/misreport VRAM on cards with 4GB+, prefer `nvidia-smi` for that figure specifically.

### 3.5 `get_disk_health()`
- SMART status via `Get-PhysicalDisk | Select-Object HealthStatus, OperationalStatus` (Storage cmdlets, Win10/11). Note: some of this needs admin rights — plan for a clear "run as admin" message if access is denied rather than a silent failure.

### 3.6 `query_registry(key_path)`
- Generic `winreg` read: open key, enumerate values and subkeys, return as structured data.
- Validate `key_path` against an allowlist of root hives (HKLM, HKCU, HKCR, HKU) before touching `winreg` — this is your one read tool with real footgun potential (typos, huge keys) even though it's read-only.
- Decide a max-depth / max-items-returned cap so a request like the root of HKLM doesn't return megabytes.

### 3.7 `list_installed_apps()`
- Enumerate `HKLM\...\Uninstall` and `HKCU\...\Uninstall` (and the WOW6432Node path for 32-bit apps on 64-bit Windows — easy to forget, doubles your app list if missed).
- Return name, version, publisher, install date. Do not return or expose the uninstall string.

### 3.8 `search_files(pattern, root_path=None)`
- Recursive search by name/glob pattern (simple wildcards only — `*`/`?`, no brace expansion, no regex). Default roots if none given: `C:\Users\<you>`, `C:\Program Files`, `C:\Program Files (x86)`.
- Use `Get-ChildItem -Recurse` via PowerShell (faster than Python's `os.walk` for large trees) with a time budget and a result cap — tell the model/user when a result is partial.
- Return path + size for matches, capped at a reasonable count (tune based on real context-window testing).

### 3.9 `get_folder_size(path)`
- Recursive size sum + breakdown of largest subfolders/files.
- Same performance consideration as `search_files` — time budget, partial results rather than hanging.

### 3.10 `analyze_file_relevance(path)`
- Last accessed/modified time, whether path matches known temp/cache patterns (kept in an easily-extendable constant list), and whether any running process currently has it open/locked.
- File-lock check: try opening the file exclusively and catch `PermissionError` — imperfect but sufficient for v1; doesn't identify *which* process holds the lock.
- This tool returns *signals*, not a verdict — it does not output "safe to delete: yes/no." The model synthesizes the signals into an answer.

### 3.11 `web_search(query)`
- Uses `ddgs`, trying multiple backends (DuckDuckGo, Bing, Google) in sequence so a single backend failure doesn't fail the whole search — no API key required for any of them.
- Summarize/trim results before returning to the model — full page content would blow the context window. Return top N results as (title, snippet, url).
- Trigger condition lives in the system prompt: use only when the model doesn't recognize something from its own knowledge, or to check current information.

### 3.12 `fetch_page(url)`
- Fetches and extracts readable text from a specific page after `web_search`, for when snippets aren't detailed enough (e.g. exact version comparisons, full technical detail).
- Rejects non-HTML content (PDFs, binaries) cleanly via `Content-Type` header check rather than passing garbage bytes to the model.
- Tunable `max_chars` argument (sane default, hard ceiling) so the model can request more detail when genuinely needed without risking unbounded context usage.

### 3.13 `get_approximate_location()`
- Resolves city-level location via IP geolocation, only when a request needs location context and none was given (e.g. weather questions).
- Falls back to a hardcoded default location if the geolocation service is unreachable.
- This is the one tool that sends anything (the public IP, implicitly) to an external service — worth being explicit about that in its description, since every other tool only reads local system state.

**For every tool above, repeat this mini-checklist:**
- [ ] Write the JSON schema in `tool_schemas.py`
- [ ] Implement the function in isolation, test it directly (no model involved) with a real path/value on your machine
- [ ] Register it in the tool registry
- [ ] Ask the model a natural-language question that should trigger it, confirm it picks the right tool with sane arguments
- [ ] Try one deliberately bad case (nonexistent path, access-denied folder, etc.) and confirm it fails gracefully

---

## Phase 4 — System prompt & tool-selection quality (completed)
**Goal:** Now that all tools exist, tune how the model chooses between them — this is where most of your iteration time will actually go.
**Done when:** A representative set of local, web, ambiguous, and multi-step questions route to sensible tools and produce correct, well-formed answers.

1. Write a system prompt that: describes NOVA's purpose, states the read-only/no-destructive-action boundary explicitly (as it applied through Phase 7), and instructs the model to ask a clarifying question rather than guess when a request is ambiguous.
2. Run a representative question set through the full system, log which tool(s) get called, and check they're the *right* ones.
3. For multi-step questions (e.g. "is my GPU driver outdated" requires a local check *and* `web_search`), confirm the model correctly chains tool calls instead of stopping after one.
4. Iterate on tool *descriptions* (in the schema, not just the system prompt) when the model picks the wrong tool — this is usually a description-wording problem, not a model-capability problem.
5. Add explicit instructions for patterns discovered through testing: don't fabricate specific details not present in tool results; don't over-search when results are inconclusive after 2-3 attempts; give real values (never placeholders like `[username]`) when the model has the tools to resolve them; chain a local check with `web_search` for "is X outdated"-type questions rather than claiming a capability is unavailable without trying it.
6. Inject the real current date/time into the system prompt at runtime (not left to the model's training-data guess) so date-relative reasoning ("has X already happened") is accurate.
7. Keep the system prompt as tight, numbered, imperative rules rather than long prose paragraphs — smaller local models have limited instruction-following headroom, and unnecessary length/complexity in the system prompt is a real risk factor for degraded tool-calling reliability.
8. Treat excessive web-search/fetch chains and long unrelated answers as failures even when the process eventually returns an answer.

---

## Phase 5 — Terminal UX polish (completed)
**Goal:** Make it pleasant to actually use day to day.
**Done when:** You'd hand this to yourself six months from now without wincing.

1. Basic REPL loop with a clear prompt, and a way to exit cleanly (`exit`/`quit`/Ctrl+C handled gracefully).
2. Pretty-print tool calls as they happen (progress messages per tool, e.g. "Checking disk health...") so the user isn't staring at a blank screen during multi-tool chains.
3. Add a debug flag (`--debug-tools`) to optionally show raw tool names/arguments/results, and a further flag (`--full-output`) to show untruncated results when debugging.
4. Handle long tool outputs sensibly in the terminal (truncate by character count, not line count, since tool results are typically single-line reprs — show a "+N more characters" note rather than flooding the terminal, while the model itself always receives the full untruncated data).
5. Simple in-session conversation history so follow-up questions retain context — no persistence to disk, in-memory for the session only.
6. Streaming output was attempted (token-by-token display) and then deliberately removed: it added real implementation complexity, directly caused a print-duplication bug when combined with tool-call handling, and had no effect on answer quality or correctness. Non-streaming (wait for full response, then print) is the settled approach for the terminal client.

---

## Phase 6 — Testing pass (completed)
**Goal:** Confirm the whole thing holds up, not just the happy path.
**Done when:** You've deliberately tried to break it and it degraded gracefully every time.

1. Re-run the representative example questions end to end after all polish changes.
2. Test permission-denied scenarios explicitly (run once as non-admin) — confirm registry/disk-health/network tools fail with a clear message rather than a stack trace.
3. Test what happens when Ollama is unreachable (service stopped) — should fail with a clear message, not hang or silently print nothing.
4. Test a rapid-fire ambiguous question ("clean up my computer") to confirm the model asks for clarification instead of inventing a destructive-sounding plan.
5. Add mocked tests for the agent turn so loop changes can be validated without calling Ollama or scanning the machine — mock the Ollama-facing chat function itself, feed scripted response sequences, assert on the resulting message history and returned/yielded values. Cover: successful single tool call, missing-argument retry-then-give-up, unknown tool name, MAX_ITERATIONS cap, Ollama-unreachable handling, a retry that successfully self-corrects, multiple tool calls in one model response, and a real Python exception during tool execution (not just a validation failure) being caught gracefully.
6. Add direct unit tests for the validation module in isolation (valid args pass through, missing required args detected individually and in combination, unknown tool name rejected, string-to-int coercion works, uncoercible values reported as errors) — faster and more precise than exercising validation only through the full loop.
7. Keep a fixed comparison prompt (one that forces multi-tool chaining plus a web-search/fetch escalation) as a manual, repeatable regression check to run after structural changes — model output is not expected to be identical between runs, but the *pattern* of tool usage and answer quality should stay consistent.

---

## Phase 7 — Local Python API (completed)
**Goal:** Expose the agent core to web or desktop clients while keeping the terminal client working, without risking regressions to the terminal client in the process.
**Done when:** A local HTTP client can submit a prompt, receive structured events and a final answer, and maintain an isolated conversation — while the terminal client continues to work exactly as before, unaffected by anything built in this phase.

1. Choose a small HTTP framework — FastAPI, plus `uvicorn` to run it.
2. Do not modify the terminal's existing agent-loop function to produce this API. Build a **separate** event-yielding function specifically for API consumption, adapted from the terminal's loop logic but kept in its own file. An earlier attempt to make one shared function serve both the terminal (printing) and the API (structured events) caused real regressions — a broken indentation bug and a print-duplication bug — precisely from the added complexity of one function trying to serve two different output needs at once. Keep them separate until the API side is fully proven; consolidate later as a deliberate, isolated refactor if desired.
3. The event-yielding function should yield structured dicts as it works: `tool_started` (name + args), `tool_finished` (name + result), `answer` (final text), `error` (failure message). No `assistant_token` event is needed unless streaming is reintroduced specifically for the API (see step 5).
4. Add a `POST /chat` route accepting a JSON body with `message` and an optional `conversation_id`. If no ID is given, generate one and start a new conversation; if given, look up and continue the existing conversation's message history.
5. Return the event stream as the HTTP response body using newline-delimited JSON (one JSON object per line), so a client can process events as they arrive without needing full SSE/WebSocket infrastructure for a first version. Upgrade to SSE or WebSockets later if a real client needs it.
6. Add a `GET /health` route that reports whether the API itself is up and whether Ollama is reachable, without exposing any system diagnostic details in the response.
7. Keep conversation histories isolated per `conversation_id`, held in memory only (a plain dict keyed by ID) — no persistence to disk, matching the terminal client's same in-memory-only scope.
8. Bind the server to `127.0.0.1` explicitly when running it — never `0.0.0.0` — until an authentication/access-control layer exists. Do not expose this to a LAN or the internet in this phase.
9. Test the API directly (curl or similar) with a live Ollama instance, confirming both a simple non-tool question and a tool-requiring question work correctly through the HTTP layer.
10. Confirm the terminal client (`python main.py`) still works completely normally, run at the same time as the API server, unaffected.
11. Add mocked tests for the API's event-yielding function, following the same pattern established in Phase 6 for the terminal's loop function — mock the chat call, assert on yielded event sequences.

---

## Phase 8 — Permission & Security Layer (completed)
**Goal:** Before any tool can modify or execute anything on the system, a deterministic, code-enforced permission layer must exist — one the model cannot bypass through phrasing, framing, or persuasion.
**Done when:** Every tool or capability that can change system state is classified into a risk tier, and the classification and enforcement live entirely in Python code, not in system-prompt instructions the model is merely asked to follow.

1. Define three risk tiers: **READ** (inspects only, auto-executes), **MODIFY** (changes something but isn't inherently destructive — e.g. moving or renaming a file, starting/stopping a non-critical service — requires user confirmation), **DESTRUCTIVE/SYSTEM-LEVEL** (permanent deletion, formatting, registry deletion, system restart/shutdown, execution policy changes, anything requiring admin elevation — requires explicit user confirmation with impact clearly stated).
2. Build the classification as a function or module the execution layer calls *before* running any state-changing tool or command — never rely on the model self-reporting which tier its own action belongs to.
3. For dynamic command generation (Phase 9), the classifier needs to inspect the actual command/cmdlet being run (e.g. detect `Remove-Item`, `Format-*`, `Stop-Process`, `reg delete`, `Set-ExecutionPolicy`, `Restart-Computer` and similar patterns) and classify accordingly, since a model-generated command's risk can't be known just from which tool was called.
4. Design the confirmation UX to state three things before asking: the plain-language action being proposed, the actual command/operation that will run, and the concrete impact (e.g. "37 files will be permanently deleted from C:\Users\you\Downloads"). Never a bare "are you sure?" with no context.
5. Ensure a rejected/declined confirmation cleanly aborts the action and reports that back to the model as a normal tool result (e.g. "user declined this action"), so the agent loop can continue the conversation rather than crashing or hanging.
6. This phase is a hard prerequisite for Phase 9 — no tool or capability that can mutate the system or files should be built or wired into the agent loop before this layer exists and is tested.
7. Write tests (mocked, no live model needed) confirming: READ-tier actions execute without any confirmation step; MODIFY/DESTRUCTIVE-tier actions correctly halt and wait for confirmation; a declined confirmation is handled gracefully; the classifier correctly identifies a sample of known-destructive command patterns.

---

## Phase 9 — Dynamic PowerShell Execution (completed)
**Goal:** Move from a fixed set of predefined tools toward a smaller set of general-purpose primitives the model can compose dynamically, while keeping existing native tools as fast, reliable, deterministic shortcuts for known common operations.
**Done when:** The model can successfully accomplish a task that has no dedicated native tool by generating and executing an appropriate PowerShell command, with the Phase 8 permission layer correctly gating anything beyond simple reads.

1. Add `execute_powershell(command)` as a new general-purpose tool — the model's escape hatch for anything not covered by an existing native tool.
2. Every `execute_powershell` call passes through the Phase 8 permission layer before running. Read-only cmdlets (the `Get-*` family and similar) can auto-execute; everything else requires confirmation per Phase 8's tiers.
3. Keep all existing native tools (`get_system_diagnostics`, `list_running_processes`, etc.) exactly as they are — the model should still prefer a native tool over generating equivalent PowerShell when one exists, both for speed and reliability. Update the system prompt to state this preference explicitly.
4. Set a reasonable timeout on `execute_powershell` calls, matching the pattern already used for other subprocess-based tools, so a hung command doesn't hang the whole agent loop.
5. Return command output, exit code, and any stderr content back to the model in a structured way, so it can reason about success/failure rather than just getting a blob of text.
6. Manually test a range of commands the model generates on its own for varied requests, checking both that harmless reads execute smoothly and that anything destructive correctly triggers the Phase 8 confirmation flow rather than executing silently.
7. Deliberately test adversarial/ambiguous requests (e.g. something that could be read as either informational or destructive) to confirm the permission layer, not the model's judgment, is what determines whether confirmation is required.

---

## Phase 10 — Search Escalation (completed)
**Goal:** Make `web_search` an adaptive two-tier system, escalating to a stronger search method only when the first attempt is genuinely insufficient, rather than always paying the cost of multiple searches.
**Done when:** A query that DDGS handles well returns from a single search tier; a query where DDGS results are weak or insufficient automatically escalates to the second tier without the model needing to explicitly decide to do so.

1. Keep the existing DDGS-based `web_search` (DuckDuckGo → Bing → Google fallback chain) as the first, default attempt — it's fast and requires no API key.
2. Identify and integrate a second-tier search option for cases where DDGS results are insufficient (e.g. Ollama's own web search capability, if/when accessible, or another documented-quality source).
3. Build an evaluation step — either heuristic (e.g. number of results, whether snippets actually address the query) or model-judged — that decides whether first-tier results are "good enough" before deciding whether to escalate. Do not escalate unconditionally on every query, since that wastes time and any rate-limited quota on the second tier.
4. Expose this to the model as a single conceptual `search_web(query)` capability where possible, so the model doesn't need to know or decide which backend tier is being used — the escalation logic lives in the tool implementation, not in the model's tool-selection reasoning.
5. This phase becomes considerably more valuable once Phase 9 exists, since dynamic PowerShell command generation will benefit from being able to look up obscure or unfamiliar Windows/PowerShell-specific documentation — but the escalation mechanism itself is independent of Phase 9 and can be built and tested on its own first.

---

## Phase 11 — Failure Recovery Loop (completed)
**Goal:** When a generated PowerShell command (Phase 9) fails, the agent should analyze the failure and attempt a fix or alternate approach automatically, rather than simply reporting the error and stopping.
**Done when:** A deliberately malformed or outdated command, fed through the agent, results in the model correctly diagnosing the failure and either correcting the command or searching for the right approach, then successfully completing the original task.

1. Ensure command execution failures (non-zero exit code, stderr content, "command not recognized," etc.) are returned to the model as a clear, structured tool result — not swallowed or generically reported.
2. Update the system prompt to instruct the model, on receiving a command failure, to analyze the specific error rather than immediately giving up or blindly retrying the identical command.
3. Encourage a recovery pattern: on failure, the model should either (a) correct an obvious mistake in its own command and retry, (b) use `web_search`/`fetch_page` to look up correct syntax or documentation, or (c) try a genuinely different approach to the same underlying goal — not simply repeat the same failing command.
4. Cap recovery attempts per task (reuse or extend the existing `MAX_RETRIES`/`MAX_ITERATIONS` pattern from the core agent loop) so a persistently failing task still terminates gracefully with a clear explanation rather than looping indefinitely.
5. Manually test with commands that are deliberately wrong in different ways (typo'd cmdlet, wrong parameter, deprecated command) and confirm the model's recovery behavior in each case.

---

## Phase 12 — Verification (completed)
**Goal:** Actions should be confirmed to have actually achieved their intended effect, not assumed successful just because a command returned without an error.
**Done when:** After a state-changing action, the agent performs a follow-up check confirming the expected outcome before reporting success to the user.

1. For any action from Phase 9 that has an observable, checkable outcome (a file deleted, a process stopped, disk space freed, a service started), have the agent perform a follow-up read-only check after execution rather than trusting a clean exit code alone.
2. Update the system prompt to require this verify-then-report pattern explicitly: act, then observe the resulting state, then report — not act, then assume, then report.
3. If verification shows the expected outcome did *not* occur (e.g. a file still exists after a supposed deletion), the agent should say so plainly and investigate further or inform the user, rather than reporting success anyway.
4. Test with at least one case where an action appears to succeed at the command level but doesn't actually achieve the intended result (e.g. a permission issue that doesn't surface as a hard error), confirming the verification step catches the discrepancy.

---

## Phase 13 — Windows Desktop UI Client
**Goal:** Replace the terminal as the primary everyday interface with a Windows desktop application that consumes the existing local API.
**Done when:** The user can open the app, type a request, submit it with a button or keyboard shortcut, see tool progress and the final answer, and continue a conversation without using the terminal directly.

1. Choose Electron as the Windows desktop shell. Build the interface with normal web technologies such as HTML, CSS, and JavaScript, optionally using React, Vue, or Svelte. Electron provides the desktop window, tray behavior, global shortcuts, and local process integration while preserving the CSS-based customization familiar from web development.
2. Build the app as a separate client of Phase 7's API: the desktop UI sends requests to and receives events from the Python API. This is the reason the API exists; "separate client" means a separate interface process, not a duplicate agent loop. Do not copy agent logic into the desktop application.
3. Add a main chat window with a prompt editor, submit/cancel controls, conversation history, tool-progress events, errors, and final answers.
4. Let the user type a request first, then submit it with a configurable global shortcut such as `Alt+Space`. The shortcut should focus/show the prompt window; it must not silently submit unfinished text.
5. Add a system-tray icon so the app can stay available without occupying the taskbar, with show/hide, quit, and shortcut settings.
6. Keep the first version Windows-only and local-only. The UI communicates with `127.0.0.1`; it does not expose the API publicly. Keep frontend styling in ordinary CSS so colors, spacing, typography, layouts, themes, and animations remain easy to customize.
7. Use CSS transitions, keyframes, or a frontend animation library for UI motion. Animate the shortcut flow so the window can reveal, slide, fade, or scale into view, and animate progress updates without blocking the chat workflow. Respect reduced-motion preferences and provide a setting to disable nonessential animation.
8. Test the desktop client against a running API and confirm the terminal client still works independently.

---

## Phase 14 — Desktop Settings & Operations
**Goal:** Make the desktop application the practical control center for NOVA's configuration and local services.
**Done when:** The user can inspect and change supported settings, manage Ollama and the Python API, and view useful process output without editing source files or manually managing terminal processes.

1. Make `settings.json` the user-editable source of runtime values, including model name, context size, prediction limit, iteration/retry limits, and tool timeouts. The Electron app reads and updates this JSON file; it must not rewrite Python source code.
2. Keep `settings.py` as the Python loader and validator. It supplies documented defaults, allowed types/ranges, and the single effective configuration consumed by the API, agent loops, and tools. Missing or invalid JSON values fall back to defaults.
3. Store the user file in a stable per-user location such as `%LOCALAPPDATA%\\NOVA\\settings.json` before packaging the application, so upgrades do not overwrite preferences. During development, a project-local `settings.json` may be used.
4. Add Apply, Reset to Defaults, and restart-required indicators. Do not silently change a running process when a setting requires a server restart.
5. Add Ollama process controls: detect whether Ollama is running, start the Ollama server, stop it, and show its current status. Do not start a second Ollama process when one is already running.
6. Capture and display Ollama server output in a bounded, scrollable log panel with clear-display, pause/resume, refresh, and filter controls. Preserve enough recent output for diagnosing startup, model-loading, and connection problems.
7. Add Python API process controls: status, start, stop, and restart. Display clear errors when the API cannot start, is already running, exits unexpectedly, or is unreachable.
8. Capture and display Python API output in a separate bounded log panel. Keep Ollama logs and API logs visibly distinct, and do not expose secrets such as API keys in the UI.
9. Add a diagnostics view for API health, Ollama reachability, selected model, and current configuration without exposing private system data unnecessarily.
10. Test settings persistence, invalid values, process detection, duplicate-start prevention, graceful stop/restart behavior, log truncation, unexpected process exits, and recovery when Ollama or the API is unavailable.

---

## Phase 15 — Voice Input & Output
**Goal:** Add optional voice interaction as a separate layer on top of the stable desktop UI and API.
**Done when:** The user can invoke voice capture, speak a request, see the transcribed text before submission, and optionally hear NOVA's response.

1. Choose Windows-compatible speech-to-text and text-to-speech components deliberately. Prefer local processing where quality and hardware allow it; document any cloud service and its data implications before enabling it.
2. Add push-to-talk or a clearly visible recording control. Do not submit audio-derived text without showing the transcript or giving the user a cancellation path.
3. Reuse the Phase 13 prompt editor and API client. Voice should produce normal text requests rather than a second agent loop.
4. Add optional text-to-speech playback with stop/replay controls and a setting to disable it.
5. Handle microphone permission, missing devices, recognition errors, and service timeouts without blocking the desktop UI.
6. Test voice as an optional feature so the text-only desktop workflow remains fully functional.

---

## Phase 16 — Persistent Memory
**Goal:** Allow the agent to remember useful facts across sessions (e.g. "my projects are usually in C:\DEV"), separate from and in addition to the existing in-session conversation history.
**Done when:** A fact stated in one session is correctly recalled and used in a later, separate session, while transient conversational statements are not incorrectly promoted into permanent memory.

1. This phase directly reopens a decision the project previously treated as explicitly out of scope (no persistent memory/logging across sessions) — treat starting this phase as a deliberate scope decision, not an incremental addition.
2. Decide on a storage mechanism (local file, local database) and where it lives on disk.
3. Design a clear boundary between what becomes persistent memory versus what stays session-only conversation context — not every statement the user makes should be treated as a permanent fact to remember.
4. Decide whether memory storage/updates require any user confirmation (per Phase 8's permission philosophy) or happen automatically, and be explicit about that choice.
5. Build a way for the user to view and clear stored memory, since persistent state the user can't inspect or reset is a trust problem.
6. Test that memory correctly persists across a full application restart, and that it's correctly incorporated into a new session's context without needing the user to restate it.

---

## Phase 17 — Plugin System
**Goal:** Support application-specific integrations (e.g. VS Code, Discord, Spotify) as independently addable modules, rather than growing the core agent codebase indefinitely as more integrations are added.
**Done when:** A new application-specific capability can be added as a self-contained module without modifying the core agent loop, tool registry pattern, or other unrelated tools.

1. Define what a "plugin" consists of structurally — likely a self-contained module exposing its own tool schemas and registry entries, following the same pattern already established for the core `tools/` modules.
2. Decide how plugins are discovered and loaded — explicit registration in a central list, or automatic discovery of a plugins folder.
3. Build one real plugin end-to-end as a proof of concept before considering the system validated — pick whichever application integration is most immediately useful.
4. Ensure a broken or misbehaving plugin can't take down the core agent loop — apply the same defensive execution patterns (try/except around execution, validation before dispatch) already used for core tools.
5. Document the plugin interface clearly enough that a new plugin could be added later without needing to re-derive the pattern from scratch.

---

## Explicitly out of scope until deliberately revisited

- Public deployment or unauthenticated remote access to the API — stays bound to `127.0.0.1` until an explicit authentication/access-control decision is made and implemented.
- Any capability in Phases 8 through 17 being started without a deliberate decision to begin that specific phase — none of this work should happen incidentally while working on something else.
- Persistent memory/logging (Phase 16) remains out of scope until that phase is explicitly and separately decided on, independent of any other phase's progress.

---

## Suggested order of attack, summarized

| Phase | What | Est. relative effort |
|---|---|---|
| 0 | Environment checks | Small |
| 1 | Minimal agent loop | Small–Medium |
| 2 | Validation/retry robustness | Medium |
| 3 | 13 read-only tools | Large |
| 4 | System prompt + tool-selection tuning | Medium |
| 5 | Terminal UX | Small |
| 6 | Testing pass | Small–Medium |
| 7 | Local Python API | Medium |
| 8 | Permission & security layer | Medium |
| 9 | Dynamic PowerShell execution | Large |
| 10 | Search escalation | Small–Medium |
| 11 | Failure recovery loop | Medium |
| 12 | Verification | Small–Medium |
| 13 | Windows desktop UI client | Large |
| 14 | Desktop settings & operations | Medium–Large |
| 15 | Voice input & output | Medium–Large |
| 16 | Persistent memory | Medium |
| 17 | Plugin system | Medium |