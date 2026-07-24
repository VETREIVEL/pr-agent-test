import os
from dotenv import load_dotenv
from agent import PRAgent

load_dotenv()

def main():
    repo = os.environ.get("GITHUB_REPO", "")
    print(f"\nPR Review Agent — repo: {repo}")
    print("Commands: 'list' to see open PRs, 'exit' to quit")
    print("Example: 'review PR #5' or 'what does PR 3 change?'\n")

    agent = PRAgent()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Bye.")
            break

        print("Agent: ", end="", flush=True)
        response = agent.chat(user_input)
        print(response)
        print()

if __name__ == "__main__":
    main()
