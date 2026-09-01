# Overview
N.O.V.A. (Native Operating-system Virtual Assistant) is a local Windows-inspection agent powered by Ollama that combines system diagnostics with natural language conversation. Instead of generic web searches, N.O.V.A. uses native tools to query running processes, network connections, registry keys, and disk health — all with permission-based safety controls.

Built with Electron as a Windows desktop client and an optional local Python API for web integration, N.O.V.A. provides voice input/output support, persistent memory across sessions, and the ability to execute dynamic PowerShell commands when no predefined tool matches the request.

**Key capabilities:**
- **System diagnostics**: CPU/RAM/disk/GPU/OS info with real-time data
- **Process management**: inspect running processes and network connections
- **Safe command execution**: risk-tiered permissions (READ/MODIFY/DESTRUCTIVE) for PowerShell
- **Web integration**: web search + page fetching for current information
- **Voice interaction**: optional STT/TTS for hands-free operation

**System architecture:**
- **Agent loop**: handles conversation flow, tool execution, validation, permissions, recovery, and verification
- **Native tools**: 18 pre-built utilities (filesystem, processes, registry, system diagnostics, etc.) plus dynamic `execute_powershell` for unknown tasks
- **Desktop client**: Electron-based UI with tray support, chat interface, and terminal windows
- **Python API**: FastAPI server exposing `/chat`, `/health`, and `/permission` endpoints


# File Structure

```
📁nova
 ├── 📁agent
 │    ├── 📄annotations.py
 │    ├── 📄client.py
 │    ├── 📄loop.py
 │    ├── 📄permissions.py
 │    ├── 📄prompts.py
 │    └── 📄tool_registry.py
 ├── 📁api
 │    └── 📄server.py
 ├── 📁app
 │    ├── 📁assets
 │    │    ├── 🖼️icon.png
 │    │    ├── 🖼️tray-icon.png
 │    │    └── 🖼️tray-icon@2x.png
 │    ├── 📦node_modules
 │    ├── 📁renderer
 │    │    ├── 📦vendor
 │    │    │    ├── 📄marked.umd.js
 │    │    │    ├── 📄xterm-addon-fit.js
 │    │    │    ├── 📄xterm.css
 │    │    │    └── 📄xterm.js
 │    │    ├── 📄index.html
 │    │    ├── 📄renderer.js
 │    │    └── 📄style.css
 │    ├── 📄api-client.js
 │    ├── 📄main.js
 │    ├── 📄package-lock.json
 │    ├── 📄package.json
 │    ├── 📄preload.js
 │    └── 📄settings.js
 ├── 📁docs
 │    └── 📄index.md
 ├── 📁temp
 ├── 📁tests
 ├── 📁tools
 │    ├── 📄__init__.py
 │    ├── 📄filesystem.py
 │    ├── 📄powershell.py
 │    ├── 📄processes.py
 │    ├── 📄registry.py
 │    ├── 📄system.py
 │    ├── 📄tool_schemas.py
 │    └── 📄websearch.py
 ├── 📦venv
 ├── 📄.env
 ├── 📄.gitignore
 ├── 📄main.py
 ├── 📄NOVA_project_plan.md
 ├── 📄pytest.ini
 ├── 📄README.md
 ├── 📄requirements.txt
 ├── 📄settings.json
 └── 📄settings.py
 ```

# File Definition

## agent/
## 📄client.py
- agent/client.py
- Client acts as a bridge between NOVA's agent layer and your local Ollama server. It handles HTTP requests, error handling, and response parsing.
    - chat(messages, tools=None, stream=False, timeout=OLLAMA_REQUEST_TIMEOUT)
        - Sends a prompt to Ollama. Builds the API payload with model settings, optionally includes tools for function calling, and handles connection errors/timeout errors. Returns the JSON response.

    - extract_tool_calls(response_json)
        - Parses tool/function calls from an Ollama response. Looks through the tool_calls array in the message object and extracts function name and arguments. If there are no tool calls, returns an empty list.

    - get_final_text(response_json)
        - Gets the plain text response content from the LLM's content field in the message object. Useful when you just want to display what the model said.

    - get_thinking(response_json)
        - Extracts the optional thinking field (if Ollama is configured to emit it) which can show the model's reasoning steps before generating the final output.

