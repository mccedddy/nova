TOOL_PROGRESS_MESSAGES = {
    "get_system_diagnostics": "Analyzing system diagnostics",
    "list_running_processes": "Checking running processes",
    "get_network_connections": "Checking network connections",
    "get_gpu_driver_info": "Analyzing GPU and driver information",
    "get_disk_health": "Checking disk health",
    "query_registry": "Inspecting the Windows registry",
    "list_installed_apps": "Checking installed applications",
    "search_files": "Searching files",
    "get_folder_size": "Calculating folder size",
    "analyze_file_relevance": "Analyzing file information",
    "web_search": "Searching the web for information",
    "fetch_page": "Checking information from web",
    "get_approximate_location": "Checking location",
}


def format_tool_description(name, arguments):
    message = TOOL_PROGRESS_MESSAGES.get(name, "Working")
    arguments = arguments or {}

    if name == "list_running_processes" and arguments.get("sort_by"):
        return f"{message} sorted by {arguments['sort_by']}"
    if name == "query_registry" and arguments.get("key_path"):
        return f"{message} at {arguments['key_path']}"
    if name == "search_files":
        pattern = arguments.get("pattern")
        root_path = arguments.get("root_path")
        if pattern and root_path:
            return f"{message} for {pattern} in {root_path}"
        if pattern:
            return f"{message} for {pattern}"
    if name == "get_folder_size" and arguments.get("path"):
        return f"{message} for {arguments['path']}"
    if name == "analyze_file_relevance" and arguments.get("path"):
        return f"{message} in {arguments['path']}"
    if name == "web_search" and arguments.get("query"):
        return f"{message} for {arguments['query']}"
    if name == "fetch_page" and arguments.get("url"):
        return f"{message} at {arguments['url']}"
    if name == "execute_powershell" and arguments.get("command"):
        timeout = arguments.get("timeout", 20)
        return (
            "Executing PowerShell command: "
            f"'{arguments['command']}' with {timeout} seconds timeout"
        )

    return message


def format_tool_progress(tool_number, name, arguments):
    return f"{tool_number}. {format_tool_description(name, arguments)}"
