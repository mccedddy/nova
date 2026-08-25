from datetime import datetime
from agent.loop import run_turn, SYSTEM_PROMPT

def main(show_debug_tools=False):
    print("N.O.V.A. -- type 'exit' or 'quit' to leave.\n")

    current_date = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
    system_prompt_with_date = f"{SYSTEM_PROMPT}\n\nToday's real date and time is {current_date}. Use this for any date/time-relative reasoning -- do not guess or assume what year or date it is."

    messages = [{"role": "system", "content": system_prompt_with_date}]

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if user_input.lower() in ("exit", "quit"):
            print("Exiting.")
            break

        if not user_input:
            continue

        answer = run_turn(
            user_input,
            messages,
            show_debug_tools=show_debug_tools,
        )
        print(f"\n{answer}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the NOVA system inspection assistant.")
    parser.add_argument(
        "--debug-tools",
        action="store_true",
        help="show raw tool names, arguments, and results while chatting",
    )
    args = parser.parse_args()
    main(show_debug_tools=args.debug_tools)