## 📄loop.py
- agent/loop.py
- Unified orchestration of conversation flow between user input and tool execution. Handles tool validation, execution, permissions, error recovery, and progress formatting for both terminal CLI and API modes.
    - run_turn_core(user_input, messages, conversation_id=None, sync_confirm_callback=None)
        - Core event generator shared between terminal and API modes. Yields structured events (tool_started, tool_finished, permission_requested, answer, error) for each turn. Orchestrates chat invocations, tool validation, execution, permission handling, error recovery, and summarization.

    - run_turn(user_input, messages, show_debug_tools=False, show_full_output=False)
        - Terminal interface: consumes core events, prints progress to console, returns final text answer. Used by main.py for CLI REPL interaction.

    - run_turn_events(user_input, messages, conversation_id)
        - API interface: yields all events from core for WebSocket streaming to client. Uses async event-based permission flow via resolve_permission(). Used by api/server.py to stream conversation to Electron app.

    - resolve_permission(conversation_id, approved)
        - Resolves a pending permission request (called from /permission API endpoint). Sets approval status and signals the waiting coroutine to proceed with tool execution.
    
    - validate_tool_call(name, args, registry, schemas)
        - Validates tool call by checking registry existence, finding schema, verifying required arguments, and coercing scalar types. Returns (success, validated_args or error_message).

    - format_tool_progress(tool_number, name, arguments)
        - Creates human-readable progress message by prepending tool number to description. Looks up predefined messages in TOOL_PROGRESS_MESSAGES dictionary.

## 📄permissions.py
- agent/permissions.py
- Risk classification and confirmation logic for N.O.V.A.'s tool execution system. Categorizes commands into READ/MODIFY/DESTRUCTIVE tiers. This module handles classification and user interaction only.
    - classify_command(command)
        - Classifies a PowerShell command text by scanning against destructive, modify, or read patterns to assign a risk tier (READ/MODIFY/DESTRUCTIVE).

    - classify_operation(tool_name, arguments)
        - Classifies a tool call's risk level without trusting model-supplied labels. If execute_powershell, analyzes the command; if in READ_ONLY_TOOLS, returns READ; otherwise defaults to DESTRUCTIVE for safety.

    - confirmation_details(tool_name, arguments, tier)
        - Builds a detailed permission request message showing proposed action, actual operation, concrete impact, and risk tier.

    - request_confirmation(details)
        - Interactive function that prints permission details and waits for user input (y/N). Returns True if approved, False otherwise.

    - execute_tool(tool_name, arguments, registry)
        - Pure executor: calls the tool from registry with arguments. Permission verification happens in loop.py's PermissionManager class.

## 📄annotations.py
- agent/annotations.py
- Unified result annotation system. Handles failure recovery guidance and state-change verification for tool execution results.
    - is_execution_failure(tool_name, result)
        - Returns True if execute_powershell failed (non-zero return code or timeout).

    - needs_verification(tool_name, arguments)
        - Returns True if tool call is riskier than READ tier (state-changing operations).

    - annotate_result(result, annotation_type, attempt_count=None)
        - Unified annotation function: adds recovery notes for failures or verification reminders for state-changing operations to result object.

## 📄prompts.py
- agent/prompts.py
- Module-level docstring and constant string defining the complete personality, communication style, tool usage rules, response length guidelines, authority/scope rules, system/tool rules (17 detailed rule sets), formatting instructions, search-result interpretation guidelines, fetch sources for detailed info, location handling, command failure recovery steps, verify-before-success protocol, follow user's scope directive, natural conversation behavior, and don't over-explain instructions for how the N.O.V.A. agent should behave and interact with users.

## 📄tool_registry.py
- agent/tool_registry.py
- collects all native NOVA tools from various modules into a single TOOL_REGISTRY dictionary, mapping each tool's string name to its actual function reference for the agent to call them.

