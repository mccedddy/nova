from agent.client import chat, extract_tool_calls, get_final_text

MAX_ITERATIONS = 6  # hard cap so a confused model can't loop forever


# --- fake tool for Phase 1 (proves the loop works before real tools exist) ---

def add(a, b):
    return a + b


TOOL_REGISTRY = {
    "add": add,
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
    }
]


def run_turn(user_input, messages):
    # messages is the running conversation history, passed in from main.py
    # so it persists across turns (Phase 5 wants follow-up context to work)
    messages.append({"role": "user", "content": user_input})

    for _ in range(MAX_ITERATIONS):
        response = chat(messages, tools=TOOL_SCHEMAS)
        tool_calls = extract_tool_calls(response)

        if not tool_calls:
            # no tool call -- model is giving its final answer
            final_text = get_final_text(response)
            messages.append({"role": "assistant", "content": final_text})
            return final_text

        # model wants to call a tool -- record the assistant's tool call
        # request in history, then execute it and feed the result back
        messages.append(response["message"])

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            print(f"\u2192 calling {name}({args})")

            func = TOOL_REGISTRY.get(name)
            if func is None:
                result = f"error: unknown tool '{name}'"
            else:
                try:
                    result = func(**args)
                except Exception as e:
                    result = f"error: {e}"

            print(f"\u2190 result: {result}")

            messages.append({
                "role": "tool",
                "content": str(result),
            })

    # hit MAX_ITERATIONS without a final answer -- give up gracefully
    return "I couldn't complete that after several tool calls -- something may be wrong with my tool use."