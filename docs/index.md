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
- Bundled MarkedJS module used to parse and render Markdown in AI responses and permission details.

## 📄xterm-addon-fit.js
- app/renderer/vendor/xterm-addon-fit.js
- xterm.js FitAddon used to automatically fit terminal dimensions to their container.

## 📄xterm.css
- app/renderer/vendor/xterm.css
- xterm.js stylesheet used by the embedded terminal views.

## 📄xterm.js
- app/renderer/vendor/xterm.js
- Bundled xterm.js library used to render the two embedded terminal instances.

## 📄index.html
- app/renderer/index.html
- Static HTML entry point for the NOVA renderer. Provides:
    - Header bar with NOVA title, global shortcut hint, and connection status text
    - Sidebar navigation for Chat, Terminal 1, Terminal 2, and Settings
    - New conversation control
    - Chat log and empty-state content
    - Chat composer with multiline textarea and send button
    - Terminal 1 and Terminal 2 containers
    - App settings UI for API base URL, global shortcut, launch-at-login, and reduced motion
    - Dynamic Agent settings UI loaded from the NOVA API

## 📄renderer.js
- app/renderer/renderer.js
- Main renderer-side UI logic. Manages chat state, API events, permission prompts, settings, terminal instances, view switching, and API/Ollama health status through the window.nova preload bridge.
    - ConversationState
        - Tracks current conversation ID, active request ID, running tools, pending permission state, and request counter.
    
    - switchView(viewName: string)
        - Switches between Chat, Terminal 1, Terminal 2, and Settings views.
        - Updates sidebar button active state and focuses the appropriate input or terminal.
    
    - scrollToBottom()
        - Scrolls the chat log to the bottom after new content is added.
    
    - resizeInput()
        - Automatically resizes the chat textarea based on its content, up to 160px.
    
    - clearEmptyState()
        - Removes the current chat empty-state placeholder.
    
    - addUserBubble(text: string)
        - Adds a user message to the chat log.
    
    - addAnswerBubble(text: string)
        - Adds an AI response to the chat log and renders its Markdown through marked.parse().
    
    - addErrorLine(message: string)
        - Adds an error message to the chat log.
    
    - addToolStarted(name: string, args: object, tier?: string, display?: string)
        - Adds a running tool execution indicator and tracks it in the conversation state.
    
    - addToolFinished(name: string, result: object, tier?: string)
        - Marks a tracked tool execution as completed or adds a completed indicator when no running entry exists.
    
    - addPermissionRequest(evt: object)
        - Displays an Approve/Decline permission prompt using the API event details.
        - Sends the selected permission decision through window.nova.respondToPermission().
    
    - handleEvent(evt: object)
        - Handles streamed API events including conversation_id, tool_started, tool_finished, answer, permission_requested, and error.
        - Ignores events belonging to unrelated or previously completed requests.
    
    - Chat form submission
        - Sends normal messages through window.nova.send().
        - Supports Y/N text responses while a permission request is pending.
        - Prevents multiple normal requests from being submitted simultaneously.
        - Supports Enter to send and Shift+Enter for a newline.
    
    - Settings management
        - Loads app settings from the Electron main process.
        - Loads dynamic Agent settings from the NOVA API.
        - Generates Agent setting inputs from API-provided values and numeric ranges.
        - Saves App settings through window.nova.saveSettings().
        - Saves Agent settings through window.nova.saveAgentSettings() and reports rejected values or the need to restart the API server.
    
    - createTerminal(id: string, container: HTMLElement)
        - Creates an xterm.js terminal with FitAddon.
        - Configures terminal font, cursor, scrollback, and theme.
        - Automatically fits the terminal when its container is resized.
        - Sends terminal input through window.nova.terminalInput().
        - Starts the corresponding PTY through window.nova.terminalStart().
    
    - focusTerminal(id: string)
        - Focuses the specified xterm.js terminal.
    
    - Terminal event handlers
        - Writes nova:terminal-data output into the matching xterm instance.
        - Displays the PTY exit code when a terminal process exits.
    
    - pollHealth()
        - Polls the NOVA API every 15 seconds through window.nova.health().
        - Displays separate connection states for API unavailable, Ollama unavailable, and both services connected.
    
    - New conversation handler
        - Clears the current conversation ID and chat log.
        - Restores the new-conversation empty state.
    
    - Escape key handler
        - Hides the NOVA window through window.nova.hide().

## 📄style.css
- app/renderer/style.css
- Main stylesheet for the NOVA renderer UI, including the window shell, sidebar, chat interface, terminal views, settings interface, status indicators, tool states, and permission controls.