## api/
## 📄server.py
- api/server.py
- FastAPI server for N.O.V.A. AI agent (localhost:8000). Exposes /health, /chat (streaming), and /permission endpoints. Maintains per-session message history and date-aware system prompts in CONVERSATIONS dict.
    - health()
        - Returns {"api": "ok", "ollama_reachable": bool}
        - Checks if Ollama service at localhost:11434 is reachable with HTTP GET
        - Returns True if Ollama responds within API_HEALTH_TIMEOUT

    - chat_endpoint(req: ChatRequest)
        - Accepts: message (str), conversation_id (str | None)
        - If conversation_id doesn't exist, initializes new session with date-timestamped system prompt
        - Runs run_turn_events() generator to stream AI responses as JSON lines (application/x-ndjson)
        - Yields conversation_id, then message events including tool lifecycle and answer

    - permission_endpoint(req: PermissionRequest)
        - Accepts: conversation_id (str), approved (bool)
        - Calls resolve_permission() to handle approval/denial of pending permission request
        - Returns {"ok": True, "approved": bool} or {"ok": False, "error": "..."}

## app/
## 📄marked.umd.js
- app/renderer/vendor/marked.umd.js
- Module for MarkedJS. Used to parse markdown formatting.

## 📄xterm-addon-fit.js
- app/renderer/vendor/xterm-addon-fit.js
- Addon for xterm. Used to run terminal in my app.

## 📄xterm.css
- app/renderer/vendor/xterm.css
- Style for xterm

## 📄xterm.js
- app/renderer/vendor/xterm.js
- Module for xterm. Used to run terminal in my app.

## 📄index.html
- app/renderer/index.html
- It's an HTML-only entry point (no embedded JS functions). Provides static markup for:
    - Header bar with NOVA title and status hint
    - Sidebar navigation (Chat, Terminal 1, Terminal 2, Settings buttons)
    - Three views: chat log, terminal containers, settings placeholder
    - Chat composer form with text input and send button

    Loads external resources:
    - style.css, xterm.css for styling
    - xterm.js addons for terminal rendering
    - marked.umd.js for markdown parsing
    - renderer.js (main JS logic)

## 📄renderer.js
- app/renderer/renderer.js
- Handles chat interface, tabs, terminal instantiation, and API health polling via window.nova IPC

    - switchView(viewName: string)
        - Switches active sidebar tab; toggles hidden state on views and highlights corresponding button

    - scrollToBottom()
        - Scrolls log container to bottom after content is appended

    - resizeInput()
        - Auto-resizes textarea input height based on scrollHeight (max 160px)

    - clearEmptyState()
        - Removes the initial "Nothing asked yet" placeholder div from chat view

    - addUserBubble(text: string)
        - Appends user message as a DOM bubble to the chat log; clears previous empty state first

    - addAnswerBubble(text: string)
        - Appends AI response bubble with markdown parsed via marked.parse() to chat log

    - addErrorLine(message: string)
        - Appends error text to chat log as red error-line element

    - addToolStarted(name: string, args: object, tier?: string, display?: string)
        - Creates and appends a running tool-line status indicator to show active tool execution

    - addToolFinished(name: string, result: object, tier?: string)
        - Updates or adds a completed tool-line indicator; removes from runningTools map

    - addPermissionRequest(evt: object)
        - Builds permission request UI with Approve/Decline buttons and event details list

    - evtDisplayForTool(name: string, args: object): string
        - Returns display name for tools (from args.display or empty string)

    - handleEvent(evt: object)
        - Dispatches incoming API events to handlers: conversation_id sets ID, tool_started/finished updates status, answer shows response, permission_requested calls addPermissionRequest, error shows error

    - pollHealth()
        - Fetches API health status via window.nova.health(); updates connection indicator and status hint text

    - createTerminal(id: string, container: HTMLElement)
        - Initializes xterm.js terminal in given container; sets theme, loads FitAddon, wires stdin to window.nova.terminalInput

    - focusTerminal(id: string)
        - Focuses the specified terminal by ID using entry.terminal.focus()

    - newConvoButtonHandler() [anonymous]
        - Resets chat log, creates empty-state placeholder for fresh conversation

