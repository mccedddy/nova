from agent.client import chat_stream, extract_tool_calls, get_final_text, OllamaUnavailableError
from agent.validation import validate_tool_call
from tools.system import get_system_diagnostics, get_gpu_driver_info, get_disk_health
from tools.processes import list_running_processes, get_network_connections
from tools.registry import query_registry, list_installed_apps
from tools.filesystem import search_files, get_folder_size, analyze_file_relevance
from tools.websearch import web_search, fetch_page, get_approximate_location

SYSTEM_PROMPT = """You are N.O.V.A. (Native Operating-system Virtual Assistant), a local AI agent that inspects this Windows system using the tools available to you.

Rules:
1. Read-only: you cannot delete, move, modify, uninstall, or change anything. Never tell the user something "is safe to delete" or recommend deleting/removing/uninstalling anything -- that judgment belongs to the user. You may describe signals neutrally (e.g. "unused for 90 days, in a temp folder") without concluding what to do about them.
2. Stay grounded: only state facts that appear in a tool result or something the user said in this conversation. Never invent version numbers, dates, file paths, other tools/integrations, or reasons why something is running. If speculating, mark it clearly as a guess ("possibly," "this could be").
3. Real values only: never answer with a placeholder like [username] or <YourUsername>. Use a tool to get the real value first.
4. Ambiguous requests: ask a clarifying question rather than guessing, especially before anything that sounds destructive.
5. No reliable answer: if a question isn't something your tools can determine (e.g. whether software is pirated), say so after 1-2 attempts rather than continuing to guess search patterns.
6. web_search: use it when you don't recognize something, or to check current info (e.g. latest version of something). Don't claim it or any other tool is "unavailable" unless you actually tried it and it failed. For "is X outdated" questions, always chain: check the local version first, then web_search for the latest, then compare -- don't stop after only the local check.
7. Don't over-search: after 2-3 searches on the same question, give your best answer with the uncertainty noted, rather than continuing to reformulate the query.
8. When calling a tool, include one short sentence in your response describing what you're checking. Don't show internal reasoning.
9. Keep answers direct. Use tables/bullets only when they genuinely help, not for single-fact answers. Avoid excessive emoji.
10. When summarizing from search results, distinguish between what a source directly states and any analysis/speculation in that source. Don't present a journalist's interpretation as a confirmed fact. If details are inconsistent or incomplete across snippets, say what's uncertain rather than filling gaps with your own inference.
11. If web_search snippets aren't detailed enough to answer confidently (e.g. comparing exact version numbers, or the user wants specifics beyond a summary), use fetch_page on the most relevant result URL to get real content instead of guessing from a fragment.
12. If a question needs location context (e.g. weather) and none was given, use get_approximate_location first, then web_search with that location."""

MAX_ITERATIONS = 10
MAX_RETRIES = 2


def add(a, b):
    return a + b


