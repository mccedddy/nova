from agent.client import chat, extract_tool_calls, get_final_text, OllamaUnavailableError
from agent.permissions import PermissionDenied, execute_tool
from agent.recovery import annotate_command_failure, is_execution_failure
from agent.tool_registry import TOOL_REGISTRY
from agent.validation import validate_tool_call
from tools.tool_schemas import TOOL_SCHEMAS

MAX_ITERATIONS = 8
MAX_RETRIES = 2


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


def run_turn_events(user_input, messages):
    messages.append({"role": "user", "content": user_input})
    failure_counts = {}
    command_failure_counts = {}

    for _ in range(MAX_ITERATIONS):
        try:
            response = chat(messages, tools=TOOL_SCHEMAS)
        except OllamaUnavailableError as e:
            messages.pop()
            yield {"type": "error", "text": str(e)}
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
            messages.append({"role": "assistant", "content": final_text})
            yield {"type": "answer", "text": final_text}
            return

        messages.append(response["message"])

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            yield {"type": "tool_started", "name": name, "args": args}

            ok, validated = validate_tool_call(name, args, TOOL_REGISTRY, TOOL_SCHEMAS)
            permission_error = False

            if ok:
                try:
                    result = execute_tool(name, validated, TOOL_REGISTRY)
                except PermissionDenied as e:
                    ok = False
                    permission_error = True
                    validated = str(e)
                except Exception as e:
                    ok = False
                    validated = str(e)

            if ok and is_execution_failure(name, result):
                command_failure_counts[name] = command_failure_counts.get(name, 0) + 1
                result = annotate_command_failure(result, command_failure_counts[name])

            if not ok:
                if permission_error:
                    result = f"error: {validated}"
                else:
                    failure_counts[name] = failure_counts.get(name, 0) + 1
                    if failure_counts[name] > MAX_RETRIES:
                        result = f"error: {validated} -- giving up on '{name}' after {MAX_RETRIES} retries"
                    else:
                        result = f"error: {validated} -- please retry with corrected arguments"

            yield {"type": "tool_finished", "name": name, "result": str(result)}

            messages.append({
                "role": "tool",
                "content": str(result),
            })

            if permission_error:
                yield {
                    "type": "error",
                    "text": "The action was not executed because confirmation was declined.",
                }
                return

    final_text = _summarize_gathered_results(messages)
    if final_text:
        messages.append({"role": "assistant", "content": final_text})
        yield {"type": "answer", "text": final_text}
        return

    yield {
        "type": "error",
        "text": "I gathered information but couldn't produce a final answer from it.",
    }