## 📄style.css
- app/renderer/style.css
- Style for index.html

## 📄api-client.js
- app/api-client.js
- Thin Electron main process client for NOVA API. Exposes newline-delimited JSON stream parsing for chat events via fetch()
    - checkHealth(baseUrl: string)
        - Returns API health object {ok, ollama_reachable}
        - Throws ApiError if HTTP status is non-ok or fetch fails

    - streamChat(baseUrl: string, message: string, conversationId?: string, onEvent: (event) => void)
        - POSTs to /chat endpoint, reads response body as lines
        - Splits buffer by newline, parses JSON events line-by-line, calls onEvent for each
        - Emits tool_started, tool_finished, answer, error events; rejects on network failure
        - Trailing partial line at stream end is also emitted before closing

    - respondToPermission(baseUrl: string, conversationId: string, approved: boolean)
        - POSTs /permission with {conversation_id, approved} payload
        - Returns permission resolution result JSON object
        - Throws ApiError on network failure or non-ok status

    - emitLine(line: string, onEvent: (event) => void)
        - Parses trimmed line as JSON, calls onEvent with resulting event object
        - Catches parse errors and emits synthetic error event instead of aborting stream

## 📄main.js
- app/main.js
- Electron main process for N.O.V.A. desktop app. Creates tray-resident window, manages terminals via node-pty, handles IPC between renderer and API client
    - createWindow()
        - Creates BrowserWindow with frameless transparent UI at center-top screen (640x460)
        - Loads renderer/index.html; wires blur/closed events to hide rather than destroy window

    - showWindow()
        - Shows mainWindow and focuses input via "nova:focus-input" IPC

    - hideWindow()
        - Hides mainWindow without destroying it

    - toggleWindow()
        - Toggles visibility: hides if shown, shows if hidden

    - createTray()
        - Creates tray with icon from assets/tray-icon.png; builds menu for show/quit actions

    - registerShortcut()
        - Registers global shortcut via settings.globalShortcut to call toggleWindow(); unregisters any existing shortcuts first

    - app.on("second-instance", handler) [anonymous]
        - Called when another instance starts; shows current window instead of creating duplicate

    - getVenvPath(): string
        - Returns venv activation script path: "../venv/Scripts/Activate.ps1" relative to app dir

    - startTerminal(id: string): {ok, alreadyRunning}
        - Spawns PowerShell via node-pty in C:\DEV\nova with optional venv activation
        - Returns {ok, alreadyRunning: true} if terminal already exists for that ID
        - Sends "nova:terminal-data" on output and "nova:terminal-exit" on process exit

    - writeTerminal(id: string, data: string): {ok, error?}
        - Writes text data to running terminal; returns error if terminal not found/running

    - resizeTerminal(id: string, cols: number, rows: number)
        - Resizes terminal by cols/rows; silently ignores if invalid dimensions or no terminal

    - killTerminal(id: string)
        - Kills specified terminal process and removes from terminals map

    - killAllTerminals()
        - Iterates all tracked terminals, kills each one, then clears the map

    - ipcMain.handle("nova:get-settings"): (event) => settings
        - IPC responder returning current loaded settings object

    - ipcMain.handle("nova:save-settings"): (_event, partial) => newSettings
        - Merges partial settings into full set; re-registers global shortcut; returns updated settings

    - ipcMain.handle("nova:health"): async () => {ok, result|error}
        - Calls checkHealth(settings.apiBaseUrl); returns {ok:true,result} or {ok:false,error}

    - ipcMain.handle("nova:permission"): async (event, {conversationId, approved}) => response
        - Calls respondToPermission via settings.apiBaseUrl; wraps API errors in IPC-safe response object

    - ipcMain.on("nova:send", handler) [anonymous]
        - Streams chat to API via streamChat; forwards "nova:event" messages per requestId
        - Tracks currentConversationId on "conversation_id" event; sends stream-end on completion/error

    - ipcMain.on("nova:new-conversation", () => null)
        - Clears currentConversationId to allow new session initialization

    - ipcMain.handle("nova:terminal-start"): (_event, id) => {ok, result}
        - Wraps startTerminal() call for IPC; returns terminal spawn success/fail status

    - ipcMain.on("nova:terminal-input", handler) [anonymous]
        - Forwards typed terminal input to writeTerminal(id, data); sends output to renderer

    - ipcMain.on("nova:terminal-resize", (_event, {id, cols, rows}) => void)
        - Calls resizeTerminal(); no return value needed

    - ipcMain.on("nova:terminal-kill", (_event, id) => void)
        - Invokes killTerminal(id); silences errors if process already terminated

