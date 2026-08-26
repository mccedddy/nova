# N.O.V.A. — Native Operating-system Virtual Assistant
## Project Plan

Local, read-only Windows-inspection agent powered by Ollama (currently `qwen3.5:9b`) using tool-calling. The first client is terminal-based; a local Python API is planned for future web and desktop clients. No destructive actions.

## Current status

The core tool and terminal foundation is implemented:

- 13 read-only tools are implemented across `tools/`.
- Native Ollama tool calling, streaming output, validation, retries, and tool timeouts are implemented.
- Tool schemas live in `tools/tool_schemas.py`.
- Tool registration lives in `agent/tool_registry.py`.
- The system prompt and terminal progress messages live in `agent/prompts.py` and `agent/progress.py`.
- The next priority is controlled behavioral testing after each small refactor.
- Full mocked agent-loop tests and the API layer are still outstanding.

---

## How to use this plan

Work top to bottom. Each phase has a **goal**, a **"done when" checkpoint**, and small numbered steps. Don't move to the next phase until the current phase's checkpoint passes — this project lives or dies on the agent loop being solid *before* you pile 11 tools on top of it. A shaky loop with 1 tool is a debugging nightmare with 11.

Suggested pace: Phases 0–2 are the foundation and deserve the most care. Phase 3 is where you'll spend the most calendar time (one tool at a time). Treat each tool in Phase 3 as its own mini-project with its own test.

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

## Phase 2 — Tool-call robustness
**Goal:** Handle the fact that a 14b local model *will* occasionally mangle tool calls — wrong tool name, malformed JSON args, missing required args, or calling a tool when it should've just answered in text.
**Done when:** You can feed the loop deliberately bad/edge-case inputs and it degrades gracefully instead of crashing.

1. Write a `validation.py` module that, before executing any tool call:
   - checks the tool name exists in your registry (if not: return an error message to the model as a tool result, not a Python exception, so the model can self-correct)
   - checks required args are present and roughly the right type (coerce simple mismatches like string "5" → int 5 where safe)
   - catches JSON parse failures on the arguments blob and returns a corrective error message to the model instead of crashing the loop
2. Add a retry policy: if a tool call fails validation, feed the error back to the model as a tool result ("invalid arguments: missing `path`") and let it try again — cap retries per tool call (e.g. 2) before giving up and telling the user directly.
3. Add a global try/except around actual tool *execution* (not just parsing) — a PowerShell call can fail for a hundred real-world reasons (permissions, path not found, etc.) and that should come back to the model as a normal tool result, not kill the process.
4. Decide on a timeout for tool execution (PowerShell/WMI calls can hang) — wrap subprocess calls with `timeout=` and handle `TimeoutExpired`.
5. Write a few deliberately adversarial manual tests: ask something ambiguous, ask something the model has no tool for, ask something where the natural first guess would be a malformed path.

---

## Phase 3 — Implement real tools, one at a time
**Goal:** Each tool gets built, schema'd, and manually tested against your real machine before moving to the next. Don't batch these.

