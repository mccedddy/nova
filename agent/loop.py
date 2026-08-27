from agent.client import chat, extract_tool_calls, get_final_text, OllamaUnavailableError
from agent.progress import TOOL_PROGRESS_MESSAGES
from agent.permissions import PermissionDenied, execute_tool, request_confirmation
from agent.tool_registry import TOOL_REGISTRY
from agent.validation import validate_tool_call
from tools.tool_schemas import TOOL_SCHEMAS

MAX_ITERATIONS = 10
MAX_RETRIES = 2
MAX_TERMINAL_CHARS = 1000


def _truncate_for_terminal(text, max_chars=MAX_TERMINAL_CHARS):
    text = str(text)
    if len(text) <= max_chars:
        return text
    remaining = len(text) - max_chars
    return text[:max_chars] + f"\n... (+{remaining} more characters, full data available to the model)"


def run_turn(user_input, messages, show_debug_tools=False, show_full_output=False):
    messages.append({"role": "user", "content": user_input})
    failure_counts = {}

    for _ in range(MAX_ITERATIONS):
        try:
            response = chat(messages, tools=TOOL_SCHEMAS)
        except OllamaUnavailableError as e:
            messages.pop()
            return f"⚠ {e}"

        tool_calls = extract_tool_calls(response)

        if not tool_calls:
            final_text = get_final_text(response)
            if not final_text.strip():
                return (
                    "⚠ I gathered information but ran out of room to summarize it "
                    "(too much data from the tool results). Try asking a more "
                    "specific question, like checking one folder or location at a time."
                )
            messages.append({"role": "assistant", "content": final_text})
            return final_text

        messages.append(response["message"])

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            print(f"\n{TOOL_PROGRESS_MESSAGES.get(name, 'Working...')}")
            if show_debug_tools:
                print(f"\u2192 calling {name}({args})")

            ok, validated = validate_tool_call(name, args, TOOL_REGISTRY, TOOL_SCHEMAS)
            permission_error = False

            if ok:
                try:
                    result = execute_tool(
                        name,
                        validated,
                        TOOL_REGISTRY,
                        confirmation_callback=request_confirmation,
                    )
                except PermissionDenied as e:
                    ok = False
                    permission_error = True
                    validated = str(e)
                except Exception as e:
                    ok = False
                    validated = str(e)

            if not ok:
                if permission_error:
                    result = f"error: {validated}"
                else:
                    failure_counts[name] = failure_counts.get(name, 0) + 1
                    if failure_counts[name] > MAX_RETRIES:
                        result = f"error: {validated} -- giving up on '{name}' after {MAX_RETRIES} retries"
                    else:
                        result = f"error: {validated} -- please retry with corrected arguments"

            if show_debug_tools:
                displayed_result = result if show_full_output else _truncate_for_terminal(result)
                print(f"\u2190 result: {displayed_result}")

            messages.append({
                "role": "tool",
                "content": str(result),
            })

    return "I couldn't complete that after several tool calls -- something may be wrong with my tool use."