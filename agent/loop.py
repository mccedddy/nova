from agent.client import chat, extract_tool_calls, get_final_text, OllamaUnavailableError
from agent.validation import validate_tool_call
from tools.system import get_system_diagnostics

MAX_ITERATIONS = 6
MAX_RETRIES = 2


def add(a, b):
    return a + b


TOOL_REGISTRY = {
    "add": add,
    "get_system_diagnostics": get_system_diagnostics,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "Add two numbers together",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_diagnostics",
            "description": (
                "Get current system diagnostics: CPU usage and core count, "
                "RAM total/used/percent, per-drive disk space, and OS "
                "name/version/build/uptime. No arguments needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def run_turn(user_input, messages):
    messages.append({"role": "user", "content": user_input})
    failure_counts = {}  # tracks validation/execution failures per tool name this turn

    for _ in range(MAX_ITERATIONS):
        try:
            response = chat(messages, tools=TOOL_SCHEMAS)
        except OllamaUnavailableError as e:
            messages.pop()
            return f"⚠ {e}"

        tool_calls = extract_tool_calls(response)

        if not tool_calls:  
            final_text = get_final_text(response)
            messages.append({"role": "assistant", "content": final_text})
            return final_text

        messages.append(response["message"])

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

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

            print(f"\u2190 result: {result}")

            messages.append({
                "role": "tool",
                "content": str(result),
            })

    return "I couldn't complete that after several tool calls -- something may be wrong with my tool use."