## 📄package.json
- app/package.json
- List of required packages

## 📄preload.js
- app/preload.js
- Electron context bridge exposing safe renderer-side API for N.O.V.A. UI. Uses contextBridge.exposeInMainWorld("nova") to expose IPC channel wrappers to renderer sandbox
    - send(message: string, requestId: string)
        - Sends chat message via ipcRenderer.send("nova:send") with message and request ID for tracking stream  

    - newConversation()
        - Sends "nova:new-conversation" IPC; clears current conversation on API side

    - hide(): void
        - Sends "nova:hide" IPC to hide main window

    - onEvent(callback: (payload) => void)
        - Registers listener for "nova:event"; calls callback with stream events (tool_started, tool_finished, answer, error, conversation_id)

    - onStreamEnd(callback: (payload) => void)
        - Registers listener for "nova:stream-end"; called when API stream closes successfully

    - onFocusInput(callback: () => void)
        - Registers listener for "nova:focus-input"; called when user focuses chat input

    - health(): Promise
        - Invokes "nova:health" IPC; returns {ok, api, ollama_reachable} or {ok, error}

    - respondToPermission(conversationId: string, approved: boolean): Promise
        - Invokes "nova:permission" with {conversationId, approved}; resolves permission response JSON

    - getSettings(): Promise
        - Invokes "nova:get-settings"; returns current settings object

    - saveSettings(partial: Object): Promise
        - Invokes "nova:save-settings" with partial update; merges and returns full settings

    - terminalStart(id: string): Promise<{ok, result}>
        - Invokes "nova:terminal-start"; starts PTY process in specified terminal ID

    - terminalInput(id: string, data: string): void
        - Sends typed input to running terminal via "nova:terminal-input" IPC

    - terminalResize(id: string, cols: number, rows: number): void
        - Sends resize command to terminal via "nova:terminal-resize"; triggers FitAddon fit

    - terminalKill(id: string): void
        - Sends kill signal to terminal process via "nova:terminal-kill" IPC

    - onTerminalData(callback: (payload) => void)
        - Registers listener for "nova:terminal-data"; calls callback with {id, data} chunks from terminal output

    - onTerminalExit(callback: (payload) => void)
        - Registers listener for "nova:terminal-exit"; called when process exits with {id, exitCode, signal}

## 📄settings.js
- app/settings.js
- Minimal client-side settings manager for N.O.V.A. shell. Provides defaults, loads JSON config from userData/settings.json, saves merged settings; intentionally small for shortcut/API endpoint only
    - DEFAULTS: object (exported constant)
        - Default config values: apiBaseUrl="http://127.0.0.1:8000", globalShortcut="Alt+Space", launchAtLogin=false, reduceMotion=false

    - settingsPath(): string
        - Returns path to settings.json in app userData directory via app.getPath("userData")

    - loadSettings(): object
        - Reads and parses settings.json; returns merged { ...DEFAULTS, ...parsed } if file exists
        - Falls back to DEFAULTS on missing/invalid file without crashing

    - saveSettings(settings: object): object
        - Merges incoming settings with DEFAULTS (defaults always win for unset keys)
        - Ensures directory exists with mkdirSync({recursive:true})
        - Writes JSON with indentation; returns merged config

