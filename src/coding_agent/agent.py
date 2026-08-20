# src/coding_agent/agent.py

import uuid
from pathlib import Path

from coding_agent.core.config import settings
from coding_agent.core.log_manager import get_logger
from coding_agent.core.state import AgentState, AgentStatus
from coding_agent.graph.state import GraphState
from coding_agent.phases.trigger import trigger
from coding_agent.phases.act import act
from coding_agent.phases.verify import verify

logger = get_logger(__name__)


# ── Single Task Agent (existing, unchanged behavior) ──────────────────────────

def run_agent(
    task: str,
    working_dir: str | None = None,
    sandbox=None,                    # ← ADD: reuse existing sandbox
    stop_sandbox: bool = True,       # ← ADD: False when called from graph
) -> AgentState:

    _sandbox = None

    try:
        state, _sandbox = trigger(task, working_dir=working_dir, sandbox=sandbox)
        state = act(state)
        state = verify(state, act_fn=act)

    except Exception as e:
        logger.error(f"Agent crashed: {e}", exc_info=True)
        if "state" not in locals():
            state = AgentState(
                task=task,
                working_dir=working_dir or "",
                log_path="",
            )
        state.status = AgentStatus.FAILED
        state.final_output = f"Agent crashed: {e}"

    finally:
        # Only stop sandbox if we own it
        if stop_sandbox and _sandbox is not None and sandbox is None:
            _sandbox.stop()

    return state


# ── Graph Entry Point (new) ───────────────────────────────────────────────────
def run_graph(task: str) -> GraphState:
    """
    Runs the full multi-agent LangGraph pipeline.
    Planner → Coder → Tester → Reviewer

    Creates a shared workspace for all plan items.
    Returns the final GraphState with docs and plan statuses.
    """
    from coding_agent.graph.graph import coding_agent_graph
    from coding_agent.sandbox.docker_sandbox import DockerSandbox
    from coding_agent.tools.shell_exec import set_sandbox

    session_id = uuid.uuid4().hex[:8]
    working_dir = settings.base_working_dir / session_id
    working_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(working_dir / settings.log_filename)

    logger.info(f"=== GRAPH RUN START ===")
    logger.info(f"Session ID  : {session_id}")
    logger.info(f"Working dir : {working_dir}")

    # ── Create sandbox ONCE for entire graph run ───────────────────────────
    sandbox = DockerSandbox(working_dir=str(working_dir))
    sandbox.start()
    set_sandbox(sandbox)
    logger.info("Graph sandbox started.")

    initial_state: GraphState = {
        "task":               task,
        "working_dir":        str(working_dir),
        "session_id":         session_id,
        "plan":               [],
        "sub_plan":           [],
        "current_plan":       "main",
        "current_item_index": 0,
        "code_output":        None,
        "test_results":       None,
        "review_output":      None,
        "task_docs":          [],
        "final_doc":          None,
        "routing_decision":   "",
        "iteration":          0,
        "max_iterations":     settings.max_iterations,
        "log_path": log_path,
    }

    try:
        final_state: GraphState = coding_agent_graph.invoke(initial_state)
        logger.info("=== GRAPH RUN COMPLETE ===")
        return final_state

    except Exception as e:
        logger.error(f"Graph run crashed: {e}", exc_info=True)
        return {
            **initial_state,
            "routing_decision": "end",
            "final_doc": f"Graph crashed: {e}",
        }

    finally:
        # ── Stop sandbox when entire graph is done ─────────────────────────
        sandbox.stop()
        logger.info("Graph sandbox stopped.")