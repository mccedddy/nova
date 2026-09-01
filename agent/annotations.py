from agent.permissions import RiskTier, classify_operation

MAX_COMMAND_RETRIES = 2


def is_execution_failure(tool_name, result):
    # Check if a tool call failed at execution level
    if tool_name != "execute_powershell":
        return False
    if not isinstance(result, dict):
        return False
    if result.get("timed_out"):
        return True
    returncode = result.get("returncode")
    return returncode is not None and returncode != 0


def needs_verification(tool_name, arguments):
    # Check if action changed (or could change) system state
    tier = classify_operation(tool_name, arguments)
    return tier is not RiskTier.READ


def annotate_result(result, annotation_type, attempt_count=None):
    # Add metadata notes to tool results for model guidance
    annotated = dict(result) if isinstance(result, dict) else {"result": result}
    
    if annotation_type == "recovery":
        if attempt_count > MAX_COMMAND_RETRIES:
            annotated["_recovery_note"] = (
                f"Command failed {attempt_count} times. Stop retrying it. "
                "Explain to user what was tried and why it failed, or ask for clarification."
            )
        else:
            annotated["_recovery_note"] = (
                f"Command failed (attempt {attempt_count} of {MAX_COMMAND_RETRIES}). "
                "Analyze error, don't repeat identical command. Either fix it, search for "
                "correct syntax, or try a different approach."
            )
    
    elif annotation_type == "verification":
        annotated["_verification_note"] = (
            "Action changed system state and appeared to complete. "
            "Perform a follow-up read-only check (search_files, get_folder_size, etc) "
            "to confirm the intended outcome happened before reporting success."
        )
    
    return annotated
