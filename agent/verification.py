from agent.permissions import RiskTier, classify_operation


def needs_verification(tool_name, arguments):
    """True if this action changed (or could have changed) system state."""
    tier = classify_operation(tool_name, arguments)
    return tier is not RiskTier.READ


def annotate_verification_reminder(result):
    """Attach a reminder to a successful state-changing result, prompting the
    model to confirm the intended outcome before reporting success."""
    annotated = dict(result) if isinstance(result, dict) else {"result": result}
    annotated["_verification_note"] = (
        "This action changed system state and appeared to complete without error. "
        "Do not report success yet. Perform a follow-up read-only check (e.g. "
        "search_files, get_folder_size, list_running_processes, or a read-only "
        "execute_powershell command like Test-Path/Get-Item) to confirm the intended "
        "outcome actually happened before telling the user it succeeded. If the "
        "follow-up check shows the expected change did not occur, say so plainly "
        "instead of reporting success."
    )
    return annotated