## 📄main.js
- app/main.js
- Electron main process for NOVA. Manages the application window, tray, global shortcut, settings, API communication, IPC, conversation state, and PTY terminals.
    - ApiError
        - Custom error type used for API communication failures.
    
    - checkHealth(baseUrl: string)
        - Calls the API /health endpoint and returns its JSON response.
        - Throws ApiError when the request fails or returns a non-success status.
    
    - streamChat(baseUrl: string, message: string, conversationId: string, onEvent: function)
        - POSTs messages to /chat.
        - Streams newline-delimited JSON events from the response body.
        - Parses each complete event and forwards it to the renderer callback.
        - Handles trailing stream data and malformed JSON events.
    
    - respondToPermission(baseUrl: string, conversationId: string, approved: boolean)
        - POSTs permission decisions to /permission.
        - Sends {conversation_id, approved} to the API.
    
    - getAgentSettings(baseUrl: string)
        - Fetches Agent model/tool settings from /settings.
    
    - saveAgentSettings(baseUrl: string, values: object)
        - Saves Agent settings through POST /settings.
    
    - createWindow()
        - Creates the frameless, transparent, always-on-top NOVA window.
        - Uses a default size of 640x460 with minimum dimensions of 420x320.
        - Loads renderer/index.html.
        - Hides the window when it loses focus instead of destroying it.
        - Prevents normal window closing unless the application is quitting.
    
    - showWindow()
        - Shows the main window and requests renderer input focus.
    
    - hideWindow()
        - Hides the main window without destroying it.
    
    - toggleWindow()
        - Toggles NOVA visibility.
    
    - createTray()
        - Creates the system tray icon and menu.
        - Provides Show NOVA and Quit NOVA actions.
    
    - registerShortcut()
        - Registers the configured global shortcut and maps it to toggleWindow().
    
    - Single-instance handling
        - Prevents multiple NOVA instances from running simultaneously.
        - A second launch shows the existing NOVA window instead.
    
    - API IPC handlers
        - nova:get-settings returns loaded app settings.
        - nova:save-settings saves app settings and re-registers the global shortcut.
        - nova:health checks API health.
        - nova:permission sends a permission decision to the API.
        - nova:get-agent-settings retrieves Agent settings.
        - nova:save-agent-settings saves Agent settings.
    
    - nova:send
        - Streams chat requests to the NOVA API.
        - Tracks the current conversation ID from conversation_id events.
        - Forwards streamed events to the renderer with the request ID.
        - Sends a stream-end event after completion or failure.
    
    - nova:new-conversation
        - Clears the current conversation ID.
    
    - Terminal IPC handlers
        - Starts, writes to, resizes, and kills PTY terminal instances through terminals.js.
    
    - Application lifecycle
        - Loads settings and initializes the window, tray, and global shortcut when Electron is ready.
        - Keeps NOVA running in the system tray when the window is hidden.
        - Unregisters global shortcuts and terminates all PTY terminals during application shutdown.

## 📄package.json
- app/package.json
- Defines the Electron application package metadata, scripts, and required Node.js dependencies.

## 📄preload.js
- app/preload.js
- Secure Electron preload bridge exposing the renderer-safe window.nova API through contextBridge.
    - send(message: string, requestId: string)
        - Sends a chat request to the Electron main process.
    
    - newConversation()
        - Resets the current conversation on the main process.
    
    - hide()
        - Hides the NOVA window.
    
    - onEvent(callback)
        - Receives streamed NOVA API events from the main process.
    
    - onStreamEnd(callback)
        - Receives the end-of-stream notification for a chat request.
    
    - onFocusInput(callback)
        - Receives requests to focus the chat input.
    
    - health()
        - Requests API/Ollama health information.
    
    - respondToPermission(conversationId: string, approved: boolean)
        - Sends a permission decision to the API through the main process.
    
    - getSettings()
        - Retrieves Electron app settings.
    
    - saveSettings(partial: object)
        - Saves a partial app settings update.
    
    - getAgentSettings()
        - Retrieves Agent settings from the NOVA API.
    
    - saveAgentSettings(values: object)
        - Saves Agent settings through the NOVA API.
    
    - terminalStart(id: string)
        - Starts the specified PTY terminal.
    
    - terminalInput(id: string, data: string)
        - Sends keyboard input to the specified terminal.
    
    - terminalResize(id: string, cols: number, rows: number)
        - Resizes the specified PTY terminal.
    
    - terminalKill(id: string)
        - Terminates the specified PTY terminal.
    
    - onTerminalData(callback)
        - Receives terminal output from the main process.
    
    - onTerminalExit(callback)
        - Receives terminal process exit events.

## 📄settings.js
- app/settings.js
- Local Electron settings manager. Stores NOVA client settings as JSON under Electron's userData directory.
    - DEFAULTS
        - apiBaseUrl: http://127.0.0.1:8000
        - globalShortcut: Alt+Space
        - launchAtLogin: false
        - reduceMotion: false
    - settingsPath()
        - Returns the path to settings.json inside Electron's user data directory.
    
    - loadSettings()
        - Reads and parses settings.json.
        - Merges stored values with the default settings.
        - Falls back to defaults if the file is missing or invalid.
    
    - saveSettings(settings: object)
        - Merges incoming settings with the defaults.
        - Creates the parent directory when necessary.
        - Writes the resulting configuration as formatted JSON.

## 📄terminals.js
- app/terminals.js
- PTY terminal manager used by the two embedded NOVA terminal views.
    - TERMINAL_CONFIG
        - Defines two terminal instances, both starting in C:\DEV\nova.
    
    - getVenvPath()
        - Resolves the project's venv\Scripts\Activate.ps1 activation script.
    
    - startTerminal(id: string, onData: function, onExit: function)
        - Creates a PowerShell PTY through node-pty.
        - Starts in C:\DEV\nova.
        - Configures UTF-8 output.
        - Activates the project virtual environment when the activation script exists.
        - Prevents duplicate PTY instances for the same terminal ID.
        - Forwards terminal output and process exit events through callbacks.
    
    - writeTerminal(id: string, data: string)
        - Writes input data to the specified running PTY.
    
    - resizeTerminal(id: string, cols: number, rows: number)
        - Resizes the specified PTY when valid dimensions are supplied.
    
    - killTerminal(id: string)
        - Terminates and removes a specific PTY instance.
    
    - killAllTerminals()
        - Terminates all tracked PTY instances and clears the terminal map.

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