## tools/
## 📄__init__.py
- tools/__init__.py
- Initialization

## 📄filesystem.py
- tools/filesystem.py
- Provides file search, folder size analysis, temp/cache detection, and lock status checks for N.O.V.A. agent
    - search_files(pattern: str, root_path=None): dict
        - Searches files matching wildcards in default roots (UserProfile, Program Files) or user-specified path
        - Returns {pattern, roots_searched, matches[[]], count, truncated_by_time/count}
        - Uses PowerShell Get-ChildItem -Recurse with timeout budget and MAX_RESULTS cap

    - _default_roots(): list
        - Private helper returning default search roots: USERPROFILE, C:\Program Files, C:\Program Files (x86)

    - _search_one_root(root, pattern, timeout): [list], bool
        - Private helper running PowerShell on single root; returns matches or hit_time_limit flag
        - Expects timeout budget remaining to prevent cascading delays across multiple roots

    - get_folder_size(path: str): dict
        - Returns recursive total size + top 10 immediate items breakdown for folder at path
        - Returns {path, total_size_gb, largest_items[[]], largest_items_truncated_by_time}
        - Times out if calculation exceeds budget; reports error for non-existent paths

    - _get_total_size(path, timeout): int
        - Private helper summing file Length via PowerShell Measure-Object across all recurse files

    - _get_largest_items(path, timeout): dict
        - Private helper returning top 10 largest immediate entries (files/folders) recursively calculated
        - Returns {items[[]], truncated_by_time}; items list contains {path, type, size_gb}

    - analyze_file_relevance(path: str): dict
        - Reports signals for unused file assessment at given path
        - Returns {path, days_since_accessed, days_since_modified, in_temp_or_cache_path, appears_locked_by_another_process, size_mb}
        - Checks if path is in temp/cache patterns; tests lock status by attempting exclusive open

    - _check_if_locked(path: str): bool|str
        - Private helper testing file lockability via "r+b" open attempt
        - Returns True (locked), False (free), or "n/a (folder)" for directories/unknown errors

## 📄powershell.py
- tools/powershell.py
- Thin wrapper around PowerShell subprocess execution via Python's subprocess.run. Exposes single public function to run arbitrary PowerShell commands with timeout clamping and error capture.
    - execute_powershell(command: str, timeout=DEFAULT_TIMEOUT): dict
        - Runs wrapped command with "$ErrorActionPreference = 'Stop'" prefix in NoProfile/NonInteractive mode
        - Clamps timeout between 1 and POWERSHELL_MAX_TIMEOUT seconds
        - Returns {"command", stdout, stderr, returncode, timed_out}
        - On TimeoutExpired: sets timed_out=True, captures partial stdout/stderr if available
        - On FileNotFoundError/OSError: sets stderr with "Could not start PowerShell" message
        - All subprocess output is captured as text; exit code mapped to returncode field

## 📄processes.py
- tools/processes.py
- Process/network enumeration tool using psutil library. Exposes two public functions: list running processes and active network connections
    - list_running_processes(limit=30, sort_by="memory"): dict
        - Returns {processes[[]], shown, total_running, truncated} for system process enumeration
        - Collects pid, name, memory_mb (RSS/MB), exe_path from psutil.process_iter()
        - Skips NoSuchProcess/AccessDenied errors gracefully
        - Sorts by "memory" (default, highest first) or "name" (alphabetical)
        - Caps results at limit; sets truncated=True if total > limit

    - get_network_connections(limit=30): dict
        - Returns {connections[[]], shown, total_connections, truncated} for active network sockets
        - Calls psutil.net_connections(kind="inet"); catches AccessDenied requiring Administrator
        - Builds per-conn: pid, process_name, status, local_address, remote_address
        - Prioritizes ESTABLISHED connections before LISTENING in sort order
        - Caps at 40 total (even if limit < 30) to avoid overwhelming truncation; reports truncated state

