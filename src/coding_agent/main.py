# src/coding_agent/main.py

from coding_agent.agent import run_agent
from coding_agent.core.log_manager import get_logger
from coding_agent.core.state import AgentStatus

logger = get_logger(__name__)


def main():
    print("=== Coding Agent ===")
    print("Type 'exit' to quit.\n")

    while True:
        task = input("Task > ").strip()

        if not task:
            continue

        if task.lower() == "exit":
            print("Goodbye.")
            break

        logger.info(f"Starting agent for task: {task}")
        state = run_agent(task)

        print("\n=== Result ===")
        print(f"Status  : {state.status.value}")
        print(f"Output  : {state.final_output}")
        print(f"Files   : {state.files_touched or 'None'}")
        print(f"Working : {state.working_dir}")
        print()


if __name__ == "__main__":
    main()