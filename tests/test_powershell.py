import subprocess
from unittest.mock import patch

from tools.powershell import execute_powershell


def test_powershell_returns_structured_success():
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="hello\n", stderr=""
    )

    with patch("tools.powershell.subprocess.run", return_value=completed) as run:
        result = execute_powershell("Get-Date", timeout=999)

    run.assert_called_once_with(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference = 'Stop'\nGet-Date",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result == {
        "command": "Get-Date",
        "stdout": "hello\n",
        "stderr": "",
        "returncode": 0,
        "timed_out": False,
    }


def test_powershell_preserves_failure_details():
    completed = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="bad command\n"
    )

    with patch("tools.powershell.subprocess.run", return_value=completed):
        result = execute_powershell("Not-A-Real-Command")

    assert result["returncode"] == 1
    assert result["stderr"] == "bad command\n"
    assert result["timed_out"] is False


def test_powershell_timeout_is_structured():
    error = subprocess.TimeoutExpired("powershell", 20, output="partial", stderr="still running")

    with patch("tools.powershell.subprocess.run", side_effect=error):
        result = execute_powershell("Get-Date")

    assert result["returncode"] is None
    assert result["stdout"] == "partial"
    assert "timed out" in result["stderr"]
    assert result["timed_out"] is True
