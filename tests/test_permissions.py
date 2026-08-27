from agent.permissions import (
    RiskTier,
    classify_command,
    classify_operation,
    confirmation_details,
    execute_tool,
    PermissionDenied,
)


def test_read_tool_executes_without_confirmation():
    confirmation_calls = []
    registry = {"get_system_diagnostics": lambda: "diagnostics"}

    result = execute_tool(
        "get_system_diagnostics",
        {},
        registry,
        confirmation_callback=lambda details: confirmation_calls.append(details),
    )

    assert result == "diagnostics"
    assert confirmation_calls == []


def test_modify_operation_requires_and_honors_confirmation():
    confirmation_details_seen = []
    registry = {"execute_powershell": lambda command: "moved"}

    result = execute_tool(
        "execute_powershell",
        {"command": "Move-Item C:\\old.txt C:\\new.txt"},
        registry,
        confirmation_callback=lambda details: confirmation_details_seen.append(details) or True,
    )

    assert result == "moved"
    assert "Action proposed:" in confirmation_details_seen[0]
    assert "Move-Item C:\\old.txt C:\\new.txt" in confirmation_details_seen[0]
    assert "Concrete impact:" in confirmation_details_seen[0]


def test_declined_operation_never_executes():
    executed = []
    registry = {"execute_powershell": lambda command: executed.append(command)}

    try:
        execute_tool(
            "execute_powershell",
            {"command": "Remove-Item C:\\old.txt"},
            registry,
            confirmation_callback=lambda details: False,
        )
    except PermissionDenied as error:
        assert "user declined" in str(error)
    else:
        raise AssertionError("declined operation was not blocked")

    assert executed == []


def test_non_read_operation_without_callback_is_blocked():
    executed = []
    registry = {"execute_powershell": lambda command: executed.append(command)}

    try:
        execute_tool(
            "execute_powershell",
            {"command": "Start-Service Spooler"},
            registry,
        )
    except PermissionDenied as error:
        assert "confirmation required" in str(error)
    else:
        raise AssertionError("unconfirmed operation was not blocked")

    assert executed == []


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


def test_operation_classifier_is_conservative_for_unknown_tools():
    assert classify_operation("get_system_diagnostics", {}) is RiskTier.READ
    assert classify_operation("unknown_state_changing_tool", {}) is RiskTier.DESTRUCTIVE
    assert confirmation_details("unknown_state_changing_tool", {}, RiskTier.DESTRUCTIVE).startswith(
        "Action proposed:"
    )
