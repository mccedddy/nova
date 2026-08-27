MAX_COMMAND_RETRIES = 2


def is_execution_failure(tool_name, result):
    """True if a technically-successful tool call actually failed at the command level."""
    if tool_name != "execute_powershell":
        return False
    if not isinstance(result, dict):
        return False
    if result.get("timed_out"):
        return True
    returncode = result.get("returncode")
    return returncode is not None and returncode != 0


def annotate_command_failure(result, attempt_count):
    """Append recovery guidance to a failed execute_powershell result before it reaches the model."""
    annotated = dict(result)

    if attempt_count > MAX_COMMAND_RETRIES:
        annotated["_recovery_note"] = (
            f"This command has now failed {attempt_count} times in this task. Stop "
            "retrying it with execute_powershell. Explain to the user what you tried "
            "and why it didn't work, or ask a clarifying question if you're unsure of "
            "the right approach."
        )
    else:
        annotated["_recovery_note"] = (
            f"This command failed (attempt {attempt_count} of {MAX_COMMAND_RETRIES}). "
            "Analyze the specific error in stderr/returncode above before trying again. "
            "Do not repeat the identical command -- either (a) correct an obvious mistake "
            "and retry, (b) use web_search/fetch_page to look up the correct syntax or "
            "approach, or (c) try a genuinely different method to reach the same goal."
        )

    return annotated