from agent.loop import run_turn

def main():
    print("N.O.V.A. -- type 'exit' or 'quit' to leave.\n")
    messages = []  # in-memory conversation history, session-only per SAFETY.md scope

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

        answer = run_turn(user_input, messages)
        print(f"\n{answer}\n")


if __name__ == "__main__":
    main()