Suggested build order (easiest/lowest-risk first, so you're validating the loop pattern, not fighting tool complexity):

### 3.1 `get_system_diagnostics()`
- CPU model/usage, RAM total/used, per-drive space, OS build, uptime.
- Source: `Get-CimInstance Win32_OperatingSystem`, `Win32_Processor`, `Win32_LogicalDisk`, or `psutil` for CPU/RAM (simpler, cross-checks WMI).
- Good first tool: no arguments, low risk, easy to eyeball-verify against Task Manager.

### 3.2 `list_running_processes()`
- Name, PID, memory, exe path. `psutil.process_iter()` is simplest here.
- Decide on output shaping now: raw dump of 200 processes will blow up context — cap/sort by memory, or paginate, or let the model pass a filter arg.

### 3.3 `get_network_connections()`
- netstat-style: local/remote address, port, owning process. `psutil.net_connections()` (may need admin privileges — note this down and handle the permission-denied case explicitly).

### 3.4 `get_gpu_driver_info()`
- `Get-CimInstance Win32_VideoController` for model + driver version. If NVIDIA, optionally also try `nvidia-smi` and merge/prefer whichever is more precise.

### 3.5 `get_disk_health()`
- SMART status via `Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictStatus` or simpler `Get-PhysicalDisk | Get-StorageReliabilityCounter` (Storage cmdlets, Win10/11). Note: some of this needs admin rights — plan for a clear "run as admin" message if access is denied rather than a silent failure.

### 3.6 `query_registry(key_path)`
- Generic `winreg` read: open key, enumerate values and subkeys, return as structured data.
- Validate `key_path` against an allowlist of root hives (HKLM, HKCU, HKCR, HKU) before touching `winreg` — this is your one tool with real footgun potential (typos, huge keys) even though it's read-only.
- Decide a max-depth / max-items-returned cap so a request like the root of HKLM doesn't return megabytes.

### 3.7 `list_installed_apps()`
- Enumerate `HKLM\...\Uninstall` and `HKCU\...\Uninstall` (and the WOW6432Node path for 32-bit apps on 64-bit Windows — easy to forget, doubles your app list if missed).
- Return name, version, publisher, install date, uninstall string (read-only — don't touch the uninstall string).

### 3.8 `search_files(pattern, root_path=None)`
- Recursive search by name/glob pattern. Default roots if none given: `C:\Users\<you>`, `C:\Program Files`, `C:\Program Files (x86)`, maybe `C:\` itself as a slow last resort.
- This one needs real thought on performance: searching all of `C:` in Python (`os.walk`) is slow. Consider using `Get-ChildItem -Recurse` via PowerShell (often faster) or Windows Search index via `everything`-style COM/CLI if you want it fast — otherwise just cap depth/time and tell the model/user it's a partial result.
- Return path + size for matches, capped at some max count (e.g. 100) with a note if truncated.

### 3.9 `get_folder_size(path)`
- Recursive size sum + breakdown of largest subfolders/files.
- Reuse the walking logic from `search_files` where possible (shared helper) rather than duplicating.
- Same perf consideration: on a huge folder this can be slow — consider a progress-safe timeout and returning partial results rather than hanging.

### 3.10 `analyze_file_relevance(path)`
- Last accessed/modified time, whether path matches known temp/cache patterns (`\AppData\Local\Temp\`, `\Temp\`, `\Cache\`, `\CrashDumps\`, browser cache paths, etc. — keep this pattern list in a constant so it's easy to extend), and whether any running process currently has it open/locked.
- File-lock check: this is the fiddly one on Windows — no built-in Python way to check "is this file open by another process" cheaply. Options: try opening the file exclusively and catch `PermissionError` (works for simple cases, imperfect), or shell out to a tool like `handle.exe` (Sysinternals) if you're willing to bundle a third-party binary, or just skip lock-checking in v1 and note it as a known gap.
- This tool should return *signals*, not a verdict — resist the temptation to have it output "SAFE TO DELETE: yes/no". Let the model synthesize the signals into an answer; keep the tool itself purely descriptive.

### 3.11 `web_search(query)`
- Build this last, after the local tools prove the loop works, since it adds an external dependency.
- Pick the search backend (DDGS since you've used it before is the path of least resistance — no API key).
- Summarize/trim results before returning to the model — raw scraped pages will blow the context window. Return top N results as (title, snippet, url) tuples.
- Decide the trigger condition explicitly in the system prompt: "use web_search only when you don't recognize a process/file name from your own knowledge" — otherwise the model may reach for it constantly and slow every answer down.

### 3.12 `fetch_page(url)`
- Fetch readable text after `web_search` when snippets are insufficient.
- Enforce a response-size ceiling before returning content to the model.

### 3.13 `get_approximate_location()`
- Resolve city-level location only when a request needs location context and the user did not provide one.
- Keep the external geolocation behavior explicit because it sends the public IP to a third-party service.

**For every tool above, repeat this mini-checklist:**
- [ ] Write the JSON schema in `tool_schemas.py`
- [ ] Implement the function in isolation, test it directly (no model involved) with a real path/value on your machine
- [ ] Register it in the tool registry
- [ ] Ask the model a natural-language question that should trigger it, confirm it picks the right tool with sane arguments
- [ ] Try one deliberately bad case (nonexistent path, access-denied folder, etc.) and confirm it fails gracefully

---

## Phase 4 — System prompt & tool-selection quality
**Goal:** Now that all tools exist, tune how the model chooses between them — this is where most of your iteration time will actually go.
**Done when:** A representative set of local, web, ambiguous, and multi-step questions route to sensible tools and produce correct, well-formed answers.

1. Write a system prompt that: describes NOVA's purpose, lists the tools at a high level (schemas already do the detail), states the read-only/no-destructive-action boundary explicitly, and instructs the model to ask a clarifying question rather than guess when a request is ambiguous (e.g. "delete garbage files" with no target given).
2. Run the representative question set through the full system, log which tool(s) get called, and check they're the *right* ones.
3. For multi-step questions ("is my GPU driver outdated" — requires `get_gpu_driver_info` *and* `web_search` to check the latest version), confirm the model correctly chains two tool calls instead of stopping after one.
4. Iterate on tool *descriptions* (in the schema, not just the system prompt) when the model picks the wrong tool — this is usually a description-wording problem, not a model-capability problem.
5. Record tool order, repeated calls, total model requests, unsupported claims, and answer focus.
6. Treat excessive web-search/fetch chains and long unrelated answers as failures even when the process eventually returns an answer.

---

## Phase 5 — Terminal UX polish
**Goal:** Make it pleasant to actually use day to day.
**Done when:** You'd hand this to yourself six months from now without wincing.

1. Basic REPL loop with a clear prompt, and a way to exit cleanly (`exit`/`quit`/Ctrl+C handled gracefully).
2. Streaming output if Ollama's API supports it for the final answer (nicer UX than waiting for the whole response).
3. Pretty-print tool calls as they happen (e.g. dim/gray text: "→ checking disk health...") so the user isn't staring at a blank screen during multi-tool chains.
4. Handle long tool outputs sensibly in the terminal (truncate huge file lists with a "+N more" instead of dumping 500 lines).
5. Simple in-session conversation history so follow-up questions ("what about the other drive?") retain context — still no persistence to disk yet, just in-memory for the session per your scope.

Streaming output, progress messages, debug tool output, clean exits, and in-memory history are already implemented. Remaining work includes terminal output truncation and broader automated coverage.

---

## Phase 6 — Testing pass
**Goal:** Confirm the whole thing holds up, not just the happy path.
**Done when:** You've deliberately tried to break it and it degraded gracefully every time.

1. Re-run all 12 example questions end to end after all polish changes.
2. Test permission-denied scenarios explicitly (run once as non-admin) — confirm registry/disk-health/network tools fail with a clear message rather than a stack trace.
3. Test on a path with unusual characters/very long paths (Windows `MAX_PATH` issues are real — consider `\\?\` prefix handling if you hit this).
4. Test what happens when Ollama is unreachable (service stopped) — should fail with a clear message, not hang forever.
5. Test a rapid-fire ambiguous question ("clean up my computer") to confirm the model asks for clarification instead of inventing a destructive-sounding plan.
6. Add mocked tests for the agent turn so loop changes can be validated without calling Ollama or scanning the machine.
7. Keep the fixed comparison prompt as a manual model-quality regression test; output is not expected to be identical between stochastic model runs.

---

## Phase 7 — Local Python API
**Goal:** Expose the agent core to web or desktop clients while keeping the terminal client working.
**Done when:** A local client can submit a prompt, receive structured progress and final output, and maintain an isolated conversation without directly accessing Ollama or Windows tools.

1. Choose a small HTTP framework, preferably FastAPI, and add it as an explicit dependency.
2. Separate agent execution from terminal printing so the core can return events instead of writing directly to stdout.
3. Add a `POST /chat` route accepting a message and conversation ID.
4. Add a health route that reports API and Ollama connectivity without exposing system details unnecessarily.
5. Support streamed responses with Server-Sent Events (SSE) or WebSockets.
6. Keep conversation histories isolated per client or conversation ID; do not persist them until persistence is explicitly designed.
7. Bind to `127.0.0.1` by default. Add authentication and access controls before allowing LAN or internet access.
8. Return structured events such as `tool_started`, `tool_finished`, `assistant_token`, `answer`, and `error`.
9. Test the API with mocked Ollama responses before connecting a real web or desktop frontend.

---

## Explicitly out of scope for this phase
Keep a running "not now" list so scope doesn't creep mid-build:
- Any actual delete/move/uninstall execution
- Persistent memory/logging across sessions
- A frontend implementation (web or desktop)
- Public deployment or unauthenticated remote access

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

