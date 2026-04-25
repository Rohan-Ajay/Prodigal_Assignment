from agent import Agent


def main() -> None:
    agent = Agent()
    print("Payment agent ready. Please enter your account ID to begin. Type `exit` to stop.")
    while True:
        try:
            user_input = input("You: ")
        except EOFError:
            break
        if user_input.strip().lower() in {"exit", "quit"}:
            break
        reply = agent.next(user_input)
        print(f"Agent: {reply['message']}")


if __name__ == "__main__":
    main()
