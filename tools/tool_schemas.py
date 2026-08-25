TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_diagnostics",
            "description": (
                "Get current system diagnostics: CPU usage and core count, "
                "RAM total/used/percent, per-drive disk space, and OS "
                "name/version/build/uptime. No arguments needed."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
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
            "parameters": {"type": "object", "properties": {}, "required": []},
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
            "parameters": {"type": "object", "properties": {}, "required": []},
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
            "parameters": {"type": "object", "properties": {}, "required": []},
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
                    "query": {"type": "string", "description": "Search query"},
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
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
