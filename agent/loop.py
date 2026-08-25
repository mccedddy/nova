from agent.client import chat_stream, extract_tool_calls, get_final_text, OllamaUnavailableError
from agent.progress import TOOL_PROGRESS_MESSAGES
from agent.tool_registry import TOOL_REGISTRY
from agent.validation import validate_tool_call
from tools.tool_schemas import TOOL_SCHEMAS

MAX_ITERATIONS = 10
MAX_RETRIES = 2


def run_turn(user_input, messages, show_debug_tools=False):
    messages.append({"role": "user", "content": user_input})
    failure_counts = {}

    for _ in range(MAX_ITERATIONS):
        printed_anything = False

        def on_token(piece):
            nonlocal printed_anything
            printed_anything = True
            print(piece, end="", flush=True)

        try:
            response = chat_stream(messages, tools=TOOL_SCHEMAS, on_token=on_token)
        except OllamaUnavailableError as e:
            if printed_anything:
                print()
            messages.pop()
            return f"⚠ {e}"

        tool_calls = extract_tool_calls(response)

        if not tool_calls:
            final_text = get_final_text(response)
            if not final_text.strip():
                if printed_anything:
                    print()
                return (
                    "⚠ I gathered information but ran out of room to summarize it "
                    "(too much data from the tool results). Try asking a more "
                    "specific question, like checking one folder or location at a time."
                )
            messages.append({"role": "assistant", "content": final_text})
            print()
            return ""

        # Execute requested tools after any streamed status text is closed.
        if printed_anything:
            print()

        messages.append(response["message"])

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            if not printed_anything:
                print(f"\n{TOOL_PROGRESS_MESSAGES.get(name, 'Working...')}")
            if show_debug_tools:
                print(f"\u2192 calling {name}({args})")

            ok, validated = validate_tool_call(name, args, TOOL_REGISTRY, TOOL_SCHEMAS)

            if ok:
                try:
                    result = TOOL_REGISTRY[name](**validated)
                except Exception as e:
                    ok = False
                    validated = str(e)

            if not ok:
                failure_counts[name] = failure_counts.get(name, 0) + 1
                if failure_counts[name] > MAX_RETRIES:
                    result = f"error: {validated} -- giving up on '{name}' after {MAX_RETRIES} retries"
                else:
                    result = f"error: {validated} -- please retry with corrected arguments"

            if show_debug_tools:
                print(f"\u2190 result: {result}")

            messages.append({
                "role": "tool",
                "content": str(result),
            })

    return "I couldn't complete that after several tool calls -- something may be wrong with my tool use."
