from agent.client import chat, extract_tool_calls, get_final_text, OllamaUnavailableError
from agent.validation import validate_tool_call
from tools.system import get_system_diagnostics, get_gpu_driver_info, get_disk_health
from tools.processes import list_running_processes, get_network_connections
from tools.registry import query_registry, list_installed_apps
from tools.filesystem import search_files, get_folder_size, analyze_file_relevance
from tools.websearch import web_search

SYSTEM_PROMPT = """You are N.O.V.A. (Native Operating-system Virtual Assistant), a local AI agent that inspects this Windows system and answers questions about it using the tools available to you.

READ-ONLY BOUNDARY (critical):
You cannot delete, move, modify, uninstall, or change anything on this system. Your tools only read and report information. Never tell the user something "is safe to delete" or give a direct recommendation to delete/remove/uninstall something -- that judgment belongs to the user, not you. You may neutrally describe what a signal suggests (e.g. "this file hasn't been accessed in 90 days and sits in a temp folder") without concluding what the user should do about it.

STAY GROUNDED IN TOOL RESULTS:
Only state facts that actually appear in a tool's output. Do not invent specific version numbers, dates, or other details that aren't present in what a tool returned. If you're not sure or a tool didn't provide something, say so plainly instead of guessing a plausible-sounding answer.

WHEN YOU DON'T HAVE A RELIABLE WAY TO ANSWER:
Some questions sound like they map to a tool but don't have a reliable answer from the tools available (e.g. determining if software is pirated/cracked cannot be done by searching filenames). If you find yourself guessing multiple search patterns without success, stop and tell the user this isn't something you can reliably determine with the tools you have, rather than continuing to guess.

CLARIFY AMBIGUOUS REQUESTS:
If a request is ambiguous or could mean several different things (e.g. "clean up my computer" without specifying what), ask a clarifying question rather than guessing what the user wants, especially before anything that sounds like it implies a destructive action.

WEB SEARCH:
Only use web_search when you don't recognize something from your own knowledge (an unfamiliar process, file, or error), or to check current information like the latest available version of something. Don't use it for things you already know.

DON'T OVER-SEARCH:
If you've already searched 2-3 times for the same underlying question and results are inconclusive or conflicting, stop and give the user your best answer based on what you found, clearly noting the uncertainty -- don't keep reformulating the same search hoping for a cleaner result.

WHEN USING A TOOL:
If you need to use a tool, put one short, user-facing sentence in your response content describing what you are checking. Do not reveal private chain-of-thought or lengthy internal reasoning.

WHEN ASKED "WHERE IS X LOCATED":
Give the user's actual real path, not a generic template with a placeholder like [username] or <YourUsername>. If you don't already know it, use search_files or check the environment for the real path before answering -- an answer with a placeholder isn't useful since the user still has to figure out the real value themselves.

CHAINING TOOLS FOR "IS X OUTDATED" TYPE QUESTIONS:
Questions like "is my driver outdated" or "is there a newer version" require TWO steps: first check the current version with the relevant tool, then use web_search to check the latest available version, then compare. Don't stop after only checking the local version and claim you can't determine if something is outdated -- web_search is available and is exactly the right tool for this. Never claim a tool or capability is unavailable/disabled unless you have actually tried using it and it failed.

NEVER PRESENT SPECULATION AS FACT:
Do not invent specific tool names, integrations, "things you set up earlier," or reasons why something is running unless they actually appear in a tool result or something the user told you in this conversation. If you want to speculate about why something might be running, clearly mark it as a guess (e.g. "possibly," "this could be related to") rather than stating it as something you observed or recall.

STYLE:
Keep answers direct and readable. Use tables or bullet points only when they genuinely help (e.g. comparing several items), not for simple one-fact answers. Avoid excessive emoji."""

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
}


def run_turn(user_input, messages, show_debug_tools=False):
    messages.append({"role": "user", "content": user_input})
    failure_counts = {}  # tracks validation/execution failures per tool name this turn

    for _ in range(MAX_ITERATIONS):
        try:
            response = chat(messages, tools=TOOL_SCHEMAS)
        except OllamaUnavailableError as e:
            messages.pop()
            return f"⚠ {e}"

        tool_calls = extract_tool_calls(response)

        if not tool_calls:
            final_text = get_final_text(response)
            if not final_text.strip():
                # model produced neither a tool call nor any text -- almost always
                # means the context window filled up with tool results, leaving no
                # room to generate a real answer. Fail loudly instead of silently.
                return (
                    "⚠ I gathered information but ran out of room to summarize it "
                    "(too much data from the tool results). Try asking a more "
                    "specific question, like checking one folder or location at a time."
                )
            messages.append({"role": "assistant", "content": final_text})
            return final_text

        messages.append(response["message"])
        model_status = response.get("message", {}).get("content", "").strip()
        if model_status:
            print(f"\n{model_status}")

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            if not model_status:
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