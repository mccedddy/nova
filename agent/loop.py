from agent.client import (
    OllamaUnavailableError,
    chat_stream,
    extract_tool_calls,
    get_final_text,
)
from agent.tool_registry import TOOL_REGISTRY
from agent.validation import validate_tool_call
from tools.schemas import TOOL_SCHEMAS

SYSTEM_PROMPT = """You are N.O.V.A. (Native Operating-system Virtual Assistant), a local AI agent that inspects this Windows system using the tools available to you.

Rules:
1. Read-only: you cannot delete, move, modify, uninstall, or change anything. Never tell the user something "is safe to delete" or recommend deleting/removing/uninstalling anything -- that judgment belongs to the user. You may describe signals neutrally (e.g. "unused for 90 days, in a temp folder") without concluding what to do about them.
2. Stay grounded: only state facts that appear in a tool result or something the user said in this conversation. Never invent version numbers, dates, file paths, other tools/integrations, or reasons why something is running. If speculating, mark it clearly as a guess ("possibly," "this could be").
3. Real values only: never answer with a placeholder like [username] or <YourUsername>. Use a tool to get the real value first.
4. Ambiguous requests: ask a clarifying question rather than guessing, especially before anything that sounds destructive.
5. No reliable answer: if a question isn't something your tools can determine (e.g. whether software is pirated), say so after 1-2 attempts rather than continuing to guess search patterns.
6. web_search: use it when you don't recognize something, or to check current info (e.g. latest version of something). Don't claim it or any other tool is "unavailable" unless you actually tried it and it failed. For "is X outdated" questions, always chain: check the local version first, then web_search for the latest, then compare -- don't stop after only the local check.
7. Don't over-search: after 2-3 searches on the same question, give your best answer with the uncertainty noted, rather than continuing to reformulate the query.
8. When calling a tool, include one short sentence in your response describing what you're checking. Don't show internal reasoning.
9. Keep answers direct. Use tables/bullets only when they genuinely help, not for single-fact answers. Avoid excessive emoji.
10. When summarizing from search results, distinguish between what a source directly states and any analysis/speculation in that source. Don't present a journalist's interpretation as a confirmed fact. If details are inconsistent or incomplete across snippets, say what's uncertain rather than filling gaps with your own inference.
11. If web_search snippets aren't detailed enough to answer confidently (e.g. comparing exact version numbers, or the user wants specifics beyond a summary), use fetch_page on the most relevant result URL to get real content instead of guessing from a fragment.
12. If a question needs location context (e.g. weather) and none was given, use get_approximate_location first, then web_search with that location."""

MAX_ITERATIONS = 10
MAX_RETRIES = 2


TOOL_PROGRESS_MESSAGES = {
    "add": "Calculating...",
    "get_system_diagnostics": "Analyzing system diagnostics...",
    "list_running_processes": "Checking running processes...",
    "get_network_connections": "Checking network connections...",
    "get_gpu_driver_info": "Analyzing GPU and driver information...",
    "get_disk_health": "Checking disk health...",
    "query_registry": "Inspecting the Windows registry...",
    "list_installed_apps": "Checking installed applications...",
    "search_files": "Searching files...",
    "get_folder_size": "Calculating folder size...",
    "analyze_file_relevance": "Analyzing file information...",
    "web_search": "Searching the web for information...",
    "fetch_page": "Checking information from web...",
    "get_approximate_location": "Checking location...",
}


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
        except OllamaUnavailableError as error:
            if printed_anything:
                print()
            messages.pop()
            return f"⚠ {error}"

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

        if printed_anything:
            print()

        messages.append(response["message"])

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            if not printed_anything:
                print(f"\n{TOOL_PROGRESS_MESSAGES.get(name, 'Working...')}")
            if show_debug_tools:
                print(f"→ calling {name}({args})")

            ok, validated = validate_tool_call(
                name, args, TOOL_REGISTRY, TOOL_SCHEMAS
            )

            if ok:
                try:
                    result = TOOL_REGISTRY[name](**validated)
                except Exception as error:
                    ok = False
                    validated = str(error)

            if not ok:
                failure_counts[name] = failure_counts.get(name, 0) + 1
                if failure_counts[name] > MAX_RETRIES:
                    result = (
                        f"error: {validated} -- giving up on '{name}' "
                        f"after {MAX_RETRIES} retries"
                    )
                else:
                    result = f"error: {validated} -- please retry with corrected arguments"

            if show_debug_tools:
                print(f"← result: {result}")

            messages.append({
                "role": "tool",
                "content": str(result),
            })

    return "I couldn't complete that after several tool calls -- something may be wrong with my tool use."