TOOL_REGISTRY = {
    "add": add,
    "get_system_diagnostics": get_system_diagnostics,
    "list_running_processes": list_running_processes,
    "get_network_connections": get_network_connections,
    "get_gpu_driver_info": get_gpu_driver_info,
    "get_disk_health": get_disk_health,
    "query_registry": query_registry,
    "list_installed_apps": list_installed_apps,
    "search_files": search_files,
    "get_folder_size": get_folder_size,
    "analyze_file_relevance": analyze_file_relevance,
    "web_search": web_search,
    "fetch_page": fetch_page,
    "get_approximate_location": get_approximate_location,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "Add two numbers together",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_diagnostics",
            "description": (
                "Get current system diagnostics: CPU usage and core count, "
                "RAM total/used/percent, per-drive disk space, and OS "
                "name/version/build/uptime. No arguments needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_running_processes",
            "description": (
                "List currently running processes with PID, name, memory "
                "usage in MB, and executable path. Results are sorted and "
                "capped by default since the system may have 200+ processes "
                "running. Use this to answer questions about what's running, "
                "what's using memory, or to look up a process by name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of processes to return (default 30)",
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort order: 'memory' (default, highest first) or 'name' (alphabetical)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_connections",
            "description": (
                "List active network connections: which process owns each "
                "one, local/remote address and port, and connection status. "
                "Established connections are shown first. Use this to answer "
                "questions about what's using the network, what's connected "
                "to what, or open ports. May report an access-denied error "
                "if not running as Administrator."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of connections to return (default 30)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gpu_driver_info",
            "description": (
                "Get GPU model, driver version, driver date, and VRAM for "
                "each graphics card in the system. Use this to answer "
                "questions about GPU driver version or whether a driver "
                "update may be needed (pair with web_search to check the "
                "latest available version once that tool exists)."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_health",
            "description": (
                "Get SMART health status for each physical disk: health status "
                "(Healthy/Warning/Unhealthy), operational status, media type "
                "(SSD/HDD), and size. May require running as Administrator."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_registry",
            "description": (
                "Read a Windows registry key: its values and subkey names. "
                "key_path must start with one of HKLM, HKCU, HKCR, or HKU, "
                "e.g. 'HKLM\\Software\\Microsoft\\Windows\\CurrentVersion'. "
                "Results are capped -- if truncated, narrow the path further "
                "rather than reading a huge key like the hive root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key_path": {
                        "type": "string",
                        "description": "Full registry path including root hive, e.g. 'HKLM\\Software\\Microsoft'",
                    },
                },
                "required": ["key_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_installed_apps",
            "description": (
                "List installed applications with name, version, publisher, "
                "and install date. Reads both 64-bit and 32-bit installed "
                "programs, and both machine-wide and per-user installs. "
                "Read-only -- does not uninstall or modify anything."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "Search for files by name pattern using simple wildcards only "
                "(* and ? -- no brace expansion like {a,b}, no regex). Examples: "
                "'*.log', 'report*.docx'. root_path must be a real, concrete "
                "directory path (e.g. 'C:\\\\Users\\\\yourname\\\\Downloads') -- "
                "wildcards and placeholders like [username] are NOT supported in "
                "root_path, only in pattern. If root_path is omitted, searches "
                "common locations (user profile, Program Files) rather than the "
                "whole C: drive. Results are capped and time-limited -- check "
                "truncated_by_time/truncated_by_count in the response."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Filename pattern to match, e.g. '*.pdf' or 'invoice*.xlsx'",
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Optional starting directory. Omit to search default common locations.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_folder_size",
            "description": (
                "Get the total size of a folder (recursive) plus a breakdown "
                "of its 10 largest immediate subfolders/files by size. Use "
                "this to find what's taking up space inside a specific "
                "directory. Requires a real, already-known path -- use "
                "search_files first if you don't know the exact path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Full path to the folder to measure, e.g. 'C:\\\\Users\\\\you\\\\Downloads'",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_file_relevance",
            "description": (
                "Get informational signals about a specific file or folder to "
                "help assess whether it looks unused: days since last accessed, "
                "days since last modified, whether it's in a typical temp/cache "
                "path, and whether it appears locked by another process. This "
                "tool does NOT determine or claim whether something is safe to "
                "delete -- it only reports raw signals for you to weigh and "
                "explain to the user, who makes the actual judgment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Full path to the file or folder to analyze",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information. Use this ONLY when "
                "you don't recognize something from your own knowledge -- an "
                "unfamiliar process name, file, error message, or to check "
                "the latest version of something like a GPU driver. Returns "
                "a handful of summarized results (title, snippet, url), not "
                "full page content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": (
                "Fetch and extract the readable text content of a specific web "
                "page by URL. Use this AFTER web_search when a search snippet "
                "isn't enough detail to answer accurately -- e.g. comparing "
                "specific version numbers, or getting full plot/technical "
                "details rather than a short preview. Don't use this as a "
                "first step; always search first to find the right URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to fetch, usually from a prior web_search result",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Max characters of page content to return (default 8000). Raise for long pages needing more detail, up to 20000.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_approximate_location",
            "description": (
                "Get an approximate city-level location for this machine, "
                "based on IP geolocation (falls back to a default if that "
                "fails). Use this when a question needs location context, "
                "like checking the weather, and no location was given. Not "
                "GPS-precise -- city/region level only."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


TOOL_PROGRESS_MESSAGES = {
    "add": "Calculating...",
    "get_system_diagnostics": "Analyzing system diagnostics...",
    "list_running_processes": "Checking running processes...",
    "get_network_connections": "Checking network connections...",
    "get_gpu_driver_info": "Analyzing GPU and driver information...",
    "get_disk_health": "Checking disk health...",
    "query_registry": "Inspecting the Windows registry...",
    "list_installed_apps": "Checking installed applications...",
    "search_files": "Searching files...",
    "get_folder_size": "Calculating folder size...",
    "analyze_file_relevance": "Analyzing file information...",
    "web_search": "Searching the web for information...",
    "fetch_page": "Checking information from web...",
    "get_approximate_location": "Checking location...",
}


def run_turn(user_input, messages, show_debug_tools=False):
    messages.append({"role": "user", "content": user_input})
    failure_counts = {}

    for _ in range(MAX_ITERATIONS):
        printed_anything = False

        def on_token(piece):
            nonlocal printed_anything
            printed_anything = True
            print(piece, end="", flush=True)

        try:
            response = chat_stream(messages, tools=TOOL_SCHEMAS, on_token=on_token)
        except OllamaUnavailableError as e:
            if printed_anything:
                print()  # close out any partial line
            messages.pop()
            return f"⚠ {e}"

        tool_calls = extract_tool_calls(response)

        if not tool_calls:
            final_text = get_final_text(response)
            if not final_text.strip():
                if printed_anything:
                    print()
                return (
                    "⚠ I gathered information but ran out of room to summarize it "
                    "(too much data from the tool results). Try asking a more "
                    "specific question, like checking one folder or location at a time."
                )
            messages.append({"role": "assistant", "content": final_text})
            print()  # newline after the streamed text
            return ""  # already printed live -- nothing left for main.py to print

        # tool call path: content, if any, was already streamed above as the
        # "thinking out loud" status line; now execute the actual tool(s)
        if printed_anything:
            print()

        messages.append(response["message"])

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            if not printed_anything:
                print(f"\n{TOOL_PROGRESS_MESSAGES.get(name, 'Working...')}")
            if show_debug_tools:
                print(f"\u2192 calling {name}({args})")

            ok, validated = validate_tool_call(name, args, TOOL_REGISTRY, TOOL_SCHEMAS)

            if ok:
                try:
                    result = TOOL_REGISTRY[name](**validated)
                except Exception as e:
                    ok = False
                    validated = str(e)

            if not ok:
                failure_counts[name] = failure_counts.get(name, 0) + 1
                if failure_counts[name] > MAX_RETRIES:
                    result = f"error: {validated} -- giving up on '{name}' after {MAX_RETRIES} retries"
                else:
                    result = f"error: {validated} -- please retry with corrected arguments"

            if show_debug_tools:
                print(f"\u2190 result: {result}")

            messages.append({
                "role": "tool",
                "content": str(result),
            })

    return "I couldn't complete that after several tool calls -- something may be wrong with my tool use."