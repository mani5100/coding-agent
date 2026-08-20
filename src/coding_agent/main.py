# src/coding_agent/main.py

from coding_agent.agent import run_graph
from coding_agent.core.log_manager import get_logger
from coding_agent.nodes.planner.helpers import format_plan_for_prompt

logger = get_logger(__name__)


def get_multiline_input() -> str:
    """
    Collect multi-line input from user.
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

        logger.info(f"Starting graph for task: {task[:100]}...")

        state = run_graph(task)

        # ── Result ─────────────────────────────────────────────────────────
        print("\n=== Result ===")
        print(f"Session     : {state.get('session_id', 'unknown')}")
        print(f"Working Dir : {state.get('working_dir', 'unknown')}")
        print()

        # ── Plan Summary ───────────────────────────────────────────────────
        plan = state.get("plan", [])
        if plan:
            print("Plan Summary:")
            for item in plan:
                status = item.status.upper()
                print(f"  [{status}] {item.id}: {item.title}")
            print()

        # ── Sub Plan (if used) ─────────────────────────────────────────────
        sub_plan = state.get("sub_plan", [])
        if sub_plan:
            print("Sub Plan:")
            for item in sub_plan:
                status = item.status.upper()
                print(f"  [{status}] {item.id}: {item.title}")
            print()

        # ── Documentation ──────────────────────────────────────────────────
        working_dir = state.get("working_dir", "")
        if state.get("final_doc"):
            doc_path = f"{working_dir}/DOCUMENTATION.md"
            print(f"Documentation : {doc_path}")
        else:
            print("Documentation : Not generated")

        # ── Test Results ───────────────────────────────────────────────────
        test_results = state.get("test_results")
        if test_results:
            print(f"\nTest Results  :\n{test_results[:300]}")

        print()


if __name__ == "__main__":
    main()