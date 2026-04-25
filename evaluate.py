from datetime import date

from agent import Agent


def run_case(name: str, turns: list[str]) -> None:
    agent = Agent(today=date(2026, 4, 24))
    print(f"\n=== {name} ===")
    for turn in turns:
        result = agent.next(turn)
        print(f"USER: {turn}")
        print(f"AGENT: {result['message']}")


def main() -> None:
    run_case(
        "Successful Flow",
        [
            "hello",
            "ACC1001",
            "Nithin Jain",
            "1990-05-14",
            "pay 500",
            "name on card: Nithin Jain",
            "4532015112830366",
            "cvv 123",
            "12/2027",
        ],
    )
    run_case(
        "Verification Failure",
        [
            "ACC1001",
            "Wrong Name",
            "full name: Wrong Name pincode 400001",
            "full name: Still Wrong pincode 400001",
            "full name: No Match pincode 400001",
        ],
    )
    run_case(
        "Payment Failure",
        [
            "ACC1002",
            "Rajarajeswari Balasubramaniam",
            "9876",
            "pay 500",
            "name on card: Rajarajeswari Balasubramaniam",
            "4111111111111111",
            "cvv 123",
            "01/2020",
            "12/2027",
        ],
    )


if __name__ == "__main__":
    main()
