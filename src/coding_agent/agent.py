from coding_agent.core.log_manager import get_logger
from coding_agent.core.state import AgentState, AgentStatus
from coding_agent.phases.trigger import trigger
from coding_agent.phases.act import act
from coding_agent.phases.verify import verify

logger = get_logger(__name__)


def run_agent(task: str) -> AgentState:
    """
    Entry point for the coding agent.
    Runs Trigger → Act → Verify and returns final AgentState.

    Args:
        task: Raw user prompt describing the coding task.

    Returns:
        AgentState with status and final_output populated.
    """
    sandbox = None

    try:
        # ── Phase 1: Trigger ───────────────────────────────────────────
        state, sandbox = trigger(task)

        # ── Phase 2: Act ───────────────────────────────────────────────
        state = act(state)

        # ── Phase 3: Verify ────────────────────────────────────────────
        state = verify(state, act_fn=act)

    except Exception as e:
        logger.error(f"Agent crashed: {e}", exc_info=True)
        if 'state' not in locals():
            state = AgentState(
                task=task,
                working_dir="",
                log_path="",
            )
        state.status = AgentStatus.FAILED
        state.final_output = f"Agent crashed with error: {e}"

    finally:
        # ── Cleanup sandbox regardless of outcome ──────────────────────
        # if sandbox is not None:
            # sandbox.stop()
        print("completed")

    return state