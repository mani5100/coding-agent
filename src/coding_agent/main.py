# src/coding_agent/main.py

from coding_agent.agent import run_agent
from coding_agent.core.log_manager import get_logger
from coding_agent.core.state import AgentStatus

logger = get_logger(__name__)


def get_multiline_input() -> str:
    """
    Collect multi-line input from user.
    User types their prompt across multiple lines.
    Submit with a blank line (press Enter twice).
    """
    print("Enter your task (press Enter twice to submit):")
    lines = []
    while True:
        line = input()
        if line == "":
            if lines:
                break
        else:
            lines.append(line)
    return "\n".join(lines)


def main():
    print("=== Coding Agent ===")
    print("Type 'exit' on a blank line to quit.\n")

    while True:
        try:
            task = get_multiline_input()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if task.strip().lower() == "exit":
            print("Goodbye.")
            break

        if not task.strip():
            continue

        logger.info(f"Starting agent for task: {task[:100]}...")
        state = run_agent(task)

        print("\n=== Result ===")
        print(f"Status  : {state.status.value}")
        print(f"Output  : {state.final_output}")
        print(f"Files   : {state.files_touched or 'None'}")
        print(f"Working : {state.working_dir}")
        print()


if __name__ == "__main__":
    main()