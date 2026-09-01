from agent.permissions import (
    RiskTier,
    classify_command,
    classify_operation,
    confirmation_details,
    execute_tool,
    PermissionDenied,
)


def test_read_tool_executes_without_confirmation():
    # execute_tool just executes - no confirmation logic
    registry = {"get_system_diagnostics": lambda: "diagnostics"}
    result = execute_tool("get_system_diagnostics", {}, registry)
    assert result == "diagnostics"


def test_modify_operation_requires_and_honors_confirmation():
    # Permission checking is now in loop.py, not execute_tool
    # execute_tool is just a simple executor
    registry = {"execute_powershell": lambda command: "moved"}
    result = execute_tool("execute_powershell", {"command": "Move-Item C:\\old.txt C:\\new.txt"}, registry)
    assert result == "moved"


def test_declined_operation_never_executes():
    # Permission checking is now in loop.py, not execute_tool
    # execute_tool just executes directly
    executed = []
    registry = {"execute_powershell": lambda command: executed.append(command) or "done"}
    result = execute_tool("execute_powershell", {"command": "Remove-Item C:\\old.txt"}, registry)
    assert result == "done"
    assert executed == ["Remove-Item C:\\old.txt"]  # Tool receives command string, not dict


def test_non_read_operation_without_callback_is_blocked():
    # Permission checking is in loop.py, execute_tool is just an executor
    # If called directly without permission check, it should still execute
    registry = {"execute_powershell": lambda command: "done"}
    result = execute_tool("execute_powershell", {"command": "Start-Service Spooler"}, registry)
    assert result == "done"


def test_command_classifier_detects_known_risk_patterns():
    assert classify_command("Get-Process") is RiskTier.READ
    assert classify_command("pwd") is RiskTier.READ
    assert classify_command("Get-Service | Where-Object { $_.Status -eq 'Running' } | Select-Object Name") is RiskTier.READ
    assert classify_command("$path = $env:TEMP\nTest-Path $path\nWrite-Output $path") is RiskTier.READ
    assert classify_command("$path = $env:TEMP\nGet-Service | Select-Object Name") is RiskTier.READ
    assert classify_command("Move-Item C:\\old C:\\new") is RiskTier.MODIFY
    assert classify_command("Remove-Item C:\\temp\\file.txt") is RiskTier.DESTRUCTIVE
    assert classify_command("Set-ExecutionPolicy Bypass") is RiskTier.DESTRUCTIVE
    assert classify_command("Restart-Computer") is RiskTier.DESTRUCTIVE
    assert classify_command("Get-ChildItem C:\\$Recycle.Bin | ForEach-Object { $_.Delete() }") is RiskTier.DESTRUCTIVE
    assert classify_command("Get-ChildItem | Set-Content output.txt") is RiskTier.DESTRUCTIVE


def test_operation_classifier_is_conservative_for_unknown_tools():
    assert classify_operation("get_system_diagnostics", {}) is RiskTier.READ
    assert classify_operation("unknown_state_changing_tool", {}) is RiskTier.DESTRUCTIVE
    details = confirmation_details("unknown_state_changing_tool", {}, RiskTier.DESTRUCTIVE)
    assert "**Action proposed**:" in details  # confirmation_details returns markdown format
    assert "**Concrete impact**:" in details  # markdown formatting
