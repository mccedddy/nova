import threading

from agent.client import chat, extract_tool_calls, get_final_text, OllamaUnavailableError
from agent.permissions import PermissionDenied, execute_tool
from agent.recovery import annotate_command_failure, is_execution_failure
from agent.verification import annotate_verification_reminder, needs_verification
from agent.tool_registry import TOOL_REGISTRY
from agent.validation import validate_tool_call
from agent.progress import format_tool_progress
from tools.tool_schemas import TOOL_SCHEMAS
from settings import MAX_ITERATIONS, MAX_RETRIES

PENDING_PERMISSIONS = {}

class PermissionRequest:
    def __init__(self, details):
        self.details = details
        self.event = threading.Event()
        self.approved = False


def resolve_permission(conversation_id, approved):
    permission = PENDING_PERMISSIONS.get(conversation_id)

    if permission is None:
        return False

    permission.approved = bool(approved)
    permission.event.set()

    return True


def _request_api_confirmation(conversation_id, details):
    permission = PermissionRequest(details)
    PENDING_PERMISSIONS[conversation_id] = permission

    return permission


def _summarize_gathered_results(messages):
    synthesis_messages = messages + [{
        "role": "user",
        "content": (
            "The tool-call limit has been reached. Answer the original user request now "
            "using only the confirmed information already gathered. State clearly what "
            "could not be verified. Do not call any tools."
        ),
    }]

    try:
        response = chat(synthesis_messages, tools=[])
    except OllamaUnavailableError:
        return None

    final_text = get_final_text(response)
    return final_text.strip() or None


def run_turn_events(user_input, messages, conversation_id):
    messages.append({
        "role": "user",
        "content": user_input,
    })

    failure_counts = {}
    command_failure_counts = {}
    tool_call_counter = 0

    for _ in range(MAX_ITERATIONS):
        try:
            response = chat(messages, tools=TOOL_SCHEMAS)
        except OllamaUnavailableError as e:
            messages.pop()
            yield {
                "type": "error",
                "text": str(e),
            }
            return

        tool_calls = extract_tool_calls(response)

        if not tool_calls:
            final_text = get_final_text(response)

            if not final_text.strip():
                yield {
                    "type": "error",
                    "text": (
                        "I gathered information but ran out of room to summarize it "
                        "(too much data from the tool results). Try asking a more "
                        "specific question, like checking one folder or location at a time."
                    ),
                }
                return

            messages.append({
                "role": "assistant",
                "content": final_text,
            })

            yield {
                "type": "answer",
                "text": final_text,
            }

            return

        messages.append(response["message"])

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            tool_call_counter += 1

            yield {
                "type": "tool_started",
                "name": name,
                "args": args,
                "display": format_tool_progress(
                    tool_call_counter,
                    name,
                    args,
                ),
            }

            ok, validated = validate_tool_call(
                name,
                args,
                TOOL_REGISTRY,
                TOOL_SCHEMAS,
            )

            permission_error = False

            if ok:
                try:
                    # ---------------------------------------------------------
                    # READ-ONLY TOOLS EXECUTE IMMEDIATELY.
                    #
                    # MODIFY / DESTRUCTIVE TOOLS pause here and wait for
                    # Electron to send Y/N through /permission.
                    # ---------------------------------------------------------

                    permission_request = None

                    # We cannot directly yield from a callback passed into
                    # execute_tool, so inspect the operation first.
                    from agent.permissions import (
                        classify_operation,
                        RiskTier,
                        confirmation_details,
                    )

                    tier = classify_operation(name, validated)

                    if tier is RiskTier.READ:
                        result = execute_tool(
                            name,
                            validated,
                            TOOL_REGISTRY,
                        )

                    else:
                        details = confirmation_details(
                            name,
                            validated,
                            tier,
                        )

                        permission = _request_api_confirmation(
                            conversation_id,
                            details,
                        )

                        yield {
                            "type": "permission_requested",
                            "name": name,
                            "args": validated,
                            "details": details,
                            "tier": tier.value,
                        }

                        permission.event.wait()

                        PENDING_PERMISSIONS.pop(
                            conversation_id,
                            None,
                        )

                        if not permission.approved:
                            raise PermissionDenied(
                                f"user declined this action:\n{details}"
                            )

                        result = execute_tool(
                            name,
                            validated,
                            TOOL_REGISTRY,
                            already_confirmed=True,
                        )
                except PermissionDenied as e:
                    ok = False
                    permission_error = True
                    validated = str(e)

                except Exception as e:
                    ok = False
                    validated = str(e)

            if ok and is_execution_failure(name, result):
                command_failure_counts[name] = (
                    command_failure_counts.get(name, 0) + 1
                )

                result = annotate_command_failure(
                    result,
                    command_failure_counts[name],
                )

            elif ok and needs_verification(name, validated):
                result = annotate_verification_reminder(result)

            if not ok:
                if permission_error:
                    result = f"error: {validated}"
                else:
                    failure_counts[name] = (
                        failure_counts.get(name, 0) + 1
                    )

                    if failure_counts[name] > MAX_RETRIES:
                        result = (
                            f"error: {validated} -- "
                            f"giving up on '{name}' after {MAX_RETRIES} retries"
                        )
                    else:
                        result = (
                            f"error: {validated} -- "
                            f"please retry with corrected arguments"
                        )

            yield {
                "type": "tool_finished",
                "name": name,
                "result": str(result),
            }

            messages.append({
                "role": "tool",
                "content": str(result),
            })

            if permission_error:
                yield {
                    "type": "error",
                    "text": (
                        "The action was not executed because confirmation "
                        "was declined."
                    ),
                }
                return

    final_text = _summarize_gathered_results(messages)

    if final_text:
        messages.append({
            "role": "assistant",
            "content": final_text,
        })

        yield {
            "type": "answer",
            "text": final_text,
        }

        return

    yield {
        "type": "error",
        "text": "I gathered information but couldn't produce a final answer from it.",
    }