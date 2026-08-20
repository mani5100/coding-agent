# src/coding_agent/nodes/coder/node.py

from coding_agent.graph.state import GraphState, PlanItem
from coding_agent.core.state import AgentStatus
from coding_agent.core.log_manager import get_logger
from coding_agent.nodes.coder.helpers import build_task_from_plan_item
from coding_agent.nodes.planner.helpers import get_current_plan_item
import coding_agent.tools.shell_exec as shell_exec_module

logger = get_logger(__name__)


def _mark_item_status(state: GraphState, item_id: str, status: str) -> None:
    """
    Updates the status of a PlanItem in place.
    Checks both main plan and sub_plan.
    """
    for item in state.get("plan", []):
        if item.id == item_id:
            item.status = status
            return

    for item in state.get("sub_plan", []):
        if item.id == item_id:
            item.status = status
            return

    logger.warning(f"Item {item_id} not found in any plan for status update")


def coder_node(state: GraphState) -> GraphState:
    """
    Coder node — wraps existing run_agent() as a LangGraph node.

    Reads current PlanItem from state.
    Builds task string with full project context.
    Runs the existing Trigger → Act → Verify agent loop.
    Always routes to Tester regardless of success or failure.
    """

    # ── Get current item ──────────────────────────────────────────────────────
    current_item = get_current_plan_item(state)

    if current_item is None:
        logger.error("Coder: no current plan item found. Terminating.")
        return {
            **state,
            "routing_decision": "end",
        }

    logger.info(f"Coder: starting item [{current_item.id}] {current_item.title}")

    # ── Mark as in progress ───────────────────────────────────────────────────
    _mark_item_status(state, current_item.id, "in_progress")

    # ── Build task string ─────────────────────────────────────────────────────
    task_str = build_task_from_plan_item(state)

    if task_str is None:
        logger.error("Coder: failed to build task string. Terminating.")
        _mark_item_status(state, current_item.id, "failed")
        return {
            **state,
            "routing_decision": "end",
        }

    # ── Run existing agent ────────────────────────────────────────────────────
    from coding_agent.agent import run_agent

    agent_state = run_agent(
        task=task_str,
        working_dir=state.get("working_dir"),
        sandbox=shell_exec_module._sandbox,
        stop_sandbox=False,
    )

    # ── Process result ────────────────────────────────────────────────────────
    if agent_state.status == AgentStatus.FAILED:
        logger.warning(f"Coder: agent failed for item [{current_item.id}]")
        _mark_item_status(state, current_item.id, "failed")
        code_output = f"FAILED: {agent_state.final_output}"
    else:
        logger.info(f"Coder: agent completed item [{current_item.id}]")
        _mark_item_status(state, current_item.id, "done")
        code_output = agent_state.final_output or ""

    # ── Advance index ─────────────────────────────────────────────────────────
    current_index = state.get("current_item_index", 0)


    return {
        **state,
        "code_output": code_output,
        "current_item_index": current_index,
        "routing_decision": "tester",
    }