## 📄registry.py
- tools/registry.py
- Windows Registry reader tool using winreg module with read limits. Exposes single public function to query registry keys within allowed hives plus one app listing helper

    - query_registry(key_path: str): dict
        - Reads Windows registry key values and subkey names for given hive-suffixed path
        - Validates key_path starts with HKLM, HKCU, HKCR, or HKU; rejects others
        - Returns {key_path, values[[]], values_truncated, subkeys[[]], subkeys_truncated}
        - Caps reads at REGISTRY_MAX_VALUES for values and REGISTRY_MAX_SUBKEYS for subkeys
        - Catches FileNotFoundError (key not found), PermissionError, OSError; reports error in dict
        - Value names with missing data show as "(default)" or "unknown"

    - list_installed_apps(): dict
        - Scans HKLM/HKU uninstall registry paths for installed application entries
        - Collects DisplayName, DisplayVersion, Publisher, InstallDate from each app subkey
        - Deduplicates apps appearing in multiple uninstall locations; sorts by name
        - Returns {apps[[]], count, errors[[]]} on access denials to specific paths
        - _read_app_entry helper extracts single app entry dict; returns None if DisplayName missing

    - _get_value(key, name): str|None
        - Private helper querying registry value by name; returns raw value or None if not found
        - Uses winreg.QueryValueEx with FileNotFoundError catch

    - _read_values(key): dict
        - Private helper enumerating registry values up to MAX_VALUES limit
        - Returns {items[[]], truncated}; items list contains {name, value} dicts

    - _read_subkeys(key): dict
        - Private helper enumerating subkey names under registry key up to MAX_SUBKEYS limit
        - Returns {items[[]], truncated}; items list is simple subkey name strings

## 📄system.py
- tools/system.py
- System diagnostics tool for CPU, RAM, disk, GPU, OS info via psutil + PowerShell WMI
    - get_system_diagnostics()
        - Returns {cpu, ram, disks, os} system state snapshot
            - cpu: {usage_percent, core_count_physical, core_count_logical} from psutil.cpu_*
            - ram: {total_gb, used_gb, percent_used} from psutil.virtual_memory()
            - disks: list of mount points with total/used/free GB and percent_used via psutil.disk_usage()
            - os: {name, version, build, uptime} from WMI Win32_OperatingSystem JSON

    - _get_cpu_info()
        - Private helper returning {usage_percent, core_count_physical, core_count_logical}
        - usage_percent via psutil.cpu_percent(interval=0.5)
        - Physical cores via psutil.cpu_count(logical=False)
        - Logical cores via psutil.cpu_count(logical=True)

    - _get_ram_info()
        - Private helper returning {total_gb, used_gb, percent_used}
        - Converts memory info bytes to GB rounded to 2 decimals

    - _get_disk_info()
        - Private helper iterating psutil.disk_partitions(all=False) for mounted volumes
        - Returns list of {drive, total_gb, used_gb, free_gb, percent_used} dicts
        - Skips PermissionError on read-only partitions

    - _get_os_info()
        - Private helper running PowerShell WMI to fetch OS Caption, Version, BuildNumber, LastBootUpTime
        - Converts .NET JSON date format for uptime calculation via timedelta from boot_time
        - Returns {name, version, build, uptime} or error dict on timeout/JSON parse failure

    - get_gpu_driver_info()
        - Returns {gpus[[]]} listing all video controllers with driver info
            - First calls _get_gpu_info_wmi() for WMI data (Name, DriverVersion, DriverDate, AdapterRAM)
            - Then calls _try_nvidia_smi() if NVIDIA GPUs detected to override VRAM and get accurate driver version
        - Each GPU dict has: name, driver_version, driver_date, vram_gb

    - _get_gpu_info_wmi()
        - Private helper running PowerShell WMI Win32_VideoController enumeration
        - Returns [{name, driver_version, driver_date, vram_gb}] or error list
        - Handles single GPU (dict response) by converting to list format

    - _try_nvidia_smi()
        - Private helper attempting nvidia-smi command for accurate NVIDIA data
        - Returns {driver_version, vram_gb} dict on success, None if nvidia-smi missing/failed
        - First overload version fetches only driver_version; second (shown last) version also queries memory.total

