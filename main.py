from agent.loop import run_turn
from agent.prompts import build_system_prompt

def main(show_debug_tools=False, show_full_output=False):
    print("N.O.V.A. -- type 'exit' or 'quit' to leave.\n")

    messages = [{"role": "system", "content": build_system_prompt()}]

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
            show_full_output=show_full_output
        )
        if answer:
            print(f"\n{answer}\n")
        else:
            print()  # just a trailing blank line after the streamed output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the NOVA system inspection assistant.")
    parser.add_argument(
        "--debug-tools",
        action="store_true",
        help="show raw tool names, arguments, and results while chatting",
    )
    parser.add_argument(
        "--full-output",
        action="store_true",
        help="show full untruncated tool results (only relevant with --debug-tools)",
    )
    args = parser.parse_args()
    main(show_debug_tools=args.debug_tools, show_full_output=args.full_output)