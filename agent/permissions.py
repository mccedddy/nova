from enum import Enum
import json
import re


class RiskTier(str, Enum):
    READ = "READ"
    MODIFY = "MODIFY"
    DESTRUCTIVE = "DESTRUCTIVE/SYSTEM-LEVEL"


READ_ONLY_TOOLS = {
    "get_system_diagnostics",
    "list_running_processes",
    "get_network_connections",
    "get_gpu_driver_info",
    "get_disk_health",
    "query_registry",
    "list_installed_apps",
    "search_files",
    "get_folder_size",
    "analyze_file_relevance",
    "web_search",
    "fetch_page",
    "get_approximate_location",
}

DESTRUCTIVE_COMMAND_PATTERNS = (
    r"\bRemove-Item\b",
    r"\bRemove-Object\b",
    r"\bFormat-[A-Za-z-]+\b",
    r"\bStop-Process\b",
    r"\bStop-Computer\b",
    r"\bRestart-Computer\b",
    r"\bSet-ExecutionPolicy\b",
    r"\breg(?:\.exe)?\s+delete\b",
    r"\b(?:del|erase|rd|rmdir)\b",
    r"\bClear-[A-Za-z-]+\b",
    r"\.(?:Delete|Remove)\s*\(",
    r"\[System\.IO\.(?:File|Directory)\]::(?:Delete|Move)\b",
    r"\b(?:Set-Content|Add-Content|Out-File|Clear-Content|Export-Csv)\b",
    r"(?:^|[;&|])\s*[^\r\n]+\s*[>]{1,2}\s*[^>\s]",
)

MODIFY_COMMAND_PATTERNS = (
    r"\bMove-Item\b",
    r"\bRename-Item\b",
    r"\bCopy-Item\b",
    r"\bNew-Item\b",
    r"\bStart-Process\b",
    r"\bStart-Service\b",
    r"\bStop-Service\b",
    r"\bSet-Service\b",
    r"\b(?:move|ren|rename|mkdir|md)\b",
)

READ_COMMAND_PATTERN = re.compile(
    r"\b(?:Get-[A-Za-z-]+|Get-ChildItem|Get-Location|pwd|dir|ls|type|cat|"
    r"Test-Path|Join-Path|Write-Output|Select-Object|Where-Object|"
    r"Format-Table|Measure-Object|Sort-Object|ForEach-Object)\b",
    re.IGNORECASE,
)


class PermissionDenied(Exception):
    """Raised when an operation was not approved for execution."""


def classify_command(command):
    """Classify the actual command text, conservatively on ambiguity."""
    command = str(command or "")

    if any(re.search(pattern, command, re.IGNORECASE) for pattern in DESTRUCTIVE_COMMAND_PATTERNS):
        return RiskTier.DESTRUCTIVE
    if any(re.search(pattern, command, re.IGNORECASE) for pattern in MODIFY_COMMAND_PATTERNS):
        return RiskTier.MODIFY
    if READ_COMMAND_PATTERN.search(command):
        return RiskTier.READ
    return RiskTier.MODIFY


def classify_operation(tool_name, arguments):
    """Classify a tool call without trusting model-supplied risk labels."""
    if tool_name == "execute_powershell":
        return classify_command(arguments.get("command", ""))
    if tool_name in READ_ONLY_TOOLS:
        return RiskTier.READ
    return RiskTier.DESTRUCTIVE


def confirmation_details(tool_name, arguments, tier):
    operation = arguments.get("command") if isinstance(arguments, dict) else None
    if not operation:
        operation = f"{tool_name}({json.dumps(arguments, sort_keys=True)})"

    if isinstance(arguments, dict):
        target = arguments.get("path") or arguments.get("root_path") or arguments.get("command")
    else:
        target = None
    impact = (
        f"This may change system state at {target}."
        if target
        else "This may change system state; review the operation and its arguments before approving."
    )

    return (
        f"Action proposed: execute {tool_name}.\n"
        f"Actual operation: {operation}\n"
        f"Concrete impact: {impact}\n"
        f"Risk tier: {tier.value}"
    )


def request_confirmation(details):
    print(f"\n{details}")
    answer = input("Approve this action? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def execute_tool(tool_name, arguments, registry, confirmation_callback=None):
    tier = classify_operation(tool_name, arguments)
    if tier is not RiskTier.READ:
        details = confirmation_details(tool_name, arguments, tier)
        if confirmation_callback is None:
            raise PermissionDenied(f"confirmation required before execution:\n{details}")
        if not confirmation_callback(details):
            raise PermissionDenied(f"user declined this action:\n{details}")

    return registry[tool_name](**arguments)