## 📄tool_schemas.py
- tools/tool_schemas.py
- Tool schema registry for N.O.V.A. agent's LLM tool calling. Contains single global constant TOOL_SCHEMAS: list of function schema definitions for available tools. No executable Python functions exist; this is metadata for agent to know which tools it can call
    - TOOL_SCHEMAS (exported list)
        - Static list of 18 tool schema dicts, each defining name, description, and parameters
        - Schema entries include: get_system_diagnostics, list_running_processes, get_network_connections, get_gpu_driver_info
            - get_disk_health, query_registry, list_installed_apps
            - search_files, get_folder_size, analyze_file_relevance
            - web_search, fetch_page
            - get_approximate_location, execute_powershell
        - Each schema has: type="function", function:{name, description, parameters}
        - No runtime logic; purely declarative JSON-like Python dicts for tool registry

## 📄websearch.py
- tools/websearch.py
- Web search + page fetching tool for N.O.V.A. agent using DDG/Bing/Google backends. Implements DuckDuckGo fallback to Ollama API escalation; fetches HTML pages and geolocates IP
    - web_search(query: str): dict
        - Searches web via DuckDuckGo/Bing/Google in order; escalates to Ollama if needed
        - Returns {query, backend_used, tier, escalated, results[[]], error?, warning?}
        - Validates result sufficiency (>=3 unique URLs, 80+char snippets); warns if limited
        - On all backend failures: returns error with last failure message

    - fetch_page(url: str, max_chars=8000): dict
        - Fetches HTML content via requests.get(); strips script/style/nav/footer elements
        - Returns {url, content, truncated} where content is trimmed to 20000 hard ceiling
        - On HTTP failure/parse error: returns {url, error} message

    - get_approximate_location(): dict
        - Fetches city/region/country via ip-api.com JSON endpoint
        - Returns {location: "city, region, country", source: "ip_geolocation"}
        - Falls back to DEFAULT_LOCATION on network failure or bad response

## /
## 📄main.py
- ./main.py
- Console CLI entry point for N.O.V.A. agent inspection assistant. Runs interactive REPL loop calling run_turn() from agent.loop with date-timestamped system prompt
    - main(show_debug_tools=False, show_full_output=False): None
        - Interactive chat loop reading stdin; prints "exit"/"quit" to stop
        - Initializes messages list with SYSTEM_PROMPT + today's date/time string
        - Calls agent.loop.run_turn() for each non-empty user input line
            - On answer: prints streamed output (tool events, AI responses)
            - On empty answer: prints blank line
        - Catches EOFError/KeyboardInterrupt on Ctrl-C or pipe closure
        - CLI args "--debug-tools" passes True to run_turn; "--full-output" enables full tool dumps

## 📄NOVA_project_plan.md
- ./NOVA_project_plan.md
- Plan

## 📄pytest.ini
- ./pytest.ini
- Configuration files for pytest

## 📄README.md
- ./README.md
- Front page for github repo

## 📄requirements.txt
- ./requirements.txt
- python module requirements. Can be ran with 'pip install requirements.txt'

## 📄settings.json
- ./settings.json
- N.O.V.A. agent configuration file
- JSON config for Ollama LLM client settings, timeouts, limits, and runtime behavior parameters
- Loaded by agent loop to tune model context window, predictions, iteration counts, tool call budgets


## 📄settings.py
- ./settings.py
- Settings loader/validation module exporting runtime config as Python constants
- Loads JSON config from settings.json, validates types/ranges against INTEGER_RANGES and DEFAULTS, merges missing keys with defaults, exports constants for all tools
    - _load_settings(): dict [private]
        - Reads settings.json; catches OSError/JSONDecodeError returning empty dict
        - Validates each config key: requires int in INTEGER_RANGES or string for ollama_url/model
        - Ignores out-of-range values, bool masquerading as ints, missing keys
        - Enforces powershell_max_timeout >= powershell_timeout after merge