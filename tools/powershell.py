import subprocess

from settings import POWERSHELL_MAX_TIMEOUT, POWERSHELL_TIMEOUT

DEFAULT_TIMEOUT = POWERSHELL_TIMEOUT


def execute_powershell(command, timeout=DEFAULT_TIMEOUT):
    """Run a PowerShell command and return structured process results."""
    timeout = max(1, min(int(timeout), POWERSHELL_MAX_TIMEOUT))
    result = {
        "command": command,
        "stdout": "",
        "stderr": "",
        "returncode": None,
        "timed_out": False,
    }

    try:
        wrapped_command = "$ErrorActionPreference = 'Stop'\n" + command
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", wrapped_command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        result["stderr"] = f"PowerShell command timed out after {timeout} seconds"
        result["timed_out"] = True
        if error.stdout:
            result["stdout"] = error.stdout
        if error.stderr:
            result["stderr"] += f": {error.stderr}"
        return result
    except (FileNotFoundError, OSError) as error:
        result["stderr"] = f"Could not start PowerShell: {error}"
        return result

    result.update({
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    })
    return result
